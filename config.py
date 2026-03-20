"""
config.py — Single source of truth for all runtime configuration.

All env vars are validated at import time. If a required var is missing,
the process exits immediately with a clear error message rather than
crashing somewhere deep in the stack later.
"""

import os
import sys
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


def _require(key: str) -> str:
    """Read a required env var or abort with a clear message."""
    value = os.environ.get(key, "").strip()
    if not value:
        print(
            f"\n[FATAL] Missing required environment variable: {key}\n"
            f"        Copy .env.example → .env and fill in the value.\n",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _optional(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


# ---------------------------------------------------------------------------
# Settings dataclass (populated once at module import)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Settings:
    # ── Discord ──────────────────────────────────────────────────────────
    discord_token: str

    # Optional: if set, slash commands are synced to this guild instantly.
    # Leave blank for global sync (up to 1-hour propagation).
    dev_guild_id: int | None

    # ── Database ─────────────────────────────────────────────────────────
    supabase_db_url: str
    db_min_pool: int
    db_max_pool: int
    db_command_timeout: int  # seconds

    # ── Binance ───────────────────────────────────────────────────────────
    binance_ws_url: str
    binance_rest_url: str
    ws_heartbeat_secs: int
    ws_read_timeout_secs: int
    ws_reconnect_base_delay: float   # seconds, doubles on each retry
    ws_reconnect_max_delay: float

    # ── Alert logic ───────────────────────────────────────────────────────
    repeat_cooldown_secs: int         # 5 minutes default
    max_alerts_per_user: int          # safety cap

    # ── Discord rate limiting ─────────────────────────────────────────────
    discord_max_msg_per_sec: int
    discord_429_backoff_secs: float

    # ── Health check ─────────────────────────────────────────────────────
    healthcheck_host: str
    healthcheck_port: int
    healthcheck_enabled: bool

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str
    log_format: str = field(default="json")   # "json" | "text"


def _load() -> Settings:
    raw_guild = _optional("DEV_GUILD_ID", "")
    dev_guild_id = int(raw_guild) if raw_guild.isdigit() else None

    hc_enabled = _optional("HEALTHCHECK_ENABLED", "true").lower() in (
        "true", "1", "yes"
    )

    return Settings(
        # Discord
        discord_token=_require("DISCORD_TOKEN"),
        dev_guild_id=dev_guild_id,
        # Database
        supabase_db_url=_require("SUPABASE_DB_URL"),
        db_min_pool=int(_optional("DB_MIN_POOL", "2")),
        db_max_pool=int(_optional("DB_MAX_POOL", "10")),
        db_command_timeout=int(_optional("DB_COMMAND_TIMEOUT", "30")),
        # Binance
        binance_ws_url=_optional(
            "BINANCE_WS_URL",
            "wss://stream.binance.com:9443/ws/!miniTicker@arr",
        ),
        binance_rest_url=_optional(
            "BINANCE_REST_URL",
            "https://api.binance.com/api/v3/ticker/price",
        ),
        ws_heartbeat_secs=int(_optional("WS_HEARTBEAT_SECS", "30")),
        ws_read_timeout_secs=int(_optional("WS_READ_TIMEOUT_SECS", "45")),
        ws_reconnect_base_delay=float(_optional("WS_RECONNECT_BASE_DELAY", "5")),
        ws_reconnect_max_delay=float(_optional("WS_RECONNECT_MAX_DELAY", "120")),
        # Alert logic
        repeat_cooldown_secs=int(_optional("REPEAT_COOLDOWN_SECS", "300")),
        max_alerts_per_user=int(_optional("MAX_ALERTS_PER_USER", "50")),
        # Discord rate limiting
        discord_max_msg_per_sec=int(_optional("DISCORD_MAX_MSG_PER_SEC", "10")),
        discord_429_backoff_secs=float(_optional("DISCORD_429_BACKOFF_SECS", "5.0")),
        # Healthcheck
        healthcheck_host=_optional("HEALTHCHECK_HOST", "0.0.0.0"),
        healthcheck_port=int(_optional("HEALTHCHECK_PORT", "8080")),
        healthcheck_enabled=hc_enabled,
        # Logging
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
        log_format=_optional("LOG_FORMAT", "text"),
    )


# Module-level singleton — imported everywhere
settings: Settings = _load()


# ---------------------------------------------------------------------------
# Logging bootstrap (called once from bot.py before anything else)
# ---------------------------------------------------------------------------

def configure_logging() -> None:
    """
    Set up root logger. If LOG_FORMAT=json, emit structured JSON lines
    (useful for Datadog / Loki log ingestion). Otherwise use a readable
    text format for local development.
    """
    handlers: list[logging.Handler] = []

    if settings.log_format == "json":
        try:
            import json_log_formatter  # type: ignore
            formatter = json_log_formatter.JSONFormatter()
        except ImportError:
            formatter = _text_formatter()
    else:
        formatter = _text_formatter()

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    handlers.append(handler)

    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        handlers=handlers,
    )
    # Silence noisy third-party loggers
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _text_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s  [%(levelname)-8s]  %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
