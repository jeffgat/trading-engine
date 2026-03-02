"""Tests for SweepTracker — first-per-day liquidity sweep detection."""

from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from trader.engine import Bar
from trader.liquidity import LiquidityLevels
from trader.sweep import SweepEvent, SweepTracker

ET = ZoneInfo("America/New_York")


def make_bar(ts: str, h: float, l: float) -> Bar:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    return Bar(timestamp=dt, open=(h + l) / 2, high=h, low=l, close=(h + l) / 2, volume=100)


def make_levels(
    kz_high: float = float("nan"),
    kz_low: float = float("nan"),
    pdh: float = float("nan"),
    pdl: float = float("nan"),
) -> LiquidityLevels:
    return LiquidityLevels(kz_high=kz_high, kz_low=kz_low, pdh=pdh, pdl=pdl)


# =============================================================================
# No sweep when levels NaN
# =============================================================================

class TestNoSweepWithNaNLevels:
    def test_all_nan_returns_none(self):
        tracker = SweepTracker()
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19999, 1),  # extreme bar
            make_levels(),  # all NaN
        )
        assert result is None


# =============================================================================
# Low sweeps (bullish direction=+1)
# =============================================================================

class TestLowSweeps:
    def test_kz_low_sweep_bullish(self):
        tracker = SweepTracker()
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19500, 19395),  # low=19395 ≤ kz_low=19400
            make_levels(kz_low=19400.0),
        )
        assert result is not None
        assert result.source == "kz_low"
        assert result.direction == 1
        assert result.level == pytest.approx(19400.0)

    def test_kz_low_no_sweep_when_above(self):
        tracker = SweepTracker()
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19500, 19401),  # low=19401 > kz_low=19400
            make_levels(kz_low=19400.0),
        )
        assert result is None

    def test_kz_low_exact_touch_counts(self):
        """Tick-perfect touch (low == kz_low) must fire sweep (uses <=, not <)."""
        tracker = SweepTracker()
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19500, 19400),  # exact touch
            make_levels(kz_low=19400.0),
        )
        assert result is not None

    def test_pdl_sweep_bullish(self):
        tracker = SweepTracker()
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19500, 19340),
            make_levels(pdl=19350.0),
        )
        assert result is not None
        assert result.source == "pdl"
        assert result.direction == 1


# =============================================================================
# High sweeps (bearish direction=-1) — long_only mode
# =============================================================================

class TestHighSweepsLongOnly:
    def test_kz_high_sweep_ignored_in_long_only(self):
        tracker = SweepTracker(long_only=True)
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19610, 19400),  # high=19610 ≥ kz_high=19600
            make_levels(kz_high=19600.0),
        )
        assert result is None

    def test_pdh_sweep_ignored_in_long_only(self):
        tracker = SweepTracker(long_only=True)
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19610, 19400),
            make_levels(pdh=19600.0),
        )
        assert result is None


# =============================================================================
# High sweeps — non-long-only mode
# =============================================================================

class TestHighSweepsNonLongOnly:
    def test_kz_high_sweep_bearish(self):
        tracker = SweepTracker(long_only=False)
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19610, 19400),
            make_levels(kz_high=19600.0),
        )
        assert result is not None
        assert result.source == "kz_high"
        assert result.direction == -1

    def test_kz_high_exact_touch_counts(self):
        tracker = SweepTracker(long_only=False)
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19600, 19400),  # high == kz_high
            make_levels(kz_high=19600.0),
        )
        assert result is not None

    def test_pdh_sweep_bearish(self):
        tracker = SweepTracker(long_only=False)
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19605, 19400),
            make_levels(pdh=19600.0),
        )
        assert result is not None
        assert result.source == "pdh"
        assert result.direction == -1


# =============================================================================
# First-per-day only
# =============================================================================

class TestFirstPerDay:
    def test_kz_low_only_fires_once_per_day(self):
        tracker = SweepTracker()
        lvl = make_levels(kz_low=19400.0)
        # First sweep fires
        r1 = tracker.on_bar(make_bar("2025-01-15 09:30", 19500, 19395), lvl)
        # Second bar also below kz_low — should NOT fire again
        r2 = tracker.on_bar(make_bar("2025-01-15 09:35", 19490, 19390), lvl)
        assert r1 is not None
        assert r2 is None

    def test_pdl_only_fires_once_per_day(self):
        tracker = SweepTracker()
        lvl = make_levels(pdl=19350.0)
        r1 = tracker.on_bar(make_bar("2025-01-15 09:30", 19500, 19340), lvl)
        r2 = tracker.on_bar(make_bar("2025-01-15 09:35", 19490, 19330), lvl)
        assert r1 is not None
        assert r2 is None

    def test_new_day_resets_first_per_day_flag(self):
        tracker = SweepTracker()
        lvl = make_levels(kz_low=19400.0)
        # Day 1 sweep
        r1 = tracker.on_bar(make_bar("2025-01-15 09:30", 19500, 19395), lvl)
        assert r1 is not None
        # Second bar same day — blocked
        r2 = tracker.on_bar(make_bar("2025-01-15 09:35", 19490, 19390), lvl)
        assert r2 is None
        # Day 2 — same kz_low, should sweep again
        r3 = tracker.on_bar(make_bar("2025-01-16 09:30", 19500, 19395), lvl)
        assert r3 is not None


# =============================================================================
# KZ preferred over PDL on same bar
# =============================================================================

class TestPreference:
    def test_kz_low_preferred_over_pdl_same_bar(self):
        """When both kz_low and pdl are swept on same bar, kz wins."""
        tracker = SweepTracker()
        lvl = make_levels(kz_low=19400.0, pdl=19350.0)
        result = tracker.on_bar(
            make_bar("2025-01-15 09:30", 19500, 19300),  # below both
            lvl,
        )
        assert result is not None
        assert result.source == "kz_low"


# =============================================================================
# Consume sweep / latest sweep property
# =============================================================================

class TestConsumeAndLatest:
    def test_consume_sweep_returns_and_clears(self):
        tracker = SweepTracker()
        lvl = make_levels(kz_low=19400.0)
        tracker.on_bar(make_bar("2025-01-15 09:30", 19500, 19395), lvl)
        # First consume returns the event
        s1 = tracker.consume_sweep()
        assert s1 is not None
        assert s1.source == "kz_low"
        # Second consume returns None
        s2 = tracker.consume_sweep()
        assert s2 is None

    def test_latest_sweep_property(self):
        tracker = SweepTracker()
        lvl = make_levels(kz_low=19400.0)
        assert tracker.latest_sweep is None
        tracker.on_bar(make_bar("2025-01-15 09:30", 19500, 19395), lvl)
        assert tracker.latest_sweep is not None
        tracker.consume_sweep()
        assert tracker.latest_sweep is None


# =============================================================================
# Reset
# =============================================================================

class TestReset:
    def test_reset_clears_all_state(self):
        tracker = SweepTracker()
        lvl = make_levels(kz_low=19400.0)
        tracker.on_bar(make_bar("2025-01-15 09:30", 19500, 19395), lvl)
        tracker.reset()
        assert tracker.latest_sweep is None
        assert tracker._kz_low_swept is False
        assert tracker._pdl_swept is False
        assert tracker._current_date == ""
