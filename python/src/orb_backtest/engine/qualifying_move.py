"""Qualifying move engine for inversion shorts.

Extends the inversion strategy with a qualifying move gate: price must first
extend upward to orb_high + (qualifying_move_atr_pct / 100) * daily_atr before
accepting a short inversion entry. This is a mean-reversion concept — fade the
upward move only after it has proven real.

The gate lives inside the candidate extraction loop (not a post-hoc filter)
because the seen_days set limits one trade per session-day. A post-hoc filter
would incorrectly block later valid qualifying trades if an earlier
non-qualifying trade was already emitted.

Only three functions are modified from simulator.py:
- _extract_qm_inversion_candidates: adds qualifying move gate
- _extract_setup_candidates_qm: routes inversion to the QM variant
- run_backtest_qm: calls _extract_setup_candidates_qm
"""

from __future__ import annotations

import math
from collections import defaultdict

import numpy as np
import pandas as pd

from ..config import StrategyConfig, SessionConfig
from ..signals.session import compute_session_masks, compute_session_days, compute_date_strings
from ..signals.daily_atr import compute_daily_atr
from ..signals.orb import compute_orb_levels
from ..signals.fvg import detect_fvg, detect_fvg_no_orb

# Import everything we reuse unchanged from simulator
from .simulator import (
    _SetupCandidate,
    _PreparedCandidate,
    TradeResult,
    EXIT_NO_FILL,
    EXIT_NAMES,
    _simulate_single_trade,
    _simulate_single_trade_magnifier,
    _scan_fill_bar,
    _scan_fill_bar_magnifier,
    _precompute_day_boundaries,
    _extract_cisd_candidates,
    build_maps,
    build_signal_cache,
    _session_key,
    _fvg_key,
)


# ---------------------------------------------------------------------------
# Qualifying-move inversion candidate extraction
# ---------------------------------------------------------------------------

def _extract_qm_inversion_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    valid_long: np.ndarray,
    valid_short: np.ndarray,
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    dates,
    close: np.ndarray,
    session: SessionConfig,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    high: np.ndarray,
    new_session_day: np.ndarray,
    direction_filter: str = "both",
    orb_low: np.ndarray | None = None,
    low: np.ndarray | None = None,
) -> list[_SetupCandidate]:
    """Extract inverted FVG candidates with qualifying move gate.

    Same logic as _extract_inversion_candidates, with one addition:
    when a bullish FVG inversion confirms (producing a SHORT), the session's
    running high must have reached orb_high + (qualifying_move_atr_pct / 100) * ATR.
    When a bearish FVG inversion confirms (producing a LONG), the session's
    running low must have reached orb_low - (qualifying_move_atr_pct / 100) * ATR.

    If not qualified, the candidate is skipped WITHOUT adding to seen_days,
    so a later qualifying trade on the same day can still be taken.

    The qualifying_move_atr_pct comes from session.qualifying_move_atr_pct.
    When 0.0, the gate is disabled (all inversions pass).
    """
    n = len(df)
    candidates: list[_SetupCandidate] = []
    qm_pct = session.qualifying_move_atr_pct

    # Collect all FVGs with their zone boundaries
    long_fvg_bottom = fvg["long_fvg_bottom"]  # high[2] — inversion level for shorts
    short_fvg_top = fvg["short_fvg_top"]       # low[2] — inversion level for longs

    # Direction filter
    take_shorts = direction_filter in ("both", "short")
    take_longs = direction_filter in ("both", "long")

    # Pending FVGs: (fvg_bar, inversion_level, gap_size, atr, sd)
    pending_long: list = []   # bullish FVGs waiting for bearish inversion -> short
    pending_short: list = []  # bearish FVGs waiting for bullish inversion -> long

    seen_days: set = set()  # one inverted signal per session-day

    # Track session running high/low for qualifying move gate
    session_running_high: dict[int, float] = {}  # sd -> max high so far
    session_running_low: dict[int, float] = {}   # sd -> min low so far
    _low = low if low is not None else df["low"].values

    for i in range(n):
        sd = session_day_id[i]

        # Update session running high (track from ORB-ready bars onward)
        if sd not in session_running_high:
            session_running_high[sd] = high[i]
        else:
            if high[i] > session_running_high[sd]:
                session_running_high[sd] = high[i]

        # Update session running low
        if sd not in session_running_low:
            session_running_low[sd] = _low[i]
        else:
            if _low[i] < session_running_low[sd]:
                session_running_low[sd] = _low[i]

        # Register new FVGs as pending (if in entry window)
        if valid_long[i] and take_shorts:  # bullish FVG -> inversion produces short
            pending_long.append((
                i, long_fvg_bottom[i],
                fvg["long_gap_size"][i], daily_atr[i], sd,
            ))

        if valid_short[i] and take_longs:  # bearish FVG -> inversion produces long
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
                # Inversion confirmed — check qualifying move gate for shorts
                if qm_pct > 0.0:
                    orb_h = orb_high[i]
                    if not np.isnan(orb_h) and not np.isnan(atr) and atr > 0:
                        qualifying_level = orb_h + (qm_pct / 100.0) * atr
                        running_high = session_running_high.get(sd, 0.0)
                        if running_high < qualifying_level:
                            # Not qualified — skip but DON'T add to seen_days
                            remaining_long.append(pending)
                            continue

                # Qualified (or gate disabled) — enter SHORT
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
                # Inversion confirmed — check qualifying sweep gate for longs
                if qm_pct > 0.0 and orb_low is not None:
                    orb_l = orb_low[i]
                    if not np.isnan(orb_l) and not np.isnan(atr) and atr > 0:
                        qualifying_level = orb_l - (qm_pct / 100.0) * atr
                        running_low = session_running_low.get(sd, float("inf"))
                        if running_low > qualifying_level:
                            # Not qualified — skip but DON'T add to seen_days
                            remaining_short.append(pending)
                            continue

                # Qualified (or gate disabled) — enter LONG
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


# ---------------------------------------------------------------------------
# Setup candidate extraction with QM routing
# ---------------------------------------------------------------------------

def _extract_setup_candidates_qm(
    df: pd.DataFrame,
    session: SessionConfig,
    config: StrategyConfig,
    _signal_cache: dict | None = None,
) -> list[_SetupCandidate]:
    """Extract setup candidates, routing inversion to QM variant.

    For non-inversion strategies, falls through to the same logic as the
    original _extract_setup_candidates (continuation/reversal/cisd paths
    are copied here to avoid importing private functions).

    Args:
        _signal_cache: Optional pre-computed signal cache from
            :func:`build_signal_cache`. When provided, all signal arrays
            are looked up instead of recomputed — critical for sweeps.
    """
    timestamps = df.index

    if _signal_cache is not None:
        # Fast path: all signals pre-computed — zero recomputation cost.
        skey = _session_key(session)
        fkey = _fvg_key(session, config)
        sc              = _signal_cache["session"][skey]
        masks           = sc["masks"]
        new_session_day = sc["new_session_day"]
        session_day_id  = sc["session_day_id"]
        orb_high        = sc["orb_high"]
        orb_low         = sc["orb_low"]
        orb_ready       = sc["orb_ready"]
        date_strs       = sc["date_strs"]
        daily_atr       = _signal_cache["atr"][config.atr_length]
        fvg             = _signal_cache["fvg"][fkey]
    else:
        # Slow path: compute signals fresh.
        # Session masks
        masks = compute_session_masks(timestamps, session)

        # Session-aware day boundaries
        new_session_day, session_day_id = compute_session_days(timestamps, session)

        # Daily ATR
        daily_atr = compute_daily_atr(df, config.atr_length)

        # ORB levels
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
        )

        # Date strings for excluded dates
        date_strs = compute_date_strings(timestamps)

    excluded = set(config.excluded_dates)

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

    if excluded:
        exclude_arr = np.array(list(excluded))
        exclude_mask = np.isin(date_strs, exclude_arr)
        valid_long &= ~exclude_mask
        valid_short &= ~exclude_mask

    candidates: list[_SetupCandidate] = []
    dates = timestamps.date
    close = df["close"].values
    high = df["high"].values

    if config.strategy == "inversion":
        # Route to qualifying-move inversion extraction
        candidates = _extract_qm_inversion_candidates(
            df, fvg, valid_long, valid_short, session_day_id,
            masks["in_entry"], dates, close, session, daily_atr,
            orb_high, high, new_session_day,
            direction_filter=config.direction_filter,
            orb_low=orb_low,
            low=df["low"].values,
        )
    elif config.strategy == "cisd":
        candidates = _extract_cisd_candidates(
            df, session_day_id,
            masks["in_entry"], masks["in_rth"], orb_ready,
            dates, close, orb_high, orb_low, daily_atr, session,
            direction_filter=config.direction_filter,
            excluded=excluded,
            date_strs=date_strs,
        )
    else:
        # Continuation or reversal mode — same as original
        dir_mult = -1 if config.strategy == "reversal" else 1
        take_longs = config.direction_filter in ("both", "long")
        take_shorts = config.direction_filter in ("both", "short")

        seen_long_days: set = set()
        seen_short_days: set = set()

        for i in range(len(df)):
            sd = session_day_id[i]

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


# ---------------------------------------------------------------------------
# Main simulation orchestrator (QM variant)
# ---------------------------------------------------------------------------

def run_backtest_qm(
    df: pd.DataFrame,
    config: StrategyConfig,
    start_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    _maps: dict | None = None,
    _signal_cache: dict | None = None,
) -> list[TradeResult]:
    """Run the full backtest pipeline with qualifying move gate.

    Identical to run_backtest() except it calls _extract_setup_candidates_qm()
    which routes inversion strategies through the qualifying move gate.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data before start_date).
        config: Strategy configuration.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
        df_1m: Optional 1-minute OHLCV DataFrame for bar magnifier mode.
        _maps: Optional pre-built maps dict from :func:`build_maps`. When
            provided, skips bar-map construction entirely. Build once with
            ``maps = build_maps(df, df_1m, None, None)`` and pass as
            ``_maps=maps``.
        _signal_cache: Optional pre-computed signal cache from
            :func:`build_signal_cache`. When provided, skips all signal
            recomputation. Build once with
            ``cache = build_signal_cache(df, configs)`` and pass as
            ``_signal_cache=cache``.

    Returns:
        List of TradeResult for each setup candidate (including no-fills).
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    timestamps = df.index
    n = len(df)

    # Build maps if not pre-supplied (fast path: use _maps from build_maps)
    if _maps is None:
        _maps = build_maps(df, df_1m, None, None)

    # Build signal cache if not pre-supplied
    if _signal_cache is None:
        _signal_cache = build_signal_cache(df, [config])

    # Bar magnifier setup — use pre-built maps when available
    from ..data.bar_mapping import map_1m_to_5m as _map_1m_to_5m
    use_magnifier = config.use_bar_magnifier and _maps["has_1m"]
    if use_magnifier:
        bar_map = _maps["map_5m_1m"]
        high_1m = _maps["high_1m"]
        low_1m = _maps["low_1m"]
        close_1m = _maps["close_1m"]
        map_1m_to_5m = _map_1m_to_5m
    else:
        bar_map = None
        high_1m = low_1m = close_1m = None
        map_1m_to_5m = None

    all_results: list[TradeResult] = []

    for session in config.sessions:
        # Extract candidates using QM-aware extraction
        candidates = _extract_setup_candidates_qm(df, session, config, _signal_cache=_signal_cache)

        # Compute session masks for entry/flat window boundaries
        masks = compute_session_masks(timestamps, session)

        # Session-aware day boundaries
        _, session_day_id = compute_session_days(timestamps, session)

        # Pre-compute half-day flat mask for NY
        half_day_set = set(config.half_days) if session.name == "NY" else set()
        date_strs = compute_date_strings(timestamps)

        # Precompute per-session-day bar boundaries
        day_bounds = _precompute_day_boundaries(
            timestamps, masks, half_day_set, date_strs, session_day_id
        )

        # Phase 1: Prepare all candidates
        prepared: list[_PreparedCandidate] = []
        for cand in candidates:
            atr = cand.daily_atr
            if np.isnan(atr) or atr <= 0:
                continue

            entry = cand.entry_price
            direction = cand.direction

            stop_dist = (session.stop_atr_pct / 100.0) * atr
            if direction == 1:
                stop = entry - stop_dist
                risk_pts = entry - stop
            else:
                stop = entry + stop_dist
                risk_pts = stop - entry

            if risk_pts <= 0:
                continue

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

            sd = session_day_id[cand.signal_bar]
            entry_bar_start = cand.signal_bar + 1

            bounds = day_bounds.get(sd)
            if bounds is None:
                continue

            entry_bar_end = bounds["entry_last"]
            if entry_bar_end < 0 or entry_bar_end < entry_bar_start:
                continue

            flat_bar_start = bounds["flat_first"]
            if flat_bar_start < 0:
                next_sd_bounds = day_bounds.get(sd + 1)
                if next_sd_bounds is not None:
                    flat_bar_start = next_sd_bounds["flat_first"]
                if flat_bar_start < 0:
                    flat_bar_start = min(entry_bar_end + 200, n - 1)

            last_bar = min(flat_bar_start + 20, n - 1)

            # Translate 5m boundaries to 1m indices for bar magnifier
            entry_start_1m = -1
            entry_end_1m = -1
            flat_start_1m_val = -1
            last_bar_1m_val = -1
            if use_magnifier:
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

        # Phase 2: Group by session-day and enforce one-trade-per-day
        sd_groups: dict[int, list[_PreparedCandidate]] = defaultdict(list)
        for pc in prepared:
            sd_groups[pc.sd].append(pc)

        def _simulate_and_append(pc: _PreparedCandidate) -> None:
            if use_magnifier and pc.entry_start_1m >= 0:
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


# ---------------------------------------------------------------------------
# No-ORB liquidity sweep inversion candidate extraction
# ---------------------------------------------------------------------------

def _extract_no_orb_inversion_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    session_day_id: np.ndarray,
    in_entry: np.ndarray,
    dates,
    close: np.ndarray,
    session: SessionConfig,
    daily_atr: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    direction_filter: str = "both",
) -> list[_SetupCandidate]:
    """Extract inversion candidates without any ORB reference.

    Instead of measuring the liquidity sweep from orb_high/orb_low, uses the
    session's running opposite extreme:
    - For SHORT: session running high must reach session_running_low + qm_pct% ATR
      (price rose X% ATR from session low before being faded short)
    - For LONG: session running low must reach session_running_high - qm_pct% ATR
      (price fell X% ATR from session high before being faded long)

    This lets any significant intraday sweep trigger an inversion, regardless of
    where the opening range was established.
    """
    n = len(df)
    candidates: list[_SetupCandidate] = []
    qm_pct = session.qualifying_move_atr_pct

    long_fvg_bottom = fvg["long_fvg_bottom"]
    short_fvg_top = fvg["short_fvg_top"]

    take_shorts = direction_filter in ("both", "short")
    take_longs = direction_filter in ("both", "long")

    pending_long: list = []   # bullish FVGs → potential SHORT inversions
    pending_short: list = []  # bearish FVGs → potential LONG inversions

    seen_days: set = set()

    # Track session running high and low from first bar of each session-day
    session_running_high: dict[int, float] = {}
    session_running_low: dict[int, float] = {}

    for i in range(n):
        sd = session_day_id[i]

        # Update session running extremes
        if sd not in session_running_high:
            session_running_high[sd] = high[i]
            session_running_low[sd] = low[i]
        else:
            if high[i] > session_running_high[sd]:
                session_running_high[sd] = high[i]
            if low[i] < session_running_low[sd]:
                session_running_low[sd] = low[i]

        if not in_entry[i]:
            # Still register FVGs so we track them, but only in entry window
            # Clean stale pending from prior days
            pending_long = [p for p in pending_long if p[4] >= sd]
            pending_short = [p for p in pending_short if p[4] >= sd]
            continue

        # Register new bullish FVGs as pending shorts
        if not np.isnan(long_fvg_bottom[i]) and take_shorts:
            pending_long.append((
                i, long_fvg_bottom[i],
                fvg["long_gap_size"][i], daily_atr[i], sd,
            ))

        # Register new bearish FVGs as pending longs
        if not np.isnan(short_fvg_top[i]) and take_longs:
            pending_short.append((
                i, short_fvg_top[i],
                fvg["short_gap_size"][i], daily_atr[i], sd,
            ))

        # Check pending bullish FVGs for bearish inversion (close below FVG bottom → SHORT)
        remaining_long = []
        for pending in pending_long:
            fvg_bar, inversion_level, gap_size, atr, fvg_sd = pending

            if sd != fvg_sd or i <= fvg_bar:
                remaining_long.append(pending)
                continue

            if close[i] < inversion_level and sd not in seen_days:
                if qm_pct > 0.0 and not np.isnan(atr) and atr > 0:
                    # Qualifying: session high must be >= session low + qm_pct% ATR
                    sess_low = session_running_low.get(sd, float("inf"))
                    qualifying_level = sess_low + (qm_pct / 100.0) * atr
                    sess_high = session_running_high.get(sd, 0.0)
                    if sess_high < qualifying_level:
                        remaining_long.append(pending)
                        continue

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

        # Check pending bearish FVGs for bullish inversion (close above FVG top → LONG)
        remaining_short = []
        for pending in pending_short:
            fvg_bar, inversion_level, gap_size, atr, fvg_sd = pending

            if sd != fvg_sd or i <= fvg_bar:
                remaining_short.append(pending)
                continue

            if close[i] > inversion_level and sd not in seen_days:
                if qm_pct > 0.0 and not np.isnan(atr) and atr > 0:
                    # Qualifying: session low must be <= session high - qm_pct% ATR
                    sess_high = session_running_high.get(sd, 0.0)
                    qualifying_level = sess_high - (qm_pct / 100.0) * atr
                    sess_low = session_running_low.get(sd, float("inf"))
                    if sess_low > qualifying_level:
                        remaining_short.append(pending)
                        continue

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

        # Clean stale pending from prior days
        pending_long = [p for p in pending_long if p[4] >= sd]
        pending_short = [p for p in pending_short if p[4] >= sd]

    return candidates


def _extract_setup_candidates_no_orb(
    df: pd.DataFrame,
    session: SessionConfig,
    config: StrategyConfig,
) -> list[_SetupCandidate]:
    """Extract inversion candidates using no-ORB liquidity sweep logic."""
    timestamps = df.index
    masks = compute_session_masks(timestamps, session)
    new_session_day, session_day_id = compute_session_days(timestamps, session)
    daily_atr = compute_daily_atr(df, config.atr_length)

    fvg = detect_fvg_no_orb(
        df["high"].values,
        df["low"].values,
        daily_atr,
        session.min_gap_atr_pct,
        session.max_gap_points,
        max_gap_atr_pct=getattr(session, "max_gap_atr_pct", 0.0),
    )

    date_strs = compute_date_strings(timestamps)
    excluded = set(config.excluded_dates)

    # Both long and short FVGs are valid anywhere in the entry window
    valid_long = masks["in_entry"] & masks["in_rth"]
    valid_short = masks["in_entry"] & masks["in_rth"]

    if excluded:
        exclude_arr = np.array(list(excluded))
        exclude_mask = np.isin(date_strs, exclude_arr)
        valid_long &= ~exclude_mask
        valid_short &= ~exclude_mask

    # Apply validity to FVG arrays
    fvg_filtered = {
        "long_fvg_bottom": np.where(valid_long, fvg["long_fvg_bottom"], np.nan),
        "short_fvg_top": np.where(valid_short, fvg["short_fvg_top"], np.nan),
        "long_gap_size": np.where(valid_long, fvg["long_gap_size"], np.nan),
        "short_gap_size": np.where(valid_short, fvg["short_gap_size"], np.nan),
    }

    return _extract_no_orb_inversion_candidates(
        df, fvg_filtered, session_day_id,
        masks["in_entry"], timestamps.date,
        df["close"].values, session, daily_atr,
        df["high"].values, df["low"].values,
        direction_filter=config.direction_filter,
    )


def run_backtest_no_orb(
    df: pd.DataFrame,
    config: StrategyConfig,
    start_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
) -> list[TradeResult]:
    """Run backtest with no-ORB liquidity sweep inversion logic.

    Identical pipeline to run_backtest_qm() but uses _extract_setup_candidates_no_orb()
    which detects FVG inversions anywhere in the session, with the qualifying sweep
    measured from the session's running opposite extreme rather than the ORB level.
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    close = df["close"].values.astype(np.float64)
    timestamps = df.index
    n = len(df)

    use_magnifier = config.use_bar_magnifier and df_1m is not None
    bar_map = None
    high_1m = low_1m = close_1m = None
    map_1m_to_5m = None
    if use_magnifier:
        from ..data.bar_mapping import build_5m_to_1m_map, map_1m_to_5m as _map_1m_to_5m
        bar_map = build_5m_to_1m_map(df, df_1m)
        high_1m = df_1m["high"].values.astype(np.float64)
        low_1m = df_1m["low"].values.astype(np.float64)
        close_1m = df_1m["close"].values.astype(np.float64)
        map_1m_to_5m = _map_1m_to_5m

    all_results: list[TradeResult] = []

    for session in config.sessions:
        candidates = _extract_setup_candidates_no_orb(df, session, config)

        masks = compute_session_masks(timestamps, session)
        _, session_day_id = compute_session_days(timestamps, session)
        half_day_set = set(config.half_days) if session.name == "NY" else set()
        date_strs = compute_date_strings(timestamps)

        day_bounds = _precompute_day_boundaries(
            timestamps, masks, half_day_set, date_strs, session_day_id
        )

        prepared: list[_PreparedCandidate] = []
        for cand in candidates:
            atr = cand.daily_atr
            if np.isnan(atr) or atr <= 0:
                continue

            entry = cand.entry_price
            direction = cand.direction

            stop_dist = (session.stop_atr_pct / 100.0) * atr
            if direction == 1:
                stop = entry - stop_dist
                risk_pts = entry - stop
            else:
                stop = entry + stop_dist
                risk_pts = stop - entry

            if risk_pts <= 0:
                continue

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

            sd = session_day_id[cand.signal_bar]
            entry_bar_start = cand.signal_bar + 1

            bounds = day_bounds.get(sd)
            if bounds is None:
                continue

            entry_bar_end = bounds["entry_last"]
            if entry_bar_end < 0 or entry_bar_end < entry_bar_start:
                continue

            flat_bar_start = bounds["flat_first"]
            if flat_bar_start < 0:
                next_sd_bounds = day_bounds.get(sd + 1)
                if next_sd_bounds is not None:
                    flat_bar_start = next_sd_bounds["flat_first"]
                if flat_bar_start < 0:
                    flat_bar_start = min(entry_bar_end + 200, n - 1)

            last_bar = min(flat_bar_start + 20, n - 1)

            entry_start_1m = entry_end_1m = flat_start_1m_val = last_bar_1m_val = -1
            if use_magnifier:
                entry_start_1m = bar_map[entry_bar_start, 0]
                entry_end_1m = bar_map[min(entry_bar_end, len(bar_map) - 1), 1] - 1
                flat_start_1m_val = bar_map[min(flat_bar_start, len(bar_map) - 1), 0]
                last_bar_1m_val = bar_map[min(last_bar, len(bar_map) - 1), 1] - 1

            prepared.append(_PreparedCandidate(
                cand=cand, sd=sd, direction=direction,
                entry_price=entry, stop_price=stop,
                tp1_price=tp1, tp2_price=tp2, be_price=be,
                risk_pts=risk_pts, qty=qty, half_qty=half_qty,
                is_single=is_single, gap_size=cand.gap_size,
                entry_bar_start=entry_bar_start, entry_bar_end=entry_bar_end,
                flat_bar_start=flat_bar_start, last_bar=last_bar,
                entry_start_1m=entry_start_1m, entry_end_1m=entry_end_1m,
                flat_start_1m=flat_start_1m_val, last_bar_1m=last_bar_1m_val,
            ))

        sd_groups: dict[int, list[_PreparedCandidate]] = defaultdict(list)
        for pc in prepared:
            sd_groups[pc.sd].append(pc)

        def _simulate_and_append(pc: _PreparedCandidate) -> None:
            if use_magnifier and pc.entry_start_1m >= 0:
                fill_bar_1m, exit_type, exit_bar_1m, pnl_pts, _, _ = _simulate_single_trade_magnifier(
                    high_1m, low_1m, close_1m,
                    pc.entry_start_1m, pc.entry_end_1m,
                    pc.flat_start_1m, pc.last_bar_1m,
                    pc.direction, pc.entry_price, pc.stop_price,
                    pc.tp1_price, pc.tp2_price, pc.be_price,
                    pc.is_single, pc.qty, pc.half_qty,
                    config.point_value, config.commission_per_contract,
                )
                fill_bar = map_1m_to_5m(fill_bar_1m, bar_map) if fill_bar_1m >= 0 else -1
                exit_bar = map_1m_to_5m(exit_bar_1m, bar_map) if exit_bar_1m >= 0 else -1
            else:
                fill_bar, exit_type, exit_bar, pnl_pts, _, _ = _simulate_single_trade(
                    high, low, close,
                    pc.entry_bar_start, pc.entry_bar_end,
                    pc.flat_bar_start, pc.last_bar,
                    pc.direction, pc.entry_price, pc.stop_price,
                    pc.tp1_price, pc.tp2_price, pc.be_price,
                    pc.is_single, pc.qty, pc.half_qty,
                    config.point_value, config.commission_per_contract,
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
                    winner_pc, _ = min(filled, key=lambda x: (x[1], x[0].cand.signal_bar))
                    _simulate_and_append(winner_pc)
                    for pc, _ in fill_bars:
                        if pc is not winner_pc:
                            _append_no_fill(pc)

    all_results.sort(key=lambda t: t.date)
    if start_date is not None:
        all_results = [t for t in all_results if t.date >= start_date]

    return all_results
