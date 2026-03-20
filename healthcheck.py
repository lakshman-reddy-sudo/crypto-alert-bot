"""
healthcheck.py — Lightweight HTTP health/readiness probe server.

Exposes three endpoints:

  GET /health   — Liveness probe. Always 200 if process is alive.
  GET /ready    — Readiness probe. 200 when Discord + WS + cache are all up.
                  (No DB check — we're in-memory only.)
  GET /metrics  — Lightweight Prometheus-style text metrics.

The server runs as a background asyncio task sharing the main event loop.
It must NOT block or interfere with the bot's main workload.
"""

import asyncio
import logging
import time
from typing import Callable

from aiohttp import web

from config import settings

logger = logging.getLogger(__name__)

_start_time = time.monotonic()


class HealthServer:
    """
    Tracks component readiness and serves health probe HTTP endpoints.
    Components register themselves via set_* methods as they come online.
    """

    def __init__(self) -> None:
        self._discord_ready: bool = False
        self._ws_ready: bool = False
        self._cache_size_fn: Callable[[], int] = lambda: 0

        self._app = web.Application()
        self._app.router.add_get("/health", self._handle_health)
        self._app.router.add_get("/ready", self._handle_ready)
        self._app.router.add_get("/metrics", self._handle_metrics)

        self._runner: web.AppRunner | None = None

    # ------------------------------------------------------------------
    # Component registration
    # ------------------------------------------------------------------

    def set_discord_ready(self, ready: bool = True) -> None:
        self._discord_ready = ready

    def set_ws_ready(self, ready: bool = True) -> None:
        self._ws_ready = ready

    def set_cache_size_fn(self, size_fn: Callable[[], int]) -> None:
        self._cache_size_fn = size_fn

    @property
    def is_ready(self) -> bool:
        return self._discord_ready and self._ws_ready

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, _request: web.Request) -> web.Response:
        """Liveness: always 200 if the event loop is running."""
        return web.json_response({"status": "alive"})

    async def _handle_ready(self, _request: web.Request) -> web.Response:
        """Readiness: 200 only when Discord + WebSocket are both online."""
        components = {
            "discord": self._discord_ready,
            "websocket": self._ws_ready,
        }
        overall = all(components.values())
        return web.json_response(
            {
                "ready": overall,
                "components": components,
                "active_alerts": self._cache_size_fn(),
                "uptime_seconds": round(time.monotonic() - _start_time, 1),
            },
            status=200 if overall else 503,
        )

    async def _handle_metrics(self, _request: web.Request) -> web.Response:
        """Prometheus-format text metrics — no prometheus_client dependency."""
        uptime = time.monotonic() - _start_time
        cache_size = self._cache_size_fn()
        ready = 1 if self.is_ready else 0

        lines = [
            "# HELP crypto_alert_bot_uptime_seconds Seconds since bot process started",
            "# TYPE crypto_alert_bot_uptime_seconds counter",
            f"crypto_alert_bot_uptime_seconds {uptime:.1f}",
            "",
            "# HELP crypto_alert_bot_ready Whether all subsystems are ready (1=yes, 0=no)",
            "# TYPE crypto_alert_bot_ready gauge",
            f"crypto_alert_bot_ready {ready}",
            "",
            "# HELP crypto_alert_bot_active_alerts Total alerts currently in memory",
            "# TYPE crypto_alert_bot_active_alerts gauge",
            f"crypto_alert_bot_active_alerts {cache_size}",
            "",
            "# HELP crypto_alert_bot_discord_ready Discord connection state (1=up)",
            "# TYPE crypto_alert_bot_discord_ready gauge",
            f"crypto_alert_bot_discord_ready {int(self._discord_ready)}",
            "",
            "# HELP crypto_alert_bot_ws_ready Binance WebSocket state (1=connected)",
            "# TYPE crypto_alert_bot_ws_ready gauge",
            f"crypto_alert_bot_ws_ready {int(self._ws_ready)}",
        ]

        return web.Response(
            text="\n".join(lines) + "\n",
            content_type="text/plain",
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not settings.healthcheck_enabled:
            logger.info("Health check server disabled via HEALTHCHECK_ENABLED=false.")
            return

        self._runner = web.AppRunner(self._app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(
            self._runner,
            settings.healthcheck_host,
            settings.healthcheck_port,
        )
        await site.start()
        logger.info(
            "Health server listening on %s:%d",
            settings.healthcheck_host,
            settings.healthcheck_port,
        )

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("Health server stopped.")
