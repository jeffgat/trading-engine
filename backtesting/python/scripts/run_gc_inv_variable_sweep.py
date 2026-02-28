#!/usr/bin/env python3
"""Sweep atr_length, entry_end, and max_gap_points for GC NY Inversion Longs.

Base: rr=3.0, tp1=0.3, stop=9.0%, gap=1.25%, be=10 ticks, magnifier ON.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")


def build_config(atr_length=30, entry_end="14:00", max_gap_points=25.0):
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=atr_length,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(session,),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


ATR_LENGTHS = [10, 14, 20, 30, 40, 50]
ENTRY_ENDS = ["11:00", "12:00", "13:00", "14:00", "15:00"]
MAX_GAP_PTS = [10.0, 15.0, 20.0, 25.0, 35.0, 50.0, 100.0]

BASELINE = {"atr_length": 30, "entry_end": "14:00", "max_gap_points": 25.0}

# Base config: GC NY Inversion Longs Robust Pipeline Conditional GO
# rr=3.5, tp1=0.2, stop=9.0%, min_gap=1.0%, be=10 ticks, magnifier ON


def run_single_sweep(df, df_1m, param_name, values, build_fn):
    """Sweep one param, holding others at baseline."""
    results = []
    for val in values:
        kwargs = dict(BASELINE)
        kwargs[param_name] = val
        config = build_config(**kwargs)
        trades = run_backtest(df, config, start_date="2016-01-01", df_1m=df_1m)
        m = compute_metrics(trades)
        results.append((val, m))
    return results


def print_sweep(param_name, results, baseline_val):
    print(f"\n{'='*80}")
    print(f"  SWEEP: {param_name} (baseline = {baseline_val})")
    print(f"{'='*80}")
    print(f"  {'Value':>10s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s} {'Avg R':>7s} {'Calmar':>7s}")
    print(f"  {'-'*65}")
    for val, m in results:
        marker = " <-- base" if str(val) == str(baseline_val) else ""
        print(
            f"  {str(val):>10s} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
            f"{m['total_r']:>7.1f} {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} "
            f"{m['max_drawdown_r']:>7.1f} {m['avg_r']:>7.3f} {m['calmar_ratio']:>7.2f}{marker}"
        )


def main():
    print("Loading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    # Sweep 1: atr_length
    print("\nSweeping atr_length...")
    t0 = time.time()
    atr_results = run_single_sweep(df, df_1m, "atr_length", ATR_LENGTHS, build_config)
    print(f"  Done in {time.time() - t0:.1f}s")
    print_sweep("atr_length", atr_results, BASELINE["atr_length"])

    # Sweep 2: entry_end
    print("\nSweeping entry_end...")
    t0 = time.time()
    entry_results = run_single_sweep(df, df_1m, "entry_end", ENTRY_ENDS, build_config)
    print(f"  Done in {time.time() - t0:.1f}s")
    print_sweep("entry_end", entry_results, BASELINE["entry_end"])

    # Sweep 3: max_gap_points
    print("\nSweeping max_gap_points...")
    t0 = time.time()
    gap_results = run_single_sweep(df, df_1m, "max_gap_points", MAX_GAP_PTS, build_config)
    print(f"  Done in {time.time() - t0:.1f}s")
    print_sweep("max_gap_points", gap_results, BASELINE["max_gap_points"])

    print()


if __name__ == "__main__":
    main()
