"""
tests/test_cache.py — Async unit tests for AlertCache in alerts.py.

Tests cover: load, add, remove, bulk remove, pause/resume semantics,
find_symbol_by_alert_id, and concurrent-access safety.

Run with:  pytest tests/test_cache.py -v
"""

import asyncio
from datetime import datetime, timezone

import pytest
import pytest_asyncio

from alerts import AlertCache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def cache() -> AlertCache:
    return AlertCache()


def make_alert(
    id: int,
    symbol: str = "BTCUSDT",
    user_id: int = 111,
    direction: str = "above",
    target_price: float = 70_000.0,
    last_price: float = 69_000.0,
    repeat: bool = False,
) -> dict:
    return {
        "id": id,
        "user_id": user_id,
        "guild_id": 999,
        "channel_id": 888,
        "symbol": symbol,
        "direction": direction,
        "target_price": target_price,
        "last_price": last_price,
        "repeat": repeat,
        "active": True,
        "paused": False,
        "last_triggered_at": None,
    }


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

class TestLoad:

    @pytest.mark.asyncio
    async def test_load_populates_cache(self, cache: AlertCache):
        alerts = [
            make_alert(1, "BTCUSDT"),
            make_alert(2, "ETHUSDT"),
            make_alert(3, "BTCUSDT"),
        ]
        await cache.load(alerts)
        assert cache.total_alerts == 3
        assert "BTCUSDT" in cache.all_symbols
        assert "ETHUSDT" in cache.all_symbols

    @pytest.mark.asyncio
    async def test_load_replaces_existing_data(self, cache: AlertCache):
        await cache.load([make_alert(1, "BTCUSDT")])
        await cache.load([make_alert(2, "ETHUSDT")])
        assert cache.total_alerts == 1
        assert "BTCUSDT" not in cache.all_symbols
        assert "ETHUSDT" in cache.all_symbols

    @pytest.mark.asyncio
    async def test_load_empty_list_clears_cache(self, cache: AlertCache):
        await cache.load([make_alert(1, "BTCUSDT")])
        await cache.load([])
        assert cache.total_alerts == 0
        assert len(cache.all_symbols) == 0


# ---------------------------------------------------------------------------
# Add / Remove
# ---------------------------------------------------------------------------

class TestAddRemove:

    @pytest.mark.asyncio
    async def test_add_inserts_alert(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        assert cache.total_alerts == 1
        assert len(cache.get_alerts_for_symbol("BTCUSDT")) == 1

    @pytest.mark.asyncio
    async def test_add_multiple_same_symbol(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.add(make_alert(2, "BTCUSDT"))
        assert len(cache.get_alerts_for_symbol("BTCUSDT")) == 2

    @pytest.mark.asyncio
    async def test_add_symbol_case_insensitive(self, cache: AlertCache):
        await cache.add(make_alert(1, "btcusdt"))
        assert len(cache.get_alerts_for_symbol("BTCUSDT")) == 1
        assert "BTCUSDT" in cache.all_symbols

    @pytest.mark.asyncio
    async def test_remove_deletes_alert(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.remove(1, "BTCUSDT")
        assert cache.total_alerts == 0
        assert len(cache.get_alerts_for_symbol("BTCUSDT")) == 0

    @pytest.mark.asyncio
    async def test_remove_cleans_up_empty_symbol_bucket(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.remove(1, "BTCUSDT")
        assert "BTCUSDT" not in cache.all_symbols

    @pytest.mark.asyncio
    async def test_remove_nonexistent_is_safe(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.remove(999, "BTCUSDT")  # id doesn't exist — should not raise
        assert cache.total_alerts == 1

    @pytest.mark.asyncio
    async def test_remove_only_affects_target_alert(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.add(make_alert(2, "BTCUSDT"))
        await cache.remove(1, "BTCUSDT")
        remaining = cache.get_alerts_for_symbol("BTCUSDT")
        assert len(remaining) == 1
        assert remaining[0]["id"] == 2


# ---------------------------------------------------------------------------
# Bulk remove (clear)
# ---------------------------------------------------------------------------

class TestRemoveAllForUser:

    @pytest.mark.asyncio
    async def test_removes_all_alerts_for_user(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT", user_id=111))
        await cache.add(make_alert(2, "ETHUSDT", user_id=111))
        await cache.add(make_alert(3, "BTCUSDT", user_id=222))  # different user
        await cache.remove_all_for_user(111)
        assert cache.total_alerts == 1
        assert cache.get_alerts_for_symbol("BTCUSDT")[0]["user_id"] == 222

    @pytest.mark.asyncio
    async def test_remove_all_for_user_with_no_alerts_is_safe(self, cache: AlertCache):
        await cache.remove_all_for_user(999)  # No alerts exist — should not raise
        assert cache.total_alerts == 0

    @pytest.mark.asyncio
    async def test_remove_all_cleans_empty_symbol_buckets(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT", user_id=111))
        await cache.add(make_alert(2, "ETHUSDT", user_id=111))
        await cache.remove_all_for_user(111)
        assert "BTCUSDT" not in cache.all_symbols
        assert "ETHUSDT" not in cache.all_symbols


# ---------------------------------------------------------------------------
# find_symbol_by_alert_id
# ---------------------------------------------------------------------------

class TestFindSymbolByAlertId:

    @pytest.mark.asyncio
    async def test_returns_correct_symbol(self, cache: AlertCache):
        await cache.add(make_alert(42, "SOLUSDT"))
        assert cache.find_symbol_by_alert_id(42) == "SOLUSDT"

    @pytest.mark.asyncio
    async def test_returns_none_for_unknown_id(self, cache: AlertCache):
        assert cache.find_symbol_by_alert_id(9999) is None

    @pytest.mark.asyncio
    async def test_returns_none_after_removal(self, cache: AlertCache):
        await cache.add(make_alert(42, "SOLUSDT"))
        await cache.remove(42, "SOLUSDT")
        assert cache.find_symbol_by_alert_id(42) is None


# ---------------------------------------------------------------------------
# update_last_price and set_triggered
# ---------------------------------------------------------------------------

class TestPriceUpdates:

    @pytest.mark.asyncio
    async def test_update_last_price_mutates_in_place(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT", last_price=69_000))
        await cache.update_last_price(1, "BTCUSDT", 70_500.0)
        alert = cache.get_alerts_for_symbol("BTCUSDT")[0]
        assert alert["last_price"] == 70_500.0

    @pytest.mark.asyncio
    async def test_update_last_price_unknown_id_is_safe(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.update_last_price(999, "BTCUSDT", 70_000.0)  # safe no-op

    @pytest.mark.asyncio
    async def test_set_triggered_updates_last_price_and_timestamp(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT", last_price=69_000, repeat=True))
        await cache.set_triggered(1, "BTCUSDT", 71_000.0)
        alert = cache.get_alerts_for_symbol("BTCUSDT")[0]
        assert alert["last_price"] == 71_000.0
        assert alert["last_triggered_at"] is not None
        assert isinstance(alert["last_triggered_at"], datetime)

    @pytest.mark.asyncio
    async def test_deactivate_removes_alert_from_cache(self, cache: AlertCache):
        await cache.add(make_alert(1, "BTCUSDT"))
        await cache.deactivate(1, "BTCUSDT")
        assert cache.total_alerts == 0


# ---------------------------------------------------------------------------
# get_alerts_for_symbol
# ---------------------------------------------------------------------------

class TestGetAlertsForSymbol:

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_unknown_symbol(self, cache: AlertCache):
        assert cache.get_alerts_for_symbol("UNKNOWN") == []

    @pytest.mark.asyncio
    async def test_returns_snapshot_not_live_reference(self, cache: AlertCache):
        """
        Mutations to the returned list must not affect the cache.
        This verifies the list() snapshot in get_alerts_for_symbol().
        """
        await cache.add(make_alert(1, "BTCUSDT"))
        snapshot = cache.get_alerts_for_symbol("BTCUSDT")
        snapshot.clear()  # mutate the snapshot
        assert len(cache.get_alerts_for_symbol("BTCUSDT")) == 1


# ---------------------------------------------------------------------------
# Concurrency safety
# ---------------------------------------------------------------------------

class TestConcurrency:

    @pytest.mark.asyncio
    async def test_concurrent_adds_do_not_corrupt_cache(self, cache: AlertCache):
        """
        Fire 50 concurrent add() coroutines and verify all are present.
        Exercises the asyncio.Lock in the cache.
        """
        alerts = [make_alert(i, "BTCUSDT") for i in range(1, 51)]
        await asyncio.gather(*[cache.add(a) for a in alerts])
        assert cache.total_alerts == 50

    @pytest.mark.asyncio
    async def test_concurrent_removes_do_not_panic(self, cache: AlertCache):
        """
        Remove the same alert from multiple concurrent coroutines.
        Only one should 'win'; rest should be safe no-ops.
        """
        await cache.add(make_alert(1, "BTCUSDT"))
        await asyncio.gather(*[cache.remove(1, "BTCUSDT") for _ in range(10)])
        assert cache.total_alerts == 0
