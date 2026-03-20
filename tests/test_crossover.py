"""
tests/test_crossover.py — Unit tests for check_crossover() in alerts.py.

These are pure unit tests — no DB, no Discord, no network.
Run with:  pytest tests/test_crossover.py -v
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from alerts import check_crossover, REPEAT_COOLDOWN_SECONDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_alert(
    *,
    id: int = 1,
    symbol: str = "BTCUSDT",
    direction: str = "above",
    target_price: float = 70_000.0,
    last_price: float | None = 69_000.0,
    repeat: bool = False,
    last_triggered_at: datetime | None = None,
) -> dict:
    return {
        "id": id,
        "symbol": symbol,
        "direction": direction,
        "target_price": target_price,
        "last_price": last_price,
        "repeat": repeat,
        "last_triggered_at": last_triggered_at,
    }


def dec(value: float) -> Decimal:
    return Decimal(str(value))


# ---------------------------------------------------------------------------
# "above" direction
# ---------------------------------------------------------------------------

class TestAboveDirection:

    def test_fires_when_price_crosses_above(self):
        alert = make_alert(direction="above", target_price=70_000, last_price=69_999.99)
        assert check_crossover(alert, dec(70_000.0)) == "above"

    def test_fires_when_price_lands_exactly_on_target(self):
        alert = make_alert(direction="above", target_price=70_000, last_price=69_999)
        assert check_crossover(alert, dec(70_000)) == "above"

    def test_fires_when_price_overshoots_target(self):
        alert = make_alert(direction="above", target_price=70_000, last_price=65_000)
        assert check_crossover(alert, dec(75_000)) == "above"

    def test_no_fire_when_price_stays_below_target(self):
        alert = make_alert(direction="above", target_price=70_000, last_price=65_000)
        assert check_crossover(alert, dec(69_999)) is None

    def test_no_fire_when_price_already_above_and_stays_above(self):
        """last_price is already above target — not a cross."""
        alert = make_alert(direction="above", target_price=70_000, last_price=71_000)
        assert check_crossover(alert, dec(72_000)) is None

    def test_no_fire_when_above_alert_price_crosses_below(self):
        """An 'above' alert must not fire on a downward cross."""
        alert = make_alert(direction="above", target_price=70_000, last_price=71_000)
        assert check_crossover(alert, dec(69_000)) is None

    def test_no_fire_when_last_price_missing(self):
        """Cannot compute a cross without a baseline."""
        alert = make_alert(direction="above", last_price=None)
        assert check_crossover(alert, dec(75_000)) is None


# ---------------------------------------------------------------------------
# "below" direction
# ---------------------------------------------------------------------------

class TestBelowDirection:

    def test_fires_when_price_crosses_below(self):
        alert = make_alert(direction="below", target_price=60_000, last_price=60_001)
        assert check_crossover(alert, dec(60_000.0)) == "below"

    def test_fires_when_price_lands_exactly_on_target(self):
        alert = make_alert(direction="below", target_price=60_000, last_price=60_001)
        assert check_crossover(alert, dec(60_000)) == "below"

    def test_fires_when_price_undershoots_target(self):
        alert = make_alert(direction="below", target_price=60_000, last_price=65_000)
        assert check_crossover(alert, dec(55_000)) == "below"

    def test_no_fire_when_price_stays_above_target(self):
        alert = make_alert(direction="below", target_price=60_000, last_price=65_000)
        assert check_crossover(alert, dec(61_000)) is None

    def test_no_fire_when_price_already_below_and_stays_below(self):
        alert = make_alert(direction="below", target_price=60_000, last_price=55_000)
        assert check_crossover(alert, dec(54_000)) is None

    def test_no_fire_when_below_alert_price_crosses_above(self):
        alert = make_alert(direction="below", target_price=60_000, last_price=55_000)
        assert check_crossover(alert, dec(65_000)) is None


# ---------------------------------------------------------------------------
# "both" direction
# ---------------------------------------------------------------------------

class TestBothDirection:

    def test_fires_above_on_upward_cross(self):
        alert = make_alert(direction="both", target_price=70_000, last_price=69_000)
        assert check_crossover(alert, dec(70_001)) == "above"

    def test_fires_below_on_downward_cross(self):
        alert = make_alert(direction="both", target_price=70_000, last_price=71_000)
        assert check_crossover(alert, dec(69_999)) == "below"

    def test_no_fire_when_price_does_not_cross(self):
        alert = make_alert(direction="both", target_price=70_000, last_price=65_000)
        assert check_crossover(alert, dec(68_000)) is None


# ---------------------------------------------------------------------------
# Repeat cooldown logic
# ---------------------------------------------------------------------------

class TestRepeatCooldown:

    def test_no_fire_during_cooldown(self):
        """Alert fired 60 seconds ago — still within 5-min cooldown."""
        recently = datetime.now(timezone.utc) - timedelta(seconds=60)
        alert = make_alert(
            direction="above",
            target_price=70_000,
            last_price=69_000,
            repeat=True,
            last_triggered_at=recently,
        )
        assert check_crossover(alert, dec(71_000)) is None

    def test_fires_after_cooldown_expires(self):
        """Alert fired 6 minutes ago — cooldown has passed."""
        long_ago = datetime.now(timezone.utc) - timedelta(
            seconds=REPEAT_COOLDOWN_SECONDS + 60
        )
        alert = make_alert(
            direction="above",
            target_price=70_000,
            last_price=69_000,
            repeat=True,
            last_triggered_at=long_ago,
        )
        assert check_crossover(alert, dec(71_000)) == "above"

    def test_fires_on_first_trigger_even_with_repeat_enabled(self):
        """repeat=True, but never triggered before — no cooldown applies."""
        alert = make_alert(
            direction="above",
            target_price=70_000,
            last_price=69_000,
            repeat=True,
            last_triggered_at=None,
        )
        assert check_crossover(alert, dec(71_000)) == "above"

    def test_one_shot_alert_ignores_cooldown_entirely(self):
        """repeat=False alerts have no cooldown — the cache removes them on fire."""
        recently = datetime.now(timezone.utc) - timedelta(seconds=10)
        alert = make_alert(
            direction="above",
            target_price=70_000,
            last_price=69_000,
            repeat=False,
            last_triggered_at=recently,
        )
        # Should fire — cooldown is only checked when repeat=True
        assert check_crossover(alert, dec(71_000)) == "above"

    def test_cooldown_with_naive_datetime_handled_gracefully(self):
        """DB may return a naive datetime — must not crash."""
        naive_dt = datetime.utcnow() - timedelta(seconds=30)
        alert = make_alert(
            direction="above",
            target_price=70_000,
            last_price=69_000,
            repeat=True,
            last_triggered_at=naive_dt,
        )
        # Still in cooldown — should NOT fire
        assert check_crossover(alert, dec(71_000)) is None


# ---------------------------------------------------------------------------
# Decimal precision (the whole reason we use Decimal)
# ---------------------------------------------------------------------------

class TestDecimalPrecision:

    def test_no_float_rounding_error_on_exact_boundary(self):
        """
        0.1 + 0.2 != 0.3 in float land.
        Verify that Decimal handles boundaries that would trip up float math.
        """
        target = 0.1 + 0.2   # float: 0.30000000000000004
        last   = 0.29

        alert = make_alert(
            direction="above",
            target_price=target,
            last_price=last,
        )
        # With Decimal, this must fire cleanly at exactly Decimal("0.3")
        result = check_crossover(alert, Decimal("0.3"))
        assert result == "above"

    def test_very_small_price_shitcoin(self):
        """Verify sub-satoshi prices (e.g. SHIBUSDT) don't lose precision."""
        alert = make_alert(
            direction="above",
            target_price=0.00002500,
            last_price=0.00002499,
        )
        assert check_crossover(alert, dec(0.00002500)) == "above"

    def test_very_large_price_bitcoin(self):
        """High-value assets with 2 decimal places should work correctly."""
        alert = make_alert(
            direction="above",
            target_price=100_000.00,
            last_price=99_999.99,
        )
        assert check_crossover(alert, dec(100_000.00)) == "above"
