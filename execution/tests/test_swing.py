"""Tests for SwingTracker — incremental swing pivot detection and sweep tracking.

Covers:
- Pivot detection (confirmed after n_right bars, strict comparison)
- Forward-fill (latest swing level persists until replaced)
- 1-bar shift (sweep uses previous bar's level)
- Sweep detection (strict > / < semantics, matching backtester)
- Day reset (rolling window clears, swing levels persist across days)
- Long-only mode (high sweeps ignored)
- Serialization round-trip
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from trader.engine import Bar
from trader.swing import SweepEvent, SwingTracker

ET = ZoneInfo("America/New_York")


# =============================================================================
# Helpers
# =============================================================================

def make_bar(ts: str, h: float, l: float, o: float = 0, c: float = 0, v: int = 100) -> Bar:
    """Create a Bar. If o/c not specified, default to midpoint."""
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    mid = (h + l) / 2
    return Bar(timestamp=dt, open=o or mid, high=h, low=l, close=c or mid, volume=v)


# =============================================================================
# Pivot detection
# =============================================================================

class TestPivotDetection:
    def test_swing_high_confirmed_after_n_right(self):
        """A swing high at bar[3] is confirmed when bar[6] is fed (n_right=3)."""
        tracker = SwingTracker(n_left=3, n_right=3)

        # Bars 0-2: lower highs (left side)
        # Bar 3: highest high (pivot)
        # Bars 4-6: lower highs (right side)
        bars = [
            make_bar("2025-01-15 09:30", h=100, l=95),  # bar 0
            make_bar("2025-01-15 09:35", h=102, l=96),  # bar 1
            make_bar("2025-01-15 09:40", h=104, l=97),  # bar 2
            make_bar("2025-01-15 09:45", h=110, l=98),  # bar 3 — pivot
            make_bar("2025-01-15 09:50", h=106, l=97),  # bar 4
            make_bar("2025-01-15 09:55", h=103, l=96),  # bar 5
            make_bar("2025-01-15 10:00", h=101, l=95),  # bar 6 — confirms pivot at bar 3
        ]

        import math
        for bar in bars[:6]:
            tracker.on_bar(bar)
        assert math.isnan(tracker.latest_swing_high)

        # Bar 6 confirms the pivot at bar 3
        tracker.on_bar(bars[6])
        assert tracker.latest_swing_high == 110.0

    def test_swing_low_confirmed_after_n_right(self):
        tracker = SwingTracker(n_left=3, n_right=3)

        bars = [
            make_bar("2025-01-15 09:30", h=105, l=100),  # bar 0
            make_bar("2025-01-15 09:35", h=104, l=98),   # bar 1
            make_bar("2025-01-15 09:40", h=103, l=96),   # bar 2
            make_bar("2025-01-15 09:45", h=102, l=90),   # bar 3 — pivot low
            make_bar("2025-01-15 09:50", h=103, l=93),   # bar 4
            make_bar("2025-01-15 09:55", h=104, l=95),   # bar 5
            make_bar("2025-01-15 10:00", h=105, l=97),   # bar 6 — confirms pivot
        ]

        import math
        for bar in bars[:6]:
            tracker.on_bar(bar)
        assert math.isnan(tracker.latest_swing_low)

        tracker.on_bar(bars[6])
        assert tracker.latest_swing_low == 90.0

    def test_equal_high_prevents_pivot(self):
        """Pivot requires STRICTLY greater — equal bars disqualify."""
        tracker = SwingTracker(n_left=3, n_right=3)

        bars = [
            make_bar("2025-01-15 09:30", h=100, l=95),
            make_bar("2025-01-15 09:35", h=102, l=96),
            make_bar("2025-01-15 09:40", h=110, l=97),  # equals pivot
            make_bar("2025-01-15 09:45", h=110, l=98),  # "pivot" — but bar 2 has equal high
            make_bar("2025-01-15 09:50", h=106, l=97),
            make_bar("2025-01-15 09:55", h=103, l=96),
            make_bar("2025-01-15 10:00", h=101, l=95),
        ]

        import math
        for bar in bars:
            tracker.on_bar(bar)
        assert math.isnan(tracker.latest_swing_high)

    def test_equal_low_prevents_pivot(self):
        """Pivot low requires STRICTLY less — equal bars disqualify."""
        tracker = SwingTracker(n_left=3, n_right=3)

        bars = [
            make_bar("2025-01-15 09:30", h=105, l=100),
            make_bar("2025-01-15 09:35", h=104, l=98),
            make_bar("2025-01-15 09:40", h=103, l=90),   # equals pivot
            make_bar("2025-01-15 09:45", h=102, l=90),   # "pivot" — but bar 2 has equal low
            make_bar("2025-01-15 09:50", h=103, l=93),
            make_bar("2025-01-15 09:55", h=104, l=95),
            make_bar("2025-01-15 10:00", h=105, l=97),
        ]

        import math
        for bar in bars:
            tracker.on_bar(bar)
        assert math.isnan(tracker.latest_swing_low)


# =============================================================================
# Forward-fill behavior
# =============================================================================

class TestForwardFill:
    def test_swing_level_persists_until_replaced(self):
        """Once confirmed, latest_swing_high persists through subsequent bars."""
        tracker = SwingTracker(n_left=3, n_right=3)

        # Confirm a swing high
        bars = [
            make_bar("2025-01-15 09:30", h=100, l=95),
            make_bar("2025-01-15 09:35", h=102, l=96),
            make_bar("2025-01-15 09:40", h=104, l=97),
            make_bar("2025-01-15 09:45", h=110, l=98),
            make_bar("2025-01-15 09:50", h=106, l=97),
            make_bar("2025-01-15 09:55", h=103, l=96),
            make_bar("2025-01-15 10:00", h=101, l=95),
        ]
        for bar in bars:
            tracker.on_bar(bar)
        assert tracker.latest_swing_high == 110.0

        # Feed more bars — level persists
        tracker.on_bar(make_bar("2025-01-15 10:05", h=99, l=94))
        assert tracker.latest_swing_high == 110.0

    def test_newer_pivot_replaces_older(self):
        """A newer confirmed pivot replaces the previous one."""
        tracker = SwingTracker(n_left=3, n_right=3)

        # First pivot at bar 3: high=110
        bars = [
            make_bar("2025-01-15 09:30", h=100, l=95),
            make_bar("2025-01-15 09:35", h=102, l=96),
            make_bar("2025-01-15 09:40", h=104, l=97),
            make_bar("2025-01-15 09:45", h=110, l=98),
            make_bar("2025-01-15 09:50", h=106, l=97),
            make_bar("2025-01-15 09:55", h=103, l=96),
            make_bar("2025-01-15 10:00", h=101, l=95),
        ]
        for bar in bars:
            tracker.on_bar(bar)
        assert tracker.latest_swing_high == 110.0

        # Second pivot at bar 10: high=120
        bars2 = [
            make_bar("2025-01-15 10:05", h=112, l=100),
            make_bar("2025-01-15 10:10", h=115, l=102),
            make_bar("2025-01-15 10:15", h=120, l=105),  # new pivot
            make_bar("2025-01-15 10:20", h=116, l=103),
            make_bar("2025-01-15 10:25", h=113, l=101),
            make_bar("2025-01-15 10:30", h=111, l=99),   # confirms new pivot
        ]
        for bar in bars2:
            tracker.on_bar(bar)
        assert tracker.latest_swing_high == 120.0


# =============================================================================
# 1-bar shift (sweep uses previous bar's level)
# =============================================================================

class TestOneBarShift:
    def test_sweep_uses_previous_bars_level(self):
        """Sweep check at bar N uses the swing level that was current at bar N-1."""
        tracker = SwingTracker(n_left=3, n_right=3)

        # Build a confirmed swing low at 90
        bars = [
            make_bar("2025-01-15 09:30", h=105, l=100),
            make_bar("2025-01-15 09:35", h=104, l=98),
            make_bar("2025-01-15 09:40", h=103, l=96),
            make_bar("2025-01-15 09:45", h=102, l=90),   # pivot low
            make_bar("2025-01-15 09:50", h=103, l=93),
            make_bar("2025-01-15 09:55", h=104, l=95),
            make_bar("2025-01-15 10:00", h=105, l=97),   # confirms pivot
        ]
        for bar in bars:
            tracker.on_bar(bar)

        # Bar 7 confirms pivot at 90, but its sweep check uses _prev_swing_low
        # which was NaN before this bar (pivot wasn't confirmed yet).
        # So bar 7 cannot sweep the level it just confirmed.

        # Bar 8: now the level is active. A bar with low <= 90 sweeps.
        sweep = tracker.on_bar(make_bar("2025-01-15 10:05", h=100, l=89))
        assert sweep is not None
        assert sweep.direction == 1
        assert sweep.level == 90.0

    def test_no_sweep_on_confirmation_bar(self):
        """The bar that confirms a pivot cannot sweep it (1-bar shift)."""
        tracker = SwingTracker(n_left=3, n_right=3)

        bars = [
            make_bar("2025-01-15 09:30", h=105, l=100),
            make_bar("2025-01-15 09:35", h=104, l=98),
            make_bar("2025-01-15 09:40", h=103, l=96),
            make_bar("2025-01-15 09:45", h=102, l=90),   # pivot low
            make_bar("2025-01-15 09:50", h=103, l=93),
            make_bar("2025-01-15 09:55", h=104, l=95),
        ]
        for bar in bars:
            tracker.on_bar(bar)

        # This bar confirms the pivot AND has low=85 (below pivot level 90).
        # But sweep check uses _prev_swing_low which was NaN → no sweep.
        sweep = tracker.on_bar(make_bar("2025-01-15 10:00", h=105, l=85))
        assert sweep is None


# =============================================================================
# Sweep detection semantics
# =============================================================================

class TestSweepDetection:
    def _build_confirmed_swing_low(self, tracker: SwingTracker, level: float = 90.0):
        """Helper: feed bars to confirm a swing low at the given level, then one more bar."""
        bars = [
            make_bar("2025-01-15 09:30", h=level + 15, l=level + 10),
            make_bar("2025-01-15 09:35", h=level + 14, l=level + 8),
            make_bar("2025-01-15 09:40", h=level + 13, l=level + 6),
            make_bar("2025-01-15 09:45", h=level + 12, l=level),  # pivot low
            make_bar("2025-01-15 09:50", h=level + 13, l=level + 3),
            make_bar("2025-01-15 09:55", h=level + 14, l=level + 5),
            make_bar("2025-01-15 10:00", h=level + 15, l=level + 7),  # confirms
        ]
        for bar in bars:
            tracker.on_bar(bar)
        # Feed one more bar so the confirmed level is in _prev_swing_low
        tracker.on_bar(make_bar("2025-01-15 10:05", h=level + 15, l=level + 8))

    def test_tick_perfect_touch_does_not_sweep(self):
        """bar.low == swing_low does NOT trigger a sweep (strict <, matching backtester)."""
        tracker = SwingTracker(n_left=3, n_right=3)
        self._build_confirmed_swing_low(tracker, level=90.0)

        sweep = tracker.on_bar(make_bar("2025-01-15 10:10", h=100, l=90.0))
        assert sweep is None

    def test_no_sweep_when_above_level(self):
        """bar.low > swing_low → no sweep."""
        tracker = SwingTracker(n_left=3, n_right=3)
        self._build_confirmed_swing_low(tracker, level=90.0)

        sweep = tracker.on_bar(make_bar("2025-01-15 10:10", h=100, l=90.5))
        assert sweep is None

    def test_sweep_returns_event(self):
        tracker = SwingTracker(n_left=3, n_right=3)
        self._build_confirmed_swing_low(tracker, level=90.0)

        sweep = tracker.on_bar(make_bar("2025-01-15 10:10", h=100, l=85))
        assert isinstance(sweep, SweepEvent)
        assert sweep.source == "swing_low"
        assert sweep.direction == 1
        assert sweep.level == 90.0
        assert sweep.bar_index > 0


# =============================================================================
# Long-only mode
# =============================================================================

class TestLongOnly:
    def _build_confirmed_swing_high(self, tracker: SwingTracker, level: float = 110.0):
        """Helper: confirm a swing high at the given level, then one more bar."""
        bars = [
            make_bar("2025-01-15 09:30", h=level - 10, l=level - 15),
            make_bar("2025-01-15 09:35", h=level - 8, l=level - 14),
            make_bar("2025-01-15 09:40", h=level - 6, l=level - 13),
            make_bar("2025-01-15 09:45", h=level, l=level - 12),       # pivot high
            make_bar("2025-01-15 09:50", h=level - 3, l=level - 13),
            make_bar("2025-01-15 09:55", h=level - 5, l=level - 14),
            make_bar("2025-01-15 10:00", h=level - 7, l=level - 15),   # confirms
        ]
        for bar in bars:
            tracker.on_bar(bar)
        tracker.on_bar(make_bar("2025-01-15 10:05", h=level - 8, l=level - 15))

    def test_high_sweep_ignored_in_long_only(self):
        """In long_only mode, high sweeps should not produce SweepEvent."""
        tracker = SwingTracker(n_left=3, n_right=3, long_only=True)
        self._build_confirmed_swing_high(tracker, level=110.0)

        sweep = tracker.on_bar(make_bar("2025-01-15 10:10", h=115, l=105))
        assert sweep is None

    def test_high_sweep_fires_when_not_long_only(self):
        """In non-long_only mode, high sweeps fire."""
        tracker = SwingTracker(n_left=3, n_right=3, long_only=False)
        self._build_confirmed_swing_high(tracker, level=110.0)

        sweep = tracker.on_bar(make_bar("2025-01-15 10:10", h=115, l=105))
        assert sweep is not None
        assert sweep.source == "swing_high"
        assert sweep.direction == -1
        assert sweep.level == 110.0


# =============================================================================
# Day reset
# =============================================================================

class TestDayReset:
    def test_new_day_preserves_swing_levels(self):
        """Swing levels persist across day boundaries (matching backtester ffill).
        Only the rolling window is cleared on a new day."""
        tracker = SwingTracker(n_left=3, n_right=3)

        # Confirm a pivot on day 1
        bars = [
            make_bar("2025-01-15 09:30", h=105, l=100),
            make_bar("2025-01-15 09:35", h=104, l=98),
            make_bar("2025-01-15 09:40", h=103, l=96),
            make_bar("2025-01-15 09:45", h=102, l=90),
            make_bar("2025-01-15 09:50", h=103, l=93),
            make_bar("2025-01-15 09:55", h=104, l=95),
            make_bar("2025-01-15 10:00", h=105, l=97),
        ]
        for bar in bars:
            tracker.on_bar(bar)
        assert tracker.latest_swing_low == 90.0

        # New day bar → swing levels preserved, rolling window cleared
        tracker.on_bar(make_bar("2025-01-16 09:30", h=105, l=100))
        assert tracker.latest_swing_low == 90.0
        # Rolling window should be cleared (only the new bar is in it)
        assert len(tracker._highs) == 1
        assert len(tracker._lows) == 1


# =============================================================================
# Serialization round-trip
# =============================================================================

class TestSerialization:
    def test_round_trip(self):
        tracker = SwingTracker(n_left=3, n_right=3)

        # Confirm a pivot
        bars = [
            make_bar("2025-01-15 09:30", h=105, l=100),
            make_bar("2025-01-15 09:35", h=104, l=98),
            make_bar("2025-01-15 09:40", h=103, l=96),
            make_bar("2025-01-15 09:45", h=102, l=90),
            make_bar("2025-01-15 09:50", h=103, l=93),
            make_bar("2025-01-15 09:55", h=104, l=95),
            make_bar("2025-01-15 10:00", h=105, l=97),
        ]
        for bar in bars:
            tracker.on_bar(bar)

        data = tracker.to_dict()
        new_tracker = SwingTracker(n_left=3, n_right=3)
        new_tracker.restore(data)

        import math
        assert new_tracker.latest_swing_low == tracker.latest_swing_low
        # Both should be NaN (no swing high confirmed in this bar sequence)
        assert math.isnan(new_tracker.latest_swing_high) == math.isnan(tracker.latest_swing_high)
        assert new_tracker._bar_count == tracker._bar_count
        assert new_tracker._current_date == tracker._current_date
        assert list(new_tracker._highs) == list(tracker._highs)
        assert list(new_tracker._lows) == list(tracker._lows)
