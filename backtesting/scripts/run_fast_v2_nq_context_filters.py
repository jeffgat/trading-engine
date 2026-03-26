#!/usr/bin/env python3
"""FAST_V2 NQ context-filter validation.

Runs the merged live FAST_V2 configs (execution main defaults + FAST_V2 profile
overrides), then evaluates a small set of post-trade context gates aimed at
local and mid-timeframe trend confirmation for NQ ORB continuation legs.

What is tested:
1. Session VWAP side at signal bar.
2. Session VWAP side + 3-bar VWAP slope alignment.
3. Signal close on the correct side of both VWAP and ORB boundary.
4. Previous-day midpoint bias.
5. Overnight midpoint bias (NY only).
6. Combined context filter.

Outputs:
- Per-leg comparison for NQ continuation legs: NQ_NY, NQ_Asia
- Combined NQ ORB comparison (NQ_NY + NQ_Asia)
- Combined FAST_V2 comparison where only the NQ continuation legs are gated
  and the other FAST_V2 legs remain unchanged

Windows:
- Full:   2016-01-01 -> end_date
- Recent: 2024-01-01 -> end_date
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT.parent / "execution" / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.signals.orb import compute_orb_levels
from orb_backtest.signals.session import compute_session_days, compute_session_masks
from orb_backtest.signals.vwap import compute_session_vwap
from trader.main import (
    EXEC_CONFIGS_PATH,
    LSI_SESSION_CONFIGS,
    SESSION_CONFIGS,
    load_config,
)

LIVE_TOML = ROOT.parent / "execution" / "config" / "live.toml"

FULL_START = "2016-01-01"
RECENT_START = "2024-01-01"

CONTINUATION_LEGS = ("NQ_NY", "NQ_Asia")


@dataclass(frozen=True)
class BuiltLeg:
    name: str
    symbol: str
    strategy: str
    config: StrategyConfig
    excluded_dow: tuple[int, ...]
    session: SessionConfig


@dataclass(frozen=True)
class LegContext:
    close: np.ndarray
    vwap: np.ndarray
    orb_high: np.ndarray
    orb_low: np.ndarray
    prev_day_mid: np.ndarray
    overnight_mid: np.ndarray | None


def load_profile_raw(profile_name: str) -> tuple[dict, dict]:
    live_cfg = load_config(LIVE_TOML)
    with open(EXEC_CONFIGS_PATH) as f:
        exec_cfgs = json.load(f)
    profile = exec_cfgs[profile_name]
    return live_cfg, profile


def _toml_session_overrides(live_cfg: dict, sess_name: str) -> dict:
    session_overrides = live_cfg.get("sessions", {})
    toml_key = sess_name.lower().replace("_", ".")
    out: dict = session_overrides
    for part in toml_key.split("."):
        if isinstance(out, dict):
            out = out.get(part, {})
        else:
            out = {}
            break
    return out if isinstance(out, dict) else {}


def _normalize_excluded_dow(value) -> tuple[int, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(int(x) for x in value)
    return (int(value),)


def _build_continuation_leg(
    sess_name: str,
    live_cfg: dict,
    profile: dict,
) -> BuiltLeg:
    base = SESSION_CONFIGS[sess_name]
    merged = {
        **base,
        **_toml_session_overrides(live_cfg, sess_name),
        **profile.get("sessions", {}).get(sess_name, {}),
    }
    risk = live_cfg.get("risk", {})
    dates = live_cfg.get("dates", {})

    session_label = sess_name.split("_", 1)[1]
    session = SessionConfig(
        name=session_label,
        orb_start=merged["orb_start"],
        orb_end=merged["orb_end"],
        entry_start=merged["entry_start"],
        entry_end=merged["entry_end"],
        flat_start=merged["flat_start"],
        flat_end=merged["flat_end"],
        stop_atr_pct=float(merged.get("stop_atr_pct", 0.0)),
        min_gap_atr_pct=float(merged.get("min_gap_atr_pct", 0.0)),
        stop_orb_pct=float(merged.get("stop_orb_pct", 0.0)),
        min_gap_orb_pct=float(merged.get("min_gap_orb_pct", 0.0)),
        min_stop_points=float(merged.get("min_stop_pts", 0.0)),
        min_tp1_points=float(merged.get("min_tp1_pts", 0.0)),
    )

    long_only = bool(merged.get("long_only", True))
    cfg = StrategyConfig(
        sessions=(session,),
        instrument=get_instrument(merged.get("instrument", sess_name.split("_", 1)[0])),
        strategy="continuation",
        direction_filter="long" if long_only else "both",
        rr=float(merged["rr"]),
        tp1_ratio=float(merged["tp1_ratio"]),
        atr_length=int(merged.get("atr_length", 14)),
        min_vwap_distance_atr_pct=float(merged.get("min_vwap_distance_atr_pct", 0.0)),
        vwap_slope_lookback=int(merged.get("vwap_slope_lookback", 0)),
        risk_usd=5000.0,
        use_bar_magnifier=True,
        impulse_close_filter=bool(merged.get("icf_enabled", False)),
        half_days=tuple(merged.get("half_days", dates.get("half_days", ()))),
        excluded_dates=tuple(merged.get("excluded_dates", dates.get("excluded", ()))),
        name=sess_name,
    )
    return BuiltLeg(
        name=sess_name,
        symbol=cfg.instrument.symbol,
        strategy="continuation",
        config=cfg,
        excluded_dow=_normalize_excluded_dow(merged.get("excluded_dow")),
        session=session,
    )


def _lsi_rth_start(sess_name: str) -> str:
    if "_NY_" in f"{sess_name}_":
        return "09:30"
    if "_Asia_" in f"{sess_name}_":
        return "20:00"
    if "_LDN_" in f"{sess_name}_":
        return "03:00"
    return "09:30"


def _build_lsi_leg(
    sess_name: str,
    live_cfg: dict,
    profile: dict,
) -> BuiltLeg:
    base = LSI_SESSION_CONFIGS[sess_name]
    merged = {**base, **profile.get("lsi_sessions", {}).get(sess_name, {})}
    risk = live_cfg.get("risk", {})
    dates = live_cfg.get("dates", {})
    session_label = sess_name.split("_", 1)[1].replace("_LSI", "")

    session = SessionConfig(
        name=session_label,
        rth_start=_lsi_rth_start(sess_name),
        entry_start=merged["entry_start"],
        entry_end=merged["entry_end"],
        flat_start=merged["flat_start"],
        flat_end=merged["flat_end"],
        min_gap_atr_pct=float(merged.get("min_gap_atr_pct", 0.0)),
        min_stop_points=float(merged.get("min_stop_points", 0.0)),
    )

    long_only = bool(merged.get("long_only", True))
    cfg = StrategyConfig(
        sessions=(session,),
        instrument=get_instrument(merged.get("instrument", sess_name.split("_", 1)[0])),
        strategy="lsi",
        direction_filter="long" if long_only else "both",
        rr=float(merged["rr"]),
        tp1_ratio=float(merged["tp1_ratio"]),
        atr_length=int(merged.get("atr_length", 14)),
        risk_usd=5000.0,
        use_bar_magnifier=True,
        half_days=tuple(merged.get("half_days", dates.get("half_days", ()))),
        excluded_dates=tuple(merged.get("excluded_dates", dates.get("excluded", ()))),
        lsi_n_left=int(merged.get("lsi_n_left", 3)),
        lsi_n_right=int(merged.get("lsi_n_right", 3)),
        lsi_fvg_window_left=int(merged.get("fvg_window_left", 10)),
        lsi_fvg_window_right=int(merged.get("fvg_window_right", 5)),
        lsi_entry_mode=str(merged.get("lsi_entry_mode", "close")),
        name=sess_name,
    )
    return BuiltLeg(
        name=sess_name,
        symbol=cfg.instrument.symbol,
        strategy="lsi",
        config=cfg,
        excluded_dow=_normalize_excluded_dow(merged.get("excluded_dow")),
        session=session,
    )


def build_profile_legs(profile_name: str) -> dict[str, BuiltLeg]:
    live_cfg, profile = load_profile_raw(profile_name)
    session_names = list(profile.get("sessions", {}).keys()) + list(profile.get("lsi_sessions", {}).keys())
    legs: dict[str, BuiltLeg] = {}
    for sess_name in session_names:
        if sess_name in SESSION_CONFIGS:
            legs[sess_name] = _build_continuation_leg(sess_name, live_cfg, profile)
        else:
            legs[sess_name] = _build_lsi_leg(sess_name, live_cfg, profile)
    return legs


def build_fast_v2_legs() -> dict[str, BuiltLeg]:
    return build_profile_legs("FAST_V2")


def _map_daily_midpoint(df: pd.DataFrame) -> np.ndarray:
    daily = df.resample("1D").agg({"high": "max", "low": "min"}).dropna()
    mid = ((daily["high"] + daily["low"]) / 2.0).values
    mid = np.roll(mid, 1)
    mid[0] = np.nan

    daily_dates = daily.index.normalize().values
    bar_dates = df.index.normalize().values
    idx = np.searchsorted(daily_dates, bar_dates, side="right") - 1

    out = np.full(len(df), np.nan, dtype=np.float64)
    valid = (idx >= 0) & (idx < len(daily_dates))
    matching = valid & (daily_dates[np.clip(idx, 0, len(daily_dates) - 1)] == bar_dates)
    out[matching] = mid[idx[matching]]
    return out


def _map_overnight_mid_ny(df: pd.DataFrame) -> np.ndarray:
    """Map previous overnight midpoint to each NY-session bar date.

    Overnight window for NY date D:
    previous day 18:00 -> D 09:30 America/New_York.
    """
    out = np.full(len(df), np.nan, dtype=np.float64)
    norm_dates = pd.DatetimeIndex(df.index.normalize().unique()).sort_values()
    mid_by_date: dict[pd.Timestamp, float] = {}

    for date in norm_dates:
        start = date - pd.Timedelta(days=1) + pd.Timedelta(hours=18)
        end = date + pd.Timedelta(hours=9, minutes=30)
        window = df[(df.index >= start) & (df.index < end)]
        if window.empty:
            continue
        mid_by_date[date] = float((window["high"].max() + window["low"].min()) / 2.0)

    for date, mid in mid_by_date.items():
        mask = df.index.normalize() == date
        out[mask] = mid
    return out


def build_leg_context(df: pd.DataFrame, session: SessionConfig) -> LegContext:
    ts = df.index
    masks = compute_session_masks(ts, session)
    new_day, session_day_id = compute_session_days(ts, session)

    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    volume = df["volume"].values.astype(np.float64)

    vwap = compute_session_vwap(high, low, close, volume, session_day_id)
    orb_high, orb_low, _ = compute_orb_levels(df, masks["in_orb"], masks["in_rth"], new_day)
    prev_day_mid = _map_daily_midpoint(df)
    overnight_mid = _map_overnight_mid_ny(df) if session.name == "NY" else None

    return LegContext(
        close=close,
        vwap=vwap,
        orb_high=orb_high,
        orb_low=orb_low,
        prev_day_mid=prev_day_mid,
        overnight_mid=overnight_mid,
    )


def _aligned_direction(direction: int, lhs: float, rhs: float) -> bool:
    if np.isnan(lhs) or np.isnan(rhs):
        return False
    return (direction == 1 and lhs > rhs) or (direction == -1 and lhs < rhs)


def gate_trades(trades: list[TradeResult], ctx: LegContext, gate_name: str) -> list[TradeResult]:
    kept: list[TradeResult] = []
    close = ctx.close
    vwap = ctx.vwap

    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            continue
        s = t.signal_bar
        if s < 0 or s >= len(close):
            continue

        side_ok = _aligned_direction(t.direction, close[s], vwap[s])
        slope_ok = False
        if s >= 3 and not np.isnan(vwap[s]) and not np.isnan(vwap[s - 3]):
            slope_ok = (t.direction == 1 and vwap[s] > vwap[s - 3]) or (
                t.direction == -1 and vwap[s] < vwap[s - 3]
            )

        orb_ok = False
        if t.direction == 1:
            orb_ok = (
                not np.isnan(ctx.orb_high[s])
                and not np.isnan(vwap[s])
                and close[s] > ctx.orb_high[s]
                and close[s] > vwap[s]
            )
        else:
            orb_ok = (
                not np.isnan(ctx.orb_low[s])
                and not np.isnan(vwap[s])
                and close[s] < ctx.orb_low[s]
                and close[s] < vwap[s]
            )

        pd_mid_ok = _aligned_direction(t.direction, close[s], ctx.prev_day_mid[s])
        on_mid_ok = True
        if ctx.overnight_mid is not None:
            on_mid_ok = _aligned_direction(t.direction, close[s], ctx.overnight_mid[s])

        keep = False
        if gate_name == "baseline":
            keep = True
        elif gate_name == "vwap_side":
            keep = side_ok
        elif gate_name == "vwap_side_slope3":
            keep = side_ok and slope_ok
        elif gate_name == "orb_vwap_hold":
            keep = orb_ok
        elif gate_name == "pd_mid_bias":
            keep = pd_mid_ok
        elif gate_name == "on_mid_bias":
            keep = on_mid_ok
        elif gate_name == "combo":
            keep = side_ok and slope_ok and orb_ok and pd_mid_ok and on_mid_ok
        else:
            raise ValueError(f"Unknown gate: {gate_name}")

        if keep:
            kept.append(t)

    return kept


def filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    filtered = [t for t in trades if start <= t.date <= end]
    filtered.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return filtered


def _fmt_metric(m: dict) -> str:
    return (
        f"{m['total_trades']:>4} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:>7.1f} | Sharpe {m['sharpe_ratio']:>5.2f} | "
        f"Calmar {m['calmar_ratio']:>5.2f}"
    )


def _print_leg_table(
    title: str,
    baseline_trades: list[TradeResult],
    gated_sets: dict[str, list[TradeResult]],
    start: str,
    end: str,
) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    base_window = filter_window(baseline_trades, start, end)
    m_base = compute_metrics(base_window)
    print(f"  baseline         {_fmt_metric(m_base)}")
    for gate_name, trades in gated_sets.items():
        window = filter_window(trades, start, end)
        m = compute_metrics(window)
        keep_pct = (m["total_trades"] / m_base["total_trades"]) if m_base["total_trades"] else 0.0
        print(
            f"  {gate_name:<15} {_fmt_metric(m)} | keep {keep_pct:>5.1%} | "
            f"dR {m['total_r'] - m_base['total_r']:+6.1f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="FAST_V2 NQ context-filter validation")
    parser.add_argument("--start", default=FULL_START, help="Backtest start date")
    parser.add_argument("--end", default="", help="Backtest end date (default: full data range)")
    args = parser.parse_args()

    t0 = time.time()
    print("FAST_V2 NQ Context Filters")
    print("=" * 80)
    print("Using merged live configs: execution main defaults + FAST_V2 profile overrides")

    legs = build_fast_v2_legs()
    all_fast_v2_legs = tuple(legs.keys())
    symbols = sorted({leg.symbol for leg in legs.values()})
    data_cache: dict[str, dict[str, pd.DataFrame]] = {}

    print("\nLoading data...")
    for symbol in symbols:
        df_5m = load_5m_data(f"{symbol}_5m.parquet", start=args.start, end=args.end or None)
        df_1m = load_1m_for_5m(f"{symbol}_5m.parquet", start=args.start, end=args.end or None)
        data_cache[symbol] = {"5m": df_5m, "1m": df_1m}
        print(f"  {symbol}: 5m={len(df_5m):,}, 1m={len(df_1m):,}")

    if not args.end:
        any_symbol = symbols[0]
        args.end = data_cache[any_symbol]["5m"].index[-1].strftime("%Y-%m-%d")

    print(f"\nBacktest window: {args.start} -> {args.end}")

    all_leg_trades: dict[str, list[TradeResult]] = {}
    contexts: dict[str, LegContext] = {}

    print("\nRunning FAST_V2 legs...")
    for leg_name in all_fast_v2_legs:
        leg = legs[leg_name]
        df_5m = data_cache[leg.symbol]["5m"]
        df_1m = data_cache[leg.symbol]["1m"]
        start_t = time.time()
        trades = run_backtest(df_5m, leg.config, start_date=args.start, end_date=args.end, df_1m=df_1m)
        if leg.excluded_dow:
            trades = apply_dow_filter(trades, set(leg.excluded_dow))
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        filled.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
        all_leg_trades[leg_name] = filled
        print(
            f"  {leg_name:12s} {len(filled):>4} fills | "
            f"{compute_metrics(filled)['total_r']:>7.1f}R [{time.time() - start_t:.1f}s]"
        )
        if leg_name in CONTINUATION_LEGS:
            contexts[leg_name] = build_leg_context(df_5m, leg.session)

    gate_names = (
        "vwap_side",
        "vwap_side_slope3",
        "orb_vwap_hold",
        "pd_mid_bias",
        "on_mid_bias",
        "combo",
    )

    gated_legs: dict[str, dict[str, list[TradeResult]]] = {}
    for leg_name in CONTINUATION_LEGS:
        gated_legs[leg_name] = {}
        for gate_name in gate_names:
            if gate_name == "on_mid_bias" and leg_name != "NQ_NY":
                continue
            gated_legs[leg_name][gate_name] = gate_trades(all_leg_trades[leg_name], contexts[leg_name], gate_name)

    full_window_start = args.start
    recent_window_start = max(RECENT_START, args.start)
    show_recent = recent_window_start <= args.end

    print("\nPer-leg continuation results")
    print("=" * 80)
    for leg_name in CONTINUATION_LEGS:
        _print_leg_table(
            f"{leg_name} | Full ({full_window_start} -> {args.end})",
            all_leg_trades[leg_name],
            gated_legs[leg_name],
            full_window_start,
            args.end,
        )
        if show_recent and recent_window_start > full_window_start:
            _print_leg_table(
                f"{leg_name} | Recent ({recent_window_start} -> {args.end})",
                all_leg_trades[leg_name],
                gated_legs[leg_name],
                recent_window_start,
                args.end,
            )

    combined_nq_orb_base = sorted(
        all_leg_trades["NQ_NY"] + all_leg_trades["NQ_Asia"],
        key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session),
    )
    print("\nCombined NQ ORB results")
    print("=" * 80)
    combined_nq_gates: dict[str, list[TradeResult]] = {}
    for gate_name in gate_names:
        if gate_name == "on_mid_bias":
            continue
        ny_trades = gated_legs["NQ_NY"].get(gate_name, all_leg_trades["NQ_NY"])
        asia_trades = gated_legs["NQ_Asia"].get(gate_name, all_leg_trades["NQ_Asia"])
        combined = ny_trades + asia_trades
        combined.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
        combined_nq_gates[gate_name] = combined

    _print_leg_table(
        f"NQ_ORB | Full ({full_window_start} -> {args.end})",
        combined_nq_orb_base,
        combined_nq_gates,
        full_window_start,
        args.end,
    )
    if show_recent and recent_window_start > full_window_start:
        _print_leg_table(
            f"NQ_ORB | Recent ({recent_window_start} -> {args.end})",
            combined_nq_orb_base,
            combined_nq_gates,
            recent_window_start,
            args.end,
        )

    print("\nFAST_V2 portfolio impact")
    print("=" * 80)
    fast_v2_base = []
    for leg_name in all_fast_v2_legs:
        fast_v2_base.extend(all_leg_trades[leg_name])
    fast_v2_base.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))

    portfolio_gates: dict[str, list[TradeResult]] = {}
    for gate_name in gate_names:
        if gate_name == "on_mid_bias":
            continue
        combined = []
        combined.extend(gated_legs["NQ_NY"].get(gate_name, all_leg_trades["NQ_NY"]))
        combined.extend(gated_legs["NQ_Asia"].get(gate_name, all_leg_trades["NQ_Asia"]))
        combined.extend(all_leg_trades["ES_Asia"])
        combined.extend(all_leg_trades["NQ_Asia_LSI"])
        combined.extend(all_leg_trades["NQ_NY_LSI"])
        combined.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
        portfolio_gates[gate_name] = combined

    _print_leg_table(
        f"FAST_V2 | Full ({full_window_start} -> {args.end})",
        fast_v2_base,
        portfolio_gates,
        full_window_start,
        args.end,
    )
    if show_recent and recent_window_start > full_window_start:
        _print_leg_table(
            f"FAST_V2 | Recent ({recent_window_start} -> {args.end})",
            fast_v2_base,
            portfolio_gates,
            recent_window_start,
            args.end,
        )

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
