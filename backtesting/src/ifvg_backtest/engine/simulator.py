"""IFVG reversal trade simulation engine.

State machine per trading day:
    IDLE → WAITING_FOR_GAP → WAITING_FOR_INVERSION → IN_POSITION → IDLE

Entry is at market (bar close) when price inverts through a gap that formed
after a liquidity sweep. Exit logic (TP1/TP2/BE/SL/EOD) reuses the same
partial-profit + breakeven mechanics as the ORB engine.

Matches HEAD_ilm.pine logic faithfully.
"""

from __future__ import annotations

import math
from typing import NamedTuple

import numpy as np
import numba as nb
import pandas as pd

from orb_backtest.engine.simulator import (
    TradeResult,
    EXIT_NO_FILL,
    EXIT_SL,
    EXIT_TP1_TP2,
    EXIT_TP1_BE,
    EXIT_TP1_EOD,
    EXIT_EOD,
    EXIT_TP2_SINGLE,
    EXIT_NAMES,
    _drill_down_1s,
    _drill_down_1m,
)
from orb_backtest.signals.session import (
    _time_in_range,
    compute_trading_days,
    compute_date_strings,
)
from orb_backtest.signals.daily_atr import compute_daily_atr
from orb_backtest.signals.fvg import detect_fvg_no_orb
from orb_backtest.data.bar_mapping import (
    build_5m_to_1m_map,
    build_1m_to_1s_map,
)
from orb_backtest.data.loader import load_1s_for_5m

from ..config import IFVGConfig
from ..signals.liquidity import compute_all_liquidity_levels
from ..signals.sweep import detect_sweeps


# ---------------------------------------------------------------------------
# State constants for the Numba loop
# ---------------------------------------------------------------------------
STATE_IDLE = 0
STATE_WAITING_FOR_GAP = 1
STATE_WAITING_FOR_INVERSION = 2
STATE_WAITING_FOR_LIMIT_FILL = 3
STATE_COLLECTING_GAPS = 4

# Sweep source constants
SRC_NONE = 0
SRC_KZ_HIGH = 1
SRC_KZ_LOW = 2
SRC_PDH = 3
SRC_PDL = 4
SRC_SWING_HIGH = 5
SRC_SWING_LOW = 6

# Direction constants
DIR_LONG = 1
DIR_SHORT = -1

# BPR (Balanced Price Range) filter constants
BPR_NONE = 0
BPR_TIGHT = 1
BPR_LOOSE = 2


# ---------------------------------------------------------------------------
# Numba-compiled exit simulation with hierarchical drill-down
# ---------------------------------------------------------------------------
@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model="numpy")
def _simulate_exit(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    fill_bar: int,
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
    # Drill-down arrays (empty if unavailable)
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    close_1m: np.ndarray,
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    map_main_1m: np.ndarray,
    map_1m_1s: np.ndarray,
    has_1m: bool,
    has_1s: bool,
) -> tuple:
    """Simulate exit from fill_bar onward with hierarchical drill-down.

    Returns: (exit_type, exit_bar, pnl_points)

    On ambiguous bars (SL + TP trigger on same bar), drills down:
      main candle → 1m sub-bars → 1s sub-bars
    to determine which event occurred first.
    """
    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    # Dummy arrays for 30s (IFVG skips 30s tier — goes 1m → 1s directly)
    empty_f64 = np.empty(0, dtype=np.float64)
    empty_i64 = np.empty((0, 2), dtype=np.int64)

    scan_start = fill_bar + 1

    for i in range(scan_start, last_bar + 1):
        is_flat_bar = i >= flat_bar_start

        if direction == 1:  # LONG
            sl_hit = low[i] <= current_stop
            tp1_trigger = high[i] >= tp1_price and not tp1_hit
            tp2_trigger = high[i] >= tp2_price

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close[i] - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                else:
                    pnl_points = close[i] - entry_price
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
                    # Ambiguous — drill down to resolve
                    resolved = False
                    if has_1m and i < len(map_main_1m):
                        s1m = map_main_1m[i, 0]
                        e1m = map_main_1m[i, 1]
                        if e1m > s1m:
                            flat_1m = e1m  # default: no flat within this bar
                            if is_flat_bar:
                                flat_1m = s1m  # entire bar is flat
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1m(
                                high_1m, low_1m, close_1m,
                                empty_f64, empty_f64, empty_f64,  # no 30s
                                high_1s, low_1s, close_1s,
                                empty_i64,  # no map_1m_30s
                                empty_i64,  # no map_30s_1s
                                map_1m_1s,
                                False,  # has_30s
                                has_1s,
                                s1m, e1m, flat_1m,
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            if res:
                                resolved = True
                                return et, i, pnl_points
                    # Direct 1s fallback (when main bars ARE 1m)
                    if not resolved and has_1s and i < len(map_1m_1s):
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
                                return et, i, pnl_points
                    # Fallback: pessimistic — SL wins
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
            sl_hit = high[i] >= current_stop
            tp1_trigger = low[i] <= tp1_price and not tp1_hit
            tp2_trigger = low[i] <= tp2_price

            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close[i]) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                else:
                    pnl_points = entry_price - close[i]
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
                    # Ambiguous — drill down to resolve
                    resolved = False
                    if has_1m and i < len(map_main_1m):
                        s1m = map_main_1m[i, 0]
                        e1m = map_main_1m[i, 1]
                        if e1m > s1m:
                            flat_1m = e1m
                            if is_flat_bar:
                                flat_1m = s1m
                            res, et, pnl_points, tp1_hit, current_stop, remaining_qty = _drill_down_1m(
                                high_1m, low_1m, close_1m,
                                empty_f64, empty_f64, empty_f64,
                                high_1s, low_1s, close_1s,
                                empty_i64,
                                empty_i64,
                                map_1m_1s,
                                False,
                                has_1s,
                                s1m, e1m, flat_1m,
                                direction, entry_price, current_stop,
                                tp1_price, tp2_price, be_price,
                                tp1_hit, is_single, qty, half_qty,
                                remaining_qty, pnl_points,
                            )
                            if res:
                                resolved = True
                                return et, i, pnl_points
                    # Direct 1s fallback (when main bars ARE 1m)
                    if not resolved and has_1s and i < len(map_1m_1s):
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
                                return et, i, pnl_points
                    # Fallback: pessimistic — SL wins
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

    # Reached end of data
    if direction == 1:
        pnl_points = close[last_bar] - entry_price
    else:
        pnl_points = entry_price - close[last_bar]
    return EXIT_EOD, last_bar, pnl_points


# ---------------------------------------------------------------------------
# Numba-compiled daily state machine
# ---------------------------------------------------------------------------
@nb.njit(cache=True, fastmath=True, boundscheck=False, error_model="numpy")
def _simulate_ifvg_day(
    # OHLC arrays (full dataset)
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    # Day boundaries
    day_start: int,
    day_end: int,
    # Session masks (full dataset, bool)
    in_entry: np.ndarray,
    in_flat: np.ndarray,
    # Liquidity levels (full dataset)
    kz_high: np.ndarray,
    kz_low: np.ndarray,
    kz_source: np.ndarray,
    pdh: np.ndarray,
    pdl: np.ndarray,
    # Sweep info (full dataset)
    kz_high_swept: np.ndarray,
    kz_low_swept: np.ndarray,
    pdh_swept: np.ndarray,
    pdl_swept: np.ndarray,
    swing_high_swept: np.ndarray,
    swing_low_swept: np.ndarray,
    kz_high_sweep_bar: np.ndarray,
    kz_low_sweep_bar: np.ndarray,
    pdh_sweep_bar: np.ndarray,
    pdl_sweep_bar: np.ndarray,
    swing_high_sweep_bar: np.ndarray,
    swing_low_sweep_bar: np.ndarray,
    # Swing level values (for checking NaN)
    swing_high: np.ndarray,
    swing_low: np.ndarray,
    # FVG pre-computed (full dataset)
    bull_fvg: np.ndarray,
    bear_fvg: np.ndarray,
    bull_fvg_top: np.ndarray,
    bull_fvg_bottom: np.ndarray,
    bear_fvg_top: np.ndarray,
    bear_fvg_bottom: np.ndarray,
    # Impulse candle data for stops
    high_1: np.ndarray,  # high[bar-1] for each bar
    low_1: np.ndarray,   # low[bar-1] for each bar
    # Daily ATR for minimum stop distance
    daily_atr: np.ndarray,
    min_stop_atr_pct: float,
    # Config scalars
    max_bars_after_sweep: int,
    gap_window_bars: int,
    rr: float,
    tp1_ratio: float,
    risk_usd: float,
    point_value: float,
    min_qty: float,
    qty_step: float,
    be_offset_ticks: int,
    min_tick: float,
    commission: float,
    # Sweep type toggles
    use_kz_high: bool,
    use_kz_low: bool,
    use_pdh: bool,
    use_pdl: bool,
    use_swing_high: bool,
    use_swing_low: bool,
    direction_filter: int,  # 0=both, 1=long only, -1=short only
    min_gap_atr_pct: float,
    entry_type: int,  # 0=market, 1=limit
    require_singular_gap: bool,  # If True, invalidate setup when a 2nd valid gap forms in window
    bpr_filter: int,            # 0=none (price-close), 1=tight, 2=loose
    bpr_tight_max_bars: int,    # max bars between original FVG bar[0] and inverting FVG bar[2]
    max_inversion_bars: int,    # max bars after gap for inversion (0=unlimited)
    # Drill-down arrays for sub-bar resolution
    high_1m: np.ndarray,
    low_1m: np.ndarray,
    close_1m: np.ndarray,
    high_1s: np.ndarray,
    low_1s: np.ndarray,
    close_1s: np.ndarray,
    map_main_1m: np.ndarray,
    map_1m_1s: np.ndarray,
    has_1m: bool,
    has_1s: bool,
) -> nb.typed.List:
    """Simulate one trading day of IFVG strategy.

    Returns a typed list of tuples:
        (signal_bar, fill_bar, direction, entry_price, stop_price, tp1_price,
         tp2_price, exit_type, exit_bar, pnl_points, qty, half_qty, gap_size,
         risk_points, sweep_source)
    """
    results = nb.typed.List()

    # State machine
    state = STATE_IDLE
    sweep_type = 0  # DIR_LONG or DIR_SHORT
    sweep_source = SRC_NONE
    sweep_bar = -1
    bars_after_sweep = 0

    # Gap state
    gap_top = 0.0
    gap_bottom = 0.0
    gap_is_bullish = False
    gap_impulse_high = 0.0
    gap_impulse_low = 0.0
    gap_bar = -1

    # Limit order state (used when entry_type == 1)
    limit_price = 0.0
    limit_direction = 0  # DIR_LONG or DIR_SHORT
    limit_stop = 0.0  # pre-computed stop for the limit order

    # Traded flags (one trade per sweep source per day)
    kz_high_traded = False
    kz_low_traded = False
    pdh_traded = False
    pdl_traded = False
    swing_high_traded = False
    swing_low_traded = False

    be_offset = be_offset_ticks * min_tick

    for i in range(day_start, day_end + 1):
        # ------------------------------------------------------------------
        # Phase: Sweep detection + setup initiation (entry window only)
        # ------------------------------------------------------------------
        if state == STATE_IDLE and in_entry[i]:
            # Check for sweep setups, prioritizing KZ over PD
            # KZ High sweep → bearish setup (SHORT)
            if (use_kz_high and not kz_high_traded
                    and kz_high_swept[i]
                    and not np.isnan(kz_high[i])
                    and kz_high_sweep_bar[i] >= 0
                    and (i - kz_high_sweep_bar[i]) <= gap_window_bars
                    and direction_filter != 1):
                kz_high_traded = True
                state = STATE_WAITING_FOR_GAP
                sweep_type = DIR_SHORT
                sweep_source = SRC_KZ_HIGH
                sweep_bar = kz_high_sweep_bar[i]
                bars_after_sweep = i - kz_high_sweep_bar[i]

            # KZ Low sweep → bullish setup (LONG)
            elif (use_kz_low and not kz_low_traded
                    and kz_low_swept[i]
                    and not np.isnan(kz_low[i])
                    and kz_low_sweep_bar[i] >= 0
                    and (i - kz_low_sweep_bar[i]) <= gap_window_bars
                    and direction_filter != -1):
                kz_low_traded = True
                state = STATE_WAITING_FOR_GAP
                sweep_type = DIR_LONG
                sweep_source = SRC_KZ_LOW
                sweep_bar = kz_low_sweep_bar[i]
                bars_after_sweep = i - kz_low_sweep_bar[i]

            # PDH sweep → bearish setup (SHORT)
            elif (use_pdh and not pdh_traded
                    and pdh_swept[i]
                    and not np.isnan(pdh[i])
                    and pdh_sweep_bar[i] >= 0
                    and (i - pdh_sweep_bar[i]) <= gap_window_bars
                    and direction_filter != 1):
                pdh_traded = True
                state = STATE_WAITING_FOR_GAP
                sweep_type = DIR_SHORT
                sweep_source = SRC_PDH
                sweep_bar = pdh_sweep_bar[i]
                bars_after_sweep = i - pdh_sweep_bar[i]

            # PDL sweep → bullish setup (LONG)
            elif (use_pdl and not pdl_traded
                    and pdl_swept[i]
                    and not np.isnan(pdl[i])
                    and pdl_sweep_bar[i] >= 0
                    and (i - pdl_sweep_bar[i]) <= gap_window_bars
                    and direction_filter != -1):
                pdl_traded = True
                state = STATE_WAITING_FOR_GAP
                sweep_type = DIR_LONG
                sweep_source = SRC_PDL
                sweep_bar = pdl_sweep_bar[i]
                bars_after_sweep = i - pdl_sweep_bar[i]

            # 1H Swing High sweep → bearish setup (SHORT)
            elif (use_swing_high and not swing_high_traded
                    and swing_high_swept[i]
                    and not np.isnan(swing_high[i])
                    and swing_high_sweep_bar[i] >= 0
                    and (i - swing_high_sweep_bar[i]) <= gap_window_bars
                    and direction_filter != 1):
                swing_high_traded = True
                state = STATE_WAITING_FOR_GAP
                sweep_type = DIR_SHORT
                sweep_source = SRC_SWING_HIGH
                sweep_bar = swing_high_sweep_bar[i]
                bars_after_sweep = i - swing_high_sweep_bar[i]

            # 1H Swing Low sweep → bullish setup (LONG)
            elif (use_swing_low and not swing_low_traded
                    and swing_low_swept[i]
                    and not np.isnan(swing_low[i])
                    and swing_low_sweep_bar[i] >= 0
                    and (i - swing_low_sweep_bar[i]) <= gap_window_bars
                    and direction_filter != -1):
                swing_low_traded = True
                state = STATE_WAITING_FOR_GAP
                sweep_type = DIR_LONG
                sweep_source = SRC_SWING_LOW
                sweep_bar = swing_low_sweep_bar[i]
                bars_after_sweep = i - swing_low_sweep_bar[i]

        # ------------------------------------------------------------------
        # Phase: Gap detection
        # ------------------------------------------------------------------
        if state == STATE_WAITING_FOR_GAP and in_entry[i]:
            impulse_bar = i - 1
            gap_within_window = (impulse_bar >= 0
                                 and abs(impulse_bar - sweep_bar) <= gap_window_bars)

            if gap_within_window:
                min_gap = (min_gap_atr_pct / 100.0) * daily_atr[i]

                # For bearish setup (after high sweep): look for BULLISH FVG
                if sweep_type == DIR_SHORT and bull_fvg[i]:
                    g_top = bull_fvg_top[i]
                    g_bottom = bull_fvg_bottom[i]
                    if g_top - g_bottom >= min_gap:
                        gap_top = g_top
                        gap_bottom = g_bottom
                        gap_is_bullish = True
                        gap_impulse_high = high_1[i]  # high of bar[1]
                        gap_impulse_low = low_1[i]    # low of bar[1]
                        gap_bar = i
                        if require_singular_gap:
                            state = STATE_COLLECTING_GAPS
                        else:
                            state = STATE_WAITING_FOR_INVERSION

                # For bullish setup (after low sweep): look for BEARISH FVG
                elif sweep_type == DIR_LONG and bear_fvg[i]:
                    g_top = bear_fvg_top[i]
                    g_bottom = bear_fvg_bottom[i]
                    if g_top - g_bottom >= min_gap:
                        gap_top = g_top
                        gap_bottom = g_bottom
                        gap_is_bullish = False
                        gap_impulse_high = high_1[i]
                        gap_impulse_low = low_1[i]
                        gap_bar = i
                        if require_singular_gap:
                            state = STATE_COLLECTING_GAPS
                        else:
                            state = STATE_WAITING_FOR_INVERSION

        # ------------------------------------------------------------------
        # Phase: Singular gap validation (reject if 2nd gap in window)
        # ------------------------------------------------------------------
        if state == STATE_COLLECTING_GAPS and i > gap_bar:
            impulse_bar_c = i - 1
            still_in_window = (impulse_bar_c >= 0
                               and abs(impulse_bar_c - sweep_bar) <= gap_window_bars)

            if still_in_window:
                min_gap_c = (min_gap_atr_pct / 100.0) * daily_atr[i]
                second_gap_found = False

                if gap_is_bullish and bull_fvg[i]:
                    g2_top = bull_fvg_top[i]
                    g2_bottom = bull_fvg_bottom[i]
                    if g2_top - g2_bottom >= min_gap_c:
                        second_gap_found = True

                if not gap_is_bullish and bear_fvg[i]:
                    g2_top = bear_fvg_top[i]
                    g2_bottom = bear_fvg_bottom[i]
                    if g2_top - g2_bottom >= min_gap_c:
                        second_gap_found = True

                if second_gap_found:
                    # 2nd gap invalidates the setup
                    state = STATE_IDLE
                    sweep_type = 0
                    sweep_source = SRC_NONE
                    sweep_bar = -1
                    bars_after_sweep = 0
                    gap_top = 0.0
                    gap_bottom = 0.0
                    gap_is_bullish = False
                    gap_bar = -1
            else:
                # Window expired with no 2nd gap — proceed to inversion
                state = STATE_WAITING_FOR_INVERSION

        # ------------------------------------------------------------------
        # Phase: Inversion detection + entry (market or limit placement)
        # Inversion must occur on a bar AFTER the gap formed (i > gap_bar)
        # to avoid acting on the same bar the FVG was confirmed.
        #
        # When bpr_filter != BPR_NONE, inversion requires an opposite-direction
        # FVG that overlaps the original gap zone (Balanced Price Range).
        # ------------------------------------------------------------------
        if state == STATE_WAITING_FOR_INVERSION and in_entry[i] and i > gap_bar:
            # Expire if inversion took too many bars after gap formed
            if max_inversion_bars > 0 and (i - gap_bar) > max_inversion_bars:
                state = STATE_IDLE
                sweep_type = 0
                sweep_source = SRC_NONE
                sweep_bar = -1
                bars_after_sweep = 0
                gap_top = 0.0
                gap_bottom = 0.0
                gap_is_bullish = False
                gap_bar = -1
                continue

            entered = False
            inversion_triggered = False
            inversion_is_short = False  # True → SHORT entry, False → LONG entry

            if bpr_filter == BPR_NONE:
                # === Original behavior: price-close inversion ===
                if gap_is_bullish and close[i] < gap_bottom:
                    inversion_triggered = True
                    inversion_is_short = True
                elif not gap_is_bullish and close[i] > gap_top:
                    inversion_triggered = True
                    inversion_is_short = False
            else:
                # === BPR behavior: opposite FVG overlaps original gap ===
                if gap_is_bullish and bear_fvg[i]:
                    # Bearish FVG at bar i overlaps bullish gap [gap_bottom, gap_top]?
                    inv_top = bear_fvg_top[i]
                    inv_bottom = bear_fvg_bottom[i]
                    if inv_top > gap_bottom and inv_bottom < gap_top:
                        if bpr_filter == BPR_TIGHT:
                            if (i - 2) - gap_bar <= bpr_tight_max_bars:
                                inversion_triggered = True
                                inversion_is_short = True
                        else:
                            # BPR_LOOSE
                            inversion_triggered = True
                            inversion_is_short = True

                elif not gap_is_bullish and bull_fvg[i]:
                    # Bullish FVG at bar i overlaps bearish gap [gap_bottom, gap_top]?
                    inv_top = bull_fvg_top[i]
                    inv_bottom = bull_fvg_bottom[i]
                    if inv_top > gap_bottom and inv_bottom < gap_top:
                        if bpr_filter == BPR_TIGHT:
                            if (i - 2) - gap_bar <= bpr_tight_max_bars:
                                inversion_triggered = True
                                inversion_is_short = False
                        else:
                            # BPR_LOOSE
                            inversion_triggered = True
                            inversion_is_short = False

            # === Entry execution (shared for both BPR and price-close) ===
            if inversion_triggered and inversion_is_short:
                # Bullish gap inversion → SHORT
                if entry_type == 0:
                    # ── Market entry at close ──
                    entry_price = close[i]
                    raw_stop = gap_impulse_high
                    min_stop_dist = daily_atr[i] * min_stop_atr_pct
                    if raw_stop - entry_price < min_stop_dist:
                        raw_stop = entry_price + min_stop_dist
                    stop_price = raw_stop
                    risk_pts = stop_price - entry_price

                    if risk_pts > 0:
                        direction = DIR_SHORT
                        qty_raw = risk_usd / (risk_pts * point_value)
                        qty = math.floor(qty_raw / qty_step) * qty_step

                        if qty >= min_qty:
                            is_single = qty <= min_qty
                            if is_single:
                                half_qty = qty
                            else:
                                half_qty = math.floor((qty / 2.0) / qty_step) * qty_step
                                if half_qty < min_qty:
                                    half_qty = min_qty

                            tp1_price = entry_price - (rr * risk_pts * tp1_ratio)
                            tp2_price = entry_price - (rr * risk_pts)
                            be_price = entry_price - be_offset
                            gap_size = gap_top - gap_bottom

                            fill_bar = i
                            signal_bar = gap_bar

                            flat_bar_start = day_end + 1
                            for fb in range(i + 1, day_end + 1):
                                if in_flat[fb]:
                                    flat_bar_start = fb
                                    break

                            exit_type, exit_bar, pnl_pts = _simulate_exit(
                                high, low, close,
                                fill_bar, flat_bar_start, day_end,
                                direction, entry_price, stop_price,
                                tp1_price, tp2_price, be_price,
                                is_single, qty, half_qty,
                                high_1m, low_1m, close_1m,
                                high_1s, low_1s, close_1s,
                                map_main_1m, map_1m_1s,
                                has_1m, has_1s,
                            )

                            results.append((
                                signal_bar, fill_bar, direction,
                                entry_price, stop_price, tp1_price, tp2_price,
                                exit_type, exit_bar, pnl_pts,
                                qty, half_qty, gap_size, risk_pts,
                                sweep_source,
                            ))
                            entered = True

                else:
                    # ── Limit entry: place limit at gap_top ──
                    limit_price = gap_top
                    limit_direction = DIR_SHORT
                    limit_stop = gap_impulse_high
                    state = STATE_WAITING_FOR_LIMIT_FILL

            elif inversion_triggered and not inversion_is_short:
                # Bearish gap inversion → LONG
                if entry_type == 0:
                    # ── Market entry at close ──
                    entry_price = close[i]
                    raw_stop = gap_impulse_low
                    min_stop_dist = daily_atr[i] * min_stop_atr_pct
                    if entry_price - raw_stop < min_stop_dist:
                        raw_stop = entry_price - min_stop_dist
                    stop_price = raw_stop
                    risk_pts = entry_price - stop_price

                    if risk_pts > 0:
                        direction = DIR_LONG
                        qty_raw = risk_usd / (risk_pts * point_value)
                        qty = math.floor(qty_raw / qty_step) * qty_step

                        if qty >= min_qty:
                            is_single = qty <= min_qty
                            if is_single:
                                half_qty = qty
                            else:
                                half_qty = math.floor((qty / 2.0) / qty_step) * qty_step
                                if half_qty < min_qty:
                                    half_qty = min_qty

                            tp1_price = entry_price + (rr * risk_pts * tp1_ratio)
                            tp2_price = entry_price + (rr * risk_pts)
                            be_price = entry_price + be_offset
                            gap_size = gap_top - gap_bottom

                            fill_bar = i
                            signal_bar = gap_bar

                            flat_bar_start = day_end + 1
                            for fb in range(i + 1, day_end + 1):
                                if in_flat[fb]:
                                    flat_bar_start = fb
                                    break

                            exit_type, exit_bar, pnl_pts = _simulate_exit(
                                high, low, close,
                                fill_bar, flat_bar_start, day_end,
                                direction, entry_price, stop_price,
                                tp1_price, tp2_price, be_price,
                                is_single, qty, half_qty,
                                high_1m, low_1m, close_1m,
                                high_1s, low_1s, close_1s,
                                map_main_1m, map_1m_1s,
                                has_1m, has_1s,
                            )

                            results.append((
                                signal_bar, fill_bar, direction,
                                entry_price, stop_price, tp1_price, tp2_price,
                                exit_type, exit_bar, pnl_pts,
                                qty, half_qty, gap_size, risk_pts,
                                sweep_source,
                            ))
                            entered = True

                else:
                    # ── Limit entry: place limit at gap_bottom ──
                    limit_price = gap_bottom
                    limit_direction = DIR_LONG
                    limit_stop = gap_impulse_low
                    state = STATE_WAITING_FOR_LIMIT_FILL

            if entered:
                state = STATE_IDLE
                sweep_type = 0
                sweep_source = SRC_NONE
                sweep_bar = -1
                bars_after_sweep = 0

        # ------------------------------------------------------------------
        # Phase: Limit fill scanning
        # ------------------------------------------------------------------
        if state == STATE_WAITING_FOR_LIMIT_FILL:
            filled = False

            if limit_direction == DIR_SHORT:
                # SHORT limit: fill when price retraces up to gap_top
                if high[i] >= limit_price:
                    # Gap-open slippage: if bar opened above limit, fill at open
                    if open_[i] > limit_price:
                        entry_price = open_[i]
                    else:
                        entry_price = limit_price
                    raw_stop = limit_stop
                    min_stop_dist = daily_atr[i] * min_stop_atr_pct
                    if raw_stop - entry_price < min_stop_dist:
                        raw_stop = entry_price + min_stop_dist
                    stop_price = raw_stop
                    risk_pts = stop_price - entry_price

                    # Same-bar stop check: if high also hit stop, immediate SL
                    if high[i] >= stop_price:
                        # Fill and stop both hit on same bar — record as SL loss
                        pnl_pts = entry_price - stop_price  # negative for short
                        direction = DIR_SHORT
                        qty_raw = risk_usd / (risk_pts * point_value) if risk_pts > 0 else 0.0
                        qty = math.floor(qty_raw / qty_step) * qty_step
                        if qty >= min_qty:
                            results.append((
                                gap_bar, i, direction,
                                entry_price, stop_price, 0.0, 0.0,
                                EXIT_SL, i, pnl_pts,
                                qty, qty, gap_top - gap_bottom, risk_pts,
                                sweep_source,
                            ))
                        filled = False
                        risk_pts = 0.0
                    else:
                        filled = True

            else:  # DIR_LONG
                # LONG limit: fill when price retraces down to gap_bottom
                if low[i] <= limit_price:
                    # Gap-open slippage: if bar opened below limit, fill at open
                    if open_[i] < limit_price:
                        entry_price = open_[i]
                    else:
                        entry_price = limit_price
                    raw_stop = limit_stop
                    min_stop_dist = daily_atr[i] * min_stop_atr_pct
                    if entry_price - raw_stop < min_stop_dist:
                        raw_stop = entry_price - min_stop_dist
                    stop_price = raw_stop
                    risk_pts = entry_price - stop_price

                    # Same-bar stop check: if low also hit stop, immediate SL
                    if low[i] <= stop_price:
                        pnl_pts = stop_price - entry_price  # negative for long
                        direction = DIR_LONG
                        qty_raw = risk_usd / (risk_pts * point_value) if risk_pts > 0 else 0.0
                        qty = math.floor(qty_raw / qty_step) * qty_step
                        if qty >= min_qty:
                            results.append((
                                gap_bar, i, direction,
                                entry_price, stop_price, 0.0, 0.0,
                                EXIT_SL, i, pnl_pts,
                                qty, qty, gap_top - gap_bottom, risk_pts,
                                sweep_source,
                            ))
                        filled = False
                        risk_pts = 0.0
                    else:
                        filled = True

            if filled and risk_pts > 0:
                direction = limit_direction
                qty_raw = risk_usd / (risk_pts * point_value)
                qty = math.floor(qty_raw / qty_step) * qty_step

                if qty >= min_qty:
                    is_single = qty <= min_qty
                    if is_single:
                        half_qty = qty
                    else:
                        half_qty = math.floor((qty / 2.0) / qty_step) * qty_step
                        if half_qty < min_qty:
                            half_qty = min_qty

                    if direction == DIR_SHORT:
                        tp1_price = entry_price - (rr * risk_pts * tp1_ratio)
                        tp2_price = entry_price - (rr * risk_pts)
                        be_price = entry_price - be_offset
                    else:
                        tp1_price = entry_price + (rr * risk_pts * tp1_ratio)
                        tp2_price = entry_price + (rr * risk_pts)
                        be_price = entry_price + be_offset

                    gap_size = gap_top - gap_bottom
                    fill_bar = i
                    signal_bar = gap_bar

                    flat_bar_start = day_end + 1
                    for fb in range(i + 1, day_end + 1):
                        if in_flat[fb]:
                            flat_bar_start = fb
                            break

                    exit_type, exit_bar, pnl_pts = _simulate_exit(
                        high, low, close,
                        fill_bar, flat_bar_start, day_end,
                        direction, entry_price, stop_price,
                        tp1_price, tp2_price, be_price,
                        is_single, qty, half_qty,
                        high_1m, low_1m, close_1m,
                        high_1s, low_1s, close_1s,
                        map_main_1m, map_1m_1s,
                        has_1m, has_1s,
                    )

                    results.append((
                        signal_bar, fill_bar, direction,
                        entry_price, stop_price, tp1_price, tp2_price,
                        exit_type, exit_bar, pnl_pts,
                        qty, half_qty, gap_size, risk_pts,
                        sweep_source,
                    ))

                # Reset after fill (or invalid risk)
                state = STATE_IDLE
                sweep_type = 0
                sweep_source = SRC_NONE
                sweep_bar = -1
                bars_after_sweep = 0

            elif filled:
                # risk_pts <= 0, invalid — cancel
                state = STATE_IDLE
                sweep_type = 0
                sweep_source = SRC_NONE
                sweep_bar = -1
                bars_after_sweep = 0

            # Cancel limit if entry window closes
            elif not in_entry[i]:
                state = STATE_IDLE
                sweep_type = 0
                sweep_source = SRC_NONE
                sweep_bar = -1
                bars_after_sweep = 0

        # ------------------------------------------------------------------
        # Expiration and cutoff
        # ------------------------------------------------------------------
        if state in (STATE_WAITING_FOR_GAP, STATE_WAITING_FOR_INVERSION, STATE_COLLECTING_GAPS):
            bars_after_sweep += 1
            if bars_after_sweep >= max_bars_after_sweep:
                state = STATE_IDLE
                sweep_type = 0
                sweep_source = SRC_NONE
                sweep_bar = -1
                bars_after_sweep = 0

        # Cancel setups after entry window closes
        if not in_entry[i] and state in (STATE_WAITING_FOR_GAP, STATE_WAITING_FOR_INVERSION, STATE_COLLECTING_GAPS):
            state = STATE_IDLE
            sweep_type = 0
            sweep_source = SRC_NONE
            sweep_bar = -1
            bars_after_sweep = 0

    return results


# ---------------------------------------------------------------------------
# High-level backtest runner
# ---------------------------------------------------------------------------

_VALID_CANDLE_TFS = {"1m", "3m", "5m", "15m"}

_TF_RESAMPLE_RULES = {
    "1m": "1min",
    "3m": "3min",
    "5m": "5min",
    "15m": "15min",
}


def _resample_ohlcv(df: pd.DataFrame, target_tf: str) -> pd.DataFrame:
    """Resample OHLCV data to the target timeframe."""
    rule = _TF_RESAMPLE_RULES[target_tf]
    resampled = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    return resampled


def run_backtest(
    df: pd.DataFrame,
    config: IFVGConfig,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
) -> list[TradeResult]:
    """Run the full IFVG backtest pipeline.

    1. Pre-compute: session masks, daily ATR, KZ levels, PDH/PDL, FVGs, sweeps
    2. Group bars by trading day
    3. Call _simulate_ifvg_day() for each day
    4. Collect and finalize TradeResult list

    Args:
        df: OHLCV DataFrame with DatetimeIndex in NY timezone (default 5m).
        config: IFVG strategy configuration.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
        end_date: Exclude trades on or after this date (YYYY-MM-DD).
        df_1m: Optional 1-minute data. Required when candle_tf is not "5m" —
            used as the source for resampling to the target timeframe.

    Returns:
        List of TradeResult for each trade taken.
    """
    # Resample to the configured candle timeframe
    candle_tf = config.candle_tf
    if candle_tf not in _VALID_CANDLE_TFS:
        raise ValueError(f"Invalid candle_tf '{candle_tf}'. Must be one of {_VALID_CANDLE_TFS}")

    if candle_tf == "1m":
        if df_1m is None:
            raise ValueError("df_1m is required when candle_tf='1m'")
        df = df_1m
    elif candle_tf != "5m":
        # 3m and 15m: resample from 1m source for accuracy
        if df_1m is not None:
            df = _resample_ohlcv(df_1m, candle_tf)
        else:
            # Fall back to resampling from 5m (only valid for 15m)
            if candle_tf == "3m":
                raise ValueError("df_1m is required when candle_tf='3m' (cannot resample 5m to 3m)")
            df = _resample_ohlcv(df, candle_tf)

    open_ = np.ascontiguousarray(df["open"].values, dtype=np.float64)
    high = np.ascontiguousarray(df["high"].values, dtype=np.float64)
    low = np.ascontiguousarray(df["low"].values, dtype=np.float64)
    close = np.ascontiguousarray(df["close"].values, dtype=np.float64)
    timestamps = df.index
    n = len(df)

    # ----- Pre-compute signals -----

    # Session masks
    hour = timestamps.hour.values
    minute = timestamps.minute.values
    in_entry = _time_in_range(hour, minute, config.entry_start, config.entry_end)
    in_flat = _time_in_range(hour, minute, config.flat_start, config.flat_end)

    # Daily ATR
    daily_atr = compute_daily_atr(df, config.atr_length)

    # Trading days
    new_day = compute_trading_days(timestamps)
    date_strs = compute_date_strings(timestamps)

    # Liquidity levels (KZ + PDH/PDL + swing pivots)
    kz_specs = [(kz.name, kz.start, kz.end) for kz in config.killzones]
    swing_len = config.swing_length if (config.use_swing_high_sweeps or config.use_swing_low_sweeps) else 0
    liq = compute_all_liquidity_levels(timestamps, high, low, kz_specs, swing_length=swing_len)

    # Sweep detection (including swing high/low)
    sweeps = detect_sweeps(
        high, low,
        liq["kz_high"], liq["kz_low"],
        liq["pdh"], liq["pdl"],
        new_day,
        swing_high=liq["swing_high"],
        swing_low=liq["swing_low"],
    )

    # FVG detection (no ORB filter)
    fvg = detect_fvg_no_orb(
        high, low, daily_atr,
        min_gap_atr_pct=0.0,  # ATR-based min gap applied in state machine
        max_gap_points=0.0,   # No max (ATR-based filtering in state machine)
    )

    # Pre-compute shifted arrays for impulse candle data
    high_1 = np.roll(high, 1)
    low_1 = np.roll(low, 1)
    high_1[0] = np.nan
    low_1[0] = np.nan

    # Build KZ sweep toggle arrays from config
    use_kz_high_sweeps = False
    use_kz_low_sweeps = False
    for kz in config.killzones:
        if kz.use_high_sweeps:
            use_kz_high_sweeps = True
        if kz.use_low_sweeps:
            use_kz_low_sweeps = True

    dir_filter = 0
    if config.direction_filter == "long":
        dir_filter = 1
    elif config.direction_filter == "short":
        dir_filter = -1

    bpr_filter_int = BPR_NONE
    if config.bpr_filter == "tight":
        bpr_filter_int = BPR_TIGHT
    elif config.bpr_filter == "loose":
        bpr_filter_int = BPR_LOOSE

    # ----- Load sub-bar data for drill-down -----
    empty_f64 = np.empty(0, dtype=np.float64)
    empty_map = np.empty((0, 2), dtype=np.int64)

    # 1m data for drill-down (load from the 5m file path)
    has_1m_data = False
    dd_high_1m = empty_f64
    dd_low_1m = empty_f64
    dd_close_1m = empty_f64
    dd_map_main_1m = empty_map

    # 1s data for drill-down
    has_1s_data = False
    dd_high_1s = empty_f64
    dd_low_1s = empty_f64
    dd_close_1s = empty_f64
    dd_map_1m_1s = empty_map

    if config.use_bar_magnifier and config.instrument is not None:
        # Load 1m data for sub-bar resolution
        from orb_backtest.data.loader import load_1m_for_5m
        df_1m_drill = None
        if candle_tf != "1m":
            # Main bars are coarser than 1m — use 1m as first drill-down tier
            try:
                df_1m_drill = load_1m_for_5m(config.instrument.data_file, start=start_date, end=end_date)
            except FileNotFoundError:
                pass
            if df_1m_drill is not None and len(df_1m_drill) > 0:
                has_1m_data = True
                dd_high_1m = np.ascontiguousarray(df_1m_drill["high"].values, dtype=np.float64)
                dd_low_1m = np.ascontiguousarray(df_1m_drill["low"].values, dtype=np.float64)
                dd_close_1m = np.ascontiguousarray(df_1m_drill["close"].values, dtype=np.float64)
                dd_map_main_1m = build_5m_to_1m_map(df, df_1m_drill)

        # Load 1s data (finest tier)
        df_1s_drill = load_1s_for_5m(config.instrument.data_file, start=start_date, end=end_date)
        if df_1s_drill is not None and len(df_1s_drill) > 0:
            has_1s_data = True
            dd_high_1s = np.ascontiguousarray(df_1s_drill["high"].values, dtype=np.float64)
            dd_low_1s = np.ascontiguousarray(df_1s_drill["low"].values, dtype=np.float64)
            dd_close_1s = np.ascontiguousarray(df_1s_drill["close"].values, dtype=np.float64)
            if has_1m_data:
                dd_map_1m_1s = build_1m_to_1s_map(df_1m_drill, df_1s_drill)
            elif candle_tf == "1m":
                # Main bars ARE 1m — map main bars directly to 1s
                # has_1m stays False so drill-down skips the 1m tier
                # and uses the direct 1s path (map_1m_1s maps main→1s)
                dd_map_1m_1s = build_1m_to_1s_map(df, df_1s_drill)

    # ----- Group by trading day and simulate -----
    day_starts = np.where(new_day)[0]
    all_results: list[TradeResult] = []

    # Excluded date set
    excluded_set = set(config.excluded_dates)

    for d_idx in range(len(day_starts)):
        ds = day_starts[d_idx]
        de = day_starts[d_idx + 1] - 1 if d_idx + 1 < len(day_starts) else n - 1

        # Date filtering
        day_str = date_strs[ds]
        if day_str in excluded_set:
            continue
        iso_date = f"{day_str[:4]}-{day_str[4:6]}-{day_str[6:8]}"
        if start_date and iso_date < start_date:
            continue
        if end_date and iso_date >= end_date:
            continue

        # Run day simulation
        day_trades = _simulate_ifvg_day(
            open_, high, low, close,
            ds, de,
            in_entry, in_flat,
            liq["kz_high"], liq["kz_low"], liq["kz_source"],
            liq["pdh"], liq["pdl"],
            sweeps["kz_high_swept"], sweeps["kz_low_swept"],
            sweeps["pdh_swept"], sweeps["pdl_swept"],
            sweeps["swing_high_swept"], sweeps["swing_low_swept"],
            sweeps["kz_high_sweep_bar"], sweeps["kz_low_sweep_bar"],
            sweeps["pdh_sweep_bar"], sweeps["pdl_sweep_bar"],
            sweeps["swing_high_sweep_bar"], sweeps["swing_low_sweep_bar"],
            liq["swing_high"], liq["swing_low"],
            fvg["long_fvg"], fvg["short_fvg"],
            fvg["long_entry_price"], fvg["long_fvg_bottom"],
            fvg["short_fvg_top"], fvg["short_entry_price"],
            high_1, low_1,
            daily_atr,
            config.min_stop_atr_pct,
            config.max_bars_after_sweep,
            config.gap_window_bars,
            config.rr,
            config.tp1_ratio,
            config.risk_usd,
            config.point_value,
            config.min_qty,
            config.qty_step,
            config.be_offset_ticks,
            config.min_tick,
            config.commission_per_contract,
            use_kz_high_sweeps,
            use_kz_low_sweeps,
            config.use_pdh_sweeps,
            config.use_pdl_sweeps,
            config.use_swing_high_sweeps,
            config.use_swing_low_sweeps,
            dir_filter,
            config.min_gap_atr_pct,
            1 if config.entry_type == "limit" else 0,
            config.require_singular_gap,
            bpr_filter_int,
            config.bpr_tight_max_bars,
            config.max_inversion_bars,
            dd_high_1m, dd_low_1m, dd_close_1m,
            dd_high_1s, dd_low_1s, dd_close_1s,
            dd_map_main_1m, dd_map_1m_1s,
            has_1m_data, has_1s_data,
        )

        # Convert raw tuples to TradeResult
        for t in day_trades:
            (signal_bar, fill_bar, direction, entry_price, stop_price,
             tp1_price, tp2_price, exit_type, exit_bar, pnl_pts,
             qty, half_qty, gap_size, risk_pts, sweep_src) = t

            # Compute USD PnL and R-multiple
            if risk_pts > 0:
                r_multiple = pnl_pts / risk_pts
            else:
                r_multiple = 0.0

            pnl_usd = pnl_pts * config.point_value * qty
            # Subtract commission (round-trip: entry + exit)
            comm = config.commission_per_contract * qty * 2
            pnl_usd -= comm

            # Timestamps
            fill_time = str(timestamps[fill_bar]) if fill_bar >= 0 else ""
            exit_time = str(timestamps[exit_bar]) if exit_bar >= 0 else ""

            # All IFVG trades execute during the NY session window
            session_name = "NY"

            all_results.append(TradeResult(
                date=iso_date,
                session=session_name,
                direction=direction,
                signal_bar=signal_bar,
                fill_bar=fill_bar,
                entry_price=entry_price,
                stop_price=stop_price,
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                exit_type=exit_type,
                exit_bar=exit_bar,
                pnl_points=pnl_pts,
                pnl_usd=pnl_usd,
                r_multiple=r_multiple,
                qty=qty,
                half_qty=half_qty,
                gap_size=gap_size,
                risk_points=risk_pts,
                fill_time=fill_time,
                exit_time=exit_time,
            ))

    return all_results
