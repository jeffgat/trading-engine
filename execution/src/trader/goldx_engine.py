"""Gold-X ORB execution engine.

This is a causal live-execution translation of the reverse-engineered
TradingView Gold-X v14.4 model. It intentionally sits beside the generic
ORB/FVG engine because Gold-X combines two different entry families:

- Classic ORB: breakout-close entry, SD target, hard stop plus Q1/Q4 close stop.
- Revised FVG: breakout-adjacent FVG selection, limit retest entry, full 2R exit.

The private TradingView script still has hidden marker/filter state, so these
legs are dry-run research legs until exact replay proves them live-native.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

import numpy as np

from .engine import Bar, ORBEngine, State
from .sizing import TradeLevels

logger = logging.getLogger(__name__)


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def _time_lte(left: time, right: time) -> bool:
    return (left.hour, left.minute, left.second) <= (right.hour, right.minute, right.second)


@dataclass(frozen=True)
class _GoldXBreakout:
    timestamp: datetime
    bar_index: int
    direction: int


@dataclass
class GoldXEngine(ORBEngine):
    """Reverse-engineered Gold-X Classic + Revised/FVG engine."""

    engine_type: str = "gold_x"

    # Variant selection.
    goldx_mode: str = "both"  # both, classic_only, fvg_only

    # Time and weekday routing.
    goldx_classic_signal_end: str = "10:45"
    goldx_fvg_signal_end: str = "13:00"
    goldx_classic_weekdays: tuple[int, ...] | list[int] = (0, 3, 4)
    goldx_fvg_weekdays: tuple[int, ...] | list[int] = (0, 1, 3)

    # Classic ORB settings.
    goldx_classic_risk_usd: float = 400.0
    goldx_classic_max_contracts: float = 20.0
    goldx_classic_target_sd: float = 1.0
    goldx_classic_hard_stop_buffer_points: float = 7.0
    goldx_classic_overextension_max_pct: float = 60.0
    goldx_enable_classic_overextension_filter: bool = True
    goldx_enable_classic_proxy_filters: bool = True
    goldx_classic_cooldown_minutes: float = 50.0
    goldx_classic_max_hold_minutes: int = 180

    # Revised/FVG settings.
    goldx_fvg_risk_usd: float = 300.0
    goldx_fvg_max_contracts: float = 30.0
    goldx_fvg_min_size_points: float = 9.0
    goldx_fvg_max_size_points: float = 60.0
    goldx_fvg_max_orb_distance_points: float = 30.0
    goldx_fvg_target_rr: float = 2.0
    goldx_fvg_min_stop_points: float = 10.0
    goldx_fvg_bars_before_breakout: int = 2
    goldx_fvg_bars_after_breakout: int = 2
    goldx_fvg_max_wait_bars: int = 30
    goldx_fvg_max_wait_minutes: int = 200
    goldx_fvg_selection_cooldown_minutes: float = 5.0
    goldx_fvg_after_classic_entry_cooldown_minutes: float = 10.0
    goldx_fvg_after_classic_exit_cooldown_minutes: float = 0.0
    goldx_fvg_max_hold_minutes: int = 270
    goldx_enable_fvg_ut_filter: bool = True

    # UT Bot proxy settings from the Gold-X guide.
    goldx_ut_key_value: float = 2.0
    goldx_ut_atr_period: int = 40

    _goldx_classic_signal_end_t: time | None = field(default=None, init=False, repr=False)
    _goldx_fvg_signal_end_t: time | None = field(default=None, init=False, repr=False)
    _goldx_active_family: str | None = field(default=None, init=False)
    _goldx_max_hold_at: datetime | None = field(default=None, init=False)
    _goldx_quartile_stop: float | None = field(default=None, init=False)
    _goldx_fvg_expiry_at: datetime | None = field(default=None, init=False)
    _goldx_pending_breakouts: list[_GoldXBreakout] = field(default_factory=list, init=False)
    _goldx_seen_fvg_keys: set[tuple[int, int, int]] = field(default_factory=set, init=False)
    _goldx_last_classic_entry: datetime | None = field(default=None, init=False)
    _goldx_last_classic_exit: datetime | None = field(default=None, init=False)
    _goldx_last_fvg_selection: datetime | None = field(default=None, init=False)

    # Continuous indicator proxy state used by Classic and FVG filters.
    _indicator_count: int = field(default=0, init=False)
    _prev_close: float | None = field(default=None, init=False)
    _highs: list[float] = field(default_factory=list, init=False)
    _lows: list[float] = field(default_factory=list, init=False)
    _closes: list[float] = field(default_factory=list, init=False)
    _ema9_high: float | None = field(default=None, init=False)
    _ema9_close: float | None = field(default=None, init=False)
    _ema8_close: float | None = field(default=None, init=False)
    _ema100_close: float | None = field(default=None, init=False)
    _prev_wae_spread: float | None = field(default=None, init=False)
    _wae_momentum: float | None = field(default=None, init=False)
    _squeeze_sources: list[float] = field(default_factory=list, init=False)
    _squeeze_momentum_values: list[float] = field(default_factory=list, init=False)
    _squeeze_momentum: float | None = field(default=None, init=False)
    _bearish_divergence: bool = field(default=False, init=False)
    _bullish_divergence: bool = field(default=False, init=False)
    _rg_avg_range: float | None = field(default=None, init=False)
    _rg_smooth_range: float | None = field(default=None, init=False)
    _rg_filter: float | None = field(default=None, init=False)
    _rg_direction: int = field(default=0, init=False)
    _ut_atr: float | None = field(default=None, init=False)
    _ut_stop: float | None = field(default=None, init=False)
    _ut_direction: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.goldx_mode not in {"both", "classic_only", "fvg_only"}:
            raise ValueError("goldx_mode must be one of both, classic_only, fvg_only")
        self.goldx_classic_weekdays = tuple(self.goldx_classic_weekdays)
        self.goldx_fvg_weekdays = tuple(self.goldx_fvg_weekdays)
        self._goldx_classic_signal_end_t = _parse_hhmm(self.goldx_classic_signal_end)
        self._goldx_fvg_signal_end_t = _parse_hhmm(self.goldx_fvg_signal_end)

    async def on_bar(self, bar: Bar, daily_atr: float) -> None:
        self._update_goldx_indicators(bar)
        await super().on_bar(bar, daily_atr)

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        self._daily_atr = daily_atr
        if self._state == State.ARMED_LIMIT:
            await self._handle_goldx_armed_fill(tick, resolution="1s")
        elif self._state in (State.FILLED, State.MANAGING):
            await self._handle_goldx_exit(tick, resolution="1s", allow_quartile_close=False)

    def _reset_day(self, date_str: str, notify: bool = True) -> None:
        super()._reset_day(date_str, notify=notify)
        self._goldx_active_family = None
        self._goldx_max_hold_at = None
        self._goldx_quartile_stop = None
        self._goldx_fvg_expiry_at = None
        self._goldx_pending_breakouts.clear()
        self._goldx_seen_fvg_keys.clear()
        self._goldx_last_classic_entry = None
        self._goldx_last_classic_exit = None
        self._goldx_last_fvg_selection = None

    async def _handle_scanning(self, bar: Bar, bar_time: time) -> None:
        self._expire_fvg_breakouts()
        if not self._goldx_any_window_open(bar):
            self._log_trade("NO_SETUP", "Gold-X windows closed")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        if len(self._session_bars) < 2 or self._orb_range <= 0:
            return

        if self._classic_enabled() and self._classic_window_open(bar):
            classic_levels = self._build_classic_levels(bar)
            if classic_levels is not None:
                await self._enter_goldx_market_style(
                    bar,
                    classic_levels,
                    family="classic",
                    event="GOLDX_CLASSIC_SETUP",
                )
                return

        if self._fvg_enabled():
            if self._fvg_window_open(bar):
                self._register_fvg_breakouts(bar)
            if not self._in_entry(bar.timestamp.time()):
                return
            levels = self._select_fvg_levels(bar)
            if levels is not None:
                if not self._contract_ready_for_entry(bar.timestamp):
                    return
                self._levels = levels
                self._lock_trade_contract()
                self._goldx_active_family = "fvg"
                self._tp1_hit = False
                self._fill_bar_idx = -1
                self._fill_timestamp = None
                self._fill_via_tick = False
                self._armed_at = bar.timestamp + timedelta(minutes=5)
                self._state = State.ARMED_LIMIT
                self._request_checkpoint()
                self._log_trade(
                    "GOLDX_FVG_ARMED",
                    "dir=%s entry=%.2f stop=%.2f target=%.2f qty=%.1f expiry=%s"
                    % (
                        "long" if levels.direction == 1 else "short",
                        levels.entry,
                        levels.stop,
                        levels.tp2,
                        levels.qty,
                        self._goldx_fvg_expiry_at,
                    ),
                )
                self._notify_state_change()
                if self._should_send:
                    await self.broker.send_entry(
                        action="buy" if levels.direction == 1 else "sell",
                        qty=levels.qty,
                        price=levels.entry,
                        tp2=levels.tp2,
                        stop=levels.stop,
                        ticker=self.broker_ticker,
                    )

    async def _handle_armed(self, bar: Bar, bar_time: time) -> None:
        await self._handle_goldx_armed_fill(bar, resolution="5m")

    async def _handle_managing(self, bar: Bar, bar_time: time) -> None:
        await self._handle_goldx_exit(bar, resolution="5m", allow_quartile_close=True)

    async def _flatten_position(self, bar: Bar, *, resolution: str, reason: str) -> None:
        exit_price = float(bar.close)
        self._log_trade(
            "GOLDX_FLAT",
            "family=%s reason=%s exit=%.2f time=%s resolution=%s"
            % (self._goldx_active_family or "-", reason, exit_price, bar.timestamp, resolution),
        )
        self._release_position_cap()
        if self._should_send:
            await self.broker.send_flatten(ticker=self.broker_ticker)
        self._emit_trade_record("eod", exit_price=exit_price, exit_timestamp=bar.timestamp)
        self._remember_goldx_exit(bar.timestamp)
        self._clear_trade_contract()
        self._state = State.WAITING_FOR_GAP if self._goldx_can_continue(bar.timestamp) else State.FLAT
        self._request_checkpoint()
        self._notify_state_change()

    def _classic_enabled(self) -> bool:
        return self.goldx_mode in {"both", "classic_only"}

    def _fvg_enabled(self) -> bool:
        return self.goldx_mode in {"both", "fvg_only"}

    def _classic_window_open(self, bar: Bar) -> bool:
        return (
            bar.timestamp.weekday() in self.goldx_classic_weekdays
            and self._in_entry(bar.timestamp.time())
            and _time_lte(bar.timestamp.time(), self._goldx_classic_signal_end_t)
        )

    def _fvg_window_open(self, bar: Bar) -> bool:
        return (
            bar.timestamp.weekday() in self.goldx_fvg_weekdays
            and self._in_entry(bar.timestamp.time())
            and _time_lte(bar.timestamp.time(), self._goldx_fvg_signal_end_t)
        )

    def _goldx_any_window_open(self, bar: Bar) -> bool:
        return (
            (self._classic_enabled() and self._classic_window_open(bar))
            or (self._fvg_enabled() and self._fvg_window_open(bar))
            or bool(self._goldx_pending_breakouts)
        )

    def _build_classic_levels(self, bar: Bar) -> TradeLevels | None:
        previous_close = float(self._session_bars[-2].close)
        sides: list[int] = []
        if previous_close <= self._orb_high and float(bar.close) > self._orb_high:
            sides.append(1)
        if previous_close >= self._orb_low and float(bar.close) < self._orb_low:
            sides.append(-1)
        if not sides:
            return None

        for direction in sides:
            if self._goldx_last_classic_entry is not None:
                minutes = (bar.timestamp + timedelta(minutes=5) - self._goldx_last_classic_entry).total_seconds() / 60.0
                if minutes < self.goldx_classic_cooldown_minutes:
                    self._log_trade("GOLDX_CLASSIC_COOLDOWN", "minutes=%.1f" % minutes)
                    continue
            extension = (
                (float(bar.close) - self._orb_high) / self._orb_range * 100.0
                if direction == 1
                else (self._orb_low - float(bar.close)) / self._orb_range * 100.0
            )
            if (
                self.goldx_enable_classic_overextension_filter
                and extension > self.goldx_classic_overextension_max_pct
            ):
                self._log_trade("GOLDX_CLASSIC_OVEREXT", "extension=%.2f" % extension)
                continue
            if not self._classic_proxy_filters_pass(bar, direction):
                continue

            entry = float(bar.close)
            target = (
                self._orb_high + self._orb_range * self.goldx_classic_target_sd
                if direction == 1
                else self._orb_low - self._orb_range * self.goldx_classic_target_sd
            )
            orb_mid = (self._orb_high + self._orb_low) / 2.0
            stop = (
                orb_mid - self.goldx_classic_hard_stop_buffer_points
                if direction == 1
                else orb_mid + self.goldx_classic_hard_stop_buffer_points
            )
            risk_pts = abs(entry - stop)
            target_pts = abs(target - entry)
            if risk_pts <= 0 or target_pts <= 0:
                self._log_trade("GOLDX_CLASSIC_BAD_GEOMETRY", "risk=%.2f target_pts=%.2f" % (risk_pts, target_pts))
                continue
            qty = self._goldx_qty_for_risk(risk_pts, family="classic")
            if qty <= 0:
                self._log_trade("GOLDX_CLASSIC_QTY", "risk_pts=%.2f" % risk_pts)
                continue
            quartile = (
                self._orb_high - self._orb_range * 0.25
                if direction == 1
                else self._orb_low + self._orb_range * 0.25
            )
            self._goldx_quartile_stop = quartile
            return TradeLevels(
                entry=entry,
                stop=stop,
                tp1=target,
                tp2=target,
                be=entry,
                qty=qty,
                half_qty=qty,
                is_single_contract=True,
                risk_pts=risk_pts,
                direction=direction,
                gap_size=extension,
            )
        return None

    async def _enter_goldx_market_style(self, bar: Bar, levels: TradeLevels, *, family: str, event: str) -> None:
        if not self._contract_ready_for_entry(bar.timestamp):
            return
        capped = self._apply_position_cap(levels)
        if capped is None:
            return
        self._levels = capped
        self._lock_trade_contract()
        self._goldx_active_family = family
        self._tp1_hit = False
        self._fill_bar_idx = self._bar_count
        self._fill_timestamp = bar.timestamp + timedelta(minutes=5)
        self._fill_via_tick = True
        self._session_filled_trades += 1
        self._goldx_max_hold_at = self._fill_timestamp + timedelta(minutes=self.goldx_classic_max_hold_minutes)
        self._goldx_last_classic_entry = self._fill_timestamp
        self._state = State.MANAGING
        self._request_checkpoint()
        self._log_trade(
            event,
            "dir=%s entry=%.2f stop=%.2f target=%.2f qty=%.1f qstop=%s"
            % (
                "long" if capped.direction == 1 else "short",
                capped.entry,
                capped.stop,
                capped.tp2,
                capped.qty,
                "%.2f" % self._goldx_quartile_stop if self._goldx_quartile_stop is not None else "na",
            ),
        )
        self._notify_state_change()
        if self._should_send:
            await self.broker.send_entry(
                action="buy" if capped.direction == 1 else "sell",
                qty=capped.qty,
                price=capped.entry,
                tp2=capped.tp2,
                stop=capped.stop,
                ticker=self.broker_ticker,
            )

    def _register_fvg_breakouts(self, bar: Bar) -> None:
        previous_close = float(self._session_bars[-2].close)
        current_index = self._bar_count - 1
        if previous_close <= self._orb_high and float(bar.close) > self._orb_high:
            self._goldx_pending_breakouts.append(_GoldXBreakout(bar.timestamp, current_index, 1))
        if previous_close >= self._orb_low and float(bar.close) < self._orb_low:
            self._goldx_pending_breakouts.append(_GoldXBreakout(bar.timestamp, current_index, -1))
        self._expire_fvg_breakouts()

    def _expire_fvg_breakouts(self) -> None:
        self._goldx_pending_breakouts = [
            item for item in self._goldx_pending_breakouts
            if (self._bar_count - 1) <= item.bar_index + self.goldx_fvg_bars_after_breakout
        ]

    def _select_fvg_levels(self, bar: Bar) -> TradeLevels | None:
        if self._goldx_last_classic_entry is not None and self.goldx_fvg_after_classic_entry_cooldown_minutes > 0:
            minutes = (bar.timestamp - self._goldx_last_classic_entry).total_seconds() / 60.0
            if 0 <= minutes < self.goldx_fvg_after_classic_entry_cooldown_minutes:
                return None
        if self._goldx_last_classic_exit is not None and self.goldx_fvg_after_classic_exit_cooldown_minutes > 0:
            minutes = (bar.timestamp - self._goldx_last_classic_exit).total_seconds() / 60.0
            if 0 <= minutes < self.goldx_fvg_after_classic_exit_cooldown_minutes:
                return None
        if self._goldx_last_fvg_selection is not None:
            minutes = (bar.timestamp - self._goldx_last_fvg_selection).total_seconds() / 60.0
            if minutes < self.goldx_fvg_selection_cooldown_minutes:
                return None

        current_index = self._bar_count - 1
        for breakout in list(self._goldx_pending_breakouts):
            start = max(2, breakout.bar_index - self.goldx_fvg_bars_before_breakout)
            end = min(current_index, breakout.bar_index + self.goldx_fvg_bars_after_breakout)
            for fvg_index in range(start, end + 1):
                key = (breakout.direction, breakout.bar_index, fvg_index)
                if key in self._goldx_seen_fvg_keys:
                    continue
                self._goldx_seen_fvg_keys.add(key)
                levels = self._build_fvg_levels(breakout, fvg_index)
                if levels is None:
                    continue
                if self.goldx_enable_fvg_ut_filter and self._ut_direction != breakout.direction:
                    self._log_trade(
                        "GOLDX_FVG_UT_BLOCKED",
                        "dir=%s ut_direction=%d" % (
                            "long" if breakout.direction == 1 else "short",
                            self._ut_direction,
                        ),
                    )
                    continue
                capped = self._apply_position_cap(levels)
                if capped is None:
                    return None
                self._goldx_last_fvg_selection = max(
                    breakout.timestamp,
                    self._session_bars[fvg_index].timestamp,
                )
                entry_earliest = self._goldx_last_fvg_selection + timedelta(minutes=5)
                self._goldx_fvg_expiry_at = min(
                    entry_earliest + timedelta(minutes=self.goldx_fvg_max_wait_bars * 5),
                    self._goldx_last_fvg_selection + timedelta(minutes=self.goldx_fvg_max_wait_minutes),
                )
                return capped
        return None

    def _build_fvg_levels(self, breakout: _GoldXBreakout, fvg_index: int) -> TradeLevels | None:
        if fvg_index < 2 or fvg_index >= len(self._session_bars):
            return None
        before = self._session_bars[fvg_index - 2]
        impulse = self._session_bars[fvg_index - 1]
        after = self._session_bars[fvg_index]
        direction = breakout.direction

        if direction == 1:
            if not (float(before.high) < float(after.low)):
                return None
            bottom = float(before.high)
            top = float(after.low)
            entry = top
            natural_stop = float(impulse.low)
            distance = min(abs(bottom - self._orb_high), abs(top - self._orb_high))
            risk = entry - natural_stop
            stop = natural_stop if risk >= self.goldx_fvg_min_stop_points else entry - self.goldx_fvg_min_stop_points
            risk = entry - stop
            target = entry + risk * self.goldx_fvg_target_rr
        else:
            if not (float(before.low) > float(after.high)):
                return None
            top = float(before.low)
            bottom = float(after.high)
            entry = bottom
            natural_stop = float(impulse.high)
            distance = min(abs(bottom - self._orb_low), abs(top - self._orb_low))
            risk = natural_stop - entry
            stop = natural_stop if risk >= self.goldx_fvg_min_stop_points else entry + self.goldx_fvg_min_stop_points
            risk = stop - entry
            target = entry - risk * self.goldx_fvg_target_rr

        size = top - bottom
        if size < self.goldx_fvg_min_size_points or size > self.goldx_fvg_max_size_points:
            return None
        if distance > self.goldx_fvg_max_orb_distance_points or risk <= 0:
            return None
        qty = self._goldx_qty_for_risk(risk, family="fvg")
        if qty <= 0:
            return None
        return TradeLevels(
            entry=entry,
            stop=stop,
            tp1=target,
            tp2=target,
            be=entry,
            qty=qty,
            half_qty=qty,
            is_single_contract=True,
            risk_pts=risk,
            direction=direction,
            gap_size=size,
        )

    async def _handle_goldx_armed_fill(self, bar: Bar, *, resolution: str) -> None:
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        if self._in_flat(bar):
            await self._cancel_armed_limit("Gold-X flat window reached entry=%.2f" % levels.entry)
            return
        if self._goldx_fvg_expiry_at is not None and bar.timestamp > self._goldx_fvg_expiry_at:
            await self._cancel_armed_limit("Gold-X FVG expired entry=%.2f" % levels.entry)
            return
        if self._armed_at is not None and bar.timestamp < self._armed_at:
            return

        filled = (
            float(bar.low) <= levels.entry
            if levels.direction == 1
            else float(bar.high) >= levels.entry
        )
        if not filled:
            return

        self._fill_timestamp = bar.timestamp
        self._fill_bar_idx = self._bar_count
        self._fill_via_tick = resolution == "1s"
        self._armed_at = None
        self._session_filled_trades += 1
        self._goldx_max_hold_at = bar.timestamp + timedelta(minutes=self.goldx_fvg_max_hold_minutes)
        self._state = State.MANAGING
        self._request_checkpoint()
        self._log_trade(
            "GOLDX_FVG_FILLED",
            "dir=%s entry=%.2f stop=%.2f target=%.2f qty=%.1f time=%s resolution=%s"
            % (
                "long" if levels.direction == 1 else "short",
                levels.entry,
                levels.stop,
                levels.tp2,
                levels.qty,
                bar.timestamp,
                resolution,
            ),
        )
        self._notify_state_change()

    async def _handle_goldx_exit(self, bar: Bar, *, resolution: str, allow_quartile_close: bool) -> None:
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return
        if self._in_flat(bar):
            await self._flatten_position(bar, resolution=resolution, reason="bar_time")
            return
        if self._fill_timestamp is not None and bar.timestamp <= self._fill_timestamp:
            return

        is_long = levels.direction == 1
        stop_hit = float(bar.low) <= levels.stop if is_long else float(bar.high) >= levels.stop
        target_hit = float(bar.high) >= levels.tp2 if is_long else float(bar.low) <= levels.tp2
        if stop_hit or target_hit:
            if stop_hit:
                await self._finish_goldx_trade("sl", levels.stop, bar.timestamp, "GOLDX_SL", resolution)
            else:
                await self._finish_goldx_trade("tp2_direct", levels.tp2, bar.timestamp, "GOLDX_TARGET", resolution)
            return

        if allow_quartile_close and self._goldx_active_family == "classic" and self._goldx_quartile_stop is not None:
            close_stop = (
                float(bar.close) <= self._goldx_quartile_stop
                if is_long
                else float(bar.close) >= self._goldx_quartile_stop
            )
            if close_stop:
                await self._finish_goldx_trade(
                    "sl",
                    float(bar.close),
                    bar.timestamp + timedelta(minutes=5),
                    "GOLDX_Q_STOP",
                    resolution,
                )
                return

        if self._goldx_max_hold_at is not None and bar.timestamp >= self._goldx_max_hold_at:
            await self._flatten_position(bar, resolution=resolution, reason="max_hold")

    async def _finish_goldx_trade(
        self,
        exit_type: str,
        exit_price: float,
        exit_timestamp: datetime,
        event: str,
        resolution: str,
    ) -> None:
        self._log_trade(
            event,
            "family=%s exit=%.2f time=%s resolution=%s"
            % (self._goldx_active_family or "-", exit_price, exit_timestamp, resolution),
        )
        self._release_position_cap()
        if self._should_send:
            self._schedule_post_exit_cleanup(reason=f"{event.lower()}_{resolution}")
        self._emit_trade_record(exit_type, exit_price=exit_price, exit_timestamp=exit_timestamp)
        self._remember_goldx_exit(exit_timestamp)
        self._clear_trade_contract()
        self._state = State.WAITING_FOR_GAP if self._goldx_can_continue(exit_timestamp) else State.FLAT
        self._request_checkpoint()
        self._notify_state_change()

    def _remember_goldx_exit(self, exit_timestamp: datetime) -> None:
        if self._goldx_active_family == "classic":
            self._goldx_last_classic_exit = exit_timestamp
        self._goldx_active_family = None
        self._goldx_max_hold_at = None
        self._goldx_quartile_stop = None
        self._goldx_fvg_expiry_at = None

    def _goldx_can_continue(self, ts: datetime) -> bool:
        return self._goldx_any_window_open(Bar(ts, 0.0, 0.0, 0.0, 0.0, 0))

    def _goldx_qty_for_risk(self, risk_pts: float, *, family: str) -> float:
        if risk_pts <= 0:
            return 0.0
        risk_usd = self.goldx_fvg_risk_usd if family == "fvg" else self.goldx_classic_risk_usd
        cap = self.goldx_fvg_max_contracts if family == "fvg" else self.goldx_classic_max_contracts
        raw_qty = math.floor(risk_usd / (risk_pts * self.point_value))
        qty = max(self.min_qty, float(raw_qty))
        if self.qty_step > 0:
            qty = math.floor(qty / self.qty_step) * self.qty_step
        return min(cap, qty)

    def _classic_proxy_filters_pass(self, bar: Bar, direction: int) -> bool:
        if not self.goldx_enable_classic_proxy_filters:
            return True

        close = float(bar.close)
        if self._rg_filter is None or self._rg_direction == 0:
            return False
        if direction == 1 and not (self._rg_direction > 0 and close >= self._rg_filter):
            return False
        if direction == -1 and not (self._rg_direction < 0 and close <= self._rg_filter):
            return False

        if self._ema9_high is None or self._ema9_close is None:
            return False
        if direction == 1 and close <= self._ema9_high:
            return False
        if direction == -1 and close >= self._ema9_close:
            return False

        if self._squeeze_momentum is None or self._wae_momentum is None:
            return False
        if direction == 1 and (self._squeeze_momentum <= 0.0 or self._wae_momentum <= 0.0):
            return False
        if direction == -1 and (self._squeeze_momentum >= 0.0 or self._wae_momentum >= 0.0):
            return False

        if direction == 1 and self._bearish_divergence:
            return False
        if direction == -1 and self._bullish_divergence:
            return False
        return True

    def _update_goldx_indicators(self, bar: Bar) -> None:
        high = float(bar.high)
        low = float(bar.low)
        close = float(bar.close)
        self._indicator_count += 1
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)
        if len(self._highs) > 260:
            self._highs.pop(0)
            self._lows.pop(0)
            self._closes.pop(0)

        self._ema9_high = self._ema(self._ema9_high, high, 9)
        self._ema9_close = self._ema(self._ema9_close, close, 9)
        self._ema8_close = self._ema(self._ema8_close, close, 8)
        self._ema100_close = self._ema(self._ema100_close, close, 100)
        if self._ema8_close is not None and self._ema100_close is not None:
            spread = self._ema8_close - self._ema100_close
            if self._prev_wae_spread is not None:
                self._wae_momentum = (spread - self._prev_wae_spread) * 250.0
            self._prev_wae_spread = spread

        self._update_rg(close)
        self._update_ut(high, low, close)
        self._update_squeeze_and_divergence(high, low)
        self._prev_close = close

    @staticmethod
    def _ema(previous: float | None, value: float, length: int) -> float:
        if previous is None:
            return value
        alpha = 2.0 / (length + 1.0)
        return value * alpha + previous * (1.0 - alpha)

    def _update_rg(self, close: float) -> None:
        if self._prev_close is None:
            return
        abs_change = abs(close - self._prev_close)
        self._rg_avg_range = self._ema(self._rg_avg_range, abs_change, 30)
        if self._rg_avg_range is None:
            return
        self._rg_smooth_range = self._ema(self._rg_smooth_range, self._rg_avg_range, 59)
        if self._rg_smooth_range is None:
            return
        smooth = self._rg_smooth_range * 5.0
        previous_filter = self._rg_filter
        if previous_filter is None:
            current_filter = close
        elif close > previous_filter:
            current_filter = max(previous_filter, close - smooth)
        else:
            current_filter = min(previous_filter, close + smooth)
        if previous_filter is not None:
            if current_filter > previous_filter:
                self._rg_direction = 1
            elif current_filter < previous_filter:
                self._rg_direction = -1
        if self._rg_direction == 0:
            self._rg_direction = 1 if close >= current_filter else -1
        self._rg_filter = current_filter

    def _update_ut(self, high: float, low: float, close: float) -> None:
        if self._prev_close is None:
            return
        true_range = max(high - low, abs(high - self._prev_close), abs(low - self._prev_close))
        self._ut_atr = self._rma(self._ut_atr, true_range, self.goldx_ut_atr_period)
        if self._ut_atr is None:
            return
        loss = self.goldx_ut_key_value * self._ut_atr
        previous_stop = self._ut_stop
        previous_src = self._prev_close
        if previous_stop is None:
            stop = close - loss
        elif close > previous_stop and previous_src > previous_stop:
            stop = max(previous_stop, close - loss)
        elif close < previous_stop and previous_src < previous_stop:
            stop = min(previous_stop, close + loss)
        elif close > previous_stop:
            stop = close - loss
        else:
            stop = close + loss

        direction = self._ut_direction
        if previous_stop is not None:
            if previous_src < previous_stop and close > previous_stop:
                direction = 1
            elif previous_src > previous_stop and close < previous_stop:
                direction = -1
        if direction == 0:
            direction = 1 if close > stop else -1
        self._ut_stop = stop
        self._ut_direction = direction

    @staticmethod
    def _rma(previous: float | None, value: float, length: int) -> float:
        if previous is None:
            return value
        alpha = 1.0 / float(length)
        return value * alpha + previous * (1.0 - alpha)

    def _update_squeeze_and_divergence(self, high: float, low: float) -> None:
        if len(self._closes) >= 100:
            recent_highs = self._highs[-100:]
            recent_lows = self._lows[-100:]
            recent_closes = self._closes[-100:]
            source = self._closes[-1] - (
                ((max(recent_highs) + min(recent_lows)) / 2.0 + sum(recent_closes) / 100.0)
                / 2.0
            )
            self._squeeze_sources.append(source)
            if len(self._squeeze_sources) > 140:
                self._squeeze_sources.pop(0)
            if len(self._squeeze_sources) >= 100:
                self._squeeze_momentum = self._linreg_last(self._squeeze_sources[-100:])
                prior_momentum = self._squeeze_momentum_values[-15:]
                prior_highs = self._highs[-16:-1]
                prior_lows = self._lows[-16:-1]
                self._bearish_divergence = (
                    len(prior_momentum) >= 15
                    and len(prior_highs) >= 15
                    and high >= max(prior_highs)
                    and self._squeeze_momentum < max(prior_momentum)
                )
                self._bullish_divergence = (
                    len(prior_momentum) >= 15
                    and len(prior_lows) >= 15
                    and low <= min(prior_lows)
                    and self._squeeze_momentum > min(prior_momentum)
                )
                self._squeeze_momentum_values.append(self._squeeze_momentum)
                if len(self._squeeze_momentum_values) > 60:
                    self._squeeze_momentum_values.pop(0)

    @staticmethod
    def _linreg_last(values: list[float]) -> float:
        length = len(values)
        x = np.arange(length, dtype=float)
        y = np.asarray(values, dtype=float)
        sum_x = float(x.sum())
        sum_y = float(y.sum())
        sum_x2 = float((x * x).sum())
        sum_xy = float((x * y).sum())
        denominator = length * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return float(y[-1])
        slope = (length * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / length
        return intercept + slope * (length - 1)
