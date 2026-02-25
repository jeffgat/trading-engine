"""Session state machine for live trade management.

Each SessionEngine tracks one trading session (NY or Asia) through its daily
lifecycle: ORB building → FVG scanning → order placement → position management.

State machine:
    IDLE → ORB_BUILDING → SCANNING → ARMED_{LONG,SHORT} → FILLED → MANAGING → FLAT → IDLE
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Callable

from .broker import TradersPostClient
from .sizing import TradeLevels, compute_trade_levels

logger = logging.getLogger(__name__)
trade_logger = logging.getLogger("trader.trades")


# ---------------------------------------------------------------------------
# Bar data
# ---------------------------------------------------------------------------

@dataclass
class Bar:
    """OHLCV bar (5m for signals, 1s for tick-level exit management)."""

    timestamp: datetime  # bar open time (Eastern)
    open: float
    high: float
    low: float
    close: float
    volume: int


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class State(enum.Enum):
    IDLE = "idle"
    ORB_BUILDING = "orb_building"
    SCANNING = "scanning"
    ARMED_LONG = "armed_long"
    ARMED_SHORT = "armed_short"
    FILLED = "filled"
    MANAGING = "managing"
    FLAT = "flat"


# ---------------------------------------------------------------------------
# Session time helpers
# ---------------------------------------------------------------------------

def _parse_time(s: str) -> time:
    """Parse 'HH:MM' to datetime.time."""
    h, m = s.split(":")
    return time(int(h), int(m))


def _time_in_range(t: time, start: time, end: time) -> bool:
    """Check if time t is in [start, end). Handles cross-midnight."""
    if start <= end:
        return start <= t < end
    else:
        return t >= start or t < end


# ---------------------------------------------------------------------------
# Session engine
# ---------------------------------------------------------------------------

@dataclass
class SessionEngine:
    """Manages one session's daily trade lifecycle.

    Args:
        name: Session name ("NY" or "Asia").
        broker: TradersPost webhook client.
        orb_start: ORB window start (HH:MM).
        orb_end: ORB window end (HH:MM).
        entry_start: Entry window start (HH:MM).
        entry_end: Entry window end (HH:MM).
        flat_start: Flat/EOD window start (HH:MM).
        flat_end: Flat/EOD window end (HH:MM).
        stop_atr_pct: Stop distance as % of daily ATR.
        min_gap_atr_pct: Min FVG gap as % of daily ATR.
        max_gap_atr_pct: Max FVG gap as % of daily ATR (0 = no limit).
        rr: Reward/risk ratio.
        tp1_ratio: Fraction of target for TP1.
        risk_usd: Risk per trade in USD.
        point_value: Dollar value per point (execution instrument).
        min_qty: Minimum contract quantity.
        qty_step: Contract quantity step.
        be_offset_ticks: Ticks above/below entry for BE stop.
        min_tick: Minimum price tick.
        excluded_dates: Dates to skip (YYYYMMDD strings).
        half_days: Half-day dates (YYYYMMDD strings) — flat earlier.
        half_day_flat_start: Flat window start on half days (HH:MM).
        half_day_flat_end: Flat window end on half days (HH:MM).
    """

    name: str
    broker: TradersPostClient

    # Session time windows
    orb_start: str
    orb_end: str
    entry_start: str
    entry_end: str
    flat_start: str
    flat_end: str

    # Strategy params
    stop_atr_pct: float
    min_gap_atr_pct: float
    max_gap_atr_pct: float
    rr: float
    tp1_ratio: float
    risk_usd: float
    point_value: float
    min_qty: float
    qty_step: float
    be_offset_ticks: int
    min_tick: float

    # Date filters
    excluded_dates: tuple[str, ...] = ()
    half_days: tuple[str, ...] = ()
    half_day_flat_start: str = "12:50"
    half_day_flat_end: str = "13:00"

    # Optional callback for dashboard state change notifications
    on_state_change: Callable[[dict], None] | None = None

    # Internal state (reset daily)
    _state: State = field(default=State.IDLE, init=False)
    _orb_high: float = field(default=float("nan"), init=False)
    _orb_low: float = field(default=float("nan"), init=False)
    _bars: list[Bar] = field(default_factory=list, init=False)  # rolling window
    _levels: TradeLevels | None = field(default=None, init=False)
    _tp1_hit: bool = field(default=False, init=False)
    _fill_bar_idx: int = field(default=-1, init=False)
    _fill_timestamp: datetime | None = field(default=None, init=False)
    _bar_count: int = field(default=0, init=False)
    _long_fvg_found: bool = field(default=False, init=False)
    _short_fvg_found: bool = field(default=False, init=False)
    _current_date: str = field(default="", init=False)
    _daily_atr: float = field(default=0.0, init=False)

    # Parsed times (computed on first bar)
    _orb_start_t: time | None = field(default=None, init=False, repr=False)
    _orb_end_t: time | None = field(default=None, init=False, repr=False)
    _entry_start_t: time | None = field(default=None, init=False, repr=False)
    _entry_end_t: time | None = field(default=None, init=False, repr=False)
    _flat_start_t: time | None = field(default=None, init=False, repr=False)
    _flat_end_t: time | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        self._orb_start_t = _parse_time(self.orb_start)
        self._orb_end_t = _parse_time(self.orb_end)
        self._entry_start_t = _parse_time(self.entry_start)
        self._entry_end_t = _parse_time(self.entry_end)
        self._flat_start_t = _parse_time(self.flat_start)
        self._flat_end_t = _parse_time(self.flat_end)

    def _notify_state_change(self) -> None:
        """Notify dashboard of a state transition."""
        if self.on_state_change is not None:
            self.on_state_change(self.status_dict())

    # ------------------------------------------------------------------
    # Time checks
    # ------------------------------------------------------------------

    def _in_orb(self, t: time) -> bool:
        return _time_in_range(t, self._orb_start_t, self._orb_end_t)

    def _in_entry(self, t: time) -> bool:
        return _time_in_range(t, self._entry_start_t, self._entry_end_t)

    def _in_rth(self, t: time) -> bool:
        return _time_in_range(t, self._orb_start_t, self._flat_end_t)

    def _in_flat(self, bar: Bar) -> bool:
        t = bar.timestamp.time()
        date_str = bar.timestamp.strftime("%Y%m%d")
        if date_str in self.half_days:
            hd_start = _parse_time(self.half_day_flat_start)
            hd_end = _parse_time(self.half_day_flat_end)
            return _time_in_range(t, hd_start, hd_end)
        return _time_in_range(t, self._flat_start_t, self._flat_end_t)

    def _is_excluded(self, bar: Bar) -> bool:
        return bar.timestamp.strftime("%Y%m%d") in self.excluded_dates

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------

    def _reset_day(self, date_str: str) -> None:
        """Reset all state for a new trading day."""
        self._state = State.IDLE
        self._orb_high = float("nan")
        self._orb_low = float("nan")
        self._bars.clear()
        self._levels = None
        self._tp1_hit = False
        self._fill_bar_idx = -1
        self._fill_timestamp = None
        self._bar_count = 0
        self._long_fvg_found = False
        self._short_fvg_found = False
        self._current_date = date_str
        logger.info("[%s] New session day: %s", self.name, date_str)
        self._notify_state_change()

    # ------------------------------------------------------------------
    # FVG detection (inline, 3-bar check)
    # ------------------------------------------------------------------

    def _check_long_fvg(self) -> tuple[bool, float, float]:
        """Check for bullish FVG in last 3 bars.

        Returns (detected, entry_price, gap_size).
        """
        if len(self._bars) < 3:
            return False, 0.0, 0.0

        bar0 = self._bars[-1]  # current (most recent)
        bar1 = self._bars[-2]  # middle
        bar2 = self._bars[-3]  # oldest

        # Pine: high[2] < low[0] AND high[2] < high[1] AND low[2] < low[0]
        if bar2.high < bar0.low and bar2.high < bar1.high and bar2.low < bar0.low:
            gap_size = bar0.low - bar2.high
            entry = bar0.low  # FVG top
            # Must be above ORB high
            if entry > self._orb_high:
                return True, entry, gap_size

        return False, 0.0, 0.0

    def _check_short_fvg(self) -> tuple[bool, float, float]:
        """Check for bearish FVG in last 3 bars.

        Returns (detected, entry_price, gap_size).
        """
        if len(self._bars) < 3:
            return False, 0.0, 0.0

        bar0 = self._bars[-1]
        bar1 = self._bars[-2]
        bar2 = self._bars[-3]

        # Pine: low[2] > high[0] AND low[2] > low[1] AND high[2] > high[0]
        if bar2.low > bar0.high and bar2.low > bar1.low and bar2.high > bar0.high:
            gap_size = bar2.low - bar0.high
            entry = bar0.high  # FVG bottom
            # Must be below ORB low
            if entry < self._orb_low:
                return True, entry, gap_size

        return False, 0.0, 0.0

    def _gap_valid(self, gap_size: float) -> bool:
        """Check if gap size is within ATR-based bounds."""
        if self._daily_atr <= 0:
            return False
        min_gap = (self.min_gap_atr_pct / 100.0) * self._daily_atr
        if gap_size < min_gap:
            return False
        if self.max_gap_atr_pct > 0:
            max_gap = (self.max_gap_atr_pct / 100.0) * self._daily_atr
            if gap_size > max_gap:
                return False
        return True

    # ------------------------------------------------------------------
    # Main bar handler
    # ------------------------------------------------------------------

    async def on_bar(self, bar: Bar, daily_atr: float) -> None:
        """Process a new confirmed 5m bar.

        This is the main entry point called by the feed on each bar close.
        """
        bar_time = bar.timestamp.time()
        date_str = bar.timestamp.strftime("%Y%m%d")

        # Store daily ATR
        self._daily_atr = daily_atr

        # Skip if not in RTH
        if not self._in_rth(bar_time):
            # If we were in a session and left RTH, cancel any pending
            if self._state in (State.ARMED_LONG, State.ARMED_SHORT):
                trade_logger.info(
                    "%s | CANCEL | outside RTH | state=%s",
                    self.name, self._state.value,
                )
                await self.broker.send_cancel()
                self._state = State.FLAT
                self._notify_state_change()
            return

        # New session day detection
        if date_str != self._current_date:
            if self._state in (State.ARMED_LONG, State.ARMED_SHORT):
                await self.broker.send_cancel()
            self._reset_day(date_str)

        # Skip excluded dates
        if self._is_excluded(bar):
            return

        # Add bar to rolling window (keep last 10 for safety)
        self._bars.append(bar)
        if len(self._bars) > 10:
            self._bars.pop(0)
        self._bar_count += 1

        # State machine dispatch
        if self._state == State.IDLE:
            await self._handle_idle(bar, bar_time)
        elif self._state == State.ORB_BUILDING:
            await self._handle_orb_building(bar, bar_time)
        elif self._state == State.SCANNING:
            await self._handle_scanning(bar, bar_time)
        elif self._state in (State.ARMED_LONG, State.ARMED_SHORT):
            await self._handle_armed(bar, bar_time)
        elif self._state in (State.FILLED, State.MANAGING):
            await self._handle_managing(bar, bar_time)
        elif self._state == State.FLAT:
            pass  # done for the day

    # ------------------------------------------------------------------
    # State handlers
    # ------------------------------------------------------------------

    async def _handle_idle(self, bar: Bar, bar_time: time) -> None:
        """Waiting for ORB window to start."""
        if self._in_orb(bar_time):
            self._state = State.ORB_BUILDING
            self._orb_high = bar.high
            self._orb_low = bar.low
            logger.info(
                "[%s] ORB building started: high=%.2f low=%.2f",
                self.name, bar.high, bar.low,
            )
            self._notify_state_change()

    async def _handle_orb_building(self, bar: Bar, bar_time: time) -> None:
        """Accumulating ORB high/low."""
        if self._in_orb(bar_time):
            if bar.high > self._orb_high:
                self._orb_high = bar.high
            if bar.low < self._orb_low:
                self._orb_low = bar.low
        else:
            # ORB window closed — ready to scan
            self._state = State.SCANNING
            trade_logger.info(
                "%s | ORB_READY | high=%.2f low=%.2f range=%.2f atr=%.2f",
                self.name, self._orb_high, self._orb_low,
                self._orb_high - self._orb_low, self._daily_atr,
            )
            self._notify_state_change()

    async def _handle_scanning(self, bar: Bar, bar_time: time) -> None:
        """Scanning for first FVG in entry window."""
        if not self._in_entry(bar_time):
            # Past entry window — cancel and go flat
            trade_logger.info(
                "%s | NO_SETUP | entry window closed",
                self.name,
            )
            self._state = State.FLAT
            self._notify_state_change()
            return

        # Check for long FVG (first one only)
        if not self._long_fvg_found:
            detected, entry, gap_size = self._check_long_fvg()
            if detected and self._gap_valid(gap_size):
                self._long_fvg_found = True
                levels = compute_trade_levels(
                    entry=entry,
                    direction=1,
                    gap_size=gap_size,
                    daily_atr=self._daily_atr,
                    stop_atr_pct=self.stop_atr_pct,
                    rr=self.rr,
                    tp1_ratio=self.tp1_ratio,
                    risk_usd=self.risk_usd,
                    point_value=self.point_value,
                    min_qty=self.min_qty,
                    qty_step=self.qty_step,
                    be_offset_ticks=self.be_offset_ticks,
                    min_tick=self.min_tick,
                )
                if levels is not None:
                    self._levels = levels
                    self._state = State.ARMED_LONG
                    trade_logger.info(
                        "%s | LONG_SETUP | entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f "
                        "qty=%.1f gap=%.2f atr=%.2f",
                        self.name, levels.entry, levels.stop, levels.tp1,
                        levels.tp2, levels.qty, gap_size, self._daily_atr,
                    )
                    self._notify_state_change()
                    await self.broker.send_entry(
                        action="buy",
                        qty=levels.qty,
                        price=levels.entry,
                        tp2=levels.tp2,
                        stop=levels.stop,
                    )
                    return

        # Check for short FVG (first one only)
        if not self._short_fvg_found:
            detected, entry, gap_size = self._check_short_fvg()
            if detected and self._gap_valid(gap_size):
                self._short_fvg_found = True
                levels = compute_trade_levels(
                    entry=entry,
                    direction=-1,
                    gap_size=gap_size,
                    daily_atr=self._daily_atr,
                    stop_atr_pct=self.stop_atr_pct,
                    rr=self.rr,
                    tp1_ratio=self.tp1_ratio,
                    risk_usd=self.risk_usd,
                    point_value=self.point_value,
                    min_qty=self.min_qty,
                    qty_step=self.qty_step,
                    be_offset_ticks=self.be_offset_ticks,
                    min_tick=self.min_tick,
                )
                if levels is not None:
                    self._levels = levels
                    self._state = State.ARMED_SHORT
                    trade_logger.info(
                        "%s | SHORT_SETUP | entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f "
                        "qty=%.1f gap=%.2f atr=%.2f",
                        self.name, levels.entry, levels.stop, levels.tp1,
                        levels.tp2, levels.qty, gap_size, self._daily_atr,
                    )
                    self._notify_state_change()
                    await self.broker.send_entry(
                        action="sell",
                        qty=levels.qty,
                        price=levels.entry,
                        tp2=levels.tp2,
                        stop=levels.stop,
                    )
                    return

    async def _handle_armed(self, bar: Bar, bar_time: time) -> None:
        """Limit order placed, waiting for fill or cancellation."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            return

        # Cancel if past entry window
        if not self._in_entry(bar_time):
            trade_logger.info(
                "%s | CANCEL | entry window expired | entry=%.2f",
                self.name, levels.entry,
            )
            await self.broker.send_cancel()
            self._state = State.FLAT
            self._notify_state_change()
            return

        # Check for fill: did price touch our limit entry?
        filled = False
        if self._state == State.ARMED_LONG and bar.low <= levels.entry:
            filled = True
        elif self._state == State.ARMED_SHORT and bar.high >= levels.entry:
            filled = True

        if filled:
            self._fill_bar_idx = self._bar_count
            self._fill_timestamp = bar.timestamp
            trade_logger.info(
                "%s | FILLED | dir=%s entry=%.2f bar_time=%s",
                self.name,
                "long" if levels.direction == 1 else "short",
                levels.entry,
                bar.timestamp,
            )
            # Immediately transition to managing — but don't check exits on fill bar
            self._state = State.MANAGING
            self._notify_state_change()

    async def _handle_managing(self, bar: Bar, bar_time: time) -> None:
        """Position open — manage TP1/TP2/SL/BE/EOD."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            return

        direction_str = "long" if levels.direction == 1 else "short"

        # EOD flat check (takes priority)
        if self._in_flat(bar):
            trade_logger.info(
                "%s | EOD_FLAT | dir=%s bar_time=%s",
                self.name, direction_str, bar.timestamp,
            )
            await self.broker.send_flatten()
            self._state = State.FLAT
            self._notify_state_change()
            return

        # Gate: don't check exits on the fill bar itself (same-bar prevention)
        if self._bar_count <= self._fill_bar_idx:
            return

        is_long = levels.direction == 1

        # Check stop loss (before TP1 — conservative)
        sl_hit = False
        if is_long and bar.low <= levels.stop:
            sl_hit = True
        elif not is_long and bar.high >= levels.stop:
            sl_hit = True

        if sl_hit and not self._tp1_hit:
            trade_logger.info(
                "%s | SL_HIT | dir=%s stop=%.2f bar_time=%s",
                self.name, direction_str, levels.stop, bar.timestamp,
            )
            # Broker bracket handles this — but send flatten to be safe
            await self.broker.send_flatten()
            self._state = State.FLAT
            self._notify_state_change()
            return

        # Check TP1
        tp1_touched = False
        if is_long and bar.high >= levels.tp1:
            tp1_touched = True
        elif not is_long and bar.low <= levels.tp1:
            tp1_touched = True

        if tp1_touched and not self._tp1_hit:
            self._tp1_hit = True

            if levels.is_single_contract:
                # Single contract: just move stop to BE
                trade_logger.info(
                    "%s | TP1_BE_SINGLE | dir=%s tp1=%.2f be=%.2f bar_time=%s",
                    self.name, direction_str, levels.tp1, levels.be, bar.timestamp,
                )
                await self.broker.send_tp1_single(
                    direction=direction_str,
                    qty=levels.qty,
                    be_price=levels.be,
                )
            else:
                # Multi contract: partial exit + BE stop + TP2 limit
                trade_logger.info(
                    "%s | TP1_PARTIAL | dir=%s tp1=%.2f half_qty=%.1f be=%.2f tp2=%.2f bar_time=%s",
                    self.name, direction_str, levels.tp1, levels.half_qty,
                    levels.be, levels.tp2, bar.timestamp,
                )
                await self.broker.send_tp1_multi(
                    direction=direction_str,
                    half_qty=levels.half_qty,
                    be_price=levels.be,
                    tp2=levels.tp2,
                )

            # After TP1, the stop is now BE — update for subsequent SL checks
            # We don't mutate frozen TradeLevels, so just check against be going forward
            self._notify_state_change()
            return

        # After TP1, check BE stop and TP2
        if self._tp1_hit:
            # BE stop hit?
            be_hit = False
            if is_long and bar.low <= levels.be:
                be_hit = True
            elif not is_long and bar.high >= levels.be:
                be_hit = True

            if be_hit:
                trade_logger.info(
                    "%s | BE_HIT | dir=%s be=%.2f bar_time=%s",
                    self.name, direction_str, levels.be, bar.timestamp,
                )
                # Broker bracket handles BE — flatten to be safe
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

            # TP2 hit?
            tp2_hit = False
            if is_long and bar.high >= levels.tp2:
                tp2_hit = True
            elif not is_long and bar.low <= levels.tp2:
                tp2_hit = True

            if tp2_hit:
                trade_logger.info(
                    "%s | TP2_HIT | dir=%s tp2=%.2f bar_time=%s",
                    self.name, direction_str, levels.tp2, bar.timestamp,
                )
                # Broker bracket handles TP2 — flatten to be safe
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return
        else:
            # Before TP1: check if full TP2 hit (skipped TP1)
            tp2_hit = False
            if is_long and bar.high >= levels.tp2:
                tp2_hit = True
            elif not is_long and bar.low <= levels.tp2:
                tp2_hit = True

            if tp2_hit:
                trade_logger.info(
                    "%s | TP2_DIRECT | dir=%s tp2=%.2f bar_time=%s",
                    self.name, direction_str, levels.tp2, bar.timestamp,
                )
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # 1-second tick handlers (fill detection + exit management)
    # ------------------------------------------------------------------

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        """Process a 1-second bar for fill detection and exit management.

        Only acts in ARMED_* and MANAGING states.  All other states
        (IDLE, ORB_BUILDING, SCANNING, FLAT) ignore ticks entirely.
        """
        self._daily_atr = daily_atr

        if self._state in (State.ARMED_LONG, State.ARMED_SHORT):
            await self._handle_armed_tick(tick)
        elif self._state in (State.FILLED, State.MANAGING):
            await self._handle_managing_tick(tick)

    async def _handle_armed_tick(self, tick: Bar) -> None:
        """Detect limit order fill on 1s bars."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            return

        tick_time = tick.timestamp.time()

        # Cancel if past entry window
        if not self._in_entry(tick_time):
            trade_logger.info(
                "%s | CANCEL | entry window expired (1s) | entry=%.2f",
                self.name, levels.entry,
            )
            await self.broker.send_cancel()
            self._state = State.FLAT
            self._notify_state_change()
            return

        # Check fill
        filled = False
        if self._state == State.ARMED_LONG and tick.low <= levels.entry:
            filled = True
        elif self._state == State.ARMED_SHORT and tick.high >= levels.entry:
            filled = True

        if filled:
            self._fill_timestamp = tick.timestamp
            self._fill_bar_idx = self._bar_count  # keep 5m fallback guard in sync
            self._state = State.MANAGING
            trade_logger.info(
                "%s | FILLED | dir=%s entry=%.2f tick_time=%s",
                self.name,
                "long" if levels.direction == 1 else "short",
                levels.entry,
                tick.timestamp,
            )
            self._notify_state_change()

    async def _handle_managing_tick(self, tick: Bar) -> None:
        """Manage position exits at 1s resolution.

        Checks TP1/SL/BE/TP2/EOD on each 1-second bar.  When TP1 and SL
        both trigger on the same 1s bar, SL wins (pessimistic — matches
        the backtester's finest-tier conflict resolution).
        """
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            return

        direction_str = "long" if levels.direction == 1 else "short"

        # EOD flat check (highest priority)
        if self._in_flat(tick):
            trade_logger.info(
                "%s | EOD_FLAT | dir=%s tick_time=%s",
                self.name, direction_str, tick.timestamp,
            )
            await self.broker.send_flatten()
            self._state = State.FLAT
            self._notify_state_change()
            return

        # Same-tick guard: skip the fill tick itself
        if self._fill_timestamp is not None and tick.timestamp <= self._fill_timestamp:
            return

        is_long = levels.direction == 1

        # --- Pre-TP1 phase ---
        if not self._tp1_hit:
            sl_hit = (is_long and tick.low <= levels.stop) or \
                     (not is_long and tick.high >= levels.stop)
            tp1_touched = (is_long and tick.high >= levels.tp1) or \
                          (not is_long and tick.low <= levels.tp1)

            # Both on same 1s bar — pessimistic: SL wins (matches backtester)
            if sl_hit and tp1_touched:
                trade_logger.info(
                    "%s | SL_HIT | dir=%s stop=%.2f (1s ambiguous, pessimistic) tick_time=%s",
                    self.name, direction_str, levels.stop, tick.timestamp,
                )
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

            if sl_hit:
                trade_logger.info(
                    "%s | SL_HIT | dir=%s stop=%.2f tick_time=%s",
                    self.name, direction_str, levels.stop, tick.timestamp,
                )
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

            if tp1_touched:
                self._tp1_hit = True
                if levels.is_single_contract:
                    trade_logger.info(
                        "%s | TP1_BE_SINGLE | dir=%s tp1=%.2f be=%.2f tick_time=%s",
                        self.name, direction_str, levels.tp1, levels.be,
                        tick.timestamp,
                    )
                    await self.broker.send_tp1_single(
                        direction=direction_str,
                        qty=levels.qty,
                        be_price=levels.be,
                    )
                else:
                    trade_logger.info(
                        "%s | TP1_PARTIAL | dir=%s tp1=%.2f half_qty=%.1f "
                        "be=%.2f tp2=%.2f tick_time=%s",
                        self.name, direction_str, levels.tp1, levels.half_qty,
                        levels.be, levels.tp2, tick.timestamp,
                    )
                    await self.broker.send_tp1_multi(
                        direction=direction_str,
                        half_qty=levels.half_qty,
                        be_price=levels.be,
                        tp2=levels.tp2,
                    )
                self._notify_state_change()
                return

            # Check for direct TP2 (skipping TP1)
            tp2_hit = (is_long and tick.high >= levels.tp2) or \
                      (not is_long and tick.low <= levels.tp2)
            if tp2_hit:
                trade_logger.info(
                    "%s | TP2_DIRECT | dir=%s tp2=%.2f tick_time=%s",
                    self.name, direction_str, levels.tp2, tick.timestamp,
                )
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

        # --- Post-TP1 phase: check BE and TP2 ---
        else:
            be_hit = (is_long and tick.low <= levels.be) or \
                     (not is_long and tick.high >= levels.be)
            tp2_hit = (is_long and tick.high >= levels.tp2) or \
                      (not is_long and tick.low <= levels.tp2)

            if be_hit:
                trade_logger.info(
                    "%s | BE_HIT | dir=%s be=%.2f tick_time=%s",
                    self.name, direction_str, levels.be, tick.timestamp,
                )
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

            if tp2_hit:
                trade_logger.info(
                    "%s | TP2_HIT | dir=%s tp2=%.2f tick_time=%s",
                    self.name, direction_str, levels.tp2, tick.timestamp,
                )
                await self.broker.send_flatten()
                self._state = State.FLAT
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # Public status
    # ------------------------------------------------------------------

    @property
    def state(self) -> State:
        return self._state

    @property
    def is_active(self) -> bool:
        """True if in a state that requires monitoring (not IDLE/FLAT)."""
        return self._state not in (State.IDLE, State.FLAT)

    def status_dict(self) -> dict:
        """Return current state as a dict for logging/debugging."""
        return {
            "session": self.name,
            "state": self._state.value,
            "date": self._current_date,
            "orb_high": self._orb_high if self._orb_high == self._orb_high else None,
            "orb_low": self._orb_low if self._orb_low == self._orb_low else None,
            "daily_atr": self._daily_atr,
            "levels": {
                "entry": self._levels.entry,
                "stop": self._levels.stop,
                "tp1": self._levels.tp1,
                "tp2": self._levels.tp2,
                "qty": self._levels.qty,
                "direction": self._levels.direction,
            } if self._levels else None,
            "tp1_hit": self._tp1_hit,
            "fill_timestamp": str(self._fill_timestamp) if self._fill_timestamp else None,
        }
