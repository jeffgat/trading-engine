#!/usr/bin/env python3
"""NQ Asia Wide Sharpe — long-only direction test.

Variable sweep showed long outperforms short on avg Sharpe (2.398 vs 1.849).
Tests long-only vs both-directions at entry_end 22:30 and 23:00.

Base: stop=5.0%, gap=1.50%, maxgap=5.0%, rr=1.25, tp1=0.10, ORB 10m, ATR 14
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

START_DATE = "2015-01-01"

RUNS = [
    dict(direction="both",  entry_end="23:00", label="Both / 23:00 (baseline)"),
    dict(direction="both",  entry_end="22:30", label="Both / 22:30"),
    dict(direction="long",  entry_end="23:00", label="Long only / 23:00"),
    dict(direction="long",  entry_end="22:30", label="Long only / 22:30"),
]


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config(direction, entry_end):
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end=entry_end,
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.50,
        max_gap_atr_pct=5.0,
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=1.25,
        tp1_ratio=0.10,
        use_bar_magnifier=True,
        atr_length=14,
        direction_filter=direction,
    )


def main():
    print("NQ Asia Wide Sharpe — Long-Only Direction Test")
    print("=" * 70)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} [{time.time()-t0:.1f}s]\n")

    results = []

    for run in RUNS:
        cfg = build_config(run["direction"], run["entry_end"])
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)
        m = compute_metrics(trades)
        results.append({**run, "m": m})

        print(f"  {run['label']}")
        print(f"    Trades: {m['total_trades']}  WR: {m['win_rate']:.1%}  "
              f"Net R: {m['total_r']:.1f}  DD: {m['max_drawdown_r']:.1f}R  "
              f"Sharpe: {m['sharpe_ratio']:.3f}  PF: {m['profit_factor']:.2f}  "
              f"Calmar: {m.get('calmar_ratio',0):.2f}")
        print(f"    Long: {m.get('long_trades',0)} trades, {m.get('long_win_rate',0):.1%} WR  |  "
              f"Short: {m.get('short_trades',0)} trades, {m.get('short_win_rate',0):.1%} WR")

        r_by_year = m.get("r_by_year", {})
        neg_years = {yr: r for yr, r in r_by_year.items() if r < 0}
        print(f"    Negative years: {neg_years if neg_years else 'None'}")
        print()

    # Comparison table
    print("=" * 70)
    print(f"{'Config':<26} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | "
          f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7}")
    print("-" * 70)
    for r in results:
        m = r["m"]
        print(f"  {r['label']:<24} | {m['total_trades']:>6} | {m['win_rate']:>5.1%} | "
              f"{m['total_r']:>7.1f} | {m['max_drawdown_r']:>6.1f} | "
              f"{m['sharpe_ratio']:>7.3f} | {m.get('calmar_ratio',0):>7.2f}")

    # Year-by-year comparison
    print("\nYear-by-year R:")
    years = sorted(set(yr for r in results for yr in r["m"].get("r_by_year", {})))
    header = f"  {'Year':>4} |" + "".join(f" {r['label'][:16]:>16} |" for r in results)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for yr in years:
        row = f"  {yr:>4} |"
        for r in results:
            val = r["m"].get("r_by_year", {}).get(yr, 0)
            row += f" {val:>15.1f}R |"
        print(row)

    # Save the two long-only configs
    print("\n" + "=" * 70)
    print("SAVING LONG-ONLY CONFIGS")
    print("=" * 70)

    for run in [r for r in results if r["direction"] == "long"]:
        m = run["m"]
        name = (
            f"NQ ASIA 2015-2026 Wide Long-Only "
            f"{'22:30' if run['entry_end'] == '22:30' else '23:00'} PRE-PIPELINE"
        )
        notes = (
            f"Long-only variant of Wide Sharpe. Variable sweep showed long avg Sharpe "
            f"2.398 vs 1.849 short. entry_end={run['entry_end']}, direction=long. "
            f"{m['total_trades']} trades, {m['win_rate']:.1%} WR, "
            f"{m['total_r']:.1f}R, {m['max_drawdown_r']:.1f}R DD, "
            f"Sharpe {m['sharpe_ratio']:.3f}. Next: robust pipeline."
        )
        cfg = build_config(run["direction"], run["entry_end"])
        cfg = with_overrides(cfg, name=name, notes=notes)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)
        result = results_to_dict(trades, cfg, include_equity_curve=True)
        rid = save_backtest_result(result)
        print(f"  {rid}")
        print(f"  {name}")
        print(f"  {m['total_trades']} trades, {m['win_rate']:.1%} WR, "
              f"{m['total_r']:.1f}R, {m['max_drawdown_r']:.1f}R DD, "
              f"Sharpe {m['sharpe_ratio']:.3f}\n")

    print(f"Total runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
