"""Session state machine for live trade management.

Each ORBEngine tracks one trading session through its daily lifecycle:
ORB building → waiting for gap → order placement → position management.

Supports the 5-leg combined longs portfolio:
  NQ NY R11, NQ Asia R9, GC NY R3, ES NY Final, ES Asia Final

State machine:
    IDLE → ORB_BUILDING → WAITING_FOR_GAP → ARMED_LIMIT → FILLED → MANAGING → FLAT → IDLE
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Callable

from .position_limits import ContractCapManager, resize_trade_levels
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


@dataclass
class TradeRecord:
    """Completed trade record for cross-session history (e.g. G5 gate)."""

    session: str          # e.g. "NQ_Asia", "ES_Asia", "NQ_LDN"
    date: str             # YYYYMMDD (session start date)
    direction: int        # +1 long, -1 short
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    exit_type: str        # sl, tp1_partial, tp1_be, tp1_eod, tp2, tp2_direct, eod, cancelled
    tp1_hit: bool         # critical for G5 gate
    timestamp: str        # ISO format exit timestamp
    config_name: str = "" # execution config (e.g. "FAST", "SLOW")
    r_result: float | None = None


# ---------------------------------------------------------------------------
# State enum
# ---------------------------------------------------------------------------

class State(enum.Enum):
    IDLE = "idle"
    ORB_BUILDING = "orb_building"
    WAITING_FOR_GAP = "waiting_for_gap"
    ARMED_LIMIT = "armed_limit"
    FILLED = "filled"
    MANAGING = "managing"
    FLAT = "flat"


# ---------------------------------------------------------------------------
# FOMC dates (GC exclusion) — update annually
# ---------------------------------------------------------------------------

FOMC_DATES: frozenset[str] = frozenset([
    "20160127", "20160316", "20160427", "20160615", "20160727", "20160921", "20161102", "20161214",
    "20170201", "20170315", "20170503", "20170614", "20170726", "20170920", "20171101", "20171213",
    "20180131", "20180321", "20180502", "20180613", "20180801", "20180926", "20181108", "20181219",
    "20190130", "20190320", "20190501", "20190619", "20190731", "20190918", "20191030", "20191211",
    "20200129", "20200311", "20200429", "20200610", "20200729", "20200916", "20201105", "20201216",
    "20210127", "20210317", "20210428", "20210616", "20210728", "20210922", "20211103", "20211215",
    "20220126", "20220316", "20220504", "20220615", "20220727", "20220921", "20221102", "20221214",
    "20230201", "20230322", "20230503", "20230614", "20230726", "20230920", "20231101", "20231213",
    "20240131", "20240320", "20240501", "20240612", "20240731", "20240918", "20241107", "20241218",
    "20250129", "20250319", "20250507", "20250618", "20250730", "20250917", "20251029", "20251210",
    "20260128", "20260318", "20260429", "20260610", "20260729", "20260916", "20261104", "20261216",
])


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
class ORBEngine:
    """Manages one session's daily trade lifecycle.

    Args:
        name: Session name (e.g. "NQ_NY", "NQ_Asia", "GC_NY", "ES_NY", "ES_Asia").
        broker: TradersPost webhook client.
        orb_start: ORB window start (HH:MM).
        orb_end: ORB window end (HH:MM).
        entry_start: Entry window start (HH:MM).
        entry_end: Entry window end (HH:MM).
        flat_start: Flat/EOD window start (HH:MM).
        flat_end: Flat/EOD window end (HH:MM).
        stop_atr_pct: Stop distance as % of daily ATR (ATR-based stops).
        stop_basis: "atr" or "orb" — how to compute stop distance.
        stop_orb_pct: Stop distance as % of ORB range (ORB-based stops).
        min_gap_atr_pct: Min FVG gap as % of daily ATR (0 = use ORB-based).
        max_gap_atr_pct: Max FVG gap as % of daily ATR (0 = no limit).
        min_gap_orb_pct: Min FVG gap as % of ORB range (for ORB-based gap filter).
        gap_filter_basis: "atr" or "orb" — how to filter gap size.
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
        excluded_dow: Day-of-week to exclude (0=Mon..6=Sun). None = no exclusion.
        fomc_exclusion: If True, skip FOMC meeting days.
        icf_enabled: If True, use impulse close filter (relaxed ORB check).
        min_stop_pts: Minimum stop distance in points (dual floor, ES only).
        min_tp1_pts: Minimum TP1 distance in points (dual floor, ES only).
        long_only: If True, only take long setups (no short FVG detection).
    """

    name: str
    broker: TradersPostClient
    exec_ticker: str  # Execution instrument ticker (e.g. "MNQ", "MES", "MGC")

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
    atr_length: int = 14

    # Stop basis: "atr" or "orb"
    stop_basis: str = "atr"
    stop_orb_pct: float = 0.0

    # Gap filter basis: "atr" or "orb"
    gap_filter_basis: str = "atr"
    min_gap_orb_pct: float = 0.0

    # Dual floor (ES only)
    min_stop_pts: float = 0.0
    min_tp1_pts: float = 0.0

    # Single-contract risk cap: if 1 contract > risk_usd, allow up to this max
    max_single_risk_usd: float = 500.0

    # Direction filter
    long_only: bool = True

    # ICF (impulse close filter) — GC only
    icf_enabled: bool = False

    # Day-of-week exclusion (0=Mon..6=Sun, None=no exclusion)
    excluded_dow: int | list[int] | None = None

    # FOMC exclusion (GC only)
    fomc_exclusion: bool = False

    # Date filters
    excluded_dates: tuple[str, ...] = ()
    half_days: tuple[str, ...] = ()
    half_day_flat_start: str = "12:50"
    half_day_flat_end: str = "13:00"

    # Execution config name (e.g. "FAST", "SLOW")
    config_name: str = ""

    # Fill detection mode
    allow_5m_fill_detection: bool = True

    # Per-leg pause: when True, all broker.send_*() calls are suppressed
    paused: bool = False

    # Optional callback for dashboard state change notifications
    on_state_change: Callable[[dict], None] | None = None
    # Optional callback for recording completed trades (G5 gate, history)
    on_trade_exit: Callable[[TradeRecord], None] | None = None
    # G5 gate: callback returns True if session should be skipped for a date
    g5_gate_check: Callable[[str], bool] | None = None
    # Optional callback to request a state checkpoint to disk (crash recovery)
    on_checkpoint: Callable[[], None] | None = None
    # Optional per-config position cap manager
    position_manager: ContractCapManager | None = None
    position_limit_key: str = ""

    # Internal state (reset daily)
    _state: State = field(default=State.IDLE, init=False)
    _orb_high: float = field(default=float("nan"), init=False)
    _orb_low: float = field(default=float("nan"), init=False)
    _bars: list[Bar] = field(default_factory=list, init=False)  # rolling window
    _levels: TradeLevels | None = field(default=None, init=False)
    _tp1_hit: bool = field(default=False, init=False)
    _tp1_bar_count: int = field(default=-1, init=False)  # _bar_count when TP1 hit (1s)
    _fill_bar_idx: int = field(default=-1, init=False)
    _fill_timestamp: datetime | None = field(default=None, init=False)
    _fill_via_tick: bool = field(default=False, init=False)
    _bar_count: int = field(default=0, init=False)
    _long_fvg_found: bool = field(default=False, init=False)
    _short_fvg_found: bool = field(default=False, init=False)
    _current_date: str = field(default="", init=False)
    _daily_atr: float = field(default=0.0, init=False)
    _asset_tag: str = field(default="", init=False)
    _exit_type: str | None = field(default=None, init=False)
    _r_result: float | None = field(default=None, init=False)

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
        self._asset_tag = self._resolve_asset_tag()

    @property
    def _should_send(self) -> bool:
        """Whether this engine should send broker payloads."""
        return not self.paused

    def _resolve_asset_tag(self) -> str:
        """resolve canonical asset tag for trade logs."""
        prefix = self.name.split("_", maxsplit=1)[0].upper()
        if prefix in {"NQ", "ES", "GC"}:
            return prefix.lower()

        ticker_map = {
            "NQ": "nq",
            "MNQ": "nq",
            "ES": "es",
            "MES": "es",
            "GC": "gc",
            "MGC": "gc",
        }
        return ticker_map.get(self.exec_ticker.upper(), self.exec_ticker.lower())

    def _request_checkpoint(self) -> None:
        """Request a state checkpoint to disk for crash recovery."""
        if self.on_checkpoint is not None:
            self.on_checkpoint()

    def _position_cap_key(self) -> str:
        return self.position_limit_key or f"{self.config_name or 'DEFAULT'}:{self.name}"

    def _apply_position_cap(self, levels: TradeLevels) -> TradeLevels | None:
        """Resize or block a setup based on remaining config-level contract capacity."""
        if self.position_manager is None or not self.position_manager.enabled:
            return levels

        requested_qty = levels.qty
        approved_qty = self.position_manager.reserve(
            self._position_cap_key(),
            requested_qty,
            qty_step=self.qty_step,
            min_qty=self.min_qty,
        )
        if approved_qty <= 0:
            self._log_trade(
                "ENTRY_SKIPPED_CAP",
                "requested_qty=%.1f open_qty=%.1f limit=%.1f"
                % (
                    requested_qty,
                    self.position_manager.total_allocated(),
                    self.position_manager.max_open_contracts,
                ),
            )
            return None
        if approved_qty < requested_qty:
            self._log_trade(
                "ENTRY_QTY_CAPPED",
                "requested_qty=%.1f approved_qty=%.1f open_qty=%.1f limit=%.1f"
                % (
                    requested_qty,
                    approved_qty,
                    self.position_manager.total_allocated(),
                    self.position_manager.max_open_contracts,
                ),
            )
            return resize_trade_levels(
                levels,
                approved_qty,
                min_qty=self.min_qty,
                qty_step=self.qty_step,
            )
        return levels

    def _remaining_position_qty(self) -> float:
        levels = self._levels
        if levels is None:
            return 0.0
        if self._tp1_hit and not levels.is_single_contract:
            return max(0.0, levels.qty - levels.half_qty)
        return levels.qty

    def _sync_position_cap(self) -> None:
        if self.position_manager is None or not self.position_manager.enabled:
            return
        self.position_manager.adjust(self._position_cap_key(), self._remaining_position_qty())

    def _release_position_cap(self) -> None:
        if self.position_manager is None or not self.position_manager.enabled:
            return
        self.position_manager.release(self._position_cap_key())

    def _log_trade(self, event: str, details: str = "") -> None:
        """emit trade log with config + asset + session tags."""
        cfg = self.config_name or "DEFAULT"
        if details:
            trade_logger.info(
                "%s | %s | %s | %s | %s",
                cfg,
                self._asset_tag,
                self.name,
                event,
                details,
            )
            return
        trade_logger.info("%s | %s | %s | %s", cfg, self._asset_tag, self.name, event)

    def _notify_state_change(self) -> None:
        """Notify dashboard of a state transition."""
        if self.on_state_change is not None:
            self.on_state_change(self.status_dict())

    def _emit_trade_record(self, exit_type: str, exit_price: float | None = None) -> None:
        """Record a completed trade for cross-session history (G5 gate etc.)."""
        self._exit_type = exit_type
        self._r_result = self._compute_r_result(exit_type, exit_price=exit_price)
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
            r_result=self._r_result,
        )
        self.on_trade_exit(record)

    def _price_to_r(self, exit_price: float) -> float:
        """Convert an exit price into an R-multiple using the active trade risk."""
        levels = self._levels
        if levels is None:
            return 0.0
        risk_pts = abs(levels.entry - levels.stop)
        if risk_pts <= 0:
            return 0.0
        pnl_pts = exit_price - levels.entry if levels.direction == 1 else levels.entry - exit_price
        return pnl_pts / risk_pts

    def _compute_r_result(self, exit_type: str, exit_price: float | None = None) -> float:
        """Compute realized R-multiple for a trade exit."""
        levels = self._levels
        if levels is None:
            return 0.0

        is_single = levels.is_single_contract
        stop_r = self._price_to_r(levels.stop)
        tp1_r = self._price_to_r(levels.tp1)
        tp2_r = self._price_to_r(levels.tp2)
        be_r = self._price_to_r(levels.be)

        if exit_type == "sl":
            return stop_r
        elif exit_type == "tp1_be":
            return be_r if is_single else (tp1_r + be_r) / 2.0
        elif exit_type == "tp1_tp2":
            return tp2_r if is_single else (tp1_r + tp2_r) / 2.0
        elif exit_type == "tp2_direct":
            return tp2_r
        elif exit_type == "tp1_eod":
            if exit_price is None:
                return be_r if is_single else (tp1_r + be_r) / 2.0
            exit_r = self._price_to_r(exit_price)
            return exit_r if is_single else (tp1_r + exit_r) / 2.0
        elif exit_type == "eod":
            return self._price_to_r(exit_price) if exit_price is not None else 0.0
        return 0.0

    # ------------------------------------------------------------------
    # Time checks
    # ------------------------------------------------------------------

    @property
    def _crosses_midnight(self) -> bool:
        """True if the session's RTH window spans midnight (e.g. Asia sessions)."""
        return self._orb_start_t > self._flat_end_t

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

    def _is_same_session_night(self, date_str: str, bar_time: time) -> bool:
        """Check if a post-midnight bar belongs to the current session night.

        For cross-midnight sessions (e.g. Asia: ORB 20:00, flat 07:00),
        bars between 00:00 and flat_end belong to the session that started
        the previous evening.  Returns True if:
          1. The bar is in the post-midnight portion (bar_time < orb_start)
          2. The bar's date is exactly _current_date + 1 day
        """
        from datetime import datetime as _dt, timedelta as _td

        # Bar is in the pre-midnight portion (at or after ORB start) —
        # this is a NEW session starting, not a continuation.
        if bar_time >= self._orb_start_t:
            return False

        # Check that date_str is exactly _current_date + 1 day
        if not self._current_date:
            return False
        try:
            current = _dt.strptime(self._current_date, "%Y%m%d")
            bar_date = _dt.strptime(date_str, "%Y%m%d")
            return bar_date == current + _td(days=1)
        except ValueError:
            return False

    def _is_excluded(self, bar: Bar) -> bool:
        date_str = bar.timestamp.strftime("%Y%m%d")
        # Static excluded dates
        if date_str in self.excluded_dates:
            return True
        # Day-of-week exclusion (Monday=0 .. Sunday=6)
        if self.excluded_dow is not None:
            dow = bar.timestamp.weekday()
            if isinstance(self.excluded_dow, (list, tuple)):
                if dow in self.excluded_dow:
                    return True
            elif dow == self.excluded_dow:
                return True
        # FOMC exclusion (GC only)
        if self.fomc_exclusion and date_str in FOMC_DATES:
            return True
        return False

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------

    def _reset_day(self, date_str: str, notify: bool = True) -> None:
        """Reset all state for a new trading day."""
        self._release_position_cap()
        self._state = State.IDLE
        self._orb_high = float("nan")
        self._orb_low = float("nan")
        self._bars.clear()
        self._levels = None
        self._tp1_hit = False
        self._tp1_bar_count = -1
        self._fill_bar_idx = -1
        self._fill_timestamp = None
        self._fill_via_tick = False
        self._bar_count = 0
        self._long_fvg_found = False
        self._short_fvg_found = False
        self._exit_type = None
        self._r_result = None
        self._current_date = date_str
        logger.info("[%s] New session day: %s", self.name, date_str)
        if notify:
            self._notify_state_change()
        self._request_checkpoint()

    def _expected_orb_bar_count(self) -> int:
        """How many 5m bars should exist in the full ORB window."""
        from datetime import datetime as _dt, timedelta as _td
        # Build datetime objects on a dummy date to compute the span
        base = _dt(2000, 1, 1)
        start = _dt.combine(base, self._orb_start_t)
        end = _dt.combine(base, self._orb_end_t)
        if end <= start:
            end += _td(days=1)  # cross-midnight
        minutes = (end - start).total_seconds() / 60
        return max(1, int(minutes // 5))

    def recover_opening_range(self, bars: list[Bar], now: datetime) -> bool:
        """recover opening range/state for current day after restart."""
        from datetime import timedelta as _td

        now_t = now.time()

        # For cross-midnight sessions, if we're in the post-midnight
        # portion (time < flat_end), the ORB was built on the *previous*
        # calendar day.  Use that date as the session date so bar
        # filtering picks up the correct ORB bars.
        if self._crosses_midnight and now_t < self._orb_start_t:
            session_date = now - _td(days=1)
            date_str = session_date.strftime("%Y%m%d")
        else:
            date_str = now.strftime("%Y%m%d")

        # reset to a clean day state without broadcasting intermediate idle.
        self._reset_day(date_str, notify=False)

        # excluded dates should remain flat even if history exists.
        now_bar = Bar(timestamp=now, open=0.0, high=0.0, low=0.0, close=0.0, volume=0)
        if self._is_excluded(now_bar):
            self._state = State.FLAT
            self._notify_state_change()
            return False

        # For cross-midnight sessions, session bars span two calendar
        # days: the ORB date (pre-midnight) and the next date (post-midnight).
        if self._crosses_midnight:
            valid_dates = {date_str, (datetime.strptime(date_str, "%Y%m%d") + _td(days=1)).strftime("%Y%m%d")}
            today_bars = [b for b in bars if b.timestamp.strftime("%Y%m%d") in valid_dates]
        else:
            today_bars = [b for b in bars if b.timestamp.strftime("%Y%m%d") == date_str]
        session_bars = [b for b in today_bars if self._in_rth(b.timestamp.time())]
        orb_bars = [b for b in session_bars if self._in_orb(b.timestamp.time())]
        if not orb_bars:
            self._notify_state_change()
            return False

        self._orb_high = max(b.high for b in orb_bars)
        self._orb_low = min(b.low for b in orb_bars)
        self._bars = session_bars[-10:]
        self._bar_count = len(session_bars)

        # Check if the preloaded history fully covers the ORB window.
        # If bars are missing (e.g. due to the DataBento historical delay),
        # stay in ORB_BUILDING so live bars can complete the range.
        expected_orb_bars = self._expected_orb_bar_count()
        orb_complete = len(orb_bars) >= expected_orb_bars

        if self._in_orb(now_t):
            self._state = State.ORB_BUILDING
        elif not orb_complete:
            # Past ORB window but preload missed some bars — stay in
            # ORB_BUILDING so the first live bars can fill the gap.
            self._state = State.ORB_BUILDING
            logger.warning(
                "[%s] ORB incomplete after recovery: got %d/%d bars, "
                "staying in ORB_BUILDING for live completion",
                self.name, len(orb_bars), expected_orb_bars,
            )
        elif self._in_entry(now_t):
            self._state = State.WAITING_FOR_GAP
        elif self._in_flat(now_bar):
            self._state = State.FLAT
        elif self._in_rth(now_t):
            # post-entry/pre-flat should not scan for new setups.
            self._state = State.FLAT
        else:
            self._state = State.IDLE

        logger.info(
            "[%s] OR recovered: high=%.2f low=%.2f range=%.2f state=%s bars=%d/%d",
            self.name,
            self._orb_high,
            self._orb_low,
            self._orb_range,
            self._state.value,
            len(orb_bars),
            expected_orb_bars,
        )
        self._notify_state_change()
        return True

    # ------------------------------------------------------------------
    # ORB range helper
    # ------------------------------------------------------------------

    @property
    def _orb_range(self) -> float:
        """Current ORB range (high - low). Returns 0 if not ready."""
        if self._orb_high != self._orb_high or self._orb_low != self._orb_low:
            return 0.0  # NaN check
        return self._orb_high - self._orb_low

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
        bar1 = self._bars[-2]  # middle (impulse candle)
        bar2 = self._bars[-3]  # oldest (before candle)

        # Pine: high[2] < low[0] AND high[2] < high[1] AND low[2] < low[0]
        if bar2.high < bar0.low and bar2.high < bar1.high and bar2.low < bar0.low:
            gap_size = bar0.low - bar2.high
            entry = bar0.low  # FVG top

            # ORB directional filter
            if self.icf_enabled:
                # ICF-relaxed: FVG top above ORB high OR impulse close above ORB high
                orb_ok = (entry > self._orb_high) or (bar1.close > self._orb_high)
            else:
                # Standard: FVG top must be above ORB high
                orb_ok = entry > self._orb_high

            if orb_ok:
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
        """Check if gap size is within bounds (ATR-based or ORB-based)."""
        if self.gap_filter_basis == "orb":
            orb_range = self._orb_range
            if orb_range <= 0:
                return False
            min_gap = (self.min_gap_orb_pct / 100.0) * orb_range
            return gap_size >= min_gap
        else:
            # ATR-based gap filter
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
            # If we were in an active state and left RTH, go flat
            if self._state not in (State.IDLE, State.FLAT):
                self._release_position_cap()
                if self._state == State.ARMED_LIMIT:
                    self._log_trade("CANCEL", f"outside RTH state={self._state.value}")
                    if self._should_send:
                        await self.broker.send_cancel(ticker=self.exec_ticker)
                else:
                    self._log_trade("NO_SETUP", f"outside RTH state={self._state.value}")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
            return

        # New session day detection
        # For cross-midnight sessions (e.g. Asia: ORB 20:00, flat 07:00),
        # the calendar date changes at midnight while the session is still
        # active.  Post-midnight bars belong to the *previous* session
        # night and must NOT trigger a reset — regardless of engine state.
        if date_str != self._current_date:
            if self._crosses_midnight and self._is_same_session_night(date_str, bar_time):
                # Still the same session night — do NOT reset.
                logger.debug(
                    "[%s] Cross-midnight: skipping reset (same session night) "
                    "date=%s current_date=%s bar_time=%s state=%s",
                    self.name, date_str, self._current_date,
                    bar_time, self._state.value,
                )
            else:
                logger.debug(
                    "[%s] Day reset: %s -> %s bar_time=%s state=%s",
                    self.name, self._current_date, date_str,
                    bar_time, self._state.value,
                )
                if self._state == State.ARMED_LIMIT and self._should_send:
                    await self.broker.send_cancel(ticker=self.exec_ticker)
                self._reset_day(date_str)

        # Skip excluded dates (DOW, FOMC, static dates)
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
        elif self._state == State.WAITING_FOR_GAP:
            await self._handle_scanning(bar, bar_time)
        elif self._state == State.ARMED_LIMIT:
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
            self._request_checkpoint()
            self._orb_high = bar.high
            self._orb_low = bar.low
            logger.info(
                "[%s] ORB building started: high=%.2f low=%.2f",
                self.name, bar.high, bar.low,
            )
            self._notify_state_change()
        elif not self._in_orb(bar_time) and self._orb_range == 0.0:
            # In RTH but past ORB window with no ORB data — missed the
            # session (e.g. service started after ORB closed and recovery
            # did not find historical bars).
            self._log_trade("NO_SETUP", "missed ORB window (late start)")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()

    async def _handle_orb_building(self, bar: Bar, bar_time: time) -> None:
        """Accumulating ORB high/low."""
        if self._in_orb(bar_time):
            if bar.high > self._orb_high:
                self._orb_high = bar.high
            if bar.low < self._orb_low:
                self._orb_low = bar.low
            logger.info(
                "[%s] ORB bar: time=%s H=%.2f L=%.2f | running high=%.2f low=%.2f",
                self.name, bar.timestamp, bar.high, bar.low,
                self._orb_high, self._orb_low,
            )
        else:
            # ORB window closed — check G5 gate before scanning
            if self.g5_gate_check is not None and self.g5_gate_check(self._current_date):
                self._log_trade("G5_GATE_BLOCKED", "date=%s" % self._current_date)
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            # Ready to scan
            self._state = State.WAITING_FOR_GAP
            self._request_checkpoint()
            self._log_trade(
                "ORB_READY",
                "high=%.2f low=%.2f range=%.2f atr=%.2f"
                % (
                    self._orb_high,
                    self._orb_low,
                    self._orb_range,
                    self._daily_atr,
                ),
            )
            self._notify_state_change()
            # The transition bar is already in _bars but never got an FVG
            # check.  Run scanning immediately so an FVG that completes on
            # this bar (e.g. ORB bar[0], ORB bar[1], this bar) is detected.
            await self._handle_scanning(bar, bar_time)

    async def _handle_scanning(self, bar: Bar, bar_time: time) -> None:
        """Scanning for first FVG in entry window (long only)."""
        if not self._in_entry(bar_time):
            # Past entry window — cancel and go flat
            self._log_trade("NO_SETUP", "entry window closed")
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        # Check for long FVG (first one only)
        if not self._long_fvg_found:
            detected, entry, gap_size = self._check_long_fvg()
            if detected:
                if not self._gap_valid(gap_size):
                    logger.debug(
                        "[%s] Long FVG rejected: gap=%.2f invalid size "
                        "bar_time=%s atr=%.2f orb_range=%.2f",
                        self.name, gap_size, bar_time,
                        self._daily_atr, self._orb_range,
                    )
                else:
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
                        stop_basis=self.stop_basis,
                        orb_range=self._orb_range,
                        stop_orb_pct=self.stop_orb_pct,
                        min_stop_pts=self.min_stop_pts,
                        min_tp1_pts=self.min_tp1_pts,
                        max_single_risk_usd=self.max_single_risk_usd,
                    )
                    if levels is not None:
                        levels = self._apply_position_cap(levels)
                    if levels is not None:
                        self._levels = levels
                        self._state = State.ARMED_LIMIT
                        self._request_checkpoint()
                        self._log_trade(
                            "LONG_SETUP",
                            (
                                "entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f "
                                "qty=%.1f gap=%.2f atr=%.2f orb_range=%.2f"
                            )
                            % (
                                levels.entry,
                                levels.stop,
                                levels.tp1,
                                levels.tp2,
                                levels.qty,
                                gap_size,
                                self._daily_atr,
                                self._orb_range,
                            ),
                        )
                        self._notify_state_change()
                        if self._should_send:
                            await self.broker.send_entry(
                                action="buy",
                                qty=levels.qty,
                                price=levels.entry,
                                tp2=levels.tp2,
                                stop=levels.stop,
                                ticker=self.exec_ticker,
                            )
                        return
                    else:
                        logger.debug(
                            "[%s] Long FVG rejected: levels=None "
                            "entry=%.2f gap=%.2f bar_time=%s",
                            self.name, entry, gap_size, bar_time,
                        )
            elif len(self._bars) >= 3:
                logger.debug(
                    "[%s] No long FVG: H=[%.2f,%.2f,%.2f] "
                    "L=[%.2f,%.2f,%.2f] orb_high=%.2f bar_time=%s",
                    self.name,
                    self._bars[-3].high, self._bars[-2].high, self._bars[-1].high,
                    self._bars[-3].low, self._bars[-2].low, self._bars[-1].low,
                    self._orb_high, bar_time,
                )

        # Short FVG check (only if not long_only)
        if not self.long_only and not self._short_fvg_found:
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
                    stop_basis=self.stop_basis,
                    orb_range=self._orb_range,
                    stop_orb_pct=self.stop_orb_pct,
                    min_stop_pts=self.min_stop_pts,
                    min_tp1_pts=self.min_tp1_pts,
                    max_single_risk_usd=self.max_single_risk_usd,
                )
                if levels is not None:
                    levels = self._apply_position_cap(levels)
                if levels is not None:
                    self._levels = levels
                    # Re-use ARMED_LIMIT state for armed short in non-long-only mode
                    # (short not used in 5-leg portfolio but kept for backward compat)
                    self._state = State.ARMED_LIMIT
                    self._request_checkpoint()
                    self._log_trade(
                        "SHORT_SETUP",
                        (
                            "entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f "
                            "qty=%.1f gap=%.2f atr=%.2f"
                        )
                        % (
                            levels.entry,
                            levels.stop,
                            levels.tp1,
                            levels.tp2,
                            levels.qty,
                            gap_size,
                            self._daily_atr,
                        ),
                    )
                    self._notify_state_change()
                    if self._should_send:
                        await self.broker.send_entry(
                            action="sell",
                            qty=levels.qty,
                            price=levels.entry,
                            tp2=levels.tp2,
                            stop=levels.stop,
                            ticker=self.exec_ticker,
                        )
                    return

    async def _handle_armed(self, bar: Bar, bar_time: time) -> None:
        """Limit order placed, waiting for fill or cancellation."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        # Cancel if past entry window
        if not self._in_entry(bar_time):
            self._log_trade(
                "CANCELLED_LIMITS",
                "entry window expired entry=%.2f" % levels.entry,
            )
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_cancel(ticker=self.exec_ticker)
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        if not self.allow_5m_fill_detection:
            return

        # Check for fill: did price touch our limit entry?
        is_long = levels.direction == 1
        filled = False
        if is_long and bar.low <= levels.entry:
            filled = True
        elif not is_long and bar.high >= levels.entry:
            filled = True

        if filled:
            self._fill_bar_idx = self._bar_count
            self._fill_timestamp = bar.timestamp
            self._fill_via_tick = False
            self._log_trade(
                "FILLED",
                "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f bar_time=%s resolution=5m"
                % ("long" if is_long else "short", levels.entry, levels.stop, levels.tp1, levels.tp2, levels.qty, bar.timestamp),
            )
            # Immediately transition to managing — but don't check exits on fill bar
            self._state = State.MANAGING
            self._request_checkpoint()
            self._notify_state_change()

    async def _handle_managing(self, bar: Bar, bar_time: time) -> None:
        """Position open — manage TP1/TP2/SL/BE/EOD."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        direction_str = "long" if levels.direction == 1 else "short"

        # EOD flat check (takes priority)
        if self._in_flat(bar):
            self._log_trade(
                "EOD_FLAT",
                f"dir={direction_str} bar_time={bar.timestamp} resolution=5m",
            )
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_flatten(ticker=self.exec_ticker)
            self._emit_trade_record("tp1_eod" if self._tp1_hit else "eod", exit_price=bar.close)
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        # Gate: don't check exits on the fill bar itself (same-bar prevention)
        if self._bar_count <= self._fill_bar_idx:
            return

        # If the fill happened on a 1s tick, only the 1s path can preserve
        # correct pre-fill/post-fill sequencing for exits.
        if self._fill_via_tick:
            return

        # Gate: skip the 5m bar that contains the TP1 hit.
        # When TP1 is detected on a 1s tick mid-bar, the enclosing 5m bar's
        # low includes pre-TP1 price action near the entry, making
        # bar.low <= BE trivially true and causing a false BE_HIT.
        # The 1s tick path is authoritative for exits on this bar.
        if self._tp1_hit and self._tp1_bar_count >= 0 and self._bar_count <= self._tp1_bar_count:
            return

        is_long = levels.direction == 1

        # Check stop loss (before TP1 — conservative)
        sl_hit = False
        if is_long and bar.low <= levels.stop:
            sl_hit = True
        elif not is_long and bar.high >= levels.stop:
            sl_hit = True

        if sl_hit and not self._tp1_hit:
            self._log_trade(
                "SL_HIT",
                "dir=%s stop=%.2f bar_time=%s resolution=5m"
                % (direction_str, levels.stop, bar.timestamp),
            )
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_flatten(ticker=self.exec_ticker)
            self._emit_trade_record("sl")
            self._state = State.FLAT
            self._request_checkpoint()
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
            self._request_checkpoint()
            self._tp1_bar_count = self._bar_count
            self._sync_position_cap()

            if levels.is_single_contract:
                self._log_trade(
                    "TP1_BE_SINGLE",
                    "dir=%s tp1=%.2f be=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.tp1, levels.be, bar.timestamp),
                )
                if self._should_send:
                    await self.broker.send_tp1_single(
                        direction=direction_str,
                        qty=levels.qty,
                        be_price=levels.be,
                        ticker=self.exec_ticker,
                    )
            else:
                self._log_trade(
                    "TP1_PARTIAL",
                    "dir=%s tp1=%.2f half_qty=%.1f be=%.2f tp2=%.2f bar_time=%s resolution=5m"
                    % (
                        direction_str,
                        levels.tp1,
                        levels.half_qty,
                        levels.be,
                        levels.tp2,
                        bar.timestamp,
                    ),
                )
                if self._should_send:
                    await self.broker.send_tp1_multi(
                        direction=direction_str,
                        half_qty=levels.half_qty,
                        be_price=levels.be,
                        tp2=levels.tp2,
                        ticker=self.exec_ticker,
                    )

            self._notify_state_change()
            return

        # After TP1, check BE stop and TP2
        if self._tp1_hit:
            be_hit = False
            if is_long and bar.low <= levels.be:
                be_hit = True
            elif not is_long and bar.high >= levels.be:
                be_hit = True

            if be_hit:
                self._log_trade(
                    "BE_HIT",
                    "dir=%s be=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.be, bar.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp1_be")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            tp2_hit = False
            if is_long and bar.high >= levels.tp2:
                tp2_hit = True
            elif not is_long and bar.low <= levels.tp2:
                tp2_hit = True

            if tp2_hit:
                self._log_trade(
                    "TP2_HIT",
                    "dir=%s tp2=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.tp2, bar.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp1_tp2")
                self._state = State.FLAT
                self._request_checkpoint()
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
                self._log_trade(
                    "TP2_DIRECT",
                    "dir=%s tp2=%.2f bar_time=%s resolution=5m"
                    % (direction_str, levels.tp2, bar.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp2_direct")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # 1-second tick handlers (fill detection + exit management)
    # ------------------------------------------------------------------

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        """Process a 1-second bar for fill detection and exit management.

        Only acts in ARMED_LIMIT and MANAGING states. All other states
        (IDLE, ORB_BUILDING, WAITING_FOR_GAP, FLAT) ignore ticks entirely.
        """
        self._daily_atr = daily_atr

        if self._state == State.ARMED_LIMIT:
            await self._handle_armed_tick(tick)
        elif self._state in (State.FILLED, State.MANAGING):
            await self._handle_managing_tick(tick)

    async def _handle_armed_tick(self, tick: Bar) -> None:
        """Detect limit order fill on 1s bars."""
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        tick_time = tick.timestamp.time()

        # Cancel if past entry window
        if not self._in_entry(tick_time):
            self._log_trade(
                "CANCELLED_LIMITS",
                "entry window expired (1s) entry=%.2f" % levels.entry,
            )
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_cancel(ticker=self.exec_ticker)
            self._state = State.FLAT
            self._request_checkpoint()
            self._notify_state_change()
            return

        # Check fill
        is_long = levels.direction == 1
        filled = False
        if is_long and tick.low <= levels.entry:
            filled = True
        elif not is_long and tick.high >= levels.entry:
            filled = True

        if filled:
            self._fill_timestamp = tick.timestamp
            self._fill_bar_idx = self._bar_count
            self._fill_via_tick = True
            self._state = State.MANAGING
            self._request_checkpoint()
            self._log_trade(
                "FILLED",
                "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f tick_time=%s resolution=1s"
                % ("long" if is_long else "short", levels.entry, levels.stop, levels.tp1, levels.tp2, levels.qty, tick.timestamp),
            )
            self._notify_state_change()

    async def _handle_managing_tick(self, tick: Bar) -> None:
        """Manage position exits at 1s resolution.

        Checks TP1/SL/BE/TP2/EOD on each 1-second bar. When TP1 and SL
        both trigger on the same 1s bar, SL wins (pessimistic — matches
        the backtester's finest-tier conflict resolution).
        """
        levels = self._levels
        if levels is None:
            self._state = State.FLAT
            self._request_checkpoint()
            return

        direction_str = "long" if levels.direction == 1 else "short"

        # EOD flat check (highest priority)
        if self._in_flat(tick):
            self._log_trade(
                "EOD_FLAT",
                f"dir={direction_str} tick_time={tick.timestamp} resolution=1s",
            )
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_flatten(ticker=self.exec_ticker)
            self._emit_trade_record("tp1_eod" if self._tp1_hit else "eod", exit_price=tick.close)
            self._state = State.FLAT
            self._request_checkpoint()
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
                self._log_trade(
                    "SL_HIT",
                    "dir=%s stop=%.2f (1s ambiguous, pessimistic) tick_time=%s resolution=1s"
                    % (direction_str, levels.stop, tick.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("sl")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            if sl_hit:
                self._log_trade(
                    "SL_HIT",
                    "dir=%s stop=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.stop, tick.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("sl")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            if tp1_touched:
                self._tp1_hit = True
                self._request_checkpoint()
                self._tp1_bar_count = self._bar_count
                self._sync_position_cap()
                if levels.is_single_contract:
                    self._log_trade(
                        "TP1_BE_SINGLE",
                        "dir=%s tp1=%.2f be=%.2f tick_time=%s resolution=1s"
                        % (direction_str, levels.tp1, levels.be, tick.timestamp),
                    )
                    if self._should_send:
                        await self.broker.send_tp1_single(
                            direction=direction_str,
                            qty=levels.qty,
                            be_price=levels.be,
                            ticker=self.exec_ticker,
                        )
                else:
                    self._log_trade(
                        "TP1_PARTIAL",
                        "dir=%s tp1=%.2f half_qty=%.1f be=%.2f tp2=%.2f tick_time=%s resolution=1s"
                        % (
                            direction_str,
                            levels.tp1,
                            levels.half_qty,
                            levels.be,
                            levels.tp2,
                            tick.timestamp,
                        ),
                    )
                    if self._should_send:
                        await self.broker.send_tp1_multi(
                            direction=direction_str,
                            half_qty=levels.half_qty,
                            be_price=levels.be,
                            tp2=levels.tp2,
                            ticker=self.exec_ticker,
                        )
                self._notify_state_change()
                return

            # Check for direct TP2 (skipping TP1)
            tp2_hit = (is_long and tick.high >= levels.tp2) or \
                      (not is_long and tick.low <= levels.tp2)
            if tp2_hit:
                self._log_trade(
                    "TP2_DIRECT",
                    "dir=%s tp2=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.tp2, tick.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp2_direct")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

        # --- Post-TP1 phase: check BE and TP2 ---
        else:
            be_hit = (is_long and tick.low <= levels.be) or \
                     (not is_long and tick.high >= levels.be)
            tp2_hit = (is_long and tick.high >= levels.tp2) or \
                      (not is_long and tick.low <= levels.tp2)

            if be_hit:
                self._log_trade(
                    "BE_HIT",
                    "dir=%s be=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.be, tick.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp1_be")
                self._state = State.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            if tp2_hit:
                self._log_trade(
                    "TP2_HIT",
                    "dir=%s tp2=%.2f tick_time=%s resolution=1s"
                    % (direction_str, levels.tp2, tick.timestamp),
                )
                self._release_position_cap()
                if self._should_send:
                    await self.broker.send_flatten(ticker=self.exec_ticker)
                self._emit_trade_record("tp1_tp2")
                self._state = State.FLAT
                self._request_checkpoint()
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
            "config_name": self.config_name,
            "session": self.name,
            "state": self._state.value,
            "date": self._current_date,
            "orb_high": self._orb_high if self._orb_high == self._orb_high else None,
            "orb_low": self._orb_low if self._orb_low == self._orb_low else None,
            "orb_range": self._orb_range if self._orb_range > 0 else None,
            "daily_atr": self._daily_atr,
            "atr_length": self.atr_length,
            "levels": {
                "entry": self._levels.entry,
                "stop": self._levels.stop,
                "tp1": self._levels.tp1,
                "tp2": self._levels.tp2,
                "qty": self._levels.qty,
                "direction": self._levels.direction,
            } if self._levels else None,
            "tp1_hit": self._tp1_hit,
            "exit_type": self._exit_type,
            "r_result": round(self._r_result, 2) if self._r_result is not None else None,
            "fill_timestamp": str(self._fill_timestamp) if self._fill_timestamp else None,
            "stop_basis": self.stop_basis,
            "long_only": self.long_only,
            "paused": self.paused,
            "excluded_dow": self.excluded_dow,
            "fomc_exclusion": self.fomc_exclusion,
        }
