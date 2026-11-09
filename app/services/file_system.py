"""
Vahak — File System Service
───────────────────────────────────────────────────────────────────────────────
Abstracted OS-level disk operations. All functions operate on Path objects that
have already been validated by the Bouncer — this layer never performs its own
security checks. Routes must not call this module directly with raw strings.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict


class FileEntry(TypedDict):
    """Serialisable descriptor for a single directory entry."""
    name: str
    is_dir: bool
    size_bytes: int
    modified_at: str  # ISO 8601 UTC, e.g. "2026-10-29T06:15:00Z"
    relative_path: str  # Relative to VAULT_DIR root, for client navigation


def _entry_to_dict(entry: os.DirEntry, vault_root: Path) -> FileEntry:
    """Convert a single os.DirEntry into a serialisable FileEntry dict."""
    stat = entry.stat(follow_symlinks=False)
    is_dir = entry.is_dir(follow_symlinks=False)
    modified_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

    return FileEntry(
        name=entry.name,
        is_dir=is_dir,
        size_bytes=0 if is_dir else stat.st_size,
        modified_at=modified_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        relative_path=str(Path(entry.path).relative_to(vault_root)),
    )


def scan_directory(safe_dir: Path, vault_root: Path) -> list[FileEntry]:
    """
    Return a sorted list of FileEntry dicts for a single Vault directory level.

    Directories are listed before files (mirrors common file-browser UX).
    Within each group entries are sorted alphabetically, case-insensitive.

    Parameters
    ----------
    safe_dir:
        Absolute Path already validated by the Bouncer.
    vault_root:
        The VAULT_DIR Path, used to compute relative_path for each entry.

    Returns
    -------
    list[FileEntry]
        Sorted, serialisable directory contents.

    Raises
    ------
    PermissionError
        Propagated up — the route handler converts it to HTTP 403.
    """
    with os.scandir(safe_dir) as scanner:
        entries = [_entry_to_dict(e, vault_root) for e in scanner]

    # Directories first, then files; alphabetical within each group
    entries.sort(key=lambda e: (not e["is_dir"], e["name"].lower()))
    return entries