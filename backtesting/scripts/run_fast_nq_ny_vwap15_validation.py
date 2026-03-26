#!/usr/bin/env python3
"""Validate FAST NQ_NY baseline vs 15% ATR VWAP-distance research variant.

Focus:
- Full / recent / 2025 holdout metrics
- Monthly stability comparison
- Per-trade outcome distribution
"""

from __future__ import annotations

import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import (
    EXIT_NO_FILL,
    TradeResult,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics

from run_fast_v2_nq_context_filters import build_profile_legs

FULL_START = "2016-01-01"
RECENT_START = "2024-01-01"
HOLDOUT_START = "2025-01-01"
END_DATE = "2025-12-31"
VWAP_DISTANCE_ATR_PCT = 15.0


def filter_window(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    out = [t for t in trades if start <= t.date <= end]
    out.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return out


def clean_trades(trades: list[TradeResult], excluded_dow: tuple[int, ...]) -> list[TradeResult]:
    if excluded_dow:
        trades = apply_dow_filter(trades, set(excluded_dow))
    trades = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    trades.sort(key=lambda t: (t.fill_time or "", t.date, t.signal_bar, t.session))
    return trades


def metrics_line(trades: list[TradeResult], start: str, end: str) -> str:
    m = compute_metrics(filter_window(trades, start, end))
    return (
        f"{m['total_trades']:>4} tr | WR {m['win_rate']:.1%} | "
        f"R {m['total_r']:>7.1f} | Sharpe {m['sharpe_ratio']:.2f} | "
        f"Calmar {m['calmar_ratio']:.2f}"
    )


def trades_to_frame(trades: list[TradeResult]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["month", "date", "r_multiple", "exit_type"])
    rows = []
    for t in trades:
        ts = t.fill_time or t.date
        month = ts[:7]
        rows.append(
            {
                "month": month,
                "date": t.date,
                "r_multiple": float(t.r_multiple),
                "exit_type": t.exit_type,
            }
        )
    return pd.DataFrame(rows)


def monthly_table(trades: list[TradeResult]) -> pd.DataFrame:
    df = trades_to_frame(trades)
    if df.empty:
        return pd.DataFrame(columns=["month", "trades", "total_r", "win_rate", "avg_r"])
    monthly = (
        df.groupby("month", as_index=False)
        .agg(
            trades=("r_multiple", "size"),
            total_r=("r_multiple", "sum"),
            avg_r=("r_multiple", "mean"),
            win_rate=("r_multiple", lambda s: float((s > 0).mean())),
        )
        .sort_values("month")
    )
    return monthly


def print_monthly_summary(label: str, trades: list[TradeResult], *, recent_only: bool = False) -> None:
    window_start = RECENT_START if recent_only else FULL_START
    monthly = monthly_table(filter_window(trades, window_start, END_DATE))
    scope = "recent" if recent_only else "full"
    if monthly.empty:
        print(f"  {label} {scope} monthly: no trades")
        return
    pos = int((monthly["total_r"] > 0).sum())
    neg = int((monthly["total_r"] < 0).sum())
    flat = int((monthly["total_r"] == 0).sum())
    print(
        f"  {label} {scope} monthly: {len(monthly)} mo | +{pos} / -{neg} / ={flat} | "
        f"avg {monthly['total_r'].mean():.2f}R | median {monthly['total_r'].median():.2f}R | "
        f"worst {monthly['total_r'].min():.2f}R | best {monthly['total_r'].max():.2f}R"
    )


def compare_monthly(base: list[TradeResult], variant: list[TradeResult], *, recent_only: bool = False) -> None:
    window_start = RECENT_START if recent_only else FULL_START
    base_m = monthly_table(filter_window(base, window_start, END_DATE))
    var_m = monthly_table(filter_window(variant, window_start, END_DATE))
    merged = base_m.merge(var_m, on="month", how="outer", suffixes=("_base", "_var")).fillna(0.0)
    if merged.empty:
        return
    delta = merged["total_r_var"] - merged["total_r_base"]
    improved = int((delta > 0).sum())
    worsened = int((delta < 0).sum())
    unchanged = int((delta == 0).sum())
    scope = "recent" if recent_only else "full"
    print(
        f"  monthly delta {scope}: improved {improved}, worsened {worsened}, unchanged {unchanged}, "
        f"avg delta {delta.mean():.2f}R, median delta {delta.median():.2f}R"
    )


def print_trade_distribution(label: str, trades: list[TradeResult], *, start: str = FULL_START) -> None:
    windowed = filter_window(trades, start, END_DATE)
    rs = np.array([float(t.r_multiple) for t in windowed], dtype=np.float64)
    if len(rs) == 0:
        print(f"  {label} trade distribution: no trades")
        return
    wins = rs[rs > 0]
    losses = rs[rs < 0]
    flats = rs[rs == 0]
    exit_counts = Counter(t.exit_type for t in windowed)
    top_exits = ", ".join(f"{name}={count}" for name, count in exit_counts.most_common(5))
    print(
        f"  {label} trade distribution ({start} -> {END_DATE}): "
        f"wins {len(wins)}, losses {len(losses)}, flat {len(flats)} | "
        f"avg win {wins.mean():.2f}R | avg loss {losses.mean():.2f}R | "
        f"p10 {np.percentile(rs, 10):.2f}R | median {np.percentile(rs, 50):.2f}R | p90 {np.percentile(rs, 90):.2f}R"
    )
    print(f"    top exits: {top_exits}")


def run_leg(
    cfg: StrategyConfig,
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame,
    maps: dict,
    signal_cache: dict,
    excluded_dow: tuple[int, ...],
) -> list[TradeResult]:
    trades = run_backtest(
        df_5m,
        cfg,
        start_date=FULL_START,
        end_date=END_DATE,
        df_1m=df_1m,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    return clean_trades(trades, excluded_dow)


def main() -> None:
    t0 = time.time()
    print("FAST NQ_NY 15% ATR VWAP-Distance Validation")
    print("=" * 72)

    legs = build_profile_legs("FAST")
    leg = legs["NQ_NY"]
    base_cfg = leg.config
    variant_cfg = with_overrides(base_cfg, min_vwap_distance_atr_pct=VWAP_DISTANCE_ATR_PCT)

    print("\nLoading NQ data...")
    df_5m = load_5m_data("NQ_5m.parquet", start=FULL_START, end=END_DATE)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=FULL_START, end=END_DATE)
    maps = build_maps(df_5m, df_1m)
    signal_cache = build_signal_cache(df_5m, [base_cfg, variant_cfg])

    print("\nRunning baseline...")
    base_trades = run_leg(base_cfg, df_5m, df_1m, maps, signal_cache, leg.excluded_dow)
    print("Running 15% variant...")
    variant_trades = run_leg(variant_cfg, df_5m, df_1m, maps, signal_cache, leg.excluded_dow)

    print("\nMetrics")
    print("  baseline full   ", metrics_line(base_trades, FULL_START, END_DATE))
    print("  baseline recent ", metrics_line(base_trades, RECENT_START, END_DATE))
    print("  baseline holdout", metrics_line(base_trades, HOLDOUT_START, END_DATE))
    print("  variant full    ", metrics_line(variant_trades, FULL_START, END_DATE))
    print("  variant recent  ", metrics_line(variant_trades, RECENT_START, END_DATE))
    print("  variant holdout ", metrics_line(variant_trades, HOLDOUT_START, END_DATE))

    print("\nMonthly Stability")
    print_monthly_summary("baseline", base_trades, recent_only=False)
    print_monthly_summary("variant ", variant_trades, recent_only=False)
    compare_monthly(base_trades, variant_trades, recent_only=False)
    print_monthly_summary("baseline", base_trades, recent_only=True)
    print_monthly_summary("variant ", variant_trades, recent_only=True)
    compare_monthly(base_trades, variant_trades, recent_only=True)

    print("\nTrade Distribution")
    print_trade_distribution("baseline", base_trades, start=FULL_START)
    print_trade_distribution("variant ", variant_trades, start=FULL_START)
    print_trade_distribution("baseline", base_trades, start=RECENT_START)
    print_trade_distribution("variant ", variant_trades, start=RECENT_START)

    print(f"\nDone in {(time.time() - t0) / 60:.1f} minutes")


if __name__ == "__main__":
    main()
