"""Incremental sweep detection for live IFVG engine.

Stateful (bar-by-bar) version of the backtester's vectorized sweep module.
Detects first-per-day sweep of each liquidity level (KZ high/low, PDH/PDL).

A "sweep" occurs when price trades beyond a liquidity level:
    - High sweep (bar.high > level): bearish signal (reversal short)
    - Low sweep (bar.low < level): bullish signal (reversal long)

Each level can only be swept once per day (first sweep wins).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SweepEvent:
    """A detected sweep of a liquidity level."""
    source: str  # "kz_high", "kz_low", "pdh", "pdl"
    level: float  # the liquidity level that was swept
    direction: int  # +1 long setup (low sweep), -1 short setup (high sweep)
    bar_index: int  # bar count when sweep occurred


class SweepTracker:
    """Incremental first-per-day sweep detection.

    Tracks whether each liquidity level type has been swept today.
    Resets on new trading day. Only long setups are tracked for long_only mode.
    """

    def __init__(self, long_only: bool = True) -> None:
        self._long_only = long_only
        self._bar_count: int = 0
        self._current_date: str = ""

        # Per-day sweep state
        self._kz_high_swept: bool = False
        self._kz_low_swept: bool = False
        self._pdh_swept: bool = False
        self._pdl_swept: bool = False

        # Most recent sweep event (cleared on new day or when consumed)
        self._latest_sweep: SweepEvent | None = None

    @property
    def latest_sweep(self) -> SweepEvent | None:
        return self._latest_sweep

    def consume_sweep(self) -> SweepEvent | None:
        """Return and clear the latest sweep event."""
        s = self._latest_sweep
        self._latest_sweep = None
        return s

    def on_bar(self, bar, levels) -> SweepEvent | None:
        """Check for sweeps against current liquidity levels.

        Args:
            bar: Bar with high, low, timestamp attributes.
            levels: LiquidityLevels from LiquidityTracker.

        Returns:
            SweepEvent if a new sweep was detected, None otherwise.
        """
        bar_date = bar.timestamp.strftime("%Y%m%d") if hasattr(bar.timestamp, "strftime") else ""

        # New day: reset sweep flags
        if bar_date and bar_date != self._current_date:
            self._current_date = bar_date
            self._kz_high_swept = False
            self._kz_low_swept = False
            self._pdh_swept = False
            self._pdl_swept = False
            self._latest_sweep = None

        self._bar_count += 1
        sweep = None

        # For long_only, we only care about low sweeps (bullish reversal)
        # Low sweep of KZ low
        if not self._kz_low_swept and not math.isnan(levels.kz_low) and bar.low < levels.kz_low:
            self._kz_low_swept = True
            sweep = SweepEvent(source="kz_low", level=levels.kz_low, direction=1, bar_index=self._bar_count)

        # Low sweep of PDL
        if not self._pdl_swept and not math.isnan(levels.pdl) and bar.low < levels.pdl:
            self._pdl_swept = True
            # Prefer KZ sweep if both happened on same bar
            if sweep is None:
                sweep = SweepEvent(source="pdl", level=levels.pdl, direction=1, bar_index=self._bar_count)

        if not self._long_only:
            # High sweep of KZ high (bearish)
            if not self._kz_high_swept and not math.isnan(levels.kz_high) and bar.high > levels.kz_high:
                self._kz_high_swept = True
                if sweep is None:
                    sweep = SweepEvent(source="kz_high", level=levels.kz_high, direction=-1, bar_index=self._bar_count)

            # High sweep of PDH (bearish)
            if not self._pdh_swept and not math.isnan(levels.pdh) and bar.high > levels.pdh:
                self._pdh_swept = True
                if sweep is None:
                    sweep = SweepEvent(source="pdh", level=levels.pdh, direction=-1, bar_index=self._bar_count)

        if sweep is not None:
            self._latest_sweep = sweep

        return sweep

    def reset(self) -> None:
        """Full reset."""
        self._bar_count = 0
        self._current_date = ""
        self._kz_high_swept = False
        self._kz_low_swept = False
        self._pdh_swept = False
        self._pdl_swept = False
        self._latest_sweep = None
