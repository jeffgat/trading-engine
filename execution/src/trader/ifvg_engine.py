"""IFVG (Inverse Fair Value Gap) engine for live LSI reversal strategy.

State machine:
    IDLE → MONITORING → WAITING_FOR_GAP → COLLECTING_GAPS →
    WAITING_FOR_INVERSION → ARMED_LIMIT → MANAGING → FLAT

Unlike SessionEngine (continuation FVG after ORB), this engine detects:
    1. Liquidity sweep (KZ/PDH/PDL levels)
    2. Opposite-direction FVG formation after sweep
    3. Price inversion through the gap
    4. Limit entry at gap edge
    5. Position management (SL/TP1/TP2/BE/EOD)

Implements the same on_bar() / on_tick() interface as SessionEngine.
"""

from __future__ import annotations

import enum
import logging
import math
from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable

from .broker import TradersPostClient
from .engine import Bar, TradeRecord
from .liquidity import LiquidityTracker
from .sizing import TradeLevels, compute_trade_levels
from .sweep import SweepEvent, SweepTracker

logger = logging.getLogger(__name__)
trade_logger = logging.getLogger("trader.trades")


class IFVGState(enum.Enum):
    IDLE = "idle"
    MONITORING = "monitoring"  # in entry window, watching for sweeps
    WAITING_FOR_GAP = "waiting_for_gap"  # sweep detected, scanning for FVG
    COLLECTING_GAPS = "collecting_gaps"  # singular gap validation
    WAITING_FOR_INVERSION = "waiting_for_inversion"  # gap found, waiting for close inversion
    ARMED_LIMIT = "armed_limit"  # limit order placed at gap edge
    MANAGING = "managing"  # in position, managing exits
    FLAT = "flat"  # done for the day


def _parse_time(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


@dataclass
class GapInfo:
    """Detected FVG after a sweep."""
    top: float
    bottom: float
    is_bullish: bool  # True = bullish FVG
    impulse_high: float  # high of impulse candle (bar[1])
    impulse_low: float  # low of impulse candle (bar[1])
    bar_index: int  # bar count when gap was detected


class IFVGEngine:
    """Live execution engine for the IFVG/LSI reversal strategy."""

    def __init__(
        self,
        name: str,
        broker: TradersPostClient,
        exec_ticker: str,
        # Session windows
        entry_start: str,
        entry_end: str,
        flat_start: str,
        flat_end: str,
        # Strategy params
        rr: float = 3.0,
        tp1_ratio: float = 0.3,
        min_gap_atr_pct: float = 5.0,
        min_stop_atr_pct: float = 0.05,
        max_bars_after_sweep: int = 20,
        max_inversion_bars: int = 10,
        # Risk params
        risk_usd: float = 250.0,
        point_value: float = 2.0,
        min_qty: float = 1.0,
        qty_step: float = 1.0,
        qty_multiplier: float = 1.0,
        be_offset_ticks: int = 4,
        min_tick: float = 0.25,
        max_single_risk_usd: float = 500.0,
        # Direction
        long_only: bool = True,
        # DOW exclusion
        excluded_dow: int | None = None,
        excluded_dates: tuple[str, ...] = (),
        half_days: tuple[str, ...] = (),
        half_day_flat_start: str = "12:50",
        half_day_flat_end: str = "13:00",
        # Killzones
        killzones: list[tuple[str, str, str]] | None = None,
        # Execution config name
        config_name: str = "",
    ) -> None:
        self.name = name
        self.broker = broker
        self.exec_ticker = exec_ticker
        self.config_name = config_name

        # Time windows
        self.entry_start = entry_start
        self.entry_end = entry_end
        self.flat_start = flat_start
        self.flat_end = flat_end
        self._entry_start_t = _parse_time(entry_start)
        self._entry_end_t = _parse_time(entry_end)
        self._flat_start_t = _parse_time(flat_start)
        self._flat_end_t = _parse_time(flat_end)

        # Strategy
        self.rr = rr
        self.tp1_ratio = tp1_ratio
        self.min_gap_atr_pct = min_gap_atr_pct
        self.min_stop_atr_pct = min_stop_atr_pct
        self.max_bars_after_sweep = max_bars_after_sweep
        self.max_inversion_bars = max_inversion_bars

        # Risk
        self.risk_usd = risk_usd
        self.point_value = point_value
        self.min_qty = min_qty
        self.qty_step = qty_step
        self.qty_multiplier = qty_multiplier
        self.be_offset_ticks = be_offset_ticks
        self.min_tick = min_tick
        self.max_single_risk_usd = max_single_risk_usd

        # Direction
        self.long_only = long_only
        self.excluded_dow = excluded_dow
        self.excluded_dates = excluded_dates
        self.half_days = half_days
        self._half_day_flat_start_t = _parse_time(half_day_flat_start)
        self._half_day_flat_end_t = _parse_time(half_day_flat_end)

        # Trackers
        kz_list = killzones or [("Asia", "20:00", "00:00"), ("London", "02:00", "05:00")]
        self._liquidity = LiquidityTracker(kz_list)
        self._sweeps = SweepTracker(long_only=long_only)

        # State
        self._state = IFVGState.IDLE
        self._current_date = ""
        self._daily_atr: float = 0.0
        self._bar_count: int = 0

        # Bar history (last 3 for FVG detection)
        self._bars: list[Bar] = []

        # Sweep + gap state
        self._active_sweep: SweepEvent | None = None
        self._active_gap: GapInfo | None = None
        self._sweep_bar_index: int = 0

        # Limit order state
        self._limit_price: float = 0.0
        self._limit_direction: int = 0
        self._limit_stop: float = 0.0

        # Position state
        self._levels: TradeLevels | None = None
        self._tp1_hit: bool = False
        self._fill_timestamp: datetime | None = None

        # Callbacks
        self.on_state_change: Callable[[dict], None] | None = None
        self.on_trade_exit: Callable[[TradeRecord], None] | None = None

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def _in_entry(self, bar_time: time) -> bool:
        s, e = self._entry_start_t, self._entry_end_t
        if s <= e:
            return s <= bar_time < e
        return bar_time >= s or bar_time < e

    def _in_flat(self, bar) -> bool:
        bar_time = bar.timestamp.time() if hasattr(bar.timestamp, "time") else bar.timestamp
        s, e = self._flat_start_t, self._flat_end_t
        # Half-day override
        if self._current_date in self.half_days:
            s, e = self._half_day_flat_start_t, self._half_day_flat_end_t
        if s <= e:
            return s <= bar_time <= e
        return bar_time >= s or bar_time <= e

    def _is_excluded_day(self, bar: Bar) -> bool:
        """Check DOW and date exclusions."""
        if self._current_date in self.excluded_dates:
            return True
        if self.excluded_dow is not None:
            dow = bar.timestamp.weekday() if hasattr(bar.timestamp, "weekday") else 0
            # excluded_dow can be a single int or a list of ints
            if isinstance(self.excluded_dow, (list, tuple)):
                if dow in self.excluded_dow:
                    return True
            elif dow == self.excluded_dow:
                return True
        return False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_trade(self, event: str, detail: str = "") -> None:
        cfg = self.config_name or "DEFAULT"
        if detail:
            trade_logger.info(
                "%s | nq | %s | %s | %s", cfg, self.name, event, detail,
            )
            return
        trade_logger.info("%s | nq | %s | %s", cfg, self.name, event)

    def _notify_state_change(self) -> None:
        if self.on_state_change:
            self.on_state_change(self.status_dict())

    def _emit_trade_record(self, exit_type: str) -> None:
        if self.on_trade_exit is None:
            return
        levels = self._levels
        record = TradeRecord(
            session=self.name,
            date=self._current_date,
            direction=levels.direction if levels else 0,
            entry_price=levels.entry if levels else 0.0,
            stop_price=levels.stop if levels else 0.0,
            tp1_price=levels.tp1 if levels else 0.0,
            tp2_price=levels.tp2 if levels else 0.0,
            exit_type=exit_type,
            tp1_hit=self._tp1_hit,
            timestamp=datetime.now().isoformat(),
            config_name=self.config_name,
        )
        self.on_trade_exit(record)

    # ------------------------------------------------------------------
    # FVG detection (3-candle pattern, no ORB filter)
    # ------------------------------------------------------------------

    def _check_fvg(self, daily_atr: float) -> tuple[bool, bool, GapInfo | None]:
        """Check last 3 bars for FVG. Returns (found, is_bullish, gap_info)."""
        if len(self._bars) < 3:
            return False, False, None

        bar0 = self._bars[-1]  # current (after candle)
        bar1 = self._bars[-2]  # impulse candle
        bar2 = self._bars[-3]  # before candle

        min_gap = (self.min_gap_atr_pct / 100.0) * daily_atr

        # Bullish FVG: bar2.high < bar0.low (gap up)
        if bar2.high < bar0.low and bar2.high < bar1.high and bar2.low < bar0.low:
            gap_size = bar0.low - bar2.high
            if gap_size >= min_gap:
                return True, True, GapInfo(
                    top=bar0.low,
                    bottom=bar2.high,
                    is_bullish=True,
                    impulse_high=bar1.high,
                    impulse_low=bar1.low,
                    bar_index=self._bar_count,
                )

        # Bearish FVG: bar2.low > bar0.high (gap down)
        if bar2.low > bar0.high and bar2.low > bar1.low and bar2.high > bar0.high:
            gap_size = bar2.low - bar0.high
            if gap_size >= min_gap:
                return True, False, GapInfo(
                    top=bar2.low,
                    bottom=bar0.high,
                    is_bullish=False,
                    impulse_high=bar1.high,
                    impulse_low=bar1.low,
                    bar_index=self._bar_count,
                )

        return False, False, None

    # ------------------------------------------------------------------
    # 5m bar handler (signals: sweep/gap/inversion detection)
    # ------------------------------------------------------------------

    async def on_bar(self, bar: Bar, daily_atr: float) -> None:
        """Process a 5m bar — runs all signal detection."""
        self._daily_atr = daily_atr
        self._bar_count += 1

        # Store bar history (keep last 3)
        self._bars.append(bar)
        if len(self._bars) > 3:
            self._bars.pop(0)

        # Feed liquidity tracker (needs ALL bars, not just entry window)
        self._liquidity.on_bar(bar)

        bar_date = bar.timestamp.strftime("%Y%m%d")
        bar_time = bar.timestamp.time()

        # New day reset
        if bar_date != self._current_date:
            if self._state == IFVGState.MANAGING:
                # Force flat on day change (shouldn't happen in normal flow)
                await self._exit_position(bar, "eod")
            self._current_date = bar_date
            self._state = IFVGState.IDLE
            self._active_sweep = None
            self._active_gap = None
            self._levels = None
            self._tp1_hit = False
            self._fill_timestamp = None

        # Feed sweep tracker
        levels = self._liquidity.levels
        sweep = self._sweeps.on_bar(bar, levels)

        # State machine
        if self._state == IFVGState.IDLE:
            if self._in_entry(bar_time) and not self._is_excluded_day(bar):
                self._state = IFVGState.MONITORING
                self._notify_state_change()

        if self._state == IFVGState.MONITORING:
            if not self._in_entry(bar_time):
                self._log_trade("NO_SETUP", "entry window closed")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            # Check for sweep events
            if sweep is not None:
                # For long_only: only accept long setups (low sweeps).
                # Use continue-style logic: skip sweep but don't return so
                # WAITING_FOR_GAP / WAITING_FOR_INVERSION blocks still run.
                if not (self.long_only and sweep.direction != 1):
                    self._active_sweep = sweep
                    self._sweep_bar_index = self._bar_count
                    self._state = IFVGState.WAITING_FOR_GAP
                    self._log_trade(
                        "SWEEP_DETECTED",
                        "source=%s level=%.2f dir=%s bar_count=%d"
                        % (sweep.source, sweep.level, "long" if sweep.direction == 1 else "short", self._bar_count),
                    )
                    self._notify_state_change()

        if self._state == IFVGState.WAITING_FOR_GAP:
            if not self._in_entry(bar_time):
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            # Check bar count since sweep
            bars_since = self._bar_count - self._sweep_bar_index
            if bars_since > self.max_bars_after_sweep:
                self._log_trade("SWEEP_EXPIRED", "bars_since=%d" % bars_since)
                self._state = IFVGState.MONITORING
                self._active_sweep = None
                self._notify_state_change()
                return

            # Look for opposite-direction FVG
            found, is_bullish, gap = self._check_fvg(daily_atr)
            if found and gap is not None:
                sweep = self._active_sweep
                # After low sweep (long setup): need bearish FVG
                # After high sweep (short setup): need bullish FVG
                need_bearish = sweep.direction == 1
                if (need_bearish and not is_bullish) or (not need_bearish and is_bullish):
                    self._active_gap = gap
                    self._state = IFVGState.WAITING_FOR_INVERSION
                    self._log_trade(
                        "GAP_DETECTED",
                        "type=%s top=%.2f bottom=%.2f size=%.2f"
                        % ("bearish" if not is_bullish else "bullish",
                           gap.top, gap.bottom, gap.top - gap.bottom),
                    )
                    self._notify_state_change()

        if self._state == IFVGState.WAITING_FOR_INVERSION:
            if not self._in_entry(bar_time):
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            gap = self._active_gap
            # Expire if inversion took too long
            bars_since_gap = self._bar_count - gap.bar_index
            if self.max_inversion_bars > 0 and bars_since_gap > self.max_inversion_bars:
                self._log_trade("INVERSION_EXPIRED", "bars_since_gap=%d" % bars_since_gap)
                self._state = IFVGState.MONITORING
                self._active_sweep = None
                self._active_gap = None
                self._notify_state_change()
                return

            # Only check inversion on bars AFTER the gap formed
            if self._bar_count <= gap.bar_index:
                return

            sweep = self._active_sweep
            # Price-close inversion
            if gap.is_bullish and bar.close < gap.bottom:
                # Bullish FVG inverted → SHORT setup
                if not self.long_only:
                    await self._place_limit_order(gap, direction=-1, daily_atr=daily_atr)
            elif not gap.is_bullish and bar.close > gap.top:
                # Bearish FVG inverted → LONG setup
                await self._place_limit_order(gap, direction=1, daily_atr=daily_atr)

        if self._state == IFVGState.ARMED_LIMIT:
            if self._in_flat(bar):
                self._log_trade("LIMIT_EXPIRED_EOD", "flat window reached")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            # Check limit fill on 5m bar
            await self._check_limit_fill(bar, daily_atr)

        if self._state == IFVGState.MANAGING:
            await self._handle_managing(bar, daily_atr)

    # ------------------------------------------------------------------
    # Limit order placement
    # ------------------------------------------------------------------

    async def _place_limit_order(self, gap: GapInfo, direction: int, daily_atr: float) -> None:
        """Place limit order at gap edge after inversion."""
        if direction == 1:
            # LONG: limit at gap bottom (bearish gap inverted upward)
            self._limit_price = gap.bottom
            self._limit_stop = gap.impulse_low
        else:
            # SHORT: limit at gap top (bullish gap inverted downward)
            self._limit_price = gap.top
            self._limit_stop = gap.impulse_high

        self._limit_direction = direction
        self._state = IFVGState.ARMED_LIMIT
        dir_str = "long" if direction == 1 else "short"
        self._log_trade(
            "LIMIT_PLACED",
            "dir=%s limit=%.2f stop=%.2f gap_size=%.2f"
            % (dir_str, self._limit_price, self._limit_stop, gap.top - gap.bottom),
        )
        self._notify_state_change()

    # ------------------------------------------------------------------
    # Limit fill check
    # ------------------------------------------------------------------

    async def _check_limit_fill(self, bar: Bar, daily_atr: float) -> None:
        """Check if limit order is filled on this bar."""
        direction = self._limit_direction
        is_long = direction == 1

        # Long limit: fill when low <= limit_price
        # Short limit: fill when high >= limit_price
        filled = (is_long and bar.low <= self._limit_price) or \
                 (not is_long and bar.high >= self._limit_price)

        if not filled:
            return

        # Determine entry price (handle gap-open slippage)
        if is_long:
            entry = min(bar.open, self._limit_price) if bar.open < self._limit_price else self._limit_price
        else:
            entry = max(bar.open, self._limit_price) if bar.open > self._limit_price else self._limit_price

        # Compute stop with minimum distance
        raw_stop = self._limit_stop
        min_stop_dist = daily_atr * self.min_stop_atr_pct
        if is_long:
            if entry - raw_stop < min_stop_dist:
                raw_stop = entry - min_stop_dist
        else:
            if raw_stop - entry < min_stop_dist:
                raw_stop = entry + min_stop_dist

        gap = self._active_gap
        gap_size = gap.top - gap.bottom if gap else 0.0

        levels = compute_trade_levels(
            entry=entry,
            direction=direction,
            gap_size=gap_size,
            daily_atr=daily_atr,
            stop_atr_pct=0.0,  # not used — stop from impulse candle
            rr=self.rr,
            tp1_ratio=self.tp1_ratio,
            risk_usd=self.risk_usd,
            point_value=self.point_value,
            min_qty=self.min_qty,
            qty_step=self.qty_step,
            be_offset_ticks=self.be_offset_ticks,
            min_tick=self.min_tick,
            max_single_risk_usd=self.max_single_risk_usd,
            qty_multiplier=self.qty_multiplier,
        )

        if levels is None:
            self._log_trade("LIMIT_REJECTED", "qty below minimum")
            self._state = IFVGState.FLAT
            self._notify_state_change()
            return

        # Override stop with our computed stop (not ATR-based)
        # We need to reconstruct TradeLevels with the correct stop
        risk_pts = abs(entry - raw_stop)
        tp1_dist = self.rr * risk_pts * self.tp1_ratio
        tp2_dist = self.rr * risk_pts
        be_offset = self.be_offset_ticks * self.min_tick

        from .sizing import TradeLevels as TL, _floor_to_step
        qty_raw = self.risk_usd / (risk_pts * self.point_value) if risk_pts > 0 else 0
        qty = _floor_to_step(qty_raw, self.qty_step)
        if qty < self.min_qty:
            single_risk = risk_pts * self.point_value * self.min_qty
            if single_risk <= self.max_single_risk_usd:
                qty = self.min_qty
            else:
                self._log_trade("LIMIT_REJECTED", "risk too high for 1 contract")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

        if self.qty_multiplier != 1.0:
            qty = _floor_to_step(qty * self.qty_multiplier, self.qty_step)
            qty = max(qty, self.min_qty)

        is_single = qty <= self.min_qty
        if is_single:
            half_qty = qty
        else:
            half_qty = _floor_to_step(qty / 2, self.qty_step)
            half_qty = max(half_qty, self.min_qty)

        self._levels = TL(
            entry=entry,
            stop=raw_stop,
            tp1=entry + tp1_dist * direction,
            tp2=entry + tp2_dist * direction,
            be=entry + be_offset * direction,
            qty=qty,
            half_qty=half_qty,
            is_single_contract=is_single,
            risk_pts=risk_pts,
            direction=direction,
            gap_size=gap_size,
        )

        # Check same-bar stop hit (pessimistic)
        sl_hit = (is_long and bar.low <= raw_stop) or (not is_long and bar.high >= raw_stop)
        if sl_hit:
            self._log_trade(
                "SL_HIT",
                "dir=%s (same-bar fill+stop) entry=%.2f stop=%.2f"
                % ("long" if is_long else "short", entry, raw_stop),
            )
            self._emit_trade_record("sl")
            self._state = IFVGState.FLAT
            self._notify_state_change()
            return

        # Filled successfully
        self._tp1_hit = False
        self._fill_timestamp = bar.timestamp
        self._state = IFVGState.MANAGING

        dir_str = "long" if is_long else "short"
        self._log_trade(
            "FILLED",
            "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f"
            % (dir_str, self._levels.entry, self._levels.stop,
               self._levels.tp1, self._levels.tp2, self._levels.qty),
        )

        await self.broker.send_entry(
            direction=dir_str,
            qty=self._levels.qty,
            ticker=self.exec_ticker,
        )
        self._notify_state_change()

    # ------------------------------------------------------------------
    # Position management (5m bars)
    # ------------------------------------------------------------------

    async def _handle_managing(self, bar: Bar, daily_atr: float) -> None:
        """Manage open position on 5m bars."""
        levels = self._levels
        if levels is None:
            self._state = IFVGState.FLAT
            return

        is_long = levels.direction == 1
        dir_str = "long" if is_long else "short"

        # EOD flat
        if self._in_flat(bar):
            await self._exit_position(bar, "tp1_eod" if self._tp1_hit else "eod")
            return

        # Pre-TP1 phase
        if not self._tp1_hit:
            sl_hit = (is_long and bar.low <= levels.stop) or (not is_long and bar.high >= levels.stop)
            tp1_touched = (is_long and bar.high >= levels.tp1) or (not is_long and bar.low <= levels.tp1)

            if sl_hit and tp1_touched:
                # Ambiguous — pessimistic: SL wins
                await self._exit_position(bar, "sl")
                return

            if sl_hit:
                await self._exit_position(bar, "sl")
                return

            if tp1_touched:
                self._tp1_hit = True
                if levels.is_single_contract:
                    self._log_trade("TP1_BE_SINGLE", "dir=%s tp1=%.2f be=%.2f" % (dir_str, levels.tp1, levels.be))
                    await self.broker.send_tp1_single(
                        direction=dir_str, qty=levels.qty, be_price=levels.be, ticker=self.exec_ticker)
                else:
                    self._log_trade("TP1_PARTIAL", "dir=%s tp1=%.2f half=%.1f be=%.2f tp2=%.2f"
                                    % (dir_str, levels.tp1, levels.half_qty, levels.be, levels.tp2))
                    await self.broker.send_tp1_multi(
                        direction=dir_str, half_qty=levels.half_qty, be_price=levels.be,
                        tp2=levels.tp2, ticker=self.exec_ticker)
                self._notify_state_change()
                return

            # TP2 direct (skipping TP1)
            tp2_hit = (is_long and bar.high >= levels.tp2) or (not is_long and bar.low <= levels.tp2)
            if tp2_hit:
                await self._exit_position(bar, "tp2_direct")
                return

        # Post-TP1: check BE and TP2
        else:
            be_hit = (is_long and bar.low <= levels.be) or (not is_long and bar.high >= levels.be)
            tp2_hit = (is_long and bar.high >= levels.tp2) or (not is_long and bar.low <= levels.tp2)

            if be_hit:
                await self._exit_position(bar, "tp1_be")
                return
            if tp2_hit:
                await self._exit_position(bar, "tp1_tp2")
                return

    async def _exit_position(self, bar: Bar, exit_type: str) -> None:
        """Exit position and transition to FLAT."""
        levels = self._levels
        dir_str = "long" if (levels and levels.direction == 1) else "short"
        self._log_trade(exit_type.upper(), "dir=%s bar_time=%s" % (dir_str, bar.timestamp))
        await self.broker.send_flatten(ticker=self.exec_ticker)
        self._emit_trade_record(exit_type)
        self._state = IFVGState.FLAT
        self._notify_state_change()

    # ------------------------------------------------------------------
    # 1s tick handler (fine-grained exit management)
    # ------------------------------------------------------------------

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        """Process a 1s bar for fine-grained exit management."""
        self._daily_atr = daily_atr

        # Feed liquidity tracker with tick data too
        self._liquidity.on_bar(tick)

        if self._state == IFVGState.ARMED_LIMIT:
            await self._check_limit_fill(tick, daily_atr)
            return

        if self._state != IFVGState.MANAGING:
            return

        levels = self._levels
        if levels is None:
            self._state = IFVGState.FLAT
            return

        is_long = levels.direction == 1
        dir_str = "long" if is_long else "short"

        # EOD flat
        if self._in_flat(tick):
            self._log_trade("EOD_FLAT", "dir=%s tick_time=%s resolution=1s" % (dir_str, tick.timestamp))
            await self.broker.send_flatten(ticker=self.exec_ticker)
            self._emit_trade_record("tp1_eod" if self._tp1_hit else "eod")
            self._state = IFVGState.FLAT
            self._notify_state_change()
            return

        # Same-tick guard
        if self._fill_timestamp is not None and tick.timestamp <= self._fill_timestamp:
            return

        # Pre-TP1
        if not self._tp1_hit:
            sl_hit = (is_long and tick.low <= levels.stop) or (not is_long and tick.high >= levels.stop)
            tp1_touched = (is_long and tick.high >= levels.tp1) or (not is_long and tick.low <= levels.tp1)

            if sl_hit and tp1_touched:
                self._log_trade("SL_HIT", "dir=%s stop=%.2f (1s ambiguous) resolution=1s" % (dir_str, levels.stop))
                await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("sl")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            if sl_hit:
                self._log_trade("SL_HIT", "dir=%s stop=%.2f resolution=1s" % (dir_str, levels.stop))
                await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("sl")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            if tp1_touched:
                self._tp1_hit = True
                if levels.is_single_contract:
                    self._log_trade("TP1_BE_SINGLE", "dir=%s tp1=%.2f be=%.2f resolution=1s" % (dir_str, levels.tp1, levels.be))
                    await self.broker.send_tp1_single(direction=dir_str, qty=levels.qty, be_price=levels.be, ticker=self.exec_ticker)
                else:
                    self._log_trade("TP1_PARTIAL", "dir=%s tp1=%.2f half=%.1f be=%.2f tp2=%.2f resolution=1s"
                                    % (dir_str, levels.tp1, levels.half_qty, levels.be, levels.tp2))
                    await self.broker.send_tp1_multi(direction=dir_str, half_qty=levels.half_qty, be_price=levels.be, tp2=levels.tp2, ticker=self.exec_ticker)
                self._notify_state_change()
                return

            # TP2 direct
            tp2_hit = (is_long and tick.high >= levels.tp2) or (not is_long and tick.low <= levels.tp2)
            if tp2_hit:
                self._log_trade("TP2_DIRECT", "dir=%s tp2=%.2f resolution=1s" % (dir_str, levels.tp2))
                await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp2_direct")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

        # Post-TP1
        else:
            be_hit = (is_long and tick.low <= levels.be) or (not is_long and tick.high >= levels.be)
            tp2_hit = (is_long and tick.high >= levels.tp2) or (not is_long and tick.low <= levels.tp2)

            if be_hit:
                self._log_trade("BE_HIT", "dir=%s be=%.2f resolution=1s" % (dir_str, levels.be))
                await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp1_be")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

            if tp2_hit:
                self._log_trade("TP2_HIT", "dir=%s tp2=%.2f resolution=1s" % (dir_str, levels.tp2))
                await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp1_tp2")
                self._state = IFVGState.FLAT
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # Public status
    # ------------------------------------------------------------------

    @property
    def state(self) -> IFVGState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state not in (IFVGState.IDLE, IFVGState.FLAT)

    def status_dict(self) -> dict:
        levels = self._levels
        liq = self._liquidity.levels
        return {
            "config_name": self.config_name,
            "session": self.name,
            "state": self._state.value,
            "type": "ifvg",
            "date": self._current_date,
            "daily_atr": round(self._daily_atr, 2) if self._daily_atr else None,
            "kz_high": round(liq.kz_high, 2) if not math.isnan(liq.kz_high) else None,
            "kz_low": round(liq.kz_low, 2) if not math.isnan(liq.kz_low) else None,
            "kz_source": liq.kz_source or None,
            "pdh": round(liq.pdh, 2) if not math.isnan(liq.pdh) else None,
            "pdl": round(liq.pdl, 2) if not math.isnan(liq.pdl) else None,
            "entry": round(levels.entry, 2) if levels else None,
            "stop": round(levels.stop, 2) if levels else None,
            "tp1": round(levels.tp1, 2) if levels else None,
            "tp2": round(levels.tp2, 2) if levels else None,
            "direction": levels.direction if levels else None,
            "qty": levels.qty if levels else None,
            "tp1_hit": self._tp1_hit,
        }
