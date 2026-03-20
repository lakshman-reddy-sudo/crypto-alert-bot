"""
alerts.py — In-memory AlertCache and price crossover detection.

The WebSocket handler reads ONLY this cache — no database anywhere.
The cache is the single source of truth for the entire bot session.

Alert IDs are auto-incrementing integers (resets on bot restart).
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# AlertCache
# ---------------------------------------------------------------------------

class AlertCache:
    """
    Two-level dict: symbol (str) → alert_id (int) → alert (dict)

    All mutating methods acquire the lock.
    The hot-path read (get_alerts_for_symbol) is lock-free — Python's GIL
    makes list() on a dict snapshot safe for our read-dominated workload.
    The tiny inconsistency window is acceptable: at worst a single tick
    misses, which the cooldown / crossover logic already guards against.

    Alert IDs are session-scoped incrementing integers starting at 1.
    """

    def __init__(self) -> None:
        self._data: dict[str, dict[int, dict]] = {}
        self._lock = asyncio.Lock()
        self._next_id: int = 1  # auto-increment counter

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def _new_id(self) -> int:
        """Return next alert ID. Must be called inside the lock."""
        aid = self._next_id
        self._next_id += 1
        return aid

    # ------------------------------------------------------------------
    # Single-alert mutations
    # ------------------------------------------------------------------

    async def add(self, alert: dict) -> dict:
        """
        Assign an ID to a new alert, insert it, and return the alert
        dict with the assigned id field set.
        """
        async with self._lock:
            alert["id"] = self._new_id()
            self._insert(alert)
            return alert

    async def remove(self, alert_id: int, symbol: str) -> bool:
        """
        Remove an alert by id + symbol. Returns True if it existed.
        """
        async with self._lock:
            sym = symbol.upper()
            bucket = self._data.get(sym)
            if bucket and alert_id in bucket:
                del bucket[alert_id]
                if not bucket:
                    del self._data[sym]
                return True
            return False

    async def remove_all_for_user(self, user_id: int) -> int:
        """
        Remove every alert owned by user_id (used by /alert clear).
        Returns the count of removed alerts.
        """
        removed = 0
        async with self._lock:
            for sym in list(self._data.keys()):
                bucket = self._data[sym]
                to_del = [
                    aid for aid, a in bucket.items() if a["user_id"] == user_id
                ]
                for aid in to_del:
                    del bucket[aid]
                    removed += 1
                if sym in self._data and not self._data[sym]:
                    del self._data[sym]
        return removed

    async def set_paused(self, alert_id: int, symbol: str, paused: bool) -> bool:
        """
        Pause or resume an alert. Returns True if found and updated.
        """
        async with self._lock:
            sym = symbol.upper()
            bucket = self._data.get(sym)
            if bucket and alert_id in bucket:
                bucket[alert_id]["paused"] = paused
                return True
            return False

    # ------------------------------------------------------------------
    # In-place field updates (called from price_stream hot path)
    # ------------------------------------------------------------------

    def update_last_price(
        self, alert_id: int, symbol: str, last_price: float
    ) -> None:
        """
        Update last_price in-cache after each tick.
        Uses a safe guard against concurrent bucket deletion.
        """
        sym = symbol.upper()
        bucket = self._data.get(sym)
        if bucket is not None:
            alert = bucket.get(alert_id)
            if alert is not None:
                alert["last_price"] = last_price

    async def set_triggered(
        self, alert_id: int, symbol: str, new_last_price: float
    ) -> None:
        """
        After a crossover fires on a repeat alert:
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
        Hot-path: called on every WS tick.
        Returns a snapshot list — intentionally lock-free.
        Skips paused alerts.
        """
        bucket = self._data.get(symbol.upper())
        if not bucket:
            return []
        return [a for a in bucket.values() if not a.get("paused", False)]

    def get_all_for_user(self, user_id: int) -> list[dict]:
        """Return all alerts (active + paused) for a given user."""
        result = []
        for bucket in self._data.values():
            for alert in bucket.values():
                if alert["user_id"] == user_id:
                    result.append(dict(alert))
        return result

    def find_alert(self, alert_id: int, user_id: int) -> Optional[dict]:
        """Find a specific alert by id + owner. Returns None if not found."""
        for bucket in self._data.values():
            alert = bucket.get(alert_id)
            if alert and alert["user_id"] == user_id:
                return dict(alert)
        return None

    def find_symbol_by_alert_id(self, alert_id: int) -> Optional[str]:
        """Return the symbol string for a given alert_id, or None."""
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
# Crossover detection — pure function, no I/O, no side effects
# ---------------------------------------------------------------------------

def check_crossover(alert: dict, current_price: Decimal) -> Optional[str]:
    """
    Returns the fired direction ('above' or 'below') if this tick
    represents a genuine price crossover, otherwise None.

    Rules:
      last_price < target  AND  current >= target  →  fires 'above'
      last_price > target  AND  current <= target  →  fires 'below'

    Cooldown:
      Repeat alerts are suppressed for settings.repeat_cooldown_secs
      after the last trigger to prevent flash-crash spam.
    """
    raw_last = alert.get("last_price")
    if raw_last is None:
        return None  # No baseline yet; cannot detect a cross

    last_price: Decimal = Decimal(str(raw_last))
    target: Decimal = Decimal(str(alert["target_price"]))
    direction: str = alert["direction"]

    # ---- cooldown guard (uses config value, not a hardcoded constant) ----
    if alert.get("repeat") and alert.get("last_triggered_at"):
        triggered_at: datetime = alert["last_triggered_at"]
        if triggered_at.tzinfo is None:
            triggered_at = triggered_at.replace(tzinfo=timezone.utc)
        elapsed = (datetime.now(timezone.utc) - triggered_at).total_seconds()
        if elapsed < settings.repeat_cooldown_secs:
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
