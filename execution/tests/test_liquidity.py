"""Tests for LiquidityTracker — killzone sessions and PDH/PDL tracking."""

from __future__ import annotations

import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trader.engine import Bar
from trader.liquidity import LiquidityLevels, LiquidityTracker

ET = ZoneInfo("America/New_York")

ASIA_KZ = [("Asia", "20:00", "00:00")]
TWO_KZ = [("Asia", "20:00", "00:00"), ("London", "02:00", "05:00")]


def make_bar(ts: str, h: float, l: float, tz=ET) -> Bar:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    mid = (h + l) / 2
    return Bar(timestamp=dt, open=mid, high=h, low=l, close=mid, volume=100)


# =============================================================================
# Initial state
# =============================================================================

class TestInitialState:
    def test_all_levels_nan_on_init(self):
        tracker = LiquidityTracker(ASIA_KZ)
        lvl = tracker.levels
        assert math.isnan(lvl.kz_high)
        assert math.isnan(lvl.kz_low)
        assert math.isnan(lvl.pdh)
        assert math.isnan(lvl.pdl)
        assert lvl.kz_source == ""


# =============================================================================
# KZ tracking
# =============================================================================

class TestKZTracking:
    def test_kz_levels_nan_during_session(self):
        """Locked KZ levels not set until session ENDS."""
        tracker = LiquidityTracker(ASIA_KZ)
        # Feed bars inside Asia (20:00 - 23:59) — session not yet ended
        for h in range(3):
            tracker.on_bar(make_bar("2025-01-14 20:00", 19500 + h * 10, 19480 + h * 5))
            tracker.on_bar(make_bar("2025-01-14 21:00", 19520 + h * 10, 19460 + h * 5))
        # Still inside Asia (00:00 would be the boundary)
        assert math.isnan(tracker.levels.kz_high)

    def test_kz_locks_on_session_end(self):
        """After Asia session ends, kz_high/kz_low reflect session extremes."""
        tracker = LiquidityTracker(ASIA_KZ)
        # Feed Asia bars Jan 14 (20:00 - 23:55)
        tracker.on_bar(make_bar("2025-01-14 20:00", 19600.0, 19400.0))
        tracker.on_bar(make_bar("2025-01-14 22:00", 19580.0, 19420.0))
        # Feed bar at 00:05 Jan 15 → Asia session ended → lock
        tracker.on_bar(make_bar("2025-01-15 00:05", 19550.0, 19450.0))
        lvl = tracker.levels
        assert lvl.kz_high == pytest.approx(19600.0)
        assert lvl.kz_low == pytest.approx(19400.0)
        assert lvl.kz_source == "Asia"

    def test_kz_source_name(self):
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-14 21:00", 19500.0, 19480.0))
        tracker.on_bar(make_bar("2025-01-15 00:05", 19490.0, 19485.0))
        assert tracker.levels.kz_source == "Asia"

    def test_second_kz_overrides_first(self):
        """Latest KZ session to end overwrites earlier one."""
        tracker = LiquidityTracker(TWO_KZ)
        # Asia session Jan 14
        tracker.on_bar(make_bar("2025-01-14 21:00", 19700.0, 19300.0))
        # End Asia (bar at 00:05)
        tracker.on_bar(make_bar("2025-01-15 00:05", 19600.0, 19400.0))
        # London session Jan 15 (02:00 - 04:55)
        tracker.on_bar(make_bar("2025-01-15 02:00", 19650.0, 19450.0))
        tracker.on_bar(make_bar("2025-01-15 04:30", 19680.0, 19420.0))
        # End London (bar at 05:00)
        tracker.on_bar(make_bar("2025-01-15 05:00", 19660.0, 19440.0))
        lvl = tracker.levels
        assert lvl.kz_source == "London"
        assert lvl.kz_high == pytest.approx(19680.0)
        assert lvl.kz_low == pytest.approx(19420.0)

    def test_kz_temp_resets_after_lock(self):
        """After Asia locks, locked levels persist through the same calendar day.
        Only on the NEXT calendar day (Jan 16) do they reset.
        """
        tracker = LiquidityTracker(ASIA_KZ)
        # Day 1 Asia: Jan 14 20:00 session, locks at Jan 15 00:05
        tracker.on_bar(make_bar("2025-01-14 21:00", 19600.0, 19400.0))
        tracker.on_bar(make_bar("2025-01-15 00:05", 19590.0, 19410.0))
        assert tracker.levels.kz_high == pytest.approx(19600.0)

        # Same calendar day (Jan 15) — locked levels persist
        tracker.on_bar(make_bar("2025-01-15 09:00", 19500.0, 19480.0))
        assert tracker.levels.kz_high == pytest.approx(19600.0)

        # NEW calendar day (Jan 16) → locked levels reset to NaN until next KZ locks
        tracker.on_bar(make_bar("2025-01-16 00:00", 19500.0, 19480.0))
        assert math.isnan(tracker.levels.kz_high)

    def test_kz_levels_reset_on_new_day(self):
        """KZ levels reset to NaN at the start of a new calendar day.

        The Asia session at 20:00 on Jan 14 locks at Jan 15 00:05.
        The locked levels persist through Jan 15.
        On Jan 16 (the next calendar day), they reset to NaN.
        """
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-14 21:00", 19600.0, 19400.0))
        tracker.on_bar(make_bar("2025-01-15 00:05", 19590.0, 19410.0))  # locks Asia

        # Feed Jan 15 regular hours — still same day, levels retained
        tracker.on_bar(make_bar("2025-01-15 09:30", 19500.0, 19490.0))
        assert tracker.levels.kz_high == pytest.approx(19600.0)

        # Jan 16 → levels reset
        tracker.on_bar(make_bar("2025-01-16 00:00", 19500.0, 19490.0))
        assert math.isnan(tracker.levels.kz_high)

    def test_midnight_wrap_kz_in_session(self):
        """Bar at 23:55 should be IN Asia session (20:00 to 00:00)."""
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-14 23:55", 19600.0, 19400.0))
        # Session not yet ended — should still be accumulating
        assert math.isnan(tracker.levels.kz_high)

    def test_midnight_wrap_kz_out_of_session(self):
        """Bar at 00:05 triggers Asia session lock."""
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-14 23:55", 19600.0, 19400.0))
        tracker.on_bar(make_bar("2025-01-15 00:05", 19550.0, 19450.0))
        lvl = tracker.levels
        assert not math.isnan(lvl.kz_high)


# =============================================================================
# PDH/PDL tracking
# =============================================================================

class TestPDHPDL:
    def test_pdh_pdl_nan_on_first_day(self):
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-15 09:30", 19600.0, 19400.0))
        assert math.isnan(tracker.levels.pdh)
        assert math.isnan(tracker.levels.pdl)

    def test_pdh_pdl_set_after_day_rollover(self):
        """Jan 15 H/L becomes Jan 16 PDH/PDL."""
        tracker = LiquidityTracker(ASIA_KZ)
        # Jan 15 bars
        tracker.on_bar(make_bar("2025-01-15 09:30", 19600.0, 19400.0))
        tracker.on_bar(make_bar("2025-01-15 12:00", 19580.0, 19420.0))
        # First bar of Jan 16 → locks Jan 15 as PDH/PDL
        tracker.on_bar(make_bar("2025-01-16 09:30", 19550.0, 19450.0))
        lvl = tracker.levels
        assert lvl.pdh == pytest.approx(19600.0)
        assert lvl.pdl == pytest.approx(19400.0)

    def test_pdh_pdl_updates_each_new_day(self):
        """Each new day, PDH/PDL reflect PREVIOUS day, not older days."""
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-15 09:30", 19700.0, 19300.0))  # Day 15: H=19700, L=19300
        tracker.on_bar(make_bar("2025-01-16 09:30", 19550.0, 19500.0))  # Day 16: previous=19700/19300
        tracker.on_bar(make_bar("2025-01-17 09:30", 19520.0, 19480.0))  # Day 17: previous=19550/19500
        lvl = tracker.levels
        assert lvl.pdh == pytest.approx(19550.0)
        assert lvl.pdl == pytest.approx(19500.0)

    def test_current_day_high_low_tracked(self):
        """Running day H/L from multiple intraday bars."""
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-15 09:30", 19560.0, 19500.0))
        tracker.on_bar(make_bar("2025-01-15 10:00", 19580.0, 19480.0))  # new high and low
        tracker.on_bar(make_bar("2025-01-15 11:00", 19550.0, 19490.0))
        # Lock Jan 15 as PDH/PDL by feeding Jan 16
        tracker.on_bar(make_bar("2025-01-16 09:30", 19540.0, 19510.0))
        assert tracker.levels.pdh == pytest.approx(19580.0)
        assert tracker.levels.pdl == pytest.approx(19480.0)


# =============================================================================
# Reset
# =============================================================================

class TestReset:
    def test_reset_clears_all_state(self):
        tracker = LiquidityTracker(ASIA_KZ)
        tracker.on_bar(make_bar("2025-01-14 21:00", 19600.0, 19400.0))
        tracker.on_bar(make_bar("2025-01-15 00:05", 19590.0, 19410.0))
        tracker.on_bar(make_bar("2025-01-16 09:30", 19550.0, 19450.0))

        tracker.reset()
        lvl = tracker.levels
        assert math.isnan(lvl.kz_high)
        assert math.isnan(lvl.kz_low)
        assert math.isnan(lvl.pdh)
        assert math.isnan(lvl.pdl)
        assert tracker._current_date == ""
