"""
Vahak — Sync Route (Last-Write-Wins Delta Diff)
───────────────────────────────────────────────────────────────────────────────
Implements the v1.0 synchronisation diff endpoint. The Flutter client sends a
snapshot of its local file index; the Hub compares it against the current Vault
state and returns a delta manifest telling the client exactly what to pull,
push, or delete.

Delta Strategy: Last-Write-Wins (LWW)
───────────────────────────────────────
Comparison key: (filename, size_bytes, modified_at). This is correct and fast
for single-hop private Wi-Fi sync between personal devices. No CRDTs, no Merkle
trees — those belong in distributed, untrusted multi-node systems.

Time complexity: O(n) where n = number of Vault entries. Runs in milliseconds.

Endpoints
─────────
POST /api/v1/sync/diff
    Accepts the client's file index, returns a delta manifest.

GET  /api/v1/sync/diff/{sub_path}
    Diff a specific Vault subdirectory against the client's index for that path.
"""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import VAULT_DIR
from app.services.file_system import scan_directory

router = APIRouter()


# ── Pydantic Models ────────────────────────────────────────────────────────────

class ClientFileRecord(BaseModel):
    """A single file entry as reported by the Flutter client."""
    name: str
    size_bytes: int
    modified_at: str   # ISO 8601 UTC string, e.g. "2026-10-29T06:15:00Z"
    relative_path: str


class SyncDiffRequest(BaseModel):
    """
    The Flutter client's file snapshot for a given Vault path.
    `vault_path` is the subdirectory being compared (empty string = Vault root).
    """
    vault_path: str = ""
    client_files: list[ClientFileRecord]


class DeltaManifest(BaseModel):
    """
    Delta manifest returned to the Flutter client.

    - `to_pull`:   Files on the Hub that the client is missing or has outdated.
    - `to_push`:   Files the client has that the Hub is missing or has outdated.
    - `to_delete`: Files the client has that no longer exist on the Hub
                   (only populated if client requests deletions).
    """
    vault_path: str
    to_pull: list[str]   # relative_path strings the client should download
    to_push: list[str]   # relative_path strings the client should upload
    to_delete: list[str] # relative_path strings the client should delete locally


# ── Helpers ────────────────────────────────────────────────────────────────────

def _compute_delta(
    hub_entries: list[dict],
    client_records: list[ClientFileRecord],
    sync_deletions: bool = False,
) -> tuple[list[str], list[str], list[str]]:
    """
    Last-Write-Wins diff: compare Hub entries against client records.

    Matching key: name + size_bytes + modified_at (ISO 8601 string comparison).
    If all three match, the files are considered identical — no action needed.

    Returns
    -------
    (to_pull, to_push, to_delete)
    """
    # Build lookup maps keyed by filename for O(1) access
    hub_map: dict[str, dict] = {e["name"]: e for e in hub_entries if not e["is_dir"]}
    client_map: dict[str, ClientFileRecord] = {r.name: r for r in client_records}

    to_pull: list[str] = []
    to_push: list[str] = []
    to_delete: list[str] = []

    # Files on the Hub
    for name, hub_entry in hub_map.items():
        if name not in client_map:
            # Hub has it, client doesn't → client must pull
            to_pull.append(hub_entry["relative_path"])
        else:
            client_rec = client_map[name]
            hub_sig = (hub_entry["size_bytes"], hub_entry["modified_at"])
            client_sig = (client_rec.size_bytes, client_rec.modified_at)
            if hub_sig != client_sig:
                # Different — compare mtime; newer version wins
                # modified_at is ISO 8601 → lexicographic string comparison is valid
                if hub_entry["modified_at"] >= client_rec.modified_at:
                    to_pull.append(hub_entry["relative_path"])
                else:
                    to_push.append(client_rec.relative_path)

    # Files the client has but the Hub doesn't.
    # P7 FIXED: These are mutually exclusive operations. When sync_deletions
    # is True, the Hub is authoritative — client-only files are deletions.
    # When False, the client is bringing new files — they are pushes.
    for name, client_rec in client_map.items():
        if name not in hub_map:
            if sync_deletions:
                to_delete.append(client_rec.relative_path)
            else:
                to_push.append(client_rec.relative_path)

    return to_pull, to_push, to_delete


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post(
    "/diff",
    response_model=DeltaManifest,
    summary="Compute LWW delta between Hub Vault and client file index",
)
async def compute_diff(body: SyncDiffRequest, sync_deletions: bool = False):
    """
    Accept the Flutter client's file snapshot and return a delta manifest.

    The Hub scans its Vault at `vault_path`, then applies Last-Write-Wins diff
    against the client's list. The manifest tells the client which files to
    pull, push, and optionally delete.

    Query param `sync_deletions=true` enables telling the client to delete
    files it has locally that no longer exist on the Hub. Defaults to false
    for safety.
    """
    from app.core.security import resolve_safe_path

    safe_dir: Path = resolve_safe_path(body.vault_path)

    if not safe_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vault path does not exist or is not a directory: {body.vault_path or '/'}",
        )

    hub_entries = await asyncio.to_thread(scan_directory, safe_dir, VAULT_DIR)
    to_pull, to_push, to_delete = _compute_delta(
        hub_entries, body.client_files, sync_deletions
    )

    return DeltaManifest(
        vault_path=body.vault_path or "/",
        to_pull=to_pull,
        to_push=to_push,
        to_delete=to_delete,
    )
