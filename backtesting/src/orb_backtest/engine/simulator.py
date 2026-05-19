"""Trade simulation engine.

Hybrid approach:
1. Vectorized signal generation produces SetupCandidate records
2. Numba-compiled loop simulates fills and exits per candidate

This module orchestrates the full pipeline: signals → candidates → trades → results.
"""

from __future__ import annotations

import math
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import numba as nb
import pandas as pd

from collections import defaultdict

from ..config import (
    StrategyConfig,
    SessionConfig,
    ASIA_SESSION,
    LDN_SESSION,
    NY_SESSION,
    REF_LSI_LEVELS,
    DATA_REF_LSI_LEVELS,
)
from ..signals.session import compute_session_masks, compute_trading_days, compute_session_days, compute_date_strings
from ..signals.daily_atr import compute_daily_atr
from ..signals.equal_levels import compute_equal_htf_levels
from ..signals.orb import compute_orb_levels
from ..signals.fvg import detect_fvg
from ..signals.cisd import detect_internal_cisd
from ..signals.htf_levels import compute_htf_unswept_levels
from ..signals.reference_levels import compute_reference_levels, compute_data_sweep_levels
from ..signals.swing import detect_swing_highs, detect_swing_lows
from ..signals.lrlr import LRLRResult, detect_lrlr_cluster
from ..signals.structure_15m import compute_all_15m_signals
from ..signals.vwap import compute_session_vwap


# ---------------------------------------------------------------------------
# Exit type constants (used in numba-compiled code)
# ---------------------------------------------------------------------------
EXIT_NO_FILL = 0
EXIT_SL = 1
EXIT_TP1_TP2 = 2
EXIT_TP1_BE = 3
EXIT_TP1_EOD = 4
EXIT_EOD = 5
EXIT_TP2_SINGLE = 6  # single contract, full target hit
EXIT_BE_SL = 7       # swing-triggered BE, then stop at entry hit before TP1 — 0R

EXIT_NAMES = {
    EXIT_NO_FILL: "no_fill",
    EXIT_SL: "sl",
    EXIT_TP1_TP2: "tp1_tp2",
    EXIT_TP1_BE: "tp1_be",
    EXIT_TP1_EOD: "tp1_eod",
    EXIT_EOD: "eod",
    EXIT_TP2_SINGLE: "tp2_single",
    EXIT_BE_SL:      "be_sl",
}

RUNNER_TRAIL_DISABLED = 0
RUNNER_TRAIL_STEP_R = 1
RUNNER_TRAIL_RISK = 2
RUNNER_TRAIL_ATR = 3


def _runner_trail_mode_code(mode: str) -> int:
    if mode == "step_r":
        return RUNNER_TRAIL_STEP_R
    if mode == "risk":
        return RUNNER_TRAIL_RISK
    if mode == "atr":
        return RUNNER_TRAIL_ATR
    return RUNNER_TRAIL_DISABLED


class TradeResult(NamedTuple):
    """Result of a single trade simulation."""

    date: str  # YYYY-MM-DD
    session: str  # NY, Asia, LDN
    direction: int  # +1 long, -1 short
    signal_bar: int  # bar index where FVG detected
    fill_bar: int  # bar index where limit filled (-1 if no fill)
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    exit_type: int  # EXIT_* constant
    exit_bar: int  # bar index of final exit
    pnl_points: float  # total PnL in points
    pnl_usd: float  # net total PnL in USD after commissions
    r_multiple: float  # gross PnL as multiple of price risk
    qty: float
    half_qty: float
    gap_size: float
    risk_points: float
    fill_time: str  # ISO timestamp of fill bar ("" if no fill)
    exit_time: str  # ISO timestamp of exit bar ("" if no fill)
    # LSI-specific overlay data (0.0/"" for non-LSI trades)
    lsi_swept_level: float = 0.0   # swing pivot price that was swept
    lsi_fvg_top: float = 0.0       # upper boundary of the inverting FVG zone
    lsi_fvg_bottom: float = 0.0    # lower boundary of the inverting FVG zone
    lsi_fvg_time: str = ""         # ISO timestamp of the FVG bar (bar[0] of 3-candle pattern)
    lsi_sweep_time: str = ""       # ISO timestamp of the bar where the liquidity sweep occurred
    lsi_confirmation_type: str = ""  # "inversion" or "cisd" for LSI-style setups
    lsi_cisd_level: float = 0.0
    lsi_cisd_time: str = ""
    reference_level_name: str = ""  # completed-session / previous-day level used by reference_lsi
    reference_level_price: float = 0.0
    htf_level_time: str = ""       # ISO timestamp of the HTF bar that supplied the swept level
    htf_level_price: float = 0.0
    htf_level_side: str = ""       # "high" or "low"
    htf_level_tf_minutes: int = 0
    fvg_to_inversion_bars: int = 0
    sweep_to_inversion_bars: int = 0
    inversion_ordinal: int = 0
    lsi_lrlr_present: bool = False
    lsi_lrlr_level_count: int = 0
    lsi_lrlr_nearest_level_price: float = 0.0
    lsi_lrlr_farthest_level_price: float = 0.0
    lsi_lrlr_span_bars: int = 0
    lsi_lrlr_price_span_atr: float = 0.0
    lsi_lrlr_slope_atr_per_bar: float = 0.0
    lsi_lrlr_fit_error_atr: float = 0.0
    lsi_lrlr_tp1_path_present: bool = False
    lsi_lrlr_nearest_tp1_gap_atr: float = 0.0
    gross_pnl_usd: float = 0.0
    commission_usd: float = 0.0
    net_r_multiple: float = 0.0


# ---------------------------------------------------------------------------
# Numba-compiled trade simulation
# ---------------------------------------------------------------------------
@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _apply_runner_trail_stop(
    direction: int,
    entry_price: float,
    risk_pts: float,
    current_stop: float,
    high_price: float,
    low_price: float,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
) -> float:
    """Ratchet a post-TP1 runner stop without ever loosening it."""
    if trail_mode == RUNNER_TRAIL_DISABLED or risk_pts <= 0.0:
        return current_stop

    new_stop = current_stop
    if trail_mode == RUNNER_TRAIL_STEP_R:
        if trail_trigger_r <= 0.0 or trail_step_r <= 0.0:
            return current_stop
        if direction == 1:
            mfe_r = (high_price - entry_price) / risk_pts
        else:
            mfe_r = (entry_price - low_price) / risk_pts
        if mfe_r >= trail_trigger_r:
            steps = math.floor((mfe_r - trail_trigger_r) / trail_step_r + 1e-9)
            lock_r = trail_stop_r + steps * trail_step_r
            if lock_r < 0.0:
                lock_r = 0.0
            if direction == 1:
                new_stop = entry_price + lock_r * risk_pts
            else:
                new_stop = entry_price - lock_r * risk_pts
    elif trail_mode == RUNNER_TRAIL_RISK:
        if trail_gap_r <= 0.0:
            return current_stop
        if direction == 1:
            new_stop = high_price - trail_gap_r * risk_pts
        else:
            new_stop = low_price + trail_gap_r * risk_pts
    elif trail_mode == RUNNER_TRAIL_ATR:
        if trail_atr_points <= 0.0:
            return current_stop
        if direction == 1:
            new_stop = high_price - trail_atr_points
        else:
            new_stop = low_price + trail_atr_points

    if direction == 1:
        return max(current_stop, new_stop)
    return min(current_stop, new_stop)


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _simulate_single_trade(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    entry_bar_start: int,
    entry_bar_end: int,
    flat_bar_start: int,
    last_bar: int,
    direction: int,
    entry_price: float,
    stop_price: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    is_single: bool,
    qty: float,
    half_qty: float,
    point_value: float,
    commission: float,
    pre_entry_cancel_requires_new_sweep: bool,
    pre_entry_new_high_sweep: np.ndarray,
    pre_entry_new_low_sweep: np.ndarray,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
    internal_swing_level: float = 1e38,
    cancel_on_swing: bool = False,
    pre_entry_cancel_target_price: float = np.nan,
) -> tuple:
    """Simulate a single trade from fill scan to exit.

    Returns: (fill_bar, exit_type, exit_bar, pnl_points, pnl_usd, r_multiple)

    Fill_bar = -1 and exit_type = EXIT_NO_FILL if limit never fills.
    """
    risk_pts = abs(entry_price - stop_price)
    if risk_pts <= 0:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 1: Scan for limit fill
    fill_bar = -1
    pre_entry_target_touched = False
    pre_entry_sweep_seen = False
    for i in range(entry_bar_start, min(entry_bar_end + 1, last_bar + 1)):
        if direction == 1:  # long: fill when low <= entry
            if low[i] <= entry_price:
                fill_bar = i
                break
        else:  # short: fill when high >= entry
            if high[i] >= entry_price:
                fill_bar = i
                break
        # Cancel check: swing swept on a non-fill bar — don't enter
        if cancel_on_swing:
            if direction == 1 and high[i] >= internal_swing_level:
                return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
            elif direction == -1 and low[i] <= internal_swing_level:
                return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
        if not np.isnan(pre_entry_cancel_target_price):
            if direction == 1:
                if pre_entry_cancel_requires_new_sweep and pre_entry_new_low_sweep[i]:
                    pre_entry_sweep_seen = True
                if high[i] >= pre_entry_cancel_target_price:
                    if not pre_entry_cancel_requires_new_sweep:
                        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
                    pre_entry_target_touched = True
                if pre_entry_target_touched and pre_entry_sweep_seen:
                    return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
            else:
                if pre_entry_cancel_requires_new_sweep and pre_entry_new_high_sweep[i]:
                    pre_entry_sweep_seen = True
                if low[i] <= pre_entry_cancel_target_price:
                    if not pre_entry_cancel_requires_new_sweep:
                        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
                    pre_entry_target_touched = True
                if pre_entry_target_touched and pre_entry_sweep_seen:
                    return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    if fill_bar == -1:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 2: Simulate exit (includes fill bar — price can hit SL/TP on same bar)
    tp1_hit = False
    be_triggered = False
    current_stop = stop_price
    risk_pts = abs(entry_price - stop_price)
    remaining_qty = qty
    pnl_points = 0.0

    scan_start = fill_bar

    for i in range(scan_start, last_bar + 1):
        # Swing BE trigger: if swing level swept, move stop to entry
        # Guard: skip fill bar itself (fill bar low <= entry price ≈ swing level)
        if not be_triggered and not tp1_hit and i > fill_bar:
            if direction == 1 and high[i] >= internal_swing_level:
                be_triggered = True
                current_stop = be_price
            elif direction == -1 and low[i] <= internal_swing_level:
                be_triggered = True
                current_stop = be_price

        # Check if we've entered flat window
        is_flat_bar = i >= flat_bar_start

        if direction == 1:  # LONG
            sl_hit = low[i] <= current_stop
            tp1_trigger = high[i] >= tp1_price and not tp1_hit
            tp2_trigger = high[i] >= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high[i], low[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = low[i] <= current_stop

            if is_flat_bar and not sl_hit:
                # EOD flat
                if tp1_hit:
                    pnl_points += (close[i] - entry_price) * (remaining_qty / qty)
                    return fill_bar, EXIT_TP1_EOD, i, pnl_points, 0.0, 0.0
                else:
                    pnl_points = (close[i] - entry_price)
                    return fill_bar, EXIT_EOD, i, pnl_points, 0.0, 0.0

            if sl_hit and not tp1_hit:
                # Full stop loss (before TP1)
                if be_triggered:
                    return fill_bar, EXIT_BE_SL, i, 0.0, 0.0, 0.0
                pnl_points = current_stop - entry_price
                return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

            if is_single:
                # Single contract: check if price touched TP1 level (BE trigger)
                if tp1_trigger:
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high[i], low[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = low[i] <= current_stop
                if tp2_trigger:
                    pnl_points = tp2_price - entry_price
                    return fill_bar, EXIT_TP2_SINGLE, i, pnl_points, 0.0, 0.0
                if sl_hit and tp1_hit:
                    pnl_points = current_stop - entry_price
                    return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
            else:
                # Multi-contract
                if sl_hit and tp1_trigger:
                    # Same bar conflict: conservative = SL wins
                    if be_triggered:
                        return fill_bar, EXIT_BE_SL, i, 0.0, 0.0, 0.0
                    pnl_points = current_stop - entry_price
                    return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

                if tp1_trigger:
                    # Partial exit at TP1
                    leg1_pnl = (tp1_price - entry_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high[i], low[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if low[i] <= current_stop:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
                    continue

                if tp1_hit:
                    if sl_hit:  # This is now BE stop
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return fill_bar, EXIT_TP1_TP2, i, pnl_points, 0.0, 0.0

        else:  # SHORT
            sl_hit = high[i] >= current_stop
            tp1_trigger = low[i] <= tp1_price and not tp1_hit
            tp2_trigger = low[i] <= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high[i], low[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = high[i] >= current_stop

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close[i]) * (remaining_qty / qty)
                    return fill_bar, EXIT_TP1_EOD, i, pnl_points, 0.0, 0.0
                else:
                    pnl_points = entry_price - close[i]
                    return fill_bar, EXIT_EOD, i, pnl_points, 0.0, 0.0

            if sl_hit and not tp1_hit:
                if be_triggered:
                    return fill_bar, EXIT_BE_SL, i, 0.0, 0.0, 0.0
                pnl_points = entry_price - current_stop
                return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high[i], low[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = high[i] >= current_stop
                if tp2_trigger:
                    pnl_points = entry_price - tp2_price
                    return fill_bar, EXIT_TP2_SINGLE, i, pnl_points, 0.0, 0.0
                if sl_hit and tp1_hit:
                    pnl_points = entry_price - current_stop
                    return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
            else:
                if sl_hit and tp1_trigger:
                    if be_triggered:
                        return fill_bar, EXIT_BE_SL, i, 0.0, 0.0, 0.0
                    pnl_points = entry_price - current_stop
                    return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

                if tp1_trigger:
                    leg1_pnl = (entry_price - tp1_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high[i], low[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if high[i] >= current_stop:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return fill_bar, EXIT_TP1_TP2, i, pnl_points, 0.0, 0.0

    # Reached end of data without exit (shouldn't happen with EOD flat)
    if direction == 1:
        pnl_points = close[last_bar] - entry_price
    else:
        pnl_points = entry_price - close[last_bar]
    return fill_bar, EXIT_EOD, last_bar, pnl_points, 0.0, 0.0


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _scan_fill_bar(
    high: np.ndarray,
    low: np.ndarray,
    entry_bar_start: int,
    entry_bar_end: int,
    last_bar: int,
    direction: int,
    entry_price: float,
) -> int:
    """Scan for limit fill without simulating the exit.

    Returns the bar index where the limit order fills, or -1 if no fill.
    Used to determine which candidate fills first on dual-signal session-days.
    """
    for i in range(entry_bar_start, min(entry_bar_end + 1, last_bar + 1)):
        if direction == 1:
            if low[i] <= entry_price:
                return i
        else:
            if high[i] >= entry_price:
                return i
    return -1


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _scan_fill_bar_ib(
    high: np.ndarray,
    low: np.ndarray,
    entry_bar_start: int,
    entry_bar_end: int,
    last_bar: int,
    direction: int,
    entry_price: float,
    ib_high: float,
    ib_low: float,
) -> int:
    """Scan for limit fill, cancelling if IB range is broken before fill.

    IB is considered broken if high > ib_high or low < ib_low on any bar
    before the limit fills. Returns -1 if IB breaks or no fill.
    """
    for i in range(entry_bar_start, min(entry_bar_end + 1, last_bar + 1)):
        # Check IB break first (strict inequality)
        if high[i] > ib_high or low[i] < ib_low:
            return -1
        # Check fill
        if direction == 1:
            if low[i] <= entry_price:
                return i
        else:
            if high[i] >= entry_price:
                return i
    return -1


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _scan_fill_bar_ib_magnifier(
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    entry_start_1m: int,
    entry_end_1m: int,
    last_bar_1m: int,
    direction: int,
    entry_price: float,
    ib_high: float,
    ib_low: float,
) -> int:
    """Scan for limit fill on 1m bars, cancelling if IB breaks before fill.

    Same logic as _scan_fill_bar_ib but at 1-minute resolution so that
    intra-5m-bar ordering of fill vs break is resolved correctly (matching
    Pine Script's bar magnifier behaviour).

    Returns 1m bar index of fill, or -1 if IB breaks first / no fill.
    """
    for i in range(entry_start_1m, min(entry_end_1m + 1, last_bar_1m + 1)):
        # Check IB break first (strict inequality)
        if high_1m[i] > ib_high or low_1m[i] < ib_low:
            return -1
        # Check fill
        if direction == 1:
            if low_1m[i] <= entry_price:
                return i
        else:
            if high_1m[i] >= entry_price:
                return i
    return -1


# ---------------------------------------------------------------------------
# Bar magnifier: 1-minute sub-bar simulation (Numba-compiled)
# ---------------------------------------------------------------------------

@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _simulate_exit_magnifier(
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    close_1m: np.ndarray,
    fill_bar_1m: int,
    flat_start_1m: int,
    last_bar_1m: int,
    direction: int,
    entry_price: float,
    stop_price: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    is_single: bool,
    qty: float,
    half_qty: float,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
    internal_swing_level: float = 1e38,
) -> tuple:
    """Simulate exit on 1m bars. Returns (exit_type, exit_bar_1m, pnl_points).

    Same TP1/TP2/BE/EOD/SL logic as Phase 2 of _simulate_single_trade,
    but operating on 1m OHLC arrays for higher precision.
    """
    tp1_hit = False
    be_triggered = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    # Include fill bar in exit scanning (price can hit SL/TP on same bar)
    scan_start = fill_bar_1m

    for i in range(scan_start, last_bar_1m + 1):
        # Swing BE trigger
        # Guard: skip fill bar itself (fill bar low <= entry price ≈ swing level)
        if not be_triggered and not tp1_hit and i > fill_bar_1m:
            if direction == 1 and high_1m[i] >= internal_swing_level:
                be_triggered = True
                current_stop = be_price
            elif direction == -1 and low_1m[i] <= internal_swing_level:
                be_triggered = True
                current_stop = be_price

        is_flat_bar = i >= flat_start_1m

        if direction == 1:  # LONG
            sl_hit = low_1m[i] <= current_stop
            tp1_trigger = high_1m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_1m[i] >= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_1m[i], low_1m[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = low_1m[i] <= current_stop

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_1m[i] - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                else:
                    pnl_points = (close_1m[i] - entry_price)
                    return EXIT_EOD, i, pnl_points

            if sl_hit and not tp1_hit:
                if be_triggered:
                    return EXIT_BE_SL, i, 0.0
                pnl_points = current_stop - entry_price
                return EXIT_SL, i, pnl_points

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = low_1m[i] <= current_stop
                if tp2_trigger:
                    pnl_points = tp2_price - entry_price
                    return EXIT_TP2_SINGLE, i, pnl_points
                if sl_hit and tp1_hit:
                    pnl_points = current_stop - entry_price
                    return EXIT_TP1_BE, i, pnl_points
            else:
                if sl_hit and tp1_trigger:
                    if be_triggered:
                        return EXIT_BE_SL, i, 0.0
                    pnl_points = current_stop - entry_price
                    return EXIT_SL, i, pnl_points

                if tp1_trigger:
                    leg1_pnl = (tp1_price - entry_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if low_1m[i] <= current_stop:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_TP2, i, pnl_points

        else:  # SHORT
            sl_hit = high_1m[i] >= current_stop
            tp1_trigger = low_1m[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_1m[i] <= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_1m[i], low_1m[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = high_1m[i] >= current_stop

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_1m[i]) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                else:
                    pnl_points = entry_price - close_1m[i]
                    return EXIT_EOD, i, pnl_points

            if sl_hit and not tp1_hit:
                if be_triggered:
                    return EXIT_BE_SL, i, 0.0
                pnl_points = entry_price - current_stop
                return EXIT_SL, i, pnl_points

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = high_1m[i] >= current_stop
                if tp2_trigger:
                    pnl_points = entry_price - tp2_price
                    return EXIT_TP2_SINGLE, i, pnl_points
                if sl_hit and tp1_hit:
                    pnl_points = entry_price - current_stop
                    return EXIT_TP1_BE, i, pnl_points
            else:
                if sl_hit and tp1_trigger:
                    if be_triggered:
                        return EXIT_BE_SL, i, 0.0
                    pnl_points = entry_price - current_stop
                    return EXIT_SL, i, pnl_points

                if tp1_trigger:
                    leg1_pnl = (entry_price - tp1_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if high_1m[i] >= current_stop:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return EXIT_TP1_TP2, i, pnl_points

    # Reached end of data without exit
    if direction == 1:
        pnl_points = close_1m[last_bar_1m] - entry_price
    else:
        pnl_points = entry_price - close_1m[last_bar_1m]
    return EXIT_EOD, last_bar_1m, pnl_points


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _simulate_single_trade_magnifier(
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    close_1m: np.ndarray,
    entry_start_1m: int,
    entry_end_1m: int,
    flat_start_1m: int,
    last_bar_1m: int,
    direction: int,
    entry_price: float,
    stop_price: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    is_single: bool,
    qty: float,
    half_qty: float,
    point_value: float,
    commission: float,
    pre_entry_cancel_requires_new_sweep: bool,
    pre_entry_new_high_sweep_1m: np.ndarray,
    pre_entry_new_low_sweep_1m: np.ndarray,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
    internal_swing_level: float = 1e38,
    cancel_on_swing: bool = False,
    pre_entry_cancel_target_price: float = np.nan,
) -> tuple:
    """Simulate fill + exit on 1m bars.

    Returns (fill_bar_1m, exit_type, exit_bar_1m, pnl_points, 0.0, 0.0).
    Same tuple shape as _simulate_single_trade for drop-in compatibility.
    """
    risk_pts = abs(entry_price - stop_price)
    if risk_pts <= 0:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 1: Scan for limit fill on 1m bars
    fill_bar_1m = -1
    pre_entry_target_touched = False
    pre_entry_sweep_seen = False
    for i in range(entry_start_1m, min(entry_end_1m + 1, last_bar_1m + 1)):
        if direction == 1:
            if low_1m[i] <= entry_price:
                fill_bar_1m = i
                break
        else:
            if high_1m[i] >= entry_price:
                fill_bar_1m = i
                break
        # Cancel check: swing swept on a non-fill bar
        if cancel_on_swing:
            if direction == 1 and high_1m[i] >= internal_swing_level:
                return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
            elif direction == -1 and low_1m[i] <= internal_swing_level:
                return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
        if not np.isnan(pre_entry_cancel_target_price):
            if direction == 1:
                if pre_entry_cancel_requires_new_sweep and pre_entry_new_low_sweep_1m[i]:
                    pre_entry_sweep_seen = True
                if high_1m[i] >= pre_entry_cancel_target_price:
                    if not pre_entry_cancel_requires_new_sweep:
                        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
                    pre_entry_target_touched = True
                if pre_entry_target_touched and pre_entry_sweep_seen:
                    return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
            else:
                if pre_entry_cancel_requires_new_sweep and pre_entry_new_high_sweep_1m[i]:
                    pre_entry_sweep_seen = True
                if low_1m[i] <= pre_entry_cancel_target_price:
                    if not pre_entry_cancel_requires_new_sweep:
                        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0
                    pre_entry_target_touched = True
                if pre_entry_target_touched and pre_entry_sweep_seen:
                    return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    if fill_bar_1m == -1:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 2: Simulate exit on 1m bars
    exit_type, exit_bar_1m, pnl_points = _simulate_exit_magnifier(
        high_1m, low_1m, close_1m,
        fill_bar_1m, flat_start_1m, last_bar_1m,
        direction,
        entry_price, stop_price, tp1_price, tp2_price, be_price,
        is_single, qty, half_qty,
        trail_mode, trail_trigger_r, trail_stop_r,
        trail_step_r, trail_gap_r, trail_atr_points,
        internal_swing_level,
    )

    return fill_bar_1m, exit_type, exit_bar_1m, pnl_points, 0.0, 0.0


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _scan_fill_bar_magnifier(
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    entry_start_1m: int,
    entry_end_1m: int,
    last_bar_1m: int,
    direction: int,
    entry_price: float,
) -> int:
    """Scan for fill on 1m bars. Returns 1m bar index or -1.

    Same logic as _scan_fill_bar but operating on 1m arrays.
    """
    for i in range(entry_start_1m, min(entry_end_1m + 1, last_bar_1m + 1)):
        if direction == 1:
            if low_1m[i] <= entry_price:
                return i
        else:
            if high_1m[i] >= entry_price:
                return i
    return -1


# ---------------------------------------------------------------------------
# Hierarchical bar magnifier: 5m → 1m → 1s
# Only magnifies when a bar simultaneously touches two price objectives.
# ---------------------------------------------------------------------------

@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _drill_down_1s(
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    start_1s: int,
    end_1s: int,
    direction: int,
    entry_price: float,
    risk_pts: float,
    current_stop: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    tp1_hit: bool,
    is_single: bool,
    qty: float,
    half_qty: float,
    remaining_qty: float,
    pnl_points: float,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
) -> tuple:
    """Scan 1s sub-bars to resolve an ambiguous 1m bar.

    Returns (resolved, exit_type, pnl_points, tp1_hit, current_stop, remaining_qty).
    If resolved=False, exit_type=-1 and state reflects any partial events (e.g. TP1 hit).
    If still ambiguous at 1s level, SL wins (pessimistic).
    """
    for i in range(start_1s, end_1s):
        if direction == 1:
            sl_hit = low_1s[i] <= current_stop
            tp1_trigger = high_1s[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_1s[i] >= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_1s[i], low_1s[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = low_1s[i] <= current_stop

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1s[i], low_1s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = low_1s[i] <= current_stop
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return True, EXIT_TP2_SINGLE, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
            else:
                if sl_hit and tp1_trigger:
                    # Still ambiguous at 1s — pessimistic
                    pnl_points += current_stop - entry_price
                    return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty
                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1s[i], low_1s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if low_1s[i] <= current_stop:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty
        else:
            sl_hit = high_1s[i] >= current_stop
            tp1_trigger = low_1s[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_1s[i] <= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_1s[i], low_1s[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = high_1s[i] >= current_stop

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1s[i], low_1s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = high_1s[i] >= current_stop
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return True, EXIT_TP2_SINGLE, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
            else:
                if sl_hit and tp1_trigger:
                    pnl_points += entry_price - current_stop
                    return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty
                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1s[i], low_1s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if high_1s[i] >= current_stop:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty

    return False, -1, pnl_points, tp1_hit, current_stop, remaining_qty


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _drill_down_30s(
    high_30s: np.ndarray,
    low_30s: np.ndarray,
    close_30s: np.ndarray,
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    map_30s_1s: np.ndarray,
    has_1s: bool,
    start_30s: int,
    end_30s: int,
    direction: int,
    entry_price: float,
    risk_pts: float,
    current_stop: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    tp1_hit: bool,
    is_single: bool,
    qty: float,
    half_qty: float,
    remaining_qty: float,
    pnl_points: float,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
) -> tuple:
    """Scan 30s sub-bars to resolve an ambiguous 1m bar.

    When a 30s bar is itself ambiguous (sl_hit AND tp1_trigger), drills to 1s.
    Returns (resolved, exit_type, pnl_points, tp1_hit, current_stop, remaining_qty).
    If resolved=False, state reflects any partial events that occurred.
    If still ambiguous at 30s level (and no 1s data), SL wins (pessimistic).
    """
    for i in range(start_30s, end_30s):
        if direction == 1:
            sl_hit = low_30s[i] <= current_stop
            tp1_trigger = high_30s[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_30s[i] >= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_30s[i], low_30s[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = low_30s[i] <= current_stop

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_30s[i], low_30s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = low_30s[i] <= current_stop
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return True, EXIT_TP2_SINGLE, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
            else:
                if sl_hit and tp1_trigger:
                    # Ambiguous at 30s — try 1s
                    if has_1s and i < len(map_30s_1s):
                        s1s = map_30s_1s[i, 0]
                        e1s = map_30s_1s[i, 1]
                        if e1s > s1s:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1s(
                                high_1s, low_1s, close_1s, s1s, e1s,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            if res:
                                return True, et, pnl_points, tp1_hit, current_stop, remaining_qty
                    # Pessimistic: SL wins
                    pnl_points += current_stop - entry_price
                    return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_30s[i], low_30s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if low_30s[i] <= current_stop:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty

        else:  # SHORT
            sl_hit = high_30s[i] >= current_stop
            tp1_trigger = low_30s[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_30s[i] <= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_30s[i], low_30s[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = high_30s[i] >= current_stop

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_30s[i], low_30s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = high_30s[i] >= current_stop
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return True, EXIT_TP2_SINGLE, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
            else:
                if sl_hit and tp1_trigger:
                    # Ambiguous at 30s — try 1s
                    if has_1s and i < len(map_30s_1s):
                        s1s = map_30s_1s[i, 0]
                        e1s = map_30s_1s[i, 1]
                        if e1s > s1s:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1s(
                                high_1s, low_1s, close_1s, s1s, e1s,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            if res:
                                return True, et, pnl_points, tp1_hit, current_stop, remaining_qty
                    # Pessimistic: SL wins
                    pnl_points += entry_price - current_stop
                    return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_30s[i], low_30s[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if high_30s[i] >= current_stop:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty

    return False, -1, pnl_points, tp1_hit, current_stop, remaining_qty


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _drill_down_1m(
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    close_1m: np.ndarray,
    high_30s: np.ndarray,
    low_30s: np.ndarray,
    close_30s: np.ndarray,
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    map_1m_30s: np.ndarray,
    map_30s_1s: np.ndarray,
    map_1m_1s: np.ndarray,
    has_30s: bool,
    has_1s: bool,
    start_1m: int,
    end_1m: int,
    flat_start_1m: int,
    direction: int,
    entry_price: float,
    risk_pts: float,
    current_stop: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    tp1_hit: bool,
    is_single: bool,
    qty: float,
    half_qty: float,
    remaining_qty: float,
    pnl_points: float,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
) -> tuple:
    """Scan 1m sub-bars for an ambiguous 5m bar or the fill bar's tail.

    When a 1m bar is itself ambiguous (sl_hit AND tp1_trigger):
      - Tries 30s sub-bars first (if has_30s), which itself tries 1s on ambiguous 30s bars.
      - Falls back to direct 1s (if has_1s but no 30s).
      - Falls back to pessimistic SL if neither resolves it.

    Returns (resolved, exit_type, exit_bar_1m, pnl_points, tp1_hit, current_stop, remaining_qty).
    """
    for i in range(start_1m, end_1m):
        is_flat = i >= flat_start_1m

        if direction == 1:
            sl_hit = low_1m[i] <= current_stop
            tp1_trigger = high_1m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_1m[i] >= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_1m[i], low_1m[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = low_1m[i] <= current_stop

            if is_flat and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_1m[i] - entry_price) * (remaining_qty / qty)
                    return True, EXIT_TP1_EOD, i, pnl_points, tp1_hit, current_stop, remaining_qty
                else:
                    pnl_points += close_1m[i] - entry_price
                    return True, EXIT_EOD, i, pnl_points, tp1_hit, current_stop, remaining_qty

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return True, EXIT_SL, i, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = low_1m[i] <= current_stop
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return True, EXIT_TP2_SINGLE, i, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return True, EXIT_TP1_BE, i, pnl_points, tp1_hit, current_stop, remaining_qty
            else:
                if sl_hit and tp1_trigger:
                    # Ambiguous at 1m — try 30s first, then direct 1s fallback
                    if has_30s and i < len(map_1m_30s):
                        s30 = map_1m_30s[i, 0]
                        e30 = map_1m_30s[i, 1]
                        if e30 > s30:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_30s(
                                high_30s, low_30s, close_30s,
                                high_1s, low_1s, close_1s,
                                map_30s_1s, has_1s, s30, e30,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            if res:
                                return True, et, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    elif has_1s and i < len(map_1m_1s):
                        s1s = map_1m_1s[i, 0]
                        e1s = map_1m_1s[i, 1]
                        if e1s > s1s:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1s(
                                high_1s, low_1s, close_1s, s1s, e1s,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            if res:
                                return True, et, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    # Fallback: pessimistic
                    pnl_points += current_stop - entry_price
                    return True, EXIT_SL, i, pnl_points, tp1_hit, current_stop, remaining_qty

                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if low_1m[i] <= current_stop:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, i, pnl_points, tp1_hit, current_stop, remaining_qty
        else:
            sl_hit = high_1m[i] >= current_stop
            tp1_trigger = low_1m[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_1m[i] <= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_1m[i], low_1m[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = high_1m[i] >= current_stop

            if is_flat and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_1m[i]) * (remaining_qty / qty)
                    return True, EXIT_TP1_EOD, i, pnl_points, tp1_hit, current_stop, remaining_qty
                else:
                    pnl_points += entry_price - close_1m[i]
                    return True, EXIT_EOD, i, pnl_points, tp1_hit, current_stop, remaining_qty

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return True, EXIT_SL, i, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = high_1m[i] >= current_stop
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return True, EXIT_TP2_SINGLE, i, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return True, EXIT_TP1_BE, i, pnl_points, tp1_hit, current_stop, remaining_qty
            else:
                if sl_hit and tp1_trigger:
                    # Ambiguous at 1m — try 30s first, then direct 1s fallback
                    if has_30s and i < len(map_1m_30s):
                        s30 = map_1m_30s[i, 0]
                        e30 = map_1m_30s[i, 1]
                        if e30 > s30:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_30s(
                                high_30s, low_30s, close_30s,
                                high_1s, low_1s, close_1s,
                                map_30s_1s, has_1s, s30, e30,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            if res:
                                return True, et, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    elif has_1s and i < len(map_1m_1s):
                        s1s = map_1m_1s[i, 0]
                        e1s = map_1m_1s[i, 1]
                        if e1s > s1s:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1s(
                                high_1s, low_1s, close_1s, s1s, e1s,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            if res:
                                return True, et, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    # Fallback: pessimistic
                    pnl_points += entry_price - current_stop
                    return True, EXIT_SL, i, pnl_points, tp1_hit, current_stop, remaining_qty

                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_1m[i], low_1m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if high_1m[i] >= current_stop:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, i, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, i, pnl_points, tp1_hit, current_stop, remaining_qty

    return False, -1, -1, pnl_points, tp1_hit, current_stop, remaining_qty


@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model='numpy')
def _simulate_single_trade_hierarchical(
    high_5m: np.ndarray,
    low_5m: np.ndarray,
    close_5m: np.ndarray,
    entry_bar_start: int,
    entry_bar_end: int,
    flat_bar_start: int,
    last_bar: int,
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    close_1m: np.ndarray,
    high_30s: np.ndarray,
    low_30s: np.ndarray,
    close_30s: np.ndarray,
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    map_5m_1m: np.ndarray,
    map_1m_30s: np.ndarray,
    map_30s_1s: np.ndarray,
    map_1m_1s: np.ndarray,
    has_30s: bool,
    has_1s: bool,
    direction: int,
    entry_price: float,
    stop_price: float,
    tp1_price: float,
    tp2_price: float,
    be_price: float,
    is_single: bool,
    qty: float,
    half_qty: float,
    point_value: float,
    commission: float,
    pre_entry_cancel_requires_new_sweep: bool,
    pre_entry_new_high_sweep_5m: np.ndarray,
    pre_entry_new_low_sweep_5m: np.ndarray,
    trail_mode: int,
    trail_trigger_r: float,
    trail_stop_r: float,
    trail_step_r: float,
    trail_gap_r: float,
    trail_atr_points: float,
    internal_swing_level: float = 1e38,
    cancel_on_swing: bool = False,
    pre_entry_cancel_target_price: float = np.nan,
) -> tuple:
    """Hierarchical fill+exit simulation: 5m primary, 1m on ambiguous bars, 30s on ambiguous 1m bars, 1s on ambiguous 30s bars.

    Fill is detected at the 5m level. When a bar simultaneously touches two price
    objectives (e.g. entry+SL, SL+TP1), we drill into the 1m sub-bars of that
    specific bar. If the conflict persists at 1m, we drill into 1s.

    Returns (fill_bar_5m, exit_type, exit_bar_5m, pnl_points, fill_1m_idx, exit_1m_idx).
    Same tuple shape as _simulate_single_trade for drop-in compatibility.
    """
    risk_pts = abs(entry_price - stop_price)
    if risk_pts <= 0:
        return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0

    # Phase 1: Scan for fill at 5m level
    fill_bar_5m = -1
    pre_entry_target_touched = False
    pre_entry_sweep_seen = False
    for i in range(entry_bar_start, min(entry_bar_end + 1, last_bar + 1)):
        if direction == 1:
            if low_5m[i] <= entry_price:
                fill_bar_5m = i
                break
        else:
            if high_5m[i] >= entry_price:
                fill_bar_5m = i
                break
        # Cancel check: swing swept on a non-fill bar
        if cancel_on_swing:
            if direction == 1 and high_5m[i] >= internal_swing_level:
                return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0
            elif direction == -1 and low_5m[i] <= internal_swing_level:
                return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0
        if not np.isnan(pre_entry_cancel_target_price):
            if direction == 1:
                if pre_entry_cancel_requires_new_sweep and pre_entry_new_low_sweep_5m[i]:
                    pre_entry_sweep_seen = True
                if high_5m[i] >= pre_entry_cancel_target_price:
                    if not pre_entry_cancel_requires_new_sweep:
                        return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0
                    pre_entry_target_touched = True
                if pre_entry_target_touched and pre_entry_sweep_seen:
                    return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0
            else:
                if pre_entry_cancel_requires_new_sweep and pre_entry_new_high_sweep_5m[i]:
                    pre_entry_sweep_seen = True
                if low_5m[i] <= pre_entry_cancel_target_price:
                    if not pre_entry_cancel_requires_new_sweep:
                        return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0
                    pre_entry_target_touched = True
                if pre_entry_target_touched and pre_entry_sweep_seen:
                    return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0

    if fill_bar_5m == -1:
        return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0

    # State
    tp1_hit = False
    be_triggered = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    # Precompute flat_start in 1m index (used for drill-down flat detection)
    flat_5m_clamped = min(flat_bar_start, len(map_5m_1m) - 1)
    flat_start_1m = map_5m_1m[flat_5m_clamped, 0]

    # 1m fill bar — initialised here so it's available for Phase 2b returns
    fill_bar_1m = -1

    # Phase 2a: Scan fill bar's remaining 1m sub-bars (handles fill+exit same 5m bar)
    if fill_bar_5m < len(map_5m_1m):
        s1m = map_5m_1m[fill_bar_5m, 0]
        e1m = map_5m_1m[fill_bar_5m, 1]

        # Find which 1m bar within the fill bar triggered the fill
        fill_bar_1m = -1
        for j in range(s1m, e1m):
            if direction == 1:
                if low_1m[j] <= entry_price:
                    fill_bar_1m = j
                    break
            else:
                if high_1m[j] >= entry_price:
                    fill_bar_1m = j
                    break

        if fill_bar_1m >= 0 and fill_bar_1m < e1m:
            # Include fill bar in exit scanning (SL/TP can hit on same bar as fill)
            res, et, exit_1m, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1m(
                high_1m, low_1m, close_1m,
                high_30s, low_30s, close_30s,
                high_1s, low_1s, close_1s,
                map_1m_30s, map_30s_1s, map_1m_1s,
                has_30s, has_1s,
                fill_bar_1m, e1m,
                flat_start_1m,
                direction, entry_price, risk_pts, current_stop,
                tp1_price, tp2_price, be_price,
                tp1_hit, is_single, qty, half_qty, remaining_qty, pnl_points,
                trail_mode, trail_trigger_r, trail_stop_r,
                trail_step_r, trail_gap_r, trail_atr_points,
            )
            if res:
                return fill_bar_5m, et, fill_bar_5m, pnl_points, float(fill_bar_1m), float(exit_1m)

    # Phase 2b: Scan subsequent 5m bars
    for i in range(fill_bar_5m + 1, last_bar + 1):
        # Swing BE trigger
        if not be_triggered and not tp1_hit:
            if direction == 1 and high_5m[i] >= internal_swing_level:
                be_triggered = True
                current_stop = be_price
            elif direction == -1 and low_5m[i] <= internal_swing_level:
                be_triggered = True
                current_stop = be_price

        is_flat_bar = i >= flat_bar_start

        if direction == 1:
            sl_hit = low_5m[i] <= current_stop
            tp1_trigger = high_5m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_5m[i] >= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_5m[i], low_5m[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = low_5m[i] <= current_stop

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_5m[i] - entry_price) * (remaining_qty / qty)
                    return fill_bar_5m, EXIT_TP1_EOD, i, pnl_points, float(fill_bar_1m), -1.0
                else:
                    pnl_points += close_5m[i] - entry_price
                    return fill_bar_5m, EXIT_EOD, i, pnl_points, float(fill_bar_1m), -1.0

            if sl_hit and not tp1_hit:
                if be_triggered:
                    return fill_bar_5m, EXIT_BE_SL, i, 0.0, float(fill_bar_1m), -1.0
                pnl_points += current_stop - entry_price
                return fill_bar_5m, EXIT_SL, i, pnl_points, float(fill_bar_1m), -1.0

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_5m[i], low_5m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = low_5m[i] <= current_stop
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return fill_bar_5m, EXIT_TP2_SINGLE, i, pnl_points, float(fill_bar_1m), -1.0
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, float(fill_bar_1m), -1.0
            else:
                if sl_hit and tp1_trigger:
                    # Ambiguous 5m bar — drill to 1m
                    if i < len(map_5m_1m):
                        s1m = map_5m_1m[i, 0]
                        e1m = map_5m_1m[i, 1]
                        if e1m > s1m:
                            res, et, _exit_1m, pnl_out, tp1_out, cs_out, rq_out = _drill_down_1m(
                                high_1m, low_1m, close_1m,
                                high_30s, low_30s, close_30s,
                                high_1s, low_1s, close_1s,
                                map_1m_30s, map_30s_1s, map_1m_1s,
                                has_30s, has_1s,
                                s1m, e1m, flat_start_1m,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            pnl_points = pnl_out
                            tp1_hit = tp1_out
                            current_stop = cs_out
                            remaining_qty = rq_out
                            if res:
                                return fill_bar_5m, et, i, pnl_points, float(fill_bar_1m), float(_exit_1m)
                            continue
                    # No 1m data for this bar — pessimistic
                    pnl_points += current_stop - entry_price
                    return fill_bar_5m, EXIT_SL, i, pnl_points, float(fill_bar_1m), -1.0

                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_5m[i], low_5m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if low_5m[i] <= current_stop:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, float(fill_bar_1m), -1.0
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, float(fill_bar_1m), -1.0
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_TP2, i, pnl_points, float(fill_bar_1m), -1.0

        else:  # SHORT
            sl_hit = high_5m[i] >= current_stop
            tp1_trigger = low_5m[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_5m[i] <= tp2_price
            if tp1_hit:
                current_stop = _apply_runner_trail_stop(
                    direction, entry_price, risk_pts, current_stop,
                    high_5m[i], low_5m[i],
                    trail_mode, trail_trigger_r, trail_stop_r,
                    trail_step_r, trail_gap_r, trail_atr_points,
                )
                sl_hit = high_5m[i] >= current_stop

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_5m[i]) * (remaining_qty / qty)
                    return fill_bar_5m, EXIT_TP1_EOD, i, pnl_points, float(fill_bar_1m), -1.0
                else:
                    pnl_points += entry_price - close_5m[i]
                    return fill_bar_5m, EXIT_EOD, i, pnl_points, float(fill_bar_1m), -1.0

            if sl_hit and not tp1_hit:
                if be_triggered:
                    return fill_bar_5m, EXIT_BE_SL, i, 0.0, float(fill_bar_1m), -1.0
                pnl_points += entry_price - current_stop
                return fill_bar_5m, EXIT_SL, i, pnl_points, float(fill_bar_1m), -1.0

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_5m[i], low_5m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    sl_hit = high_5m[i] >= current_stop
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return fill_bar_5m, EXIT_TP2_SINGLE, i, pnl_points, float(fill_bar_1m), -1.0
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, float(fill_bar_1m), -1.0
            else:
                if sl_hit and tp1_trigger:
                    if i < len(map_5m_1m):
                        s1m = map_5m_1m[i, 0]
                        e1m = map_5m_1m[i, 1]
                        if e1m > s1m:
                            res, et, _exit_1m, pnl_out, tp1_out, cs_out, rq_out = _drill_down_1m(
                                high_1m, low_1m, close_1m,
                                high_30s, low_30s, close_30s,
                                high_1s, low_1s, close_1s,
                                map_1m_30s, map_30s_1s, map_1m_1s,
                                has_30s, has_1s,
                                s1m, e1m, flat_start_1m,
                                direction, entry_price, risk_pts, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                                trail_mode, trail_trigger_r, trail_stop_r,
                                trail_step_r, trail_gap_r, trail_atr_points,
                            )
                            pnl_points = pnl_out
                            tp1_hit = tp1_out
                            current_stop = cs_out
                            remaining_qty = rq_out
                            if res:
                                return fill_bar_5m, et, i, pnl_points, float(fill_bar_1m), float(_exit_1m)
                            continue
                    pnl_points += entry_price - current_stop
                    return fill_bar_5m, EXIT_SL, i, pnl_points, float(fill_bar_1m), -1.0

                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    be_triggered = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    current_stop = _apply_runner_trail_stop(
                        direction, entry_price, risk_pts, current_stop,
                        high_5m[i], low_5m[i],
                        trail_mode, trail_trigger_r, trail_stop_r,
                        trail_step_r, trail_gap_r, trail_atr_points,
                    )
                    if high_5m[i] >= current_stop:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, float(fill_bar_1m), -1.0
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, float(fill_bar_1m), -1.0
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_TP2, i, pnl_points, float(fill_bar_1m), -1.0

    # Reached end without exit
    if direction == 1:
        pnl_points += close_5m[last_bar] - entry_price
    else:
        pnl_points += entry_price - close_5m[last_bar]
    return fill_bar_5m, EXIT_EOD, last_bar, pnl_points, float(fill_bar_1m), -1.0


@dataclass
class _PreparedCandidate:
    """Candidate with all trade params computed, ready for simulation."""

    cand: "_SetupCandidate"
    sd: int  # session_day_id
    direction: int
    entry_price: float
    stop_price: float
    tp1_price: float
    tp2_price: float
    be_price: float
    risk_pts: float
    qty: float
    half_qty: float
    is_single: bool
    gap_size: float
    entry_bar_start: int
    entry_bar_end: int
    flat_bar_start: int
    last_bar: int
    trail_atr_points: float = 0.0
    # Bar magnifier: 1m bar boundaries (-1 when magnifier is off)
    entry_start_1m: int = -1
    entry_end_1m: int = -1
    flat_start_1m: int = -1
    last_bar_1m: int = -1
    # Internal swing level for LSI BE trigger (1e38/-1e38 = disabled)
    internal_swing_level: float = 1e38
    cancel_on_swing: bool = False
    pre_entry_cancel_target_price: float = np.nan


# ---------------------------------------------------------------------------
# Setup candidate extraction (vectorized + per-day grouping)
# ---------------------------------------------------------------------------

@dataclass
class _SetupCandidate:
    """Internal setup record produced by signal generation."""

    date_str: str
    session: str
    direction: int
    signal_bar: int
    entry_price: float
    gap_size: float
    daily_atr: float
    orb_range: float
    structural_stop_price: float = 0.0
    lsi_absolute_stop_price: float = 0.0
    # LSI overlay data (0.0/-1 for non-LSI candidates)
    lsi_swept_level: float = 0.0
    lsi_fvg_top: float = 0.0
    lsi_fvg_bottom: float = 0.0
    lsi_fvg_bar: int = -1
    lsi_sweep_bar: int = -1
    lsi_confirmation_type: str = ""
    lsi_cisd_level: float = 0.0
    lsi_cisd_bar: int = -1
    lsi_internal_swing_level: float = 1e38  # sentinel: 1e38=disabled (longs), -1e38=disabled (shorts)
    reference_level_name: str = ""
    reference_level_price: float = 0.0
    htf_level_time: str = ""
    htf_level_price: float = 0.0
    htf_level_side: str = ""
    htf_level_tf_minutes: int = 0
    fvg_to_inversion_bars: int = 0
    sweep_to_inversion_bars: int = 0
    inversion_ordinal: int = 0
    lsi_lrlr_present: bool = False
    lsi_lrlr_level_count: int = 0
    lsi_lrlr_nearest_level_price: float = 0.0
    lsi_lrlr_farthest_level_price: float = 0.0
    lsi_lrlr_span_bars: int = 0
    lsi_lrlr_price_span_atr: float = 0.0
    lsi_lrlr_slope_atr_per_bar: float = 0.0
    lsi_lrlr_fit_error_atr: float = 0.0
    lsi_lrlr_tp1_path_present: bool = False
    lsi_lrlr_nearest_tp1_gap_atr: float = 0.0


@dataclass(frozen=True)
class _LSILRLRSettings:
    enabled: bool
    gate: str
    swing_n_left: int
    swing_n_right: int
    min_pivots: int
    lookback_minutes: int
    max_pivot_gap_minutes: int
    max_cluster_span_minutes: int
    max_price_span_atr: float
    monotonic_tolerance_atr: float
    line_tolerance_atr: float
    tp1_path_enabled: bool
    tp1_buffer_atr: float


_LSI_GAP_STOP_MULTIPLIERS = {
    "gap_1x": 1.0,
    "gap_2x": 2.0,
    "gap_3x": 3.0,
    "gap_4x": 4.0,
}

_LSI_STRUCT_STOP_FRACTIONS = {
    "struct_50pct": 0.50,
    "struct_75pct": 0.75,
}


def _stop_from_distance(direction: int, entry_price: float, stop_dist: float) -> float:
    return entry_price - stop_dist if direction == 1 else entry_price + stop_dist


def _resolve_lsi_orb_range(orb_high_value: float, orb_low_value: float) -> float:
    if not np.isfinite(orb_high_value) or not np.isfinite(orb_low_value):
        return 0.0
    orb_range = float(orb_high_value - orb_low_value)
    if not np.isfinite(orb_range) or orb_range <= 0.0:
        return 0.0
    return orb_range


def _resolve_lsi_session_stop_points(
    *,
    session: SessionConfig,
    daily_atr: float,
    orb_range: float,
) -> tuple[float, float]:
    atr_points = np.nan
    if session.stop_atr_pct > 0.0 and np.isfinite(daily_atr) and daily_atr > 0.0:
        atr_points = (float(session.stop_atr_pct) / 100.0) * float(daily_atr)

    orb_points = np.nan
    if session.stop_orb_pct > 0.0 and np.isfinite(orb_range) and orb_range > 0.0:
        orb_points = (float(session.stop_orb_pct) / 100.0) * float(orb_range)

    return float(atr_points), float(orb_points)


def _resolve_lsi_stop_price(
    *,
    direction: int,
    entry_price: float,
    absolute_stop_price: float,
    fvg_stop_price: float,
    gap_size: float,
    atr_points: float = np.nan,
    orb_points: float = np.nan,
    stop_mode: str,
) -> float:
    structural_dist = abs(entry_price - absolute_stop_price)
    if structural_dist <= 0.0:
        return absolute_stop_price

    if stop_mode == "absolute":
        return absolute_stop_price

    if stop_mode == "fvg":
        chosen_stop = fvg_stop_price
    elif stop_mode == "atr_pct":
        if not np.isfinite(atr_points) or atr_points <= 0.0:
            return absolute_stop_price
        stop_dist = min(float(atr_points), structural_dist)
        chosen_stop = _stop_from_distance(direction, entry_price, stop_dist)
    elif stop_mode == "orb_pct":
        if not np.isfinite(orb_points) or orb_points <= 0.0:
            return absolute_stop_price
        stop_dist = min(float(orb_points), structural_dist)
        chosen_stop = _stop_from_distance(direction, entry_price, stop_dist)
    elif stop_mode in _LSI_GAP_STOP_MULTIPLIERS:
        raw_dist = max(0.0, gap_size * _LSI_GAP_STOP_MULTIPLIERS[stop_mode])
        stop_dist = min(raw_dist, structural_dist)
        chosen_stop = _stop_from_distance(direction, entry_price, stop_dist)
    elif stop_mode in _LSI_STRUCT_STOP_FRACTIONS:
        stop_dist = structural_dist * _LSI_STRUCT_STOP_FRACTIONS[stop_mode]
        chosen_stop = _stop_from_distance(direction, entry_price, stop_dist)
    else:
        raise ValueError(f"Unsupported LSI stop mode {stop_mode!r}")

    chosen_dist = abs(entry_price - chosen_stop)
    if chosen_dist <= 0.0:
        return absolute_stop_price
    if chosen_dist > structural_dist:
        return absolute_stop_price
    return chosen_stop


def _resolve_lsi_target_distances(
    *,
    actual_risk_pts: float,
    structural_risk_pts: float,
    rr: float,
    tp1_ratio: float,
    target_mode: str,
) -> tuple[float, float]:
    target_basis_pts = actual_risk_pts
    if target_mode == "structural" and structural_risk_pts > 0.0:
        target_basis_pts = max(structural_risk_pts, actual_risk_pts)

    tp1_dist = rr * target_basis_pts * tp1_ratio
    tp1_dist = max(tp1_dist, actual_risk_pts)

    tp2_dist = rr * target_basis_pts
    if target_mode == "structural":
        tp2_dist = max(tp2_dist, 1.5 * actual_risk_pts)

    return tp1_dist, tp2_dist


def _infer_bar_minutes(index: pd.DatetimeIndex) -> float:
    if len(index) < 2:
        return 1.0
    delta = index[1] - index[0]
    minutes = delta.total_seconds() / 60.0
    return minutes if minutes > 0.0 else 1.0


def _resolve_lsi_entry_mode(
    *,
    entry_mode: str,
    bar_minutes: float,
    sweep_to_inversion_bars: int,
    close_on_sweep_to_inversion_minutes: int,
) -> str:
    if entry_mode != "timed_hybrid":
        return entry_mode
    if close_on_sweep_to_inversion_minutes <= 0:
        return "fvg_limit"
    inversion_minutes = float(sweep_to_inversion_bars) * float(bar_minutes)
    if inversion_minutes <= float(close_on_sweep_to_inversion_minutes):
        return "close"
    return "fvg_limit"


def _is_lsi_level_limit_entry_mode(entry_mode: str) -> bool:
    return entry_mode in {"fvg_limit", "level_limit"}


def _build_lrlr_settings(config: StrategyConfig) -> _LSILRLRSettings:
    return _LSILRLRSettings(
        enabled=bool(config.lsi_lrlr_enabled),
        gate=str(config.lsi_lrlr_gate),
        swing_n_left=int(config.lsi_lrlr_swing_n_left),
        swing_n_right=int(config.lsi_lrlr_swing_n_right),
        min_pivots=int(config.lsi_lrlr_min_pivots),
        lookback_minutes=int(config.lsi_lrlr_lookback_minutes),
        max_pivot_gap_minutes=int(config.lsi_lrlr_max_pivot_gap_minutes),
        max_cluster_span_minutes=int(config.lsi_lrlr_max_cluster_span_minutes),
        max_price_span_atr=float(config.lsi_lrlr_max_price_span_atr),
        monotonic_tolerance_atr=float(config.lsi_lrlr_monotonic_tolerance_atr),
        line_tolerance_atr=float(config.lsi_lrlr_line_tolerance_atr),
        tp1_path_enabled=bool(config.lsi_lrlr_tp1_path_enabled),
        tp1_buffer_atr=float(config.lsi_lrlr_tp1_buffer_atr),
    )


def _build_lrlr_pivot_arrays(
    high: np.ndarray,
    low: np.ndarray,
    settings: _LSILRLRSettings,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if not settings.enabled:
        empty_int = np.empty(0, dtype=np.int64)
        empty_float = np.empty(0, dtype=np.float64)
        return empty_int, empty_int, empty_float, empty_int, empty_int, empty_float

    swing_highs = detect_swing_highs(high, settings.swing_n_left, settings.swing_n_right)
    swing_lows = detect_swing_lows(low, settings.swing_n_left, settings.swing_n_right)

    high_confirm_idx = np.flatnonzero(swing_highs).astype(np.int64)
    high_pivot_idx = (high_confirm_idx - settings.swing_n_right).astype(np.int64)
    valid_high = high_pivot_idx >= 0
    high_confirm_idx = high_confirm_idx[valid_high]
    high_pivot_idx = high_pivot_idx[valid_high]
    high_pivot_price = high[high_pivot_idx].astype(np.float64, copy=False)

    low_confirm_idx = np.flatnonzero(swing_lows).astype(np.int64)
    low_pivot_idx = (low_confirm_idx - settings.swing_n_right).astype(np.int64)
    valid_low = low_pivot_idx >= 0
    low_confirm_idx = low_confirm_idx[valid_low]
    low_pivot_idx = low_pivot_idx[valid_low]
    low_pivot_price = low[low_pivot_idx].astype(np.float64, copy=False)

    return (
        high_confirm_idx,
        high_pivot_idx,
        high_pivot_price,
        low_confirm_idx,
        low_pivot_idx,
        low_pivot_price,
    )


def _build_target_pivot_arrays(
    high: np.ndarray,
    low: np.ndarray,
    n_bars: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if n_bars < 1:
        empty_int = np.empty(0, dtype=np.int64)
        empty_float = np.empty(0, dtype=np.float64)
        return empty_int, empty_int, empty_float, empty_int, empty_int, empty_float

    swing_highs = detect_swing_highs(high, n_bars, n_bars)
    swing_lows = detect_swing_lows(low, n_bars, n_bars)

    high_confirm_idx = np.flatnonzero(swing_highs).astype(np.int64)
    high_pivot_idx = (high_confirm_idx - n_bars).astype(np.int64)
    valid_high = high_pivot_idx >= 0
    high_confirm_idx = high_confirm_idx[valid_high]
    high_pivot_idx = high_pivot_idx[valid_high]
    high_pivot_price = high[high_pivot_idx].astype(np.float64, copy=False)

    low_confirm_idx = np.flatnonzero(swing_lows).astype(np.int64)
    low_pivot_idx = (low_confirm_idx - n_bars).astype(np.int64)
    valid_low = low_pivot_idx >= 0
    low_confirm_idx = low_confirm_idx[valid_low]
    low_pivot_idx = low_pivot_idx[valid_low]
    low_pivot_price = low[low_pivot_idx].astype(np.float64, copy=False)

    return (
        high_confirm_idx,
        high_pivot_idx,
        high_pivot_price,
        low_confirm_idx,
        low_pivot_idx,
        low_pivot_price,
    )


def _resolve_lsi_left_structure_target_distances(
    *,
    direction: int,
    entry_price: float,
    actual_risk_pts: float,
    left_end_bar: int,
    high: np.ndarray,
    low: np.ndarray,
    pivot_arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    min_tick: float,
) -> tuple[float, float]:
    if left_end_bar <= 0 or actual_risk_pts <= 0.0:
        return actual_risk_pts, max(1.5 * actual_risk_pts, actual_risk_pts + min_tick)

    (
        high_confirm_idx,
        high_pivot_idx,
        high_pivot_price,
        low_confirm_idx,
        low_pivot_idx,
        low_pivot_price,
    ) = pivot_arrays

    if direction == 1:
        confirm_idx = high_confirm_idx
        pivot_idx = high_pivot_idx
        pivot_price = high_pivot_price
        path_prices = high
    else:
        confirm_idx = low_confirm_idx
        pivot_idx = low_pivot_idx
        pivot_price = low_pivot_price
        path_prices = low

    hi = int(np.searchsorted(confirm_idx, left_end_bar, side="right"))
    candidate_distances: list[float] = []
    for j in range(hi):
        bar = int(pivot_idx[j])
        price = float(pivot_price[j])
        if bar >= left_end_bar or not np.isfinite(price):
            continue
        if direction == 1:
            if price <= entry_price:
                continue
            if bar + 1 <= left_end_bar and np.max(path_prices[bar + 1:left_end_bar + 1]) > price:
                continue
            dist = price - entry_price
        else:
            if price >= entry_price:
                continue
            if bar + 1 <= left_end_bar and np.min(path_prices[bar + 1:left_end_bar + 1]) < price:
                continue
            dist = entry_price - price
        candidate_distances.append(float(dist))

    candidate_distances.sort()

    tp1_floor = actual_risk_pts
    tp1_dist = next((dist for dist in candidate_distances if dist >= tp1_floor), tp1_floor)

    tp2_floor = max(1.5 * actual_risk_pts, tp1_dist + max(min_tick, 1e-9))
    tp2_dist = next((dist for dist in candidate_distances if dist >= tp2_floor), tp2_floor)
    return tp1_dist, tp2_dist


def _resolve_lsi_candidate_target_distances(
    *,
    target_mode: str,
    direction: int,
    entry_price: float,
    actual_risk_pts: float,
    structural_risk_pts: float,
    rr: float,
    tp1_ratio: float,
    left_end_bar: int,
    high: np.ndarray,
    low: np.ndarray,
    pivot_arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None,
    min_tick: float,
) -> tuple[float, float]:
    if target_mode == "left_structure" and pivot_arrays is not None:
        return _resolve_lsi_left_structure_target_distances(
            direction=direction,
            entry_price=entry_price,
            actual_risk_pts=actual_risk_pts,
            left_end_bar=left_end_bar,
            high=high,
            low=low,
            pivot_arrays=pivot_arrays,
            min_tick=min_tick,
        )
    return _resolve_lsi_target_distances(
        actual_risk_pts=actual_risk_pts,
        structural_risk_pts=structural_risk_pts,
        rr=rr,
        tp1_ratio=tp1_ratio,
        target_mode=target_mode,
    )


def _detect_candidate_lrlr(
    *,
    high: np.ndarray,
    low: np.ndarray,
    bar_minutes: float,
    left_end_bar: int,
    direction: int,
    entry_price: float,
    tp1_price: float | None,
    daily_atr: float,
    settings: _LSILRLRSettings,
    pivot_arrays: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
) -> LRLRResult:
    if not settings.enabled or left_end_bar <= 0:
        return LRLRResult(False)

    (
        high_confirm_idx,
        high_pivot_idx,
        high_pivot_price,
        low_confirm_idx,
        low_pivot_idx,
        low_pivot_price,
    ) = pivot_arrays
    return detect_lrlr_cluster(
        high=high,
        low=low,
        pivot_high_confirm_idx=high_confirm_idx,
        pivot_high_idx=high_pivot_idx,
        pivot_high_price=high_pivot_price,
        pivot_low_confirm_idx=low_confirm_idx,
        pivot_low_idx=low_pivot_idx,
        pivot_low_price=low_pivot_price,
        direction=direction,
        entry_price=entry_price,
        tp1_price=tp1_price,
        left_end_bar=left_end_bar,
        daily_atr=daily_atr,
        bar_minutes=bar_minutes,
        min_levels=settings.min_pivots,
        lookback_minutes=settings.lookback_minutes,
        max_pivot_gap_minutes=settings.max_pivot_gap_minutes,
        max_cluster_span_minutes=settings.max_cluster_span_minutes,
        max_price_span_atr=settings.max_price_span_atr,
        monotonic_tolerance_atr=settings.monotonic_tolerance_atr,
        line_tolerance_atr=settings.line_tolerance_atr,
        tp1_buffer_atr=settings.tp1_buffer_atr,
    )


def _lrlr_gate_blocks(match: LRLRResult, settings: _LSILRLRSettings) -> bool:
    if not settings.enabled or not settings.gate:
        return False
    effective_present = bool(match.present)
    if settings.tp1_path_enabled:
        effective_present = effective_present and bool(match.tp1_path_present)
    if settings.gate == "require":
        return not effective_present
    if settings.gate == "exclude":
        return effective_present
    return False


def _session_key(session: SessionConfig) -> tuple:
    """Hashable key identifying a session's time windows (independent of trade params)."""
    return (
        session.name,
        session.rth_start,
        session.sweep_start, session.sweep_end,
        session.orb_start, session.orb_end,
        session.entry_start, session.entry_end,
        session.flat_start, session.flat_end,
    )


def _fvg_key(session: SessionConfig, config: StrategyConfig) -> tuple:
    """Hashable key identifying a unique FVG signal computation."""
    return (
        _session_key(session),
        config.atr_length,
        session.min_gap_atr_pct,
        getattr(session, "min_gap_orb_pct", 0.0),
        config.impulse_close_filter,
    )


def _fvg_no_orb_key(session: SessionConfig, config: StrategyConfig) -> tuple:
    """Hashable key identifying a unique no-ORB FVG computation."""
    return (
        config.atr_length,
        session.min_gap_atr_pct,
    )


def _htf_key(session: SessionConfig, config: StrategyConfig) -> tuple:
    """Hashable key identifying a unique HTF level computation."""
    return (
        config.htf_level_tf_minutes,
        config.htf_n_left,
        session.sweep_start,
        session.sweep_end,
    )


def _eqhl_key(session: SessionConfig, config: StrategyConfig) -> tuple:
    """Hashable key identifying a unique equal-high/low level computation."""
    return (
        config.eqhl_level_tf_minutes,
        config.eqhl_n_left,
        config.eqhl_tolerance_ticks,
        config.eqhl_min_touches,
        config.eqhl_lookback_bars,
        session.sweep_start,
        session.sweep_end,
    )


def _compute_previous_day_instance_ids(timestamps: pd.DatetimeIndex) -> np.ndarray:
    """Return a per-bar id for the currently published previous-day level."""
    return np.cumsum(compute_trading_days(timestamps)) - 1


def _compute_completed_session_instance_ids(
    timestamps: pd.DatetimeIndex,
    session: SessionConfig,
) -> np.ndarray:
    """Return a per-bar id for the most recently completed session instance."""
    masks = compute_session_masks(timestamps, session)
    in_rth = masks["in_rth"]
    instance_ids = np.full(len(timestamps), -1, dtype=np.int64)
    completed_count = -1

    for i in range(len(timestamps)):
        if i > 0 and in_rth[i - 1] and not in_rth[i]:
            completed_count += 1
        instance_ids[i] = completed_count

    return instance_ids


def _compute_previous_week_instance_ids(timestamps: pd.DatetimeIndex) -> np.ndarray:
    """Return a per-bar id for the currently published previous-week level."""
    localized = timestamps.tz_convert("America/New_York") if timestamps.tz is not None else timestamps.tz_localize("America/New_York")
    week_periods = localized.tz_localize(None).to_period("W-SUN")
    new_week = np.empty(len(timestamps), dtype=bool)
    new_week[0] = True
    new_week[1:] = week_periods[1:] != week_periods[:-1]
    return np.cumsum(new_week) - 1


def _reference_levels_need_data(level_names: tuple[str, ...] | None) -> bool:
    return bool(level_names) and any(level_name in DATA_REF_LSI_LEVELS for level_name in level_names)


def _build_static_reference_level_cache(
    df: pd.DataFrame,
    timestamps: pd.DatetimeIndex,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    levels = compute_reference_levels(df)
    prev_day_ids = _compute_previous_day_instance_ids(timestamps)
    prev_week_ids = _compute_previous_week_instance_ids(timestamps)
    asia_ids = _compute_completed_session_instance_ids(timestamps, ASIA_SESSION)
    london_ids = _compute_completed_session_instance_ids(timestamps, LDN_SESSION)
    new_york_ids = _compute_completed_session_instance_ids(timestamps, NY_SESSION)
    instance_ids = {
        "previous_day_high": prev_day_ids,
        "previous_day_low": prev_day_ids,
        "previous_week_high": prev_week_ids,
        "previous_week_low": prev_week_ids,
        "asia_high": asia_ids,
        "asia_low": asia_ids,
        "london_high": london_ids,
        "london_low": london_ids,
        "new_york_high": new_york_ids,
        "new_york_low": new_york_ids,
    }
    return levels, instance_ids


def _resolve_reference_levels(
    df: pd.DataFrame,
    timestamps: pd.DatetimeIndex,
    *,
    session: SessionConfig,
    selected_level_names: tuple[str, ...],
    signal_df_1m: pd.DataFrame | None,
    atr_length: int,
    data_sweep_min_daily_atr_pct: float,
    data_sweep_require_session_extreme: bool,
    data_sweep_event_types: tuple[str, ...],
    data_sweep_release_window_minutes: int,
    signal_cache: dict | None = None,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    if signal_cache is not None and "reference_levels" in signal_cache:
        reference_levels = dict(signal_cache["reference_levels"])
        reference_instance_ids = dict(signal_cache["reference_level_instance_ids"])
    else:
        reference_levels, reference_instance_ids = _build_static_reference_level_cache(df, timestamps)

    if not _reference_levels_need_data(selected_level_names):
        return reference_levels, reference_instance_ids

    data_key = (
        _session_key(session),
        int(atr_length),
        float(data_sweep_min_daily_atr_pct),
        bool(data_sweep_require_session_extreme),
        tuple(str(event_type).strip().upper() for event_type in data_sweep_event_types if str(event_type).strip()),
        int(data_sweep_release_window_minutes),
    )
    data_cache = signal_cache.get("data_reference_levels") if signal_cache is not None else None
    cached_data = data_cache.get(data_key) if data_cache is not None else None
    if cached_data is None and signal_df_1m is None:
        raise ValueError(
            "signal_df_1m is required when data_high/data_low reference levels are enabled."
        )
    if cached_data is None:
        data_levels, data_ids = compute_data_sweep_levels(
            df,
            signal_df_1m,
            atr_length=atr_length,
            min_daily_atr_pct=data_sweep_min_daily_atr_pct,
            session=session,
            require_session_extreme=data_sweep_require_session_extreme,
            event_types=data_sweep_event_types,
            release_window_minutes=data_sweep_release_window_minutes,
        )
    else:
        data_levels = cached_data["levels"]
        data_ids = cached_data["instance_ids"]

    reference_levels.update(data_levels)
    reference_instance_ids["data_high"] = data_ids["data_high"]
    reference_instance_ids["data_low"] = data_ids["data_low"]
    return reference_levels, reference_instance_ids


def _select_recent_htf_sweep(
    events: list[dict],
    *,
    side: str,
) -> dict | None:
    """Pick the freshest sweep event, preferring the outermost level on ties."""
    if not events:
        return None
    latest_bar = max(int(event["sweep_bar"]) for event in events)
    latest_events = [event for event in events if int(event["sweep_bar"]) == latest_bar]
    if side == "high":
        return max(latest_events, key=lambda event: (float(event["level_price"]), -int(event["source_rank"])))
    return min(latest_events, key=lambda event: (float(event["level_price"]), int(event["source_rank"])))


def _build_htf_lsi_level_sources(
    *,
    htf_levels: dict[str, np.ndarray] | None,
    eqhl_levels: dict[str, np.ndarray] | None,
    reference_levels: dict[str, np.ndarray] | None,
    reference_instance_ids: dict[str, np.ndarray] | None,
    selected_reference_level_names: tuple[str, ...],
    include_htf_levels: bool,
    include_eqhl_levels: bool,
    htf_level_tf_minutes: int,
) -> tuple[list[dict], list[dict]]:
    """Build the configured HTF-LSI sweep sources split by side."""
    high_level_sources: list[dict] = []
    low_level_sources: list[dict] = []
    source_rank = 0

    if include_htf_levels:
        if htf_levels is None:
            raise ValueError("htf_levels are required when include_htf_levels=True.")
        high_level_sources.append(
            {
                "source_name": "htf_high",
                "level_name": "",
                "prices": htf_levels["active_high_price"],
                "instance_ids": htf_levels["active_high_instance_id"],
                "times": htf_levels["active_high_level_time"],
                "tf_minutes": htf_level_tf_minutes,
                "source_rank": source_rank,
            }
        )
        source_rank += 1
        low_level_sources.append(
            {
                "source_name": "htf_low",
                "level_name": "",
                "prices": htf_levels["active_low_price"],
                "instance_ids": htf_levels["active_low_instance_id"],
                "times": htf_levels["active_low_level_time"],
                "tf_minutes": htf_level_tf_minutes,
                "source_rank": source_rank,
            }
        )
        source_rank += 1

    if include_eqhl_levels:
        if eqhl_levels is None:
            raise ValueError("eqhl_levels are required when include_eqhl_levels=True.")
        eqhl_tf_minutes = int(eqhl_levels["tf_minutes"])
        high_level_sources.append(
            {
                "source_name": f"equal_high_{eqhl_tf_minutes}m",
                "level_name": f"equal_high_{eqhl_tf_minutes}m",
                "prices": eqhl_levels["active_high_price"],
                "instance_ids": eqhl_levels["active_high_instance_id"],
                "times": eqhl_levels["active_high_level_time"],
                "tf_minutes": eqhl_tf_minutes,
                "source_rank": source_rank,
            }
        )
        source_rank += 1
        low_level_sources.append(
            {
                "source_name": f"equal_low_{eqhl_tf_minutes}m",
                "level_name": f"equal_low_{eqhl_tf_minutes}m",
                "prices": eqhl_levels["active_low_price"],
                "instance_ids": eqhl_levels["active_low_instance_id"],
                "times": eqhl_levels["active_low_level_time"],
                "tf_minutes": eqhl_tf_minutes,
                "source_rank": source_rank,
            }
        )
        source_rank += 1

    if selected_reference_level_names:
        if reference_levels is None or reference_instance_ids is None:
            raise ValueError(
                "reference_levels and reference_instance_ids are required when HTF-LSI reference levels are enabled."
            )
        for level_name in selected_reference_level_names:
            if level_name not in reference_levels or level_name not in reference_instance_ids:
                raise ValueError(f"Missing cached HTF-LSI reference level arrays for {level_name!r}.")
            source = {
                "source_name": level_name,
                "level_name": level_name,
                "prices": reference_levels[level_name],
                "instance_ids": reference_instance_ids[level_name],
                "times": None,
                "tf_minutes": 0,
                "source_rank": source_rank,
            }
            source_rank += 1
            if level_name.endswith("_high"):
                high_level_sources.append(source)
            else:
                low_level_sources.append(source)

    return high_level_sources, low_level_sources


def _build_htf_lsi_new_sweep_flags(
    *,
    high: np.ndarray,
    low: np.ndarray,
    in_entry: np.ndarray,
    in_sweep: np.ndarray,
    high_level_sources: list[dict],
    low_level_sources: list[dict],
    stale_breach_consumes_pivot: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-bar flags for fresh HTF-LSI high-side and low-side sweeps."""
    n = len(high)
    new_high_sweep = np.zeros(n, dtype=bool)
    new_low_sweep = np.zeros(n, dtype=bool)

    level_state: dict[str, dict[str, int | bool]] = {
        source["source_name"]: {"instance_id": -10_000_000, "consumed": False}
        for source in (*high_level_sources, *low_level_sources)
    }

    for i in range(n):
        for source in high_level_sources:
            state = level_state[source["source_name"]]
            instance_ids = source["instance_ids"]
            instance_id = int(instance_ids[i]) if i < len(instance_ids) else -1
            if instance_id != state["instance_id"]:
                state["instance_id"] = instance_id
                state["consumed"] = False
            if state["consumed"] or instance_id < 0:
                continue
            level_price = float(source["prices"][i])
            if not np.isfinite(level_price) or high[i] <= level_price:
                continue
            valid_sweep = bool(in_sweep[i])
            if valid_sweep or stale_breach_consumes_pivot:
                state["consumed"] = True
            if valid_sweep and in_entry[i]:
                new_high_sweep[i] = True

        for source in low_level_sources:
            state = level_state[source["source_name"]]
            instance_ids = source["instance_ids"]
            instance_id = int(instance_ids[i]) if i < len(instance_ids) else -1
            if instance_id != state["instance_id"]:
                state["instance_id"] = instance_id
                state["consumed"] = False
            if state["consumed"] or instance_id < 0:
                continue
            level_price = float(source["prices"][i])
            if not np.isfinite(level_price) or low[i] >= level_price:
                continue
            valid_sweep = bool(in_sweep[i])
            if valid_sweep or stale_breach_consumes_pivot:
                state["consumed"] = True
            if valid_sweep and in_entry[i]:
                new_low_sweep[i] = True

    return new_high_sweep, new_low_sweep


def _build_htf_lsi_pre_entry_cancel_sweep_flags(
    *,
    df: pd.DataFrame,
    timestamps,
    masks: dict[str, np.ndarray],
    session_day_id: np.ndarray,
    session,
    config: StrategyConfig,
    signal_df_1m: pd.DataFrame | None,
    daily_atr: np.ndarray,
    _signal_cache: dict | None,
) -> tuple[np.ndarray, np.ndarray]:
    """Build fresh-sweep flags used by HTF-LSI pre-entry cancel rules."""
    n = len(df)
    empty = (np.zeros(n, dtype=bool), np.zeros(n, dtype=bool))

    if config.strategy != "htf_lsi":
        return empty

    htf_levels = None
    if config.htf_lsi_include_htf_levels:
        if _signal_cache is not None and "htf_levels" in _signal_cache:
            htf_levels = _signal_cache["htf_levels"][_htf_key(session, config)]
        else:
            if signal_df_1m is None:
                raise ValueError(
                    "htf_lsi requires signal_df_1m when HTF sweep levels are enabled and signal cache is not provided."
                )
            htf_levels = compute_htf_unswept_levels(
                df,
                signal_df_1m,
                tf_minutes=config.htf_level_tf_minutes,
                n_left=config.htf_n_left,
            )

    eqhl_levels = None
    if config.htf_lsi_include_eqhl_levels:
        if _signal_cache is not None and "eqhl_levels" in _signal_cache:
            eqhl_levels = _signal_cache["eqhl_levels"][_eqhl_key(session, config)]
        else:
            if signal_df_1m is None:
                raise ValueError(
                    "htf_lsi requires signal_df_1m when equal high/low sweep levels are enabled and signal cache is not provided."
                )
            eqhl_levels = compute_equal_htf_levels(
                df,
                signal_df_1m,
                tf_minutes=config.eqhl_level_tf_minutes,
                n_left=config.eqhl_n_left,
                tolerance_points=float(config.eqhl_tolerance_ticks) * float(config.min_tick),
                min_touches=config.eqhl_min_touches,
                lookback_bars=config.eqhl_lookback_bars,
            )
            eqhl_levels["tf_minutes"] = int(config.eqhl_level_tf_minutes)

    reference_levels = None
    reference_instance_ids = None
    if config.htf_lsi_reference_levels:
        reference_levels, reference_instance_ids = _resolve_reference_levels(
            df,
            timestamps,
            session=session,
            selected_level_names=config.htf_lsi_reference_levels,
            signal_df_1m=signal_df_1m,
            atr_length=config.atr_length,
            data_sweep_min_daily_atr_pct=config.data_sweep_min_daily_atr_pct,
            data_sweep_require_session_extreme=config.data_sweep_require_session_extreme,
            data_sweep_event_types=config.data_sweep_event_types,
            data_sweep_release_window_minutes=config.data_sweep_release_window_minutes,
            signal_cache=_signal_cache,
        )

    high_level_sources, low_level_sources = _build_htf_lsi_level_sources(
        htf_levels=htf_levels,
        eqhl_levels=eqhl_levels,
        reference_levels=reference_levels,
        reference_instance_ids=reference_instance_ids,
        selected_reference_level_names=config.htf_lsi_reference_levels,
        include_htf_levels=config.htf_lsi_include_htf_levels,
        include_eqhl_levels=config.htf_lsi_include_eqhl_levels,
        htf_level_tf_minutes=config.htf_level_tf_minutes,
    )

    if not high_level_sources and not low_level_sources:
        return empty

    return _build_htf_lsi_new_sweep_flags(
        high=np.ascontiguousarray(df["high"].to_numpy(dtype=np.float64)),
        low=np.ascontiguousarray(df["low"].to_numpy(dtype=np.float64)),
        in_entry=masks["in_entry"],
        in_sweep=masks["in_sweep"],
        high_level_sources=high_level_sources,
        low_level_sources=low_level_sources,
        stale_breach_consumes_pivot=config.lsi_stale_breach_consumes_pivot,
    )


def _select_fvg_bars_per_day(
    valid_mask: np.ndarray,
    session_day_id: np.ndarray,
    entry_price: np.ndarray,
    *,
    mode: str,
    prefer_highest: bool,
) -> np.ndarray:
    """Return one valid FVG bar per session-day for continuation/reversal.

    ``mode="first"`` preserves the historical engine behavior.
    ``mode="extreme"`` ratchets to the most aggressive same-direction FVG
    seen that day: highest entry price for long-side FVGs, lowest entry price
    for short-side FVGs.
    """
    indices = np.where(valid_mask)[0]
    if len(indices) == 0:
        return indices
    if mode == "first":
        day_ids = session_day_id[indices]
        _, first_idx = np.unique(day_ids, return_index=True)
        return indices[first_idx]

    selected: list[int] = []
    current_day = int(session_day_id[indices[0]])
    best_idx = int(indices[0])
    best_price = float(entry_price[best_idx])

    for idx in indices[1:]:
        idx = int(idx)
        day = int(session_day_id[idx])
        price = float(entry_price[idx])
        if day != current_day:
            selected.append(best_idx)
            current_day = day
            best_idx = idx
            best_price = price
            continue
        if prefer_highest:
            if price > best_price:
                best_idx = idx
                best_price = price
        else:
            if price < best_price:
                best_idx = idx
                best_price = price

    selected.append(best_idx)
    return np.asarray(selected, dtype=np.int64)


def _first_per_day(valid_mask: np.ndarray, session_day_id: np.ndarray) -> np.ndarray:
    """Backward-compatible helper for legacy call sites."""
    return _select_fvg_bars_per_day(
        valid_mask,
        session_day_id,
        np.zeros(len(valid_mask), dtype=np.float64),
        mode="first",
        prefer_highest=True,
    )


def _select_orb_candidate_bars(
    valid_mask: np.ndarray,
    session_day_id: np.ndarray,
    entry_price: np.ndarray,
    *,
    prefer_highest: bool,
    selection_mode: str,
    trade_cap: int,
) -> np.ndarray:
    """Return ORB candidate bars for the configured same-day trade cap."""
    if trade_cap == 1:
        return _select_fvg_bars_per_day(
            valid_mask,
            session_day_id,
            entry_price,
            mode=selection_mode,
            prefer_highest=prefer_highest,
    )
    return np.where(valid_mask)[0]


def _realized_orb_outcome(
    pc: _PreparedCandidate,
    exit_type: int,
    pnl_pts: float,
    *,
    reverse_dir: bool,
) -> tuple[int, float]:
    """Normalize exit type and R-multiple to the executed trade outcome."""
    realized_exit_type = exit_type
    realized_pnl_pts = pnl_pts
    if reverse_dir:
        realized_pnl_pts = -realized_pnl_pts
        if realized_exit_type == EXIT_SL:
            realized_exit_type = EXIT_TP2_SINGLE
        elif realized_exit_type in (EXIT_TP1_TP2, EXIT_TP2_SINGLE):
            realized_exit_type = EXIT_SL
    realized_r_multiple = realized_pnl_pts / pc.risk_pts if pc.risk_pts > 0 else 0.0
    return realized_exit_type, realized_r_multiple


def _orb_reentry_policy_allows(policy: str, exit_type: int, r_multiple: float) -> bool:
    """Return whether the next same-session ORB trade may be armed."""
    if policy == "any_reentry":
        return True
    if policy == "after_positive_first":
        return r_multiple > 0.0
    if policy == "after_nonpositive_first":
        return r_multiple <= 0.0
    if policy == "after_sl_first":
        return exit_type == EXIT_SL
    if policy == "after_full_target_first":
        return exit_type in {EXIT_TP1_TP2, EXIT_TP2_SINGLE}
    return True


def _compute_vwap_gate_masks(
    close: np.ndarray,
    vwap: np.ndarray,
    daily_atr: np.ndarray,
    session_day_id: np.ndarray,
    min_vwap_distance_atr_pct: float,
    vwap_slope_lookback: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Return per-bar VWAP gate masks for long and short continuation entries.

    Rules:
    - Same-side acceptance is always required when either VWAP gate is enabled.
    - Distance gate uses signal close distance from VWAP as % of daily ATR.
    - Slope gate compares current session VWAP to VWAP `lookback` bars ago,
      but only within the same session day.
    """
    n = len(close)
    long_ok = np.ones(n, dtype=bool)
    short_ok = np.ones(n, dtype=bool)

    same_side_enabled = (min_vwap_distance_atr_pct > 0.0) or (vwap_slope_lookback > 0)
    if same_side_enabled:
        long_ok &= close > vwap
        short_ok &= close < vwap

    if min_vwap_distance_atr_pct > 0.0:
        threshold = (min_vwap_distance_atr_pct / 100.0) * np.where(
            np.isnan(daily_atr), np.inf, daily_atr
        )
        diff = close - vwap
        long_ok &= diff >= threshold
        short_ok &= (-diff) >= threshold

    if vwap_slope_lookback > 0:
        lb = int(vwap_slope_lookback)
        slope_long = np.zeros(n, dtype=bool)
        slope_short = np.zeros(n, dtype=bool)
        if lb < n:
            same_day = session_day_id[lb:] == session_day_id[:-lb]
            curr = vwap[lb:]
            prev = vwap[:-lb]
            valid = same_day & ~np.isnan(curr) & ~np.isnan(prev)
            slope_long[lb:] = valid & (curr > prev)
            slope_short[lb:] = valid & (curr < prev)
        long_ok &= slope_long
        short_ok &= slope_short

    valid_vwap = ~np.isnan(vwap)
    long_ok &= valid_vwap
    short_ok &= valid_vwap
    return long_ok, short_ok


def _compute_structure_vwap_gate_masks(
    df: pd.DataFrame,
    session: SessionConfig,
    vwap: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    orb_ready: np.ndarray,
    session_day_id: np.ndarray,
    gate_name: str,
) -> tuple[np.ndarray, np.ndarray]:
    """Return 15m structure + VWAP masks on the 5m signal-bar index."""
    n = len(df)
    long_ok = np.ones(n, dtype=bool)
    short_ok = np.ones(n, dtype=bool)
    if not gate_name:
        return long_ok, short_ok

    signals = compute_all_15m_signals(
        df,
        session,
        vwap,
        daily_atr,
        orb_high,
        orb_low,
        orb_ready,
        session_day_id,
    )
    close = signals["close"]
    valid_vwap_atr = ~np.isnan(vwap) & ~np.isnan(daily_atr) & (daily_atr > 0.0)
    long_dist = np.divide(
        close - vwap,
        daily_atr,
        out=np.full(n, np.nan, dtype=np.float64),
        where=valid_vwap_atr,
    )
    short_dist = np.divide(
        vwap - close,
        daily_atr,
        out=np.full(n, np.nan, dtype=np.float64),
        where=valid_vwap_atr,
    )

    if gate_name == "any2of3_vwap_d10":
        long_ok = signals["hh_hl_any2of3_bull"] & (long_dist >= 0.10)
        short_ok = signals["hh_hl_any2of3_bear"] & (short_dist >= 0.10)
    elif gate_name == "hh_or_hl_vwap_d10":
        long_ok = signals["hh_or_hl_bull"] & (long_dist >= 0.10)
        short_ok = signals["hh_or_hl_bear"] & (short_dist >= 0.10)
    elif gate_name == "score_gte2_vwap_d10":
        long_ok = (signals["bull_score"] >= 2) & (long_dist >= 0.10)
        short_ok = (signals["bear_score"] >= 2) & (short_dist >= 0.10)
    elif gate_name == "hh_hl_2_vwap":
        long_ok = signals["hh_hl_2_bull"] & (close > vwap)
        short_ok = signals["hh_hl_2_bear"] & (close < vwap)
    elif gate_name == "any2of3_vwap":
        long_ok = signals["hh_hl_any2of3_bull"] & (close > vwap)
        short_ok = signals["hh_hl_any2of3_bear"] & (close < vwap)
    else:
        raise ValueError(f"Unsupported structure_vwap_gate: {gate_name!r}")

    long_ok &= valid_vwap_atr
    short_ok &= valid_vwap_atr
    return long_ok, short_ok


def _extract_setup_candidates(
    df: pd.DataFrame,
    session: SessionConfig,
    config: StrategyConfig,
    signal_df_1m: pd.DataFrame | None = None,
    _signal_cache: dict | None = None,
) -> list[_SetupCandidate]:
    """Extract continuation/reversal setup candidates for a session.

    This is the vectorized Phase 1: compute all signals, then group by
    session-day and select one valid FVG per direction.

    Args:
        signal_df_1m: Optional raw 1-minute DataFrame used for HTF level
            construction in ``htf_lsi`` mode.
        _signal_cache: Optional pre-computed signal cache from
            :func:`build_signal_cache`. When provided, all signal arrays
            are looked up instead of recomputed — critical for parameter
            sweeps where the same session/ATR params repeat across many configs.
    """
    timestamps = df.index

    if _signal_cache is not None:
        # Fast path: all signals pre-computed — zero recomputation cost.
        skey = _session_key(session)
        fkey = _fvg_key(session, config)
        sc          = _signal_cache["session"][skey]
        masks       = sc["masks"]
        new_session_day = sc["new_session_day"]
        session_day_id  = sc["session_day_id"]
        orb_high    = sc["orb_high"]
        orb_low     = sc["orb_low"]
        orb_ready   = sc["orb_ready"]
        date_strs   = sc["date_strs"]
        vwap        = sc["vwap"]
        daily_atr   = _signal_cache["atr"][config.atr_length]
        fvg         = _signal_cache["fvg"][fkey]
    else:
        # Slow path: compute signals fresh (correct for single-backtest calls).
        # Session masks
        masks = compute_session_masks(timestamps, session)

        # Session-aware day boundaries (handles cross-midnight sessions like Asia)
        new_session_day, session_day_id = compute_session_days(timestamps, session)

        # Daily ATR
        daily_atr = compute_daily_atr(df, config.atr_length)

        # ORB levels — use session day boundaries so ORB isn't reset at midnight
        orb_high, orb_low, orb_ready = compute_orb_levels(
            df, masks["in_orb"], masks["in_rth"], new_session_day
        )
        vwap = compute_session_vwap(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            df["volume"].values,
            session_day_id,
        )

        # FVG detection
        fvg = detect_fvg(
            df["high"].values,
            df["low"].values,
            daily_atr,
            orb_high,
            orb_low,
            session.min_gap_atr_pct,
            close=df["close"].values if config.impulse_close_filter else None,
            impulse_close_filter=config.impulse_close_filter,
            min_gap_orb_pct=getattr(session, "min_gap_orb_pct", 0.0),
        )

        # Date strings for excluded dates and half-days
        date_strs = compute_date_strings(timestamps)

    excluded = set(config.excluded_dates)

    # Add DOW-excluded days to the excluded set
    if config.excluded_days:
        from datetime import datetime as _dt
        _dow_set = set(config.excluded_days)
        _unique_dates = set(date_strs) - excluded
        for _ds in _unique_dates:
            if _dt.strptime(_ds, "%Y%m%d").weekday() in _dow_set:
                excluded.add(_ds)
    exclude_mask = None
    if excluded:
        exclude_mask = np.isin(date_strs, np.array(list(excluded)))

    # Filter candidates: must be in entry window, ORB ready, not excluded, bar confirmed
    # Pine uses barstate.isconfirmed — for completed 5m bars, all bars in historical data
    # are confirmed, so we just check the conditions.
    valid_long = (
        fvg["long_fvg"]
        & masks["in_entry"]
        & masks["in_rth"]
        & orb_ready
    )
    valid_short = (
        fvg["short_fvg"]
        & masks["in_entry"]
        & masks["in_rth"]
        & orb_ready
    )

    if config.strategy in {"continuation", "reversal"} and (
        config.min_vwap_distance_atr_pct > 0.0 or config.vwap_slope_lookback > 0
    ):
        close_arr = df["close"].values
        vwap_long_ok, vwap_short_ok = _compute_vwap_gate_masks(
            close_arr,
            vwap,
            daily_atr,
            session_day_id,
            config.min_vwap_distance_atr_pct,
            config.vwap_slope_lookback,
        )
        valid_long &= vwap_long_ok
        valid_short &= vwap_short_ok

    if config.strategy in {"continuation", "reversal"} and config.structure_vwap_gate:
        struct_long_ok, struct_short_ok = _compute_structure_vwap_gate_masks(
            df,
            session,
            vwap,
            daily_atr,
            orb_high,
            orb_low,
            orb_ready,
            session_day_id,
            config.structure_vwap_gate,
        )
        valid_long &= struct_long_ok
        valid_short &= struct_short_ok

    # Exclude specific dates (vectorized via numpy isin)
    if exclude_mask is not None:
        valid_long &= ~exclude_mask
        valid_short &= ~exclude_mask

    # Group by session day, take first FVG per direction.
    # Use session_day_id (not calendar date) so cross-midnight sessions
    # like Asia (20:00-07:00) are treated as one session day.
    candidates: list[_SetupCandidate] = []
    dates = timestamps.date
    close = df["close"].values
    lrlr_settings = _build_lrlr_settings(config)

    if config.strategy == "lsi":
        # LSI uses ORB-free FVG detection — no directional ORB filter, no orb_ready gate
        from ..signals.fvg import detect_fvg_no_orb
        if _signal_cache is not None and "fvg_no_orb" in _signal_cache:
            fvg_lsi = _signal_cache["fvg_no_orb"][_fvg_no_orb_key(session, config)]
        else:
            fvg_lsi = detect_fvg_no_orb(
                df["high"].values,
                df["low"].values,
                daily_atr,
                session.min_gap_atr_pct,
            )
        lsi_in_entry = masks["in_entry"]
        lsi_in_rth = masks["in_rth"]
        lsi_in_sweep = masks["in_sweep"]
        if exclude_mask is not None:
            lsi_in_entry = lsi_in_entry & ~exclude_mask
            lsi_in_rth = lsi_in_rth & ~exclude_mask
            lsi_in_sweep = lsi_in_sweep & ~exclude_mask
        valid_long_lsi = fvg_lsi["long_fvg"] & lsi_in_entry & lsi_in_rth
        valid_short_lsi = fvg_lsi["short_fvg"] & lsi_in_entry & lsi_in_rth
        candidates = _extract_lsi_candidates(
            df, fvg_lsi, valid_long_lsi, valid_short_lsi, session_day_id,
            lsi_in_entry, lsi_in_rth, lsi_in_sweep, dates, close,
            daily_atr, orb_high, orb_low, session,
            n_left=config.lsi_n_left,
            n_right=config.lsi_n_right,
            fvg_window_left=config.lsi_fvg_window_left,
            fvg_window_right=config.lsi_fvg_window_right,
            direction_filter=config.direction_filter,
            stop_mode=config.lsi_stop_mode,
            target_mode=config.lsi_target_mode,
            entry_mode=config.lsi_entry_mode,
            close_on_sweep_to_inversion_minutes=config.lsi_close_on_sweep_to_inversion_minutes,
            confirmation_mode=config.lsi_confirmation_mode,
            cisd_min_leg_bars=config.cisd_min_leg_bars,
            cisd_min_leg_atr_pct=config.cisd_min_leg_atr_pct,
            cisd_max_leg_bars=config.cisd_max_leg_bars,
            first_fvg_only=config.lsi_first_fvg_only,
            clean_path=config.lsi_clean_path,
            rr=config.rr,
            tp1_ratio=config.tp1_ratio,
            target_swing_n_bars=config.swing_n_bars,
            min_tick=config.min_tick,
            be_swing_n_left=config.lsi_be_swing_n_left,
            sweep_gate=config.lsi_sweep_gate,
            stale_breach_consumes_pivot=config.lsi_stale_breach_consumes_pivot,
            lrlr_settings=lrlr_settings,
        )
    elif config.strategy == "htf_lsi":
        from ..signals.fvg import detect_fvg_no_orb

        if _signal_cache is not None and "fvg_no_orb" in _signal_cache:
            fvg_htf = _signal_cache["fvg_no_orb"][_fvg_no_orb_key(session, config)]
        else:
            fvg_htf = detect_fvg_no_orb(
                df["high"].values,
                df["low"].values,
                daily_atr,
                session.min_gap_atr_pct,
            )

        htf_in_entry = masks["in_entry"]
        htf_in_rth = masks["in_rth"]
        htf_in_sweep = masks["in_sweep"]
        if exclude_mask is not None:
            htf_in_entry = htf_in_entry & ~exclude_mask
            htf_in_rth = htf_in_rth & ~exclude_mask
            htf_in_sweep = htf_in_sweep & ~exclude_mask
        valid_long_htf = fvg_htf["long_fvg"] & htf_in_entry & htf_in_rth
        valid_short_htf = fvg_htf["short_fvg"] & htf_in_entry & htf_in_rth

        htf_levels = None
        if config.htf_lsi_include_htf_levels:
            if _signal_cache is not None and "htf_levels" in _signal_cache:
                htf_levels = _signal_cache["htf_levels"][_htf_key(session, config)]
            else:
                if signal_df_1m is None:
                    raise ValueError("htf_lsi requires signal_df_1m when HTF sweep levels are enabled and signal cache is not provided.")
                htf_levels = compute_htf_unswept_levels(
                    df,
                    signal_df_1m,
                    tf_minutes=config.htf_level_tf_minutes,
                    n_left=config.htf_n_left,
                )

        eqhl_levels = None
        if config.htf_lsi_include_eqhl_levels:
            if _signal_cache is not None and "eqhl_levels" in _signal_cache:
                eqhl_levels = _signal_cache["eqhl_levels"][_eqhl_key(session, config)]
            else:
                if signal_df_1m is None:
                    raise ValueError("htf_lsi requires signal_df_1m when equal high/low sweep levels are enabled and signal cache is not provided.")
                eqhl_levels = compute_equal_htf_levels(
                    df,
                    signal_df_1m,
                    tf_minutes=config.eqhl_level_tf_minutes,
                    n_left=config.eqhl_n_left,
                    tolerance_points=float(config.eqhl_tolerance_ticks) * float(config.min_tick),
                    min_touches=config.eqhl_min_touches,
                    lookback_bars=config.eqhl_lookback_bars,
                )
                eqhl_levels["tf_minutes"] = int(config.eqhl_level_tf_minutes)

        reference_levels = None
        reference_instance_ids = None
        if config.htf_lsi_reference_levels:
            reference_levels, reference_instance_ids = _resolve_reference_levels(
                df,
                timestamps,
                session=session,
                selected_level_names=config.htf_lsi_reference_levels,
                signal_df_1m=signal_df_1m,
                atr_length=config.atr_length,
                data_sweep_min_daily_atr_pct=config.data_sweep_min_daily_atr_pct,
                data_sweep_require_session_extreme=config.data_sweep_require_session_extreme,
                data_sweep_event_types=config.data_sweep_event_types,
                data_sweep_release_window_minutes=config.data_sweep_release_window_minutes,
                signal_cache=_signal_cache,
            )

        candidates = _extract_htf_lsi_candidates(
            df,
            fvg_htf,
            valid_long_htf,
            valid_short_htf,
            session_day_id,
            htf_in_entry,
            htf_in_rth,
            htf_in_sweep,
            dates,
            close,
            daily_atr,
            orb_high,
            orb_low,
            session,
            htf_levels=htf_levels,
            eqhl_levels=eqhl_levels,
            reference_levels=reference_levels,
            reference_instance_ids=reference_instance_ids,
            selected_reference_level_names=config.htf_lsi_reference_levels,
            include_htf_levels=config.htf_lsi_include_htf_levels,
            include_eqhl_levels=config.htf_lsi_include_eqhl_levels,
            fvg_window_left=config.lsi_fvg_window_left,
            fvg_window_right=config.lsi_fvg_window_right,
            direction_filter=config.direction_filter,
            stop_mode=config.lsi_stop_mode,
            target_mode=config.lsi_target_mode,
            entry_mode=config.lsi_entry_mode,
            close_on_sweep_to_inversion_minutes=config.lsi_close_on_sweep_to_inversion_minutes,
            confirmation_mode=config.lsi_confirmation_mode,
            cisd_min_leg_bars=config.cisd_min_leg_bars,
            cisd_min_leg_atr_pct=config.cisd_min_leg_atr_pct,
            cisd_max_leg_bars=config.cisd_max_leg_bars,
            rr=config.rr,
            tp1_ratio=config.tp1_ratio,
            target_swing_n_bars=config.swing_n_bars,
            min_tick=config.min_tick,
            inversion_ordinal=config.htf_lsi_inversion_ordinal,
            max_fvg_to_inversion_bars=config.max_fvg_to_inversion_bars,
            htf_level_tf_minutes=config.htf_level_tf_minutes,
            stale_breach_consumes_pivot=config.lsi_stale_breach_consumes_pivot,
            lrlr_settings=lrlr_settings,
        )
    elif config.strategy == "reference_lsi":
        from ..signals.fvg import detect_fvg_no_orb

        if _signal_cache is not None and "fvg_no_orb" in _signal_cache:
            fvg_ref = _signal_cache["fvg_no_orb"][_fvg_no_orb_key(session, config)]
        else:
            fvg_ref = detect_fvg_no_orb(
                df["high"].values,
                df["low"].values,
                daily_atr,
                session.min_gap_atr_pct,
            )

        ref_in_entry = masks["in_entry"]
        ref_in_rth = masks["in_rth"]
        if exclude_mask is not None:
            ref_in_entry = ref_in_entry & ~exclude_mask
            ref_in_rth = ref_in_rth & ~exclude_mask
        valid_long_ref = fvg_ref["long_fvg"] & ref_in_entry & ref_in_rth
        valid_short_ref = fvg_ref["short_fvg"] & ref_in_entry & ref_in_rth

        reference_levels, reference_instance_ids = _resolve_reference_levels(
            df,
            timestamps,
            session=session,
            selected_level_names=config.ref_lsi_reference_levels,
            signal_df_1m=signal_df_1m,
            atr_length=config.atr_length,
            data_sweep_min_daily_atr_pct=config.data_sweep_min_daily_atr_pct,
            data_sweep_require_session_extreme=config.data_sweep_require_session_extreme,
            data_sweep_event_types=config.data_sweep_event_types,
            data_sweep_release_window_minutes=config.data_sweep_release_window_minutes,
            signal_cache=_signal_cache,
        )

        candidates = _extract_reference_lsi_candidates(
            df,
            fvg_ref,
            valid_long_ref,
            valid_short_ref,
            session_day_id,
            ref_in_entry,
            ref_in_rth,
            dates,
            close,
            daily_atr,
            orb_high,
            orb_low,
            session,
            reference_levels=reference_levels,
            reference_instance_ids=reference_instance_ids,
            gap_lookback_bars=config.ref_lsi_gap_lookback_bars,
            inversion_max_bars=config.ref_lsi_inversion_max_bars,
            direction_filter=config.direction_filter,
            stop_mode=config.lsi_stop_mode,
            entry_mode=config.lsi_entry_mode,
            close_on_sweep_to_inversion_minutes=config.lsi_close_on_sweep_to_inversion_minutes,
            gap_entry_edge=config.ref_lsi_gap_entry_edge,
            selected_level_names=config.ref_lsi_reference_levels,
            confirmation_mode=config.lsi_confirmation_mode,
            cisd_min_leg_bars=config.cisd_min_leg_bars,
            cisd_min_leg_atr_pct=config.cisd_min_leg_atr_pct,
            cisd_max_leg_bars=config.cisd_max_leg_bars,
            rr=config.rr,
            tp1_ratio=config.tp1_ratio,
            target_mode=config.lsi_target_mode,
            target_swing_n_bars=config.swing_n_bars,
            min_tick=config.min_tick,
            lrlr_settings=lrlr_settings,
        )
    elif config.strategy == "cisd":
        # CISD mode: ORB liquidity sweep + displacement candle reversal.
        # Price breaks beyond ORB (sweep), then a displacement candle reverses
        # and closes beyond the prior candle's body — entry at that close.
        candidates = _extract_cisd_candidates(
            df, session_day_id,
            masks["in_entry"], masks["in_rth"], orb_ready,
            dates, close, orb_high, orb_low, daily_atr, session,
            direction_filter=config.direction_filter,
            excluded=excluded,
            date_strs=date_strs,
        )
    elif config.strategy == "ib":
        # IB mode: Initial Balance mean-reversion.
        # orb_start/orb_end define the IB window (e.g. 09:30-10:30).
        # Direction based on which extreme formed first; entry at midpoint.
        candidates = _extract_ib_candidates(
            df, session_day_id,
            masks["in_orb"], masks["in_entry"], masks["in_rth"],
            new_session_day, dates, daily_atr, session,
            direction_filter=config.direction_filter,
            excluded=excluded,
            date_strs=date_strs,
        )
    elif config.strategy == "inversion":
        # Inversion mode: wait for a candle to close through the FVG zone,
        # then enter in the opposite direction on a retest.
        # Bullish FVG inverted → SHORT: close below long_fvg_bottom (high[2])
        # Bearish FVG inverted → LONG: close above short_fvg_top (low[2])
        candidates = _extract_inversion_candidates(
            df, fvg, valid_long, valid_short, session_day_id,
            masks["in_entry"], dates, close, session, daily_atr,
            orb_high=orb_high, orb_low=orb_low,
            direction_filter=config.direction_filter,
        )
    else:
        # Continuation or reversal mode — select one same-direction FVG per
        # session-day using the configured selection mode.
        dir_mult = -1 if config.strategy == "reversal" else 1
        take_longs = config.direction_filter in ("both", "long")
        take_shorts = config.direction_filter in ("both", "short")

        # Bullish FVG: continuation=long, reversal=short
        long_out_dir = 1 * dir_mult
        want_long = (long_out_dir == 1 and take_longs) or (long_out_dir == -1 and take_shorts)
        if want_long:
            long_entry_price = fvg["long_entry_price"]
            selected_long_bars = _select_orb_candidate_bars(
                valid_long,
                session_day_id,
                long_entry_price,
                prefer_highest=True,
                selection_mode=config.continuation_fvg_selection,
                trade_cap=config.orb_trade_max_per_session,
            )
            long_gap_size = fvg["long_gap_size"]
            for i in selected_long_bars:
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=long_out_dir,
                    signal_bar=i,
                    entry_price=long_entry_price[i],
                    gap_size=long_gap_size[i],
                    daily_atr=daily_atr[i],
                    orb_range=orb_high[i] - orb_low[i],
                ))

        # Bearish FVG: continuation=short, reversal=long
        short_out_dir = -1 * dir_mult
        want_short = (short_out_dir == 1 and take_longs) or (short_out_dir == -1 and take_shorts)
        if want_short:
            short_entry_price = fvg["short_entry_price"]
            selected_short_bars = _select_orb_candidate_bars(
                valid_short,
                session_day_id,
                short_entry_price,
                prefer_highest=False,
                selection_mode=config.continuation_fvg_selection,
                trade_cap=config.orb_trade_max_per_session,
            )
            short_gap_size = fvg["short_gap_size"]
            for i in selected_short_bars:
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=short_out_dir,
                    signal_bar=i,
                    entry_price=short_entry_price[i],
                    gap_size=short_gap_size[i],
                    daily_atr=daily_atr[i],
                    orb_range=orb_high[i] - orb_low[i],
                ))

    return candidates


def _extract_cisd_candidates(
    df: pd.DataFrame,
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    orb_ready: np.ndarray,
    dates,
    close: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    daily_atr: np.ndarray,
    session,
    direction_filter: str = "both",
    excluded: set | None = None,
    date_strs: np.ndarray | None = None,
) -> list[_SetupCandidate]:
    """Extract CISD (Change in State of Delivery) candidates.

    CISD detects a liquidity sweep of the ORB level followed by a displacement
    candle that reverses direction — signaling the delivery state has changed.

    CISD Long:
      1. Price trades below ORB low (sweep / liquidity grab)
      2. A bullish displacement candle closes above the prior candle's body high
         (max of open, close of bar i-1)
      3. Entry at the displacement candle's close

    CISD Short:
      1. Price trades above ORB high (sweep)
      2. A bearish displacement candle closes below the prior candle's body low
         (min of open, close of bar i-1)
      3. Entry at the displacement candle's close

    Does NOT require FVG detection — this is a pure price-action signal.
    One signal per session-day.
    """
    n = len(df)
    high = df["high"].values
    low = df["low"].values
    open_ = df["open"].values
    candidates: list[_SetupCandidate] = []

    take_longs = direction_filter in ("both", "long")
    take_shorts = direction_filter in ("both", "short")

    excluded = excluded or set()

    # Per session-day state tracking
    seen_days: set = set()
    # Track whether ORB has been swept on each side per session-day
    swept_low: dict[int, bool] = {}   # sd → True if price traded below ORB low
    swept_high: dict[int, bool] = {}  # sd → True if price traded above ORB high

    for i in range(1, n):
        sd = session_day_id[i]

        # Skip excluded dates
        if date_strs is not None and date_strs[i] in excluded:
            continue

        # Must be in RTH and ORB must be ready
        if not in_rth[i] or not orb_ready[i]:
            # Reset sweep tracking on new session day
            continue

        orb_h = orb_high[i]
        orb_l = orb_low[i]

        if np.isnan(orb_h) or np.isnan(orb_l):
            continue

        # Track ORB sweeps: price traded beyond ORB level
        if low[i] < orb_l:
            swept_low[sd] = True
        if high[i] > orb_h:
            swept_high[sd] = True

        # Only look for displacement candles during the entry window
        if not in_entry[i]:
            continue

        if sd in seen_days:
            continue

        # Prior candle's body boundaries
        prev_body_high = max(open_[i - 1], close[i - 1])
        prev_body_low = min(open_[i - 1], close[i - 1])

        # CISD Long: ORB low was swept + bullish displacement candle
        if take_longs and swept_low.get(sd, False):
            # Bullish displacement: close above prior candle's body high
            if close[i] > prev_body_high and close[i] > open_[i]:
                seen_days.add(sd)
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=abs(close[i] - open_[i]),  # displacement size
                    daily_atr=daily_atr[i],
                    orb_range=orb_h - orb_l,
                ))
                continue

        # CISD Short: ORB high was swept + bearish displacement candle
        if take_shorts and swept_high.get(sd, False):
            # Bearish displacement: close below prior candle's body low
            if close[i] < prev_body_low and close[i] < open_[i]:
                seen_days.add(sd)
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=abs(open_[i] - close[i]),  # displacement size
                    daily_atr=daily_atr[i],
                    orb_range=orb_h - orb_l,
                ))
                continue

    return candidates


def _extract_ib_candidates(
    df: pd.DataFrame,
    session_day_id: np.ndarray,
    in_orb: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    new_session_day: np.ndarray,
    dates,
    daily_atr: np.ndarray,
    session,
    direction_filter: str = "both",
    excluded: set | None = None,
    date_strs: np.ndarray | None = None,
) -> list[_SetupCandidate]:
    """Extract IB (Initial Balance) mean-reversion candidates.

    One candidate per session-day:
    1. Compute IB high/low/midpoint during orb_start-orb_end window
    2. Determine direction: low formed first → LONG, high formed first → SHORT
    3. Entry = midpoint, SL = IB boundary, TP = opposite IB boundary
    4. Gate: IB must NOT be broken at entry start (broken-before-fill checked in Phase 2)
    """
    from ..signals.ib import compute_ib_levels

    ib_high, ib_low, ib_mid, ib_direction, ib_ready, ib_broken = compute_ib_levels(
        df, in_orb, in_rth, new_session_day
    )

    candidates: list[_SetupCandidate] = []
    seen_days: set = set()
    excluded = excluded or set()
    n = len(df)

    for i in range(n):
        if not ib_ready[i] or not in_entry[i]:
            continue

        sd = session_day_id[i]
        if sd in seen_days:
            continue

        if date_strs is not None and date_strs[i] in excluded:
            seen_days.add(sd)
            continue

        direction = int(ib_direction[i])
        if direction == 0:
            seen_days.add(sd)
            continue

        if direction_filter == "long" and direction != 1:
            seen_days.add(sd)
            continue
        if direction_filter == "short" and direction != -1:
            seen_days.add(sd)
            continue

        # IB already broken at entry start → skip
        if ib_broken[i]:
            seen_days.add(sd)
            continue

        entry_price = ib_mid[i]
        ib_range = ib_high[i] - ib_low[i]
        if ib_range <= 0 or np.isnan(ib_range):
            seen_days.add(sd)
            continue

        # Structural stop = IB boundary
        if direction == 1:
            structural_stop = ib_low[i]
        else:
            structural_stop = ib_high[i]

        # Use daily ATR if available, otherwise fall back to IB range
        atr = daily_atr[i] if not np.isnan(daily_atr[i]) else ib_range

        seen_days.add(sd)
        candidates.append(_SetupCandidate(
            date_str=str(dates[i]),
            session=session.name,
            direction=direction,
            signal_bar=i,
            entry_price=entry_price,
            gap_size=ib_range,
            daily_atr=atr,
            orb_range=ib_range,
            structural_stop_price=structural_stop,
            # Store IB levels for fill-scan IB-break check
            lsi_fvg_top=ib_high[i],
            lsi_fvg_bottom=ib_low[i],
        ))

    return candidates


def _extract_inversion_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    valid_long: np.ndarray,
    valid_short: np.ndarray,
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    dates,
    close: np.ndarray,
    session,
    daily_atr: np.ndarray,
    orb_high: np.ndarray | None = None,
    orb_low: np.ndarray | None = None,
    direction_filter: str = "both",
) -> list[_SetupCandidate]:
    """Extract inverted FVG candidates.

    For each FVG, scan forward within the same session-day entry window for a
    candle that closes through the FVG zone (inversion). Once inverted, create
    a candidate in the opposite direction with the inversion bar as the signal.

    Entry is at the inversion level (near edge of the FVG zone — where price
    broke through). This gives higher fill rates since price is already there.

    Bullish FVG inverted → SHORT at long_fvg_bottom (high[2] — inversion level)
    Bearish FVG inverted → LONG at short_fvg_top (low[2] — inversion level)

    direction_filter: "both", "long", or "short" — restricts output directions.
    """
    n = len(df)
    candidates: list[_SetupCandidate] = []

    # Collect all FVGs with their zone boundaries
    long_fvg_bottom = fvg["long_fvg_bottom"]  # high[2] — inversion level for shorts
    short_fvg_top = fvg["short_fvg_top"]       # low[2] — inversion level for longs

    # Direction filter: skip FVG types that can't produce the desired direction
    # Bullish FVG inversion → short, Bearish FVG inversion → long
    take_shorts = direction_filter in ("both", "short")
    take_longs = direction_filter in ("both", "long")

    # Pending FVGs: (fvg_bar, inversion_level, gap_size, atr, sd)
    pending_long: list = []   # bullish FVGs waiting for bearish inversion → short
    pending_short: list = []  # bearish FVGs waiting for bullish inversion → long

    seen_days: set = set()  # one inverted signal per session-day

    for i in range(n):
        sd = session_day_id[i]

        # Register new FVGs as pending (if in entry window)
        if valid_long[i] and take_shorts:  # bullish FVG → inversion produces short
            pending_long.append((
                i, long_fvg_bottom[i],
                fvg["long_gap_size"][i], daily_atr[i], sd,
            ))

        if valid_short[i] and take_longs:  # bearish FVG → inversion produces long
            pending_short.append((
                i, short_fvg_top[i],
                fvg["short_gap_size"][i], daily_atr[i], sd,
            ))

        # Check pending bullish FVGs for bearish inversion (close below FVG bottom)
        remaining_long = []
        for pending in pending_long:
            fvg_bar, inversion_level, gap_size, atr, fvg_sd = pending

            # Must be same session-day, after the FVG bar, still in entry window
            if sd != fvg_sd or i <= fvg_bar:
                remaining_long.append(pending)
                continue

            if not in_entry[i]:
                # Past entry window — discard
                continue

            if close[i] < inversion_level and sd not in seen_days:
                # Inversion confirmed — enter SHORT at candle close
                seen_days.add(sd)
                _orb_r = (orb_high[i] - orb_low[i]) if orb_high is not None else 0.0
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=gap_size,
                    daily_atr=atr,
                    orb_range=_orb_r,
                ))
                continue

            remaining_long.append(pending)
        pending_long = remaining_long

        # Check pending bearish FVGs for bullish inversion (close above FVG top)
        remaining_short = []
        for pending in pending_short:
            fvg_bar, inversion_level, gap_size, atr, fvg_sd = pending

            if sd != fvg_sd or i <= fvg_bar:
                remaining_short.append(pending)
                continue

            if not in_entry[i]:
                continue

            if close[i] > inversion_level and sd not in seen_days:
                # Inversion confirmed — enter LONG at candle close
                seen_days.add(sd)
                _orb_r = (orb_high[i] - orb_low[i]) if orb_high is not None else 0.0
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=gap_size,
                    daily_atr=atr,
                    orb_range=_orb_r,
                ))
                continue

            remaining_short.append(pending)
        pending_short = remaining_short

        # Clean up pending FVGs from previous session days
        pending_long = [p for p in pending_long if p[4] >= sd]
        pending_short = [p for p in pending_short if p[4] >= sd]

    return candidates


def _extract_lsi_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    valid_long: np.ndarray,
    valid_short: np.ndarray,
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    in_sweep: np.ndarray,
    dates,
    close: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    session,
    n_left: int = 3,
    n_right: int = 3,
    fvg_window_left: int = 10,
    fvg_window_right: int = 10,
    direction_filter: str = "both",
    stop_mode: str = "absolute",
    target_mode: str = "risk",
    entry_mode: str = "close",
    close_on_sweep_to_inversion_minutes: int = 0,
    confirmation_mode: str = "inversion",
    cisd_min_leg_bars: int = 2,
    cisd_min_leg_atr_pct: float = 5.0,
    cisd_max_leg_bars: int = 60,
    first_fvg_only: bool = False,
    clean_path: bool = False,
    rr: float = 2.5,
    tp1_ratio: float = 0.5,
    target_swing_n_bars: int = 10,
    min_tick: float = 0.25,
    be_swing_n_left: int = 0,
    sweep_gate: str = "sweep_window",
    stale_breach_consumes_pivot: bool = True,
    lrlr_settings: _LSILRLRSettings | None = None,
) -> list[_SetupCandidate]:
    """Extract Liquidity Sweep Inversion (LSI) candidates.

    Default LSI combines these events:
    1. A confirmed swing high/low (pivot detection with n_left/n_right bars)
    2. A liquidity sweep — price crosses above swing high (for shorts) or below swing low (for longs)
    3. An FVG that forms within fvg_window bars before OR after the sweep
    4. That FVG is inverted — close < FVG bottom (for shorts) or close > FVG top (for longs)
    5. Entry at the close of the inversion candle

    ``confirmation_mode="cisd"`` replaces steps 3-4 with an internal,
    body-based CISD close through the most recent local structure level after
    the sweep. ``"inversion_or_cisd"`` arms both confirmation paths.

    Direction logic:
    - SHORT LSI: swing HIGH swept → bullish FVG nearby → bullish FVG inverted → short at close
    - LONG LSI: swing LOW swept → bearish FVG nearby → bearish FVG inverted → long at close
    """
    n = len(df)
    high = df["high"].values
    low = df["low"].values
    open_ = df["open"].values
    lrlr_settings = lrlr_settings or _LSILRLRSettings(False, "", 2, 2, 3, 120, 30, 120, 0.18, 0.03, 0.04, False, 0.0)
    bar_minutes = _infer_bar_minutes(df.index)
    lrlr_pivot_arrays = _build_lrlr_pivot_arrays(high, low, lrlr_settings)
    target_pivot_arrays = (
        _build_target_pivot_arrays(high, low, target_swing_n_bars)
        if target_mode == "left_structure"
        else None
    )

    take_shorts = direction_filter in ("both", "short")
    take_longs = direction_filter in ("both", "long")
    use_inversion = confirmation_mode in {"inversion", "inversion_or_cisd"}
    use_cisd = confirmation_mode in {"cisd", "inversion_or_cisd"}

    cisd = detect_internal_cisd(
        open_,
        close,
        daily_atr=daily_atr,
        min_leg_bars=cisd_min_leg_bars,
        min_leg_atr_pct=cisd_min_leg_atr_pct,
        max_leg_bars=cisd_max_leg_bars,
    ) if use_cisd else {}

    # --- Phase 1: Vectorized swing and sweep detection ---

    # Detect confirmed swing pivots
    # swing_highs[i] = True means bar i - n_right was a confirmed swing high
    swing_highs = detect_swing_highs(high, n_left, n_right)
    swing_lows = detect_swing_lows(low, n_left, n_right)

    # Pivot level is the actual price of the pivot candle: high[i - n_right]
    # when confirmed at bar i.
    pivot_high_vals = np.where(swing_highs, np.roll(high, n_right), np.nan).astype(float)
    pivot_high_vals[:n_right] = np.nan  # first n_right bars have no valid pivot reference

    pivot_low_vals = np.where(swing_lows, np.roll(low, n_right), np.nan).astype(float)
    pivot_low_vals[:n_right] = np.nan

    # FVG zone boundaries
    long_fvg_bottom = fvg["long_fvg_bottom"]  # high[2] — inversion level for shorts
    short_fvg_top = fvg["short_fvg_top"]      # low[2] — inversion level for longs

    # Pre-extract FVG boundary arrays for clean-path scanning
    short_fvg_bool = fvg["short_fvg"]          # bearish FVGs (obstacles for longs)
    short_fvg_top_arr = fvg["short_fvg_top"]    # low[j-2] — upper boundary of bearish FVG zone
    short_fvg_bot_arr = fvg["short_entry_price"] # high[j] — lower boundary of bearish FVG zone
    long_fvg_bool = fvg["long_fvg"]             # bullish FVGs (obstacles for shorts)
    long_fvg_top_arr = fvg["long_entry_price"]  # low[j] — upper boundary of bullish FVG zone
    long_fvg_bot_arr = fvg["long_fvg_bottom"]   # high[j-2] — lower boundary of bullish FVG zone

    if sweep_gate == "entry":
        sweep_gate_mask = in_entry
    elif sweep_gate == "rth":
        sweep_gate_mask = in_rth
    else:
        sweep_gate_mask = in_sweep

    # --- Phase 2: Sequential state machine ---

    # Pending bullish FVGs waiting for a nearby sweep → then awaiting inversion for SHORT
    # (fvg_bar, inversion_level, gap_size, atr, sd)
    detected_bullish_fvgs: list = []  # bullish FVGs seen, no sweep yet within window
    active_for_short: list = []       # bullish FVGs with confirmed nearby sweep → await inversion

    # Pending bearish FVGs waiting for a nearby sweep → then awaiting inversion for LONG
    detected_bearish_fvgs: list = []  # bearish FVGs seen, no sweep yet
    active_for_long: list = []        # bearish FVGs with confirmed nearby sweep → await inversion

    # Active confirmed pivots. A breach consumes the pivot immediately even if
    # the breach happens outside the valid sweep window.
    active_swing_high = np.nan
    active_swing_low = np.nan

    # Only valid in-window sweeps can activate LSI setups. Keep a short rolling
    # history so same-bar / post-sweep FVGs can attach to the most recent valid sweep.
    recent_sweep_highs: list[tuple[int, float, int]] = []  # (bar, level, session_day_id)
    recent_sweep_lows: list[tuple[int, float, int]] = []

    seen_inversion_days: set = set()  # one FVG-inversion signal per session-day
    seen_cisd_days: set = set()       # one CISD signal per session-day
    candidates: list[_SetupCandidate] = []

    for i in range(n):
        sd = session_day_id[i]

        valid_sweep_high = False
        valid_sweep_low = False
        swept_high_level = np.nan
        swept_low_level = np.nan

        # Fixed mode retires a pivot on any breach. Legacy mode leaves the pivot
        # active until a breach happens inside the configured sweep gate.
        if not np.isnan(active_swing_high) and high[i] > active_swing_high:
            swept_high_level = float(active_swing_high)
            valid_sweep_high = bool(sweep_gate_mask[i])
            if valid_sweep_high or stale_breach_consumes_pivot:
                active_swing_high = np.nan
            if valid_sweep_high and take_shorts:
                recent_sweep_highs.append((i, swept_high_level, sd))

        if not np.isnan(active_swing_low) and low[i] < active_swing_low:
            swept_low_level = float(active_swing_low)
            valid_sweep_low = bool(sweep_gate_mask[i])
            if valid_sweep_low or stale_breach_consumes_pivot:
                active_swing_low = np.nan
            if valid_sweep_low and take_longs:
                recent_sweep_lows.append((i, swept_low_level, sd))

        recent_sweep_highs = [
            sweep for sweep in recent_sweep_highs
            if sweep[2] == sd and (i - sweep[0]) <= fvg_window_right
        ]
        recent_sweep_lows = [
            sweep for sweep in recent_sweep_lows
            if sweep[2] == sd and (i - sweep[0]) <= fvg_window_right
        ]

        # A) Register new bullish FVG (valid_long[i] means in_entry + in_rth + orb_ready)
        if use_inversion and valid_long[i] and take_shorts:
            base_entry = (i, long_fvg_bottom[i], fvg["long_gap_size"][i], daily_atr[i], sd)
            if recent_sweep_highs:
                _sweep_bar, _swept, _ = recent_sweep_highs[-1]
                # 8-element: adds swept_level + fvg_other_bound + sweep_bar
                active_entry = base_entry + (_swept, float(long_fvg_top_arr[i]), _sweep_bar)
                if first_fvg_only:
                    if not any(p[4] == sd for p in active_for_short):
                        active_for_short.append(active_entry)
                else:
                    active_for_short.append(active_entry)
            else:
                detected_bullish_fvgs.append(base_entry)

        # B) Register new bearish FVG
        if use_inversion and valid_short[i] and take_longs:
            base_entry = (i, short_fvg_top[i], fvg["short_gap_size"][i], daily_atr[i], sd)
            if recent_sweep_lows:
                _sweep_bar, _swept, _ = recent_sweep_lows[-1]
                # 8-element: adds swept_level + fvg_other_bound + sweep_bar
                active_entry = base_entry + (_swept, float(short_fvg_bot_arr[i]), _sweep_bar)
                if first_fvg_only:
                    if not any(p[4] == sd for p in active_for_long):
                        active_for_long.append(active_entry)
                else:
                    active_for_long.append(active_entry)
            else:
                detected_bearish_fvgs.append(base_entry)

        # C) Sweep of swing HIGH at bar i → promote bullish FVGs within window → active_for_short
        if use_inversion and valid_sweep_high and take_shorts:
            _swept_c = float(swept_high_level)
            still_pending = []
            to_promote = []
            for pending in detected_bullish_fvgs:
                fvg_bar, inv_level, gap_sz, atr_v, fvg_sd = pending
                if fvg_sd == sd and abs(i - fvg_bar) <= fvg_window_left:
                    # Upgrade to 8-element: add swept_level + fvg_other_bound + sweep_bar (FVG top = low[fvg_bar])
                    to_promote.append((fvg_bar, inv_level, gap_sz, atr_v, fvg_sd, _swept_c, float(long_fvg_top_arr[fvg_bar]), i))
                else:
                    still_pending.append(pending)
            if first_fvg_only:
                if to_promote and not any(p[4] == sd for p in active_for_short):
                    first = min(to_promote, key=lambda p: p[0])
                    active_for_short.append(first)
            else:
                active_for_short.extend(to_promote)
            detected_bullish_fvgs = still_pending

        # D) Sweep of swing LOW at bar i → promote bearish FVGs within window → active_for_long
        if use_inversion and valid_sweep_low and take_longs:
            _swept_d = float(swept_low_level)
            still_pending = []
            to_promote = []
            for pending in detected_bearish_fvgs:
                fvg_bar, inv_level, gap_sz, atr_v, fvg_sd = pending
                if fvg_sd == sd and abs(i - fvg_bar) <= fvg_window_left:
                    # Upgrade to 8-element: add swept_level + fvg_other_bound + sweep_bar (FVG bottom = high[fvg_bar])
                    to_promote.append((fvg_bar, inv_level, gap_sz, atr_v, fvg_sd, _swept_d, float(short_fvg_bot_arr[fvg_bar]), i))
                else:
                    still_pending.append(pending)
            if first_fvg_only:
                if to_promote and not any(p[4] == sd for p in active_for_long):
                    first = min(to_promote, key=lambda p: p[0])
                    active_for_long.append(first)
            else:
                active_for_long.extend(to_promote)
            detected_bearish_fvgs = still_pending

        # E0) CISD confirmation path: sweep first, then close through the
        # body-level that started the most recent internal opposite leg.
        if use_cisd and in_entry[i] and sd not in seen_cisd_days:
            if take_longs and recent_sweep_lows and cisd["bullish_cisd"][i]:
                sweep_bar, swept_lv, _ = recent_sweep_lows[-1]
                cisd_level = float(cisd["bullish_level"][i])
                cisd_level_bar = int(cisd["bullish_level_bar"][i])
                if np.isfinite(cisd_level) and cisd_level_bar >= 0:
                    _orb_r = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
                    _resolved_entry_mode = _resolve_lsi_entry_mode(
                        entry_mode=entry_mode,
                        bar_minutes=bar_minutes,
                        sweep_to_inversion_bars=i - sweep_bar,
                        close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
                    )
                    _entry_price = cisd_level if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else close[i]
                    _signal_bar = i if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else i - 1
                    _absolute_stop = float(np.min(low[sweep_bar:i + 1]))
                    _atr_points, _orb_points = _resolve_lsi_session_stop_points(
                        session=session,
                        daily_atr=float(daily_atr[i]),
                        orb_range=_orb_r,
                    )
                    _actual_stop = _resolve_lsi_stop_price(
                        direction=1,
                        entry_price=_entry_price,
                        absolute_stop_price=_absolute_stop,
                        fvg_stop_price=float(low[i]),
                        gap_size=abs(float(close[i]) - cisd_level),
                        atr_points=_atr_points,
                        orb_points=_orb_points,
                        stop_mode=stop_mode,
                    )
                    _risk = _entry_price - _actual_stop
                    _structural_risk = _entry_price - _absolute_stop
                    if _risk > 0.0 and _structural_risk > 0.0:
                        _tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                            target_mode=target_mode,
                            direction=1,
                            entry_price=_entry_price,
                            actual_risk_pts=_risk,
                            structural_risk_pts=_structural_risk,
                            rr=rr,
                            tp1_ratio=tp1_ratio,
                            left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                            high=high,
                            low=low,
                            pivot_arrays=target_pivot_arrays,
                            min_tick=min_tick,
                        )
                        _tp1_est = _entry_price + _tp1_dist
                        _path_clear = True
                        if clean_path:
                            scan_start = max(0, i - 100)
                            for j in range(scan_start, i + 1):
                                if short_fvg_bool[j]:
                                    fvg_bot = short_fvg_bot_arr[j]
                                    fvg_top = short_fvg_top_arr[j]
                                    if fvg_bot < _tp1_est and fvg_top > _entry_price:
                                        _path_clear = False
                                        break
                        _lrlr_match = _detect_candidate_lrlr(
                            high=high,
                            low=low,
                            bar_minutes=bar_minutes,
                            left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                            direction=1,
                            entry_price=_entry_price,
                            tp1_price=_tp1_est,
                            daily_atr=float(daily_atr[i]),
                            settings=lrlr_settings,
                            pivot_arrays=lrlr_pivot_arrays,
                        )
                        if _path_clear and not _lrlr_gate_blocks(_lrlr_match, lrlr_settings):
                            _swing_level = 1e38
                            if be_swing_n_left > 0:
                                _search_start = cisd_level_bar - 1
                                for _j in range(_search_start, max(-1, _search_start - 50), -1):
                                    _is_pivot = True
                                    for _k in range(1, be_swing_n_left + 1):
                                        if _j - _k < 0 or high[_j] <= high[_j - _k]:
                                            _is_pivot = False
                                            break
                                    if _is_pivot and high[_j] > _entry_price:
                                        _swing_level = float(high[_j])
                                        break
                            seen_cisd_days.add(sd)
                            candidates.append(_SetupCandidate(
                                date_str=str(dates[i]),
                                session=session.name,
                                direction=1,
                                signal_bar=_signal_bar,
                                entry_price=_entry_price,
                                gap_size=abs(float(close[i]) - cisd_level),
                                daily_atr=float(daily_atr[i]),
                                orb_range=_orb_r,
                                structural_stop_price=_actual_stop,
                                lsi_absolute_stop_price=_absolute_stop,
                                lsi_swept_level=float(swept_lv),
                                lsi_fvg_bar=cisd_level_bar,
                                lsi_sweep_bar=sweep_bar,
                                lsi_fvg_top=cisd_level,
                                lsi_fvg_bottom=cisd_level,
                                lsi_confirmation_type="cisd",
                                lsi_cisd_level=cisd_level,
                                lsi_cisd_bar=cisd_level_bar,
                                lsi_internal_swing_level=_swing_level,
                                fvg_to_inversion_bars=i - cisd_level_bar,
                                sweep_to_inversion_bars=i - sweep_bar,
                                lsi_lrlr_present=_lrlr_match.present,
                                lsi_lrlr_level_count=_lrlr_match.level_count,
                                lsi_lrlr_nearest_level_price=_lrlr_match.nearest_level_price,
                                lsi_lrlr_farthest_level_price=_lrlr_match.farthest_level_price,
                                lsi_lrlr_span_bars=_lrlr_match.span_bars,
                                lsi_lrlr_price_span_atr=_lrlr_match.price_span_atr,
                                lsi_lrlr_slope_atr_per_bar=_lrlr_match.slope_atr_per_bar,
                                lsi_lrlr_fit_error_atr=_lrlr_match.fit_error_atr,
                                lsi_lrlr_tp1_path_present=_lrlr_match.tp1_path_present,
                                lsi_lrlr_nearest_tp1_gap_atr=_lrlr_match.nearest_tp1_gap_atr,
                            ))

            if take_shorts and sd not in seen_cisd_days and recent_sweep_highs and cisd["bearish_cisd"][i]:
                sweep_bar, swept_lv, _ = recent_sweep_highs[-1]
                cisd_level = float(cisd["bearish_level"][i])
                cisd_level_bar = int(cisd["bearish_level_bar"][i])
                if np.isfinite(cisd_level) and cisd_level_bar >= 0:
                    _orb_r = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
                    _resolved_entry_mode = _resolve_lsi_entry_mode(
                        entry_mode=entry_mode,
                        bar_minutes=bar_minutes,
                        sweep_to_inversion_bars=i - sweep_bar,
                        close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
                    )
                    _entry_price = cisd_level if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else close[i]
                    _signal_bar = i if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else i - 1
                    _absolute_stop = float(np.max(high[sweep_bar:i + 1]))
                    _atr_points, _orb_points = _resolve_lsi_session_stop_points(
                        session=session,
                        daily_atr=float(daily_atr[i]),
                        orb_range=_orb_r,
                    )
                    _actual_stop = _resolve_lsi_stop_price(
                        direction=-1,
                        entry_price=_entry_price,
                        absolute_stop_price=_absolute_stop,
                        fvg_stop_price=float(high[i]),
                        gap_size=abs(float(close[i]) - cisd_level),
                        atr_points=_atr_points,
                        orb_points=_orb_points,
                        stop_mode=stop_mode,
                    )
                    _risk = _actual_stop - _entry_price
                    _structural_risk = _absolute_stop - _entry_price
                    if _risk > 0.0 and _structural_risk > 0.0:
                        _tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                            target_mode=target_mode,
                            direction=-1,
                            entry_price=_entry_price,
                            actual_risk_pts=_risk,
                            structural_risk_pts=_structural_risk,
                            rr=rr,
                            tp1_ratio=tp1_ratio,
                            left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                            high=high,
                            low=low,
                            pivot_arrays=target_pivot_arrays,
                            min_tick=min_tick,
                        )
                        _tp1_est = _entry_price - _tp1_dist
                        _path_clear = True
                        if clean_path:
                            scan_start = max(0, i - 100)
                            for j in range(scan_start, i + 1):
                                if long_fvg_bool[j]:
                                    fvg_bot = long_fvg_bot_arr[j]
                                    fvg_top = long_fvg_top_arr[j]
                                    if fvg_bot < _entry_price and fvg_top > _tp1_est:
                                        _path_clear = False
                                        break
                        _lrlr_match = _detect_candidate_lrlr(
                            high=high,
                            low=low,
                            bar_minutes=bar_minutes,
                            left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                            direction=-1,
                            entry_price=_entry_price,
                            tp1_price=_tp1_est,
                            daily_atr=float(daily_atr[i]),
                            settings=lrlr_settings,
                            pivot_arrays=lrlr_pivot_arrays,
                        )
                        if _path_clear and not _lrlr_gate_blocks(_lrlr_match, lrlr_settings):
                            _swing_level = -1e38
                            if be_swing_n_left > 0:
                                _search_start = cisd_level_bar - 1
                                for _j in range(_search_start, max(-1, _search_start - 50), -1):
                                    _is_pivot = True
                                    for _k in range(1, be_swing_n_left + 1):
                                        if _j - _k < 0 or low[_j] >= low[_j - _k]:
                                            _is_pivot = False
                                            break
                                    if _is_pivot and low[_j] < _entry_price:
                                        _swing_level = float(low[_j])
                                        break
                            seen_cisd_days.add(sd)
                            candidates.append(_SetupCandidate(
                                date_str=str(dates[i]),
                                session=session.name,
                                direction=-1,
                                signal_bar=_signal_bar,
                                entry_price=_entry_price,
                                gap_size=abs(float(close[i]) - cisd_level),
                                daily_atr=float(daily_atr[i]),
                                orb_range=_orb_r,
                                structural_stop_price=_actual_stop,
                                lsi_absolute_stop_price=_absolute_stop,
                                lsi_swept_level=float(swept_lv),
                                lsi_fvg_bar=cisd_level_bar,
                                lsi_sweep_bar=sweep_bar,
                                lsi_fvg_top=cisd_level,
                                lsi_fvg_bottom=cisd_level,
                                lsi_confirmation_type="cisd",
                                lsi_cisd_level=cisd_level,
                                lsi_cisd_bar=cisd_level_bar,
                                lsi_internal_swing_level=_swing_level,
                                fvg_to_inversion_bars=i - cisd_level_bar,
                                sweep_to_inversion_bars=i - sweep_bar,
                                lsi_lrlr_present=_lrlr_match.present,
                                lsi_lrlr_level_count=_lrlr_match.level_count,
                                lsi_lrlr_nearest_level_price=_lrlr_match.nearest_level_price,
                                lsi_lrlr_farthest_level_price=_lrlr_match.farthest_level_price,
                                lsi_lrlr_span_bars=_lrlr_match.span_bars,
                                lsi_lrlr_price_span_atr=_lrlr_match.price_span_atr,
                                lsi_lrlr_slope_atr_per_bar=_lrlr_match.slope_atr_per_bar,
                                lsi_lrlr_fit_error_atr=_lrlr_match.fit_error_atr,
                                lsi_lrlr_tp1_path_present=_lrlr_match.tp1_path_present,
                                lsi_lrlr_nearest_tp1_gap_atr=_lrlr_match.nearest_tp1_gap_atr,
                            ))

        # E) Check active setups for inversion — runs on every bar, discards past-entry-window
        # entries explicitly (mirrors _extract_inversion_candidates pattern).
        remaining_short_active = []
        for pending in active_for_short:
            fvg_bar, inv_level, gap_sz, atr_v, fvg_sd, swept_lv, fvg_other_bound, sweep_bar = pending
            if fvg_sd != sd or i <= fvg_bar:
                remaining_short_active.append(pending)
                continue
            if not in_entry[i]:
                # Past entry window — discard
                continue
            if close[i] < inv_level and sd not in seen_inversion_days:
                seen_inversion_days.add(sd)
                _orb_r = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
                _resolved_entry_mode = _resolve_lsi_entry_mode(
                    entry_mode=entry_mode,
                    bar_minutes=bar_minutes,
                    sweep_to_inversion_bars=i - sweep_bar,
                    close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
                )
                _entry_price = inv_level if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else close[i]
                _signal_bar = i if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else i - 1
                _absolute_stop = float(np.max(high[fvg_bar:i + 1]))
                _fvg_stop = float(low[fvg_bar])  # long_fvg_top = low of fvg bar
                _atr_points, _orb_points = _resolve_lsi_session_stop_points(
                    session=session,
                    daily_atr=float(atr_v),
                    orb_range=_orb_r,
                )
                _actual_stop = _resolve_lsi_stop_price(
                    direction=-1,
                    entry_price=_entry_price,
                    absolute_stop_price=_absolute_stop,
                    fvg_stop_price=_fvg_stop,
                    gap_size=gap_sz,
                    atr_points=_atr_points,
                    orb_points=_orb_points,
                    stop_mode=stop_mode,
                )
                _risk = _actual_stop - _entry_price
                _structural_risk = _absolute_stop - _entry_price
                _tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                    target_mode=target_mode,
                    direction=-1,
                    entry_price=_entry_price,
                    actual_risk_pts=_risk,
                    structural_risk_pts=_structural_risk,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                    left_end_bar=min(fvg_bar, sweep_bar) - 1,
                    high=high,
                    low=low,
                    pivot_arrays=target_pivot_arrays,
                    min_tick=min_tick,
                )
                _tp1_est = _entry_price - _tp1_dist
                if clean_path:
                    _path_clear = True
                    scan_start = max(0, i - 100)
                    for j in range(scan_start, i + 1):
                        if long_fvg_bool[j]:
                            fvg_bot = long_fvg_bot_arr[j]
                            fvg_top = long_fvg_top_arr[j]
                            # Overlap with [_tp1_est, _entry_price]:
                            if fvg_bot < _entry_price and fvg_top > _tp1_est:
                                _path_clear = False
                                break
                    if not _path_clear:
                        remaining_short_active.append(pending)
                        seen_inversion_days.discard(sd)
                        continue
                _lrlr_match = _detect_candidate_lrlr(
                    high=high,
                    low=low,
                    bar_minutes=bar_minutes,
                    left_end_bar=min(fvg_bar, sweep_bar) - 1,
                    direction=-1,
                    entry_price=_entry_price,
                    tp1_price=_tp1_est,
                    daily_atr=atr_v,
                    settings=lrlr_settings,
                    pivot_arrays=lrlr_pivot_arrays,
                )
                if _lrlr_gate_blocks(_lrlr_match, lrlr_settings):
                    remaining_short_active.append(pending)
                    seen_inversion_days.discard(sd)
                    continue
                # Internal swing LOW: search BEFORE the FVG (not [fvg_bar, signal_bar-1] as originally
                # specced). For fvg_limit shorts, bars between fvg_bar and signal_bar have lows ABOVE
                # inv_level (entry price) by LSI definition, so that range yields no valid pivots below
                # entry. The pre-FVG region is where meaningful swing lows reside.
                # SHORT trade: if price falls to sweep swing low after entry, liquidity exhausted → BE
                _swing_level = -1e38  # sentinel = disabled (low[i] <= -1e38 never fires)
                if be_swing_n_left > 0:
                    _search_start = fvg_bar - 3  # bar before the 3-candle FVG pattern
                    for _j in range(_search_start, max(-1, _search_start - 50), -1):
                        _is_pivot = True
                        for _k in range(1, be_swing_n_left + 1):
                            if _j - _k < 0 or low[_j] >= low[_j - _k]:
                                _is_pivot = False
                                break
                        if _is_pivot and low[_j] < _entry_price:
                            _swing_level = float(low[_j])
                            break
                # SHORT LSI FVG zone: fvg_other_bound = long_entry_price[fvg_bar] = low[fvg_bar] (top),
                #                     inv_level = long_fvg_bottom[fvg_bar] = high[fvg_bar-2] (bottom)
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=_signal_bar,
                    entry_price=_entry_price,
                    gap_size=gap_sz,
                    daily_atr=atr_v,
                    orb_range=_orb_r,
                    structural_stop_price=_actual_stop,
                    lsi_absolute_stop_price=_absolute_stop,
                    lsi_swept_level=swept_lv,
                    lsi_fvg_bar=fvg_bar,
                    lsi_sweep_bar=sweep_bar,
                    lsi_fvg_top=fvg_other_bound,
                    lsi_fvg_bottom=inv_level,
                    lsi_confirmation_type="inversion",
                    lsi_internal_swing_level=_swing_level,
                    lsi_lrlr_present=_lrlr_match.present,
                    lsi_lrlr_level_count=_lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=_lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=_lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=_lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=_lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=_lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=_lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=_lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=_lrlr_match.nearest_tp1_gap_atr,
                ))
                continue
            remaining_short_active.append(pending)
        active_for_short = remaining_short_active

        remaining_long_active = []
        for pending in active_for_long:
            fvg_bar, inv_level, gap_sz, atr_v, fvg_sd, swept_lv, fvg_other_bound, sweep_bar = pending
            if fvg_sd != sd or i <= fvg_bar:
                remaining_long_active.append(pending)
                continue
            if not in_entry[i]:
                # Past entry window — discard
                continue
            if close[i] > inv_level and sd not in seen_inversion_days:
                seen_inversion_days.add(sd)
                _orb_r = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
                _resolved_entry_mode = _resolve_lsi_entry_mode(
                    entry_mode=entry_mode,
                    bar_minutes=bar_minutes,
                    sweep_to_inversion_bars=i - sweep_bar,
                    close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
                )
                _entry_price = inv_level if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else close[i]
                _signal_bar = i if _is_lsi_level_limit_entry_mode(_resolved_entry_mode) else i - 1
                _absolute_stop = float(np.min(low[fvg_bar:i + 1]))
                _fvg_stop = float(high[fvg_bar])  # short_fvg_bottom = high of fvg bar
                _atr_points, _orb_points = _resolve_lsi_session_stop_points(
                    session=session,
                    daily_atr=float(atr_v),
                    orb_range=_orb_r,
                )
                _actual_stop = _resolve_lsi_stop_price(
                    direction=1,
                    entry_price=_entry_price,
                    absolute_stop_price=_absolute_stop,
                    fvg_stop_price=_fvg_stop,
                    gap_size=gap_sz,
                    atr_points=_atr_points,
                    orb_points=_orb_points,
                    stop_mode=stop_mode,
                )
                _risk = _entry_price - _actual_stop
                _structural_risk = _entry_price - _absolute_stop
                _tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                    target_mode=target_mode,
                    direction=1,
                    entry_price=_entry_price,
                    actual_risk_pts=_risk,
                    structural_risk_pts=_structural_risk,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                    left_end_bar=min(fvg_bar, sweep_bar) - 1,
                    high=high,
                    low=low,
                    pivot_arrays=target_pivot_arrays,
                    min_tick=min_tick,
                )
                _tp1_est = _entry_price + _tp1_dist
                if clean_path:
                    _path_clear = True
                    scan_start = max(0, i - 100)
                    for j in range(scan_start, i + 1):
                        if short_fvg_bool[j]:
                            fvg_bot = short_fvg_bot_arr[j]
                            fvg_top = short_fvg_top_arr[j]
                            # Overlap with [_entry_price, _tp1_est]:
                            if fvg_bot < _tp1_est and fvg_top > _entry_price:
                                _path_clear = False
                                break
                    if not _path_clear:
                        remaining_long_active.append(pending)
                        seen_inversion_days.discard(sd)
                        continue
                _lrlr_match = _detect_candidate_lrlr(
                    high=high,
                    low=low,
                    bar_minutes=bar_minutes,
                    left_end_bar=min(fvg_bar, sweep_bar) - 1,
                    direction=1,
                    entry_price=_entry_price,
                    tp1_price=_tp1_est,
                    daily_atr=atr_v,
                    settings=lrlr_settings,
                    pivot_arrays=lrlr_pivot_arrays,
                )
                if _lrlr_gate_blocks(_lrlr_match, lrlr_settings):
                    remaining_long_active.append(pending)
                    seen_inversion_days.discard(sd)
                    continue
                # Internal swing HIGH: search BEFORE the FVG (not [fvg_bar, signal_bar-1] as originally
                # specced). For fvg_limit longs, bars between fvg_bar and signal_bar have highs BELOW
                # inv_level (entry price) by LSI definition, so that range yields no valid pivots above
                # entry. The pre-FVG region is where meaningful swing highs reside.
                # LONG trade: if price rises to sweep swing high after entry, liquidity exhausted → BE
                _swing_level = 1e38  # sentinel = disabled (high[i] >= 1e38 never fires)
                if be_swing_n_left > 0:
                    _search_start = fvg_bar - 3  # bar before the 3-candle FVG pattern
                    for _j in range(_search_start, max(-1, _search_start - 50), -1):
                        _is_pivot = True
                        for _k in range(1, be_swing_n_left + 1):
                            if _j - _k < 0 or high[_j] <= high[_j - _k]:
                                _is_pivot = False
                                break
                        if _is_pivot and high[_j] > _entry_price:
                            _swing_level = float(high[_j])
                            break
                # LONG LSI FVG zone: inv_level = short_fvg_top[fvg_bar] = low[fvg_bar-2] (top),
                #                    fvg_other_bound = short_entry_price[fvg_bar] = high[fvg_bar] (bottom)
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=_signal_bar,
                    entry_price=_entry_price,
                    gap_size=gap_sz,
                    daily_atr=atr_v,
                    orb_range=_orb_r,
                    structural_stop_price=_actual_stop,
                    lsi_absolute_stop_price=_absolute_stop,
                    lsi_swept_level=swept_lv,
                    lsi_fvg_bar=fvg_bar,
                    lsi_sweep_bar=sweep_bar,
                    lsi_fvg_top=inv_level,
                    lsi_fvg_bottom=fvg_other_bound,
                    lsi_confirmation_type="inversion",
                    lsi_internal_swing_level=_swing_level,
                    lsi_lrlr_present=_lrlr_match.present,
                    lsi_lrlr_level_count=_lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=_lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=_lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=_lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=_lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=_lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=_lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=_lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=_lrlr_match.nearest_tp1_gap_atr,
                ))
                continue
            remaining_long_active.append(pending)
        active_for_long = remaining_long_active

        # F) Cleanup: discard entries from older session days
        detected_bullish_fvgs = [p for p in detected_bullish_fvgs if p[4] >= sd]
        detected_bearish_fvgs = [p for p in detected_bearish_fvgs if p[4] >= sd]
        active_for_short = [p for p in active_for_short if p[4] >= sd]
        active_for_long = [p for p in active_for_long if p[4] >= sd]

        if swing_highs[i]:
            active_swing_high = float(pivot_high_vals[i])
        if swing_lows[i]:
            active_swing_low = float(pivot_low_vals[i])

    return candidates


def _dt64_to_iso(value: np.datetime64) -> str:
    """Convert datetime64[ns] to ISO string, preserving missing values."""
    if np.isnat(value):
        return ""
    return pd.Timestamp(value).isoformat()


def _extract_htf_lsi_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    valid_long: np.ndarray,
    valid_short: np.ndarray,
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    in_sweep: np.ndarray,
    dates,
    close: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    session,
    *,
    htf_levels: dict[str, np.ndarray] | None = None,
    eqhl_levels: dict[str, np.ndarray] | None = None,
    reference_levels: dict[str, np.ndarray] | None = None,
    reference_instance_ids: dict[str, np.ndarray] | None = None,
    selected_reference_level_names: tuple[str, ...] = (),
    include_htf_levels: bool = True,
    include_eqhl_levels: bool = False,
    fvg_window_left: int = 10,
    fvg_window_right: int = 10,
    direction_filter: str = "both",
    stop_mode: str = "absolute",
    target_mode: str = "risk",
    entry_mode: str = "close",
    close_on_sweep_to_inversion_minutes: int = 0,
    confirmation_mode: str = "inversion",
    cisd_min_leg_bars: int = 2,
    cisd_min_leg_atr_pct: float = 5.0,
    cisd_max_leg_bars: int = 60,
    rr: float = 2.5,
    tp1_ratio: float = 0.5,
    target_swing_n_bars: int = 10,
    min_tick: float = 0.25,
    inversion_ordinal: int = 1,
    max_fvg_to_inversion_bars: int = 0,
    htf_level_tf_minutes: int = 60,
    stale_breach_consumes_pivot: bool = True,
    lrlr_settings: _LSILRLRSettings | None = None,
) -> list[_SetupCandidate]:
    """Extract HTF-LSI candidates using HTF pivots and optional named reference levels."""
    n = len(df)
    high = df["high"].to_numpy(dtype=np.float64)
    low = df["low"].to_numpy(dtype=np.float64)
    open_ = df["open"].to_numpy(dtype=np.float64)
    lrlr_settings = lrlr_settings or _LSILRLRSettings(False, "", 2, 2, 3, 120, 30, 120, 0.18, 0.03, 0.04, False, 0.0)
    bar_minutes = _infer_bar_minutes(df.index)
    lrlr_pivot_arrays = _build_lrlr_pivot_arrays(high, low, lrlr_settings)
    target_pivot_arrays = (
        _build_target_pivot_arrays(high, low, target_swing_n_bars)
        if target_mode == "left_structure"
        else None
    )

    take_shorts = direction_filter in ("both", "short")
    take_longs = direction_filter in ("both", "long")
    use_inversion = confirmation_mode in {"inversion", "inversion_or_cisd"}
    use_cisd = confirmation_mode in {"cisd", "inversion_or_cisd"}

    cisd = detect_internal_cisd(
        open_,
        close,
        daily_atr=daily_atr,
        min_leg_bars=cisd_min_leg_bars,
        min_leg_atr_pct=cisd_min_leg_atr_pct,
        max_leg_bars=cisd_max_leg_bars,
    ) if use_cisd else {}

    long_fvg_bottom = fvg["long_fvg_bottom"]
    short_fvg_top = fvg["short_fvg_top"]
    long_fvg_bool = fvg["long_fvg"]
    short_fvg_bool = fvg["short_fvg"]
    long_fvg_top_arr = fvg["long_entry_price"]
    long_fvg_bot_arr = fvg["long_fvg_bottom"]
    short_fvg_top_arr = fvg["short_fvg_top"]
    short_fvg_bot_arr = fvg["short_entry_price"]

    high_level_sources, low_level_sources = _build_htf_lsi_level_sources(
        htf_levels=htf_levels,
        eqhl_levels=eqhl_levels,
        reference_levels=reference_levels,
        reference_instance_ids=reference_instance_ids,
        selected_reference_level_names=selected_reference_level_names,
        include_htf_levels=include_htf_levels,
        include_eqhl_levels=include_eqhl_levels,
        htf_level_tf_minutes=htf_level_tf_minutes,
    )

    if not high_level_sources and not low_level_sources:
        raise ValueError("htf_lsi requires at least one configured sweep source.")

    detected_bullish_fvgs: list[dict] = []
    detected_bearish_fvgs: list[dict] = []
    active_for_short: list[dict] = []
    active_for_long: list[dict] = []
    recent_sweep_highs: list[dict] = []
    recent_sweep_lows: list[dict] = []
    armed_high_instances: set[tuple[str, int]] = set()
    armed_low_instances: set[tuple[str, int]] = set()
    high_inversion_counts: defaultdict[tuple[str, int], int] = defaultdict(int)
    low_inversion_counts: defaultdict[tuple[str, int], int] = defaultdict(int)

    level_state: dict[str, dict[str, int | bool]] = {
        source["source_name"]: {"instance_id": -10_000_000, "consumed": False}
        for source in (*high_level_sources, *low_level_sources)
    }
    candidates: list[_SetupCandidate] = []

    for i in range(n):
        sd = int(session_day_id[i])

        new_sweep_highs: list[dict] = []
        new_sweep_lows: list[dict] = []

        for source in high_level_sources:
            state = level_state[source["source_name"]]
            instance_ids = source["instance_ids"]
            instance_id = int(instance_ids[i]) if i < len(instance_ids) else -1
            if instance_id != state["instance_id"]:
                state["instance_id"] = instance_id
                state["consumed"] = False

            if not take_shorts or state["consumed"] or instance_id < 0:
                continue

            level_price = float(source["prices"][i])
            if not np.isfinite(level_price) or high[i] <= level_price:
                continue

            valid_sweep = bool(in_sweep[i])
            if valid_sweep or stale_breach_consumes_pivot:
                state["consumed"] = True
            if not valid_sweep:
                continue
            level_key = (str(source["source_name"]), instance_id)
            if not in_entry[i] or level_key in armed_high_instances:
                continue

            level_time_iso = ""
            if source["times"] is not None:
                level_time_iso = _dt64_to_iso(source["times"][i])
            event = {
                "sweep_bar": i,
                "level_price": level_price,
                "session_day": sd,
                "level_key": level_key,
                "level_name": str(source["level_name"]),
                "level_time_iso": level_time_iso,
                "tf_minutes": int(source["tf_minutes"]),
                "source_rank": int(source["source_rank"]),
            }
            recent_sweep_highs.append(event)
            new_sweep_highs.append(event)

        for source in low_level_sources:
            state = level_state[source["source_name"]]
            instance_ids = source["instance_ids"]
            instance_id = int(instance_ids[i]) if i < len(instance_ids) else -1
            if instance_id != state["instance_id"]:
                state["instance_id"] = instance_id
                state["consumed"] = False

            if not take_longs or state["consumed"] or instance_id < 0:
                continue

            level_price = float(source["prices"][i])
            if not np.isfinite(level_price) or low[i] >= level_price:
                continue

            valid_sweep = bool(in_sweep[i])
            if valid_sweep or stale_breach_consumes_pivot:
                state["consumed"] = True
            if not valid_sweep:
                continue
            level_key = (str(source["source_name"]), instance_id)
            if not in_entry[i] or level_key in armed_low_instances:
                continue

            level_time_iso = ""
            if source["times"] is not None:
                level_time_iso = _dt64_to_iso(source["times"][i])
            event = {
                "sweep_bar": i,
                "level_price": level_price,
                "session_day": sd,
                "level_key": level_key,
                "level_name": str(source["level_name"]),
                "level_time_iso": level_time_iso,
                "tf_minutes": int(source["tf_minutes"]),
                "source_rank": int(source["source_rank"]),
            }
            recent_sweep_lows.append(event)
            new_sweep_lows.append(event)

        recent_sweep_highs = [
            sweep for sweep in recent_sweep_highs
            if sweep["session_day"] == sd
            and (i - int(sweep["sweep_bar"])) <= fvg_window_right
            and sweep["level_key"] not in armed_high_instances
        ]
        recent_sweep_lows = [
            sweep for sweep in recent_sweep_lows
            if sweep["session_day"] == sd
            and (i - int(sweep["sweep_bar"])) <= fvg_window_right
            and sweep["level_key"] not in armed_low_instances
        ]

        if use_inversion and valid_long[i] and take_shorts:
            base_entry = {
                "fvg_bar": i,
                "inv_level": float(long_fvg_bottom[i]),
                "gap_sz": float(fvg["long_gap_size"][i]),
                "atr_v": float(daily_atr[i]),
                "sd": sd,
            }
            selected_sweep = _select_recent_htf_sweep(recent_sweep_highs, side="high")
            if selected_sweep is not None:
                active_for_short.append(
                    {
                        **base_entry,
                        "swept_level": float(selected_sweep["level_price"]),
                        "fvg_other_bound": float(long_fvg_top_arr[i]),
                        "sweep_bar": int(selected_sweep["sweep_bar"]),
                        "level_key": selected_sweep["level_key"],
                        "level_time_iso": str(selected_sweep["level_time_iso"]),
                        "reference_level_name": str(selected_sweep["level_name"]),
                        "level_tf_minutes": int(selected_sweep["tf_minutes"]),
                    }
                )
            else:
                detected_bullish_fvgs.append(base_entry)

        if use_inversion and valid_short[i] and take_longs:
            base_entry = {
                "fvg_bar": i,
                "inv_level": float(short_fvg_top[i]),
                "gap_sz": float(fvg["short_gap_size"][i]),
                "atr_v": float(daily_atr[i]),
                "sd": sd,
            }
            selected_sweep = _select_recent_htf_sweep(recent_sweep_lows, side="low")
            if selected_sweep is not None:
                active_for_long.append(
                    {
                        **base_entry,
                        "swept_level": float(selected_sweep["level_price"]),
                        "fvg_other_bound": float(short_fvg_bot_arr[i]),
                        "sweep_bar": int(selected_sweep["sweep_bar"]),
                        "level_key": selected_sweep["level_key"],
                        "level_time_iso": str(selected_sweep["level_time_iso"]),
                        "reference_level_name": str(selected_sweep["level_name"]),
                        "level_tf_minutes": int(selected_sweep["tf_minutes"]),
                    }
                )
            else:
                detected_bearish_fvgs.append(base_entry)

        selected_new_high_sweep = _select_recent_htf_sweep(new_sweep_highs, side="high")
        if use_inversion and selected_new_high_sweep is not None:
            still_pending = []
            to_promote: list[dict] = []
            for pending in detected_bullish_fvgs:
                if pending["sd"] == sd and abs(i - int(pending["fvg_bar"])) <= fvg_window_left:
                    to_promote.append(
                        {
                            **pending,
                            "swept_level": float(selected_new_high_sweep["level_price"]),
                            "fvg_other_bound": float(long_fvg_top_arr[int(pending["fvg_bar"])]),
                            "sweep_bar": int(selected_new_high_sweep["sweep_bar"]),
                            "level_key": selected_new_high_sweep["level_key"],
                            "level_time_iso": str(selected_new_high_sweep["level_time_iso"]),
                            "reference_level_name": str(selected_new_high_sweep["level_name"]),
                            "level_tf_minutes": int(selected_new_high_sweep["tf_minutes"]),
                        }
                    )
                else:
                    still_pending.append(pending)
            active_for_short.extend(to_promote)
            detected_bullish_fvgs = still_pending

        selected_new_low_sweep = _select_recent_htf_sweep(new_sweep_lows, side="low")
        if use_inversion and selected_new_low_sweep is not None:
            still_pending = []
            to_promote: list[dict] = []
            for pending in detected_bearish_fvgs:
                if pending["sd"] == sd and abs(i - int(pending["fvg_bar"])) <= fvg_window_left:
                    to_promote.append(
                        {
                            **pending,
                            "swept_level": float(selected_new_low_sweep["level_price"]),
                            "fvg_other_bound": float(short_fvg_bot_arr[int(pending["fvg_bar"])]),
                            "sweep_bar": int(selected_new_low_sweep["sweep_bar"]),
                            "level_key": selected_new_low_sweep["level_key"],
                            "level_time_iso": str(selected_new_low_sweep["level_time_iso"]),
                            "reference_level_name": str(selected_new_low_sweep["level_name"]),
                            "level_tf_minutes": int(selected_new_low_sweep["tf_minutes"]),
                        }
                    )
                else:
                    still_pending.append(pending)
            active_for_long.extend(to_promote)
            detected_bearish_fvgs = still_pending

        if use_cisd and in_entry[i]:
            selected_high_sweep = _select_recent_htf_sweep(recent_sweep_highs, side="high")
            if selected_high_sweep is not None and take_shorts and cisd["bearish_cisd"][i]:
                level_key = selected_high_sweep["level_key"]
                if level_key not in armed_high_instances:
                    sweep_bar = int(selected_high_sweep["sweep_bar"])
                    cisd_level = float(cisd["bearish_level"][i])
                    cisd_level_bar = int(cisd["bearish_level_bar"][i])
                    if np.isfinite(cisd_level) and cisd_level_bar >= 0:
                        resolved_entry_mode = _resolve_lsi_entry_mode(
                            entry_mode=entry_mode,
                            bar_minutes=bar_minutes,
                            sweep_to_inversion_bars=i - sweep_bar,
                            close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
                        )
                        entry_price = (
                            cisd_level if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
                        )
                        signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
                        orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
                        absolute_stop = float(np.max(high[sweep_bar:i + 1]))
                        atr_points, orb_points = _resolve_lsi_session_stop_points(
                            session=session,
                            daily_atr=float(daily_atr[i]),
                            orb_range=orb_range,
                        )
                        structural_stop = _resolve_lsi_stop_price(
                            direction=-1,
                            entry_price=entry_price,
                            absolute_stop_price=absolute_stop,
                            fvg_stop_price=float(high[i]),
                            gap_size=abs(float(close[i]) - cisd_level),
                            atr_points=atr_points,
                            orb_points=orb_points,
                            stop_mode=stop_mode,
                        )
                        risk = structural_stop - entry_price
                        structural_risk = absolute_stop - entry_price
                        if risk > 0.0 and structural_risk > 0.0:
                            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                                target_mode=target_mode,
                                direction=-1,
                                entry_price=entry_price,
                                actual_risk_pts=risk,
                                structural_risk_pts=structural_risk,
                                rr=rr,
                                tp1_ratio=tp1_ratio,
                                left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                                high=high,
                                low=low,
                                pivot_arrays=target_pivot_arrays,
                                min_tick=min_tick,
                            )
                            tp1_est = entry_price - tp1_dist
                            lrlr_match = _detect_candidate_lrlr(
                                high=high,
                                low=low,
                                bar_minutes=bar_minutes,
                                left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                                direction=-1,
                                entry_price=entry_price,
                                tp1_price=tp1_est,
                                daily_atr=float(daily_atr[i]),
                                settings=lrlr_settings,
                                pivot_arrays=lrlr_pivot_arrays,
                            )
                            if not _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                                swept_level = float(selected_high_sweep["level_price"])
                                armed_high_instances.add(level_key)
                                candidates.append(
                                    _SetupCandidate(
                                        date_str=str(dates[i]),
                                        session=session.name,
                                        direction=-1,
                                        signal_bar=signal_bar,
                                        entry_price=entry_price,
                                        gap_size=abs(float(close[i]) - cisd_level),
                                        daily_atr=float(daily_atr[i]),
                                        orb_range=orb_range,
                                        structural_stop_price=structural_stop,
                                        lsi_absolute_stop_price=absolute_stop,
                                        lsi_swept_level=swept_level,
                                        lsi_fvg_bar=cisd_level_bar,
                                        lsi_sweep_bar=sweep_bar,
                                        lsi_fvg_top=cisd_level,
                                        lsi_fvg_bottom=cisd_level,
                                        lsi_confirmation_type="cisd",
                                        lsi_cisd_level=cisd_level,
                                        lsi_cisd_bar=cisd_level_bar,
                                        reference_level_name=str(selected_high_sweep["level_name"]),
                                        reference_level_price=swept_level,
                                        htf_level_time=str(selected_high_sweep["level_time_iso"]),
                                        htf_level_price=swept_level,
                                        htf_level_side="high",
                                        htf_level_tf_minutes=int(selected_high_sweep["tf_minutes"]),
                                        fvg_to_inversion_bars=i - cisd_level_bar,
                                        sweep_to_inversion_bars=i - sweep_bar,
                                        lsi_lrlr_present=lrlr_match.present,
                                        lsi_lrlr_level_count=lrlr_match.level_count,
                                        lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                                        lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                                        lsi_lrlr_span_bars=lrlr_match.span_bars,
                                        lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                                        lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                                        lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                                        lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                                        lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                                    )
                                )

            selected_low_sweep = _select_recent_htf_sweep(recent_sweep_lows, side="low")
            if selected_low_sweep is not None and take_longs and cisd["bullish_cisd"][i]:
                level_key = selected_low_sweep["level_key"]
                if level_key not in armed_low_instances:
                    sweep_bar = int(selected_low_sweep["sweep_bar"])
                    cisd_level = float(cisd["bullish_level"][i])
                    cisd_level_bar = int(cisd["bullish_level_bar"][i])
                    if np.isfinite(cisd_level) and cisd_level_bar >= 0:
                        resolved_entry_mode = _resolve_lsi_entry_mode(
                            entry_mode=entry_mode,
                            bar_minutes=bar_minutes,
                            sweep_to_inversion_bars=i - sweep_bar,
                            close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
                        )
                        entry_price = (
                            cisd_level if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
                        )
                        signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
                        orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
                        absolute_stop = float(np.min(low[sweep_bar:i + 1]))
                        atr_points, orb_points = _resolve_lsi_session_stop_points(
                            session=session,
                            daily_atr=float(daily_atr[i]),
                            orb_range=orb_range,
                        )
                        structural_stop = _resolve_lsi_stop_price(
                            direction=1,
                            entry_price=entry_price,
                            absolute_stop_price=absolute_stop,
                            fvg_stop_price=float(low[i]),
                            gap_size=abs(float(close[i]) - cisd_level),
                            atr_points=atr_points,
                            orb_points=orb_points,
                            stop_mode=stop_mode,
                        )
                        risk = entry_price - structural_stop
                        structural_risk = entry_price - absolute_stop
                        if risk > 0.0 and structural_risk > 0.0:
                            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                                target_mode=target_mode,
                                direction=1,
                                entry_price=entry_price,
                                actual_risk_pts=risk,
                                structural_risk_pts=structural_risk,
                                rr=rr,
                                tp1_ratio=tp1_ratio,
                                left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                                high=high,
                                low=low,
                                pivot_arrays=target_pivot_arrays,
                                min_tick=min_tick,
                            )
                            tp1_est = entry_price + tp1_dist
                            lrlr_match = _detect_candidate_lrlr(
                                high=high,
                                low=low,
                                bar_minutes=bar_minutes,
                                left_end_bar=min(cisd_level_bar, sweep_bar) - 1,
                                direction=1,
                                entry_price=entry_price,
                                tp1_price=tp1_est,
                                daily_atr=float(daily_atr[i]),
                                settings=lrlr_settings,
                                pivot_arrays=lrlr_pivot_arrays,
                            )
                            if not _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                                swept_level = float(selected_low_sweep["level_price"])
                                armed_low_instances.add(level_key)
                                candidates.append(
                                    _SetupCandidate(
                                        date_str=str(dates[i]),
                                        session=session.name,
                                        direction=1,
                                        signal_bar=signal_bar,
                                        entry_price=entry_price,
                                        gap_size=abs(float(close[i]) - cisd_level),
                                        daily_atr=float(daily_atr[i]),
                                        orb_range=orb_range,
                                        structural_stop_price=structural_stop,
                                        lsi_absolute_stop_price=absolute_stop,
                                        lsi_swept_level=swept_level,
                                        lsi_fvg_bar=cisd_level_bar,
                                        lsi_sweep_bar=sweep_bar,
                                        lsi_fvg_top=cisd_level,
                                        lsi_fvg_bottom=cisd_level,
                                        lsi_confirmation_type="cisd",
                                        lsi_cisd_level=cisd_level,
                                        lsi_cisd_bar=cisd_level_bar,
                                        reference_level_name=str(selected_low_sweep["level_name"]),
                                        reference_level_price=swept_level,
                                        htf_level_time=str(selected_low_sweep["level_time_iso"]),
                                        htf_level_price=swept_level,
                                        htf_level_side="low",
                                        htf_level_tf_minutes=int(selected_low_sweep["tf_minutes"]),
                                        fvg_to_inversion_bars=i - cisd_level_bar,
                                        sweep_to_inversion_bars=i - sweep_bar,
                                        lsi_lrlr_present=lrlr_match.present,
                                        lsi_lrlr_level_count=lrlr_match.level_count,
                                        lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                                        lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                                        lsi_lrlr_span_bars=lrlr_match.span_bars,
                                        lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                                        lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                                        lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                                        lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                                        lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                                    )
                                )

        remaining_short_active = []
        invertible_short_by_level: defaultdict[tuple[str, int], list[dict]] = defaultdict(list)
        for pending in active_for_short:
            if pending["level_key"] in armed_high_instances:
                continue
            if pending["sd"] != sd or i <= int(pending["fvg_bar"]):
                remaining_short_active.append(pending)
                continue
            if not in_entry[i]:
                continue
            if close[i] < float(pending["inv_level"]):
                fvg_to_inversion = i - int(pending["fvg_bar"])
                if max_fvg_to_inversion_bars > 0 and fvg_to_inversion > max_fvg_to_inversion_bars:
                    continue
                invertible_short_by_level[pending["level_key"]].append(pending)
                continue
            remaining_short_active.append(pending)
        active_for_short = remaining_short_active

        for level_key, pending_list in invertible_short_by_level.items():
            high_inversion_counts[level_key] += 1
            current_inversion_ordinal = high_inversion_counts[level_key]
            if current_inversion_ordinal != inversion_ordinal:
                continue

            pending = pending_list[0]
            fvg_bar = int(pending["fvg_bar"])
            sweep_bar = int(pending["sweep_bar"])
            swept_level = float(pending["swept_level"])
            fvg_to_inversion = i - fvg_bar
            resolved_entry_mode = _resolve_lsi_entry_mode(
                entry_mode=entry_mode,
                bar_minutes=bar_minutes,
                sweep_to_inversion_bars=i - sweep_bar,
                close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
            )
            entry_price = (
                float(pending["inv_level"]) if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
            )
            signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
            orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
            absolute_stop = float(np.max(high[fvg_bar:i + 1]))
            fvg_stop = float(low[fvg_bar])
            atr_points, orb_points = _resolve_lsi_session_stop_points(
                session=session,
                daily_atr=float(pending["atr_v"]),
                orb_range=orb_range,
            )
            structural_stop = _resolve_lsi_stop_price(
                direction=-1,
                entry_price=entry_price,
                absolute_stop_price=absolute_stop,
                fvg_stop_price=fvg_stop,
                gap_size=float(pending["gap_sz"]),
                atr_points=atr_points,
                orb_points=orb_points,
                stop_mode=stop_mode,
            )
            risk = structural_stop - entry_price
            structural_risk = absolute_stop - entry_price
            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=-1,
                entry_price=entry_price,
                actual_risk_pts=risk,
                structural_risk_pts=structural_risk,
                rr=rr,
                tp1_ratio=tp1_ratio,
                left_end_bar=min(fvg_bar, sweep_bar) - 1,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=min_tick,
            )
            tp1_est = entry_price - tp1_dist
            lrlr_match = _detect_candidate_lrlr(
                high=high,
                low=low,
                bar_minutes=bar_minutes,
                left_end_bar=min(fvg_bar, sweep_bar) - 1,
                direction=-1,
                entry_price=entry_price,
                tp1_price=tp1_est,
                daily_atr=float(pending["atr_v"]),
                settings=lrlr_settings,
                pivot_arrays=lrlr_pivot_arrays,
            )
            if _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                continue
            armed_high_instances.add(level_key)
            candidates.append(
                _SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=signal_bar,
                    entry_price=entry_price,
                    gap_size=float(pending["gap_sz"]),
                    daily_atr=float(pending["atr_v"]),
                    orb_range=orb_range,
                    structural_stop_price=structural_stop,
                    lsi_absolute_stop_price=absolute_stop,
                    lsi_swept_level=swept_level,
                    lsi_fvg_bar=fvg_bar,
                    lsi_sweep_bar=sweep_bar,
                    lsi_fvg_top=float(pending["fvg_other_bound"]),
                    lsi_fvg_bottom=float(pending["inv_level"]),
                    lsi_confirmation_type="inversion",
                    reference_level_name=str(pending["reference_level_name"]),
                    reference_level_price=swept_level if pending["reference_level_name"] else 0.0,
                    htf_level_time=str(pending["level_time_iso"]),
                    htf_level_price=swept_level,
                    htf_level_side="high",
                    htf_level_tf_minutes=int(pending["level_tf_minutes"]),
                    fvg_to_inversion_bars=fvg_to_inversion,
                    sweep_to_inversion_bars=i - sweep_bar,
                    inversion_ordinal=current_inversion_ordinal,
                    lsi_lrlr_present=lrlr_match.present,
                    lsi_lrlr_level_count=lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                )
            )

        remaining_long_active = []
        invertible_long_by_level: defaultdict[tuple[str, int], list[dict]] = defaultdict(list)
        for pending in active_for_long:
            if pending["level_key"] in armed_low_instances:
                continue
            if pending["sd"] != sd or i <= int(pending["fvg_bar"]):
                remaining_long_active.append(pending)
                continue
            if not in_entry[i]:
                continue
            if close[i] > float(pending["inv_level"]):
                fvg_to_inversion = i - int(pending["fvg_bar"])
                if max_fvg_to_inversion_bars > 0 and fvg_to_inversion > max_fvg_to_inversion_bars:
                    continue
                invertible_long_by_level[pending["level_key"]].append(pending)
                continue
            remaining_long_active.append(pending)
        active_for_long = remaining_long_active

        for level_key, pending_list in invertible_long_by_level.items():
            low_inversion_counts[level_key] += 1
            current_inversion_ordinal = low_inversion_counts[level_key]
            if current_inversion_ordinal != inversion_ordinal:
                continue

            pending = pending_list[0]
            fvg_bar = int(pending["fvg_bar"])
            sweep_bar = int(pending["sweep_bar"])
            swept_level = float(pending["swept_level"])
            fvg_to_inversion = i - fvg_bar
            resolved_entry_mode = _resolve_lsi_entry_mode(
                entry_mode=entry_mode,
                bar_minutes=bar_minutes,
                sweep_to_inversion_bars=i - sweep_bar,
                close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
            )
            entry_price = (
                float(pending["inv_level"]) if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
            )
            signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
            orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
            absolute_stop = float(np.min(low[fvg_bar:i + 1]))
            fvg_stop = float(high[fvg_bar])
            atr_points, orb_points = _resolve_lsi_session_stop_points(
                session=session,
                daily_atr=float(pending["atr_v"]),
                orb_range=orb_range,
            )
            structural_stop = _resolve_lsi_stop_price(
                direction=1,
                entry_price=entry_price,
                absolute_stop_price=absolute_stop,
                fvg_stop_price=fvg_stop,
                gap_size=float(pending["gap_sz"]),
                atr_points=atr_points,
                orb_points=orb_points,
                stop_mode=stop_mode,
            )
            risk = entry_price - structural_stop
            structural_risk = entry_price - absolute_stop
            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=1,
                entry_price=entry_price,
                actual_risk_pts=risk,
                structural_risk_pts=structural_risk,
                rr=rr,
                tp1_ratio=tp1_ratio,
                left_end_bar=min(fvg_bar, sweep_bar) - 1,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=min_tick,
            )
            tp1_est = entry_price + tp1_dist
            lrlr_match = _detect_candidate_lrlr(
                high=high,
                low=low,
                bar_minutes=bar_minutes,
                left_end_bar=min(fvg_bar, sweep_bar) - 1,
                direction=1,
                entry_price=entry_price,
                tp1_price=tp1_est,
                daily_atr=float(pending["atr_v"]),
                settings=lrlr_settings,
                pivot_arrays=lrlr_pivot_arrays,
            )
            if _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                continue
            armed_low_instances.add(level_key)
            candidates.append(
                _SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=signal_bar,
                    entry_price=entry_price,
                    gap_size=float(pending["gap_sz"]),
                    daily_atr=float(pending["atr_v"]),
                    orb_range=orb_range,
                    structural_stop_price=structural_stop,
                    lsi_absolute_stop_price=absolute_stop,
                    lsi_swept_level=swept_level,
                    lsi_fvg_bar=fvg_bar,
                    lsi_sweep_bar=sweep_bar,
                    lsi_fvg_top=float(pending["inv_level"]),
                    lsi_fvg_bottom=float(pending["fvg_other_bound"]),
                    lsi_confirmation_type="inversion",
                    reference_level_name=str(pending["reference_level_name"]),
                    reference_level_price=swept_level if pending["reference_level_name"] else 0.0,
                    htf_level_time=str(pending["level_time_iso"]),
                    htf_level_price=swept_level,
                    htf_level_side="low",
                    htf_level_tf_minutes=int(pending["level_tf_minutes"]),
                    fvg_to_inversion_bars=fvg_to_inversion,
                    sweep_to_inversion_bars=i - sweep_bar,
                    inversion_ordinal=current_inversion_ordinal,
                    lsi_lrlr_present=lrlr_match.present,
                    lsi_lrlr_level_count=lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                )
            )

        detected_bullish_fvgs = [p for p in detected_bullish_fvgs if p["sd"] >= sd]
        detected_bearish_fvgs = [p for p in detected_bearish_fvgs if p["sd"] >= sd]
        active_for_short = [p for p in active_for_short if p["sd"] >= sd and p["level_key"] not in armed_high_instances]
        active_for_long = [p for p in active_for_long if p["sd"] >= sd and p["level_key"] not in armed_low_instances]

    return candidates


def _extract_reference_lsi_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    valid_long: np.ndarray,
    valid_short: np.ndarray,
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    dates,
    close: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    session,
    *,
    reference_levels: dict[str, np.ndarray],
    reference_instance_ids: dict[str, np.ndarray],
    gap_lookback_bars: int = 12,
    inversion_max_bars: int = 18,
    direction_filter: str = "both",
    stop_mode: str = "absolute",
    entry_mode: str = "level_limit",
    close_on_sweep_to_inversion_minutes: int = 0,
    gap_entry_edge: str = "near",
    selected_level_names: tuple[str, ...] | None = None,
    confirmation_mode: str = "inversion",
    cisd_min_leg_bars: int = 2,
    cisd_min_leg_atr_pct: float = 5.0,
    cisd_max_leg_bars: int = 60,
    rr: float = 2.5,
    tp1_ratio: float = 0.5,
    target_mode: str = "risk",
    target_swing_n_bars: int = 10,
    min_tick: float = 0.25,
    lrlr_settings: _LSILRLRSettings | None = None,
) -> list[_SetupCandidate]:
    """Extract reference-level sweep inversion candidates.

    Setup logic:
    1. A completed reference level is swept during the active entry window.
    2. A same-direction FVG must have formed before the sweep within
       ``gap_lookback_bars``.
    3. Price must invert that FVG within ``inversion_max_bars`` after the sweep.
    4. Entry is a limit at the configured FVG edge.

    High-side level sweeps create short candidates, low-side sweeps create long
    candidates. Each published level instance can only sweep once.
    """
    n = len(df)
    open_ = df["open"].values
    high = df["high"].values
    low = df["low"].values
    lrlr_settings = lrlr_settings or _LSILRLRSettings(False, "", 2, 2, 3, 120, 30, 120, 0.18, 0.03, 0.04, False, 0.0)
    bar_minutes = _infer_bar_minutes(df.index)
    lrlr_pivot_arrays = _build_lrlr_pivot_arrays(high, low, lrlr_settings)
    target_pivot_arrays = (
        _build_target_pivot_arrays(high, low, target_swing_n_bars)
        if target_mode == "left_structure"
        else None
    )

    take_shorts = direction_filter in ("both", "short")
    take_longs = direction_filter in ("both", "long")
    use_inversion = confirmation_mode in {"inversion", "inversion_or_cisd"}
    use_cisd = confirmation_mode in {"cisd", "inversion_or_cisd"}

    cisd = detect_internal_cisd(
        open_,
        close,
        daily_atr=daily_atr,
        min_leg_bars=cisd_min_leg_bars,
        min_leg_atr_pct=cisd_min_leg_atr_pct,
        max_leg_bars=cisd_max_leg_bars,
    ) if use_cisd else {}

    long_fvg_bottom = fvg["long_fvg_bottom"]
    long_fvg_top = fvg["long_entry_price"]
    short_fvg_top = fvg["short_fvg_top"]
    short_fvg_bottom = fvg["short_entry_price"]

    if selected_level_names is None:
        selected_level_names = REF_LSI_LEVELS

    high_side_levels = tuple(level for level in selected_level_names if level.endswith("_high"))
    low_side_levels = tuple(level for level in selected_level_names if level.endswith("_low"))

    level_state: dict[str, dict[str, int | bool]] = {
        name: {"instance_id": -10_000_000, "consumed": False}
        for name in (*high_side_levels, *low_side_levels)
    }

    active_short_events: list[dict] = []
    active_long_events: list[dict] = []
    active_short_cisd_events: list[dict] = []
    active_long_cisd_events: list[dict] = []
    armed_high_instances: set[tuple[str, int]] = set()
    armed_low_instances: set[tuple[str, int]] = set()
    candidates: list[_SetupCandidate] = []

    for i in range(n):
        sd = session_day_id[i]

        # Reset per-level consumption when a new published level instance arrives.
        for level_name, state in level_state.items():
            instance_ids = reference_instance_ids[level_name]
            instance_id = int(instance_ids[i]) if i < len(instance_ids) else -1
            if instance_id != state["instance_id"]:
                state["instance_id"] = instance_id
                state["consumed"] = False

        # A reference level can only create one sweep event per published instance.
        if in_entry[i] and in_rth[i]:
            if take_shorts:
                for level_name in high_side_levels:
                    level = float(reference_levels[level_name][i])
                    if not np.isfinite(level):
                        continue
                    state = level_state[level_name]
                    if state["consumed"]:
                        continue
                    if not (open_[i] <= level and high[i] > level):
                        continue
                    state["consumed"] = True
                    level_key = (level_name, int(reference_instance_ids[level_name][i]))
                    if level_key in armed_high_instances:
                        continue
                    lo = max(0, i - gap_lookback_bars)
                    eligible_fvg_bars = [
                        j for j in range(lo, i)
                        if session_day_id[j] == sd and valid_long[j]
                    ]
                    if use_cisd:
                        active_short_cisd_events.append(
                            {
                                "sd": sd,
                                "sweep_bar": i,
                                "expiry_bar": i + inversion_max_bars,
                                "level_name": level_name,
                                "level_price": level,
                                "level_key": level_key,
                            }
                        )
                    if use_inversion and eligible_fvg_bars:
                        active_short_events.append(
                            {
                                "sd": sd,
                                "sweep_bar": i,
                                "expiry_bar": i + inversion_max_bars,
                                "level_name": level_name,
                                "level_price": level,
                                "level_key": level_key,
                                "fvg_bars": eligible_fvg_bars,
                            }
                        )

            if take_longs:
                for level_name in low_side_levels:
                    level = float(reference_levels[level_name][i])
                    if not np.isfinite(level):
                        continue
                    state = level_state[level_name]
                    if state["consumed"]:
                        continue
                    if not (open_[i] >= level and low[i] < level):
                        continue
                    state["consumed"] = True
                    level_key = (level_name, int(reference_instance_ids[level_name][i]))
                    if level_key in armed_low_instances:
                        continue
                    lo = max(0, i - gap_lookback_bars)
                    eligible_fvg_bars = [
                        j for j in range(lo, i)
                        if session_day_id[j] == sd and valid_short[j]
                    ]
                    if use_cisd:
                        active_long_cisd_events.append(
                            {
                                "sd": sd,
                                "sweep_bar": i,
                                "expiry_bar": i + inversion_max_bars,
                                "level_name": level_name,
                                "level_price": level,
                                "level_key": level_key,
                            }
                        )
                    if use_inversion and eligible_fvg_bars:
                        active_long_events.append(
                            {
                                "sd": sd,
                                "sweep_bar": i,
                                "expiry_bar": i + inversion_max_bars,
                                "level_name": level_name,
                                "level_price": level,
                                "level_key": level_key,
                                "fvg_bars": eligible_fvg_bars,
                            }
                        )

        remaining_short_cisd_events: list[dict] = []
        for event in active_short_cisd_events:
            if event["level_key"] in armed_high_instances:
                continue
            if event["sd"] != sd:
                continue
            if i <= event["sweep_bar"]:
                remaining_short_cisd_events.append(event)
                continue
            if i > event["expiry_bar"] or not in_entry[i]:
                continue
            if not cisd["bearish_cisd"][i]:
                remaining_short_cisd_events.append(event)
                continue

            cisd_level = float(cisd["bearish_level"][i])
            cisd_level_bar = int(cisd["bearish_level_bar"][i])
            if not np.isfinite(cisd_level) or cisd_level_bar < 0:
                remaining_short_cisd_events.append(event)
                continue

            resolved_entry_mode = _resolve_lsi_entry_mode(
                entry_mode=entry_mode,
                bar_minutes=bar_minutes,
                sweep_to_inversion_bars=i - int(event["sweep_bar"]),
                close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
            )
            entry_price = cisd_level if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
            signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
            orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
            absolute_stop = float(np.max(high[int(event["sweep_bar"]):i + 1]))
            atr_points, orb_points = _resolve_lsi_session_stop_points(
                session=session,
                daily_atr=float(daily_atr[i]),
                orb_range=orb_range,
            )
            structural_stop = _resolve_lsi_stop_price(
                direction=-1,
                entry_price=entry_price,
                absolute_stop_price=absolute_stop,
                fvg_stop_price=float(high[i]),
                gap_size=abs(float(close[i]) - cisd_level),
                atr_points=atr_points,
                orb_points=orb_points,
                stop_mode=stop_mode,
            )
            risk = structural_stop - entry_price
            structural_risk = absolute_stop - entry_price
            if risk <= 0.0 or structural_risk <= 0.0:
                continue
            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=-1,
                entry_price=entry_price,
                actual_risk_pts=risk,
                structural_risk_pts=structural_risk,
                rr=rr,
                tp1_ratio=tp1_ratio,
                left_end_bar=min(cisd_level_bar, int(event["sweep_bar"])) - 1,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=min_tick,
            )
            tp1_est = entry_price - tp1_dist
            lrlr_match = _detect_candidate_lrlr(
                high=high,
                low=low,
                bar_minutes=bar_minutes,
                left_end_bar=min(cisd_level_bar, int(event["sweep_bar"])) - 1,
                direction=-1,
                entry_price=entry_price,
                tp1_price=tp1_est,
                daily_atr=float(daily_atr[i]),
                settings=lrlr_settings,
                pivot_arrays=lrlr_pivot_arrays,
            )
            if _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                remaining_short_cisd_events.append(event)
                continue
            armed_high_instances.add(event["level_key"])
            candidates.append(
                _SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=signal_bar,
                    entry_price=entry_price,
                    gap_size=abs(float(close[i]) - cisd_level),
                    daily_atr=float(daily_atr[i]),
                    orb_range=orb_range,
                    structural_stop_price=structural_stop,
                    lsi_absolute_stop_price=absolute_stop,
                    lsi_swept_level=float(event["level_price"]),
                    lsi_fvg_top=cisd_level,
                    lsi_fvg_bottom=cisd_level,
                    lsi_fvg_bar=cisd_level_bar,
                    lsi_sweep_bar=int(event["sweep_bar"]),
                    lsi_confirmation_type="cisd",
                    lsi_cisd_level=cisd_level,
                    lsi_cisd_bar=cisd_level_bar,
                    reference_level_name=str(event["level_name"]),
                    reference_level_price=float(event["level_price"]),
                    lsi_lrlr_present=lrlr_match.present,
                    lsi_lrlr_level_count=lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                )
            )
        active_short_cisd_events = remaining_short_cisd_events

        remaining_long_cisd_events: list[dict] = []
        for event in active_long_cisd_events:
            if event["level_key"] in armed_low_instances:
                continue
            if event["sd"] != sd:
                continue
            if i <= event["sweep_bar"]:
                remaining_long_cisd_events.append(event)
                continue
            if i > event["expiry_bar"] or not in_entry[i]:
                continue
            if not cisd["bullish_cisd"][i]:
                remaining_long_cisd_events.append(event)
                continue

            cisd_level = float(cisd["bullish_level"][i])
            cisd_level_bar = int(cisd["bullish_level_bar"][i])
            if not np.isfinite(cisd_level) or cisd_level_bar < 0:
                remaining_long_cisd_events.append(event)
                continue

            resolved_entry_mode = _resolve_lsi_entry_mode(
                entry_mode=entry_mode,
                bar_minutes=bar_minutes,
                sweep_to_inversion_bars=i - int(event["sweep_bar"]),
                close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
            )
            entry_price = cisd_level if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
            signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
            orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
            absolute_stop = float(np.min(low[int(event["sweep_bar"]):i + 1]))
            atr_points, orb_points = _resolve_lsi_session_stop_points(
                session=session,
                daily_atr=float(daily_atr[i]),
                orb_range=orb_range,
            )
            structural_stop = _resolve_lsi_stop_price(
                direction=1,
                entry_price=entry_price,
                absolute_stop_price=absolute_stop,
                fvg_stop_price=float(low[i]),
                gap_size=abs(float(close[i]) - cisd_level),
                atr_points=atr_points,
                orb_points=orb_points,
                stop_mode=stop_mode,
            )
            risk = entry_price - structural_stop
            structural_risk = entry_price - absolute_stop
            if risk <= 0.0 or structural_risk <= 0.0:
                continue
            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=1,
                entry_price=entry_price,
                actual_risk_pts=risk,
                structural_risk_pts=structural_risk,
                rr=rr,
                tp1_ratio=tp1_ratio,
                left_end_bar=min(cisd_level_bar, int(event["sweep_bar"])) - 1,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=min_tick,
            )
            tp1_est = entry_price + tp1_dist
            lrlr_match = _detect_candidate_lrlr(
                high=high,
                low=low,
                bar_minutes=bar_minutes,
                left_end_bar=min(cisd_level_bar, int(event["sweep_bar"])) - 1,
                direction=1,
                entry_price=entry_price,
                tp1_price=tp1_est,
                daily_atr=float(daily_atr[i]),
                settings=lrlr_settings,
                pivot_arrays=lrlr_pivot_arrays,
            )
            if _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                remaining_long_cisd_events.append(event)
                continue
            armed_low_instances.add(event["level_key"])
            candidates.append(
                _SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=signal_bar,
                    entry_price=entry_price,
                    gap_size=abs(float(close[i]) - cisd_level),
                    daily_atr=float(daily_atr[i]),
                    orb_range=orb_range,
                    structural_stop_price=structural_stop,
                    lsi_absolute_stop_price=absolute_stop,
                    lsi_swept_level=float(event["level_price"]),
                    lsi_fvg_top=cisd_level,
                    lsi_fvg_bottom=cisd_level,
                    lsi_fvg_bar=cisd_level_bar,
                    lsi_sweep_bar=int(event["sweep_bar"]),
                    lsi_confirmation_type="cisd",
                    lsi_cisd_level=cisd_level,
                    lsi_cisd_bar=cisd_level_bar,
                    reference_level_name=str(event["level_name"]),
                    reference_level_price=float(event["level_price"]),
                    lsi_lrlr_present=lrlr_match.present,
                    lsi_lrlr_level_count=lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                )
            )
        active_long_cisd_events = remaining_long_cisd_events

        remaining_short_events: list[dict] = []
        for event in active_short_events:
            if event["level_key"] in armed_high_instances:
                continue
            if event["sd"] != sd:
                continue
            if i <= event["sweep_bar"]:
                remaining_short_events.append(event)
                continue
            if i > event["expiry_bar"] or not in_entry[i]:
                continue

            inverted = [
                fvg_bar for fvg_bar in event["fvg_bars"]
                if close[i] < long_fvg_bottom[fvg_bar]
            ]
            if not inverted:
                remaining_short_events.append(event)
                continue

            # Use the most recent eligible pre-sweep FVG when several invert on
            # the same bar. This keeps the setup anchored to the freshest gap.
            fvg_bar = max(inverted)
            resolved_entry_mode = _resolve_lsi_entry_mode(
                entry_mode=entry_mode,
                bar_minutes=bar_minutes,
                sweep_to_inversion_bars=i - int(event["sweep_bar"]),
                close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
            )
            level_entry_price = (
                float(long_fvg_bottom[fvg_bar]) if gap_entry_edge == "near" else float(long_fvg_top[fvg_bar])
            )
            entry_price = (
                level_entry_price if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
            )
            signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
            orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
            absolute_stop = float(np.max(high[event["sweep_bar"]: i + 1]))
            fvg_stop = float(long_fvg_top[fvg_bar])
            atr_points, orb_points = _resolve_lsi_session_stop_points(
                session=session,
                daily_atr=float(daily_atr[i]),
                orb_range=orb_range,
            )
            structural_stop = _resolve_lsi_stop_price(
                direction=-1,
                entry_price=entry_price,
                absolute_stop_price=absolute_stop,
                fvg_stop_price=fvg_stop,
                gap_size=float(fvg["long_gap_size"][fvg_bar]),
                atr_points=atr_points,
                orb_points=orb_points,
                stop_mode=stop_mode,
            )
            risk = structural_stop - entry_price
            structural_risk = absolute_stop - entry_price
            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=-1,
                entry_price=entry_price,
                actual_risk_pts=risk,
                structural_risk_pts=structural_risk,
                rr=rr,
                tp1_ratio=tp1_ratio,
                left_end_bar=min(fvg_bar, int(event["sweep_bar"])) - 1,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=min_tick,
            )
            tp1_est = entry_price - tp1_dist
            lrlr_match = _detect_candidate_lrlr(
                high=high,
                low=low,
                bar_minutes=bar_minutes,
                left_end_bar=min(fvg_bar, int(event["sweep_bar"])) - 1,
                direction=-1,
                entry_price=entry_price,
                tp1_price=tp1_est,
                daily_atr=float(daily_atr[i]),
                settings=lrlr_settings,
                pivot_arrays=lrlr_pivot_arrays,
            )
            if _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                remaining_short_events.append(event)
                continue
            armed_high_instances.add(event["level_key"])
            candidates.append(
                _SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=signal_bar,
                    entry_price=entry_price,
                    gap_size=float(fvg["long_gap_size"][fvg_bar]),
                    daily_atr=float(daily_atr[i]),
                    orb_range=orb_range,
                    structural_stop_price=structural_stop,
                    lsi_absolute_stop_price=absolute_stop,
                    lsi_swept_level=event["level_price"],
                    lsi_fvg_top=float(long_fvg_top[fvg_bar]),
                    lsi_fvg_bottom=float(long_fvg_bottom[fvg_bar]),
                    lsi_fvg_bar=fvg_bar,
                    lsi_sweep_bar=int(event["sweep_bar"]),
                    lsi_confirmation_type="inversion",
                    reference_level_name=str(event["level_name"]),
                    reference_level_price=float(event["level_price"]),
                    lsi_lrlr_present=lrlr_match.present,
                    lsi_lrlr_level_count=lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                )
            )
        active_short_events = remaining_short_events

        remaining_long_events: list[dict] = []
        for event in active_long_events:
            if event["level_key"] in armed_low_instances:
                continue
            if event["sd"] != sd:
                continue
            if i <= event["sweep_bar"]:
                remaining_long_events.append(event)
                continue
            if i > event["expiry_bar"] or not in_entry[i]:
                continue

            inverted = [
                fvg_bar for fvg_bar in event["fvg_bars"]
                if close[i] > short_fvg_top[fvg_bar]
            ]
            if not inverted:
                remaining_long_events.append(event)
                continue

            fvg_bar = max(inverted)
            resolved_entry_mode = _resolve_lsi_entry_mode(
                entry_mode=entry_mode,
                bar_minutes=bar_minutes,
                sweep_to_inversion_bars=i - int(event["sweep_bar"]),
                close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
            )
            level_entry_price = (
                float(short_fvg_top[fvg_bar]) if gap_entry_edge == "near" else float(short_fvg_bottom[fvg_bar])
            )
            entry_price = (
                level_entry_price if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else float(close[i])
            )
            signal_bar = i if _is_lsi_level_limit_entry_mode(resolved_entry_mode) else i - 1
            orb_range = _resolve_lsi_orb_range(float(orb_high[i]), float(orb_low[i]))
            absolute_stop = float(np.min(low[event["sweep_bar"]: i + 1]))
            fvg_stop = float(short_fvg_bottom[fvg_bar])
            atr_points, orb_points = _resolve_lsi_session_stop_points(
                session=session,
                daily_atr=float(daily_atr[i]),
                orb_range=orb_range,
            )
            structural_stop = _resolve_lsi_stop_price(
                direction=1,
                entry_price=entry_price,
                absolute_stop_price=absolute_stop,
                fvg_stop_price=fvg_stop,
                gap_size=float(fvg["short_gap_size"][fvg_bar]),
                atr_points=atr_points,
                orb_points=orb_points,
                stop_mode=stop_mode,
            )
            risk = entry_price - structural_stop
            structural_risk = entry_price - absolute_stop
            tp1_dist, _ = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=1,
                entry_price=entry_price,
                actual_risk_pts=risk,
                structural_risk_pts=structural_risk,
                rr=rr,
                tp1_ratio=tp1_ratio,
                left_end_bar=min(fvg_bar, int(event["sweep_bar"])) - 1,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=min_tick,
            )
            tp1_est = entry_price + tp1_dist
            lrlr_match = _detect_candidate_lrlr(
                high=high,
                low=low,
                bar_minutes=bar_minutes,
                left_end_bar=min(fvg_bar, int(event["sweep_bar"])) - 1,
                direction=1,
                entry_price=entry_price,
                tp1_price=tp1_est,
                daily_atr=float(daily_atr[i]),
                settings=lrlr_settings,
                pivot_arrays=lrlr_pivot_arrays,
            )
            if _lrlr_gate_blocks(lrlr_match, lrlr_settings):
                remaining_long_events.append(event)
                continue
            armed_low_instances.add(event["level_key"])
            candidates.append(
                _SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=signal_bar,
                    entry_price=entry_price,
                    gap_size=float(fvg["short_gap_size"][fvg_bar]),
                    daily_atr=float(daily_atr[i]),
                    orb_range=orb_range,
                    structural_stop_price=structural_stop,
                    lsi_absolute_stop_price=absolute_stop,
                    lsi_swept_level=event["level_price"],
                    lsi_fvg_top=float(short_fvg_top[fvg_bar]),
                    lsi_fvg_bottom=float(short_fvg_bottom[fvg_bar]),
                    lsi_fvg_bar=fvg_bar,
                    lsi_sweep_bar=int(event["sweep_bar"]),
                    lsi_confirmation_type="inversion",
                    reference_level_name=str(event["level_name"]),
                    reference_level_price=float(event["level_price"]),
                    lsi_lrlr_present=lrlr_match.present,
                    lsi_lrlr_level_count=lrlr_match.level_count,
                    lsi_lrlr_nearest_level_price=lrlr_match.nearest_level_price,
                    lsi_lrlr_farthest_level_price=lrlr_match.farthest_level_price,
                    lsi_lrlr_span_bars=lrlr_match.span_bars,
                    lsi_lrlr_price_span_atr=lrlr_match.price_span_atr,
                    lsi_lrlr_slope_atr_per_bar=lrlr_match.slope_atr_per_bar,
                    lsi_lrlr_fit_error_atr=lrlr_match.fit_error_atr,
                    lsi_lrlr_tp1_path_present=lrlr_match.tp1_path_present,
                    lsi_lrlr_nearest_tp1_gap_atr=lrlr_match.nearest_tp1_gap_atr,
                )
            )
        active_long_events = remaining_long_events

    return candidates


def _find_bar_index(timestamps: pd.DatetimeIndex, in_mask: np.ndarray, date, find_last: bool = False) -> int:
    """Find the first (or last) bar index matching a date and mask condition."""
    date_match = timestamps.date == date
    combined = date_match & in_mask
    indices = np.where(combined)[0]
    if len(indices) == 0:
        return -1
    return int(indices[-1]) if find_last else int(indices[0])


def _precompute_day_boundaries(
    timestamps: pd.DatetimeIndex,
    masks: dict[str, np.ndarray],
    half_day_set: set[str],
    date_strs: np.ndarray,
    session_day_id: np.ndarray,
) -> dict:
    """Precompute per-session-day entry/flat bar boundaries in a single pass.

    Uses session_day_id (from compute_session_days) so cross-midnight sessions
    are grouped correctly.

    Returns dict mapping session_day_id (int) -> {
        'entry_last': int,  last bar index in entry window
        'flat_first': int,  first bar index in flat window
        'date': datetime.date,  calendar date of first bar in this session day
    }
    """
    in_entry = masks["in_entry"]
    in_flat = masks["in_flat"]
    dates = timestamps.date
    n = len(timestamps)
    hours = timestamps.hour.values
    minutes = timestamps.minute.values

    result: dict = {}
    current_sd = -1
    entry_last = -1
    flat_first = -1
    is_half = False
    sd_date = None

    for i in range(n):
        sd = session_day_id[i]
        if sd != current_sd:
            # Save previous session day
            if current_sd >= 0:
                result[current_sd] = {"entry_last": entry_last, "flat_first": flat_first, "date": sd_date}
            current_sd = sd
            entry_last = -1
            flat_first = -1
            sd_date = dates[i]
            is_half = date_strs[i] in half_day_set if half_day_set else False

        if in_entry[i]:
            entry_last = i

        if flat_first == -1:
            if is_half:
                # Half-day: flat at 12:50
                if (hours[i] == 12 and minutes[i] >= 50) or hours[i] > 12:
                    flat_first = i
            else:
                if in_flat[i]:
                    flat_first = i

    # Save last session day
    if current_sd >= 0:
        result[current_sd] = {"entry_last": entry_last, "flat_first": flat_first, "date": sd_date}

    return result


# ---------------------------------------------------------------------------
# Map pre-builder (call once before a sweep, pass result as _maps=)
# ---------------------------------------------------------------------------

def build_maps(
    df: pd.DataFrame,
    df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
) -> dict:
    """Pre-build all bar maps and extract sub-minute OHLCV arrays.

    Call this once before a parameter sweep and pass the result as ``_maps=``
    to :func:`run_backtest`. This avoids rebuilding maps on every call, which
    for GC (5m+1m+30s+1s) saves ~4 seconds per backtest iteration.

    Parameters
    ----------
    df : pd.DataFrame
        5-minute OHLCV DataFrame.
    df_1m : pd.DataFrame, optional
        1-minute OHLCV DataFrame.
    df_30s : pd.DataFrame, optional
        30-second OHLCV DataFrame.
    df_1s : pd.DataFrame, optional
        1-second OHLCV DataFrame.

    Returns
    -------
    dict
        Pre-built numpy arrays for maps and OHLCV data, ready to pass to
        ``run_backtest(_maps=...)``.
    """
    from ..data.bar_mapping import (
        build_5m_to_1m_map,
        build_1m_to_30s_map,
        build_30s_to_1s_map,
        build_1m_to_1s_map,
    )

    has_1m  = df_1m  is not None
    has_30s = df_30s is not None
    has_1s  = df_1s  is not None

    empty2   = np.empty((0, 2), dtype=np.int64)
    empty1   = np.empty(0, dtype=np.float64)

    maps: dict = {
        "has_1m":  has_1m,
        "has_30s": has_30s,
        "has_1s":  has_1s,
        "map_5m_1m":  empty2,
        "map_1m_30s": empty2,
        "map_30s_1s": empty2,
        "map_1m_1s":  empty2,
        "high_1m":  empty1, "low_1m":  empty1, "close_1m":  empty1,
        "high_30s": empty1, "low_30s": empty1, "close_30s": empty1,
        "high_1s":  empty1, "low_1s":  empty1, "close_1s":  empty1,
        "timestamps_1m": np.empty(0, dtype="datetime64[ns]"),
    }

    if has_1m:
        maps["map_5m_1m"]  = build_5m_to_1m_map(df, df_1m)
        maps["high_1m"]    = np.ascontiguousarray(df_1m["high"].values, dtype=np.float64)
        maps["low_1m"]     = np.ascontiguousarray(df_1m["low"].values, dtype=np.float64)
        maps["close_1m"]   = np.ascontiguousarray(df_1m["close"].values, dtype=np.float64)
        maps["timestamps_1m"] = df_1m.index.values.astype("datetime64[ns]")

    if has_30s:
        maps["map_1m_30s"] = build_1m_to_30s_map(df_1m, df_30s)
        maps["high_30s"]   = np.ascontiguousarray(df_30s["high"].values, dtype=np.float64)
        maps["low_30s"]    = np.ascontiguousarray(df_30s["low"].values, dtype=np.float64)
        maps["close_30s"]  = np.ascontiguousarray(df_30s["close"].values, dtype=np.float64)

    if has_1s:
        maps["high_1s"]  = np.ascontiguousarray(df_1s["high"].values, dtype=np.float64)
        maps["low_1s"]   = np.ascontiguousarray(df_1s["low"].values, dtype=np.float64)
        maps["close_1s"] = np.ascontiguousarray(df_1s["close"].values, dtype=np.float64)
        if has_30s:
            maps["map_30s_1s"] = build_30s_to_1s_map(df_30s, df_1s)
        elif has_1m:
            maps["map_1m_1s"]  = build_1m_to_1s_map(df_1m, df_1s)

    return maps


# ---------------------------------------------------------------------------
# Signal pre-computation cache
# ---------------------------------------------------------------------------

def build_signal_cache(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
    signal_df_1m: pd.DataFrame | None = None,
) -> dict:
    """Pre-compute all signal arrays needed by a set of configs.

    Call once before a parameter sweep, then pass the result as
    ``_signal_cache=cache`` to :func:`run_backtest` or (via parallel.py)
    to :func:`run_sweep`.

    Groups configs by their signal-determining keys and computes each unique
    combination exactly once:

    - ``cache["atr"][atr_length]``       → daily ATR array
    - ``cache["session"][session_key]``   → masks, day IDs, ORB levels, date strings
    - ``cache["fvg"][fvg_key]``           → FVG signal arrays

    For a 1000-config sweep where only rr/tp1_ratio vary (session params and
    atr_length are constant), each signal is computed exactly once instead of
    1000 times — saving ~11 minutes for full-history GC data.

    ATR and session computations run in parallel (batch 1), then FVG
    computations run in parallel (batch 2) since FVG depends on session + ATR.
    NumPy/Numba operations release the GIL, so threads achieve true parallelism.
    """
    cache: dict = {
        "atr": {},
        "session": {},
        "fvg": {},
        "fvg_no_orb": {},
        "htf_levels": {},
        "eqhl_levels": {},
    }
    timestamps = df.index

    # --- Date strings: config-independent, computed exactly once ---
    date_strs = compute_date_strings(timestamps)

    needs_reference_levels = any(
        c.strategy == "reference_lsi" or (c.strategy == "htf_lsi" and bool(c.htf_lsi_reference_levels))
        for c in configs
    )
    needs_data_reference_levels = any(
        (
            c.strategy == "reference_lsi"
            and _reference_levels_need_data(c.ref_lsi_reference_levels)
        )
        or (
            c.strategy == "htf_lsi"
            and _reference_levels_need_data(c.htf_lsi_reference_levels)
        )
        for c in configs
    )
    needs_htf_levels = any(c.strategy == "htf_lsi" and c.htf_lsi_include_htf_levels for c in configs)
    needs_eqhl_levels = any(c.strategy == "htf_lsi" and c.htf_lsi_include_eqhl_levels for c in configs)
    if needs_reference_levels:
        cache["reference_levels"], cache["reference_level_instance_ids"] = _build_static_reference_level_cache(
            df,
            timestamps,
        )
    if (needs_htf_levels or needs_eqhl_levels or needs_data_reference_levels) and signal_df_1m is None:
        raise ValueError(
            "build_signal_cache requires signal_df_1m when configs enable HTF-LSI pivot sweep levels, equal high/low sweep levels, or data_high/data_low."
        )
    if needs_data_reference_levels:
        cache["data_reference_levels"] = {}
        data_keys = {
            (
                _session_key(session),
                session,
                c.atr_length,
                float(c.data_sweep_min_daily_atr_pct),
                bool(c.data_sweep_require_session_extreme),
                tuple(
                    str(event_type).strip().upper()
                    for event_type in c.data_sweep_event_types
                    if str(event_type).strip()
                ),
                int(c.data_sweep_release_window_minutes),
            )
            for c in configs
            for session in c.sessions
            if (
                (c.strategy == "reference_lsi" and _reference_levels_need_data(c.ref_lsi_reference_levels))
                or (c.strategy == "htf_lsi" and _reference_levels_need_data(c.htf_lsi_reference_levels))
            )
        }
        for session_key, session, atr_length, min_pct, require_session_extreme, event_types, release_window_minutes in data_keys:
            data_levels, data_ids = compute_data_sweep_levels(
                df,
                signal_df_1m,
                atr_length=atr_length,
                min_daily_atr_pct=min_pct,
                session=session,
                require_session_extreme=require_session_extreme,
                event_types=event_types,
                release_window_minutes=release_window_minutes,
            )
            cache["data_reference_levels"][
                (
                    session_key,
                    int(atr_length),
                    float(min_pct),
                    bool(require_session_extreme),
                    tuple(event_types),
                    int(release_window_minutes),
                )
            ] = {
                "levels": data_levels,
                "instance_ids": data_ids,
            }

    # Collect unique keys
    atr_lengths = {c.atr_length for c in configs}
    unique_sessions: dict[tuple, SessionConfig] = {}
    for config in configs:
        for session in config.sessions:
            skey = _session_key(session)
            if skey not in unique_sessions:
                unique_sessions[skey] = session

    # --- Batch 1: ATR + session computations in parallel ---
    # NumPy/Numba release the GIL, so threads achieve real parallelism.
    def _compute_atr(atr_length):
        return atr_length, compute_daily_atr(df, atr_length)

    def _compute_session(skey, session):
        masks = compute_session_masks(timestamps, session)
        new_session_day, session_day_id = compute_session_days(timestamps, session)
        orb_high, orb_low, orb_ready = compute_orb_levels(
            df, masks["in_orb"], masks["in_rth"], new_session_day
        )
        vwap = compute_session_vwap(
            df["high"].values,
            df["low"].values,
            df["close"].values,
            df["volume"].values,
            session_day_id,
        )
        # Pre-compute day boundaries with empty half_day_set (default case).
        # This avoids re-running the Python loop over all bars on every config
        # in a sweep when half_days is empty (the common case).
        day_bounds_default = _precompute_day_boundaries(
            timestamps, masks, set(), date_strs, session_day_id
        )
        return skey, {
            "masks": masks,
            "new_session_day": new_session_day,
            "session_day_id": session_day_id,
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_ready": orb_ready,
            "vwap": vwap,
            "date_strs": date_strs,
            "day_bounds_default": day_bounds_default,
        }

    n_batch1 = len(atr_lengths) + len(unique_sessions)
    max_workers = min(n_batch1, (os.cpu_count() or 1))

    if max_workers > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            atr_futures = [executor.submit(_compute_atr, al) for al in atr_lengths]
            session_futures = [
                executor.submit(_compute_session, skey, session)
                for skey, session in unique_sessions.items()
            ]
            for f in atr_futures:
                atr_length, atr_arr = f.result()
                cache["atr"][atr_length] = atr_arr
            for f in session_futures:
                skey, session_data = f.result()
                cache["session"][skey] = session_data
    else:
        for atr_length in atr_lengths:
            cache["atr"][atr_length] = compute_daily_atr(df, atr_length)
        for skey, session in unique_sessions.items():
            _, session_data = _compute_session(skey, session)
            cache["session"][skey] = session_data

    # --- Batch 2: FVG signals in parallel (depends on ATR + session from batch 1) ---
    unique_fvg_tasks: list[tuple] = []
    seen_fvg: set = set()
    unique_no_orb_fvg_tasks: list[tuple] = []
    seen_no_orb_fvg: set = set()
    for config in configs:
        for session in config.sessions:
            fkey = _fvg_key(session, config)
            if fkey not in seen_fvg:
                seen_fvg.add(fkey)
                unique_fvg_tasks.append((fkey, session, config))
            if config.strategy in {"lsi", "htf_lsi", "reference_lsi"}:
                no_orb_key = _fvg_no_orb_key(session, config)
                if no_orb_key not in seen_no_orb_fvg:
                    seen_no_orb_fvg.add(no_orb_key)
                    unique_no_orb_fvg_tasks.append((no_orb_key, session, config))
            if config.strategy == "htf_lsi" and config.htf_lsi_include_htf_levels:
                htf_key = _htf_key(session, config)
                if htf_key not in cache["htf_levels"]:
                    cache["htf_levels"][htf_key] = None
            if config.strategy == "htf_lsi" and config.htf_lsi_include_eqhl_levels:
                eqhl_key = _eqhl_key(session, config)
                if eqhl_key not in cache["eqhl_levels"]:
                    cache["eqhl_levels"][eqhl_key] = None

    def _compute_fvg(fkey, session, config):
        skey = _session_key(session)
        sc = cache["session"][skey]
        daily_atr = cache["atr"][config.atr_length]
        fvg = detect_fvg(
            df["high"].values,
            df["low"].values,
            daily_atr,
            sc["orb_high"],
            sc["orb_low"],
            session.min_gap_atr_pct,
            close=df["close"].values if config.impulse_close_filter else None,
            impulse_close_filter=config.impulse_close_filter,
            min_gap_orb_pct=getattr(session, "min_gap_orb_pct", 0.0),
        )
        return fkey, fvg

    def _compute_no_orb_fvg(no_orb_key, session, config):
        from ..signals.fvg import detect_fvg_no_orb

        daily_atr = cache["atr"][config.atr_length]
        fvg = detect_fvg_no_orb(
            df["high"].values,
            df["low"].values,
            daily_atr,
            session.min_gap_atr_pct,
        )
        return no_orb_key, fvg

    unique_htf_tasks: list[tuple] = []
    if needs_htf_levels:
        seen_htf: set[tuple] = set()
        for config in configs:
            if config.strategy != "htf_lsi" or not config.htf_lsi_include_htf_levels:
                continue
            for session in config.sessions:
                htf_key = _htf_key(session, config)
                if htf_key in seen_htf:
                    continue
                seen_htf.add(htf_key)
                unique_htf_tasks.append((htf_key, config))

    def _compute_htf_levels(htf_key, config):
        levels = compute_htf_unswept_levels(
            df,
            signal_df_1m,
            tf_minutes=config.htf_level_tf_minutes,
            n_left=config.htf_n_left,
        )
        return htf_key, levels

    unique_eqhl_tasks: list[tuple] = []
    if needs_eqhl_levels:
        seen_eqhl: set[tuple] = set()
        for config in configs:
            if config.strategy != "htf_lsi" or not config.htf_lsi_include_eqhl_levels:
                continue
            for session in config.sessions:
                eqhl_key = _eqhl_key(session, config)
                if eqhl_key in seen_eqhl:
                    continue
                seen_eqhl.add(eqhl_key)
                unique_eqhl_tasks.append((eqhl_key, config))

    def _compute_eqhl_levels(eqhl_key, config):
        levels = compute_equal_htf_levels(
            df,
            signal_df_1m,
            tf_minutes=config.eqhl_level_tf_minutes,
            n_left=config.eqhl_n_left,
            tolerance_points=float(config.eqhl_tolerance_ticks) * float(config.min_tick),
            min_touches=config.eqhl_min_touches,
            lookback_bars=config.eqhl_lookback_bars,
        )
        levels["tf_minutes"] = int(config.eqhl_level_tf_minutes)
        return eqhl_key, levels

    n_fvg = len(unique_fvg_tasks)
    max_fvg_workers = min(n_fvg, (os.cpu_count() or 1))

    if max_fvg_workers > 1:
        with ThreadPoolExecutor(max_workers=max_fvg_workers) as executor:
            fvg_futures = [
                executor.submit(_compute_fvg, fkey, session, config)
                for fkey, session, config in unique_fvg_tasks
            ]
            for f in fvg_futures:
                fkey, fvg = f.result()
                cache["fvg"][fkey] = fvg
    else:
        for fkey, session, config in unique_fvg_tasks:
            _, fvg = _compute_fvg(fkey, session, config)
            cache["fvg"][fkey] = fvg

    n_no_orb_fvg = len(unique_no_orb_fvg_tasks)
    max_no_orb_workers = min(n_no_orb_fvg, (os.cpu_count() or 1))

    if max_no_orb_workers > 1:
        with ThreadPoolExecutor(max_workers=max_no_orb_workers) as executor:
            futures = [
                executor.submit(_compute_no_orb_fvg, no_orb_key, session, config)
                for no_orb_key, session, config in unique_no_orb_fvg_tasks
            ]
            for f in futures:
                no_orb_key, fvg = f.result()
                cache["fvg_no_orb"][no_orb_key] = fvg
    else:
        for no_orb_key, session, config in unique_no_orb_fvg_tasks:
            _, fvg = _compute_no_orb_fvg(no_orb_key, session, config)
            cache["fvg_no_orb"][no_orb_key] = fvg

    n_htf = len(unique_htf_tasks)
    max_htf_workers = min(n_htf, (os.cpu_count() or 1))
    if max_htf_workers > 1:
        with ThreadPoolExecutor(max_workers=max_htf_workers) as executor:
            futures = [
                executor.submit(_compute_htf_levels, htf_key, config)
                for htf_key, config in unique_htf_tasks
            ]
            for f in futures:
                htf_key, levels = f.result()
                cache["htf_levels"][htf_key] = levels
    else:
        for htf_key, config in unique_htf_tasks:
            _, levels = _compute_htf_levels(htf_key, config)
            cache["htf_levels"][htf_key] = levels

    n_eqhl = len(unique_eqhl_tasks)
    max_eqhl_workers = min(n_eqhl, (os.cpu_count() or 1))
    if max_eqhl_workers > 1:
        with ThreadPoolExecutor(max_workers=max_eqhl_workers) as executor:
            futures = [
                executor.submit(_compute_eqhl_levels, eqhl_key, config)
                for eqhl_key, config in unique_eqhl_tasks
            ]
            for f in futures:
                eqhl_key, levels = f.result()
                cache["eqhl_levels"][eqhl_key] = levels
    else:
        for eqhl_key, config in unique_eqhl_tasks:
            _, levels = _compute_eqhl_levels(eqhl_key, config)
            cache["eqhl_levels"][eqhl_key] = levels

    return cache


# ---------------------------------------------------------------------------
# Timestamp resolution helper
# ---------------------------------------------------------------------------

def _resolve_time(
    timestamps_5m: pd.DatetimeIndex,
    bar_5m: int,
    timestamps_1m: np.ndarray,
    bar_1m_f: float,
) -> str:
    """Pick the best-resolution timestamp for a trade event."""
    bar_1m = int(bar_1m_f) if bar_1m_f >= 0 else -1
    if bar_1m >= 0 and bar_1m < len(timestamps_1m):
        return str(pd.Timestamp(timestamps_1m[bar_1m]).isoformat())
    if bar_5m >= 0:
        return timestamps_5m[bar_5m].isoformat()
    return ""


def _entry_context_passes(
    gate_tokens: tuple[str, ...],
    min_atr: float,
    max_atr: float,
    direction: int,
    entry_price: float,
    fill_bar: int,
    daily_atr: np.ndarray,
    indicator_values: dict[str, np.ndarray],
) -> bool:
    """Return True when the configured fill-time context overlay is satisfied."""
    if not gate_tokens:
        return True
    if fill_bar < 0 or fill_bar >= len(daily_atr):
        return False

    atr = daily_atr[fill_bar]
    if not np.isfinite(atr) or atr <= 0:
        return False

    def _in_band(token: str) -> bool:
        values = indicator_values.get(token)
        if values is None or fill_bar >= len(values):
            return False
        level = values[fill_bar]
        if not np.isfinite(level):
            return False
        signed_dist = float(direction) * (entry_price - float(level)) / float(atr)
        return min_atr <= signed_dist < max_atr

    return all(_in_band(token) for token in gate_tokens)


# ---------------------------------------------------------------------------
# Main simulation orchestrator
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    config: StrategyConfig,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    signal_df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
    _maps: dict | None = None,
    _signal_cache: dict | None = None,
) -> list[TradeResult]:
    """Run the full backtest pipeline.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data before start_date).
        config: Strategy configuration.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
            Data before this date is used for indicator warmup (ATR, etc.)
            but trades are excluded from results.
        end_date: Exclude trades on or after this date (YYYY-MM-DD).
            Used by walk-forward IS folds to skip simulating OOS-period candidates.
        df_1m: Optional 1-minute OHLCV DataFrame.
            Enables hierarchical drill-down mode: simulation runs at 5m, drilling
            to 1m only on ambiguous bars (where a single candle simultaneously
            touches two price objectives).
        signal_df_1m: Optional raw 1-minute OHLCV DataFrame used to build
            HTF structure for ``htf_lsi``. Kept separate from ``df_1m`` so HTF
            signal construction does not depend on whether bar magnifier is used.
        df_30s: Optional 30-second OHLCV DataFrame.
            When provided alongside df_1m, adds a 30s tier between 1m and 1s:
            ambiguous 1m bars drill to 30s before going to 1s.
            Currently only available for GC (created by scripts/convert_to_parquet.py).
        df_1s: Optional 1-second OHLCV DataFrame.
            Adds the finest resolution tier: ambiguous 30s bars drill to 1s
            (when df_30s present) or ambiguous 1m bars drill directly to 1s
            (when df_30s is not present).
        _maps: Optional pre-built maps dict from :func:`build_maps`. When
            provided, skips all map construction — critical for parameter sweeps
            where the same data is reused across many configs. Build once with
            ``maps = build_maps(df, df_1m, df_30s, df_1s)`` and pass as
            ``_maps=maps``.
        _signal_cache: Optional pre-computed signal cache from
            :func:`build_signal_cache`. When provided, skips all signal
            generation (ATR, session masks, ORB levels, FVG detection) for
            configs that share the same signal-determining parameters. Build
            once with ``cache = build_signal_cache(df, configs)`` and pass as
            ``_signal_cache=cache``.

    Returns:
        List of TradeResult for each setup candidate (including no-fills).
    """
    high = np.ascontiguousarray(df["high"].values, dtype=np.float64)
    low = np.ascontiguousarray(df["low"].values, dtype=np.float64)
    close = np.ascontiguousarray(df["close"].values, dtype=np.float64)
    timestamps = df.index
    n = len(df)

    # Bar magnifier setup
    #
    # Hierarchical mode (default when df_1m provided):
    #   - Fill detected at 5m
    #   - Exit runs at 5m; drills to 1m only on ambiguous bars (sl+tp same candle)
    #   - If df_30s also provided: drills to 30s on ambiguous 1m bars
    #   - If df_1s also provided: drills to 1s on ambiguous 30s bars
    #     (or directly to 1s from 1m when df_30s is not available)
    #
    # Legacy full-1m mode (backward compat, use_bar_magnifier=True, no sub-minute data):
    #   - Entire fill+exit simulation on 1m bars
    #
    use_magnifier = False  # superseded by hierarchical; kept only as explicit fallback

    if _maps is not None:
        # Fast path: use pre-built maps from build_maps() — skips all construction.
        # Critical for parameter sweeps: saves ~4s/iter for GC with all tiers.
        use_hierarchical = _maps["has_1m"]
        has_30s          = _maps["has_30s"]
        has_1s           = _maps["has_1s"]
        map_5m_1m_arr    = _maps["map_5m_1m"]
        map_1m_30s_arr   = _maps["map_1m_30s"]
        map_30s_1s_arr   = _maps["map_30s_1s"]
        map_1m_1s_arr    = _maps["map_1m_1s"]
        high_1m          = _maps["high_1m"]
        low_1m           = _maps["low_1m"]
        close_1m         = _maps["close_1m"]
        high_30s         = _maps["high_30s"]
        low_30s          = _maps["low_30s"]
        close_30s        = _maps["close_30s"]
        high_1s          = _maps["high_1s"]
        low_1s           = _maps["low_1s"]
        close_1s         = _maps["close_1s"]
        timestamps_1m    = _maps["timestamps_1m"]
        bar_map          = map_5m_1m_arr
        map_1m_to_5m     = None  # only used in legacy magnifier path

    else:
        # Slow path: build maps from DataFrames (correct for one-off backtests).
        has_30s = df_30s is not None
        has_1s  = df_1s  is not None
        use_hierarchical = df_1m is not None

        bar_map = None
        high_1m = low_1m = close_1m = None
        map_1m_to_5m = None
        map_5m_1m_arr  = None
        map_1m_30s_arr = np.empty((0, 2), dtype=np.int64)
        map_30s_1s_arr = np.empty((0, 2), dtype=np.int64)
        map_1m_1s_arr  = np.empty((0, 2), dtype=np.int64)
        high_30s  = np.empty(0, dtype=np.float64)
        low_30s   = np.empty(0, dtype=np.float64)
        close_30s = np.empty(0, dtype=np.float64)
        high_1s   = np.empty(0, dtype=np.float64)
        low_1s    = np.empty(0, dtype=np.float64)
        close_1s  = np.empty(0, dtype=np.float64)
        timestamps_1m = np.empty(0, dtype="datetime64[ns]")

        if use_hierarchical:
            from ..data.bar_mapping import (
                build_5m_to_1m_map,
                map_1m_to_5m as _map_1m_to_5m,
            )
            bar_map = build_5m_to_1m_map(df, df_1m)
            map_5m_1m_arr = bar_map
            high_1m   = np.ascontiguousarray(df_1m["high"].values, dtype=np.float64)
            low_1m    = np.ascontiguousarray(df_1m["low"].values, dtype=np.float64)
            close_1m  = np.ascontiguousarray(df_1m["close"].values, dtype=np.float64)
            timestamps_1m = df_1m.index.values.astype("datetime64[ns]")
            map_1m_to_5m = _map_1m_to_5m

        if has_30s:
            from ..data.bar_mapping import build_1m_to_30s_map
            map_1m_30s_arr = build_1m_to_30s_map(df_1m, df_30s)
            high_30s  = np.ascontiguousarray(df_30s["high"].values, dtype=np.float64)
            low_30s   = np.ascontiguousarray(df_30s["low"].values, dtype=np.float64)
            close_30s = np.ascontiguousarray(df_30s["close"].values, dtype=np.float64)

        if has_1s:
            high_1s  = np.ascontiguousarray(df_1s["high"].values, dtype=np.float64)
            low_1s   = np.ascontiguousarray(df_1s["low"].values, dtype=np.float64)
            close_1s = np.ascontiguousarray(df_1s["close"].values, dtype=np.float64)
            if has_30s:
                from ..data.bar_mapping import build_30s_to_1s_map
                map_30s_1s_arr = build_30s_to_1s_map(df_30s, df_1s)
            else:
                from ..data.bar_mapping import build_1m_to_1s_map
                map_1m_1s_arr = build_1m_to_1s_map(df_1m, df_1s)

    all_results: list[TradeResult] = []
    context_gate = config.entry_context_gate
    context_gate_tokens = tuple()
    context_daily_atr = None
    context_indicator_values: dict[str, np.ndarray] = {}
    if context_gate:
        context_gate_tokens = tuple(
            token for token in context_gate[: -len("_aligned")].split("_") if token
        )
        if _signal_cache is not None:
            context_daily_atr = _signal_cache["atr"][config.atr_length]
        else:
            context_daily_atr = compute_daily_atr(df, config.atr_length)
        close_series = pd.Series(close, index=timestamps)
        for token in context_gate_tokens:
            if token == "vwap":
                continue
            if token.startswith("sma"):
                period = int(token[3:])
                context_indicator_values[token] = np.ascontiguousarray(
                    close_series.rolling(period, min_periods=period).mean().shift(1).to_numpy(dtype=np.float64)
                )
            elif token.startswith("ema"):
                period = int(token[3:])
                context_indicator_values[token] = np.ascontiguousarray(
                    close_series.ewm(span=period, adjust=False, min_periods=period).mean().shift(1).to_numpy(dtype=np.float64)
                )

    runner_trail_mode = _runner_trail_mode_code(config.runner_trail_mode)

    for session in config.sessions:
        # Extract candidates (vectorized); reuses _signal_cache when provided
        candidates = _extract_setup_candidates(
            df,
            session,
            config,
            signal_df_1m=signal_df_1m,
            _signal_cache=_signal_cache,
        )

        # Pre-simulation date filter: skip candidates outside the active window.
        # This avoids running expensive Numba simulation on dates that will be
        # filtered out post-hoc. Critical for walk-forward IS folds where the full
        # df is passed but only a subset of dates is needed.
        if start_date or end_date:
            candidates = [
                c for c in candidates
                if (start_date is None or c.date_str >= start_date)
                and (end_date is None or c.date_str < end_date)
            ]

        # Session signals: reuse from cache (avoids double-compute vs _extract_setup_candidates)
        if _signal_cache is not None:
            skey = _session_key(session)
            sc = _signal_cache["session"][skey]
            masks = sc["masks"]
            session_day_id = sc["session_day_id"]
            date_strs = sc["date_strs"]
        else:
            # Compute session masks for entry/flat window boundaries
            masks = compute_session_masks(timestamps, session)
            # Session-aware day boundaries for precomputing bar lookups
            _, session_day_id = compute_session_days(timestamps, session)
            date_strs = compute_date_strings(timestamps)

        session_context_values = dict(context_indicator_values)
        if context_gate and "vwap" in context_gate_tokens:
            if _signal_cache is not None:
                session_vwap = sc["vwap"]
            else:
                session_vwap = compute_session_vwap(
                    high,
                    low,
                    close,
                    np.ascontiguousarray(df["volume"].fillna(0.0).values, dtype=np.float64),
                    session_day_id,
                )
            context_vwap_prev = np.empty_like(session_vwap)
            context_vwap_prev[:] = np.nan
            if len(context_vwap_prev) > 1:
                context_vwap_prev[1:] = session_vwap[:-1]
            session_context_values["vwap"] = context_vwap_prev

        # Pre-compute half-day flat mask for NY
        half_day_set = set(config.half_days) if session.name == "NY" else set()

        # Precompute per-session-day bar boundaries (single pass over all bars).
        # Use cached default (empty half_days) when available to avoid re-running
        # the Python loop over all bars on every config in a sweep.
        if _signal_cache is not None and not half_day_set:
            day_bounds = sc["day_bounds_default"]
        else:
            day_bounds = _precompute_day_boundaries(
                timestamps, masks, half_day_set, date_strs, session_day_id
            )

        pre_entry_cancel_requires_new_htf_lsi_sweep = (
            config.strategy == "htf_lsi"
            and bool(config.limit_cancel_on_pre_entry_target_touch)
            and config.limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep
        )
        pre_entry_new_high_sweep_5m = np.zeros(n, dtype=bool)
        pre_entry_new_low_sweep_5m = np.zeros(n, dtype=bool)
        pre_entry_new_high_sweep_1m = np.zeros(len(high_1m) if high_1m is not None else 0, dtype=bool)
        pre_entry_new_low_sweep_1m = np.zeros(len(low_1m) if low_1m is not None else 0, dtype=bool)
        if pre_entry_cancel_requires_new_htf_lsi_sweep:
            session_daily_atr = (
                _signal_cache["atr"][config.atr_length]
                if _signal_cache is not None
                else compute_daily_atr(df, config.atr_length)
            )
            pre_entry_new_high_sweep_5m, pre_entry_new_low_sweep_5m = _build_htf_lsi_pre_entry_cancel_sweep_flags(
                df=df,
                timestamps=timestamps,
                masks=masks,
                session_day_id=session_day_id,
                session=session,
                config=config,
                signal_df_1m=signal_df_1m,
                daily_atr=session_daily_atr,
                _signal_cache=_signal_cache,
            )
            if (use_hierarchical or use_magnifier) and bar_map is not None and len(pre_entry_new_high_sweep_1m) > 0:
                flagged_high = np.where(pre_entry_new_high_sweep_5m)[0]
                flagged_low = np.where(pre_entry_new_low_sweep_5m)[0]
                for idx in flagged_high:
                    start_1m = bar_map[idx, 0]
                    end_1m = bar_map[idx, 1]
                    pre_entry_new_high_sweep_1m[start_1m:end_1m] = True
                for idx in flagged_low:
                    start_1m = bar_map[idx, 0]
                    end_1m = bar_map[idx, 1]
                    pre_entry_new_low_sweep_1m[start_1m:end_1m] = True

        # Phase 1: Prepare all candidates (compute trade params + bar boundaries)
        prepared: list[_PreparedCandidate] = []
        target_pivot_arrays = None
        if (
            config.strategy in {"lsi", "htf_lsi", "reference_lsi"}
            and config.lsi_target_mode == "left_structure"
        ):
            target_pivot_arrays = _build_target_pivot_arrays(high, low, config.swing_n_bars)
        for cand in candidates:
            atr = cand.daily_atr
            if np.isnan(atr) or atr <= 0:
                continue

            entry = cand.entry_price
            direction = cand.direction

            # Compute stop, TP1, TP2, BE prices
            if cand.structural_stop_price > 0.0:
                # Structural stop: pre-computed stop price from candidate extraction
                stop_dist = abs(cand.entry_price - cand.structural_stop_price)
            elif session.stop_orb_pct > 0 and cand.orb_range > 0:
                stop_dist = (session.stop_orb_pct / 100.0) * cand.orb_range
            else:
                stop_dist = (session.stop_atr_pct / 100.0) * atr
            # Hard rule: stop must be at least 5% of daily ATR regardless of source
            min_atr_stop = 0.05 * atr
            stop_dist = max(stop_dist, min_atr_stop)
            # Apply minimum stop floor (points)
            if session.min_stop_points > 0:
                stop_dist = max(stop_dist, session.min_stop_points)
            if direction == 1:
                stop = entry - stop_dist
                risk_pts = entry - stop
            else:
                stop = entry + stop_dist
                risk_pts = stop - entry

            if risk_pts <= 0:
                continue

            if config.strategy == "reference_lsi":
                max_stop_points = config.risk_usd / config.point_value
                if risk_pts > max_stop_points:
                    continue

            # Position sizing
            qty_raw = config.risk_usd / (risk_pts * config.point_value)
            qty = math.floor(qty_raw / config.qty_step) * config.qty_step
            if qty < config.min_qty:
                continue

            is_single = qty <= config.min_qty
            if is_single:
                half_qty = qty
            else:
                half_qty = math.floor((qty / 2) / config.qty_step) * config.qty_step
                half_qty = max(half_qty, config.min_qty)

            structural_risk_pts = risk_pts
            if (
                config.strategy in {"lsi", "htf_lsi", "reference_lsi"}
                and cand.lsi_absolute_stop_price > 0.0
            ):
                structural_risk_pts = abs(entry - cand.lsi_absolute_stop_price)

            effective_rr = config.rr
            if (
                config.wide_stop_target_threshold_points > 0.0
                and config.wide_stop_target_rr > 0.0
                and risk_pts >= config.wide_stop_target_threshold_points
            ):
                effective_rr = min(config.rr, config.wide_stop_target_rr)

            target_mode = (
                config.lsi_target_mode
                if config.strategy in {"lsi", "htf_lsi", "reference_lsi"}
                else "risk"
            )
            left_end_bar = (
                min(cand.lsi_fvg_bar, cand.lsi_sweep_bar) - 1
                if config.strategy in {"lsi", "htf_lsi", "reference_lsi"}
                else -1
            )
            tp1_dist, tp2_dist = _resolve_lsi_candidate_target_distances(
                target_mode=target_mode,
                direction=direction,
                entry_price=entry,
                actual_risk_pts=risk_pts,
                structural_risk_pts=structural_risk_pts,
                rr=effective_rr,
                tp1_ratio=config.tp1_ratio,
                left_end_bar=left_end_bar,
                high=high,
                low=low,
                pivot_arrays=target_pivot_arrays,
                min_tick=config.min_tick,
            )
            # Apply minimum TP1 distance floor (points)
            if session.min_tp1_points > 0:
                tp1_dist = max(tp1_dist, session.min_tp1_points)
            if (
                config.wide_stop_full_exit_at_tp1
                and config.wide_stop_target_threshold_points > 0.0
                and risk_pts >= config.wide_stop_target_threshold_points
            ):
                tp2_dist = tp1_dist
            sim_is_single = is_single
            sim_half_qty = half_qty
            if config.exit_mode == "single_target":
                tp1_dist = tp2_dist
                sim_is_single = True
                sim_half_qty = qty
            if direction == 1:
                tp1 = entry + tp1_dist
                tp2 = entry + tp2_dist
                be = entry
            else:
                tp1 = entry - tp1_dist
                tp2 = entry - tp2_dist
                be = entry

            trail_atr_points = 0.0
            if runner_trail_mode == RUNNER_TRAIL_ATR:
                trail_atr_points = (config.runner_trail_atr_pct / 100.0) * atr

            # Look up precomputed boundaries using the signal bar's session day
            sd = session_day_id[cand.signal_bar]

            # Entry starts on bar AFTER the signal bar (matching bar_index > setupBar)
            entry_bar_start = cand.signal_bar + 1

            bounds = day_bounds.get(sd)
            if bounds is None:
                continue

            entry_bar_end = bounds["entry_last"]
            if entry_bar_end < 0 or entry_bar_end < entry_bar_start:
                continue

            flat_bar_start = bounds["flat_first"]
            if flat_bar_start < 0:
                # No flat window found (e.g., holiday early close).
                # Use the end of the entry window as the effective flat point
                # so we don't scan into the next overnight session.
                flat_bar_start = entry_bar_end

            # Last bar for scanning (end of RTH or end of data)
            last_bar = min(flat_bar_start + 20, n - 1)  # buffer past flat window

            # Translate 5m boundaries to 1m indices for bar magnifier (legacy) or
            # hierarchical mode (needed for winner determination fill scan)
            entry_start_1m = -1
            entry_end_1m = -1
            flat_start_1m_val = -1
            last_bar_1m_val = -1
            if use_magnifier or use_hierarchical:
                entry_start_1m = bar_map[entry_bar_start, 0]
                entry_end_1m = bar_map[min(entry_bar_end, len(bar_map) - 1), 1] - 1
                flat_start_1m_val = bar_map[min(flat_bar_start, len(bar_map) - 1), 0]
                last_bar_1m_val = bar_map[min(last_bar, len(bar_map) - 1), 1] - 1

            # Compute direction-aware safe sentinel for internal swing level.
            # LONG check: high[i] >= internal_swing_level → disabled sentinel = 1e38
            # SHORT check: low[i] <= internal_swing_level → disabled sentinel = -1e38
            # Non-LSI candidates default to 1e38; for SHORT we override to -1e38 so the
            # check never fires on non-LSI trades.
            raw_swing = cand.lsi_internal_swing_level
            if raw_swing >= 1e37 and direction == -1:
                # Default sentinel (1e38) on a SHORT would always fire (low[i] <= 1e38) — use SHORT safe sentinel
                raw_swing = -1e38
            prepared.append(_PreparedCandidate(
                cand=cand,
                sd=sd,
                direction=direction,
                entry_price=entry,
                stop_price=stop,
                tp1_price=tp1,
                tp2_price=tp2,
                be_price=be,
                risk_pts=risk_pts,
                qty=qty,
                half_qty=sim_half_qty,
                is_single=sim_is_single,
                gap_size=cand.gap_size,
                entry_bar_start=entry_bar_start,
                entry_bar_end=entry_bar_end,
                flat_bar_start=flat_bar_start,
                last_bar=last_bar,
                trail_atr_points=trail_atr_points,
                entry_start_1m=entry_start_1m,
                entry_end_1m=entry_end_1m,
                flat_start_1m=flat_start_1m_val,
                last_bar_1m=last_bar_1m_val,
                internal_swing_level=raw_swing,
                cancel_on_swing=config.lsi_cancel_on_swing,
                pre_entry_cancel_target_price=(
                    tp1 if config.limit_cancel_on_pre_entry_target_touch == "tp1"
                    else tp2 if config.limit_cancel_on_pre_entry_target_touch == "tp2"
                    else np.nan
                ),
            ))

        # Phase 2: Group by session-day and enforce one-trade-per-day.
        # Pine Script allows both long and short setups to arm, but once
        # any limit order fills (position_size != 0), the other is blocked.
        # We replicate this by scanning fill bars for all candidates in a
        # session-day, then only simulating the one that fills first.
        sd_groups: dict[int, list[_PreparedCandidate]] = defaultdict(list)
        for pc in prepared:
            sd_groups[pc.sd].append(pc)

        def _run_simulation(pc: _PreparedCandidate) -> tuple[int, int, int, float, float, float]:
            if use_hierarchical:
                # Hierarchical: 5m primary, 1m drill-down on ambiguous bars,
                # 30s on ambiguous 1m bars (when available), 1s on ambiguous 30s bars
                return _simulate_single_trade_hierarchical(
                    high, low, close,
                    pc.entry_bar_start, pc.entry_bar_end,
                    pc.flat_bar_start, pc.last_bar,
                    high_1m, low_1m, close_1m,
                    high_30s, low_30s, close_30s,
                    high_1s, low_1s, close_1s,
                    map_5m_1m_arr, map_1m_30s_arr, map_30s_1s_arr, map_1m_1s_arr,
                    has_30s, has_1s,
                    pc.direction,
                    pc.entry_price, pc.stop_price, pc.tp1_price, pc.tp2_price, pc.be_price,
                    pc.is_single, pc.qty, pc.half_qty,
                    config.point_value,
                    config.commission_per_contract,
                    pre_entry_cancel_requires_new_htf_lsi_sweep,
                    pre_entry_new_high_sweep_5m,
                    pre_entry_new_low_sweep_5m,
                    runner_trail_mode,
                    config.runner_trail_trigger_r,
                    config.runner_trail_stop_r,
                    config.runner_trail_step_r,
                    config.runner_trail_gap_r,
                    pc.trail_atr_points,
                    pc.internal_swing_level,
                    pc.cancel_on_swing,
                    pc.pre_entry_cancel_target_price,
                )
            elif use_magnifier and pc.entry_start_1m >= 0:
                fill_bar_1m, exit_type, exit_bar_1m, pnl_pts, _, _ = _simulate_single_trade_magnifier(
                    high_1m, low_1m, close_1m,
                    pc.entry_start_1m, pc.entry_end_1m,
                    pc.flat_start_1m, pc.last_bar_1m,
                    pc.direction,
                    pc.entry_price, pc.stop_price, pc.tp1_price, pc.tp2_price, pc.be_price,
                    pc.is_single, pc.qty, pc.half_qty,
                    config.point_value,
                    config.commission_per_contract,
                    pre_entry_cancel_requires_new_htf_lsi_sweep,
                    pre_entry_new_high_sweep_1m,
                    pre_entry_new_low_sweep_1m,
                    runner_trail_mode,
                    config.runner_trail_trigger_r,
                    config.runner_trail_stop_r,
                    config.runner_trail_step_r,
                    config.runner_trail_gap_r,
                    pc.trail_atr_points,
                    pc.internal_swing_level,
                    pc.cancel_on_swing,
                    pc.pre_entry_cancel_target_price,
                )
                # Map 1m indices back to 5m for TradeResult timestamps
                fill_bar = map_1m_to_5m(fill_bar_1m, bar_map) if fill_bar_1m >= 0 else -1
                exit_bar = map_1m_to_5m(exit_bar_1m, bar_map) if exit_bar_1m >= 0 else -1
                return fill_bar, exit_type, exit_bar, pnl_pts, -1.0, -1.0
            else:
                return _simulate_single_trade(
                    high, low, close,
                    pc.entry_bar_start, pc.entry_bar_end,
                    pc.flat_bar_start, pc.last_bar,
                    pc.direction,
                    pc.entry_price, pc.stop_price, pc.tp1_price, pc.tp2_price, pc.be_price,
                    pc.is_single, pc.qty, pc.half_qty,
                    config.point_value,
                    config.commission_per_contract,
                    pre_entry_cancel_requires_new_htf_lsi_sweep,
                    pre_entry_new_high_sweep_5m,
                    pre_entry_new_low_sweep_5m,
                    runner_trail_mode,
                    config.runner_trail_trigger_r,
                    config.runner_trail_stop_r,
                    config.runner_trail_step_r,
                    config.runner_trail_gap_r,
                    pc.trail_atr_points,
                    pc.internal_swing_level,
                    pc.cancel_on_swing,
                    pc.pre_entry_cancel_target_price,
                )

        def _simulate_candidate(pc: _PreparedCandidate) -> tuple[int, int, int, float, float, float]:
            fill_bar, exit_type, exit_bar, pnl_pts, fill_1m_f, exit_1m_f = _run_simulation(pc)
            if (
                context_gate_tokens
                and fill_bar >= 0
                and not _entry_context_passes(
                    context_gate_tokens,
                    config.entry_context_min_atr,
                    config.entry_context_max_atr,
                    pc.direction,
                    pc.entry_price,
                    fill_bar,
                    context_daily_atr,
                    session_context_values,
                )
            ):
                return -1, EXIT_NO_FILL, -1, 0.0, -1.0, -1.0
            return fill_bar, exit_type, exit_bar, pnl_pts, fill_1m_f, exit_1m_f

        def _append_sim_result(
            pc: _PreparedCandidate,
            fill_bar: int,
            exit_type: int,
            exit_bar: int,
            pnl_pts: float,
            fill_1m_f: float,
            exit_1m_f: float,
        ) -> None:
            if reverse_dir:
                pnl_pts = -pnl_pts
                # Swap exit labels so dashboard shows correct win/loss
                if exit_type == EXIT_SL:
                    exit_type = EXIT_TP2_SINGLE
                elif exit_type in (EXIT_TP1_TP2, EXIT_TP2_SINGLE):
                    exit_type = EXIT_SL
            gross_pnl_usd = pnl_pts * pc.qty * config.point_value
            commission_usd = 0.0
            if exit_type != EXIT_NO_FILL:
                commission_usd = 2 * pc.qty * config.commission_per_contract
            pnl_usd = gross_pnl_usd - commission_usd
            r_multiple = pnl_pts / pc.risk_pts if pc.risk_pts > 0 else 0.0
            gross_risk_usd = pc.risk_pts * pc.qty * config.point_value
            net_r_multiple = pnl_usd / gross_risk_usd if gross_risk_usd > 0 else 0.0
            all_results.append(TradeResult(
                date=pc.cand.date_str, session=session.name,
                direction=-pc.direction if reverse_dir else pc.direction,
                signal_bar=pc.cand.signal_bar,
                fill_bar=fill_bar, entry_price=pc.entry_price,
                stop_price=pc.stop_price, tp1_price=pc.tp1_price,
                tp2_price=pc.tp2_price, exit_type=exit_type,
                exit_bar=exit_bar, pnl_points=pnl_pts, pnl_usd=pnl_usd,
                r_multiple=r_multiple, qty=pc.qty, half_qty=pc.half_qty,
                gap_size=pc.gap_size, risk_points=pc.risk_pts,
                fill_time=_resolve_time(timestamps, fill_bar, timestamps_1m, fill_1m_f if use_hierarchical else -1.0),
                exit_time=_resolve_time(timestamps, exit_bar, timestamps_1m, exit_1m_f if use_hierarchical else -1.0),
                lsi_swept_level=pc.cand.lsi_swept_level,
                lsi_fvg_top=pc.cand.lsi_fvg_top,
                lsi_fvg_bottom=pc.cand.lsi_fvg_bottom,
                lsi_fvg_time=timestamps[pc.cand.lsi_fvg_bar].isoformat() if pc.cand.lsi_fvg_bar >= 0 else "",
                lsi_sweep_time=timestamps[pc.cand.lsi_sweep_bar].isoformat() if pc.cand.lsi_sweep_bar >= 0 else "",
                lsi_confirmation_type=pc.cand.lsi_confirmation_type,
                lsi_cisd_level=pc.cand.lsi_cisd_level,
                lsi_cisd_time=timestamps[pc.cand.lsi_cisd_bar].isoformat() if pc.cand.lsi_cisd_bar >= 0 else "",
                reference_level_name=pc.cand.reference_level_name,
                reference_level_price=pc.cand.reference_level_price,
                htf_level_time=pc.cand.htf_level_time,
                htf_level_price=pc.cand.htf_level_price,
                htf_level_side=pc.cand.htf_level_side,
                htf_level_tf_minutes=pc.cand.htf_level_tf_minutes,
                fvg_to_inversion_bars=pc.cand.fvg_to_inversion_bars,
                sweep_to_inversion_bars=pc.cand.sweep_to_inversion_bars,
                inversion_ordinal=pc.cand.inversion_ordinal,
                lsi_lrlr_present=pc.cand.lsi_lrlr_present,
                lsi_lrlr_level_count=pc.cand.lsi_lrlr_level_count,
                lsi_lrlr_nearest_level_price=pc.cand.lsi_lrlr_nearest_level_price,
                lsi_lrlr_farthest_level_price=pc.cand.lsi_lrlr_farthest_level_price,
                lsi_lrlr_span_bars=pc.cand.lsi_lrlr_span_bars,
                lsi_lrlr_price_span_atr=pc.cand.lsi_lrlr_price_span_atr,
                lsi_lrlr_slope_atr_per_bar=pc.cand.lsi_lrlr_slope_atr_per_bar,
                lsi_lrlr_fit_error_atr=pc.cand.lsi_lrlr_fit_error_atr,
                lsi_lrlr_tp1_path_present=pc.cand.lsi_lrlr_tp1_path_present,
                lsi_lrlr_nearest_tp1_gap_atr=pc.cand.lsi_lrlr_nearest_tp1_gap_atr,
                gross_pnl_usd=gross_pnl_usd,
                commission_usd=commission_usd,
                net_r_multiple=net_r_multiple,
            ))

        def _append_no_fill(pc: _PreparedCandidate) -> None:
            all_results.append(TradeResult(
                date=pc.cand.date_str, session=session.name,
                direction=-pc.direction if reverse_dir else pc.direction, signal_bar=pc.cand.signal_bar,
                fill_bar=-1, entry_price=pc.entry_price,
                stop_price=pc.stop_price, tp1_price=pc.tp1_price,
                tp2_price=pc.tp2_price, exit_type=EXIT_NO_FILL,
                exit_bar=-1, pnl_points=0.0, pnl_usd=0.0,
                r_multiple=0.0, qty=pc.qty, half_qty=pc.half_qty,
                gap_size=pc.gap_size, risk_points=pc.risk_pts,
                fill_time="", exit_time="",
                lsi_swept_level=pc.cand.lsi_swept_level,
                lsi_fvg_top=pc.cand.lsi_fvg_top,
                lsi_fvg_bottom=pc.cand.lsi_fvg_bottom,
                lsi_fvg_time=timestamps[pc.cand.lsi_fvg_bar].isoformat() if pc.cand.lsi_fvg_bar >= 0 else "",
                lsi_sweep_time=timestamps[pc.cand.lsi_sweep_bar].isoformat() if pc.cand.lsi_sweep_bar >= 0 else "",
                lsi_confirmation_type=pc.cand.lsi_confirmation_type,
                lsi_cisd_level=pc.cand.lsi_cisd_level,
                lsi_cisd_time=timestamps[pc.cand.lsi_cisd_bar].isoformat() if pc.cand.lsi_cisd_bar >= 0 else "",
                reference_level_name=pc.cand.reference_level_name,
                reference_level_price=pc.cand.reference_level_price,
                htf_level_time=pc.cand.htf_level_time,
                htf_level_price=pc.cand.htf_level_price,
                htf_level_side=pc.cand.htf_level_side,
                htf_level_tf_minutes=pc.cand.htf_level_tf_minutes,
                fvg_to_inversion_bars=pc.cand.fvg_to_inversion_bars,
                sweep_to_inversion_bars=pc.cand.sweep_to_inversion_bars,
                inversion_ordinal=pc.cand.inversion_ordinal,
                lsi_lrlr_present=pc.cand.lsi_lrlr_present,
                lsi_lrlr_level_count=pc.cand.lsi_lrlr_level_count,
                lsi_lrlr_nearest_level_price=pc.cand.lsi_lrlr_nearest_level_price,
                lsi_lrlr_farthest_level_price=pc.cand.lsi_lrlr_farthest_level_price,
                lsi_lrlr_span_bars=pc.cand.lsi_lrlr_span_bars,
                lsi_lrlr_price_span_atr=pc.cand.lsi_lrlr_price_span_atr,
                lsi_lrlr_slope_atr_per_bar=pc.cand.lsi_lrlr_slope_atr_per_bar,
                lsi_lrlr_fit_error_atr=pc.cand.lsi_lrlr_fit_error_atr,
                lsi_lrlr_tp1_path_present=pc.cand.lsi_lrlr_tp1_path_present,
                lsi_lrlr_nearest_tp1_gap_atr=pc.cand.lsi_lrlr_nearest_tp1_gap_atr,
            ))

        is_ib = config.strategy == "ib"
        reverse_dir = config.reverse_direction

        def _reverse_pc(pc: _PreparedCandidate) -> _PreparedCandidate:
            """Flip direction and swap stop/TP for post-fill reversal.

            For a 1:1 at midpoint: old SL price becomes new TP, old TP becomes new SL.
            tp1 mirrors the tp1_ratio offset from the new TP side.
            """
            new_dir = -pc.direction
            new_stop = pc.tp2_price     # old full TP becomes new stop
            new_tp2 = pc.stop_price     # old stop becomes new full TP
            # Mirror tp1: same proportional distance from entry on the new TP side
            tp1_frac = abs(pc.tp1_price - pc.entry_price) / abs(pc.tp2_price - pc.entry_price) if abs(pc.tp2_price - pc.entry_price) > 0 else 1.0
            new_risk = abs(new_tp2 - pc.entry_price)
            if new_dir == 1:
                new_tp1 = pc.entry_price + tp1_frac * new_risk
            else:
                new_tp1 = pc.entry_price - tp1_frac * new_risk
            return _PreparedCandidate(
                cand=pc.cand, sd=pc.sd,
                direction=new_dir,
                entry_price=pc.entry_price,
                stop_price=new_stop,
                tp1_price=new_tp1,
                tp2_price=new_tp2,
                be_price=pc.be_price,
                risk_pts=pc.risk_pts,
                qty=pc.qty, half_qty=pc.half_qty,
                is_single=pc.is_single,
                gap_size=pc.gap_size,
                entry_bar_start=pc.entry_bar_start,
                entry_bar_end=pc.entry_bar_end,
                flat_bar_start=pc.flat_bar_start,
                last_bar=pc.last_bar,
                trail_atr_points=pc.trail_atr_points,
                entry_start_1m=pc.entry_start_1m,
                entry_end_1m=pc.entry_end_1m,
                flat_start_1m=pc.flat_start_1m,
                last_bar_1m=pc.last_bar_1m,
                internal_swing_level=pc.internal_swing_level,
                cancel_on_swing=pc.cancel_on_swing,
                pre_entry_cancel_target_price=pc.pre_entry_cancel_target_price,
            )

        for sd in sorted(sd_groups):
            group = sd_groups[sd]
            if config.strategy == "reference_lsi":
                pending = [
                    (pc, _simulate_candidate(pc))
                    for pc in sorted(group, key=lambda pc: (pc.cand.signal_bar, pc.entry_bar_start))
                ]
                current_exit_bar = -1

                while pending:
                    blocked = [(pc, sim) for pc, sim in pending if pc.cand.signal_bar <= current_exit_bar]
                    if blocked:
                        for pc, _ in blocked:
                            _append_no_fill(pc)
                        pending = [(pc, sim) for pc, sim in pending if pc.cand.signal_bar > current_exit_bar]
                        if not pending:
                            break

                    filled = [(pc, sim) for pc, sim in pending if sim[0] >= 0]
                    if not filled:
                        for pc, sim in pending:
                            _append_sim_result(pc, *sim)
                        break

                    winner_pc, winner_sim = min(
                        filled,
                        key=lambda x: (x[1][0], x[0].cand.signal_bar),
                    )
                    _append_sim_result(winner_pc, *winner_sim)
                    current_exit_bar = max(current_exit_bar, winner_sim[2])

                    next_pending = []
                    for pc, sim in pending:
                        if pc is winner_pc:
                            continue
                        if pc.cand.signal_bar <= current_exit_bar:
                            _append_no_fill(pc)
                        else:
                            next_pending.append((pc, sim))
                    pending = next_pending
                continue
            if config.strategy == "htf_lsi":
                pending = [
                    (pc, _simulate_candidate(pc))
                    for pc in sorted(group, key=lambda pc: (pc.cand.signal_bar, pc.entry_bar_start))
                ]
                current_exit_bar = -1
                filled_count = 0
                direction_priority = {-1: -1, 1: 1}

                while pending:
                    blocked = [(pc, sim) for pc, sim in pending if pc.cand.signal_bar <= current_exit_bar]
                    if blocked:
                        for pc, _ in blocked:
                            _append_no_fill(pc)
                        pending = [(pc, sim) for pc, sim in pending if pc.cand.signal_bar > current_exit_bar]
                        if not pending:
                            break

                    if (
                        config.htf_trade_max_per_session > 0
                        and filled_count >= config.htf_trade_max_per_session
                    ):
                        for pc, _ in pending:
                            _append_no_fill(pc)
                        break

                    filled = [(pc, sim) for pc, sim in pending if sim[0] >= 0]
                    if not filled:
                        for pc, sim in pending:
                            _append_sim_result(pc, *sim)
                        break

                    winner_pc, winner_sim = min(
                        filled,
                        key=lambda x: (
                            x[1][0],
                            x[0].cand.signal_bar,
                            direction_priority.get(x[0].direction, 0),
                        ),
                    )
                    _append_sim_result(winner_pc, *winner_sim)
                    current_exit_bar = max(current_exit_bar, winner_sim[2])
                    filled_count += 1

                    next_pending = []
                    for pc, sim in pending:
                        if pc is winner_pc:
                            continue
                        if pc.cand.signal_bar <= current_exit_bar:
                            _append_no_fill(pc)
                        else:
                            next_pending.append((pc, sim))
                    pending = next_pending
                continue
            if config.strategy in {"continuation", "reversal"} and config.orb_trade_max_per_session != 1:
                pending = [
                    (pc, _simulate_candidate(pc))
                    for pc in sorted(group, key=lambda pc: (pc.cand.signal_bar, pc.entry_bar_start))
                ]
                current_exit_bar = -1
                filled_count = 0

                while pending:
                    blocked = [(pc, sim) for pc, sim in pending if pc.cand.signal_bar <= current_exit_bar]
                    if blocked:
                        for pc, _ in blocked:
                            _append_no_fill(pc)
                        pending = [(pc, sim) for pc, sim in pending if pc.cand.signal_bar > current_exit_bar]
                        if not pending:
                            break

                    if (
                        config.orb_trade_max_per_session > 0
                        and filled_count >= config.orb_trade_max_per_session
                    ):
                        for pc, _ in pending:
                            _append_no_fill(pc)
                        break

                    # Re-arm only the next fresh setup per direction after each exit.
                    armed_by_direction: dict[int, bool] = {}
                    armed = []
                    for pc, sim in pending:
                        if armed_by_direction.get(pc.direction, False):
                            continue
                        armed_by_direction[pc.direction] = True
                        armed.append((pc, sim))

                    filled = [(pc, sim) for pc, sim in armed if sim[0] >= 0]
                    if not filled:
                        for pc, _ in pending:
                            _append_no_fill(pc)
                        break

                    winner_pc, winner_sim = min(
                        filled,
                        key=lambda x: (x[1][0], x[0].cand.signal_bar),
                    )
                    _append_sim_result(winner_pc, *winner_sim)
                    current_exit_bar = max(current_exit_bar, winner_sim[2])
                    filled_count += 1

                    realized_exit_type, realized_r_multiple = _realized_orb_outcome(
                        winner_pc,
                        winner_sim[1],
                        winner_sim[3],
                        reverse_dir=reverse_dir,
                    )
                    if not _orb_reentry_policy_allows(
                        config.orb_reentry_policy,
                        realized_exit_type,
                        realized_r_multiple,
                    ):
                        for pc, _ in pending:
                            if pc is not winner_pc:
                                _append_no_fill(pc)
                        break

                    next_pending = []
                    for pc, sim in pending:
                        if pc is winner_pc:
                            continue
                        if pc.cand.signal_bar <= current_exit_bar:
                            _append_no_fill(pc)
                        else:
                            next_pending.append((pc, sim))
                    pending = next_pending
                continue

            if len(group) == 1:
                pc = group[0]
                if is_ib and pc.cand.lsi_fvg_top > 0:
                    # IB strategy: check IB-break before fill using dedicated scanner.
                    # Use 1m magnifier when available for correct intra-bar ordering.
                    if use_magnifier and pc.entry_start_1m >= 0:
                        fb_1m = _scan_fill_bar_ib_magnifier(
                            high_1m, low_1m,
                            pc.entry_start_1m, pc.entry_end_1m, pc.last_bar_1m,
                            pc.direction, pc.entry_price,
                            pc.cand.lsi_fvg_top,    # IB high
                            pc.cand.lsi_fvg_bottom,  # IB low
                        )
                        fb = map_1m_to_5m(fb_1m, bar_map) if fb_1m >= 0 else -1
                    else:
                        fb = _scan_fill_bar_ib(
                            high, low,
                            pc.entry_bar_start, pc.entry_bar_end, pc.last_bar,
                            pc.direction, pc.entry_price,
                            pc.cand.lsi_fvg_top,    # IB high
                            pc.cand.lsi_fvg_bottom,  # IB low
                        )
                    if fb < 0:
                        _append_no_fill(pc)
                    else:
                        # Narrow entry window to fill bar so standard sim finds it immediately
                        pc = _PreparedCandidate(
                            cand=pc.cand, sd=pc.sd,
                            direction=pc.direction,
                            entry_price=pc.entry_price,
                            stop_price=pc.stop_price,
                            tp1_price=pc.tp1_price,
                            tp2_price=pc.tp2_price,
                            be_price=pc.be_price,
                            risk_pts=pc.risk_pts,
                            qty=pc.qty, half_qty=pc.half_qty,
                            is_single=pc.is_single,
                            gap_size=pc.gap_size,
                            entry_bar_start=fb,
                            entry_bar_end=pc.entry_bar_end,
                            flat_bar_start=pc.flat_bar_start,
                            last_bar=pc.last_bar,
                            trail_atr_points=pc.trail_atr_points,
                            entry_start_1m=pc.entry_start_1m,
                            entry_end_1m=pc.entry_end_1m,
                            flat_start_1m=pc.flat_start_1m,
                            last_bar_1m=pc.last_bar_1m,
                            internal_swing_level=pc.internal_swing_level,
                            cancel_on_swing=pc.cancel_on_swing,
                            pre_entry_cancel_target_price=pc.pre_entry_cancel_target_price,
                        )
                        _append_sim_result(pc, *_simulate_candidate(pc))
                else:
                    _append_sim_result(pc, *_simulate_candidate(pc))
            else:
                # Multiple candidates (long + short) on same session-day.
                # Determine which valid candidate fills first after structural
                # simulation plus any configured fill-time context overlay.
                sim_results = []
                for pc in group:
                    sim_results.append((pc, _simulate_candidate(pc)))

                filled = [
                    (pc, sim)
                    for pc, sim in sim_results
                    if sim[0] >= 0
                ]
                if not filled:
                    for pc, _ in sim_results:
                        _append_no_fill(pc)
                else:
                    # Winner = earliest fill bar (ties: earlier signal_bar wins)
                    winner_pc, winner_sim = min(
                        filled,
                        key=lambda x: (x[1][0], x[0].cand.signal_bar),
                    )
                    _append_sim_result(winner_pc, *winner_sim)
                    for pc, _ in sim_results:
                        if pc is not winner_pc:
                            _append_no_fill(pc)

    # Sort by date
    all_results.sort(key=lambda t: t.date)

    # Filter out warmup-period trades
    if start_date is not None:
        all_results = [t for t in all_results if t.date >= start_date]

    return all_results
