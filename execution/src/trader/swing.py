"""Incremental swing pivot detection and sweep tracking for live LSI engine.

Stateful (bar-by-bar) port of the backtester's vectorized swing module.
Detects swing highs/lows using a rolling window, then checks for sweeps
when price trades through the most recent confirmed swing level.

A confirmed swing high at bar j requires:
  - n_left bars before j all have strictly lower highs
  - n_right bars after j all have strictly lower highs

Because we need n_right bars after j, the confirmation is known at bar
i = j + n_right. The rolling window must hold n_left + 1 + n_right bars.

Sweep detection uses strict > / < to match the backtesting simulator's
_extract_lsi_candidates logic (high > prev_sh, low < prev_sl).
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass


@dataclass
class SweepEvent:
    """A detected sweep of a liquidity level."""
    source: str       # "swing_high" or "swing_low"
    level: float      # the swing level that was swept
    direction: int    # +1 long setup (low sweep), -1 short setup (high sweep)
    bar_index: int    # bar count when sweep occurred
    pivot_time: str = ""   # timestamp of the pivot bar that formed the swing level ("HH:MM" ET)


class SwingTracker:
    """Incremental swing high/low detection with sweep tracking.

    Maintains a rolling window of bars to detect confirmed pivots,
    then checks if price sweeps the most recent pivot level.

    The sweep check uses the *previous bar's* latest swing level
    (1-bar shift) to avoid same-bar lookahead, matching the
    backtester's np.roll(..., 1) design.
    """

    def __init__(
        self,
        n_left: int = 3,
        n_right: int = 3,
        long_only: bool = True,
        reset_window_on_new_day: bool = True,
        consume_on_sweep: bool = True,
    ) -> None:
        self.n_left = n_left
        self.n_right = n_right
        self.long_only = long_only
        self.reset_window_on_new_day = reset_window_on_new_day
        self.consume_on_sweep = consume_on_sweep

        self._window_size = n_left + 1 + n_right
        # Rolling window of (high, low) tuples
        self._highs: deque[float] = deque(maxlen=self._window_size)
        self._lows: deque[float] = deque(maxlen=self._window_size)
        self._timestamps: deque[str] = deque(maxlen=self._window_size)  # "HH:MM" ET

        self._bar_count: int = 0
        self._current_date: str = ""

        # Forward-filled latest confirmed swing levels
        self._latest_swing_high: float = float("nan")
        self._latest_swing_low: float = float("nan")

        # Timestamps of the pivot bars that formed the swing levels ("HH:MM" ET)
        self._latest_swing_high_time: str = ""
        self._latest_swing_low_time: str = ""

        # Previous bar's swing levels (for 1-bar-shifted sweep check)
        self._prev_swing_high: float = float("nan")
        self._prev_swing_low: float = float("nan")
        self._prev_swing_high_time: str = ""
        self._prev_swing_low_time: str = ""

    @property
    def latest_swing_high(self) -> float:
        return self._latest_swing_high

    @property
    def latest_swing_low(self) -> float:
        return self._latest_swing_low

    def on_bar(self, bar) -> SweepEvent | None:
        """Process a bar: detect pivots, check for sweeps.

        Args:
            bar: Bar with high, low, timestamp attributes.

        Returns:
            SweepEvent if a new sweep was detected, None otherwise.
        """
        bar_date = bar.timestamp.strftime("%Y%m%d") if hasattr(bar.timestamp, "strftime") else ""

        # New day: reset state
        if bar_date and bar_date != self._current_date:
            self._on_new_day(bar_date)

        self._bar_count += 1

        # Save previous bar's swing levels before any update
        self._prev_swing_high = self._latest_swing_high
        self._prev_swing_low = self._latest_swing_low
        self._prev_swing_high_time = self._latest_swing_high_time
        self._prev_swing_low_time = self._latest_swing_low_time

        # Add to rolling window
        bar_time_str = bar.timestamp.strftime("%H:%M") if hasattr(bar.timestamp, "strftime") else ""
        self._highs.append(bar.high)
        self._lows.append(bar.low)
        self._timestamps.append(bar_time_str)

        # Check for confirmed pivot (need full window)
        if len(self._highs) == self._window_size:
            self._check_pivot()

        # Check for sweep using previous bar's levels (1-bar shift)
        return self._check_sweep(bar)

    def _check_pivot(self) -> None:
        """Check if the bar at the pivot position is a confirmed swing high/low.

        The pivot is at index n_left (the center of the window).
        Left bars: indices [0, n_left)
        Right bars: indices [n_left + 1, window_size)
        """
        n_l = self.n_left
        n_r = self.n_right

        pivot_high = self._highs[n_l]
        pivot_low = self._lows[n_l]

        # Swing high: pivot.high > all left highs AND > all right highs
        is_swing_high = True
        for i in range(n_l):
            if self._highs[i] >= pivot_high:
                is_swing_high = False
                break
        if is_swing_high:
            for i in range(n_l + 1, self._window_size):
                if self._highs[i] >= pivot_high:
                    is_swing_high = False
                    break

        # Swing low: pivot.low < all left lows AND < all right lows
        is_swing_low = True
        for i in range(n_l):
            if self._lows[i] <= pivot_low:
                is_swing_low = False
                break
        if is_swing_low:
            for i in range(n_l + 1, self._window_size):
                if self._lows[i] <= pivot_low:
                    is_swing_low = False
                    break

        if is_swing_high:
            self._latest_swing_high = pivot_high
            self._latest_swing_high_time = self._timestamps[n_l] if len(self._timestamps) > n_l else ""

        if is_swing_low:
            self._latest_swing_low = pivot_low
            self._latest_swing_low_time = self._timestamps[n_l] if len(self._timestamps) > n_l else ""

    def _check_sweep(self, bar) -> SweepEvent | None:
        """Check if bar sweeps the previous bar's swing level.

        Uses previous bar's level (1-bar shift) to avoid same-bar
        lookahead. Uses strict > / < to match the backtester's
        _extract_lsi_candidates sweep detection.
        """
        sweep = None

        # Low sweep of swing low → bullish setup (direction=+1)
        if not math.isnan(self._prev_swing_low) and bar.low < self._prev_swing_low:
            sweep = SweepEvent(
                source="swing_low",
                level=self._prev_swing_low,
                direction=1,
                bar_index=self._bar_count,
                pivot_time=self._prev_swing_low_time,
            )
            if self.consume_on_sweep:
                self._consume_low_level(self._prev_swing_low)

        # High sweep of swing high → bearish setup (direction=-1)
        if not math.isnan(self._prev_swing_high) and bar.high > self._prev_swing_high:
            if self.consume_on_sweep:
                self._consume_high_level(self._prev_swing_high)
            if not self.long_only:
                # Low sweep takes priority (same as old tracker preferring kz_low)
                if sweep is None:
                    sweep = SweepEvent(
                        source="swing_high",
                        level=self._prev_swing_high,
                        direction=-1,
                        bar_index=self._bar_count,
                        pivot_time=self._prev_swing_high_time,
                    )

        return sweep

    def _consume_low_level(self, level: float) -> None:
        if math.isclose(self._latest_swing_low, level, rel_tol=0.0, abs_tol=1e-9):
            self._latest_swing_low = float("nan")
            self._latest_swing_low_time = ""
        self._prev_swing_low = float("nan")
        self._prev_swing_low_time = ""

    def _consume_high_level(self, level: float) -> None:
        if math.isclose(self._latest_swing_high, level, rel_tol=0.0, abs_tol=1e-9):
            self._latest_swing_high = float("nan")
            self._latest_swing_high_time = ""
        self._prev_swing_high = float("nan")
        self._prev_swing_high_time = ""

    def _on_new_day(self, new_date: str) -> None:
        """Update date tracking for new trading day.

        Swing levels are NOT reset — the backtester's vectorized ffill()
        carries swing levels across day boundaries, so the live engine
        must preserve them as well.  Only the rolling window is cleared
        so pivot detection restarts cleanly.
        """
        self._current_date = new_date
        if self.reset_window_on_new_day:
            self._highs.clear()
            self._lows.clear()
            self._timestamps.clear()
        # NOTE: _latest_swing_high/low and _prev_swing_high/low (and their
        # timestamps) are intentionally preserved across days to match the
        # backtester.

    def reset(self) -> None:
        """Full reset (e.g. on service restart)."""
        self._bar_count = 0
        self._current_date = ""
        self._on_new_day("")

    # ------------------------------------------------------------------
    # Serialization support (for checkpoint/restore)
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize tracker state for checkpointing."""
        return {
            "n_left": self.n_left,
            "n_right": self.n_right,
            "long_only": self.long_only,
            "reset_window_on_new_day": self.reset_window_on_new_day,
            "consume_on_sweep": self.consume_on_sweep,
            "bar_count": self._bar_count,
            "current_date": self._current_date,
            "highs": list(self._highs),
            "lows": list(self._lows),
            "timestamps": list(self._timestamps),
            "latest_swing_high": self._latest_swing_high if not math.isnan(self._latest_swing_high) else None,
            "latest_swing_low": self._latest_swing_low if not math.isnan(self._latest_swing_low) else None,
            "latest_swing_high_time": self._latest_swing_high_time,
            "latest_swing_low_time": self._latest_swing_low_time,
            "prev_swing_high": self._prev_swing_high if not math.isnan(self._prev_swing_high) else None,
            "prev_swing_low": self._prev_swing_low if not math.isnan(self._prev_swing_low) else None,
            "prev_swing_high_time": self._prev_swing_high_time,
            "prev_swing_low_time": self._prev_swing_low_time,
        }

    def restore(self, data: dict) -> None:
        """Restore tracker state from checkpoint data."""
        self._bar_count = data.get("bar_count", 0)
        self._current_date = data.get("current_date", "")
        self.reset_window_on_new_day = data.get("reset_window_on_new_day", self.reset_window_on_new_day)
        self.consume_on_sweep = data.get("consume_on_sweep", self.consume_on_sweep)

        self._highs.clear()
        for h in data.get("highs", []):
            self._highs.append(h)

        self._lows.clear()
        for l in data.get("lows", []):
            self._lows.append(l)

        self._timestamps.clear()
        for t in data.get("timestamps", []):
            self._timestamps.append(t)

        lsh = data.get("latest_swing_high")
        self._latest_swing_high = lsh if lsh is not None else float("nan")

        lsl = data.get("latest_swing_low")
        self._latest_swing_low = lsl if lsl is not None else float("nan")

        self._latest_swing_high_time = data.get("latest_swing_high_time", "")
        self._latest_swing_low_time = data.get("latest_swing_low_time", "")

        psh = data.get("prev_swing_high")
        self._prev_swing_high = psh if psh is not None else float("nan")

        psl = data.get("prev_swing_low")
        self._prev_swing_low = psl if psl is not None else float("nan")

        self._prev_swing_high_time = data.get("prev_swing_high_time", "")
        self._prev_swing_low_time = data.get("prev_swing_low_time", "")
