#!/usr/bin/env python3
"""NQ Asia Wide — RR sweep from 1.0 to 5.0.

Base: stop=5.0%, gap=1.50%, maxgap=5.0%, ORB 10m, ATR 14,
      entry≤22:30, both dirs, no-Thursday, be=0
"""

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"

RR_VALUES = [1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config(rr):
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="22:30",
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.50,
        max_gap_atr_pct=5.0,
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=rr,
        tp1_ratio=0.10,
        use_bar_magnifier=True,
        atr_length=14,
    )


def main():
    print("NQ Asia Wide — RR Sweep (1.0 → 5.0)")
    print("Base: stop=5%, gap=1.5%, maxgap=5%, ORB 10m, ATR 14, entry≤22:30, be=0")
    print()

    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m\n")

    results = []
    for rr in RR_VALUES:
        cfg = build_config(rr)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)
        m = compute_metrics(trades)
        results.append({"rr": rr, "m": m})
        print(f"  rr={rr:.2f}  trades={m['total_trades']:>4}  WR={m['win_rate']:.1%}  "
              f"Net R={m['total_r']:>7.1f}  DD={m['max_drawdown_r']:>5.1f}R  "
              f"Sharpe={m['sharpe_ratio']:.3f}  R/trd={m['avg_r']:.4f}",
              flush=True)

    # Summary table
    print()
    print("=" * 90)
    print(f"{'rr':>5} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'DD R':>6} | "
          f"{'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'R/trd':>7} | {'Neg Yrs':>7}")
    print("-" * 90)
    for r in results:
        m = r["m"]
        neg_yrs = sum(1 for v in m.get("r_by_year", {}).values() if v < 0)
        print(f"{r['rr']:>5.2f} | {m['total_trades']:>6} | {m['win_rate']:>5.1%} | "
              f"{m['total_r']:>7.1f} | {m['max_drawdown_r']:>6.1f} | "
              f"{m['sharpe_ratio']:>7.3f} | {m['profit_factor']:>5.2f} | "
              f"{m.get('calmar_ratio',0):>7.2f} | {m['avg_r']:>7.4f} | {neg_yrs:>7}")

    # Year-by-year
    print()
    print("Year-by-year R:")
    years = sorted(set(yr for r in results for yr in r["m"].get("r_by_year", {})))
    hdr = f"  {'Year':>4} |" + "".join(f" {'rr='+str(r['rr']):>8} |" for r in results)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for yr in years:
        row = f"  {yr:>4} |"
        for r in results:
            val = r["m"].get("r_by_year", {}).get(yr, 0)
            row += f" {val:>7.1f}R |"
        print(row)


if __name__ == "__main__":
    main()
