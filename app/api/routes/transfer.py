"""
Vahak — Transfer Route (Zero-Copy Download + Hardened Upload)
───────────────────────────────────────────────────────────────────────────────
Implements the two critical data-movement endpoints with all seven audit
findings patched:

  P0  — resolve_safe_path() called explicitly with exact URL param string.
        No implicit DI, no parameter-name mismatch. Bouncer is live.
  P1  — Concurrency capped at MAX_CONCURRENT_UPLOADS via asyncio.Semaphore.
        Upload size capped at MAX_UPLOAD_SIZE (10 GB) with mid-stream check.
  P2  — Filename sanitised via sanitize_filename() before disk write.
        Blocks null bytes, control chars, 300-char names, Windows reserved.
  P3  — Writes go to a UUID temp file. Atomic os.rename() on completion.
        Two concurrent pushes of the same name cannot interleave bytes.
  P4  — If the client disconnects mid-stream, the except block deletes the
        partial temp file. No ghost files. The original file is untouched.

Phase 3 — Zero-Copy Highway
────────────────────────────
The pull endpoint returns FastAPI's native FileResponse. Granian intercepts
this via the `http.response.pathsend` ASGI extension and executes an OS-level
`sendfile()` syscall. The kernel pipes the file descriptor directly from the
NVMe SSD to the TCP network interface via DMA. Python never touches the bytes.

  ┌──────────┐   sendfile()   ┌─────────────┐    DMA    ┌────────────┐
  │ NVMe SSD │ ─────────────▶ │ OS Kernel   │ ─────────▶ │ NIC Buffer │
  └──────────┘                └─────────────┘            └────────────┘
                                 (no Python RAM involvement)

Endpoints
─────────
GET  /api/v1/transfer/pull/{file_path}   — Download a file from the Vault
POST /api/v1/transfer/push/{dest_path}   — Upload a file into the Vault
"""

import asyncio
import uuid

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import (
    MAX_CONCURRENT_UPLOADS,
    MAX_UPLOAD_SIZE,
    UPLOAD_CHUNK_SIZE,
    VAULT_DIR,
)
from app.core.security import resolve_safe_path, sanitize_filename

router = APIRouter()

# P1: Concurrency gate — at most MAX_CONCURRENT_UPLOADS active write streams.
# Protects file descriptor budget and bounds total I/O pressure.
_upload_semaphore = asyncio.Semaphore(MAX_CONCURRENT_UPLOADS)


# ── Pull (Zero-Copy Download) ──────────────────────────────────────────────────

@router.get("/pull/{file_path:path}", summary="Download a file from the Vault")
async def pull_file(file_path: str):
    """
    Stream a file from the Vault to the client using Granian's zero-copy path.

    Returns FastAPI's FileResponse directly — Granian translates this into an
    OS `sendfile()` call. Do NOT read or buffer the file in Python.

    P0 FIXED: file_path is passed explicitly to resolve_safe_path().
    Raises HTTP 404 if the path does not exist or is a directory.
    Raises HTTP 403 on path traversal (from the Bouncer).
    """
    safe_file = resolve_safe_path(file_path)

    if not safe_file.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File not found in Vault: {safe_file.relative_to(VAULT_DIR)}",
        )
    if safe_file.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested path is a directory. Use the /scan/list endpoint to browse it.",
        )

    # FileResponse triggers Granian's http.response.pathsend ASGI extension.
    # Python is bypassed entirely — the OS kernel handles the DMA transfer.
    return FileResponse(
        path=safe_file,
        filename=safe_file.name,
        media_type="application/octet-stream",
    )


# ── Push (Hardened Chunked Upload) ─────────────────────────────────────────────

@router.post("/push/{dest_path:path}", summary="Upload a file into the Vault", status_code=status.HTTP_201_CREATED)
async def push_file(dest_path: str, file: UploadFile = File(...)):
    """
    Receive a multipart/form-data file upload and write it to the Vault.

    P0  — dest_path passed explicitly to resolve_safe_path().
    P1  — Size enforced mid-stream; semaphore limits concurrent uploads.
    P2  — Filename sanitised before any disk operation.
    P3  — Bytes written to a UUID temp file; atomic rename on success.
    P4  — Partial temp file deleted on any failure (disconnect, size limit).

    `dest_path` is the target subdirectory inside the Vault. The file will be
    written as: VAULT_DIR / dest_path / <sanitised_filename>
    """
    # ── Validate destination path ──
    safe_dest = resolve_safe_path(dest_path)

    # ── Validate and sanitise filename ──
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload rejected: no filename provided in the multipart payload.",
        )
    clean_name = sanitize_filename(file.filename)

    # ── Ensure destination directory exists (safe — already Vault-bounded) ──
    safe_dest.mkdir(parents=True, exist_ok=True)

    # ── Build final target path and re-validate through the Bouncer ──
    # Defence-in-depth: even though sanitize_filename strips separators, the
    # composed path is run through the Bouncer a second time.
    target_file = resolve_safe_path(
        str(safe_dest.relative_to(VAULT_DIR) / clean_name)
    )

    # P3: Write to a temporary file with a unique name. Two concurrent pushes
    # of the same filename will write to separate temp files — no interleave.
    # The temp name starts with a dot (hidden from scandir) and contains a
    # UUID segment to guarantee uniqueness.
    temp_file = target_file.parent / f".vahak_tmp_{uuid.uuid4().hex[:12]}"
    bytes_written = 0

    # P1: Acquire the concurrency semaphore. If MAX_CONCURRENT_UPLOADS slots
    # are occupied, this coroutine awaits here without blocking the event loop.
    async with _upload_semaphore:
        try:
            async with aiofiles.open(temp_file, "wb") as buffer:
                while chunk := await file.read(UPLOAD_CHUNK_SIZE):
                    bytes_written += len(chunk)
                    # P1: Mid-stream size enforcement — kill before writing
                    if bytes_written > MAX_UPLOAD_SIZE:
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"Upload exceeds maximum allowed size ({MAX_UPLOAD_SIZE // (1024**3)} GB).",
                        )
                    await buffer.write(chunk)

            # P3: Atomic rename — last writer wins cleanly, no interleaved bytes.
            # os.rename() on Linux is atomic within the same filesystem.
            temp_file.rename(target_file)

        except Exception:
            # P4: Nuke the partial temp file if the connection drops, the size
            # limit is exceeded, or any other error occurs. The original file
            # (if any) remains untouched.
            temp_file.unlink(missing_ok=True)
            raise

    return {
        "status": "success",
        "filename": clean_name,
        "destination": str(target_file.relative_to(VAULT_DIR)),
        "written_bytes": bytes_written,
    }