"""Broad screen for ALPHA_V1 ORB close-entry variants.

Tests the three ORB legs from ALPHA_V1:
- Current baseline: first valid FVG outside ORB, enter on FVG retest.
- FVG close: first valid FVG outside ORB, enter at the confirming 5m close.
- Breakout close: first 5m close outside ORB, no FVG requirement.

The close-entry variants are intentionally implemented here instead of changing
the production simulator. They enter at the signal 5m close and begin exit
scanning on the next bar, preserving point-in-time behavior.
"""

from __future__ import annotations

import gc
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    build_alpha_v1_legs,
    filled_trades,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import (
    EXIT_BE_SL,
    EXIT_EOD,
    EXIT_NO_FILL,
    EXIT_SL,
    EXIT_TP1_BE,
    EXIT_TP1_EOD,
    EXIT_TP1_TP2,
    EXIT_TP2_SINGLE,
    TradeResult,
    _drill_down_1m,
    build_maps,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.signals.daily_atr import compute_daily_atr
from orb_backtest.signals.fvg import detect_fvg
from orb_backtest.signals.orb import compute_orb_levels
from orb_backtest.signals.session import compute_date_strings, compute_session_days, compute_session_masks


ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_close_entry_probe"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_CLOSE_ENTRY_PROBE.md"

FULL_START = "2016-04-17"
AVAILABLE_END = "2026-03-24"
HOLDOUT_START = "2025-01-01"
ORB_LEG_KEYS = ("nq_asia_orb_long", "es_asia_orb_long", "es_ny_orb_long")


@dataclass(frozen=True)
class MarketData:
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None
    maps: dict | None


@dataclass(frozen=True)
class CloseCandidate:
    date_str: str
    session: str
    direction: int
    signal_bar: int
    entry_price: float
    gap_size: float
    daily_atr: float
    orb_range: float


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100 or value == int(value):
            return f"{value:.0f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _load_or_resample_market_data(config: StrategyConfig) -> MarketData:
    """Load 5m/1m/1s data, resampling from 1s when 5m is absent."""

    try:
        df_5m = load_5m_data(config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
        try:
            df_1m = load_1m_for_5m(config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
        except FileNotFoundError:
            df_1m = None
        df_1s = load_1s_for_5m(config.instrument.data_file, start=FULL_START, end=AVAILABLE_END)
    except FileNotFoundError:
        symbol = config.instrument.symbol
        one_second_path = RAW_DIR / f"{symbol}_1s.parquet"
        if not one_second_path.exists():
            raise
        df_1s = pd.read_parquet(one_second_path)
        df_1s = df_1s[(df_1s.index >= FULL_START) & (df_1s.index <= AVAILABLE_END)]
        df_1m = _resample_ohlcv(df_1s, "1min")
        df_5m = _resample_ohlcv(df_1s, "5min")

    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s) if df_1m is not None else None
    return MarketData(df_5m=df_5m, df_1m=df_1m, df_1s=df_1s, maps=maps)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"])


def _candidate_indices(
    valid_mask: np.ndarray,
    session_day_id: np.ndarray,
) -> np.ndarray:
    indices = np.where(valid_mask)[0]
    if len(indices) == 0:
        return indices
    day_ids = session_day_id[indices]
    _, first_idx = np.unique(day_ids, return_index=True)
    return indices[first_idx]


def _extract_close_candidates(
    df: pd.DataFrame,
    config: StrategyConfig,
    session: SessionConfig,
    mode: str,
) -> list[CloseCandidate]:
    timestamps = df.index
    masks = compute_session_masks(timestamps, session)
    new_session_day, session_day_id = compute_session_days(timestamps, session)
    daily_atr = compute_daily_atr(df, config.atr_length)
    orb_high, orb_low, orb_ready = compute_orb_levels(
        df, masks["in_orb"], masks["in_rth"], new_session_day
    )
    date_strs = compute_date_strings(timestamps)
    close = df["close"].to_numpy(dtype=np.float64)
    dates = timestamps.date

    excluded = set(config.excluded_dates)
    if config.excluded_days:
        unique_dates = set(date_strs) - excluded
        for ds in unique_dates:
            if pd.Timestamp(ds).weekday() in set(config.excluded_days):
                excluded.add(ds)

    common = masks["in_entry"] & masks["in_rth"] & orb_ready
    if excluded:
        common &= ~np.isin(date_strs, np.array(list(excluded)))

    selected_candidates: list[CloseCandidate] = []
    take_longs = config.direction_filter in ("both", "long")
    take_shorts = config.direction_filter in ("both", "short")

    if mode == "fvg_close":
        fvg = detect_fvg(
            df["high"].to_numpy(dtype=np.float64),
            df["low"].to_numpy(dtype=np.float64),
            daily_atr,
            orb_high,
            orb_low,
            session.min_gap_atr_pct,
            close=close if config.impulse_close_filter else None,
            impulse_close_filter=config.impulse_close_filter,
            min_gap_orb_pct=getattr(session, "min_gap_orb_pct", 0.0),
        )
        if take_longs:
            valid_long = fvg["long_fvg"] & common & (close > orb_high)
            for i in _candidate_indices(valid_long, session_day_id):
                selected_candidates.append(
                    CloseCandidate(
                        date_str=str(dates[i]),
                        session=session.name,
                        direction=1,
                        signal_bar=int(i),
                        entry_price=float(close[i]),
                        gap_size=float(fvg["long_gap_size"][i]),
                        daily_atr=float(daily_atr[i]),
                        orb_range=float(orb_high[i] - orb_low[i]),
                    )
                )
        if take_shorts:
            valid_short = fvg["short_fvg"] & common & (close < orb_low)
            for i in _candidate_indices(valid_short, session_day_id):
                selected_candidates.append(
                    CloseCandidate(
                        date_str=str(dates[i]),
                        session=session.name,
                        direction=-1,
                        signal_bar=int(i),
                        entry_price=float(close[i]),
                        gap_size=float(fvg["short_gap_size"][i]),
                        daily_atr=float(daily_atr[i]),
                        orb_range=float(orb_high[i] - orb_low[i]),
                    )
                )
    elif mode == "breakout_close":
        if take_longs:
            valid_long = common & (close > orb_high)
            for i in _candidate_indices(valid_long, session_day_id):
                selected_candidates.append(
                    CloseCandidate(
                        date_str=str(dates[i]),
                        session=session.name,
                        direction=1,
                        signal_bar=int(i),
                        entry_price=float(close[i]),
                        gap_size=0.0,
                        daily_atr=float(daily_atr[i]),
                        orb_range=float(orb_high[i] - orb_low[i]),
                    )
                )
        if take_shorts:
            valid_short = common & (close < orb_low)
            for i in _candidate_indices(valid_short, session_day_id):
                selected_candidates.append(
                    CloseCandidate(
                        date_str=str(dates[i]),
                        session=session.name,
                        direction=-1,
                        signal_bar=int(i),
                        entry_price=float(close[i]),
                        gap_size=0.0,
                        daily_atr=float(daily_atr[i]),
                        orb_range=float(orb_high[i] - orb_low[i]),
                    )
                )
    else:
        raise ValueError(f"Unknown close candidate mode: {mode}")

    return selected_candidates


def _simulate_close_trade_5m(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    signal_bar: int,
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
) -> tuple[int, int, float]:
    """Simulate exits after a 5m close entry. Returns exit_type, exit_bar, pnl_points."""

    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    for i in range(signal_bar + 1, last_bar + 1):
        is_flat_bar = i >= flat_bar_start
        if direction == 1:
            sl_hit = low[i] <= current_stop
            tp1_trigger = high[i] >= tp1_price and not tp1_hit
            tp2_trigger = high[i] >= tp2_price
            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close[i] - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                return EXIT_EOD, i, close[i] - entry_price
            if sl_hit and not tp1_hit:
                return EXIT_SL, i, current_stop - entry_price
            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    sl_hit = low[i] <= current_stop
                if tp2_trigger:
                    return EXIT_TP2_SINGLE, i, tp2_price - entry_price
                if sl_hit and tp1_hit:
                    return EXIT_TP1_BE, i, current_stop - entry_price
            else:
                if sl_hit and tp1_trigger:
                    return EXIT_SL, i, current_stop - entry_price
                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    if low[i] <= be_price:
                        pnl_points += (be_price - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_TP2, i, pnl_points
        else:
            sl_hit = high[i] >= current_stop
            tp1_trigger = low[i] <= tp1_price and not tp1_hit
            tp2_trigger = low[i] <= tp2_price
            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close[i]) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points
                return EXIT_EOD, i, entry_price - close[i]
            if sl_hit and not tp1_hit:
                return EXIT_SL, i, entry_price - current_stop
            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    sl_hit = high[i] >= current_stop
                if tp2_trigger:
                    return EXIT_TP2_SINGLE, i, entry_price - tp2_price
                if sl_hit and tp1_hit:
                    return EXIT_TP1_BE, i, entry_price - current_stop
            else:
                if sl_hit and tp1_trigger:
                    return EXIT_SL, i, entry_price - current_stop
                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    if high[i] >= be_price:
                        pnl_points += (entry_price - be_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return EXIT_TP1_TP2, i, pnl_points

    if direction == 1:
        return EXIT_EOD, last_bar, close[last_bar] - entry_price
    return EXIT_EOD, last_bar, entry_price - close[last_bar]


def _simulate_close_trade_hierarchical(
    maps: dict,
    high_5m: np.ndarray,
    low_5m: np.ndarray,
    close_5m: np.ndarray,
    signal_bar: int,
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
) -> tuple[int, int, float, float]:
    """Hierarchical exit scan after a market-at-close fill."""

    map_5m_1m = maps["map_5m_1m"]
    flat_5m_clamped = min(flat_bar_start, len(map_5m_1m) - 1)
    flat_start_1m = int(map_5m_1m[flat_5m_clamped, 0])
    fill_1m = -1.0
    if signal_bar < len(map_5m_1m):
        fill_1m = float(max(int(map_5m_1m[signal_bar, 1]) - 1, int(map_5m_1m[signal_bar, 0])))

    tp1_hit = False
    current_stop = stop_price
    remaining_qty = qty
    pnl_points = 0.0

    for i in range(signal_bar + 1, last_bar + 1):
        is_flat_bar = i >= flat_bar_start
        if direction == 1:
            sl_hit = low_5m[i] <= current_stop
            tp1_trigger = high_5m[i] >= tp1_price and not tp1_hit
            tp2_trigger = high_5m[i] >= tp2_price
            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (close_5m[i] - entry_price) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points, fill_1m
                pnl_points += close_5m[i] - entry_price
                return EXIT_EOD, i, pnl_points, fill_1m
            if sl_hit and not tp1_hit:
                pnl_points += current_stop - entry_price
                return EXIT_SL, i, pnl_points, fill_1m
            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    sl_hit = low_5m[i] <= current_stop
                if tp2_trigger:
                    pnl_points += tp2_price - entry_price
                    return EXIT_TP2_SINGLE, i, pnl_points, fill_1m
                if sl_hit and tp1_hit:
                    pnl_points += current_stop - entry_price
                    return EXIT_TP1_BE, i, pnl_points, fill_1m
            else:
                if sl_hit and tp1_trigger:
                    if i < len(map_5m_1m):
                        s1m = int(map_5m_1m[i, 0])
                        e1m = int(map_5m_1m[i, 1])
                        if e1m > s1m:
                            resolved, exit_type, exit_1m, pnl_out, tp1_out, stop_out, qty_out = _drill_down_1m(
                                maps["high_1m"],
                                maps["low_1m"],
                                maps["close_1m"],
                                maps["high_30s"],
                                maps["low_30s"],
                                maps["close_30s"],
                                maps["high_1s"],
                                maps["low_1s"],
                                maps["close_1s"],
                                maps["map_1m_30s"],
                                maps["map_30s_1s"],
                                maps["map_1m_1s"],
                                maps["has_30s"],
                                maps["has_1s"],
                                s1m,
                                e1m,
                                flat_start_1m,
                                direction,
                                entry_price,
                                current_stop,
                                tp1_price,
                                tp2_price,
                                be_price,
                                tp1_hit,
                                is_single,
                                qty,
                                half_qty,
                                remaining_qty,
                                pnl_points,
                            )
                            pnl_points = pnl_out
                            tp1_hit = tp1_out
                            current_stop = stop_out
                            remaining_qty = qty_out
                            if resolved:
                                return exit_type, i, pnl_points, fill_1m
                            continue
                    pnl_points += current_stop - entry_price
                    return EXIT_SL, i, pnl_points, fill_1m
                if tp1_trigger:
                    pnl_points += (tp1_price - entry_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    if low_5m[i] <= be_price:
                        pnl_points += (be_price - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points, fill_1m
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (current_stop - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points, fill_1m
                    if tp2_trigger:
                        pnl_points += (tp2_price - entry_price) * (remaining_qty / qty)
                        return EXIT_TP1_TP2, i, pnl_points, fill_1m
        else:
            sl_hit = high_5m[i] >= current_stop
            tp1_trigger = low_5m[i] <= tp1_price and not tp1_hit
            tp2_trigger = low_5m[i] <= tp2_price
            if is_flat_bar and not sl_hit:
                if tp1_hit:
                    pnl_points += (entry_price - close_5m[i]) * (remaining_qty / qty)
                    return EXIT_TP1_EOD, i, pnl_points, fill_1m
                pnl_points += entry_price - close_5m[i]
                return EXIT_EOD, i, pnl_points, fill_1m
            if sl_hit and not tp1_hit:
                pnl_points += entry_price - current_stop
                return EXIT_SL, i, pnl_points, fill_1m
            if is_single:
                if tp1_trigger:
                    tp1_hit = True
                    current_stop = be_price
                    sl_hit = high_5m[i] >= current_stop
                if tp2_trigger:
                    pnl_points += entry_price - tp2_price
                    return EXIT_TP2_SINGLE, i, pnl_points, fill_1m
                if sl_hit and tp1_hit:
                    pnl_points += entry_price - current_stop
                    return EXIT_TP1_BE, i, pnl_points, fill_1m
            else:
                if sl_hit and tp1_trigger:
                    if i < len(map_5m_1m):
                        s1m = int(map_5m_1m[i, 0])
                        e1m = int(map_5m_1m[i, 1])
                        if e1m > s1m:
                            resolved, exit_type, exit_1m, pnl_out, tp1_out, stop_out, qty_out = _drill_down_1m(
                                maps["high_1m"],
                                maps["low_1m"],
                                maps["close_1m"],
                                maps["high_30s"],
                                maps["low_30s"],
                                maps["close_30s"],
                                maps["high_1s"],
                                maps["low_1s"],
                                maps["close_1s"],
                                maps["map_1m_30s"],
                                maps["map_30s_1s"],
                                maps["map_1m_1s"],
                                maps["has_30s"],
                                maps["has_1s"],
                                s1m,
                                e1m,
                                flat_start_1m,
                                direction,
                                entry_price,
                                current_stop,
                                tp1_price,
                                tp2_price,
                                be_price,
                                tp1_hit,
                                is_single,
                                qty,
                                half_qty,
                                remaining_qty,
                                pnl_points,
                            )
                            pnl_points = pnl_out
                            tp1_hit = tp1_out
                            current_stop = stop_out
                            remaining_qty = qty_out
                            if resolved:
                                return exit_type, i, pnl_points, fill_1m
                            continue
                    pnl_points += entry_price - current_stop
                    return EXIT_SL, i, pnl_points, fill_1m
                if tp1_trigger:
                    pnl_points += (entry_price - tp1_price) * (half_qty / qty)
                    tp1_hit = True
                    current_stop = be_price
                    remaining_qty -= half_qty
                    if high_5m[i] >= be_price:
                        pnl_points += (entry_price - be_price) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points, fill_1m
                    continue
                if tp1_hit:
                    if sl_hit:
                        pnl_points += (entry_price - current_stop) * (remaining_qty / qty)
                        return EXIT_TP1_BE, i, pnl_points, fill_1m
                    if tp2_trigger:
                        pnl_points += (entry_price - tp2_price) * (remaining_qty / qty)
                        return EXIT_TP1_TP2, i, pnl_points, fill_1m

    if direction == 1:
        pnl_points += close_5m[last_bar] - entry_price
    else:
        pnl_points += entry_price - close_5m[last_bar]
    return EXIT_EOD, last_bar, pnl_points, fill_1m


def _day_bounds(df: pd.DataFrame, session: SessionConfig) -> dict[int, dict[str, int]]:
    timestamps = df.index
    masks = compute_session_masks(timestamps, session)
    _, session_day_id = compute_session_days(timestamps, session)
    bounds: dict[int, dict[str, int]] = {}
    for sd in np.unique(session_day_id):
        day_mask = session_day_id == sd
        entry_idx = np.where(day_mask & masks["in_entry"])[0]
        flat_idx = np.where(day_mask & masks["in_flat"])[0]
        rth_idx = np.where(day_mask & masks["in_rth"])[0]
        if len(entry_idx) == 0 or len(rth_idx) == 0:
            continue
        flat_first = int(flat_idx[0]) if len(flat_idx) else int(entry_idx[-1])
        bounds[int(sd)] = {
            "entry_last": int(entry_idx[-1]),
            "flat_first": flat_first,
            "last_bar": min(flat_first + 20, len(df) - 1),
        }
    return bounds


def _run_close_variant(config: StrategyConfig, market: MarketData, mode: str) -> list[TradeResult]:
    session = config.sessions[0]
    candidates = _extract_close_candidates(market.df_5m, config, session, mode)
    if config.excluded_days:
        candidates = [
            c for c in candidates
            if pd.Timestamp(c.date_str).weekday() not in set(config.excluded_days)
        ]

    high = market.df_5m["high"].to_numpy(dtype=np.float64)
    low = market.df_5m["low"].to_numpy(dtype=np.float64)
    close = market.df_5m["close"].to_numpy(dtype=np.float64)
    timestamps = market.df_5m.index
    _, session_day_id = compute_session_days(timestamps, session)
    bounds = _day_bounds(market.df_5m, session)
    first_by_session_day: dict[int, CloseCandidate] = {}
    for cand in sorted(candidates, key=lambda item: (item.signal_bar, item.direction)):
        sd = int(session_day_id[cand.signal_bar])
        first_by_session_day.setdefault(sd, cand)

    trades: list[TradeResult] = []
    for cand in first_by_session_day.values():
        if np.isnan(cand.daily_atr) or cand.daily_atr <= 0:
            continue
        sd = int(session_day_id[cand.signal_bar])
        day_bound = bounds.get(sd)
        if day_bound is None:
            continue
        if cand.signal_bar >= day_bound["entry_last"]:
            continue

        if session.stop_orb_pct > 0 and cand.orb_range > 0:
            stop_dist = (session.stop_orb_pct / 100.0) * cand.orb_range
        else:
            stop_dist = (session.stop_atr_pct / 100.0) * cand.daily_atr
        stop_dist = max(stop_dist, 0.05 * cand.daily_atr)
        if session.min_stop_points > 0:
            stop_dist = max(stop_dist, session.min_stop_points)

        entry = cand.entry_price
        if cand.direction == 1:
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
        half_qty = qty if is_single else max(
            math.floor((qty / 2) / config.qty_step) * config.qty_step,
            config.min_qty,
        )

        tp1_dist = max(config.tp1_ratio * config.rr * risk_pts, risk_pts)
        tp2_dist = config.rr * risk_pts
        if session.min_tp1_points > 0:
            tp1_dist = max(tp1_dist, session.min_tp1_points)
        if cand.direction == 1:
            tp1 = entry + tp1_dist
            tp2 = entry + tp2_dist
        else:
            tp1 = entry - tp1_dist
            tp2 = entry - tp2_dist

        if market.maps is not None and market.maps.get("has_1m"):
            exit_type, exit_bar, pnl_points, fill_1m = _simulate_close_trade_hierarchical(
                market.maps,
                high,
                low,
                close,
                cand.signal_bar,
                day_bound["flat_first"],
                day_bound["last_bar"],
                cand.direction,
                entry,
                stop,
                tp1,
                tp2,
                entry,
                is_single,
                qty,
                half_qty,
            )
        else:
            exit_type, exit_bar, pnl_points = _simulate_close_trade_5m(
                high,
                low,
                close,
                cand.signal_bar,
                day_bound["flat_first"],
                day_bound["last_bar"],
                cand.direction,
                entry,
                stop,
                tp1,
                tp2,
                entry,
                is_single,
                qty,
                half_qty,
            )
            fill_1m = -1.0

        pnl_usd = pnl_points * qty * config.point_value
        if exit_type != EXIT_NO_FILL:
            pnl_usd -= 2 * qty * config.commission_per_contract
        r_multiple = pnl_points / risk_pts if risk_pts > 0 else 0.0
        fill_time = timestamps[cand.signal_bar].isoformat()
        exit_time = timestamps[exit_bar].isoformat() if exit_bar >= 0 else ""

        trades.append(
            TradeResult(
                date=cand.date_str,
                session=session.name,
                direction=cand.direction,
                signal_bar=cand.signal_bar,
                fill_bar=cand.signal_bar,
                entry_price=entry,
                stop_price=stop,
                tp1_price=tp1,
                tp2_price=tp2,
                exit_type=exit_type,
                exit_bar=exit_bar,
                pnl_points=pnl_points,
                pnl_usd=pnl_usd,
                r_multiple=r_multiple,
                qty=qty,
                half_qty=half_qty,
                gap_size=cand.gap_size,
                risk_points=risk_pts,
                fill_time=fill_time,
                exit_time=exit_time,
            )
        )

    return trades


def _metrics_row(
    leg: str,
    variant: str,
    trades: list[TradeResult],
    baseline_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    holdout = compute_metrics([t for t in trades if t.date >= HOLDOUT_START])
    neg_years = sum(1 for r in metrics.get("r_by_year", {}).values() if r < 0)
    row = {
        "leg": leg,
        "variant": variant,
        "trades": metrics["total_trades"],
        "wr_pct": _round(metrics["win_rate"] * 100.0, 1),
        "pf": _round(metrics["profit_factor"], 2),
        "net_r": _round(metrics["total_r"], 1),
        "max_dd_r": _round(metrics["max_drawdown_r"], 1),
        "sharpe": _round(metrics["sharpe_ratio"], 2),
        "neg_years": neg_years,
        "holdout_trades": holdout["total_trades"],
        "holdout_net_r": _round(holdout["total_r"], 1),
        "holdout_dd_r": _round(holdout["max_drawdown_r"], 1),
    }
    if baseline_metrics is not None:
        row["delta_r"] = _round(metrics["total_r"] - baseline_metrics["total_r"], 1)
        row["delta_dd"] = _round(metrics["max_drawdown_r"] - baseline_metrics["max_drawdown_r"], 1)
    else:
        row["delta_r"] = 0.0
        row["delta_dd"] = 0.0
    return row


def _portfolio_row(variant: str, named_streams: dict[str, list[TradeResult]]) -> dict[str, Any]:
    filled_streams = {name: filled_trades(trades) for name, trades in named_streams.items()}
    daily = portfolio_daily_frame(filled_streams)
    total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
    summary = summarize_daily_returns(total_series)
    return {
        "variant": variant,
        "trades": sum(len(stream) for stream in filled_streams.values()),
        "net_r": _round(summary["total_r"], 1),
        "max_dd_r": _round(summary["max_drawdown_r"], 1),
        "daily_sharpe": _round(summary["sharpe_ratio"], 2),
        "calmar": _round(summary["calmar_ratio"], 2),
    }


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    legs = build_alpha_v1_legs()

    rows: list[dict[str, Any]] = []
    portfolio_streams: dict[str, dict[str, list[TradeResult]]] = defaultdict(dict)

    for leg_key in ORB_LEG_KEYS:
        config = legs[leg_key].config
        print(f"[probe] Loading {leg_key} ({config.instrument.symbol})")
        market = _load_or_resample_market_data(config)

        print(f"[probe] Baseline retest {leg_key}")
        baseline = run_backtest(
            market.df_5m,
            config,
            start_date=FULL_START,
            end_date=AVAILABLE_END,
            df_1m=market.df_1m,
            df_1s=market.df_1s,
            _maps=market.maps,
        )
        if config.excluded_days:
            baseline = apply_dow_filter(baseline, set(config.excluded_days))
        baseline_metrics = compute_metrics(baseline)
        rows.append(_metrics_row(leg_key, "baseline_retest", baseline))
        portfolio_streams["baseline_retest"][leg_key] = baseline

        for mode in ("fvg_close", "breakout_close"):
            print(f"[probe] {mode} {leg_key}")
            trades = _run_close_variant(config, market, mode)
            rows.append(_metrics_row(leg_key, mode, trades, baseline_metrics=baseline_metrics))
            portfolio_streams[mode][leg_key] = trades

        del market
        gc.collect()

    portfolio_rows = [
        _portfolio_row(variant, streams)
        for variant, streams in portfolio_streams.items()
    ]

    payload = {
        "scope": {
            "start": FULL_START,
            "end": AVAILABLE_END,
            "holdout_start": HOLDOUT_START,
            "legs": list(ORB_LEG_KEYS),
        },
        "leg_rows": rows,
        "portfolio_rows": portfolio_rows,
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    report_lines = [
        "# ALPHA_V1 ORB Close-Entry Probe",
        "",
        f"Window: `{FULL_START}` to `{AVAILABLE_END}`. Holdout shown as `{HOLDOUT_START}+`.",
        "",
        "## Takeaway",
        "",
        "- Broad screen verdict: do not replace the ALPHA_V1 ORB retest entry with a close-entry rule.",
        "- `fvg_close` kept the FVG requirement but nearly erased the ORB sleeve edge: `+28.3R` vs `+359.5R` baseline, with max DD widening from `-21.2R` to `-54.8R`.",
        "- `breakout_close` helped only the NQ Asia leg in raw R, but the combined sleeve turned negative because ES Asia collapsed toward flat and ES NY became strongly negative.",
        "- The retest appears to be an important quality/liquidity filter, not just a delayed fill mechanic.",
        "",
        "## Definitions",
        "",
        "- `baseline_retest`: current ALPHA_V1 ORB continuation logic, first valid FVG outside ORB, limit entry on FVG retest.",
        "- `fvg_close`: same valid FVG condition, but market-at-close on the 5m FVG confirmation bar; exits begin on the next bar.",
        "- `breakout_close`: first 5m close outside the ORB in the leg direction; no FVG requirement; exits begin on the next bar.",
        "- Data note: this checkout has `NQ_1s.parquet` but no `NQ_5m` file, so the NQ leg is resampled from 1-second data in-memory for this probe.",
        "",
        "## Leg Results",
        "",
        _markdown_table(
            rows,
            [
                "leg",
                "variant",
                "trades",
                "wr_pct",
                "pf",
                "net_r",
                "max_dd_r",
                "sharpe",
                "neg_years",
                "holdout_trades",
                "holdout_net_r",
                "holdout_dd_r",
                "delta_r",
                "delta_dd",
            ],
        ),
        "",
        "## ORB Sleeve",
        "",
        _markdown_table(
            portfolio_rows,
            ["variant", "trades", "net_r", "max_dd_r", "daily_sharpe", "calmar"],
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print("")
    print(_markdown_table(rows, ["leg", "variant", "trades", "wr_pct", "pf", "net_r", "max_dd_r", "sharpe", "holdout_net_r"]))
    print("")
    print(_markdown_table(portfolio_rows, ["variant", "trades", "net_r", "max_dd_r", "daily_sharpe", "calmar"]))
    print(f"\nReport written to: {REPORT_PATH}")
    print(f"Summary JSON written to: {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
