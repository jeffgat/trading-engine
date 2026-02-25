#!/usr/bin/env python3
"""NQ Asia Wide — rr × tp1 × atr_length sweep.

Base: stop=5.0%, gap=1.50%, maxgap=5.0%, ORB 10m, entry≤22:30,
      both dirs, no-Thursday, be=0

Sweep:
  rr:         [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
  tp1_ratio:  [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
  atr_length: [5, 14]

Total: 6 × 8 × 2 = 96 combos
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
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"

PARAM_RANGES = {
    "rr":         [1.0, 1.25, 1.5, 2.0, 2.5, 3.0],
    "tp1_ratio":  [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50],
    "atr_length": [5, 14],
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
        rr=1.25,
        tp1_ratio=0.10,
        use_bar_magnifier=True,
        atr_length=14,
    )


def extract_row(config, metrics):
    neg_years = {yr: round(r, 1) for yr, r in metrics.get("r_by_year", {}).items() if r < 0}
    return {
        "rr":        config.rr,
        "tp1":       config.tp1_ratio,
        "atr":       config.atr_length,
        "trades":    metrics["total_trades"],
        "wr":        metrics["win_rate"],
        "net_r":     round(metrics["total_r"], 1),
        "max_dd_r":  round(metrics["max_drawdown_r"], 1),
        "sharpe":    round(metrics["sharpe_ratio"], 3),
        "pf":        round(metrics["profit_factor"], 2),
        "calmar":    round(metrics.get("calmar_ratio", 0), 2),
        "r_per_trade": round(metrics["avg_r"], 4),
        "neg_years": len(neg_years),
        "neg_detail": neg_years,
        "r_by_year": metrics.get("r_by_year", {}),
    }


HDR = (
    f"{'#':>3} | {'rr':>4} | {'tp1':>4} | {'atr':>3} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'DD R':>6} | "
    f"{'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'R/trd':>6} | {'NegYr':>5}"
)


def print_table(rows, label, n=10):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        print(
            f"{i:>3} | {r['rr']:>4.2f} | {r['tp1']:>4.2f} | {r['atr']:>3} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>6.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | "
            f"{r['r_per_trade']:>6.4f} | {r['neg_years']:>5}"
        )


def marginal(results, key, label, values):
    print(f"\n--- Marginal: {label} ---")
    print(f"  {'Value':>6} | {'Sharpe':>7} | {'Net R':>7} | {'DD R':>6} | {'WR':>6} | {'NegYr':>5}")
    print("  " + "-" * 44)
    best_sharpe = max(
        sum(r["sharpe"] for r in results if r[key] == v) / max(sum(1 for r in results if r[key] == v), 1)
        for v in values
    )
    for v in values:
        subset = [r for r in results if r[key] == v]
        if not subset:
            continue
        n = len(subset)
        avg_sh = sum(r["sharpe"] for r in subset) / n
        avg_nr = sum(r["net_r"] for r in subset) / n
        avg_dd = sum(r["max_dd_r"] for r in subset) / n
        avg_wr = sum(r["wr"] for r in subset) / n
        avg_ny = sum(r["neg_years"] for r in subset) / n
        marker = " <--" if abs(avg_sh - best_sharpe) < 1e-9 else ""
        print(f"  {str(v):>6} | {avg_sh:>7.3f} | {avg_nr:>7.1f} | {avg_dd:>6.1f} | "
              f"{avg_wr:>5.1%} | {avg_ny:>5.1f}{marker}")


def main():
    print("NQ Asia Wide — rr × tp1 × atr_length Sweep")
    print("Base: stop=5%, gap=1.5%, maxgap=5%, ORB 10m, entry≤22:30, be=0")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]")

    configs = generate_param_grid(base_config(), PARAM_RANGES)
    print(describe_grid(PARAM_RANGES))
    print(f"\nRunning {len(configs)} configs with 8 workers...", flush=True)

    t1 = time.time()
    raw = run_sweep(
        df, configs, n_workers=8, start_date=START_DATE, df_1m=df_1m,
        progress_fn=lambda done, total: print(
            f"\r  {done}/{total}", end="", flush=True
        ) if done % 16 == 0 or done == total else None,
    )
    print(f"\n  Done in {time.time()-t1:.0f}s", flush=True)

    results = []
    for cfg, trades in raw:
        gated = no_thursday_gate(trades)
        filled = [t for t in gated if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 10:
            continue
        m = compute_metrics(gated)
        results.append(extract_row(cfg, m))

    print(f"  Valid: {len(results)}/{len(raw)}")

    by_sharpe = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    by_net_r  = sorted(results, key=lambda r: r["net_r"], reverse=True)
    clean     = sorted(
        [r for r in results if r["neg_years"] == 0],
        key=lambda r: r["net_r"], reverse=True,
    )

    print_table(by_sharpe, "Best Sharpe")
    print_table(by_net_r,  "Best Net R")
    print_table(clean,     "Clean (zero negative years), by Net R")

    print("\n" + "=" * 80)
    print("MARGINAL ANALYSIS")
    print("=" * 80)
    marginal(results, "rr",  "RR",         PARAM_RANGES["rr"])
    marginal(results, "tp1", "tp1_ratio",  PARAM_RANGES["tp1_ratio"])
    marginal(results, "atr", "atr_length", PARAM_RANGES["atr_length"])

    # Year-by-year for #1 Sharpe
    if by_sharpe:
        r = by_sharpe[0]
        print(f"\n--- Year-by-year: #1 Sharpe (rr={r['rr']}, tp1={r['tp1']}, atr={r['atr']}) ---")
        for yr, yr_r in sorted(r["r_by_year"].items()):
            flag = " <--" if yr_r < 0 else ""
            print(f"  {yr}: {yr_r:>7.1f}R{flag}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
