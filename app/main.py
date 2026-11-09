"""
Vahak — ASGI Entry Point & Middleware Assembly
───────────────────────────────────────────────────────────────────────────────
This is the module Granian loads. It assembles the FastAPI application,
registers all routers, wires up the lifespan handler (which starts/stops the
UDP discovery beacon), and exposes a health endpoint for the Flutter client to
confirm connectivity post-discovery.

Boot Command (Production)
──────────────────────────
  granian --interface asgi app.main:app --host 0.0.0.0 --port 8000 --workers 8

Boot Command (Development)
───────────────────────────
  granian --interface asgi app.main:app --host 0.0.0.0 --port 8000 --reload
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from app.api.routes import scanner, sync, transfer
from app.core.config import (
    API_PORT,
    APP_NAME,
    APP_VERSION,
    DISCOVERY_PORT,
    VAULT_DIR,
)
from app.services.discovery import start_beacon

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ── Lifespan ────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan handler: runs startup logic before yielding, then teardown
    logic after the `yield` when the server is shutting down.

    Startup
    ───────
    1. Log the Vault path so operators can confirm the correct directory.
    2. Start the UDP discovery beacon as a background asyncio.Task.

    Shutdown
    ────────
    1. Cancel the beacon task and await its clean exit (CancelledError is
       handled inside the beacon loop — socket is always closed).
    """
    # ── Startup ──
    logger.info("━" * 60)
    logger.info("  Vahak Hub v%s starting up", APP_VERSION)
    logger.info("  Vault   : %s", VAULT_DIR)
    logger.info("  API     : http://0.0.0.0:%d", API_PORT)
    logger.info("  Beacon  : UDP broadcast → 255.255.255.255:%d", DISCOVERY_PORT)
    logger.info("━" * 60)

    beacon_task: asyncio.Task = await start_beacon()

    yield  # ← server is running; handle requests here

    # ── Shutdown ──
    logger.info("Vahak Hub shutting down — cancelling discovery beacon …")
    beacon_task.cancel()
    try:
        await beacon_task
    except asyncio.CancelledError:
        pass  # expected; beacon loop exits cleanly
    logger.info("Vahak Hub stopped.")


# ── Application Assembly ───────────────────────────────────────────────────────

app = FastAPI(
    title="Vahak Hub",
    description=(
        "Local-first, peer-to-peer file sync engine. "
        "Operates over a private Wi-Fi hotspot with zero-copy DMA transfers."
    ),
    version=APP_VERSION,
    default_response_class=ORJSONResponse,  # orjson for maximum JSON throughput
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS: allow any local-network origin so the Flutter Web debug build and
# third-party HTTP clients on the LAN can reach the API during development.
# Tighten to specific origins before any internet-facing deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(scanner.router, prefix="/api/v1/scan",     tags=["Scanner"])
app.include_router(transfer.router, prefix="/api/v1/transfer", tags=["Transfer"])
app.include_router(sync.router,     prefix="/api/v1/sync",     tags=["Sync"])


# ── Health Endpoint ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["Meta"], summary="Hub liveness + metadata probe")
async def health():
    """
    Lightweight liveness probe. The Flutter client calls this immediately after
    discovering the Hub's IP via the UDP beacon to:
      1. Confirm the TCP connection succeeds (basic reachability).
      2. Verify the service name and version before starting sync.
      3. Know the Vault directory name (for display in the mobile UI).

    P6 FIXED: Returns VAULT_DIR.name ("VahakVault") instead of the full
    absolute path, which previously leaked the host's OS username.
    """
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "status": "active",
        "vault": VAULT_DIR.name,  # P6 FIXED: directory name only, no absolute path
        "endpoints": {
            "scan":      "/api/v1/scan/list/{sub_path}",
            "pull":      "/api/v1/transfer/pull/{file_path}",
            "push":      "/api/v1/transfer/push/{dest_path}",
            "sync_diff": "/api/v1/sync/diff",
        },
    }

import time
@app.get("/poison", summary="The uvicorn killer")
def posion_pill():
    time.sleep(10)
    return {
        "message": "I survived the poison!"
    }


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect bare root requests to the interactive API docs."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


