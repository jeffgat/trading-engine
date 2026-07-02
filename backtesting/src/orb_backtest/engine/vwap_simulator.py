"""VWAP Reversion trade simulation engine.

Hybrid approach (mirrors the ORB engine):
1. Vectorized signal generation produces _VWAPSetupCandidate records
2. Numba-compiled loop simulates exits per candidate (reuses ORB engine Numba functions)

The ONLY difference from the ORB engine is signal generation: VWAP deviation +
rejection candle detection instead of ORB + FVG.  Trade simulation (fill scanning,
SL/TP1/TP2/BE/EOD exits) is IDENTICAL and reused directly from simulator.py.
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from ..vwap_config import VWAPStrategyConfig, VWAPSessionConfig
from ..signals.vwap import (
    compute_session_vwap,
    compute_vwap_std_bands,
    detect_deviation,
    detect_rejection_candles,
)
from ..signals.session import (
    compute_session_days,
    compute_date_strings,
)
from ..signals.daily_atr import compute_daily_atr

# Reuse ALL trade simulation machinery from the ORB engine
from .simulator import (
    TradeResult,
    EXIT_NO_FILL,
    EXIT_SL,
    EXIT_TP1_TP2,
    EXIT_TP1_BE,
    EXIT_TP1_EOD,
    EXIT_EOD,
    EXIT_TP2_SINGLE,
    EXIT_NAMES,
    _simulate_single_trade_hierarchical,
    _simulate_single_trade,
    _scan_fill_bar,
    build_maps,
    _resolve_time,
    _precompute_day_boundaries,
)


# ---------------------------------------------------------------------------
# VWAP-specific session mask computation
# ---------------------------------------------------------------------------

def _compute_vwap_session_masks(
    timestamps: pd.DatetimeIndex,
    session: VWAPSessionConfig,
) -> dict[str, np.ndarray]:
    """Compute boolean masks for a VWAP session's time windows.

    Unlike ORB sessions, VWAP sessions have no ORB window.  The RTH span
    runs from ``entry_start`` to ``flat_end``.

    Returns:
        Dict with keys:
            'in_entry': True during entry window
            'in_flat': True during flat/EOD window
            'in_rth': True during regular trading hours (entry_start -> flat_end)
    """
    from ..signals.session import _time_in_range

    hour = timestamps.hour.values
    minute = timestamps.minute.values

    in_entry = _time_in_range(hour, minute, session.entry_start, session.entry_end)
    in_flat = _time_in_range(hour, minute, session.flat_start, session.flat_end)

    # RTH spans from session_open (or entry_start) to flat_end
    session_open = session.session_open or session.entry_start
    in_rth = _time_in_range(hour, minute, session_open, session.flat_end)

    return {
        "in_entry": in_entry,
        "in_flat": in_flat,
        "in_rth": in_rth,
    }


def _compute_vwap_session_days(
    timestamps: pd.DatetimeIndex,
    session: VWAPSessionConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute session-aware day boundaries for a VWAP session.

    Delegates to the shared ``compute_session_days()`` but creates a
    lightweight shim object so the function can read ``orb_start`` (mapped
    to ``entry_start``) and ``flat_end``.
    """

    class _Shim:
        """Duck-typed stand-in accepted by ``compute_session_days``."""

        def __init__(self, vwap_session: VWAPSessionConfig) -> None:
            # session_days needs orb_start (session open) and flat_end
            self.orb_start = vwap_session.session_open or vwap_session.entry_start
            self.rth_start = self.orb_start
            self.flat_end = vwap_session.flat_end

    shim = _Shim(session)
    return compute_session_days(timestamps, shim)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Internal VWAP setup candidate
# ---------------------------------------------------------------------------

@dataclass
class _VWAPSetupCandidate:
    """Internal record for a VWAP reversion signal, ready for trade simulation."""

    date_str: str
    session: str
    direction: int  # +1 long (fade below VWAP), -1 short (fade above VWAP)
    signal_bar: int  # bar index of the rejection candle
    entry_bar: int  # first executable bar after the rejection candle
    entry_price: float  # next executable bar open after the rejection candle
    stop_price: float  # candle extreme + optional ATR buffer
    vwap_at_signal: float  # VWAP value at signal bar
    daily_atr: float


# ---------------------------------------------------------------------------
# Vectorized helper: first valid bar per session-day
# ---------------------------------------------------------------------------

def _first_per_day(valid_mask: np.ndarray, session_day_id: np.ndarray) -> np.ndarray:
    """Return indices of first True bar per session-day (vectorized)."""
    indices = np.where(valid_mask)[0]
    if len(indices) == 0:
        return indices
    day_ids = session_day_id[indices]
    _, first_idx = np.unique(day_ids, return_index=True)
    return indices[first_idx]


# ---------------------------------------------------------------------------
# Signal cache key
# ---------------------------------------------------------------------------

def _vwap_session_key(session: VWAPSessionConfig) -> tuple:
    """Hashable key identifying a VWAP session's time windows."""
    return (
        session.name,
        session.session_open,
        session.entry_start,
        session.entry_end,
        session.flat_start,
        session.flat_end,
    )


def _vwap_signal_key(session: VWAPSessionConfig, config: VWAPStrategyConfig) -> tuple:
    """Hashable key for VWAP signal caching.

    Two configs with identical signal-determining params will produce
    identical candidate lists, so only trade-level params (rr, tp1_ratio,
    risk_usd, tp2_mode, min_stop_points, min_tp1_points) can vary freely.
    """
    return (
        _vwap_session_key(session),
        config.atr_length,
        session.deviation_mode,
        session.deviation_atr_pct,
        session.deviation_std,
        session.rejection_mode,
        session.min_wick_atr_pct,
        session.max_body_atr_pct,
        session.stop_atr_pct,
        config.direction_filter,
        config.excluded_dates,
    )


# ---------------------------------------------------------------------------
# Signal extraction pipeline
# ---------------------------------------------------------------------------

def _extract_vwap_candidates(
    df: pd.DataFrame,
    session: VWAPSessionConfig,
    config: VWAPStrategyConfig,
    _signal_cache: dict | None = None,
) -> list[_VWAPSetupCandidate]:
    """Extract first-VWAP-rejection-per-day setup candidates for a session.

    Signal pipeline:
      1. Session masks (entry/flat/RTH windows)
      2. Session-day IDs (handles cross-midnight sessions)
      3. Daily ATR
      4. Session VWAP
      5. Std-dev bands (if deviation_mode == "std")
      6. Deviation detection (price extended from VWAP)
      7. Rejection candle detection
      8. Combine: deviation + rejection in entry window + direction filter
      9. One signal per session-day (first valid wins)

    Args:
        _signal_cache: Optional pre-computed signal cache from
            :func:`build_vwap_signal_cache`.  When provided, all signal
            arrays are looked up instead of recomputed.
    """
    timestamps = df.index
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    open_ = df["open"].values
    volume = df["volume"].values
    dates = timestamps.date

    if _signal_cache is not None:
        skey = _vwap_session_key(session)
        vkey = _vwap_signal_key(session, config)
        sc = _signal_cache["session"][skey]
        masks = sc["masks"]
        session_day_id = sc["session_day_id"]
        date_strs = sc["date_strs"]
        daily_atr = _signal_cache["atr"][config.atr_length]

        vs = _signal_cache["vwap_signals"][vkey]
        vwap = vs["vwap"]
        extended_above = vs["extended_above"]
        extended_below = vs["extended_below"]
        rejection = vs["rejection"]
    else:
        # 1. Session masks
        masks = _compute_vwap_session_masks(timestamps, session)

        # 2. Session-day IDs
        _, session_day_id = _compute_vwap_session_days(timestamps, session)

        # 3. Daily ATR
        daily_atr = compute_daily_atr(df, config.atr_length)

        # 4. Session VWAP
        vwap = compute_session_vwap(high, low, close, volume, session_day_id)

        # 5. Std-dev bands (only for "std" mode)
        upper_band = None
        lower_band = None
        if session.deviation_mode == "std":
            upper_band, lower_band = compute_vwap_std_bands(
                high, low, close, volume, session_day_id, session.deviation_std,
            )

        # 6. Deviation detection
        extended_above, extended_below = detect_deviation(
            close, vwap, daily_atr,
            session.deviation_atr_pct,
            session.deviation_mode,
            upper_band=upper_band,
            lower_band=lower_band,
        )

        # 7. Rejection candle detection
        rejection = detect_rejection_candles(
            open_, high, low, close, vwap,
            session.rejection_mode,
            min_wick_atr_pct=session.min_wick_atr_pct,
            max_body_atr_pct=session.max_body_atr_pct,
            daily_atr=daily_atr,
        )

        # Date strings
        date_strs = compute_date_strings(timestamps)

    # 8. Combine signals: deviation + rejection in entry window + in RTH
    in_entry = masks["in_entry"]
    in_rth = masks["in_rth"]

    # Extended ABOVE + bearish rejection -> SHORT signal (fade back to VWAP)
    valid_short = (
        extended_above
        & rejection["bearish_rejection"]
        & in_entry
        & in_rth
    )

    # Extended BELOW + bullish rejection -> LONG signal (fade back to VWAP)
    valid_long = (
        extended_below
        & rejection["bullish_rejection"]
        & in_entry
        & in_rth
    )

    # 9. Direction filter
    take_longs = config.direction_filter in ("both", "long")
    take_shorts = config.direction_filter in ("both", "short")

    if not take_longs:
        valid_long = np.zeros(len(valid_long), dtype=bool)
    if not take_shorts:
        valid_short = np.zeros(len(valid_short), dtype=bool)

    # 10. Excluded dates filter
    excluded = set(config.excluded_dates)
    if excluded:
        exclude_arr = np.array(list(excluded))
        exclude_mask = np.isin(date_strs, exclude_arr)
        valid_long = valid_long & ~exclude_mask
        valid_short = valid_short & ~exclude_mask

    # 11. One signal per session-day per direction, first wins
    # Combine both directions, then take the first per session-day
    # (exactly one trade per session-day, like the ORB engine)
    valid_any = valid_long | valid_short
    first_bars = _first_per_day(valid_any, session_day_id)

    # 12. Build candidates
    candidates: list[_VWAPSetupCandidate] = []
    for i in first_bars:
        atr = daily_atr[i]
        if np.isnan(atr) or atr <= 0:
            continue
        entry_bar = i + 1
        if entry_bar >= len(close) or session_day_id[entry_bar] != session_day_id[i]:
            continue

        # Determine direction from which condition this bar matched
        if valid_long[i]:
            direction = 1
            entry = open_[entry_bar]
            stop = low[i]
            # Apply ATR buffer to stop (extend away from entry)
            if session.stop_atr_pct > 0:
                stop -= (session.stop_atr_pct / 100.0) * atr
        elif valid_short[i]:
            direction = -1
            entry = open_[entry_bar]
            stop = high[i]
            # Apply ATR buffer to stop (extend away from entry)
            if session.stop_atr_pct > 0:
                stop += (session.stop_atr_pct / 100.0) * atr
        else:
            continue  # shouldn't happen, but defensive

        candidates.append(_VWAPSetupCandidate(
            date_str=str(dates[i]),
            session=session.name,
            direction=direction,
            signal_bar=i,
            entry_bar=entry_bar,
            entry_price=entry,
            stop_price=stop,
            vwap_at_signal=vwap[i],
            daily_atr=atr,
        ))

    return candidates


# ---------------------------------------------------------------------------
# Internal prepared candidate (trade params computed, ready for Numba)
# ---------------------------------------------------------------------------

@dataclass
class _VWAPPreparedCandidate:
    """Candidate with all trade params computed, ready for simulation."""

    cand: _VWAPSetupCandidate
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
    entry_bar_start: int
    entry_bar_end: int
    flat_bar_start: int
    last_bar: int


# ---------------------------------------------------------------------------
# Main simulation orchestrator
# ---------------------------------------------------------------------------

def run_vwap_backtest(
    df: pd.DataFrame,
    config: VWAPStrategyConfig,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
    _maps: dict | None = None,
    _signal_cache: dict | None = None,
) -> list[TradeResult]:
    """Run the full VWAP reversion backtest pipeline.

    Same interface as ``run_backtest()`` from the ORB engine.  The only
    difference is signal generation: VWAP deviation + rejection candles
    instead of ORB + FVG.  Trade simulation is delegated entirely to the
    shared Numba functions.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data before
            start_date).
        config: VWAP strategy configuration.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
        end_date: Exclude trades on or after this date (YYYY-MM-DD).
        df_1m: Optional 1-minute OHLCV DataFrame for hierarchical drill-down.
        df_30s: Optional 30-second OHLCV DataFrame.
        df_1s: Optional 1-second OHLCV DataFrame.
        _maps: Pre-built maps dict from :func:`build_maps`.
        _signal_cache: Pre-computed signal cache from
            :func:`build_vwap_signal_cache`.

    Returns:
        List of TradeResult (including no-fills), sorted by date.
    """
    high = np.ascontiguousarray(df["high"].values, dtype=np.float64)
    low = np.ascontiguousarray(df["low"].values, dtype=np.float64)
    close = np.ascontiguousarray(df["close"].values, dtype=np.float64)
    timestamps = df.index
    n = len(df)
    no_pre_entry_new_high_sweep = np.zeros(n, dtype=np.bool_)
    no_pre_entry_new_low_sweep = np.zeros(n, dtype=np.bool_)

    # ------------------------------------------------------------------
    # Bar magnifier setup (identical to ORB engine)
    # ------------------------------------------------------------------
    use_magnifier = False  # legacy path, superseded by hierarchical

    if _maps is not None:
        use_hierarchical = _maps["has_1m"]
        has_30s = _maps["has_30s"]
        has_1s = _maps["has_1s"]
        map_5m_1m_arr = _maps["map_5m_1m"]
        map_1m_30s_arr = _maps["map_1m_30s"]
        map_30s_1s_arr = _maps["map_30s_1s"]
        map_1m_1s_arr = _maps["map_1m_1s"]
        high_1m = _maps["high_1m"]
        low_1m = _maps["low_1m"]
        close_1m = _maps["close_1m"]
        high_30s = _maps["high_30s"]
        low_30s = _maps["low_30s"]
        close_30s = _maps["close_30s"]
        high_1s = _maps["high_1s"]
        low_1s = _maps["low_1s"]
        close_1s = _maps["close_1s"]
        timestamps_1m = _maps["timestamps_1m"]
        bar_map = map_5m_1m_arr
    else:
        has_30s = df_30s is not None
        has_1s = df_1s is not None
        use_hierarchical = df_1m is not None

        bar_map = None
        high_1m = low_1m = close_1m = None
        map_5m_1m_arr = None
        map_1m_30s_arr = np.empty((0, 2), dtype=np.int64)
        map_30s_1s_arr = np.empty((0, 2), dtype=np.int64)
        map_1m_1s_arr = np.empty((0, 2), dtype=np.int64)
        high_30s = np.empty(0, dtype=np.float64)
        low_30s = np.empty(0, dtype=np.float64)
        close_30s = np.empty(0, dtype=np.float64)
        high_1s = np.empty(0, dtype=np.float64)
        low_1s = np.empty(0, dtype=np.float64)
        close_1s = np.empty(0, dtype=np.float64)
        timestamps_1m = np.empty(0, dtype="datetime64[ns]")

        if use_hierarchical:
            from ..data.bar_mapping import build_5m_to_1m_map
            bar_map = build_5m_to_1m_map(df, df_1m)
            map_5m_1m_arr = bar_map
            high_1m = np.ascontiguousarray(df_1m["high"].values, dtype=np.float64)
            low_1m = np.ascontiguousarray(df_1m["low"].values, dtype=np.float64)
            close_1m = np.ascontiguousarray(df_1m["close"].values, dtype=np.float64)
            timestamps_1m = df_1m.index.values.astype("datetime64[ns]")

        if has_30s:
            from ..data.bar_mapping import build_1m_to_30s_map
            map_1m_30s_arr = build_1m_to_30s_map(df_1m, df_30s)
            high_30s = np.ascontiguousarray(df_30s["high"].values, dtype=np.float64)
            low_30s = np.ascontiguousarray(df_30s["low"].values, dtype=np.float64)
            close_30s = np.ascontiguousarray(df_30s["close"].values, dtype=np.float64)

        if has_1s:
            high_1s = np.ascontiguousarray(df_1s["high"].values, dtype=np.float64)
            low_1s = np.ascontiguousarray(df_1s["low"].values, dtype=np.float64)
            close_1s = np.ascontiguousarray(df_1s["close"].values, dtype=np.float64)
            if has_30s:
                from ..data.bar_mapping import build_30s_to_1s_map
                map_30s_1s_arr = build_30s_to_1s_map(df_30s, df_1s)
            else:
                from ..data.bar_mapping import build_1m_to_1s_map
                map_1m_1s_arr = build_1m_to_1s_map(df_1m, df_1s)

    # ------------------------------------------------------------------
    # Per-session simulation
    # ------------------------------------------------------------------
    all_results: list[TradeResult] = []

    for session in config.sessions:
        # Extract VWAP candidates (vectorized)
        candidates = _extract_vwap_candidates(
            df, session, config, _signal_cache=_signal_cache,
        )

        # Pre-simulation date filter
        if start_date or end_date:
            candidates = [
                c for c in candidates
                if (start_date is None or c.date_str >= start_date)
                and (end_date is None or c.date_str < end_date)
            ]

        # Session signals: reuse from cache when available
        if _signal_cache is not None:
            skey = _vwap_session_key(session)
            sc = _signal_cache["session"][skey]
            masks = sc["masks"]
            session_day_id = sc["session_day_id"]
            date_strs = sc["date_strs"]
        else:
            masks = _compute_vwap_session_masks(timestamps, session)
            _, session_day_id = _compute_vwap_session_days(timestamps, session)
            date_strs = compute_date_strings(timestamps)

        # Half-day flat mask for NY
        half_day_set = set(config.half_days) if session.name == "NY" else set()

        # Precompute per-session-day bar boundaries
        if _signal_cache is not None and not half_day_set:
            day_bounds = sc["day_bounds_default"]
        else:
            day_bounds = _precompute_day_boundaries(
                timestamps, masks, half_day_set, date_strs, session_day_id,
            )

        # Phase 1: Prepare all candidates (compute trade params + bar boundaries)
        prepared: list[_VWAPPreparedCandidate] = []
        for cand in candidates:
            atr = cand.daily_atr
            if np.isnan(atr) or atr <= 0:
                continue

            entry = cand.entry_price
            direction = cand.direction
            stop = cand.stop_price

            if direction == 1 and stop >= entry:
                continue
            if direction == -1 and stop <= entry:
                continue

            # Risk in points
            risk_pts = abs(entry - stop)

            # Apply minimum stop floor
            if session.min_stop_points > 0 and risk_pts < session.min_stop_points:
                risk_pts = session.min_stop_points
                if direction == 1:
                    stop = entry - risk_pts
                else:
                    stop = entry + risk_pts

            if risk_pts <= 0:
                continue

            # Position sizing
            qty_raw = config.risk_usd / (risk_pts * config.point_value)
            qty = math.floor(qty_raw / config.qty_step) * config.qty_step
            if qty < config.min_qty:
                continue

            # VWAP has no explicit exit_mode. Treat tp1_ratio=1.0 as a
            # true fixed-R single target, even when risk sizing yields
            # multiple contracts.
            is_single = config.tp1_ratio >= 1.0 or qty <= config.min_qty
            if is_single:
                half_qty = qty
            else:
                half_qty = math.floor((qty / 2) / config.qty_step) * config.qty_step
                half_qty = max(half_qty, config.min_qty)

            # TP1 / TP2 computation depends on tp2_mode
            if config.tp2_mode == "vwap":
                # TP2 = revert to VWAP, TP1 = midpoint between entry and VWAP
                vwap_target = cand.vwap_at_signal
                if direction == 1:
                    tp2 = vwap_target
                    tp1 = entry + abs(vwap_target - entry) * config.tp1_ratio
                else:
                    tp2 = vwap_target
                    tp1 = entry - abs(entry - vwap_target) * config.tp1_ratio
            else:
                # fixed_rr mode (default): standard R:R target
                tp1_dist = config.rr * risk_pts * config.tp1_ratio
                tp2_dist = config.rr * risk_pts
                if direction == 1:
                    tp1 = entry + tp1_dist
                    tp2 = entry + tp2_dist
                else:
                    tp1 = entry - tp1_dist
                    tp2 = entry - tp2_dist

            # Apply minimum TP1 distance floor
            if session.min_tp1_points > 0:
                tp1_dist_actual = abs(tp1 - entry)
                if tp1_dist_actual < session.min_tp1_points:
                    if direction == 1:
                        tp1 = entry + session.min_tp1_points
                    else:
                        tp1 = entry - session.min_tp1_points

            # Breakeven price
            be = entry

            # Look up precomputed boundaries using the signal bar's session day
            sd = session_day_id[cand.signal_bar]

            # VWAP reversion confirms at the rejection candle close and enters
            # on the next executable 5m bar. This avoids using the rejection
            # bar's earlier high/low as post-entry exit information.
            entry_bar_start = cand.entry_bar
            entry_bar_end = cand.entry_bar

            bounds = day_bounds.get(sd)
            if bounds is None:
                continue

            flat_bar_start = bounds["flat_first"]
            if flat_bar_start < 0:
                # Last bar for scanning (buffer past entry end)
                last_bar = min(entry_bar_end + 200, n - 1)
                flat_bar_start = last_bar  # Use end of RTH as flat fallback
            else:
                last_bar = min(flat_bar_start + 20, n - 1)

            # Skip signals on or after flat_bar_start (no time to trade)
            if cand.signal_bar >= flat_bar_start:
                continue

            prepared.append(_VWAPPreparedCandidate(
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
                entry_bar_start=entry_bar_start,
                entry_bar_end=entry_bar_end,
                flat_bar_start=flat_bar_start,
                last_bar=last_bar,
            ))

        # Phase 2: Group by session-day and enforce one-trade-per-day.
        # VWAP reversion only produces one signal per session-day (first wins
        # via _first_per_day), so most groups have exactly one candidate.
        # But we still enforce the rule for safety.
        sd_groups: dict[int, list[_VWAPPreparedCandidate]] = defaultdict(list)
        for pc in prepared:
            sd_groups[pc.sd].append(pc)

        def _simulate_and_append(pc: _VWAPPreparedCandidate) -> None:
            neutral_internal_swing_level = 1e38 if pc.direction == 1 else -1e38
            if use_hierarchical:
                fill_bar, exit_type, exit_bar, pnl_pts, fill_1m_f, exit_1m_f = (
                    _simulate_single_trade_hierarchical(
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
                        False,
                        no_pre_entry_new_high_sweep,
                        no_pre_entry_new_low_sweep,
                        0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        neutral_internal_swing_level,
                        False,
                        np.nan,
                    )
                )
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
                    False,
                    no_pre_entry_new_high_sweep,
                    no_pre_entry_new_low_sweep,
                    0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    neutral_internal_swing_level,
                    False,
                    np.nan,
                )
                fill_1m_f = -1.0
                exit_1m_f = -1.0

            gross_pnl_usd = pnl_pts * pc.qty * config.point_value
            commission_usd = 0.0
            if exit_type != EXIT_NO_FILL:
                commission_usd = 2 * pc.qty * config.commission_per_contract
            pnl_usd = gross_pnl_usd - commission_usd
            r_multiple = pnl_pts / pc.risk_pts if pc.risk_pts > 0 else 0.0
            gross_risk_usd = pc.risk_pts * pc.qty * config.point_value
            net_r_multiple = pnl_usd / gross_risk_usd if gross_risk_usd > 0 else 0.0

            all_results.append(TradeResult(
                date=pc.cand.date_str,
                session=session.name,
                direction=pc.direction,
                signal_bar=pc.cand.signal_bar,
                fill_bar=fill_bar,
                entry_price=pc.entry_price,
                stop_price=pc.stop_price,
                tp1_price=pc.tp1_price,
                tp2_price=pc.tp2_price,
                exit_type=exit_type,
                exit_bar=exit_bar,
                pnl_points=pnl_pts,
                pnl_usd=pnl_usd,
                r_multiple=r_multiple,
                qty=pc.qty,
                half_qty=pc.half_qty,
                gap_size=0.0,  # no FVG gap in VWAP strategy
                risk_points=pc.risk_pts,
                fill_time=_resolve_time(
                    timestamps, fill_bar, timestamps_1m,
                    fill_1m_f if use_hierarchical else -1.0,
                ),
                exit_time=_resolve_time(
                    timestamps, exit_bar, timestamps_1m,
                    exit_1m_f if use_hierarchical else -1.0,
                ),
                gross_pnl_usd=gross_pnl_usd,
                commission_usd=commission_usd,
                net_r_multiple=net_r_multiple,
            ))

        def _append_no_fill(pc: _VWAPPreparedCandidate) -> None:
            all_results.append(TradeResult(
                date=pc.cand.date_str,
                session=session.name,
                direction=pc.direction,
                signal_bar=pc.cand.signal_bar,
                fill_bar=-1,
                entry_price=pc.entry_price,
                stop_price=pc.stop_price,
                tp1_price=pc.tp1_price,
                tp2_price=pc.tp2_price,
                exit_type=EXIT_NO_FILL,
                exit_bar=-1,
                pnl_points=0.0,
                pnl_usd=0.0,
                r_multiple=0.0,
                qty=pc.qty,
                half_qty=pc.half_qty,
                gap_size=0.0,
                risk_points=pc.risk_pts,
                fill_time="",
                exit_time="",
            ))

        for sd in sorted(sd_groups):
            group = sd_groups[sd]
            if len(group) == 1:
                _simulate_and_append(group[0])
            else:
                # Multiple candidates on same session-day.
                # VWAP market orders fill immediately, so use signal_bar order.
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
                    winner_pc, _ = min(
                        filled, key=lambda x: (x[1], x[0].cand.signal_bar),
                    )
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
# Signal pre-computation cache (for parameter sweeps)
# ---------------------------------------------------------------------------

def build_vwap_signal_cache(
    df: pd.DataFrame,
    configs: list[VWAPStrategyConfig],
) -> dict:
    """Pre-compute all signal arrays needed by a set of VWAP configs.

    Call once before a parameter sweep, then pass the result as
    ``_signal_cache=cache`` to :func:`run_vwap_backtest`.

    Groups configs by their signal-determining keys and computes each unique
    combination exactly once:

    - ``cache["atr"][atr_length]``                    -> daily ATR array
    - ``cache["session"][session_key]``               -> masks, day IDs, date strings
    - ``cache["vwap_signals"][vwap_signal_key]``      -> VWAP + deviation + rejection arrays

    For a 1000-config sweep where only rr/tp1_ratio vary, each signal
    computation runs exactly once.
    """
    cache: dict = {"atr": {}, "session": {}, "vwap_signals": {}}
    timestamps = df.index
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    open_ = df["open"].values
    volume = df["volume"].values

    # Date strings: config-independent, computed exactly once
    date_strs = compute_date_strings(timestamps)

    # Collect unique keys
    atr_lengths: set[int] = set()
    unique_sessions: dict[tuple, VWAPSessionConfig] = {}
    unique_vwap_tasks: list[tuple[tuple, VWAPSessionConfig, VWAPStrategyConfig]] = []
    seen_vwap: set[tuple] = set()

    for config in configs:
        atr_lengths.add(config.atr_length)
        for session in config.sessions:
            skey = _vwap_session_key(session)
            if skey not in unique_sessions:
                unique_sessions[skey] = session

            vkey = _vwap_signal_key(session, config)
            if vkey not in seen_vwap:
                seen_vwap.add(vkey)
                unique_vwap_tasks.append((vkey, session, config))

    # --- Batch 1: ATR + session computations in parallel ---
    def _compute_atr(atr_length: int) -> tuple[int, np.ndarray]:
        return atr_length, compute_daily_atr(df, atr_length)

    def _compute_session(
        skey: tuple, session: VWAPSessionConfig,
    ) -> tuple[tuple, dict]:
        masks = _compute_vwap_session_masks(timestamps, session)
        _, session_day_id = _compute_vwap_session_days(timestamps, session)
        day_bounds_default = _precompute_day_boundaries(
            timestamps, masks, set(), date_strs, session_day_id,
        )
        return skey, {
            "masks": masks,
            "session_day_id": session_day_id,
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

    # --- Batch 2: VWAP signal computations in parallel ---
    def _compute_vwap_signals(
        vkey: tuple,
        session: VWAPSessionConfig,
        config: VWAPStrategyConfig,
    ) -> tuple[tuple, dict]:
        skey = _vwap_session_key(session)
        sc = cache["session"][skey]
        session_day_id = sc["session_day_id"]
        daily_atr = cache["atr"][config.atr_length]

        vwap = compute_session_vwap(high, low, close, volume, session_day_id)

        upper_band = None
        lower_band = None
        if session.deviation_mode == "std":
            upper_band, lower_band = compute_vwap_std_bands(
                high, low, close, volume, session_day_id, session.deviation_std,
            )

        extended_above, extended_below = detect_deviation(
            close, vwap, daily_atr,
            session.deviation_atr_pct,
            session.deviation_mode,
            upper_band=upper_band,
            lower_band=lower_band,
        )

        rejection = detect_rejection_candles(
            open_, high, low, close, vwap,
            session.rejection_mode,
            min_wick_atr_pct=session.min_wick_atr_pct,
            max_body_atr_pct=session.max_body_atr_pct,
            daily_atr=daily_atr,
        )

        return vkey, {
            "vwap": vwap,
            "extended_above": extended_above,
            "extended_below": extended_below,
            "rejection": rejection,
        }

    n_vwap = len(unique_vwap_tasks)
    max_vwap_workers = min(n_vwap, (os.cpu_count() or 1))

    if max_vwap_workers > 1:
        with ThreadPoolExecutor(max_workers=max_vwap_workers) as executor:
            vwap_futures = [
                executor.submit(_compute_vwap_signals, vkey, session, config)
                for vkey, session, config in unique_vwap_tasks
            ]
            for f in vwap_futures:
                vkey, vwap_data = f.result()
                cache["vwap_signals"][vkey] = vwap_data
    else:
        for vkey, session, config in unique_vwap_tasks:
            _, vwap_data = _compute_vwap_signals(vkey, session, config)
            cache["vwap_signals"][vkey] = vwap_data

    return cache
