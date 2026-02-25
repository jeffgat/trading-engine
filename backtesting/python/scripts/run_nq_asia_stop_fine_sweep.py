#!/usr/bin/env python3
"""NQ Asia — Fine stop ATR% sweep, 3.5% to 4.5% in 0.1 increments.

Anchor: gap=0.75%, maxgap=5.0%, rr=2.0, tp1=0.35, entry≤22:30,
        ORB 10m, ATR 14, be=0, no-Thursday, both dirs
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

START_DATE = "2015-01-01"
FULL_YEARS = [str(y) for y in range(2015, 2026)]

STOP_VALUES = [round(x * 0.1, 1) for x in range(35, 46)]  # 3.5 to 4.5


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config(stop):
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="22:30",
        stop_atr_pct=stop,
        min_gap_atr_pct=0.75,
        max_gap_atr_pct=5.0,
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=2.0,
        tp1_ratio=0.35,
        use_bar_magnifier=True,
        atr_length=14,
    )


def main():
    print("NQ Asia — Fine Stop Sweep (3.5% → 4.5% in 0.1 steps)")
    print("Anchor: gap=0.75%, maxgap=5%, rr=2.0, tp1=0.35, entry≤22:30, ATR 14, be=0, no-Thu")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]\n")

    results = []
    for stop in STOP_VALUES:
        cfg    = build_config(stop)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

        m = compute_metrics(trades)
        r_by_year   = m.get("r_by_year", {})
        full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
        avg_annual  = sum(full_year_r) / len(full_year_r) if full_year_r else 0
        neg_full    = {yr: round(r, 1) for yr, r in r_by_year.items()
                       if r < 0 and yr in FULL_YEARS}

        results.append({
            "stop":       stop,
            "trades":     m["total_trades"],
            "filled":     len(filled),
            "wr":         m["win_rate"],
            "net_r":      round(m["total_r"], 1),
            "avg_annual": round(avg_annual, 1),
            "max_dd_r":   round(m["max_drawdown_r"], 1),
            "calmar":     round(m.get("calmar_ratio", 0), 2),
            "r_per_trade": round(m["avg_r"], 4),
            "neg_full":   len(neg_full),
            "neg_detail": neg_full,
            "r_by_year":  r_by_year,
        })

    # Summary table
    print(f"{'stop%':>6} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
          f"{'DD R':>6} | {'Calmar':>7} | {'R/trd':>7} | {'NegFYr':>6}")
    print("-" * 80)
    for r in results:
        marker = "  <--" if r["stop"] == 4.0 else ""
        neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
        print(f"{r['stop']:>6.1f} | {r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | "
              f"{r['avg_annual']:>7.1f} | {r['max_dd_r']:>6.1f} | {r['calmar']:>7.2f} | "
              f"{r['r_per_trade']:>7.4f} | {neg}{marker}")

    # Year-by-year grid
    print(f"\n--- Year-by-year R by stop% ---")
    years = sorted(FULL_YEARS)
    print(f"{'stop%':>6} |" + "".join(f" {yr:>7} |" for yr in years))
    print("-" * (8 + 10 * len(years)))
    for r in results:
        row = f"{r['stop']:>6.1f} |"
        for yr in years:
            val  = r["r_by_year"].get(yr, 0.0)
            flag = "*" if val < 0 else " "
            row += f" {val:>6.1f}{flag}|"
        print(row)
    print("  * = negative year")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
