"""Hunter/classic ORB execution engine.

This engine is a live-execution translation of the reverse-engineered
TradingView Hunter ORB mode. It intentionally lives beside the existing
ORB/FVG and LSI engines because its entry and exit model is different:
breakout candle close entry, signal-candle structural stop, full target only,
and optional Hunter re-entry rules.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from .engine import Bar, ORBEngine, State
from .sizing import TradeLevels

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _HunterOutcome:
    entry_timestamp: datetime
    exit_timestamp: datetime
    r_result: float
    exit_type: str


@dataclass
class HunterORBEngine(ORBEngine):
    """Classic/Hunter ORB breakout engine.

    The parent ``ORBEngine`` supplies session timing, ORB construction,
    checkpointing, position-cap handling, broker fan-out, and dashboard status.
    This subclass replaces FVG scanning and TP1/BE management with the Hunter
    rules inferred from TradingView exports.
    """

    engine_type: str = "hunter_orb"

    # Breakout-candle filters.
    body_min_pct: float = 55.0
    rejection_wick_max_pct: float = 20.0

    # Hunter stop/target model.
    sl_buffer_points: float = 1.0
    hunter_target_rr: float = 2.0
    large_sl_threshold_points: float = 50.0
    reduced_target_rr: float = 1.0
    max_hold_minutes: int = 270
    max_contracts: float = 20.0

    # 15m EMA bias filter.
    ema15_length: int = 14
    ema15_source: str = "close"
    ema15_tolerance_points: float = 2.0
    ema15_max_distance: float | None = None

    # Re-entry model from the best TradingView parity patch.
    reentry_policy: str = "after_each_loss"
    allow_same_bar_win_reentry: bool = True
    same_bar_win_reentry_max_minutes: float = 5.0
    reentry_max_extension_pct: float | None = 100.0
    enable_fast_reentry_exhaustion_filter: bool = True
    fast_reentry_exhaustion_max_minutes: float = 10.1
    fast_reentry_exhaustion_max_extension_pct: float = 12.0
    fast_reentry_exhaustion_min_ema15_distance: float = 50.0

    _hunter_outcomes: list[_HunterOutcome] = field(default_factory=list, init=False)
    _hunter_max_hold_at: datetime | None = field(default=None, init=False)
    _ema15_bucket_start: datetime | None = field(default=None, init=False)
    _ema15_open: float = field(default=0.0, init=False)
    _ema15_high: float = field(default=float("-inf"), init=False)
    _ema15_low: float = field(default=float("inf"), init=False)
    _ema15_close: float = field(default=0.0, init=False)
    _ema15_last_completed: float | None = field(default=None, init=False)

    async def on_bar(self, bar: Bar, daily_atr: float) -> None:
        """Update the continuous 15m EMA, then run the Hunter state machine."""
        self._update_ema15(bar)
        await super().on_bar(bar, daily_atr)

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        """Use 1s bars for bracket exit and max-hold detection."""
        self._daily_atr = daily_atr
        if self._state in (State.FILLED, State.MANAGING):
            await self._handle_hunter_exit(tick, resolution="1s")

    def recover_opening_range(self, bars: list[Bar], now: datetime) -> bool:
        """Seed the 15m EMA from preloaded intraday bars before recovery."""
        self._reset_ema15()
        for bar in sorted(bars, key=lambda item: item.timestamp):
            if bar.timestamp < now:
                self._update_ema15(bar)
        return super().recover_opening_range(bars, now)

    def _reset_day(self, date_str: str, notify: bool = True) -> None:
        super()._reset_day(date_str, notify=notify)
        self._hunter_outcomes.clear()
        self._hunter_max_hold_at = None

    async def _handle_scanning(self, bar: Bar, bar_time: time) -> None:
        """Scan confirmed 5m bars for Hunter breakout entries."""
        if not self._in_entry(bar_time):
            self._log_trade("NO_SETUP", "entry window closed")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        if len(self._session_bars) < 2 or self._orb_range <= 0:
            return

        previous_close = float(self._session_bars[-2].close)
        sides: list[int] = []
        if not self.short_only and float(bar.close) > self._orb_high and previous_close <= self._orb_high:
            sides.append(1)
        if (not self.long_only or self.short_only) and float(bar.close) < self._orb_low and previous_close >= self._orb_low:
            sides.append(-1)

        for direction in sides:
            candidate = self._build_hunter_levels(bar, direction)
            if candidate is None:
                continue
            levels, body_pct, rejection_pct, extension_pct, ema15_distance = candidate
            if not self._can_take_hunter_candidate(bar, extension_pct, ema15_distance):
                self._log_trade(
                    "HUNTER_REENTRY_BLOCKED",
                    "dir=%s extension=%.2f ema15_dist=%s"
                    % (
                        "long" if direction == 1 else "short",
                        extension_pct,
                        "%.2f" % ema15_distance if ema15_distance is not None else "na",
                    ),
                )
                continue

            capped_levels = self._apply_position_cap(levels)
            if capped_levels is None:
                return

            self._levels = capped_levels
            self._tp1_hit = False
            self._fill_bar_idx = self._bar_count
            self._fill_timestamp = bar.timestamp + timedelta(minutes=5)
            self._fill_via_tick = True
            self._hunter_max_hold_at = self._fill_timestamp + timedelta(minutes=self.max_hold_minutes)
            self._state = State.MANAGING
            self._request_checkpoint()
            self._log_trade(
                "HUNTER_SETUP",
                (
                    "dir=%s entry=%.2f stop=%.2f target=%.2f rr=%.2f "
                    "qty=%.1f body=%.2f rejection=%.2f extension=%.2f ema15_dist=%s"
                )
                % (
                    "long" if direction == 1 else "short",
                    capped_levels.entry,
                    capped_levels.stop,
                    capped_levels.tp2,
                    self._hunter_rr_for_risk(capped_levels.risk_pts),
                    capped_levels.qty,
                    body_pct,
                    rejection_pct,
                    extension_pct,
                    "%.2f" % ema15_distance if ema15_distance is not None else "na",
                ),
            )
            self._notify_state_change()
            if self._should_send:
                await self.broker.send_entry(
                    action="buy" if direction == 1 else "sell",
                    qty=capped_levels.qty,
                    price=capped_levels.entry,
                    tp2=capped_levels.tp2,
                    stop=capped_levels.stop,
                    ticker=self.exec_ticker,
                )
            return

    async def _handle_managing(self, bar: Bar, bar_time: time) -> None:
        """5m fallback exit handling if 1s bars are unavailable."""
        if self._in_flat(bar):
            await self._flatten_position(bar, resolution="5m", reason="bar_time")
            return
        if self._bar_count <= self._fill_bar_idx:
            return
        await self._handle_hunter_exit(bar, resolution="5m")

    async def _flatten_position(self, bar: Bar, *, resolution: str, reason: str) -> None:
        exit_price = float(bar.close)
        exit_timestamp = bar.timestamp
        await super()._flatten_position(bar, resolution=resolution, reason=reason)
        self._remember_hunter_outcome(exit_timestamp, self._price_to_r(exit_price), "eod")

    def _build_hunter_levels(
        self,
        bar: Bar,
        direction: int,
    ) -> tuple[TradeLevels, float, float, float, float | None] | None:
        body_pct, rejection_pct = self._body_rejection_pct(bar, direction)
        if body_pct < self.body_min_pct:
            self._log_trade("HUNTER_FILTER_BODY", "body=%.2f min=%.2f" % (body_pct, self.body_min_pct))
            return None
        if rejection_pct > self.rejection_wick_max_pct:
            self._log_trade(
                "HUNTER_FILTER_REJECTION",
                "rejection=%.2f max=%.2f" % (rejection_pct, self.rejection_wick_max_pct),
            )
            return None

        ema15_distance = self._ema15_distance(bar, direction)
        if ema15_distance is None:
            self._log_trade("HUNTER_FILTER_EMA15", "ema not ready")
            return None
        if ema15_distance < -self.ema15_tolerance_points:
            self._log_trade(
                "HUNTER_FILTER_EMA15",
                "distance=%.2f tolerance=%.2f" % (ema15_distance, self.ema15_tolerance_points),
            )
            return None
        if self.ema15_max_distance is not None and ema15_distance > self.ema15_max_distance:
            self._log_trade(
                "HUNTER_FILTER_EMA15_EXT",
                "distance=%.2f max=%.2f" % (ema15_distance, self.ema15_max_distance),
            )
            return None

        entry = float(bar.close)
        stop = float(bar.low) - self.sl_buffer_points if direction == 1 else float(bar.high) + self.sl_buffer_points
        risk_pts = (entry - stop) if direction == 1 else (stop - entry)
        if risk_pts <= 0:
            self._log_trade("HUNTER_FILTER_RISK", "risk_pts=%.2f" % risk_pts)
            return None

        rr = self._hunter_rr_for_risk(risk_pts)
        target = entry + direction * risk_pts * rr
        qty = self._hunter_qty_for_risk(risk_pts)
        if qty <= 0:
            self._log_trade("HUNTER_FILTER_QTY", "risk_pts=%.2f" % risk_pts)
            return None

        extension_pct = (
            (float(bar.close) - self._orb_high) / self._orb_range * 100.0
            if direction == 1
            else (self._orb_low - float(bar.close)) / self._orb_range * 100.0
        )
        levels = TradeLevels(
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
            gap_size=extension_pct,
        )
        return levels, body_pct, rejection_pct, extension_pct, ema15_distance

    async def _handle_hunter_exit(self, bar: Bar, *, resolution: str) -> None:
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return
        if self._fill_timestamp is not None and bar.timestamp < self._fill_timestamp:
            return

        is_long = levels.direction == 1
        stop_hit = bar.low <= levels.stop if is_long else bar.high >= levels.stop
        target_hit = bar.high >= levels.tp2 if is_long else bar.low <= levels.tp2

        if stop_hit or target_hit:
            if stop_hit:
                await self._finish_hunter_trade(
                    "sl",
                    exit_price=levels.stop,
                    exit_timestamp=bar.timestamp,
                    event="HUNTER_SL",
                    resolution=resolution,
                )
            else:
                await self._finish_hunter_trade(
                    "tp2_direct",
                    exit_price=levels.tp2,
                    exit_timestamp=bar.timestamp,
                    event="HUNTER_TARGET",
                    resolution=resolution,
                )
            return

        if self._hunter_max_hold_at is not None and bar.timestamp >= self._hunter_max_hold_at:
            await self._flatten_position(bar, resolution=resolution, reason="max_hold")

    async def _finish_hunter_trade(
        self,
        exit_type: str,
        *,
        exit_price: float,
        exit_timestamp: datetime,
        event: str,
        resolution: str,
    ) -> None:
        levels = self._levels
        direction_str = "long" if (levels and levels.direction == 1) else "short"
        self._log_trade(
            event,
            "dir=%s exit=%.2f time=%s resolution=%s"
            % (direction_str, exit_price, exit_timestamp, resolution),
        )
        self._release_position_cap()
        if self._should_send:
            self._schedule_post_exit_cleanup(reason=f"{event.lower()}_{resolution}")
        self._emit_trade_record(exit_type, exit_price=exit_price, exit_timestamp=exit_timestamp)
        self._remember_hunter_outcome(exit_timestamp, self._price_to_r(exit_price), exit_type)

        if self._should_continue_scanning(exit_timestamp):
            self._state = State.WAITING_FOR_GAP
        else:
            self._state = State.FLAT
        self._request_checkpoint()
        self._notify_state_change()

    def _remember_hunter_outcome(
        self,
        exit_timestamp: datetime,
        r_result: float,
        exit_type: str,
    ) -> None:
        entry_timestamp = self._fill_timestamp or exit_timestamp
        self._hunter_outcomes.append(
            _HunterOutcome(
                entry_timestamp=entry_timestamp,
                exit_timestamp=exit_timestamp,
                r_result=r_result,
                exit_type=exit_type,
            )
        )
        self._hunter_max_hold_at = None

    def _should_continue_scanning(self, exit_timestamp: datetime) -> bool:
        return self._in_entry(exit_timestamp.time())

    def _can_take_hunter_candidate(
        self,
        signal_bar: Bar,
        extension_pct: float,
        ema15_distance: float | None,
    ) -> bool:
        if not self._hunter_outcomes:
            return True
        if self.reentry_max_extension_pct is not None and extension_pct > self.reentry_max_extension_pct:
            return False

        last = self._hunter_outcomes[-1]
        candidate_entry = signal_bar.timestamp + timedelta(minutes=5)
        minutes_from_last_exit = (candidate_entry - last.exit_timestamp).total_seconds() / 60.0
        last_lost = last.r_result < 0 and last.exit_type == "sl"
        last_won = last.r_result > 0 and last.exit_type == "tp2_direct"
        same_bar_win = (
            last_won
            and (last.exit_timestamp - last.entry_timestamp).total_seconds() / 60.0
            <= self.same_bar_win_reentry_max_minutes
        )

        if (
            self.enable_fast_reentry_exhaustion_filter
            and last_lost
            and minutes_from_last_exit <= self.fast_reentry_exhaustion_max_minutes
            and extension_pct <= self.fast_reentry_exhaustion_max_extension_pct
            and ema15_distance is not None
            and ema15_distance >= self.fast_reentry_exhaustion_min_ema15_distance
        ):
            return False

        if self.reentry_policy == "legacy_one_reentry_after_loss":
            allowed = len(self._hunter_outcomes) == 1 and last_lost
        elif self.reentry_policy == "after_each_loss":
            allowed = last_lost
        elif self.reentry_policy == "all_nonoverlap":
            allowed = True
        else:
            logger.warning("[%s] Unknown reentry_policy=%s", self.name, self.reentry_policy)
            allowed = False

        return allowed or (self.allow_same_bar_win_reentry and same_bar_win)

    def _hunter_qty_for_risk(self, risk_pts: float) -> float:
        if risk_pts <= 0:
            return 0.0
        raw_qty = math.floor(self.risk_usd / (risk_pts * self.point_value))
        qty = max(self.min_qty, float(raw_qty))
        if self.qty_step > 0:
            qty = math.floor(qty / self.qty_step) * self.qty_step
        return min(self.max_contracts, qty)

    def _hunter_rr_for_risk(self, risk_pts: float) -> float:
        return self.reduced_target_rr if risk_pts >= self.large_sl_threshold_points else self.hunter_target_rr

    @staticmethod
    def _body_rejection_pct(bar: Bar, direction: int) -> tuple[float, float]:
        candle_range = float(bar.high - bar.low)
        if candle_range <= 0:
            return 0.0, 100.0
        body_pct = abs(float(bar.close - bar.open)) / candle_range * 100.0
        if direction == 1:
            rejection_pct = (float(bar.high) - max(float(bar.open), float(bar.close))) / candle_range * 100.0
        else:
            rejection_pct = (min(float(bar.open), float(bar.close)) - float(bar.low)) / candle_range * 100.0
        return body_pct, rejection_pct

    def _ema15_distance(self, bar: Bar, direction: int) -> float | None:
        if self._ema15_last_completed is None:
            return None
        if direction == 1:
            return float(bar.close) - self._ema15_last_completed
        return self._ema15_last_completed - float(bar.close)

    def _reset_ema15(self) -> None:
        self._ema15_bucket_start = None
        self._ema15_open = 0.0
        self._ema15_high = float("-inf")
        self._ema15_low = float("inf")
        self._ema15_close = 0.0
        self._ema15_last_completed = None

    def _update_ema15(self, bar: Bar) -> None:
        bucket = self._bucket_15m(bar.timestamp)
        if self._ema15_bucket_start is None:
            self._start_ema15_bucket(bucket, bar)
            return

        if bucket != self._ema15_bucket_start:
            self._finalize_ema15_bucket()
            self._start_ema15_bucket(bucket, bar)
            return

        self._ema15_high = max(self._ema15_high, float(bar.high))
        self._ema15_low = min(self._ema15_low, float(bar.low))
        self._ema15_close = float(bar.close)

    def _start_ema15_bucket(self, bucket: datetime, bar: Bar) -> None:
        self._ema15_bucket_start = bucket
        self._ema15_open = float(bar.open)
        self._ema15_high = float(bar.high)
        self._ema15_low = float(bar.low)
        self._ema15_close = float(bar.close)

    def _finalize_ema15_bucket(self) -> None:
        source_value = self._ema15_source_value()
        if self._ema15_last_completed is None:
            self._ema15_last_completed = source_value
            return
        alpha = 2.0 / (self.ema15_length + 1.0)
        self._ema15_last_completed = (
            source_value * alpha + self._ema15_last_completed * (1.0 - alpha)
        )

    def _ema15_source_value(self) -> float:
        if self.ema15_source == "close":
            return self._ema15_close
        if self.ema15_source == "hl2":
            return (self._ema15_high + self._ema15_low) / 2.0
        if self.ema15_source == "hlc3":
            return (self._ema15_high + self._ema15_low + self._ema15_close) / 3.0
        if self.ema15_source == "ohlc4":
            return (self._ema15_open + self._ema15_high + self._ema15_low + self._ema15_close) / 4.0
        logger.warning("[%s] Unknown ema15_source=%s; using close", self.name, self.ema15_source)
        return self._ema15_close

    @staticmethod
    def _bucket_15m(ts: datetime) -> datetime:
        minute = (ts.minute // 15) * 15
        return ts.replace(minute=minute, second=0, microsecond=0)
