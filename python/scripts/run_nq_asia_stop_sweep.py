#!/usr/bin/env python3
"""NQ Asia — Wide stop ATR% sweep.

Anchor: gap=0.75%, maxgap=5.0%, tp1=0.35, entry≤22:30, ORB 10m, ATR 14, be=0,
        no-Thursday, both dirs

Sweep:
  asia_stop_atr_pct: [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0]
  rr:                [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]

Total: 15 × 7 = 105 combos

Reporting prioritises: Avg Annual R, DD, Net R, Neg Full Years (no Sharpe focus).
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
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
FULL_YEARS = [str(y) for y in range(2015, 2026)]

STOP_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0, 20.0]
RR_VALUES   = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]

PARAM_RANGES = {
    "asia_stop_atr_pct": STOP_VALUES,
    "rr":                RR_VALUES,
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
        stop_atr_pct=4.0,
        min_gap_atr_pct=0.75,
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
        "rr":         config.rr,
        "trades":     metrics["total_trades"],
        "wr":         metrics["win_rate"],
        "net_r":      round(metrics["total_r"], 1),
        "avg_annual": avg_annual,
        "max_dd_r":   round(metrics["max_drawdown_r"], 1),
        "calmar":     round(metrics.get("calmar_ratio", 0), 2),
        "r_per_trade": round(metrics["avg_r"], 4),
        "neg_full":   len(neg_full),
        "neg_detail": neg_full,
        "r_by_year":  r_by_year,
    }


HDR = (
    f"{'#':>3} | {'stop%':>5} | {'rr':>4} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Calmar':>7} | {'R/trd':>7} | {'NegFYr':>6}"
)


def print_table(rows, label, n=15):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        neg = f"{r['neg_detail']}" if r["neg_detail"] else "-"
        print(
            f"{i:>3} | {r['stop']:>5.1f} | {r['rr']:>4.1f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
            f"{r['max_dd_r']:>6.1f} | {r['calmar']:>7.2f} | {r['r_per_trade']:>7.4f} | {neg}"
        )


def print_heatmap(results, metric, label, fmt=".1f"):
    print(f"\n--- {label} (stop × rr) ---")
    print(f"{'rr→':>7}", end="")
    for rr in RR_VALUES:
        print(f" {rr:>6.1f}", end="")
    print()
    print("-" * (8 + 7 * len(RR_VALUES)))
    for stop in STOP_VALUES:
        print(f"s={stop:<5}", end="")
        for rr in RR_VALUES:
            row = next((r for r in results if r["stop"] == stop and r["rr"] == rr), None)
            if row:
                val = row[metric]
                print(f" {val:>6{fmt}}", end="")
            else:
                print("    n/a", end="")
        print()


def marginal_stop(results):
    print(f"\n--- Marginal: stop_atr_pct (averaged across all rr values) ---")
    print(f"{'stop%':>6} | {'Avg/Yr':>7} | {'Net R':>7} | {'DD R':>6} | {'WR':>6} | {'Calmar':>7} | {'NegFYr':>6}")
    print("-" * 60)
    for stop in STOP_VALUES:
        subset = [r for r in results if r["stop"] == stop]
        if not subset:
            continue
        n = len(subset)
        print(
            f"{stop:>6.1f} | "
            f"{sum(r['avg_annual'] for r in subset)/n:>7.1f} | "
            f"{sum(r['net_r'] for r in subset)/n:>7.1f} | "
            f"{sum(r['max_dd_r'] for r in subset)/n:>6.1f} | "
            f"{sum(r['wr'] for r in subset)/n:>5.1%} | "
            f"{sum(r['calmar'] for r in subset)/n:>7.2f} | "
            f"{sum(r['neg_full'] for r in subset)/n:>6.2f}"
        )


def main():
    print("NQ Asia — Wide Stop ATR% Sweep")
    print("Anchor: gap=0.75%, maxgap=5%, tp1=0.35, entry≤22:30, ORB 10m, ATR 14, be=0, no-Thu")
    print("Reference: stop=4.0%, rr=2.0 → 17.0R/yr, -11.4R DD, 0 neg years")
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

    print(f"  Valid: {len(results)}/{len(raw)}")

    by_annual  = sorted(results, key=lambda r: r["avg_annual"], reverse=True)
    by_dd      = sorted(results, key=lambda r: r["max_dd_r"], reverse=True)
    by_calmar  = sorted(results, key=lambda r: r["calmar"], reverse=True)
    clean      = sorted(
        [r for r in results if r["neg_full"] == 0],
        key=lambda r: r["avg_annual"], reverse=True,
    )
    sweet_spot = sorted(
        [r for r in results if r["max_dd_r"] >= -13.0
         and r["avg_annual"] >= 15.0 and r["neg_full"] == 0],
        key=lambda r: r["avg_annual"], reverse=True,
    )

    print_table(by_annual,  "Best Avg Annual R")
    print_table(by_dd,      "Best DD (least negative)")
    print_table(by_calmar,  "Best Calmar")
    print_table(clean,      "0 Neg Full Years, by Avg Annual R")
    print_table(sweet_spot, "Sweet Spot: DD ≥ -13R, Avg/Yr ≥ 15R, 0 neg years")

    marginal_stop(results)

    print_heatmap(results, "avg_annual", "Avg Annual R", fmt=".1f")
    print_heatmap(results, "max_dd_r",   "Max DD R",     fmt=".1f")
    print_heatmap(results, "neg_full",   "Neg Full Years", fmt="d")

    # Year-by-year for sweet spot or best annual R
    top = sweet_spot[0] if sweet_spot else by_annual[0]
    label = "Sweet Spot #1" if sweet_spot else "#1 Avg Annual R"
    print(f"\n--- Year-by-year: {label} (stop={top['stop']}, rr={top['rr']}) ---")
    print(f"  Net R={top['net_r']}, Avg/Yr={top['avg_annual']}, DD={top['max_dd_r']}R, Calmar={top['calmar']}")
    for yr, yr_r in sorted(top["r_by_year"].items()):
        flag = " <-- NEG" if yr_r < 0 and yr in FULL_YEARS else ""
        print(f"  {yr}: {yr_r:>7.1f}R{flag}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
