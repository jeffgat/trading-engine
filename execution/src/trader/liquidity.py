"""Incremental liquidity level tracking for live LSI engine.

Stateful (bar-by-bar) version of the backtester's vectorized liquidity module.
Tracks killzone session highs/lows and previous day high/low (PDH/PDL).

Usage:
    tracker = LiquidityTracker(killzones=[("Asia", "20:00", "00:00"), ("London", "02:00", "05:00")])
    tracker.on_bar(bar)  # call on every 5m bar
    levels = tracker.levels  # current liquidity levels
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import time


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _time_in_range(t: time, start: time, end: time) -> bool:
    """Check if time t is within [start, end), handling midnight wrap."""
    if start <= end:
        return start <= t < end
    # Wraps midnight: e.g. 20:00 → 00:00
    return t >= start or t < end


@dataclass
class KZState:
    """State for one killzone session."""
    name: str
    start: time
    end: time
    # Running levels during session
    temp_high: float = float("nan")
    temp_low: float = float("nan")
    # Locked levels after session ends
    locked_high: float = float("nan")
    locked_low: float = float("nan")
    _was_in_kz: bool = False


@dataclass
class LiquidityLevels:
    """Current liquidity levels available for sweep detection."""
    kz_high: float = float("nan")
    kz_low: float = float("nan")
    kz_source: str = ""  # name of the KZ that set the levels
    pdh: float = float("nan")
    pdl: float = float("nan")


class LiquidityTracker:
    """Incremental bar-by-bar liquidity level tracker.

    Processes ALL bars (including pre-market/overnight) to track killzone
    sessions and daily highs/lows. Unlike ORBEngine which filters to
    entry windows, this needs the full price stream.
    """

    def __init__(self, killzones: list[tuple[str, str, str]]) -> None:
        self._kz_states: list[KZState] = [
            KZState(name=name, start=_parse_time(start), end=_parse_time(end))
            for name, start, end in killzones
        ]
        # PDH/PDL tracking
        self._cur_day_high: float = float("nan")
        self._cur_day_low: float = float("nan")
        self._pdh: float = float("nan")
        self._pdl: float = float("nan")
        self._current_date: str = ""

        # Merged KZ levels (latest KZ to end overrides earlier)
        self._kz_high: float = float("nan")
        self._kz_low: float = float("nan")
        self._kz_source: str = ""

    @property
    def levels(self) -> LiquidityLevels:
        return LiquidityLevels(
            kz_high=self._kz_high,
            kz_low=self._kz_low,
            kz_source=self._kz_source,
            pdh=self._pdh,
            pdl=self._pdl,
        )

    def on_bar(self, bar) -> None:
        """Process a single bar (5m or 1s). Updates all liquidity levels."""
        bar_time = bar.timestamp.time() if hasattr(bar.timestamp, "time") else bar.timestamp
        bar_date = bar.timestamp.strftime("%Y%m%d") if hasattr(bar.timestamp, "strftime") else ""

        # New day detection
        if bar_date and bar_date != self._current_date:
            self._on_new_day(bar)
            self._current_date = bar_date

        # Update current day high/low
        if math.isnan(self._cur_day_high) or bar.high > self._cur_day_high:
            self._cur_day_high = bar.high
        if math.isnan(self._cur_day_low) or bar.low < self._cur_day_low:
            self._cur_day_low = bar.low

        # Update killzone states
        for kz in self._kz_states:
            in_kz = _time_in_range(bar_time, kz.start, kz.end)

            if in_kz:
                # During session: track running H/L
                if math.isnan(kz.temp_high) or bar.high > kz.temp_high:
                    kz.temp_high = bar.high
                if math.isnan(kz.temp_low) or bar.low < kz.temp_low:
                    kz.temp_low = bar.low

            # Session just ended: lock levels
            if kz._was_in_kz and not in_kz:
                if not math.isnan(kz.temp_high):
                    kz.locked_high = kz.temp_high
                    kz.locked_low = kz.temp_low
                    # Update merged KZ levels (latest KZ overrides)
                    self._kz_high = kz.locked_high
                    self._kz_low = kz.locked_low
                    self._kz_source = kz.name
                # Reset temp for next session
                kz.temp_high = float("nan")
                kz.temp_low = float("nan")

            kz._was_in_kz = in_kz

    def _on_new_day(self, bar) -> None:
        """Lock current day as PDH/PDL, reset for new day."""
        if not math.isnan(self._cur_day_high):
            self._pdh = self._cur_day_high
            self._pdl = self._cur_day_low
        self._cur_day_high = bar.high
        self._cur_day_low = bar.low

        # Reset KZ merged levels on new day
        self._kz_high = float("nan")
        self._kz_low = float("nan")
        self._kz_source = ""

        # Reset KZ locked levels (they need to re-lock each day)
        for kz in self._kz_states:
            kz.locked_high = float("nan")
            kz.locked_low = float("nan")

    def reset(self) -> None:
        """Full reset (e.g. on service restart)."""
        self._cur_day_high = float("nan")
        self._cur_day_low = float("nan")
        self._pdh = float("nan")
        self._pdl = float("nan")
        self._current_date = ""
        self._kz_high = float("nan")
        self._kz_low = float("nan")
        self._kz_source = ""
        for kz in self._kz_states:
            kz.temp_high = float("nan")
            kz.temp_low = float("nan")
            kz.locked_high = float("nan")
            kz.locked_low = float("nan")
            kz._was_in_kz = False
