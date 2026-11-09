"""
Vahak — Scanner Route
───────────────────────────────────────────────────────────────────────────────
Provides a JSON view of the VahakVault directory tree. The Flutter client uses
this endpoint to render its file-browser navigation UI.

All disk I/O is offloaded to asyncio.to_thread() so it never blocks the Granian
event loop during large directory scans.

P0 FIX: resolve_safe_path() is called explicitly with the exact URL path
parameter string. No implicit DI, no parameter-name mismatch.

Endpoints
─────────
GET /api/v1/scan/list/{sub_path}
    List the contents of a Vault directory. `sub_path` is optional; omitting it
    lists the Vault root. Returns directories before files, both alphabetically
    sorted.

GET /api/v1/scan/list
    Convenience alias for the Vault root.
"""

import asyncio

from fastapi import APIRouter, HTTPException, status

from app.core.config import VAULT_DIR
from app.core.security import resolve_safe_path
from app.services.file_system import scan_directory

router = APIRouter()


@router.get("/list/{sub_path:path}", summary="List Vault directory contents")
async def list_directory(sub_path: str = ""):
    """
    Return a sorted JSON array of all entries in the requested Vault directory.

    P0 FIXED: The raw `sub_path` string from the URL is passed directly to
    resolve_safe_path(). No dependency injection layer in between.
    """
    safe_dir = resolve_safe_path(sub_path)

    if not safe_dir.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Path does not exist inside the Vault: {safe_dir.relative_to(VAULT_DIR)}",
        )
    if not safe_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Requested path is a file, not a directory. Use the /pull endpoint to download files.",
        )

    try:
        contents = await asyncio.to_thread(scan_directory, safe_dir, VAULT_DIR)
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="OS-level permission denied reading this directory.",
        )

    return {
        "path": str(safe_dir.relative_to(VAULT_DIR)) if safe_dir != VAULT_DIR else "/",
        "entry_count": len(contents),
        "contents": contents,
    }


@router.get("/list", summary="List Vault root")
async def list_vault_root():
    """
    Convenience alias: lists the root of the Vault without requiring a trailing
    path segment. Equivalent to GET /list/
    """
    contents = await asyncio.to_thread(scan_directory, VAULT_DIR, VAULT_DIR)
    return {
        "path": "/",
        "entry_count": len(contents),
        "contents": contents,
    }