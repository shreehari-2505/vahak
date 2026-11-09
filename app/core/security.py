"""
Vahak — The Bouncer (Security Core)
───────────────────────────────────────────────────────────────────────────────
This module is the most critical logic in the Vahak system. It implements the
hermetic Vault seal AND the OS-level filename sanitizer.

Every path received from the network is resolved to its absolute disk location
and verified to be a strict descendant of VAULT_DIR before any disk operation
is allowed to proceed.

The dependency injection shim (dependencies.py) that previously wrapped this
module has been killed. Routes call resolve_safe_path() and sanitize_filename()
explicitly — no implicit DI, no parameter-name mismatches, no silent bypasses.

Attack Vectors Neutralised
───────────────────────────
  ✗  Classic traversal        ../../../etc/shadow
  ✗  URL-encoded traversal    %2e%2e%2fetc%2fshadow  (FastAPI decodes before us)
  ✗  Absolute path injection  /etc/shadow  (lstrip removes leading slashes)
  ✗  Null-byte injection      foo\\x00../etc/shadow  (Path.resolve() handles this)
  ✗  Symlink escape           link -> /etc  (resolve() follows symlinks first)
  ✗  Filename traversal       filename=../../etc/cron.d/evil  (sanitize_filename strips)
  ✗  Oversized filename       AAAA...300 chars  (clamped to 255 byte ext4 limit)
  ✗  Control characters       \\x00 \\x1f embedded in names  (stripped)
  ✗  Windows reserved names   CON, PRN, NUL, AUX, COM1-9  (rejected)

The function does NOT raise on a path that does not yet exist on disk — that
is intentional so the push endpoint can safely create new subdirectories inside
the Vault without triggering a false positive.
"""

import re
from pathlib import Path

from fastapi import HTTPException, status

from app.core.config import VAULT_DIR

# ── Path Traversal Defence ─────────────────────────────────────────────────────

def resolve_safe_path(requested_path: str) -> Path:
    """
    Resolve `requested_path` to an absolute Path that is guaranteed to be
    inside VAULT_DIR. Raises HTTP 403 immediately on any traversal attempt.

    Parameters
    ----------
    requested_path:
        A raw path string received from a network request (query param, URL
        segment, or form field). Treated as untrusted input.

    Returns
    -------
    Path
        The fully-resolved absolute Path inside the Vault.

    Raises
    ------
    HTTPException(403)
        If the resolved path escapes the Vault boundary by any mechanism.
    """
    # Strip leading slashes / backslashes to neutralise absolute path injection.
    # A value like "/etc/passwd" becomes "etc/passwd" and resolves inside Vault.
    clean_path: str = requested_path.lstrip("/\\")

    # Resolve to the canonical absolute path.
    # Path.resolve() expands ".." components AND follows symlinks, so a symlink
    # pointing outside the Vault is caught here rather than at open() time.
    target_path: Path = (VAULT_DIR / clean_path).resolve()

    # The single invariant that must hold: the target must be inside the Vault.
    # is_relative_to() is False if target_path == VAULT_DIR itself only when
    # clean_path is empty — that case is valid (listing the root Vault dir).
    if not target_path.is_relative_to(VAULT_DIR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "CRITICAL: Path traversal violation detected. "
                "All access is restricted to the VahakVault directory."
            ),
        )

    return target_path


# ── Filename Sanitiser ─────────────────────────────────────────────────────────

# Characters illegal on Windows or dangerous on any OS (null bytes, control
# characters, path separators, shell metacharacters).
_UNSAFE_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Windows reserved device names. These cannot be used as filenames on NTFS even
# with extensions (e.g. "CON.txt" is illegal). Since Vault files may be synced
# to Windows devices, reject them unconditionally.
_WINDOWS_RESERVED: frozenset[str] = frozenset({
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
})

# ext4/btrfs hard limit on filename byte length (NOT character length).
_MAX_FILENAME_BYTES: int = 255


def sanitize_filename(raw: str) -> str:
    """
    Strip path separators, control characters, and OS-reserved names from a
    raw filename received in a multipart upload payload.

    Parameters
    ----------
    raw:
        The raw `UploadFile.filename` string. Treated as fully untrusted.

    Returns
    -------
    str
        A safe filename suitable for `Path() /` composition.

    Raises
    ------
    HTTPException(400)
        If the filename is empty, consists of only dots, or is a Windows
        reserved device name after sanitisation.
    """
    # Extract basename — discard any directory components the client injected
    name = raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    # Replace control characters and OS-unsafe characters with underscores
    name = _UNSAFE_FILENAME_RE.sub("_", name)

    # Strip leading/trailing whitespace and dots (Windows rejects trailing dots)
    name = name.strip(" .")

    # Reject Windows reserved device names (case-insensitive, with or without
    # extension — "CON.txt" is just as illegal as "CON")
    stem = name.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Filename '{raw}' uses a reserved device name.",
        )

    # Clamp to ext4 255-byte limit, preserving the file extension
    raw_bytes = name.encode("utf-8")
    if len(raw_bytes) > _MAX_FILENAME_BYTES:
        stem_part, dot, ext = name.rpartition(".")
        ext_bytes = ext.encode("utf-8")
        if dot and len(ext_bytes) < _MAX_FILENAME_BYTES - 1:
            # Trim the stem, keep the extension
            max_stem_bytes = _MAX_FILENAME_BYTES - len(ext_bytes) - 1  # 1 for the dot
            trimmed_stem = stem_part.encode("utf-8")[:max_stem_bytes].decode("utf-8", errors="ignore")
            name = trimmed_stem + "." + ext
        else:
            # No extension or extension itself is too long — brute truncate
            name = raw_bytes[:_MAX_FILENAME_BYTES].decode("utf-8", errors="ignore")

    # Final sanity gate
    if not name or name in (".", ".."):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload rejected: filename is empty or invalid after sanitisation.",
        )

    return name
