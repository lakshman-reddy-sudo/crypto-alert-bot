import logging
import os
import sys
from dataclasses import dataclass, field


def _require(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        print(f"\n[FATAL] Missing required environment variable: {key}\n", file=sys.stderr)
        sys.exit(1)
    return value


def _optional(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


def _healthcheck_port() -> int:
    for key in ("PORT", "HEALTHCHECK_PORT"):
        val = os.environ.get(key, "").strip()
        if val.isdigit():
            return int(val)
    return 8080


@dataclass(frozen=True)
class Settings:
    discord_token: str
    dev_guild_id: int | None
    binance_ws_url: str
    binance_rest_url: str
    ws_heartbeat_secs: int
    ws_read_timeout_secs: int
    ws_reconnect_base_delay: float
    ws_reconnect_max_delay: float
    repeat_cooldown_secs: int
    max_alerts_per_user: int
    discord_max_msg_per_sec: int
    discord_429_backoff_secs: float
    healthcheck_host: str
    healthcheck_port: int
    healthcheck_enabled: bool
    log_level: str
    log_format: str = field(default="text")


def _load() -> Settings:
    raw_guild = _optional("DEV_GUILD_ID", "")
    dev_guild_id = int(raw_guild) if raw_guild.isdigit() else None
    hc_enabled = _optional("HEALTHCHECK_ENABLED", "true").lower() in ("true", "1", "yes")

    return Settings(
        discord_token=_require("DISCORD_TOKEN"),
        dev_guild_id=dev_guild_id,
        binance_ws_url=_optional("BINANCE_WS_URL", "wss://stream.binance.com:9443/ws/!miniTicker@arr"),
        binance_rest_url=_optional("BINANCE_REST_URL", "https://api.binance.com/api/v3/ticker/price"),
        ws_heartbeat_secs=int(_optional("WS_HEARTBEAT_SECS", "20")),
        ws_read_timeout_secs=int(_optional("WS_READ_TIMEOUT_SECS", "60")),
        ws_reconnect_base_delay=float(_optional("WS_RECONNECT_BASE_DELAY", "5")),
        ws_reconnect_max_delay=float(_optional("WS_RECONNECT_MAX_DELAY", "120")),
        repeat_cooldown_secs=int(_optional("REPEAT_COOLDOWN_SECS", "300")),
        max_alerts_per_user=int(_optional("MAX_ALERTS_PER_USER", "50")),
        discord_max_msg_per_sec=int(_optional("DISCORD_MAX_MSG_PER_SEC", "5")),
        discord_429_backoff_secs=float(_optional("DISCORD_429_BACKOFF_SECS", "5.0")),
        healthcheck_host=_optional("HEALTHCHECK_HOST", "0.0.0.0"),
        healthcheck_port=_healthcheck_port(),
        healthcheck_enabled=hc_enabled,
        log_level=_optional("LOG_LEVEL", "INFO").upper(),
        log_format=_optional("LOG_FORMAT", "text"),
    )


settings: Settings = _load()


def configure_logging() -> None:
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
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        handlers=[handler],
    )
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


def _text_formatter() -> logging.Formatter:
    return logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
