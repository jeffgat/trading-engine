#!/usr/bin/env python3
"""NQ Asia Wide — stop/gap sweep to reduce DD.

Anchor: rr=2.0, tp1=0.35, atr=14, be=0, ORB 10m, entry≤22:30, no-Thursday
Current: 142.2R net, 13.0R/yr avg, -16.2R DD, Sharpe 1.744

Goal: tighten DD toward -10 to -12R without sacrificing much annual R.

Sweep:
  stop_atr_pct:    [3.0, 3.5, 4.0, 4.5, 5.0]
  min_gap_atr_pct: [1.25, 1.50, 1.75, 2.0, 2.25]
  max_gap_atr_pct: [3.0, 4.0, 5.0, 6.0]

Total: 5 × 5 × 4 = 100 combos
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
FULL_YEARS = [str(y) for y in range(2015, 2026)]

PARAM_RANGES = {
    "asia_stop_atr_pct":    [3.0, 3.5, 4.0, 4.5, 5.0],
    "asia_min_gap_atr_pct": [1.25, 1.50, 1.75, 2.0, 2.25],
    "asia_max_gap_atr_pct": [3.0, 4.0, 5.0, 6.0],
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


def extract_row(config, metrics):
    sess = config.sessions[0]
    r_by_year   = metrics.get("r_by_year", {})
    neg_full    = {yr: round(r, 1) for yr, r in r_by_year.items()
                  if r < 0 and yr in FULL_YEARS}
    full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
    avg_annual  = round(sum(full_year_r) / len(full_year_r), 1) if full_year_r else 0
    return {
        "stop":       sess.stop_atr_pct,
        "gap":        sess.min_gap_atr_pct,
        "maxgap":     sess.max_gap_atr_pct,
        "trades":     metrics["total_trades"],
        "wr":         metrics["win_rate"],
        "net_r":      round(metrics["total_r"], 1),
        "avg_annual": avg_annual,
        "max_dd_r":   round(metrics["max_drawdown_r"], 1),
        "sharpe":     round(metrics["sharpe_ratio"], 3),
        "calmar":     round(metrics.get("calmar_ratio", 0), 2),
        "r_per_trade": round(metrics["avg_r"], 4),
        "neg_full":   len(neg_full),
        "neg_detail": neg_full,
        "r_by_year":  r_by_year,
    }


HDR = (
    f"{'#':>3} | {'stop%':>5} | {'gap%':>5} | {'mg%':>4} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7} | {'NegFYr':>6}"
)


def print_table(rows, label, n=10):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        neg = f"{r['neg_detail']}" if r["neg_detail"] else "-"
        print(
            f"{i:>3} | {r['stop']:>5.1f} | {r['gap']:>5.2f} | {r['maxgap']:>4.1f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
            f"{r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | {r['calmar']:>7.2f} | {neg}"
        )


def marginal(results, key, label, values):
    print(f"\n  {label}:")
    print(f"  {'Value':>6} | {'Sharpe':>7} | {'Avg/Yr':>7} | {'Net R':>7} | {'DD R':>6} | {'NegFYr':>6}")
    print("  " + "-" * 48)
    for v in values:
        subset = [r for r in results if r[key] == v]
        if not subset:
            continue
        n = len(subset)
        print(f"  {v:>6} | "
              f"{sum(r['sharpe'] for r in subset)/n:>7.3f} | "
              f"{sum(r['avg_annual'] for r in subset)/n:>7.1f} | "
              f"{sum(r['net_r'] for r in subset)/n:>7.1f} | "
              f"{sum(r['max_dd_r'] for r in subset)/n:>6.1f} | "
              f"{sum(r['neg_full'] for r in subset)/n:>6.2f}")


def main():
    print("NQ Asia Wide — Stop/Gap DD Reduction Sweep")
    print("Anchor: rr=2.0, tp1=0.35, atr=14, be=0")
    print("Baseline: 142.2R, 13.0R/yr, -16.2R DD, Sharpe 1.744")
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
        ) if done == total else None,
    )
    print(f"\n  Done in {time.time()-t1:.0f}s")

    results = []
    for cfg, trades in raw:
        gated  = no_thursday_gate(trades)
        filled = [t for t in gated if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 10:
            continue
        m = compute_metrics(gated)
        results.append(extract_row(cfg, m))

    by_dd      = sorted(results, key=lambda r: r["max_dd_r"], reverse=True)  # least negative
    by_annual  = sorted(results, key=lambda r: r["avg_annual"], reverse=True)
    by_sharpe  = sorted(results, key=lambda r: r["sharpe"], reverse=True)

    # Key filter: DD <= -12R and avg annual R >= 10R and zero negative full years
    viable = sorted(
        [r for r in results if r["max_dd_r"] >= -12.0
         and r["avg_annual"] >= 10.0 and r["neg_full"] == 0],
        key=lambda r: r["avg_annual"], reverse=True,
    )

    print_table(by_dd,     "Best DD (least negative)")
    print_table(by_annual, "Best Avg Annual R")
    print_table(by_sharpe, "Best Sharpe")
    print_table(viable,    "Sweet Spot: DD ≥ -12R, Avg/Yr ≥ 10R, 0 neg years")

    print("\n" + "=" * 70)
    print("MARGINAL ANALYSIS")
    print("=" * 70)
    marginal(results, "stop",   "stop_atr_pct",    PARAM_RANGES["asia_stop_atr_pct"])
    marginal(results, "gap",    "min_gap_atr_pct",  PARAM_RANGES["asia_min_gap_atr_pct"])
    marginal(results, "maxgap", "max_gap_atr_pct",  PARAM_RANGES["asia_max_gap_atr_pct"])

    # DD grid: stop × gap (at best maxgap)
    stops  = PARAM_RANGES["asia_stop_atr_pct"]
    gaps   = PARAM_RANGES["asia_min_gap_atr_pct"]
    maxgaps = PARAM_RANGES["asia_max_gap_atr_pct"]

    for mg in maxgaps:
        print(f"\n--- DD grid (stop × gap) at maxgap={mg}% ---")
        print(f"{'gap→':>6}", end="")
        for g in gaps:
            print(f" {g:>6.2f}", end="")
        print()
        print("-" * (7 + 7 * len(gaps)))
        for s in stops:
            print(f"s={s:<4}", end="")
            for g in gaps:
                row = next((r for r in results
                            if r["stop"] == s and r["gap"] == g and r["maxgap"] == mg), None)
                val = f"{row['max_dd_r']:>6.1f}" if row else "   n/a"
                print(f" {val}", end="")
            print()

    # Year-by-year for sweet spot #1
    if viable:
        r = viable[0]
        print(f"\n--- Year-by-year: Sweet Spot #1 "
              f"(stop={r['stop']}, gap={r['gap']}, maxgap={r['maxgap']}) ---")
        print(f"  Net R={r['net_r']}, Avg/Yr={r['avg_annual']}, "
              f"DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        for yr, yr_r in sorted(r["r_by_year"].items()):
            flag = " <-- NEG" if yr_r < 0 and yr in FULL_YEARS else ""
            print(f"  {yr}: {yr_r:>7.1f}R{flag}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
