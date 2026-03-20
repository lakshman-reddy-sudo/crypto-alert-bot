"""
alerts.py — In-memory AlertCache and price crossover detection.

The WebSocket handler reads ONLY this cache — never Supabase.
The cache is updated atomically via asyncio.Lock to prevent race conditions
between the WS handler task and slash-command coroutines.
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

logger = logging.getLogger(__name__)

# 5-minute cooldown between repeat-alert firings
REPEAT_COOLDOWN_SECONDS = 300


# ---------------------------------------------------------------------------
# AlertCache
# ---------------------------------------------------------------------------

class AlertCache:
    """
    Two-level dict:  symbol (str) → alert_id (int) → alert (dict)

    All mutating methods acquire the lock.
    The hot-path read (get_alerts_for_symbol) is intentionally lock-free
    because Python's GIL makes list() on a dict snapshot safe for our
    read-dominated workload, and the tiny window of inconsistency is
    acceptable (at worst, a single tick misses or double-fires, which
    the cooldown / crossover logic already guards against).
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[int, dict]] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Bulk load (startup / reconnect)
    # ------------------------------------------------------------------

    async def load(self, alerts: list[dict]) -> None:
        """Replace the entire cache. Called on startup and after resync."""
        async with self._lock:
            self._data.clear()
            for alert in alerts:
                self._insert(alert)
        logger.info(
            "AlertCache loaded: %d alerts across %d symbols.",
            len(alerts),
            len(self._data),
        )

    # ------------------------------------------------------------------
    # Single-alert mutations
    # ------------------------------------------------------------------

    async def add(self, alert: dict) -> None:
        """Add a newly-created alert."""
        async with self._lock:
            self._insert(alert)

    async def remove(self, alert_id: int, symbol: str) -> None:
        """Remove an alert (user-deleted or one-shot triggered)."""
        async with self._lock:
            sym = symbol.upper()
            bucket = self._data.get(sym)
            if bucket and alert_id in bucket:
                del bucket[alert_id]
                if not bucket:
                    del self._data[sym]

    async def remove_all_for_user(self, user_id: int) -> None:
        """Remove every alert owned by user_id (used by /alert clear)."""
        async with self._lock:
            for sym in list(self._data.keys()):
                bucket = self._data[sym]
                to_del = [
                    aid for aid, a in bucket.items() if a["user_id"] == user_id
                ]
                for aid in to_del:
                    del bucket[aid]
                if not bucket:
                    del self._data[sym]

    # ------------------------------------------------------------------
    # In-place field updates (no DB round-trip)
    # ------------------------------------------------------------------

    async def update_last_price(
        self, alert_id: int, symbol: str, last_price: float
    ) -> None:
        """Silently update last_price in-cache after each tick (no lock needed for float write)."""
        sym = symbol.upper()
        bucket = self._data.get(sym)
        if bucket and alert_id in bucket:
            bucket[alert_id]["last_price"] = last_price

    async def set_triggered(
        self, alert_id: int, symbol: str, new_last_price: float
    ) -> None:
        """
        After a crossover fires (repeat=True path):
        update last_price + last_triggered_at so the cooldown clock starts.
        """
        async with self._lock:
            sym = symbol.upper()
            bucket = self._data.get(sym)
            if bucket and alert_id in bucket:
                bucket[alert_id]["last_price"] = new_last_price
                bucket[alert_id]["last_triggered_at"] = datetime.now(timezone.utc)

    async def deactivate(self, alert_id: int, symbol: str) -> None:
        """Remove a one-shot alert after it fires."""
        await self.remove(alert_id, symbol)

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_alerts_for_symbol(self, symbol: str) -> list[dict]:
        """
        Hot-path: called on every WS tick for symbols we care about.
        Returns a snapshot list — intentionally lock-free (see class docstring).
        """
        bucket = self._data.get(symbol.upper())
        return list(bucket.values()) if bucket else []

    def find_symbol_by_alert_id(self, alert_id: int) -> Optional[str]:
        """Return the symbol string for a given alert_id, or None if not found."""
        for sym, bucket in self._data.items():
            if alert_id in bucket:
                return sym
        return None

    @property
    def all_symbols(self) -> set[str]:
        """Set of all symbols currently being tracked."""
        return set(self._data.keys())

    @property
    def total_alerts(self) -> int:
        return sum(len(b) for b in self._data.values())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _insert(self, alert: dict) -> None:
        sym = alert["symbol"].upper()
        if sym not in self._data:
            self._data[sym] = {}
        self._data[sym][alert["id"]] = alert


# ---------------------------------------------------------------------------
# Crossover detection
# ---------------------------------------------------------------------------

def check_crossover(alert: dict, current_price: Decimal) -> Optional[str]:
    """
    Pure function — no I/O, no side effects.

    Returns the fired direction ('above' or 'below') if this tick
    represents a genuine price crossover, otherwise None.

    Rules:
      - last_price < target AND current >= target  →  fires 'above'
      - last_price > target AND current <= target  →  fires 'below'

    Cooldown:
      - Repeat alerts are suppressed for REPEAT_COOLDOWN_SECONDS after
        the last trigger to prevent flash-crash spam.
    """
    raw_last = alert.get("last_price")
    if raw_last is None:
        return None  # No baseline yet; cannot detect a cross

    last_price: Decimal = Decimal(str(raw_last))
    target: Decimal = Decimal(str(alert["target_price"]))
    direction: str = alert["direction"]

    # ---- cooldown guard ------------------------------------------------
    if alert.get("repeat") and alert.get("last_triggered_at"):
        triggered_at: datetime = alert["last_triggered_at"]
        if triggered_at.tzinfo is None:
            triggered_at = triggered_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - triggered_at).total_seconds()
        if elapsed < REPEAT_COOLDOWN_SECONDS:
            return None

    # ---- crossover logic -----------------------------------------------
    crossed_above = last_price < target <= current_price
    crossed_below = last_price > target >= current_price

    if direction == "above" and crossed_above:
        return "above"
    if direction == "below" and crossed_below:
        return "below"
    if direction == "both":
        if crossed_above:
            return "above"
        if crossed_below:
            return "below"

    return None
