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

    # Track which session days already have a signal
    seen_long_days: set = set()
    seen_short_days: set = set()

    for i in range(len(df)):
        sd = session_day_id[i]

        if valid_long[i] and sd not in seen_long_days:
            seen_long_days.add(sd)
            candidates.append(_SetupCandidate(
                date_str=str(dates[i]),
                session=session.name,
                direction=1,
                signal_bar=i,
                entry_price=fvg["long_entry_price"][i],
                gap_size=fvg["long_gap_size"][i],
                daily_atr=daily_atr[i],
            ))

        if valid_short[i] and sd not in seen_short_days:
            seen_short_days.add(sd)
            candidates.append(_SetupCandidate(
                date_str=str(dates[i]),
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
# Main simulation orchestrator
# ---------------------------------------------------------------------------

def run_backtest(
    df: pd.DataFrame,
    config: StrategyConfig,
    start_date: str | None = None,
) -> list[TradeResult]:
    """Run the full backtest pipeline.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data before start_date).
        config: Strategy configuration.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
            Data before this date is used for indicator warmup (ATR, etc.)
            but trades are excluded from results.

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
                be = entry + config.be_offset
            else:
                tp1 = entry - config.rr * risk_pts * config.tp1_ratio
                tp2 = entry - config.rr * risk_pts
                be = entry - config.be_offset

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
