#!/usr/bin/env python3
"""NQ Asia Wide — high-R sweep. Prioritising annual R over win rate.

Base: stop=5.0%, gap=1.50%, maxgap=5.0%, ORB 10m, ATR 14,
      entry≤22:30, both dirs, no-Thursday, be=0

Sweep:
  rr:        [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
  tp1_ratio: [0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70]

Total: 7 × 7 = 49 combos
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
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
FULL_YEARS = [str(y) for y in range(2015, 2026)]  # exclude partial 2026

PARAM_RANGES = {
    "rr":        [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
    "tp1_ratio": [0.25, 0.30, 0.35, 0.40, 0.50, 0.60, 0.70],
}


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def base_config():
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
        rr=2.0,
        tp1_ratio=0.30,
        use_bar_magnifier=True,
        atr_length=14,
    )


def extract_row(config, metrics):
    r_by_year = metrics.get("r_by_year", {})
    neg_full  = {yr: round(r, 1) for yr, r in r_by_year.items()
                 if r < 0 and yr in FULL_YEARS}
    full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
    avg_annual  = sum(full_year_r) / len(full_year_r) if full_year_r else 0
    return {
        "rr":         config.rr,
        "tp1":        config.tp1_ratio,
        "trades":     metrics["total_trades"],
        "wr":         metrics["win_rate"],
        "net_r":      round(metrics["total_r"], 1),
        "max_dd_r":   round(metrics["max_drawdown_r"], 1),
        "sharpe":     round(metrics["sharpe_ratio"], 3),
        "pf":         round(metrics["profit_factor"], 2),
        "calmar":     round(metrics.get("calmar_ratio", 0), 2),
        "r_per_trade": round(metrics["avg_r"], 4),
        "avg_annual": round(avg_annual, 1),
        "neg_full":   len(neg_full),
        "neg_detail": neg_full,
        "r_by_year":  r_by_year,
    }


HDR = (
    f"{'#':>3} | {'rr':>4} | {'tp1':>4} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | {'DD R':>6} | "
    f"{'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>6} | {'NegFYr':>6}"
)


def print_table(rows, label, n=10):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        neg = f"{r['neg_full']}  {r['neg_detail']}" if r["neg_detail"] else "0"
        print(
            f"{i:>3} | {r['rr']:>4.1f} | {r['tp1']:>4.2f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
            f"{r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | {r['calmar']:>7.2f} | "
            f"{r['r_per_trade']:>6.4f} | {neg}"
        )


def main():
    print("NQ Asia Wide — High-R Sweep (rr × tp1)")
    print("Optimising for annual R, accepting lower WR")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]")

    configs = generate_param_grid(base_config(), PARAM_RANGES)
    print(f"\nGrid: {len(configs)} combos (rr × tp1, atr=14, be=0)")
    print(f"Running with 8 workers...", flush=True)

    t1 = time.time()
    raw = run_sweep(
        df, configs, n_workers=8, start_date=START_DATE, df_1m=df_1m,
        progress_fn=lambda done, total: print(
            f"\r  {done}/{total}", end="", flush=True
        ) if done == total else None,
    )
    print(f"\n  Done in {time.time()-t1:.0f}s")

    results = []
    for cfg, trades in raw:
        gated = no_thursday_gate(trades)
        filled = [t for t in gated if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 10:
            continue
        m = compute_metrics(gated)
        results.append(extract_row(cfg, m))

    by_annual = sorted(results, key=lambda r: r["avg_annual"], reverse=True)
    by_net_r  = sorted(results, key=lambda r: r["net_r"], reverse=True)
    by_sharpe = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    clean     = sorted(
        [r for r in results if r["neg_full"] == 0],
        key=lambda r: r["avg_annual"], reverse=True,
    )

    print_table(by_annual,  "Best Average Annual R (full years only)")
    print_table(by_net_r,   "Best Net R (total)")
    print_table(by_sharpe,  "Best Sharpe")
    print_table(clean,      "Clean full years (0 neg), by Avg Annual R")

    # Grid heatmap: rr vs tp1 for avg_annual R
    rr_vals  = PARAM_RANGES["rr"]
    tp1_vals = PARAM_RANGES["tp1_ratio"]

    print(f"\n--- Avg Annual R grid (rr × tp1) ---")
    print(f"{'tp1→':>6}", end="")
    for tp1 in tp1_vals:
        print(f" {tp1:>6.2f}", end="")
    print()
    print("-" * (7 + 7 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"rr={rr:<4}", end="")
        for tp1 in tp1_vals:
            row = next((r for r in results if r["rr"] == rr and r["tp1"] == tp1), None)
            val = f"{row['avg_annual']:>6.1f}" if row else "   n/a"
            print(f" {val}", end="")
        print()

    print(f"\n--- Net R grid (rr × tp1) ---")
    print(f"{'tp1→':>6}", end="")
    for tp1 in tp1_vals:
        print(f" {tp1:>6.2f}", end="")
    print()
    print("-" * (7 + 7 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"rr={rr:<4}", end="")
        for tp1 in tp1_vals:
            row = next((r for r in results if r["rr"] == rr and r["tp1"] == tp1), None)
            val = f"{row['net_r']:>6.1f}" if row else "   n/a"
            print(f" {val}", end="")
        print()

    print(f"\n--- Neg full years grid (rr × tp1) ---")
    print(f"{'tp1→':>6}", end="")
    for tp1 in tp1_vals:
        print(f" {tp1:>6.2f}", end="")
    print()
    print("-" * (7 + 7 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"rr={rr:<4}", end="")
        for tp1 in tp1_vals:
            row = next((r for r in results if r["rr"] == rr and r["tp1"] == tp1), None)
            val = f"{row['neg_full']:>6}" if row else "   n/a"
            print(f" {val}", end="")
        print()

    # Year-by-year for best annual R config
    if by_annual:
        r = by_annual[0]
        print(f"\n--- Year-by-year: Best Avg Annual R (rr={r['rr']}, tp1={r['tp1']}) ---")
        print(f"  Avg annual R (full years): {r['avg_annual']:.1f}R")
        for yr, yr_r in sorted(r["r_by_year"].items()):
            flag = " <-- NEG" if yr_r < 0 and yr in FULL_YEARS else ""
            print(f"  {yr}: {yr_r:>7.1f}R{flag}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
