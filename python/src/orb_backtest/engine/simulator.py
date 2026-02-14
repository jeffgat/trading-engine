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

from ..config import StrategyConfig, SessionConfig
from ..signals.session import compute_session_masks, compute_trading_days, compute_date_strings
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
    new_day = compute_trading_days(timestamps)

    # Daily ATR
    daily_atr = compute_daily_atr(df, config.atr_length)

    # ORB levels
    orb_high, orb_low, orb_ready = compute_orb_levels(
        df, masks["in_orb"], masks["in_rth"], new_day
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

    # Exclude specific dates
    if excluded:
        exclude_mask = np.array([d in excluded for d in date_strs])
        valid_long &= ~exclude_mask
        valid_short &= ~exclude_mask

    # Group by trading day, take first FVG per direction
    candidates: list[_SetupCandidate] = []
    dates = timestamps.date

    # Track which days already have a signal
    seen_long_days: set = set()
    seen_short_days: set = set()

    for i in range(len(df)):
        d = dates[i]

        if valid_long[i] and d not in seen_long_days:
            seen_long_days.add(d)
            candidates.append(_SetupCandidate(
                date_str=str(d),
                session=session.name,
                direction=1,
                signal_bar=i,
                entry_price=fvg["long_entry_price"][i],
                gap_size=fvg["long_gap_size"][i],
                daily_atr=daily_atr[i],
            ))

        if valid_short[i] and d not in seen_short_days:
            seen_short_days.add(d)
            candidates.append(_SetupCandidate(
                date_str=str(d),
                session=session.name,
                direction=-1,
                signal_bar=i,
                entry_price=fvg["short_entry_price"][i],
                gap_size=fvg["short_gap_size"][i],
                daily_atr=daily_atr[i],
            ))

    return candidates


def _find_bar_index(timestamps: pd.DatetimeIndex, in_mask: np.ndarray, date, find_last: bool = False) -> int:
    """Find the first (or last) bar index matching a date and mask condition."""
    date_match = timestamps.date == date
    combined = date_match & in_mask
    indices = np.where(combined)[0]
    if len(indices) == 0:
        return -1
    return int(indices[-1]) if find_last else int(indices[0])


# ---------------------------------------------------------------------------
# Main simulation orchestrator
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    config: StrategyConfig,
) -> list[TradeResult]:
    """Run the full backtest pipeline.

    Args:
        df: 5-minute OHLCV DataFrame.
        config: Strategy configuration.

    Returns:
        List of TradeResult for each setup candidate (including no-fills).
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    timestamps = df.index
    n = len(df)

    all_results: list[TradeResult] = []

    for session in config.sessions:
        # Extract candidates (vectorized)
        candidates = _extract_setup_candidates(df, session, config)

        # Compute session masks for entry/flat window boundaries
        masks = compute_session_masks(timestamps, session)

        # Pre-compute half-day flat mask for NY
        half_day_set = set(config.half_days) if session.name == "NY" else set()
        date_strs = compute_date_strings(timestamps)

        # Simulate each candidate
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
                be = entry + config.be_offset
            else:
                tp1 = entry - config.rr * risk_pts * config.tp1_ratio
                tp2 = entry - config.rr * risk_pts
                be = entry - config.be_offset

            # Find entry window and flat window boundaries for this day
            cand_date = pd.Timestamp(cand.date_str).date()

            # Entry starts on bar AFTER the signal bar (matching bar_index > setupBar)
            entry_bar_start = cand.signal_bar + 1

            # Find last bar in entry window for this day
            entry_bar_end = _find_bar_index(timestamps, masks["in_entry"], cand_date, find_last=True)
            if entry_bar_end < 0 or entry_bar_end < entry_bar_start:
                continue

            # Find flat window start bar
            # For half-days (NY only), use earlier flat time
            is_half_day = False
            if half_day_set:
                cand_date_str = cand_date.strftime("%Y%m%d")
                is_half_day = cand_date_str in half_day_set

            if is_half_day:
                # Half-day flat: 12:50-13:00 — find first bar with time >= 12:50
                flat_bar_start = -1
                for fb in range(entry_bar_start, min(n, entry_bar_end + 100)):
                    if timestamps[fb].date() != cand_date:
                        break
                    if timestamps[fb].hour == 12 and timestamps[fb].minute >= 50:
                        flat_bar_start = fb
                        break
                    if timestamps[fb].hour > 12:
                        flat_bar_start = fb
                        break
                if flat_bar_start < 0:
                    flat_bar_start = entry_bar_end
            else:
                flat_bar_start = _find_bar_index(timestamps, masks["in_flat"], cand_date)
                if flat_bar_start < 0:
                    # No flat window found — use a bar far in the future
                    # This can happen for cross-midnight sessions
                    # Look for flat window on the NEXT calendar day
                    import datetime
                    next_date = cand_date + datetime.timedelta(days=1)
                    flat_bar_start = _find_bar_index(timestamps, masks["in_flat"], next_date)
                    if flat_bar_start < 0:
                        flat_bar_start = min(entry_bar_end + 200, n - 1)

            # Last bar for scanning (end of RTH or end of data)
            last_bar = min(flat_bar_start + 20, n - 1)  # buffer past flat window

            # Run numba-compiled simulation
            fill_bar, exit_type, exit_bar, pnl_pts, _, _ = _simulate_single_trade(
                high, low, close,
                entry_bar_start, entry_bar_end,
                flat_bar_start, last_bar,
                direction,
                entry, stop, tp1, tp2, be,
                is_single, qty, half_qty,
                config.point_value,
                config.commission_per_contract,
            )

            # Calculate USD PnL
            pnl_usd = pnl_pts * qty * config.point_value

            # Subtract commission (round-trip: entry + exit, per contract)
            if exit_type != EXIT_NO_FILL:
                commission_total = 2 * qty * config.commission_per_contract
                pnl_usd -= commission_total

            # R-multiple
            r_multiple = pnl_pts / risk_pts if risk_pts > 0 else 0.0

            all_results.append(TradeResult(
                date=cand.date_str,
                session=session.name,
                direction=direction,
                signal_bar=cand.signal_bar,
                fill_bar=fill_bar,
                entry_price=entry,
                stop_price=stop,
                tp1_price=tp1,
                tp2_price=tp2,
                exit_type=exit_type,
                exit_bar=exit_bar,
                pnl_points=pnl_pts,
                pnl_usd=pnl_usd,
                r_multiple=r_multiple,
                qty=qty,
                half_qty=half_qty,
                gap_size=cand.gap_size,
                risk_points=risk_pts,
            ))

    # Sort by date
    all_results.sort(key=lambda t: t.date)
    return all_results
