"""LSI (Inverse Fair Value Gap) engine for live LSI reversal strategy.

State machine:
    IDLE → SCANNING → WAITING_FOR_GAP → COLLECTING_GAPS →
    WAITING_FOR_INVERSION → ARMED_LIMIT → MANAGING → FLAT

Unlike ORBEngine (continuation FVG after ORB), this engine detects:
    1. Liquidity sweep of confirmed swing pivots
    2. Opposite-direction FVG formation near sweep (before or after)
    3. Price-close inversion through the gap
    4. Entry via two modes (matches backtester):
       - "close": enter at inversion bar close
       - "fvg_limit": limit order at FVG boundary, fill on next bar touch
    5. Absolute-range stop (matches backtester stop_mode="absolute")
    6. Position management (SL/TP1/TP2/BE/EOD)

Implements the same on_bar() / on_tick() interface as ORBEngine.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import math
from dataclasses import dataclass
from datetime import datetime, time
from typing import Callable

from .broker import TradersPostClient
from .engine import Bar, TradeRecord
from .htf_levels import HtfLevelTracker
from .position_limits import ContractCapManager, resize_trade_levels
from .sizing import TradeLevels, compute_trade_levels
from .swing import SweepEvent, SwingTracker

logger = logging.getLogger(__name__)
trade_logger = logging.getLogger("trader.trades")

STANDARD_LSI_VARIANT = "standard"
LEGACY_LSI_VARIANT = "legacy-LSI"
HTF_LSI_VARIANT = "htf-LSI"
VALID_LSI_VARIANTS = frozenset({STANDARD_LSI_VARIANT, LEGACY_LSI_VARIANT, HTF_LSI_VARIANT})


class LSIState(enum.Enum):
    IDLE = "idle"
    SCANNING = "scanning"  # in entry window, watching for sweeps
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


class LSIEngine:
    """Live execution engine for the LSI/LSI reversal strategy."""

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
        sweep_start: str | None = None,
        sweep_end: str | None = None,
        # Strategy params
        rr: float = 3.0,
        tp1_ratio: float = 0.3,
        atr_length: int = 14,
        min_gap_atr_pct: float = 5.0,
        min_stop_points: float = 0.0,
        fvg_window_left: int = 10,
        fvg_window_right: int = 5,
        lsi_entry_mode: str = "close",  # "close" or "fvg_limit"
        lsi_variant: str = LEGACY_LSI_VARIANT,
        # Risk params
        risk_usd: float = 250.0,
        point_value: float = 2.0,
        min_qty: float = 1.0,
        qty_step: float = 1.0,
        qty_multiplier: float = 1.0,
        min_tick: float = 0.25,
        max_single_risk_usd: float = 500.0,
        # Direction
        long_only: bool = True,
        # DOW exclusion
        excluded_dow: int | list[int] | None = None,
        regime_gate: str | None = None,
        regime_gates: tuple[str, ...] = (),
        regime_gate_check: Callable[[str], bool] | None = None,
        regime_gate_checks: tuple[tuple[str, Callable[[str], bool]], ...] = (),
        excluded_dates: tuple[str, ...] = (),
        half_days: tuple[str, ...] = (),
        half_day_flat_start: str = "12:50",
        half_day_flat_end: str = "13:00",
        # Swing pivot detection
        lsi_n_left: int = 3,
        lsi_n_right: int = 3,
        htf_level_tf_minutes: int = 60,
        htf_n_left: int = 5,
        htf_trade_max_per_session: int = 1,
        max_fvg_to_inversion_bars: int = 0,
        base_bar_minutes: int = 5,
        # Execution config name
        config_name: str = "",
        post_exit_cleanup_delay_s: float = 6.0,
        post_exit_cancel_settle_delay_s: float = 0.25,
    ) -> None:
        self.name = name
        self.broker = broker
        self.exec_ticker = exec_ticker
        self.config_name = config_name
        self.paused: bool = False
        self.post_exit_cleanup_delay_s = post_exit_cleanup_delay_s
        self.post_exit_cancel_settle_delay_s = post_exit_cancel_settle_delay_s

        # Time windows
        self.entry_start = entry_start
        self.entry_end = entry_end
        self.sweep_start = sweep_start or entry_start
        self.sweep_end = sweep_end or entry_end
        self.flat_start = flat_start
        self.flat_end = flat_end
        self._entry_start_t = _parse_time(entry_start)
        self._entry_end_t = _parse_time(entry_end)
        self._sweep_start_t = _parse_time(self.sweep_start)
        self._sweep_end_t = _parse_time(self.sweep_end)
        self._flat_start_t = _parse_time(flat_start)
        self._flat_end_t = _parse_time(flat_end)

        # Strategy
        self.rr = rr
        self.tp1_ratio = tp1_ratio
        self.atr_length = atr_length
        self.min_gap_atr_pct = min_gap_atr_pct
        self.min_stop_points = min_stop_points
        self.fvg_window_left = fvg_window_left
        self.fvg_window_right = fvg_window_right
        self.lsi_entry_mode = lsi_entry_mode
        if lsi_variant not in VALID_LSI_VARIANTS:
            raise ValueError(
                "lsi_variant must be one of "
                f"{sorted(VALID_LSI_VARIANTS)} (got {lsi_variant!r})"
            )
        self.lsi_variant = lsi_variant
        self.htf_level_tf_minutes = htf_level_tf_minutes
        self.htf_n_left = htf_n_left
        self.htf_trade_max_per_session = htf_trade_max_per_session
        self.max_fvg_to_inversion_bars = max_fvg_to_inversion_bars
        self.base_bar_minutes = base_bar_minutes

        # Risk
        self.risk_usd = risk_usd
        self.point_value = point_value
        self.min_qty = min_qty
        self.qty_step = qty_step
        self.qty_multiplier = qty_multiplier
        self.min_tick = min_tick
        self.max_single_risk_usd = max_single_risk_usd

        # Direction
        self.long_only = long_only
        self.excluded_dow = excluded_dow
        from .gates import normalize_regime_gate_fields
        (
            self.regime_gate,
            self.regime_gates,
            self.regime_gate_check,
            self.regime_gate_checks,
        ) = normalize_regime_gate_fields(
            regime_gate,
            regime_gates,
            regime_gate_check,
            regime_gate_checks,
        )
        self.excluded_dates = excluded_dates
        self.half_days = half_days
        self._half_day_flat_start_t = _parse_time(half_day_flat_start)
        self._half_day_flat_end_t = _parse_time(half_day_flat_end)

        # Swing pivot tracker (replaces KZ/PDH/PDL liquidity tracking)
        self._swings = SwingTracker(n_left=lsi_n_left, n_right=lsi_n_right, long_only=long_only)
        self._htf_levels = HtfLevelTracker(
            tf_minutes=htf_level_tf_minutes,
            n_left=htf_n_left,
            base_bar_minutes=base_bar_minutes,
        ) if self._is_htf_variant() else None
        self._htf_high_state = {"instance_id": -1, "consumed": False}
        self._htf_low_state = {"instance_id": -1, "consumed": False}

        # State
        self._state = LSIState.IDLE
        self._current_date = ""
        self._skip_reason: str | None = None
        self._blocking_gate: str | None = None
        self._regime_gate_status: dict | None = None
        self._last_regime_gate_audit: tuple[str, bool] | None = None
        self._daily_atr: float = 0.0
        self._bar_count: int = 0
        self._session_filled_trades: int = 0

        # Bar history — keep enough for absolute stop computation
        # (FVG bar through inversion bar can span ~30 bars)
        self._bars: list[Bar] = []
        self._MAX_BAR_HISTORY = 50

        # Sweep + gap state
        self._active_sweep: SweepEvent | None = None
        self._active_gap: GapInfo | None = None
        self._active_sweep_instance_id: int = -1
        self._active_htf_level_side: str = ""
        self._sweep_bar_index: int = 0
        self._pending_gaps: list[GapInfo] = []
        # Recent FVGs awaiting a sweep (for fvg_window_left lookback)
        # Each entry: (bar_index, GapInfo)
        self._recent_fvgs: list[tuple[int, GapInfo]] = []
        self._fvg_to_inversion_bars: int | None = None
        self._sweep_to_inversion_bars: int | None = None

        # Entry state
        self._entry_price: float = 0.0
        self._entry_direction: int = 0
        self._entry_stop: float = 0.0

        # ARMED_LIMIT state (fvg_limit mode only)
        self._limit_price: float = 0.0
        self._limit_direction: int = 0
        self._limit_gap: GapInfo | None = None
        self._limit_daily_atr: float = 0.0

        # LSI overlay (swept level + FVG zone, persists until next session reset)
        self._swept_level: float | None = None
        self._swept_level_time: str | None = None  # "HH:MM" ET of the pivot bar
        self._fvg_top: float | None = None
        self._fvg_bottom: float | None = None

        # Trade resolution (persists until next session reset)
        self._exit_type: str | None = None
        self._r_result: float | None = None

        # Position state
        self._levels: TradeLevels | None = None
        self._tp1_hit: bool = False
        self._tp1_bar_count: int = -1  # _bar_count when TP1 detected (guards 5m BE false trigger)
        self._fill_bar_count: int = -1  # _bar_count when fill detected (guards 5m fill-bar exits)
        self._fill_timestamp: datetime | None = None
        self._last_market_bar: Bar | None = None

        # Callbacks
        self.on_state_change: Callable[[dict], None] | None = None
        self.on_trade_exit: Callable[[TradeRecord], None] | None = None
        self.on_checkpoint: Callable[[], None] | None = None
        self.position_manager: ContractCapManager | None = None
        self.position_limit_key: str = ""
        self.trade_overlap_check: Callable[[int], bool] | None = None
        self._trade_overlap: bool = False
        self._trade_overlap_direction: int = 0
        self._cleanup_task: asyncio.Task | None = None

    def _is_legacy_variant(self) -> bool:
        return self.lsi_variant == LEGACY_LSI_VARIANT

    def _is_htf_variant(self) -> bool:
        return self.lsi_variant == HTF_LSI_VARIANT

    def _clear_dashboard_overlay(self) -> None:
        """Clear the current LSI setup overlay shown on the dashboard."""
        self._swept_level = None
        self._swept_level_time = None
        self._fvg_top = None
        self._fvg_bottom = None
        self._fvg_to_inversion_bars = None
        self._sweep_to_inversion_bars = None

    def _reset_active_setup(self) -> None:
        """Drop the current sweep/gap chain while preserving session counters."""
        self._active_sweep = None
        self._active_gap = None
        self._active_sweep_instance_id = -1
        self._active_htf_level_side = ""
        self._pending_gaps.clear()
        self._clear_dashboard_overlay()

    def _set_post_exit_state(self, exit_time: time) -> None:
        """Mirror the research/live HTF behavior after a trade finishes."""
        if (
            self._is_htf_variant()
            and (
                self.htf_trade_max_per_session <= 0
                or self._session_filled_trades < self.htf_trade_max_per_session
            )
            and self._in_entry(exit_time)
        ):
            self._state = LSIState.SCANNING
            self._clear_dashboard_overlay()
        else:
            self._state = LSIState.FLAT

    def _blocking_regime_gate_name(self, date_key: str) -> str | None:
        from .gates import blocking_regime_gate_name
        return blocking_regime_gate_name(self.regime_gate_checks, date_key)

    def _clear_gate_audit(self) -> None:
        self._skip_reason = None
        self._blocking_gate = None
        self._regime_gate_status = None
        self._last_regime_gate_audit = None

    def _record_regime_gate_status(self, date_key: str, blocking_gate: str | None) -> None:
        from .gates import evaluate_regime_gates

        evaluations: list[dict[str, object]] = []
        if self.regime_gates:
            try:
                evaluations = [
                    evaluation.to_status_dict()
                    for evaluation in evaluate_regime_gates(self.regime_gates, date_key)
                ]
            except ValueError:
                evaluations = []

        if evaluations and blocking_gate is not None:
            for evaluation in evaluations:
                evaluation["allowed"] = evaluation.get("gate") != blocking_gate

        self._blocking_gate = blocking_gate
        self._skip_reason = "regime_gate" if blocking_gate is not None else None
        self._regime_gate_status = {
            "date": date_key,
            "allowed": blocking_gate is None,
            "blocking_gate": blocking_gate,
            "evaluations": evaluations,
        } if (self.regime_gates or blocking_gate is not None) else None

    def _maybe_log_regime_gate_audit(self) -> None:
        from .gates import RegimeGateEvaluation, format_regime_gate_detail

        status = self._regime_gate_status
        if not status:
            return

        date_key = str(status.get("date") or self._current_date)
        allowed = bool(status.get("allowed"))
        marker = (date_key, allowed)
        if self._last_regime_gate_audit == marker:
            return

        evaluations = status.get("evaluations") or []
        primary_eval: RegimeGateEvaluation | None = None
        if evaluations:
            blocking_gate = status.get("blocking_gate")
            for evaluation in evaluations:
                if evaluation.get("gate") == blocking_gate or primary_eval is None:
                    primary_eval = RegimeGateEvaluation(
                        gate=str(evaluation.get("gate", "")),
                        date_key=str(evaluation.get("date", date_key)),
                        allowed=bool(evaluation.get("allowed")),
                        reason=str(evaluation["reason"]) if evaluation.get("reason") else None,
                        regime=str(evaluation["regime"]) if evaluation.get("regime") is not None else None,
                        vol_regime=str(evaluation["vol_regime"]) if evaluation.get("vol_regime") is not None else None,
                        combined_regime=(
                            str(evaluation["combined_regime"])
                            if evaluation.get("combined_regime") is not None else None
                        ),
                        low_confidence=(
                            bool(evaluation["low_confidence"])
                            if evaluation.get("low_confidence") is not None else None
                        ),
                        warmup_ok=(
                            bool(evaluation["warmup_ok"])
                            if evaluation.get("warmup_ok") is not None else None
                        ),
                    )
                if evaluation.get("gate") == blocking_gate:
                    break

        if allowed:
            if primary_eval is not None:
                self._log_trade("REGIME_GATE_PASSED", format_regime_gate_detail(primary_eval))
            else:
                self._log_trade("REGIME_GATE_PASSED", f"date={date_key}")
        else:
            blocking_gate = status.get("blocking_gate") or self._blocking_gate
            self._log_trade("REGIME_GATE_BLOCKED", f"gate={blocking_gate} date={date_key}")

        self._last_regime_gate_audit = marker

    def _set_sweep_overlay(self, sweep: SweepEvent) -> None:
        """Persist the active swept level immediately after sweep detection."""
        self._swept_level = sweep.level
        self._swept_level_time = sweep.pivot_time
        self._fvg_top = None
        self._fvg_bottom = None

    def _set_gap_overlay(self, gap: GapInfo) -> None:
        """Add the identified gap bounds to the current dashboard overlay."""
        if self._active_sweep is not None:
            self._swept_level = self._active_sweep.level
            self._swept_level_time = self._active_sweep.pivot_time
        self._fvg_top = gap.top
        self._fvg_bottom = gap.bottom

    def _sync_htf_level_state(self) -> None:
        tracker = self._htf_levels
        if tracker is None:
            return

        latest_high = tracker.latest_high
        latest_low = tracker.latest_low

        high_id = latest_high.instance_id if latest_high is not None else -1
        if high_id != self._htf_high_state["instance_id"]:
            self._htf_high_state["instance_id"] = high_id
            self._htf_high_state["consumed"] = False

        low_id = latest_low.instance_id if latest_low is not None else -1
        if low_id != self._htf_low_state["instance_id"]:
            self._htf_low_state["instance_id"] = low_id
            self._htf_low_state["consumed"] = False

    def _check_htf_sweep(self, bar: Bar, *, allow_arm: bool) -> SweepEvent | None:
        tracker = self._htf_levels
        if tracker is None:
            return None

        self._sync_htf_level_state()
        sweep: SweepEvent | None = None
        current_bar_ts = bar.timestamp

        latest_low = tracker.latest_low
        if (
            latest_low is not None
            and not self._htf_low_state["consumed"]
            and datetime.fromisoformat(latest_low.publish_time) <= current_bar_ts
            and bar.low < latest_low.price
        ):
            self._htf_low_state["consumed"] = True
            if allow_arm:
                sweep = SweepEvent(
                    source="htf_low",
                    level=latest_low.price,
                    direction=1,
                    bar_index=self._bar_count,
                    pivot_time=latest_low.level_time,
                )
                self._active_sweep_instance_id = latest_low.instance_id
                self._active_htf_level_side = "low"
            else:
                self._log_trade(
                    "HTF_LEVEL_INVALIDATED",
                    "side=low level=%.2f level_time=%s bar_time=%s"
                    % (latest_low.price, latest_low.level_time, bar.timestamp),
                )

        latest_high = tracker.latest_high
        if (
            not self.long_only
            and latest_high is not None
            and not self._htf_high_state["consumed"]
            and datetime.fromisoformat(latest_high.publish_time) <= current_bar_ts
            and bar.high > latest_high.price
            and sweep is None
        ):
            self._htf_high_state["consumed"] = True
            if allow_arm:
                sweep = SweepEvent(
                    source="htf_high",
                    level=latest_high.price,
                    direction=-1,
                    bar_index=self._bar_count,
                    pivot_time=latest_high.level_time,
                )
                self._active_sweep_instance_id = latest_high.instance_id
                self._active_htf_level_side = "high"
            else:
                self._log_trade(
                    "HTF_LEVEL_INVALIDATED",
                    "side=high level=%.2f level_time=%s bar_time=%s"
                    % (latest_high.price, latest_high.level_time, bar.timestamp),
                )

        return sweep

    # ------------------------------------------------------------------
    # Checkpoint
    # ------------------------------------------------------------------

    def _request_checkpoint(self) -> None:
        """Request a state checkpoint to disk for crash recovery."""
        if self.on_checkpoint is not None:
            self.on_checkpoint()

    def _position_cap_key(self) -> str:
        return self.position_limit_key or f"{self.config_name or 'DEFAULT'}:{self.name}"

    def _position_cap_owner(self) -> str:
        return self.name

    def _apply_position_cap(self, levels: TradeLevels) -> TradeLevels | None:
        if self.position_manager is None or not self.position_manager.enabled:
            return levels

        requested_qty = levels.qty
        approved_qty = self.position_manager.reserve(
            self._position_cap_key(),
            requested_qty,
            qty_step=self.qty_step,
            min_qty=self.min_qty,
            owner_id=self._position_cap_owner(),
            exclusive_key=True,
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
        self.position_manager.adjust(
            self._position_cap_key(),
            self._remaining_position_qty(),
            owner_id=self._position_cap_owner(),
        )

    def _release_position_cap(self) -> None:
        if self.position_manager is None or not self.position_manager.enabled:
            return
        self.position_manager.release(
            self._position_cap_key(),
            owner_id=self._position_cap_owner(),
        )

    def _schedule_post_exit_cleanup(self, *, reason: str, delay_s: float | None = None) -> None:
        """Cancel stale orders and flatten residual position after a resting exit should have filled."""
        if not self._should_send:
            self._release_position_cap()
            return

        if self._cleanup_task is not None and not self._cleanup_task.done():
            return

        cleanup_delay = self.post_exit_cleanup_delay_s if delay_s is None else delay_s

        async def _runner() -> None:
            try:
                if cleanup_delay > 0:
                    await asyncio.sleep(cleanup_delay)
                await self.broker.send_cancel(ticker=self.exec_ticker)
                if self.post_exit_cancel_settle_delay_s > 0:
                    await asyncio.sleep(self.post_exit_cancel_settle_delay_s)
                await self.broker.send_flatten(ticker=self.exec_ticker)
            except Exception:
                logger.exception("[%s] post-exit cleanup failed (%s)", self.name, reason)
            finally:
                self._release_position_cap()
                self._cleanup_task = None
                self._request_checkpoint()
                self._notify_state_change()

        self._cleanup_task = asyncio.create_task(_runner())

    def _broker_exit_cleanup_delay(self, default_delay_s: float) -> float:
        return 0.0 if self.post_exit_cleanup_delay_s <= 0 else default_delay_s

    def _display_state(self) -> str:
        if self._trade_overlap and self._state in {LSIState.WAITING_FOR_INVERSION, LSIState.ARMED_LIMIT}:
            return "trade_overlap"
        return self._state.value

    def _set_trade_overlap(
        self,
        active: bool,
        *,
        direction: int = 0,
        detail: str = "",
        notify: bool = True,
    ) -> None:
        changed = (self._trade_overlap != active) or (active and self._trade_overlap_direction != direction)
        self._trade_overlap = active
        self._trade_overlap_direction = direction if active else 0
        if not changed:
            return
        if active:
            self._log_trade("TRADE_OVERLAP", detail)
        if notify:
            self._notify_state_change()

    def _overlap_blocks(self, direction: int) -> bool:
        if direction != 1:
            return False
        if self.trade_overlap_check is None:
            return False
        return self.trade_overlap_check(direction)

    def _refresh_trade_overlap(self) -> None:
        if not self._trade_overlap:
            return
        if not self._overlap_blocks(self._trade_overlap_direction):
            self._set_trade_overlap(False)

    def _block_for_overlap(self, direction: int) -> bool:
        if self._overlap_blocks(direction):
            self._set_trade_overlap(
                True,
                direction=direction,
                detail="blocked_by=NQ_NY dir=long preferring_orb_short",
            )
            return True
        if self._trade_overlap:
            self._set_trade_overlap(False)
        return False

    # ------------------------------------------------------------------
    # Time helpers
    # ------------------------------------------------------------------

    def _in_entry(self, bar_time: time) -> bool:
        s, e = self._entry_start_t, self._entry_end_t
        if s <= e:
            return s <= bar_time < e
        return bar_time >= s or bar_time < e

    def _in_sweep(self, bar_time: time) -> bool:
        s, e = self._sweep_start_t, self._sweep_end_t
        if s <= e:
            return s <= bar_time < e
        return bar_time >= s or bar_time < e

    @property
    def _crosses_midnight(self) -> bool:
        """true if this session spans midnight."""
        return self._entry_start_t > self._flat_end_t

    def _is_same_session_night(self, date_str: str, bar_time: time) -> bool:
        """check whether a post-midnight bar belongs to the current session."""
        from datetime import datetime as _dt, timedelta as _td

        if bar_time >= self._entry_start_t:
            return False
        if not self._current_date:
            return False
        try:
            current = _dt.strptime(self._current_date, "%Y%m%d")
            bar_date = _dt.strptime(date_str, "%Y%m%d")
            return bar_date == current + _td(days=1)
        except ValueError:
            return False

    def _in_flat(self, bar) -> bool:
        bar_time = bar.timestamp.time() if hasattr(bar.timestamp, "time") else bar.timestamp
        s, e = self._flat_window_for_date(self._current_date)
        if s <= e:
            return s <= bar_time <= e
        return bar_time >= s or bar_time <= e

    def _flat_window_for_date(self, date_key: str) -> tuple[time, time]:
        """Return the effective flat window for a session date."""
        if date_key and date_key in self.half_days:
            return self._half_day_flat_start_t, self._half_day_flat_end_t
        return self._flat_start_t, self._flat_end_t

    def _crossed_flat_gap(self, previous_ts: datetime, current_ts: datetime) -> bool:
        """Detect when sparse data jumps over the configured flat window.

        Research exits at the last observed intraday bar when no bars exist inside
        the flat window (for example, CL days that jump from 14:29 to the evening
        reopen). Mirror that behavior here so exact replay does not carry the
        position into the next session just because no flat-window event arrived.
        """
        if self._crosses_midnight:
            return False

        date_key = previous_ts.strftime("%Y%m%d")
        flat_start, flat_end = self._flat_window_for_date(date_key)
        previous_time = previous_ts.time()
        current_time = current_ts.time()

        if previous_ts.date() != current_ts.date():
            return previous_time < flat_start

        return previous_time < flat_start and current_time > flat_end

    async def _exit_on_gap_flat(self, previous_bar: Bar, current_ts: datetime) -> None:
        """Force an EOD exit at the last observed price before a flat-window gap."""
        levels = self._levels
        dir_str = "long" if (levels and levels.direction == 1) else "short"
        self._log_trade(
            "EOD_GAP_FLAT",
            "dir=%s last_seen=%s current=%s"
            % (dir_str, previous_bar.timestamp, current_ts),
        )
        self._set_trade_overlap(False, notify=False)
        self._release_position_cap()
        if self._should_send:
            await self.broker.send_flatten(ticker=self.exec_ticker)
        self._emit_trade_record(
            "tp1_eod" if self._tp1_hit else "eod",
            exit_price=previous_bar.close,
            exit_timestamp=previous_bar.timestamp,
        )
        self._reset_active_setup()
        self._state = LSIState.FLAT
        self._request_checkpoint()
        self._notify_state_change()

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
    # Startup recovery
    # ------------------------------------------------------------------

    def recover_session_state(self, bars: list[Bar], now: datetime) -> bool:
        """Recover session state after restart (parallel to ORBEngine.recover_opening_range).

        Determines the correct state based on current time and feeds
        historical bars through the swing tracker to warm pivot levels.
        Returns True if the engine was set to a non-IDLE state.
        """
        from datetime import timedelta as _td

        now_t = now.time()

        # For cross-midnight sessions, if we're in the post-midnight
        # portion, the session started on the previous calendar day.
        if self._crosses_midnight and now_t < self._entry_start_t:
            session_date = now - _td(days=1)
            date_str = session_date.strftime("%Y%m%d")
        else:
            date_str = now.strftime("%Y%m%d")

        self._current_date = date_str
        self._clear_gate_audit()

        # Check exclusions
        dummy_bar = Bar(timestamp=now, open=0.0, high=0.0, low=0.0, close=0.0, volume=0)
        if self._is_excluded_day(dummy_bar):
            self._state = LSIState.FLAT
            self._notify_state_change()
            logger.info("[%s] Session excluded for %s, set FLAT", self.name, date_str)
            return True

        # Warm structure state from recent historical bars.
        # Legacy-LSI and HTF-LSI both need broader warmup than same-day only
        # because valid levels can survive across day boundaries.
        if self._crosses_midnight:
            valid_dates = {date_str, (datetime.strptime(date_str, "%Y%m%d") + _td(days=1)).strftime("%Y%m%d")}
            session_bars = [b for b in bars if b.timestamp <= now and b.timestamp.strftime("%Y%m%d") in valid_dates]
        elif self._is_legacy_variant() or self._is_htf_variant():
            session_bars = [b for b in bars if b.timestamp <= now]
        else:
            session_bars = [b for b in bars if b.timestamp <= now and b.timestamp.strftime("%Y%m%d") == date_str]

        for b in session_bars:
            if self._is_htf_variant():
                self._htf_levels.on_bar(b)
                self._sync_htf_level_state()
            else:
                self._swings.on_bar(b)
        self._bar_count = len(session_bars)
        self._bars = session_bars[-self._MAX_BAR_HISTORY:] if session_bars else []

        # Determine state based on current time
        if self._in_entry(now_t):
            blocking_gate = self._blocking_regime_gate_name(date_str)
            self._record_regime_gate_status(date_str, blocking_gate)
            if blocking_gate is not None:
                self._maybe_log_regime_gate_audit()
                self._state = LSIState.FLAT
            else:
                self._maybe_log_regime_gate_audit()
                self._state = LSIState.SCANNING
        elif self._in_flat(dummy_bar):
            self._state = LSIState.FLAT
        elif not self._crosses_midnight and now_t < self._entry_start_t:
            # Pre-session (daytime sessions only): stay IDLE so the normal
            # IDLE→SCANNING transition fires when the entry window opens.
            self._state = LSIState.IDLE
        elif self._crosses_midnight and self._flat_end_t <= now_t < self._entry_start_t:
            # Pre-session for cross-midnight sessions: the daytime gap between
            # flat_end and entry_start (e.g. 07:00–20:40). Post-midnight times
            # like 02:15 don't match because 02:15 < flat_end (07:00).
            self._state = LSIState.IDLE
        else:
            # Between entry_end and flat_start — session over, no new entries
            self._state = LSIState.FLAT

        logger.info(
            "[%s] Session recovered: state=%s date=%s bars_fed=%d "
            "structure=%s",
            self.name,
            self._state.value,
            date_str,
            len(session_bars),
            (
                "htf_high=%s htf_low=%s"
                % (
                    round(self._htf_levels.latest_high.price, 2) if self._htf_levels and self._htf_levels.latest_high else None,
                    round(self._htf_levels.latest_low.price, 2) if self._htf_levels and self._htf_levels.latest_low else None,
                )
            ) if self._is_htf_variant() else (
                "swing_high=%.2f swing_low=%.2f"
                % (self._swings.latest_swing_high, self._swings.latest_swing_low)
            ),
        )
        self._notify_state_change()
        return self._state != LSIState.IDLE

    # ------------------------------------------------------------------
    # Pause guard
    # ------------------------------------------------------------------

    @property
    def _should_send(self) -> bool:
        """Whether this engine should send broker payloads."""
        return not self.paused

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

    def _emit_trade_record(
        self,
        exit_type: str,
        exit_price: float | None = None,
        *,
        exit_timestamp: datetime | None = None,
    ) -> None:
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
            timestamp=(exit_timestamp or datetime.now()).isoformat(),
            config_name=self.config_name,
            r_result=self._r_result,
            entry_timestamp=self._fill_timestamp.isoformat() if self._fill_timestamp else "",
        )
        self.on_trade_exit(record)

    def _price_to_r(self, exit_price: float) -> float:
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
    # FVG detection (3-candle pattern, no ORB filter)
    # ------------------------------------------------------------------

    def _check_fvg(self, daily_atr: float) -> tuple[bool, bool, GapInfo | None]:
        """Check last 3 bars for FVG. Returns (found, is_bullish, gap_info)."""
        if len(self._bars) < 3:
            return False, False, None
        if not math.isfinite(daily_atr) or daily_atr <= 0.0:
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
        """Process a 5m bar — runs all signal detection.

        Mirrors the backtester's _extract_lsi_candidates logic:
        - Tracks recent FVGs and sweeps in parallel
        - FVGs formed before a sweep (within fvg_window_left) are promoted
        - FVGs formed after a sweep (within fvg_window_right) are promoted
        - Entry at inversion-bar close with absolute-range stop
        - Optional inversion-lag expiry for HTF-LSI
        """
        self._daily_atr = daily_atr
        self._refresh_trade_overlap()
        previous_bar = self._last_market_bar
        self._last_market_bar = bar

        if (
            self._state == LSIState.MANAGING
            and self._levels is not None
            and previous_bar is not None
            and self._crossed_flat_gap(previous_bar.timestamp, bar.timestamp)
        ):
            await self._exit_on_gap_flat(previous_bar, bar.timestamp)
            return

        self._bar_count += 1

        # Store bar history (keep enough for absolute stop computation)
        self._bars.append(bar)
        if len(self._bars) > self._MAX_BAR_HISTORY:
            self._bars.pop(0)

        bar_date = bar.timestamp.strftime("%Y%m%d")
        bar_time = bar.timestamp.time()

        # new day reset
        if bar_date != self._current_date:
            if self._crosses_midnight and self._is_same_session_night(bar_date, bar_time):
                logger.debug(
                    "[%s] cross-midnight: skipping reset (same session night) date=%s current_date=%s bar_time=%s state=%s",
                    self.name,
                    bar_date,
                    self._current_date,
                    bar_time,
                    self._state.value,
                )
            else:
                if self._state == LSIState.MANAGING:
                    await self._exit_position(bar, "eod")
                self._release_position_cap()
                self._current_date = bar_date
                self._clear_gate_audit()
                self._state = LSIState.IDLE
                self._session_filled_trades = 0
                self._active_sweep = None
                self._active_gap = None
                self._active_sweep_instance_id = -1
                self._active_htf_level_side = ""
                self._pending_gaps.clear()
                self._recent_fvgs.clear()
                self._limit_price = 0.0
                self._limit_direction = 0
                self._limit_gap = None
                self._limit_daily_atr = 0.0
                self._levels = None
                self._set_trade_overlap(False, notify=False)
                self._tp1_hit = False
                self._tp1_bar_count = -1
                self._fill_bar_count = -1
                self._fill_timestamp = None
                self._exit_type = None
                self._r_result = None
                self._clear_dashboard_overlay()
                self._request_checkpoint()

        if self._is_htf_variant():
            self._htf_levels.on_bar(bar)
            self._sync_htf_level_state()
            if self._in_sweep(bar_time):
                sweep = self._check_htf_sweep(bar, allow_arm=self._in_entry(bar_time))
            else:
                sweep = None
        else:
            sweep = self._swings.on_bar(bar)

        # State machine
        if self._state == LSIState.IDLE:
            if self._in_sweep(bar_time) and not self._is_excluded_day(bar):
                blocking_gate = self._blocking_regime_gate_name(self._current_date)
                self._record_regime_gate_status(self._current_date, blocking_gate)
                if blocking_gate is not None:
                    self._maybe_log_regime_gate_audit()
                    self._state = LSIState.FLAT
                    self._request_checkpoint()
                    self._notify_state_change()
                    return
                self._maybe_log_regime_gate_audit()
                self._state = LSIState.SCANNING
                self._request_checkpoint()
                self._notify_state_change()

        if self._state == LSIState.SCANNING:
            if not self._in_sweep(bar_time):
                self._log_trade("NO_SETUP", "sweep window closed")
                self._state = LSIState.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            # Register any new FVG into the recent buffer (for lookback pairing)
            current_bar_gap: GapInfo | None = None
            if self._in_entry(bar_time):
                found, is_bullish, gap = self._check_fvg(daily_atr)
                if found and gap is not None:
                    self._recent_fvgs.append((self._bar_count, gap))
                    current_bar_gap = gap

            # Check for sweep events
            if sweep is not None:
                if not (self.long_only and sweep.direction != 1):
                    self._active_sweep = sweep
                    self._sweep_bar_index = self._bar_count
                    self._set_sweep_overlay(sweep)
                    self._log_trade(
                        "SWEEP_DETECTED",
                        "source=%s level=%.2f dir=%s bar_count=%d"
                        % (sweep.source, sweep.level, "long" if sweep.direction == 1 else "short", self._bar_count),
                    )

                    # Check if any recent FVGs (within fvg_window_left) already qualify
                    promoted_gaps = self._promote_recent_fvgs(sweep)
                    if (
                        current_bar_gap is not None
                        and self._gap_matches_sweep(current_bar_gap, sweep)
                    ):
                        # Research appends the same-bar/post-sweep gap first,
                        # then extends with promoted pre-sweep gaps.
                        promoted_gaps = self._prepend_unique_gap(current_bar_gap, promoted_gaps)
                    if promoted_gaps:
                        self._pending_gaps = promoted_gaps
                        self._active_gap = promoted_gaps[0]
                        self._set_gap_overlay(promoted_gaps[0])
                        self._state = LSIState.WAITING_FOR_INVERSION
                        self._request_checkpoint()
                        self._log_trade(
                            "GAP_DETECTED",
                            "type=%s top=%.2f bottom=%.2f size=%.2f (pre-sweep)"
                            % ("bearish" if not promoted_gaps[0].is_bullish else "bullish",
                               promoted_gaps[0].top, promoted_gaps[0].bottom,
                               promoted_gaps[0].top - promoted_gaps[0].bottom),
                        )
                        self._notify_state_change()
                    else:
                        self._pending_gaps.clear()
                        self._state = LSIState.WAITING_FOR_GAP
                        self._request_checkpoint()
                        self._notify_state_change()

            # Prune stale FVGs from buffer
            self._recent_fvgs = [
                (idx, g) for idx, g in self._recent_fvgs
                if self._bar_count - idx <= self.fvg_window_left + self.fvg_window_right
            ]

        if self._state == LSIState.WAITING_FOR_GAP:
            if not self._in_entry(bar_time):
                self._state = LSIState.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            # Check bar count since sweep
            bars_since = self._bar_count - self._sweep_bar_index
            if bars_since > self.fvg_window_right:
                self._log_trade("SWEEP_EXPIRED", "bars_since=%d" % bars_since)
                self._state = LSIState.SCANNING
                self._active_sweep = None
                self._active_gap = None
                self._active_sweep_instance_id = -1
                self._active_htf_level_side = ""
                self._pending_gaps.clear()
                self._clear_dashboard_overlay()
                self._request_checkpoint()
                self._notify_state_change()
                return

            # Look for opposite-direction FVG
            found, is_bullish, gap = self._check_fvg(daily_atr)
            if found and gap is not None:
                sweep_dir = self._active_sweep.direction
                need_bearish = sweep_dir == 1
                if (need_bearish and not is_bullish) or (not need_bearish and is_bullish):
                    self._pending_gaps.append(gap)
                    self._active_gap = self._pending_gaps[0]
                    self._set_gap_overlay(self._active_gap)
                    self._state = LSIState.WAITING_FOR_INVERSION
                    self._request_checkpoint()
                    self._log_trade(
                        "GAP_DETECTED",
                        "type=%s top=%.2f bottom=%.2f size=%.2f"
                        % ("bearish" if not is_bullish else "bullish",
                           gap.top, gap.bottom, gap.top - gap.bottom),
                    )
                    self._notify_state_change()

        if self._state == LSIState.WAITING_FOR_INVERSION:
            if not self._in_entry(bar_time):
                self._state = LSIState.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            if self._active_gap is not None and not self._pending_gaps:
                self._pending_gaps = [self._active_gap]

            if not self._pending_gaps and self._active_gap is None:
                self._state = LSIState.SCANNING
                self._active_sweep = None
                self._active_sweep_instance_id = -1
                self._active_htf_level_side = ""
                self._pending_gaps.clear()
                self._clear_dashboard_overlay()
                self._request_checkpoint()
                self._notify_state_change()
                return

            bars_since_sweep = self._bar_count - self._sweep_bar_index
            if bars_since_sweep <= self.fvg_window_right:
                found, is_bullish, new_gap = self._check_fvg(daily_atr)
                if found and new_gap is not None:
                    sweep_dir = self._active_sweep.direction
                    need_bearish = sweep_dir == 1
                    if (need_bearish and not is_bullish) or (not need_bearish and is_bullish):
                        if not any(self._same_gap(existing, new_gap) for existing in self._pending_gaps):
                            self._pending_gaps.append(new_gap)
                        if self._active_gap is None:
                            self._active_gap = new_gap
                            self._set_gap_overlay(new_gap)

            if not self._pending_gaps and bars_since_sweep > self.fvg_window_right:
                self._log_trade("SWEEP_EXPIRED", "bars_since=%d" % bars_since_sweep)
                self._state = LSIState.SCANNING
                self._active_sweep = None
                self._active_gap = None
                self._active_sweep_instance_id = -1
                self._active_htf_level_side = ""
                self._pending_gaps.clear()
                self._clear_dashboard_overlay()
                self._request_checkpoint()
                self._notify_state_change()
                return

            gap = self._active_gap or (self._pending_gaps[0] if self._pending_gaps else None)
            if gap is None:
                return

            # Only check inversion on bars AFTER the gap formed
            surviving_gaps: list[GapInfo] = []
            chosen_gap: GapInfo | None = None
            for candidate_gap in self._pending_gaps:
                if self._bar_count <= candidate_gap.bar_index:
                    surviving_gaps.append(candidate_gap)
                    continue
                if self.max_fvg_to_inversion_bars > 0:
                    fvg_to_inversion_bars = self._bar_count - candidate_gap.bar_index
                    if fvg_to_inversion_bars > self.max_fvg_to_inversion_bars:
                        continue
                inverted = (
                    candidate_gap.is_bullish and bar.close < candidate_gap.bottom
                ) or (
                    not candidate_gap.is_bullish and bar.close > candidate_gap.top
                )
                if chosen_gap is None and inverted:
                    chosen_gap = candidate_gap
                    continue
                surviving_gaps.append(candidate_gap)

            self._pending_gaps = surviving_gaps
            self._active_gap = self._pending_gaps[0] if self._pending_gaps else None
            if self._active_gap is not None:
                self._set_gap_overlay(self._active_gap)
            elif chosen_gap is None:
                if self._active_sweep is not None and bars_since_sweep <= self.fvg_window_right:
                    self._state = LSIState.WAITING_FOR_GAP
                    self._set_sweep_overlay(self._active_sweep)
                else:
                    self._state = LSIState.SCANNING
                    self._active_sweep = None
                    self._active_sweep_instance_id = -1
                    self._active_htf_level_side = ""
                    self._clear_dashboard_overlay()
                self._request_checkpoint()
                self._notify_state_change()
                return

            if chosen_gap is not None:
                if chosen_gap.is_bullish:
                    if not self.long_only:
                        if self._block_for_overlap(direction=-1):
                            self._pending_gaps.insert(0, chosen_gap)
                            self._active_gap = chosen_gap
                            return
                        self._fvg_to_inversion_bars = self._bar_count - chosen_gap.bar_index
                        self._sweep_to_inversion_bars = self._bar_count - self._sweep_bar_index
                        self._active_gap = chosen_gap
                        self._set_gap_overlay(chosen_gap)
                        if self.lsi_entry_mode == "fvg_limit":
                            await self._arm_limit(bar, chosen_gap, direction=-1, daily_atr=daily_atr)
                            return
                        await self._enter_at_close(bar, chosen_gap, direction=-1, daily_atr=daily_atr)
                else:
                    if self._block_for_overlap(direction=1):
                        self._pending_gaps.insert(0, chosen_gap)
                        self._active_gap = chosen_gap
                        return
                    self._fvg_to_inversion_bars = self._bar_count - chosen_gap.bar_index
                    self._sweep_to_inversion_bars = self._bar_count - self._sweep_bar_index
                    self._active_gap = chosen_gap
                    self._set_gap_overlay(chosen_gap)
                    if self.lsi_entry_mode == "fvg_limit":
                        await self._arm_limit(bar, chosen_gap, direction=1, daily_atr=daily_atr)
                        return
                    await self._enter_at_close(bar, chosen_gap, direction=1, daily_atr=daily_atr)

        if self._state == LSIState.ARMED_LIMIT:
            if not self._in_entry(bar_time):
                self._log_trade("LIMIT_CANCELLED", "entry window closed")
                self._set_trade_overlap(False, notify=False)
                self._state = LSIState.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return

            # Check if limit price was hit on this bar
            is_long = self._limit_direction == 1
            filled = (is_long and bar.low <= self._limit_price) or (
                not is_long and bar.high >= self._limit_price
            )
            if filled:
                if self._block_for_overlap(self._limit_direction):
                    return
                await self._fill_limit(bar, daily_atr)

        if self._state == LSIState.MANAGING:
            await self._handle_managing(bar, daily_atr)

    # ------------------------------------------------------------------
    # FVG lookback promotion (backtest's "FVG before sweep" pairing)
    # ------------------------------------------------------------------

    def _promote_recent_fvgs(self, sweep: SweepEvent) -> list[GapInfo]:
        """Collect all recently buffered FVGs that pair with this sweep.

        Mirrors the backtester's phase C/D: when a sweep occurs, check
        detected FVGs within fvg_window_left bars for opposite-direction match.
        """
        need_bearish = sweep.direction == 1  # low sweep → need bearish FVG
        promoted: list[GapInfo] = []
        for fvg_idx, gap in self._recent_fvgs:
            bars_ago = self._bar_count - fvg_idx
            if bars_ago > self.fvg_window_left:
                continue
            # Direction check: low sweep needs bearish FVG, high sweep needs bullish
            if need_bearish and not gap.is_bullish:
                promoted.append(gap)
            if not need_bearish and gap.is_bullish:
                promoted.append(gap)
        return promoted

    @staticmethod
    def _same_gap(left: GapInfo, right: GapInfo) -> bool:
        return (
            left.is_bullish == right.is_bullish
            and left.bar_index == right.bar_index
            and math.isclose(left.top, right.top, rel_tol=0.0, abs_tol=1e-9)
            and math.isclose(left.bottom, right.bottom, rel_tol=0.0, abs_tol=1e-9)
        )

    @staticmethod
    def _gap_matches_sweep(gap: GapInfo, sweep: SweepEvent) -> bool:
        need_bearish = sweep.direction == 1
        return (need_bearish and not gap.is_bullish) or (not need_bearish and gap.is_bullish)

    def _prepend_unique_gap(self, gap: GapInfo, gaps: list[GapInfo]) -> list[GapInfo]:
        deduped = [existing for existing in gaps if not self._same_gap(existing, gap)]
        return [gap] + deduped

    # ------------------------------------------------------------------
    # fvg_limit entry mode: arm limit → fill on next bar touch
    # ------------------------------------------------------------------

    async def _arm_limit(self, bar: Bar, gap: GapInfo, direction: int, daily_atr: float) -> None:
        """Arm a limit order at the FVG boundary after inversion is confirmed.

        Matches backtester's entry_mode="fvg_limit":
        - LONG:  limit at gap.top  (top of bearish FVG = low[fvg_bar - 2])
        - SHORT: limit at gap.bottom (bottom of bullish FVG = high[fvg_bar - 2])
        Fill scan starts on the NEXT bar (signal_bar = inversion bar).
        """
        is_long = direction == 1
        limit_price = gap.top if is_long else gap.bottom

        self._set_trade_overlap(False, notify=False)
        self._limit_price = limit_price
        self._limit_direction = direction
        self._limit_gap = gap
        self._limit_daily_atr = daily_atr
        self._state = LSIState.ARMED_LIMIT
        self._request_checkpoint()

        dir_str = "long" if is_long else "short"
        self._log_trade(
            "LIMIT_ARMED",
            "dir=%s limit=%.2f gap_top=%.2f gap_bottom=%.2f"
            % (dir_str, limit_price, gap.top, gap.bottom),
        )
        self._notify_state_change()

    async def _fill_limit(self, bar: Bar, daily_atr: float) -> None:
        """Fill the armed limit order — compute levels and enter position.

        Entry price = limit price (FVG boundary).
        Stop = absolute range from FVG bar through current bar (fill bar).
        """
        gap = self._limit_gap
        direction = self._limit_direction
        entry = self._limit_price
        is_long = direction == 1
        dir_str = "long" if is_long else "short"

        # Compute absolute-range stop from FVG bar through fill bar
        fvg_bar_offset = self._bar_count - gap.bar_index
        if fvg_bar_offset >= len(self._bars):
            fvg_bar_offset = len(self._bars) - 1
        start_idx = max(0, len(self._bars) - 1 - fvg_bar_offset)
        range_bars = self._bars[start_idx:]

        if is_long:
            raw_stop = min(b.low for b in range_bars) if range_bars else entry - 1.0
        else:
            raw_stop = max(b.high for b in range_bars) if range_bars else entry + 1.0

        if self.min_stop_points > 0:
            stop_dist = abs(entry - raw_stop)
            if stop_dist < self.min_stop_points:
                raw_stop = entry - self.min_stop_points if is_long else entry + self.min_stop_points

        await self._build_and_enter(bar, gap, entry, raw_stop, direction, daily_atr)

    # ------------------------------------------------------------------
    # Inversion-bar-close entry
    # ------------------------------------------------------------------

    async def _enter_at_close(self, bar: Bar, gap: GapInfo, direction: int, daily_atr: float) -> None:
        """Enter at inversion bar close with absolute-range stop.

        Matches the backtester's entry_mode="close" and stop_mode="absolute":
        - Entry price = bar.close (the inversion candle's close)
        - Stop = absolute min(low) or max(high) from FVG bar through inversion bar
        """
        entry = bar.close
        is_long = direction == 1

        # Compute absolute-range stop
        fvg_bar_offset = self._bar_count - gap.bar_index
        if fvg_bar_offset >= len(self._bars):
            fvg_bar_offset = len(self._bars) - 1
        start_idx = max(0, len(self._bars) - 1 - fvg_bar_offset)
        range_bars = self._bars[start_idx:]

        if is_long:
            raw_stop = min(b.low for b in range_bars) if range_bars else entry - 1.0
        else:
            raw_stop = max(b.high for b in range_bars) if range_bars else entry + 1.0

        if self.min_stop_points > 0:
            stop_dist = abs(entry - raw_stop)
            if stop_dist < self.min_stop_points:
                raw_stop = entry - self.min_stop_points if is_long else entry + self.min_stop_points

        await self._build_and_enter(bar, gap, entry, raw_stop, direction, daily_atr)

    async def _build_and_enter(
        self, bar: Bar, gap: GapInfo, entry: float, raw_stop: float,
        direction: int, daily_atr: float,
    ) -> None:
        """Shared sizing + state transition for both entry modes."""
        is_long = direction == 1
        dir_str = "long" if is_long else "short"
        gap_size = gap.top - gap.bottom

        risk_pts = abs(entry - raw_stop)
        tp1_dist = self.rr * risk_pts * self.tp1_ratio
        tp2_dist = self.rr * risk_pts

        from .sizing import TradeLevels as TL, _floor_to_step
        qty_raw = self.risk_usd / (risk_pts * self.point_value) if risk_pts > 0 else 0
        qty = _floor_to_step(qty_raw, self.qty_step)
        if qty < self.min_qty:
            single_risk = risk_pts * self.point_value * self.min_qty
            if single_risk <= self.max_single_risk_usd:
                qty = self.min_qty
            else:
                self._log_trade("ENTRY_REJECTED", "risk too high for 1 contract: risk=%.2f" % single_risk)
                self._state = LSIState.SCANNING
                self._active_sweep = None
                self._active_gap = None
                self._active_sweep_instance_id = -1
                self._active_htf_level_side = ""
                self._pending_gaps.clear()
                self._clear_dashboard_overlay()
                self._request_checkpoint()
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
            be=entry,
            qty=qty,
            half_qty=half_qty,
            is_single_contract=is_single,
            risk_pts=risk_pts,
            direction=direction,
            gap_size=gap_size,
        )
        self._levels = self._apply_position_cap(self._levels)
        if self._levels is None:
            self._state = LSIState.SCANNING
            self._active_sweep = None
            self._active_gap = None
            self._active_sweep_instance_id = -1
            self._active_htf_level_side = ""
            self._pending_gaps.clear()
            self._clear_dashboard_overlay()
            self._request_checkpoint()
            self._notify_state_change()
            return

        # Persist LSI overlay for dashboard display
        self._set_gap_overlay(gap)

        self._set_trade_overlap(False, notify=False)
        self._tp1_hit = False
        self._tp1_bar_count = -1
        self._fill_bar_count = self._bar_count
        self._fill_timestamp = bar.timestamp
        self._session_filled_trades += 1
        self._state = LSIState.MANAGING
        self._request_checkpoint()

        mode_str = self.lsi_entry_mode
        self._log_trade(
            "FILLED",
            "dir=%s entry=%.2f stop=%.2f tp1=%.2f tp2=%.2f qty=%.1f (%s)"
            % (dir_str, entry, raw_stop,
               self._levels.tp1, self._levels.tp2, self._levels.qty, mode_str),
        )

        if self._should_send:
            entry_action = "buy" if is_long else "sell"
            await self.broker.send_entry(
                action=entry_action,
                qty=self._levels.qty,
                price=self._levels.entry,
                tp2=self._levels.tp2,
                stop=self._levels.stop,
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
            self._state = LSIState.FLAT
            self._request_checkpoint()
            return

        is_long = levels.direction == 1
        dir_str = "long" if is_long else "short"

        # EOD flat
        if self._in_flat(bar):
            await self._exit_position(bar, "tp1_eod" if self._tp1_hit else "eod")
            return

        # Gate: don't check exits on the fill bar itself (same-bar prevention)
        if self._bar_count <= self._fill_bar_count:
            return

        # Gate: skip the 5m bar that contains the TP1 hit.
        # When TP1 is detected on a 1s tick mid-bar, the enclosing 5m bar's
        # low includes pre-TP1 price action near the entry, making
        # bar.low <= BE trivially true and causing a false BE_HIT.
        # The 1s tick path is authoritative for exits on this bar.
        if self._tp1_hit and self._tp1_bar_count >= 0 and self._bar_count <= self._tp1_bar_count:
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
                self._request_checkpoint()
                self._tp1_bar_count = self._bar_count
                self._sync_position_cap()
                if levels.is_single_contract:
                    self._log_trade("TP1_BE_SINGLE", "dir=%s tp1=%.2f be=%.2f" % (dir_str, levels.tp1, levels.be))
                    if self._should_send:
                        await self.broker.send_tp1_single(
                            direction=dir_str, qty=levels.qty, be_price=levels.be, ticker=self.exec_ticker)
                else:
                    self._log_trade("TP1_PARTIAL", "dir=%s tp1=%.2f half=%.1f be=%.2f tp2=%.2f"
                                    % (dir_str, levels.tp1, levels.half_qty, levels.be, levels.tp2))
                    if self._should_send:
                        await self.broker.send_tp1_multi(
                            direction=dir_str, total_qty=levels.qty, exit_qty=levels.half_qty, be_price=levels.be,
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
        self._set_trade_overlap(False, notify=False)
        if exit_type in {"eod", "tp1_eod"}:
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_flatten(ticker=self.exec_ticker)
        else:
            cleanup_delay = self._broker_exit_cleanup_delay(1.0) if exit_type in {"sl", "tp2_direct"} else None
            self._schedule_post_exit_cleanup(
                reason=f"{exit_type}_hit_5m",
                delay_s=cleanup_delay,
            )
        exit_price = bar.close if exit_type in {"eod", "tp1_eod"} else None
        self._emit_trade_record(
            exit_type,
            exit_price=exit_price,
            exit_timestamp=bar.timestamp,
        )
        self._reset_active_setup()
        self._set_post_exit_state(bar.timestamp.time())
        self._request_checkpoint()
        self._notify_state_change()

    # ------------------------------------------------------------------
    # 1s tick handler (fine-grained exit management)
    # ------------------------------------------------------------------

    async def on_tick(self, tick: Bar, daily_atr: float) -> None:
        """Process a 1s bar for fine-grained exit management and limit fill detection."""
        self._daily_atr = daily_atr
        self._refresh_trade_overlap()
        previous_bar = self._last_market_bar
        self._last_market_bar = tick

        # ARMED_LIMIT: check for limit fill on tick data
        if self._state == LSIState.ARMED_LIMIT:
            if not self._in_entry(tick.timestamp.time()):
                self._log_trade("LIMIT_CANCELLED", "entry window closed (1s)")
                self._set_trade_overlap(False, notify=False)
                self._state = LSIState.FLAT
                self._request_checkpoint()
                self._notify_state_change()
                return
            is_long = self._limit_direction == 1
            filled = (is_long and tick.low <= self._limit_price) or (
                not is_long and tick.high >= self._limit_price
            )
            if filled:
                if self._block_for_overlap(self._limit_direction):
                    return
                # Use the tick as the bar context for fill
                await self._fill_limit(tick, daily_atr)
            return

        if self._state != LSIState.MANAGING:
            return

        levels = self._levels
        if levels is None:
            self._state = LSIState.FLAT
            self._request_checkpoint()
            return

        if previous_bar is not None and self._crossed_flat_gap(previous_bar.timestamp, tick.timestamp):
            await self._exit_on_gap_flat(previous_bar, tick.timestamp)
            return

        is_long = levels.direction == 1
        dir_str = "long" if is_long else "short"

        # EOD flat
        if self._in_flat(tick):
            self._log_trade("EOD_FLAT", "dir=%s tick_time=%s resolution=1s" % (dir_str, tick.timestamp))
            self._set_trade_overlap(False, notify=False)
            self._release_position_cap()
            if self._should_send:
                await self.broker.send_flatten(ticker=self.exec_ticker)
            self._emit_trade_record(
                "tp1_eod" if self._tp1_hit else "eod",
                exit_price=tick.close,
                exit_timestamp=tick.timestamp,
            )
            self._reset_active_setup()
            self._state = LSIState.FLAT
            self._request_checkpoint()
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
                self._set_trade_overlap(False, notify=False)
                self._schedule_post_exit_cleanup(
                    reason="sl_hit_1s_ambiguous",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("sl", exit_timestamp=tick.timestamp)
                self._reset_active_setup()
                self._set_post_exit_state(tick.timestamp.time())
                self._request_checkpoint()
                self._notify_state_change()
                return

            if sl_hit:
                self._log_trade("SL_HIT", "dir=%s stop=%.2f resolution=1s" % (dir_str, levels.stop))
                self._set_trade_overlap(False, notify=False)
                self._schedule_post_exit_cleanup(
                    reason="sl_hit_1s",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("sl", exit_timestamp=tick.timestamp)
                self._reset_active_setup()
                self._set_post_exit_state(tick.timestamp.time())
                self._request_checkpoint()
                self._notify_state_change()
                return

            if tp1_touched:
                self._tp1_hit = True
                self._request_checkpoint()
                self._tp1_bar_count = self._bar_count
                self._sync_position_cap()
                if levels.is_single_contract:
                    self._log_trade("TP1_BE_SINGLE", "dir=%s tp1=%.2f be=%.2f resolution=1s" % (dir_str, levels.tp1, levels.be))
                    if self._should_send:
                        await self.broker.send_tp1_single(direction=dir_str, qty=levels.qty, be_price=levels.be, ticker=self.exec_ticker)
                else:
                    self._log_trade("TP1_PARTIAL", "dir=%s tp1=%.2f half=%.1f be=%.2f tp2=%.2f resolution=1s"
                                    % (dir_str, levels.tp1, levels.half_qty, levels.be, levels.tp2))
                    if self._should_send:
                        await self.broker.send_tp1_multi(
                            direction=dir_str,
                            total_qty=levels.qty,
                            exit_qty=levels.half_qty,
                            be_price=levels.be,
                            tp2=levels.tp2,
                            ticker=self.exec_ticker,
                        )
                self._notify_state_change()
                return

            # TP2 direct
            tp2_hit = (is_long and tick.high >= levels.tp2) or (not is_long and tick.low <= levels.tp2)
            if tp2_hit:
                self._log_trade("TP2_DIRECT", "dir=%s tp2=%.2f resolution=1s" % (dir_str, levels.tp2))
                self._set_trade_overlap(False, notify=False)
                self._schedule_post_exit_cleanup(
                    reason="tp2_direct_1s",
                    delay_s=self._broker_exit_cleanup_delay(1.0),
                )
                self._emit_trade_record("tp2_direct", exit_timestamp=tick.timestamp)
                self._reset_active_setup()
                self._set_post_exit_state(tick.timestamp.time())
                self._request_checkpoint()
                self._notify_state_change()
                return

        # Post-TP1
        else:
            be_hit = (is_long and tick.low <= levels.be) or (not is_long and tick.high >= levels.be)
            tp2_hit = (is_long and tick.high >= levels.tp2) or (not is_long and tick.low <= levels.tp2)

            if be_hit:
                self._log_trade("BE_HIT", "dir=%s be=%.2f resolution=1s" % (dir_str, levels.be))
                self._set_trade_overlap(False, notify=False)
                self._schedule_post_exit_cleanup(reason="be_hit_1s")
                self._emit_trade_record("tp1_be", exit_timestamp=tick.timestamp)
                self._reset_active_setup()
                self._set_post_exit_state(tick.timestamp.time())
                self._request_checkpoint()
                self._notify_state_change()
                return

            if tp2_hit:
                self._log_trade("TP2_HIT", "dir=%s tp2=%.2f resolution=1s" % (dir_str, levels.tp2))
                self._set_trade_overlap(False, notify=False)
                self._schedule_post_exit_cleanup(reason="tp2_hit_1s")
                self._emit_trade_record("tp1_tp2", exit_timestamp=tick.timestamp)
                self._reset_active_setup()
                self._set_post_exit_state(tick.timestamp.time())
                self._request_checkpoint()
                self._notify_state_change()
                return

    # ------------------------------------------------------------------
    # Public status
    # ------------------------------------------------------------------

    @property
    def state(self) -> LSIState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state not in (LSIState.IDLE, LSIState.FLAT)

    def status_dict(self) -> dict:
        levels = self._levels
        sw = self._swings
        latest_htf_high = self._htf_levels.latest_high if self._htf_levels is not None else None
        latest_htf_low = self._htf_levels.latest_low if self._htf_levels is not None else None
        overlap_active = self._trade_overlap and self._state in {
            LSIState.WAITING_FOR_INVERSION,
            LSIState.ARMED_LIMIT,
        }
        result: dict = {
            "config_name": self.config_name,
            "session": self.name,
            "state": self._display_state(),
            "raw_state": self._state.value,
            "type": "lsi",
            "date": self._current_date,
            "daily_atr": round(self._daily_atr, 2) if self._daily_atr else None,
            "atr_length": self.atr_length,
            "sweep_start": self.sweep_start,
            "sweep_end": self.sweep_end,
            "latest_swing_high": round(sw.latest_swing_high, 2) if not math.isnan(sw.latest_swing_high) else None,
            "latest_swing_low": round(sw.latest_swing_low, 2) if not math.isnan(sw.latest_swing_low) else None,
            "latest_htf_high": round(latest_htf_high.price, 2) if latest_htf_high is not None else None,
            "latest_htf_high_time": latest_htf_high.level_time if latest_htf_high is not None else None,
            "latest_htf_low": round(latest_htf_low.price, 2) if latest_htf_low is not None else None,
            "latest_htf_low_time": latest_htf_low.level_time if latest_htf_low is not None else None,
            # Nested levels dict — matches ORB engine format for frontend
            "levels": {
                "entry": round(levels.entry, 2),
                "stop": round(levels.stop, 2),
                "tp1": round(levels.tp1, 2),
                "tp2": round(levels.tp2, 2),
                "qty": levels.qty,
                "direction": levels.direction,
            } if levels else None,
            "tp1_hit": self._tp1_hit,
            "exit_type": self._exit_type,
            "r_result": round(self._r_result, 2) if self._r_result is not None else None,
            "risk_usd": self.risk_usd,
            "paused": self.paused,
            "excluded_dow": self.excluded_dow,
            "skip_reason": self._skip_reason,
            "blocking_gate": self._blocking_gate,
            "regime_gate_status": self._regime_gate_status,
            "entry_mode": self.lsi_entry_mode,
            "lsi_variant": self.lsi_variant,
            "base_bar_minutes": self.base_bar_minutes,
            "htf_level_tf_minutes": self.htf_level_tf_minutes if self._is_htf_variant() else None,
            "htf_n_left": self.htf_n_left if self._is_htf_variant() else None,
            "htf_trade_max_per_session": self.htf_trade_max_per_session if self._is_htf_variant() else None,
            "max_fvg_to_inversion_bars": self.max_fvg_to_inversion_bars if self._is_htf_variant() else None,
            "session_filled_trades": self._session_filled_trades,
            "trade_overlap": overlap_active,
            # LSI overlay — swept level + FVG zone (persists into FLAT)
            "swept_level": round(self._swept_level, 2) if self._swept_level is not None else None,
            "swept_level_time": self._swept_level_time,
            "fvg_top": round(self._fvg_top, 2) if self._fvg_top is not None else None,
            "fvg_bottom": round(self._fvg_bottom, 2) if self._fvg_bottom is not None else None,
            "fvg_to_inversion_bars": self._fvg_to_inversion_bars,
            "sweep_to_inversion_bars": self._sweep_to_inversion_bars,
        }
        if self._state == LSIState.ARMED_LIMIT:
            result["limit_price"] = round(self._limit_price, 2)
            result["limit_direction"] = self._limit_direction
        return result
