"""Incremental internal CISD detection for live LSI execution.

This is a causal, bar-by-bar port of
``backtesting/src/orb_backtest/signals/cisd.py``. A bar can only trigger a
CISD level that was armed by prior bars; the current bar is processed for new
leg state only after trigger checks complete.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class CisdEvent:
    """A close through a previously armed internal body level."""

    direction: int  # +1 bullish CISD, -1 bearish CISD
    level: float
    level_bar_index: int
    leg_bars: int
    leg_move: float


class InternalCisdTracker:
    """Body-based internal CISD tracker.

    A bullish CISD is armed by a consecutive lower-body leg and triggers when a
    later close breaks above the body high of the first leg candle. Bearish is
    the mirrored higher-body version.
    """

    def __init__(
        self,
        *,
        min_leg_bars: int = 2,
        min_leg_atr_pct: float = 0.0,
        max_leg_bars: int = 60,
    ) -> None:
        if min_leg_bars < 1:
            raise ValueError("min_leg_bars must be >= 1")
        if min_leg_atr_pct < 0:
            raise ValueError("min_leg_atr_pct must be >= 0")
        if max_leg_bars < 0:
            raise ValueError("max_leg_bars must be >= 0")

        self.min_leg_bars = int(min_leg_bars)
        self.min_leg_atr_pct = float(min_leg_atr_pct)
        self.max_leg_bars = int(max_leg_bars)
        self.reset()

    def reset(self) -> None:
        self._prev_body_high: float | None = None
        self._prev_body_low: float | None = None

        self._down_level = math.nan
        self._down_level_bar = -1
        self._down_leg_bars = 0
        self._down_leg_low = math.nan
        self._down_leg_move = 0.0
        self._in_down_leg = False

        self._up_level = math.nan
        self._up_level_bar = -1
        self._up_leg_bars = 0
        self._up_leg_high = math.nan
        self._up_leg_move = 0.0
        self._in_up_leg = False

    def on_bar(self, bar, *, daily_atr: float, bar_index: int) -> list[CisdEvent]:
        body_high = float(max(bar.open, bar.close))
        body_low = float(min(bar.open, bar.close))
        events: list[CisdEvent] = []

        if self._prev_body_high is None or self._prev_body_low is None:
            self._prev_body_high = body_high
            self._prev_body_low = body_low
            return events

        bullish = self._try_trigger_down_leg(
            close=float(bar.close),
            daily_atr=float(daily_atr),
            bar_index=bar_index,
        )
        if bullish is not None:
            events.append(bullish)

        bearish = self._try_trigger_up_leg(
            close=float(bar.close),
            daily_atr=float(daily_atr),
            bar_index=bar_index,
        )
        if bearish is not None:
            events.append(bearish)

        lower_body = body_high < self._prev_body_high and body_low < self._prev_body_low
        higher_body = body_high > self._prev_body_high and body_low > self._prev_body_low

        if lower_body:
            if not self._in_down_leg:
                self._down_level = body_high
                self._down_level_bar = bar_index
                self._down_leg_bars = 1
                self._down_leg_low = body_low
            else:
                self._down_leg_bars += 1
                self._down_leg_low = min(float(self._down_leg_low), body_low)
            self._down_leg_move = max(0.0, float(self._down_level) - float(self._down_leg_low))
            self._in_down_leg = True
            self._in_up_leg = False
        elif higher_body:
            if not self._in_up_leg:
                self._up_level = body_low
                self._up_level_bar = bar_index
                self._up_leg_bars = 1
                self._up_leg_high = body_high
            else:
                self._up_leg_bars += 1
                self._up_leg_high = max(float(self._up_leg_high), body_high)
            self._up_leg_move = max(0.0, float(self._up_leg_high) - float(self._up_level))
            self._in_up_leg = True
            self._in_down_leg = False
        else:
            self._in_down_leg = False
            self._in_up_leg = False

        self._prev_body_high = body_high
        self._prev_body_low = body_low
        return events

    def _min_move(self, daily_atr: float) -> float:
        if self.min_leg_atr_pct <= 0:
            return 0.0
        if math.isfinite(daily_atr) and daily_atr > 0:
            return (self.min_leg_atr_pct / 100.0) * daily_atr
        return math.inf

    def _clear_down_leg(self) -> None:
        self._down_level = math.nan
        self._down_level_bar = -1
        self._down_leg_bars = 0
        self._down_leg_low = math.nan
        self._down_leg_move = 0.0
        self._in_down_leg = False

    def _clear_up_leg(self) -> None:
        self._up_level = math.nan
        self._up_level_bar = -1
        self._up_leg_bars = 0
        self._up_leg_high = math.nan
        self._up_leg_move = 0.0
        self._in_up_leg = False

    def _try_trigger_down_leg(
        self,
        *,
        close: float,
        daily_atr: float,
        bar_index: int,
    ) -> CisdEvent | None:
        if math.isnan(self._down_level):
            return None

        expired = self.max_leg_bars > 0 and (bar_index - self._down_level_bar) > self.max_leg_bars
        if expired:
            self._clear_down_leg()
            return None

        if (
            self._down_leg_bars >= self.min_leg_bars
            and self._down_leg_move >= self._min_move(daily_atr)
            and close > self._down_level
        ):
            event = CisdEvent(
                direction=1,
                level=float(self._down_level),
                level_bar_index=int(self._down_level_bar),
                leg_bars=int(self._down_leg_bars),
                leg_move=float(self._down_leg_move),
            )
            self._clear_down_leg()
            return event
        return None

    def _try_trigger_up_leg(
        self,
        *,
        close: float,
        daily_atr: float,
        bar_index: int,
    ) -> CisdEvent | None:
        if math.isnan(self._up_level):
            return None

        expired = self.max_leg_bars > 0 and (bar_index - self._up_level_bar) > self.max_leg_bars
        if expired:
            self._clear_up_leg()
            return None

        if (
            self._up_leg_bars >= self.min_leg_bars
            and self._up_leg_move >= self._min_move(daily_atr)
            and close < self._up_level
        ):
            event = CisdEvent(
                direction=-1,
                level=float(self._up_level),
                level_bar_index=int(self._up_level_bar),
                leg_bars=int(self._up_leg_bars),
                leg_move=float(self._up_leg_move),
            )
            self._clear_up_leg()
            return event
        return None
