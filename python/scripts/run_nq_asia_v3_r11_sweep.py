#!/usr/bin/env python3
"""NQ Asia v3 — Round 11 analog: full grid at stop=3.7% anchor.

Stop anchor confirmed from Round 10 fine sweep:
  stop=3.7% is the Calmar peak (11.12 at rr=3.0, 0 neg years, 13.8 R/yr, DD -13.7R)

This sweep holds stop=3.7% fixed and explores the full surface:
  gap × rr × tp1 × maxgap

Goal: find if any gap/tp1/maxgap combination brings DD closer to -10R
while preserving Calmar > 10. Objective: Calmar.

Sweep:
  asia_min_gap_atr_pct: [0.75, 1.0, 1.25, 1.5, 2.0]       (5)
  asia_max_gap_atr_pct: [5.0, 8.0, 11.0, 15.0]             (4)
  rr:                   [2.0, 2.5, 3.0, 3.5, 4.0]           (5)
  tp1_ratio:            [0.15, 0.20, 0.25, 0.30, 0.35]      (5)

Total: 5 × 4 × 5 × 5 = 500 combos (8 workers)

v2 CONDITIONAL baseline: stop=5.75%, gap=1.25%, maxgap=11%, rr=1.5, tp1=0.20
  → Calmar 8.66, 7.7 R/yr, DD -9.7R, Sharpe 1.254, 0 neg years
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

STOP_ANCHOR = 3.7

PARAM_RANGES = {
    "asia_min_gap_atr_pct": [0.75, 1.0, 1.25, 1.5, 2.0],
    "asia_max_gap_atr_pct": [5.0, 8.0, 11.0, 15.0],
    "rr":                   [2.0, 2.5, 3.0, 3.5, 4.0],
    "tp1_ratio":            [0.15, 0.20, 0.25, 0.30, 0.35],
}


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def base_config():
    asia = replace(
        ASIA_SESSION,
        orb_end="20:10",
        entry_start="20:10",
        entry_end="23:00",
        stop_atr_pct=STOP_ANCHOR,
        min_gap_atr_pct=1.25,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=3.0,
        tp1_ratio=0.20,
        use_bar_magnifier=True,
        atr_length=5,
    )


def extract_row(config, metrics):
    sess = config.sessions[0]
    r_by_year   = metrics.get("r_by_year", {})
    full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
    avg_annual  = round(sum(full_year_r) / len(full_year_r), 1) if full_year_r else 0
    neg_full    = {yr: round(r, 1) for yr, r in r_by_year.items()
                   if r < 0 and yr in FULL_YEARS}
    return {
        "gap":        sess.min_gap_atr_pct,
        "maxgap":     sess.max_gap_atr_pct,
        "rr":         config.rr,
        "tp1":        config.tp1_ratio,
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
    f"{'#':>3} | {'gap%':>5} | {'maxg%':>5} | {'rr':>4} | {'tp1':>4} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>6} | NegFYr"
)


def print_table(rows, label, n=15):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
        print(
            f"{i:>3} | {r['gap']:>5.2f} | {r['maxgap']:>5.1f} | {r['rr']:>4.1f} | {r['tp1']:>4.2f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
            f"{r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | {r['calmar']:>7.2f} | "
            f"{r['r_per_trade']:>6.4f} | {neg}"
        )


def print_year_breakdown(row, label=""):
    print(f"  Year-by-year R{' — ' + label if label else ''}:")
    for yr, r in sorted(row.get("r_by_year", {}).items()):
        flag = " *" if r < 0 and yr in FULL_YEARS else ""
        print(f"    {yr}: {r:>7.1f}R{flag}")


def sweep_progress(done, total):
    if done % 50 == 0 or done == total:
        print(f"\r  {done:,}/{total:,}", end="", flush=True)


def main():
    print("NQ Asia v3 — Round 11: Full Grid at stop=3.7% anchor")
    print(f"stop={STOP_ANCHOR}%, ATR 5, ORB 10m, entry≤23:00, no-Thursday")
    print("v2 baseline: stop=5.75%, gap=1.25%, maxgap=11%, rr=1.5, tp1=0.20 → Calmar 8.66, DD -9.7R")
    print("R10 anchor:  stop=3.7%,  gap=1.25%, maxgap=11%, rr=3.0, tp1=0.20 → Calmar 11.12, DD -13.7R")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]")

    configs = generate_param_grid(base_config(), PARAM_RANGES)
    print(describe_grid(PARAM_RANGES))
    print(f"\nRunning {len(configs):,} configs with 8 workers...", flush=True)

    t1 = time.time()
    raw = run_sweep(df, configs, n_workers=8, start_date=START_DATE,
                    df_1m=df_1m, progress_fn=sweep_progress)
    print(f"\n  Completed in {time.time()-t1:.0f}s", flush=True)

    results = []
    for cfg, trades in raw:
        gated  = no_thursday_gate(trades)
        filled = [t for t in gated if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 20:
            continue
        m = compute_metrics(gated)
        results.append(extract_row(cfg, m))

    print(f"  Valid: {len(results):,}/{len(raw):,}")

    by_calmar  = sorted(results, key=lambda r: r["calmar"], reverse=True)
    by_sharpe  = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    by_annual  = sorted(results, key=lambda r: r["avg_annual"], reverse=True)
    clean      = sorted(
        [r for r in results if r["neg_full"] == 0],
        key=lambda r: r["calmar"], reverse=True,
    )
    prop_dd    = sorted(
        [r for r in results if r["max_dd_r"] >= -10.0],
        key=lambda r: r["calmar"], reverse=True,
    )
    sweet_spot = sorted(
        [r for r in results if r["max_dd_r"] >= -11.0 and r["calmar"] >= 9.0 and r["neg_full"] == 0],
        key=lambda r: r["calmar"], reverse=True,
    )

    print_table(by_calmar,  "Best Calmar")
    print_table(by_sharpe,  "Best Sharpe")
    print_table(by_annual,  "Best Avg Annual R")
    print_table(clean,      "0 Negative Full Years, by Calmar")
    print_table(prop_dd,    "DD >= -10R (prop-viable), by Calmar")
    print_table(sweet_spot, "Sweet Spot: DD >= -11R, Calmar >= 9, 0 neg years")

    # Year-by-year for top configs
    print(f"\n--- Year-by-year: Top 3 by Calmar ---")
    for i, r in enumerate(by_calmar[:3], 1):
        label = f"#{i}: gap={r['gap']:.2f}%, maxgap={r['maxgap']:.0f}%, rr={r['rr']:.1f}, tp1={r['tp1']:.2f}"
        print(f"\n  {label}")
        print(f"  Calmar={r['calmar']}, Avg/Yr={r['avg_annual']}, DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        print_year_breakdown(r)

    if sweet_spot:
        print(f"\n--- Year-by-year: Sweet Spot #1 ---")
        r = sweet_spot[0]
        label = f"gap={r['gap']:.2f}%, maxgap={r['maxgap']:.0f}%, rr={r['rr']:.1f}, tp1={r['tp1']:.2f}"
        print(f"  {label}")
        print(f"  Calmar={r['calmar']}, Avg/Yr={r['avg_annual']}, DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        print_year_breakdown(r)

    # Marginal analysis: how does each variable affect Calmar?
    print(f"\n--- Marginal: avg Calmar by variable value ---")
    for var, vals in [
        ("gap",    sorted(set(r["gap"]    for r in results))),
        ("maxgap", sorted(set(r["maxgap"] for r in results))),
        ("rr",     sorted(set(r["rr"]     for r in results))),
        ("tp1",    sorted(set(r["tp1"]    for r in results))),
    ]:
        print(f"\n  {var}:")
        for v in vals:
            subset = [r for r in results if r[var] == v]
            if not subset:
                continue
            avg_c  = sum(r["calmar"]    for r in subset) / len(subset)
            avg_dd = sum(r["max_dd_r"]  for r in subset) / len(subset)
            avg_yr = sum(r["avg_annual"] for r in subset) / len(subset)
            print(f"    {v:>5}: Calmar={avg_c:.2f}, DD={avg_dd:.1f}R, R/yr={avg_yr:.1f}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f}m)")
    print(f"\nv2 reference: Calmar 8.66, DD -9.7R, 7.7 R/yr (stop=5.75%, rr=1.5, tp1=0.20)")
    print(f"R10 anchor:   Calmar 11.12, DD -13.7R, 13.8 R/yr (stop=3.7%, rr=3.0, tp1=0.20)")


if __name__ == "__main__":
    main()
