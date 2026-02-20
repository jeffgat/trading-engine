"""Trade simulation engine.

Hybrid approach:
1. Vectorized signal generation produces SetupCandidate records
2. Numba-compiled loop simulates fills and exits per candidate

This module orchestrates the full pipeline: signals → candidates → trades → results.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
import numba as nb
import pandas as pd

from collections import defaultdict

from ..config import StrategyConfig, SessionConfig
from ..signals.session import compute_session_masks, compute_trading_days, compute_session_days, compute_date_strings
from ..signals.daily_atr import compute_daily_atr
from ..signals.orb import compute_orb_levels
from ..signals.fvg import detect_fvg


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

EXIT_NAMES = {
    EXIT_NO_FILL: "no_fill",
    EXIT_SL: "sl",
    EXIT_TP1_TP2: "tp1_tp2",
    EXIT_TP1_BE: "tp1_be",
    EXIT_TP1_EOD: "tp1_eod",
    EXIT_EOD: "eod",
    EXIT_TP2_SINGLE: "tp2_single",
}


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
    pnl_usd: float  # total PnL in USD
    r_multiple: float  # PnL as multiple of risk
    qty: float
    half_qty: float
    gap_size: float
    risk_points: float
    fill_time: str  # ISO timestamp of fill bar ("" if no fill)
    exit_time: str  # ISO timestamp of exit bar ("" if no fill)


# ---------------------------------------------------------------------------
# Numba-compiled trade simulation
# ---------------------------------------------------------------------------
@nb.njit(cache=True)
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
    for i in range(entry_bar_start, min(entry_bar_end + 1, last_bar + 1)):
        if direction == 1:  # long: fill when low <= entry
            if low[i] <= entry_price:
                fill_bar = i
                break
        else:  # short: fill when high >= entry
            if high[i] >= entry_price:
                fill_bar = i
                break

    if fill_bar == -1:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 2: Simulate exit
    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    # Start checking from the bar AFTER fill
    scan_start = fill_bar + 1

    for i in range(scan_start, last_bar + 1):
        # Check if we've entered flat window
        is_flat_bar = i >= flat_bar_start

        if direction == 1:  # LONG
            sl_hit = low[i] <= current_stop
            tp1_trigger = high[i] >= tp1_price and not tp1_hit
            tp2_trigger = high[i] >= tp2_price

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
                pnl_points = current_stop - entry_price
                return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

            if is_single:
                # Single contract: check if price touched TP1 level (BE trigger)
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
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
                    pnl_points = current_stop - entry_price
                    return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

                if tp1_trigger:
                    # Partial exit at TP1
                    leg1_pnl = (tp1_price - entry_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
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

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close[i]) * (remaining_qty / qty)
                    return fill_bar, EXIT_TP1_EOD, i, pnl_points, 0.0, 0.0
                else:
                    pnl_points = entry_price - close[i]
                    return fill_bar, EXIT_EOD, i, pnl_points, 0.0, 0.0

            if sl_hit and not tp1_hit:
                pnl_points = entry_price - current_stop
                return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points = entry_price - tp2_price
                    return fill_bar, EXIT_TP2_SINGLE, i, pnl_points, 0.0, 0.0
                if sl_hit and tp1_hit:
                    pnl_points = entry_price - current_stop
                    return fill_bar, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
            else:
                if sl_hit and tp1_trigger:
                    pnl_points = entry_price - current_stop
                    return fill_bar, EXIT_SL, i, pnl_points, 0.0, 0.0

                if tp1_trigger:
                    leg1_pnl = (entry_price - tp1_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
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


@nb.njit(cache=True)
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


# ---------------------------------------------------------------------------
# Bar magnifier: 1-minute sub-bar simulation (Numba-compiled)
# ---------------------------------------------------------------------------

@nb.njit(cache=True)
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
) -> tuple:
    """Simulate exit on 1m bars. Returns (exit_type, exit_bar_1m, pnl_points).

    Same TP1/TP2/BE/EOD/SL logic as Phase 2 of _simulate_single_trade,
    but operating on 1m OHLC arrays for higher precision.
    """
    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    scan_start = fill_bar_1m + 1

    for i in range(scan_start, last_bar_1m + 1):
        is_flat_bar = i >= flat_start_1m

        if direction == 1:  # LONG
            sl_hit = low_1m[i] <= current_stop
            tp1_trigger = high_1m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_1m[i] >= tp2_price

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_1m[i] - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                else:
                    pnl_points = (close_1m[i] - entry_price)
                    return EXIT_EOD, i, pnl_points

            if sl_hit and not tp1_hit:
                pnl_points = current_stop - entry_price
                return EXIT_SL, i, pnl_points

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points = tp2_price - entry_price
                    return EXIT_TP2_SINGLE, i, pnl_points
                if sl_hit and tp1_hit:
                    pnl_points = current_stop - entry_price
                    return EXIT_TP1_BE, i, pnl_points
            else:
                if sl_hit and tp1_trigger:
                    pnl_points = current_stop - entry_price
                    return EXIT_SL, i, pnl_points

                if tp1_trigger:
                    leg1_pnl = (tp1_price - entry_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
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

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_1m[i]) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                else:
                    pnl_points = entry_price - close_1m[i]
                    return EXIT_EOD, i, pnl_points

            if sl_hit and not tp1_hit:
                pnl_points = entry_price - current_stop
                return EXIT_SL, i, pnl_points

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points = entry_price - tp2_price
                    return EXIT_TP2_SINGLE, i, pnl_points
                if sl_hit and tp1_hit:
                    pnl_points = entry_price - current_stop
                    return EXIT_TP1_BE, i, pnl_points
            else:
                if sl_hit and tp1_trigger:
                    pnl_points = entry_price - current_stop
                    return EXIT_SL, i, pnl_points

                if tp1_trigger:
                    leg1_pnl = (entry_price - tp1_price) * (half_qty / qty)
                    pnl_points += leg1_pnl
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
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


@nb.njit(cache=True)
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
    for i in range(entry_start_1m, min(entry_end_1m + 1, last_bar_1m + 1)):
        if direction == 1:
            if low_1m[i] <= entry_price:
                fill_bar_1m = i
                break
        else:
            if high_1m[i] >= entry_price:
                fill_bar_1m = i
                break

    if fill_bar_1m == -1:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 2: Simulate exit on 1m bars
    exit_type, exit_bar_1m, pnl_points = _simulate_exit_magnifier(
        high_1m, low_1m, close_1m,
        fill_bar_1m, flat_start_1m, last_bar_1m,
        direction,
        entry_price, stop_price, tp1_price, tp2_price, be_price,
        is_single, qty, half_qty,
    )

    return fill_bar_1m, exit_type, exit_bar_1m, pnl_points, 0.0, 0.0


@nb.njit(cache=True)
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

@nb.njit(cache=True)
def _drill_down_1s(
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    start_1s: int,
    end_1s: int,
    direction: int,
    entry_price: float,
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

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
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

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
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
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty

    return False, -1, pnl_points, tp1_hit, current_stop, remaining_qty


@nb.njit(cache=True)
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

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
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
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
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

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
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
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
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
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty

    return False, -1, pnl_points, tp1_hit, current_stop, remaining_qty


@nb.njit(cache=True)
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
) -> tuple:
    """Scan 1m sub-bars for an ambiguous 5m bar or the fill bar's tail.

    When a 1m bar is itself ambiguous (sl_hit AND tp1_trigger):
      - Tries 30s sub-bars first (if has_30s), which itself tries 1s on ambiguous 30s bars.
      - Falls back to direct 1s (if has_1s but no 30s).
      - Falls back to pessimistic SL if neither resolves it.

    Returns (resolved, exit_type, pnl_points, tp1_hit, current_stop, remaining_qty).
    """
    for i in range(start_1m, end_1m):
        is_flat = i >= flat_start_1m

        if direction == 1:
            sl_hit = low_1m[i] <= current_stop
            tp1_trigger = high_1m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_1m[i] >= tp2_price

            if is_flat and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_1m[i] - entry_price) * (remaining_qty / qty)
                    return True, EXIT_TP1_EOD, pnl_points, tp1_hit, current_stop, remaining_qty
                else:
                    pnl_points += close_1m[i] - entry_price
                    return True, EXIT_EOD, pnl_points, tp1_hit, current_stop, remaining_qty

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return True, EXIT_TP2_SINGLE, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
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
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            if res:
                                return True, et, pnl_points, tp1_hit, current_stop, remaining_qty
                    elif has_1s and i < len(map_1m_1s):
                        s1s = map_1m_1s[i, 0]
                        e1s = map_1m_1s[i, 1]
                        if e1s > s1s:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1s(
                                high_1s, low_1s, close_1s, s1s, e1s,
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            if res:
                                return True, et, pnl_points, tp1_hit, current_stop, remaining_qty
                    # Fallback: pessimistic
                    pnl_points += current_stop - entry_price
                    return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty
        else:
            sl_hit = high_1m[i] >= current_stop
            tp1_trigger = low_1m[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_1m[i] <= tp2_price

            if is_flat and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_1m[i]) * (remaining_qty / qty)
                    return True, EXIT_TP1_EOD, pnl_points, tp1_hit, current_stop, remaining_qty
                else:
                    pnl_points += entry_price - close_1m[i]
                    return True, EXIT_EOD, pnl_points, tp1_hit, current_stop, remaining_qty

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return True, EXIT_TP2_SINGLE, pnl_points, tp1_hit, current_stop, remaining_qty
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
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
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            if res:
                                return True, et, pnl_points, tp1_hit, current_stop, remaining_qty
                    elif has_1s and i < len(map_1m_1s):
                        s1s = map_1m_1s[i, 0]
                        e1s = map_1m_1s[i, 1]
                        if e1s > s1s:
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1s(
                                high_1s, low_1s, close_1s, s1s, e1s,
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            if res:
                                return True, et, pnl_points, tp1_hit, current_stop, remaining_qty
                    # Fallback: pessimistic
                    pnl_points += entry_price - current_stop
                    return True, EXIT_SL, pnl_points, tp1_hit, current_stop, remaining_qty

                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return True, EXIT_TP1_BE, pnl_points, tp1_hit, current_stop, remaining_qty
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return True, EXIT_TP1_TP2, pnl_points, tp1_hit, current_stop, remaining_qty

    return False, -1, pnl_points, tp1_hit, current_stop, remaining_qty


@nb.njit(cache=True)
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
) -> tuple:
    """Hierarchical fill+exit simulation: 5m primary, 1m on ambiguous bars, 30s on ambiguous 1m bars, 1s on ambiguous 30s bars.

    Fill is detected at the 5m level. When a bar simultaneously touches two price
    objectives (e.g. entry+SL, SL+TP1), we drill into the 1m sub-bars of that
    specific bar. If the conflict persists at 1m, we drill into 1s.

    Returns (fill_bar_5m, exit_type, exit_bar_5m, pnl_points, 0.0, 0.0).
    Same tuple shape as _simulate_single_trade for drop-in compatibility.
    """
    risk_pts = abs(entry_price - stop_price)
    if risk_pts <= 0:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # Phase 1: Scan for fill at 5m level
    fill_bar_5m = -1
    for i in range(entry_bar_start, min(entry_bar_end + 1, last_bar + 1)):
        if direction == 1:
            if low_5m[i] <= entry_price:
                fill_bar_5m = i
                break
        else:
            if high_5m[i] >= entry_price:
                fill_bar_5m = i
                break

    if fill_bar_5m == -1:
        return -1, EXIT_NO_FILL, -1, 0.0, 0.0, 0.0

    # State
    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    # Precompute flat_start in 1m index (used for drill-down flat detection)
    flat_5m_clamped = min(flat_bar_start, len(map_5m_1m) - 1)
    flat_start_1m = map_5m_1m[flat_5m_clamped, 0]

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

        if fill_bar_1m >= 0 and fill_bar_1m + 1 < e1m:
            # Scan remaining 1m bars inside the fill bar for exits
            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1m(
                high_1m, low_1m, close_1m,
                high_30s, low_30s, close_30s,
                high_1s, low_1s, close_1s,
                map_1m_30s, map_30s_1s, map_1m_1s,
                has_30s, has_1s,
                fill_bar_1m + 1, e1m,
                flat_start_1m,
                direction, entry_price, current_stop,
                tp1_price, tp2_price, be_price,
                tp1_hit, is_single, qty, half_qty, remaining_qty, pnl_points,
            )
            if res:
                return fill_bar_5m, et, fill_bar_5m, pnl_points, 0.0, 0.0

    # Phase 2b: Scan subsequent 5m bars
    for i in range(fill_bar_5m + 1, last_bar + 1):
        is_flat_bar = i >= flat_bar_start

        if direction == 1:
            sl_hit = low_5m[i] <= current_stop
            tp1_trigger = high_5m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_5m[i] >= tp2_price

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_5m[i] - entry_price) * (remaining_qty / qty)
                    return fill_bar_5m, EXIT_TP1_EOD, i, pnl_points, 0.0, 0.0
                else:
                    pnl_points += close_5m[i] - entry_price
                    return fill_bar_5m, EXIT_EOD, i, pnl_points, 0.0, 0.0

            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return fill_bar_5m, EXIT_SL, i, pnl_points, 0.0, 0.0

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return fill_bar_5m, EXIT_TP2_SINGLE, i, pnl_points, 0.0, 0.0
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
            else:
                if sl_hit and tp1_trigger:
                    # Ambiguous 5m bar — drill to 1m
                    if i < len(map_5m_1m):
                        s1m = map_5m_1m[i, 0]
                        e1m = map_5m_1m[i, 1]
                        if e1m > s1m:
                            res, et, pnl_out, tp1_out, cs_out, rq_out = _drill_down_1m(
                                high_1m, low_1m, close_1m,
                                high_30s, low_30s, close_30s,
                                high_1s, low_1s, close_1s,
                                map_1m_30s, map_30s_1s, map_1m_1s,
                                has_30s, has_1s,
                                s1m, e1m, flat_start_1m,
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            pnl_points = pnl_out
                            tp1_hit = tp1_out
                            current_stop = cs_out
                            remaining_qty = rq_out
                            if res:
                                return fill_bar_5m, et, i, pnl_points, 0.0, 0.0
                            continue
                    # No 1m data for this bar — pessimistic
                    pnl_points += current_stop - entry_price
                    return fill_bar_5m, EXIT_SL, i, pnl_points, 0.0, 0.0

                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_TP2, i, pnl_points, 0.0, 0.0

        else:  # SHORT
            sl_hit = high_5m[i] >= current_stop
            tp1_trigger = low_5m[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_5m[i] <= tp2_price

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_5m[i]) * (remaining_qty / qty)
                    return fill_bar_5m, EXIT_TP1_EOD, i, pnl_points, 0.0, 0.0
                else:
                    pnl_points += entry_price - close_5m[i]
                    return fill_bar_5m, EXIT_EOD, i, pnl_points, 0.0, 0.0

            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return fill_bar_5m, EXIT_SL, i, pnl_points, 0.0, 0.0

            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return fill_bar_5m, EXIT_TP2_SINGLE, i, pnl_points, 0.0, 0.0
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
            else:
                if sl_hit and tp1_trigger:
                    if i < len(map_5m_1m):
                        s1m = map_5m_1m[i, 0]
                        e1m = map_5m_1m[i, 1]
                        if e1m > s1m:
                            res, et, pnl_out, tp1_out, cs_out, rq_out = _drill_down_1m(
                                high_1m, low_1m, close_1m,
                                high_30s, low_30s, close_30s,
                                high_1s, low_1s, close_1s,
                                map_1m_30s, map_30s_1s, map_1m_1s,
                                has_30s, has_1s,
                                s1m, e1m, flat_start_1m,
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            pnl_points = pnl_out
                            tp1_hit = tp1_out
                            current_stop = cs_out
                            remaining_qty = rq_out
                            if res:
                                return fill_bar_5m, et, i, pnl_points, 0.0, 0.0
                            continue
                    pnl_points += entry_price - current_stop
                    return fill_bar_5m, EXIT_SL, i, pnl_points, 0.0, 0.0

                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    continue

                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_BE, i, pnl_points, 0.0, 0.0
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return fill_bar_5m, EXIT_TP1_TP2, i, pnl_points, 0.0, 0.0

    # Reached end without exit
    if direction == 1:
        pnl_points += close_5m[last_bar] - entry_price
    else:
        pnl_points += entry_price - close_5m[last_bar]
    return fill_bar_5m, EXIT_EOD, last_bar, pnl_points, 0.0, 0.0


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
    # Bar magnifier: 1m bar boundaries (-1 when magnifier is off)
    entry_start_1m: int = -1
    entry_end_1m: int = -1
    flat_start_1m: int = -1
    last_bar_1m: int = -1


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


def _extract_setup_candidates(
    df: pd.DataFrame,
    session: SessionConfig,
    config: StrategyConfig,
) -> list[_SetupCandidate]:
    """Extract first-FVG-per-day setup candidates for a session.

    This is the vectorized Phase 1: compute all signals, then group by
    session-day and take the first valid FVG per direction.
    """
    timestamps = df.index

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

    # FVG detection
    fvg = detect_fvg(
        df["high"].values,
        df["low"].values,
        daily_atr,
        orb_high,
        orb_low,
        session.min_gap_atr_pct,
        session.max_gap_points,
        max_gap_atr_pct=getattr(session, "max_gap_atr_pct", 0.0),
        close=df["close"].values if config.impulse_close_filter else None,
        impulse_close_filter=config.impulse_close_filter,
    )

    # Date strings for excluded dates and half-days
    date_strs = compute_date_strings(timestamps)

    excluded = set(config.excluded_dates)

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

    # Exclude specific dates (vectorized via numpy isin)
    if excluded:
        exclude_arr = np.array(list(excluded))
        exclude_mask = np.isin(date_strs, exclude_arr)
        valid_long &= ~exclude_mask
        valid_short &= ~exclude_mask

    # Group by session day, take first FVG per direction.
    # Use session_day_id (not calendar date) so cross-midnight sessions
    # like Asia (20:00-07:00) are treated as one session day.
    candidates: list[_SetupCandidate] = []
    dates = timestamps.date
    close = df["close"].values

    if config.strategy == "cisd":
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
    elif config.strategy == "inversion":
        # Inversion mode: wait for a candle to close through the FVG zone,
        # then enter in the opposite direction on a retest.
        # Bullish FVG inverted → SHORT: close below long_fvg_bottom (high[2])
        # Bearish FVG inverted → LONG: close above short_fvg_top (low[2])
        candidates = _extract_inversion_candidates(
            df, fvg, valid_long, valid_short, session_day_id,
            masks["in_entry"], dates, close, session, daily_atr,
            direction_filter=config.direction_filter,
        )
    else:
        # Continuation or reversal mode
        dir_mult = -1 if config.strategy == "reversal" else 1
        take_longs = config.direction_filter in ("both", "long")
        take_shorts = config.direction_filter in ("both", "short")

        seen_long_days: set = set()
        seen_short_days: set = set()

        for i in range(len(df)):
            sd = session_day_id[i]

            # Bullish FVG: continuation=long, reversal=short
            out_dir = 1 * dir_mult
            if valid_long[i] and sd not in seen_long_days:
                if (out_dir == 1 and take_longs) or (out_dir == -1 and take_shorts):
                    seen_long_days.add(sd)
                    candidates.append(_SetupCandidate(
                        date_str=str(dates[i]),
                        session=session.name,
                        direction=out_dir,
                        signal_bar=i,
                        entry_price=fvg["long_entry_price"][i],
                        gap_size=fvg["long_gap_size"][i],
                        daily_atr=daily_atr[i],
                    ))

            # Bearish FVG: continuation=short, reversal=long
            out_dir = -1 * dir_mult
            if valid_short[i] and sd not in seen_short_days:
                if (out_dir == 1 and take_longs) or (out_dir == -1 and take_shorts):
                    seen_short_days.add(sd)
                    candidates.append(_SetupCandidate(
                        date_str=str(dates[i]),
                        session=session.name,
                        direction=out_dir,
                        signal_bar=i,
                        entry_price=fvg["short_entry_price"][i],
                        gap_size=fvg["short_gap_size"][i],
                        daily_atr=daily_atr[i],
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
                ))
                continue

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
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=-1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=gap_size,
                    daily_atr=atr,
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
                candidates.append(_SetupCandidate(
                    date_str=str(dates[i]),
                    session=session.name,
                    direction=1,
                    signal_bar=i - 1,
                    entry_price=close[i],
                    gap_size=gap_size,
                    daily_atr=atr,
                ))
                continue

            remaining_short.append(pending)
        pending_short = remaining_short

        # Clean up pending FVGs from previous session days
        pending_long = [p for p in pending_long if p[4] >= sd]
        pending_short = [p for p in pending_short if p[4] >= sd]

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
    }

    if has_1m:
        maps["map_5m_1m"]  = build_5m_to_1m_map(df, df_1m)
        maps["high_1m"]    = df_1m["high"].values.astype(np.float64)
        maps["low_1m"]     = df_1m["low"].values.astype(np.float64)
        maps["close_1m"]   = df_1m["close"].values.astype(np.float64)

    if has_30s:
        maps["map_1m_30s"] = build_1m_to_30s_map(df_1m, df_30s)
        maps["high_30s"]   = df_30s["high"].values.astype(np.float64)
        maps["low_30s"]    = df_30s["low"].values.astype(np.float64)
        maps["close_30s"]  = df_30s["close"].values.astype(np.float64)

    if has_1s:
        maps["high_1s"]  = df_1s["high"].values.astype(np.float64)
        maps["low_1s"]   = df_1s["low"].values.astype(np.float64)
        maps["close_1s"] = df_1s["close"].values.astype(np.float64)
        if has_30s:
            maps["map_30s_1s"] = build_30s_to_1s_map(df_30s, df_1s)
        elif has_1m:
            maps["map_1m_1s"]  = build_1m_to_1s_map(df_1m, df_1s)

    return maps


# ---------------------------------------------------------------------------
# Main simulation orchestrator
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    config: StrategyConfig,
    start_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
    _maps: dict | None = None,
) -> list[TradeResult]:
    """Run the full backtest pipeline.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data before start_date).
        config: Strategy configuration.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
            Data before this date is used for indicator warmup (ATR, etc.)
            but trades are excluded from results.
        df_1m: Optional 1-minute OHLCV DataFrame.
            Enables hierarchical drill-down mode: simulation runs at 5m, drilling
            to 1m only on ambiguous bars (where a single candle simultaneously
            touches two price objectives).
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

    Returns:
        List of TradeResult for each setup candidate (including no-fills).
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
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

        if use_hierarchical:
            from ..data.bar_mapping import (
                build_5m_to_1m_map,
                map_1m_to_5m as _map_1m_to_5m,
            )
            bar_map = build_5m_to_1m_map(df, df_1m)
            map_5m_1m_arr = bar_map
            high_1m   = df_1m["high"].values.astype(np.float64)
            low_1m    = df_1m["low"].values.astype(np.float64)
            close_1m  = df_1m["close"].values.astype(np.float64)
            map_1m_to_5m = _map_1m_to_5m

        if has_30s:
            from ..data.bar_mapping import build_1m_to_30s_map
            map_1m_30s_arr = build_1m_to_30s_map(df_1m, df_30s)
            high_30s  = df_30s["high"].values.astype(np.float64)
            low_30s   = df_30s["low"].values.astype(np.float64)
            close_30s = df_30s["close"].values.astype(np.float64)

        if has_1s:
            high_1s  = df_1s["high"].values.astype(np.float64)
            low_1s   = df_1s["low"].values.astype(np.float64)
            close_1s = df_1s["close"].values.astype(np.float64)
            if has_30s:
                from ..data.bar_mapping import build_30s_to_1s_map
                map_30s_1s_arr = build_30s_to_1s_map(df_30s, df_1s)
            else:
                from ..data.bar_mapping import build_1m_to_1s_map
                map_1m_1s_arr = build_1m_to_1s_map(df_1m, df_1s)

    all_results: list[TradeResult] = []

    for session in config.sessions:
        # Extract candidates (vectorized)
        candidates = _extract_setup_candidates(df, session, config)

        # Compute session masks for entry/flat window boundaries
        masks = compute_session_masks(timestamps, session)

        # Session-aware day boundaries for precomputing bar lookups
        _, session_day_id = compute_session_days(timestamps, session)

        # Pre-compute half-day flat mask for NY
        half_day_set = set(config.half_days) if session.name == "NY" else set()
        date_strs = compute_date_strings(timestamps)

        # Precompute per-session-day bar boundaries (single pass over all bars)
        day_bounds = _precompute_day_boundaries(
            timestamps, masks, half_day_set, date_strs, session_day_id
        )

        # Phase 1: Prepare all candidates (compute trade params + bar boundaries)
        prepared: list[_PreparedCandidate] = []
        for cand in candidates:
            atr = cand.daily_atr
            if np.isnan(atr) or atr <= 0:
                continue

            entry = cand.entry_price
            direction = cand.direction

            # Compute stop, TP1, TP2, BE prices
            stop_dist = (session.stop_atr_pct / 100.0) * atr
            if direction == 1:
                stop = entry - stop_dist
                risk_pts = entry - stop
            else:
                stop = entry + stop_dist
                risk_pts = stop - entry

            if risk_pts <= 0:
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

            if direction == 1:
                tp1 = entry + config.rr * risk_pts * config.tp1_ratio
                tp2 = entry + config.rr * risk_pts
                be = entry
            else:
                tp1 = entry - config.rr * risk_pts * config.tp1_ratio
                tp2 = entry - config.rr * risk_pts
                be = entry

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
                # No flat window found in this session day — check next session day
                next_sd_bounds = day_bounds.get(sd + 1)
                if next_sd_bounds is not None:
                    flat_bar_start = next_sd_bounds["flat_first"]
                if flat_bar_start < 0:
                    flat_bar_start = min(entry_bar_end + 200, n - 1)

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
                half_qty=half_qty,
                is_single=is_single,
                gap_size=cand.gap_size,
                entry_bar_start=entry_bar_start,
                entry_bar_end=entry_bar_end,
                flat_bar_start=flat_bar_start,
                last_bar=last_bar,
                entry_start_1m=entry_start_1m,
                entry_end_1m=entry_end_1m,
                flat_start_1m=flat_start_1m_val,
                last_bar_1m=last_bar_1m_val,
            ))

        # Phase 2: Group by session-day and enforce one-trade-per-day.
        # Pine Script allows both long and short setups to arm, but once
        # any limit order fills (position_size != 0), the other is blocked.
        # We replicate this by scanning fill bars for all candidates in a
        # session-day, then only simulating the one that fills first.
        sd_groups: dict[int, list[_PreparedCandidate]] = defaultdict(list)
        for pc in prepared:
            sd_groups[pc.sd].append(pc)

        def _simulate_and_append(pc: _PreparedCandidate) -> None:
            if use_hierarchical:
                # Hierarchical: 5m primary, 1m drill-down on ambiguous bars,
                # 30s on ambiguous 1m bars (when available), 1s on ambiguous 30s bars
                fill_bar, exit_type, exit_bar, pnl_pts, _, _ = _simulate_single_trade_hierarchical(
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
                )
                # Map 1m indices back to 5m for TradeResult timestamps
                fill_bar = map_1m_to_5m(fill_bar_1m, bar_map) if fill_bar_1m >= 0 else -1
                exit_bar = map_1m_to_5m(exit_bar_1m, bar_map) if exit_bar_1m >= 0 else -1
            else:
                fill_bar, exit_type, exit_bar, pnl_pts, _, _ = _simulate_single_trade(
                    high, low, close,
                    pc.entry_bar_start, pc.entry_bar_end,
                    pc.flat_bar_start, pc.last_bar,
                    pc.direction,
                    pc.entry_price, pc.stop_price, pc.tp1_price, pc.tp2_price, pc.be_price,
                    pc.is_single, pc.qty, pc.half_qty,
                    config.point_value,
                    config.commission_per_contract,
                )
            pnl_usd = pnl_pts * pc.qty * config.point_value
            if exit_type != EXIT_NO_FILL:
                pnl_usd -= 2 * pc.qty * config.commission_per_contract
            r_multiple = pnl_pts / pc.risk_pts if pc.risk_pts > 0 else 0.0
            all_results.append(TradeResult(
                date=pc.cand.date_str, session=session.name,
                direction=pc.direction, signal_bar=pc.cand.signal_bar,
                fill_bar=fill_bar, entry_price=pc.entry_price,
                stop_price=pc.stop_price, tp1_price=pc.tp1_price,
                tp2_price=pc.tp2_price, exit_type=exit_type,
                exit_bar=exit_bar, pnl_points=pnl_pts, pnl_usd=pnl_usd,
                r_multiple=r_multiple, qty=pc.qty, half_qty=pc.half_qty,
                gap_size=pc.gap_size, risk_points=pc.risk_pts,
                fill_time=timestamps[fill_bar].isoformat() if fill_bar >= 0 else "",
                exit_time=timestamps[exit_bar].isoformat() if exit_bar >= 0 else "",
            ))

        def _append_no_fill(pc: _PreparedCandidate) -> None:
            all_results.append(TradeResult(
                date=pc.cand.date_str, session=session.name,
                direction=pc.direction, signal_bar=pc.cand.signal_bar,
                fill_bar=-1, entry_price=pc.entry_price,
                stop_price=pc.stop_price, tp1_price=pc.tp1_price,
                tp2_price=pc.tp2_price, exit_type=EXIT_NO_FILL,
                exit_bar=-1, pnl_points=0.0, pnl_usd=0.0,
                r_multiple=0.0, qty=pc.qty, half_qty=pc.half_qty,
                gap_size=pc.gap_size, risk_points=pc.risk_pts,
                fill_time="", exit_time="",
            ))

        for sd in sorted(sd_groups):
            group = sd_groups[sd]
            if len(group) == 1:
                _simulate_and_append(group[0])
            else:
                # Multiple candidates (long + short) on same session-day.
                # Determine which limit order fills first.
                fill_bars = []
                for pc in group:
                    if use_magnifier and pc.entry_start_1m >= 0:
                        fb_1m = _scan_fill_bar_magnifier(
                            high_1m, low_1m,
                            pc.entry_start_1m, pc.entry_end_1m, pc.last_bar_1m,
                            pc.direction, pc.entry_price,
                        )
                        fb = map_1m_to_5m(fb_1m, bar_map) if fb_1m >= 0 else -1
                    else:
                        fb = _scan_fill_bar(
                            high, low,
                            pc.entry_bar_start, pc.entry_bar_end, pc.last_bar,
                            pc.direction, pc.entry_price,
                        )
                    fill_bars.append((pc, fb))

                filled = [(pc, fb) for pc, fb in fill_bars if fb >= 0]
                if not filled:
                    for pc, _ in fill_bars:
                        _append_no_fill(pc)
                else:
                    # Winner = earliest fill bar (ties: earlier signal_bar wins)
                    winner_pc, _ = min(filled, key=lambda x: (x[1], x[0].cand.signal_bar))
                    _simulate_and_append(winner_pc)
                    for pc, _ in fill_bars:
                        if pc is not winner_pc:
                            _append_no_fill(pc)

    # Sort by date
    all_results.sort(key=lambda t: t.date)

    # Filter out warmup-period trades
    if start_date is not None:
        all_results = [t for t in all_results if t.date >= start_date]

    return all_results
