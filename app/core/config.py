"""
Vahak — Core Configuration
───────────────────────────────────────────────────────────────────────────────
Single source of truth for all environment-level constants. Imported by every
module that touches the filesystem or the network. Nothing else should compute
paths, port numbers, or resource limits independently.

Vault Initialization Contract
──────────────────────────────
VAULT_DIR is resolved to an absolute Path on the host OS at import time.
`mkdir(parents=True, exist_ok=True)` guarantees the directory exists before
any route handler or security check runs. This is intentionally side-effectful
on import — the Vault must exist before the Bouncer can defend it.
"""

from pathlib import Path

# ── Vault ──────────────────────────────────────────────────────────────────────
# All user files live exclusively inside this directory. The Bouncer in
# security.py verifies every incoming path is a strict child of VAULT_DIR.
HOST_HOME: Path = Path.home()
VAULT_DIR: Path = HOST_HOME / "VahakVault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

# ── Server Metadata ────────────────────────────────────────────────────────────
# Broadcast in UDP beacon payloads and the /health endpoint so Flutter clients
# can identify this Hub and verify version compatibility.
APP_NAME: str = "vahak"
APP_VERSION: str = "1.0.0"

# ── Network ────────────────────────────────────────────────────────────────────
# API port Granian binds to. Must match the UDP beacon payload so the Flutter
# client knows where to open its TCP connection after auto-discovery.
API_PORT: int = 8000

# UDP broadcast address and port for the auto-discovery beacon (Phase 4).
# The Flutter client listens on DISCOVERY_PORT and parses the originating IP.
DISCOVERY_BROADCAST_ADDR: str = "255.255.255.255"
DISCOVERY_PORT: int = 55430
DISCOVERY_INTERVAL_SECONDS: float = 2.0

# ── Upload Limits ──────────────────────────────────────────────────────────────
# Hard ceiling for a single upload. Prevents a rogue client from filling the
# SSD with a single infinite stream. 10 GB accommodates the largest video
# files in the Chitranidhi photo vault with headroom.
MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024 * 1024  # 10 GB

# Maximum number of simultaneous upload streams. Prevents file descriptor
# exhaustion (Ubuntu default ulimit -n = 1024) and bounds total I/O pressure
# across concurrent Android clients.
MAX_CONCURRENT_UPLOADS: int = 5

# Upload chunk size for chunked ingestion in the push endpoint.
# 64 KB matches the typical TCP send buffer and keeps RAM usage flat for
# arbitrarily large files.
UPLOAD_CHUNK_SIZE: int = 65_536  # 64 KB
