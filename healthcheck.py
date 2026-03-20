"""
healthcheck.py — Lightweight HTTP health/readiness probe server.

Exposes two endpoints for orchestrators (Docker, Kubernetes, Railway, etc.):

  GET /health   — Liveness probe.
                  Returns 200 if the bot process is alive and the event loop
                  is responsive.

  GET /ready    — Readiness probe.
                  Returns 200 only when ALL of the following are true:
                    • Bot is logged into Discord
                    • asyncpg pool is connected
                    • Binance WebSocket is active
                    • AlertCache has been populated

  GET /metrics  — Lightweight Prometheus-style text metrics (no library needed).
                  Suitable for scraping by Prometheus or Grafana Agent.

The server runs as a background asyncio task and shares the main event loop.
It must NOT block or interfere with the bot's main workload.
"""

import asyncio
import logging
import time
from typing import Callable

from aiohttp import web

from config import settings

logger = logging.getLogger(__name__)

# Module-level start time for uptime tracking
_start_time = time.monotonic()


class HealthServer:
    """
    Wraps the aiohttp web Application and tracks component readiness.

    Components register themselves via the `set_*` methods as they come online.
    The /ready endpoint uses all flags to compute overall readiness.
    """

    def __init__(self) -> None:
        self._discord_ready: bool = False
        self._db_ready: bool = False
        self._ws_ready: bool = False
        self._cache_loaded: bool = False
        self._cache_size_fn: Callable[[], int] = lambda: 0

        self._app = web.Application()
        self._app.router.add_get("/health",  self._handle_health)
        self._app.router.add_get("/ready",   self._handle_ready)
        self._app.router.add_get("/metrics", self._handle_metrics)

        self._runner: web.AppRunner | None = None
        self._task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Component registration (called by bot.py / price_stream.py)
    # ------------------------------------------------------------------

    def set_discord_ready(self, ready: bool = True) -> None:
        self._discord_ready = ready

    def set_db_ready(self, ready: bool = True) -> None:
        self._db_ready = ready

    def set_ws_ready(self, ready: bool = True) -> None:
        self._ws_ready = ready

    def set_cache_loaded(self, ready: bool = True, size_fn: Callable[[], int] | None = None) -> None:
        self._cache_loaded = ready
        if size_fn:
            self._cache_size_fn = size_fn

    @property
    def is_ready(self) -> bool:
        return (
            self._discord_ready
            and self._db_ready
            and self._ws_ready
            and self._cache_loaded
        )

    # ------------------------------------------------------------------
    # Route handlers
    # ------------------------------------------------------------------

    async def _handle_health(self, _request: web.Request) -> web.Response:
        """
        Liveness: always 200 if the event loop is running.
        Orchestrators use this to know whether to restart the container.
        """
        return web.json_response({"status": "alive"})

    async def _handle_ready(self, _request: web.Request) -> web.Response:
        """
        Readiness: 200 only when all subsystems are online.
        Orchestrators use this to know whether to route traffic.
        """
        components = {
            "discord": self._discord_ready,
            "database": self._db_ready,
            "websocket": self._ws_ready,
            "cache": self._cache_loaded,
        }
        overall = all(components.values())
        status_code = 200 if overall else 503
        return web.json_response(
            {
                "ready": overall,
                "components": components,
                "uptime_seconds": round(time.monotonic() - _start_time, 1),
            },
            status=status_code,
        )

    async def _handle_metrics(self, _request: web.Request) -> web.Response:
        """
        Exposes lightweight Prometheus-format text metrics.
        No prometheus_client dependency required — pure string output.
        """
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
