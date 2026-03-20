"""
data.py — asyncpg connection pool, schema, and all DB operations.

All queries are async and go through a shared connection pool.
The WebSocket layer NEVER calls these directly on every tick.
Only called on: bot startup, alert CRUD, alert trigger, pause/resume.
"""

import logging
from typing import Optional
import asyncpg

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_CREATE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS alerts (
    id                BIGSERIAL       PRIMARY KEY,
    user_id           BIGINT          NOT NULL,
    guild_id          BIGINT          NOT NULL,
    channel_id        BIGINT          NOT NULL,
    symbol            VARCHAR(20)     NOT NULL,
    direction         VARCHAR(10)     NOT NULL
                          CHECK (direction IN ('above', 'below', 'both')),
    target_price      NUMERIC(28, 8)  NOT NULL,
    last_price        NUMERIC(28, 8),
    repeat            BOOLEAN         NOT NULL DEFAULT FALSE,
    active            BOOLEAN         NOT NULL DEFAULT TRUE,
    paused            BOOLEAN         NOT NULL DEFAULT FALSE,
    last_triggered_at TIMESTAMPTZ,
    created_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_active_symbol
    ON alerts (symbol) WHERE active = TRUE AND paused = FALSE;

CREATE INDEX IF NOT EXISTS idx_alerts_user_active
    ON alerts (user_id) WHERE active = TRUE;
"""

_pool: Optional[asyncpg.Pool] = None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def init_db() -> asyncpg.Pool:
    """Create the connection pool and ensure the schema exists."""
    global _pool
    _pool = await asyncpg.create_pool(
        settings.supabase_db_url,
        min_size=settings.db_min_pool,
        max_size=settings.db_max_pool,
        command_timeout=settings.db_command_timeout,
        ssl="require",
    )
    async with _pool.acquire() as conn:
        await conn.execute(_CREATE_SCHEMA_SQL)
    logger.info(
        "asyncpg pool initialized (min=%d, max=%d).",
        settings.db_min_pool,
        settings.db_max_pool,
    )
    return _pool


async def close_db() -> None:
    """Gracefully close all pool connections."""
    global _pool
    if _pool:
        await _pool.close()
        logger.info("asyncpg pool closed.")


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized — call init_db() first.")
    return _pool


# ---------------------------------------------------------------------------
# Alert CRUD
# ---------------------------------------------------------------------------

async def create_alert(
    *,
    user_id: int,
    guild_id: int,
    channel_id: int,
    symbol: str,
    direction: str,
    target_price: float,
    last_price: float,
    repeat: bool,
) -> dict:
    """Insert a new alert and return the full row as a dict."""
    async with get_pool().acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alerts
                (user_id, guild_id, channel_id, symbol, direction,
                 target_price, last_price, repeat)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
            """,
            user_id, guild_id, channel_id,
            symbol, direction,
            target_price, last_price, repeat,
        )
        return dict(row)


async def get_user_alerts(user_id: int) -> list[dict]:
    """Return all active alerts for a user, newest first."""
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT * FROM alerts
            WHERE user_id = $1 AND active = TRUE
            ORDER BY created_at DESC
            """,
            user_id,
        )
        return [dict(r) for r in rows]


async def delete_alert(alert_id: int, user_id: int) -> bool:
    """
    Soft-delete an alert (set active=FALSE).
    Returns True only if a row owned by user_id was actually updated.
    """
    async with get_pool().acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE alerts
            SET active = FALSE
            WHERE id = $1 AND user_id = $2 AND active = TRUE
            """,
            alert_id, user_id,
        )
        return tag == "UPDATE 1"


async def clear_user_alerts(user_id: int) -> int:
    """Soft-delete all active alerts for a user. Returns the count removed."""
    async with get_pool().acquire() as conn:
        tag = await conn.execute(
            "UPDATE alerts SET active = FALSE WHERE user_id = $1 AND active = TRUE",
            user_id,
        )
        return int(tag.split()[-1])


async def load_all_active_alerts() -> list[dict]:
    """
    Load every active, non-paused alert on startup.
    Paused alerts are intentionally excluded from the hot-path cache.
    """
    async with get_pool().acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM alerts WHERE active = TRUE AND paused = FALSE"
        )
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Trigger / price updates  (called only on state changes, never per WS tick)
# ---------------------------------------------------------------------------

async def mark_alert_triggered(
    alert_id: int, new_last_price: float, repeat: bool
) -> None:
    """
    After a crossover fires:
      - If repeat=True:  update last_price + last_triggered_at (stays active).
      - If repeat=False: soft-delete the alert.
    """
    async with get_pool().acquire() as conn:
        if repeat:
            await conn.execute(
                """
                UPDATE alerts
                SET last_price        = $1,
                    last_triggered_at = NOW()
                WHERE id = $2
                """,
                new_last_price, alert_id,
            )
        else:
            await conn.execute(
                "UPDATE alerts SET active = FALSE WHERE id = $1",
                alert_id,
            )


async def batch_update_last_prices(updates: list[tuple[int, float]]) -> None:
    """
    Bulk-update last_price for a list of (alert_id, price) pairs.
    Called on resync after a WebSocket reconnect — avoids N individual round-trips.
    """
    if not updates:
        return
    async with get_pool().acquire() as conn:
        await conn.executemany(
            "UPDATE alerts SET last_price = $2 WHERE id = $1",
            updates,
        )


async def count_user_alerts(user_id: int) -> int:
    """Return the number of currently active alerts for a user."""
    async with get_pool().acquire() as conn:
        return await conn.fetchval(
            "SELECT COUNT(*) FROM alerts WHERE user_id = $1 AND active = TRUE",
            user_id,
        )


async def set_alert_paused(alert_id: int, user_id: int, paused: bool) -> bool:
    """
    Toggle the paused state for a specific alert.
    Returns True if the alert was found and updated.
    """
    async with get_pool().acquire() as conn:
        tag = await conn.execute(
            """
            UPDATE alerts
            SET paused = $1
            WHERE id = $2 AND user_id = $3 AND active = TRUE
            """,
            paused, alert_id, user_id,
        )
        return tag == "UPDATE 1"
