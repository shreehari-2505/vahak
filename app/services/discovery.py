"""
Vahak — UDP Discovery Beacon (Phase 4: Auto-Discovery)
───────────────────────────────────────────────────────────────────────────────
Broadcasts a small UDP payload every DISCOVERY_INTERVAL_SECONDS on the local
subnet so Flutter clients can find the Hub's IP address automatically without
manual entry.

Beacon Payload (JSON)
──────────────────────
  {
    "service": "vahak",
    "version": "1.0.0",
    "port": 8000,
    "status": "active"
  }

Protocol Flow
─────────────
  Hub (this module)              Flutter Client
  ─────────────────              ──────────────
  bind UDP socket ──────────▶   listen on port 55430
  broadcast every 2s ──────▶   parse originating IP from UDP datagram
                                open TCP connection to <ip>:8000
                                GET /health → confirm it's a Vahak Hub
                                begin sync

Why UDP Broadcast (not mDNS)
──────────────────────────────
mDNS (zeroconf) requires a heavy third-party library that spins up its own
background threads, conflicting with Granian's Tokio async runtime. Pure UDP
broadcast runs entirely inside our asyncio event loop with zero extra threads.

mDNS will be evaluated in v1.1 if physical testing reveals hotspot configs that
block 255.255.255.255 broadcasts.
"""

import asyncio
import json
import logging
import socket

from app.core.config import (
    API_PORT,
    APP_NAME,
    APP_VERSION,
    DISCOVERY_BROADCAST_ADDR,
    DISCOVERY_INTERVAL_SECONDS,
    DISCOVERY_PORT,
)

logger = logging.getLogger(__name__)

# Pre-encode the beacon payload once at module load — zero allocation per tick
_BEACON_PAYLOAD: bytes = json.dumps(
    {
        "service": APP_NAME,
        "version": APP_VERSION,
        "port": API_PORT,
        "status": "active",
    },
    separators=(",", ":"),  # compact JSON, no whitespace
).encode("utf-8")


async def _broadcast_loop() -> None:
    """
    Inner coroutine: open a UDP broadcast socket and send the beacon payload
    every DISCOVERY_INTERVAL_SECONDS until the task is cancelled.

    The socket is created in blocking mode and handed to asyncio via
    loop.sock_sendto() so we never block the event loop thread.
    """
    loop = asyncio.get_running_loop()

    # SO_BROADCAST must be set explicitly on Linux/macOS; ignored on Windows
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)

    dest = (DISCOVERY_BROADCAST_ADDR, DISCOVERY_PORT)
    logger.info(
        "Vahak discovery beacon started — broadcasting to %s:%d every %.1fs",
        DISCOVERY_BROADCAST_ADDR,
        DISCOVERY_PORT,
        DISCOVERY_INTERVAL_SECONDS,
    )

    try:
        while True:
            try:
                await loop.sock_sendto(sock, _BEACON_PAYLOAD, dest)
            except OSError as exc:
                # Log but don't crash — a transient network error should not
                # kill the entire server process
                logger.warning("Discovery beacon send error (will retry): %s", exc)

            await asyncio.sleep(DISCOVERY_INTERVAL_SECONDS)
    except asyncio.CancelledError:
        logger.info("Vahak discovery beacon stopped cleanly.")
    finally:
        sock.close()


async def start_beacon() -> asyncio.Task:
    """
    Schedule the UDP broadcast loop as a background asyncio.Task.

    Returns the Task object so the caller (lifespan handler in main.py) can
    cancel it on server shutdown for a clean teardown.
    """
    task = asyncio.create_task(_broadcast_loop(), name="vahak-discovery-beacon")
    return task
