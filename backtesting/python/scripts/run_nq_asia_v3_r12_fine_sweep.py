#!/usr/bin/env python3
"""NQ Asia v3 — Round 12: Fine sweep at stop=3.7% anchor.

R11 findings:
  - gap=1.25% is the optimal value (marginal Calmar peak 9.85)
  - maxgap is flat (5-11 all within 0.3 avg Calmar) — fixed at [5, 8]
  - rr is flat (2.0-4.0 within 0.7 avg) — fine sweep in 0.25 steps
  - tp1=0.25-0.30 is the sweet spot — fine sweep in 0.05 steps

Best R11 (0 neg years): gap=1.25%, maxgap=5%, rr=2.5, tp1=0.25
  → Calmar 13.05, 15.1 R/yr, DD -12.8R, Sharpe 1.729

Sweep:
  asia_min_gap_atr_pct: 0.90 → 1.50 in 0.1 steps  (7)
  asia_max_gap_atr_pct: [5.0, 8.0]                  (2)
  rr:                   1.75 → 3.50 in 0.25 steps   (8)
  tp1_ratio:            [0.20, 0.25, 0.30, 0.35]     (4)

Total: 7 × 2 × 8 × 4 = 448 combos (8 workers)
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
    "asia_min_gap_atr_pct": [round(0.90 + i * 0.10, 2) for i in range(7)],  # 0.90-1.50
    "asia_max_gap_atr_pct": [5.0, 8.0],
    "rr":                   [round(1.75 + i * 0.25, 2) for i in range(8)],  # 1.75-3.50
    "tp1_ratio":            [0.20, 0.25, 0.30, 0.35],
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
        rr=2.5,
        tp1_ratio=0.25,
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
    f"{'#':>3} | {'gap%':>5} | {'maxg%':>5} | {'rr':>5} | {'tp1':>4} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>6} | NegFYr"
)


def print_table(rows, label, n=15):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
        r11_mark = " <-- R11" if (
            abs(r["gap"] - 1.25) < 0.01 and r["maxgap"] == 5.0
            and abs(r["rr"] - 2.5) < 0.01 and abs(r["tp1"] - 0.25) < 0.01
        ) else ""
        print(
            f"{i:>3} | {r['gap']:>5.2f} | {r['maxgap']:>5.1f} | {r['rr']:>5.2f} | {r['tp1']:>4.2f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
            f"{r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | {r['calmar']:>7.2f} | "
            f"{r['r_per_trade']:>6.4f} | {neg}{r11_mark}"
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
    print("NQ Asia v3 — Round 12: Fine Grid at stop=3.7% anchor")
    print(f"stop={STOP_ANCHOR}%, ATR 5, ORB 10m, entry≤23:00, no-Thursday")
    print("R11 best (0 neg yrs): gap=1.25%, maxgap=5%, rr=2.5, tp1=0.25 → Calmar 13.05, DD -12.8R")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]")

    configs = generate_param_grid(base_config(), PARAM_RANGES)
    print(describe_grid(PARAM_RANGES))
    print(f"  gap values:    {PARAM_RANGES['asia_min_gap_atr_pct']}")
    print(f"  rr values:     {PARAM_RANGES['rr']}")
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
    clean      = sorted(
        [r for r in results if r["neg_full"] == 0],
        key=lambda r: r["calmar"], reverse=True,
    )

    print_table(by_calmar, "Best Calmar")
    print_table(by_sharpe, "Best Sharpe")
    print_table(clean,     "0 Negative Full Years, by Calmar")

    # Year-by-year for top 3 by Calmar
    print(f"\n--- Year-by-year: Top 3 by Calmar ---")
    for i, r in enumerate(by_calmar[:3], 1):
        label = f"#{i}: gap={r['gap']:.2f}%, maxgap={r['maxgap']:.0f}%, rr={r['rr']:.2f}, tp1={r['tp1']:.2f}"
        print(f"\n  {label}")
        print(f"  Calmar={r['calmar']}, Avg/Yr={r['avg_annual']}, DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        print_year_breakdown(r)

    if clean:
        print(f"\n--- Year-by-year: Best 0-neg-year config ---")
        r = clean[0]
        label = f"gap={r['gap']:.2f}%, maxgap={r['maxgap']:.0f}%, rr={r['rr']:.2f}, tp1={r['tp1']:.2f}"
        print(f"  {label}")
        print(f"  Calmar={r['calmar']}, Avg/Yr={r['avg_annual']}, DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        print_year_breakdown(r)

    # Marginal analysis
    print(f"\n--- Marginal: avg Calmar by variable value ---")
    gap_vals    = sorted(set(r["gap"]    for r in results))
    maxgap_vals = sorted(set(r["maxgap"] for r in results))
    rr_vals     = sorted(set(r["rr"]     for r in results))
    tp1_vals    = sorted(set(r["tp1"]    for r in results))

    for var_name, var_key, vals in [
        ("gap",    "gap",    gap_vals),
        ("maxgap", "maxgap", maxgap_vals),
        ("rr",     "rr",     rr_vals),
        ("tp1",    "tp1",    tp1_vals),
    ]:
        print(f"\n  {var_name}:")
        for v in vals:
            subset = [r for r in results if abs(r[var_key] - v) < 0.001]
            if not subset:
                continue
            avg_c  = sum(r["calmar"]    for r in subset) / len(subset)
            avg_dd = sum(r["max_dd_r"]  for r in subset) / len(subset)
            avg_yr = sum(r["avg_annual"] for r in subset) / len(subset)
            n_clean = sum(1 for r in subset if r["neg_full"] == 0)
            print(f"    {v:>5.2f}: Calmar={avg_c:.2f}, DD={avg_dd:.1f}R, R/yr={avg_yr:.1f}, clean={n_clean}/{len(subset)}")

    # Calmar heatmap: gap (rows) × rr (cols), best tp1/maxgap per cell
    print(f"\n--- Best Calmar per (gap × rr) cell ---")
    print(f"{'rr→':>7}", end="")
    for rr in rr_vals:
        print(f"  {rr:>5.2f}", end="")
    print()
    print("-" * (8 + 8 * len(rr_vals)))
    for gap in gap_vals:
        print(f"g={gap:<5.2f}", end="")
        for rr in rr_vals:
            cell = [r for r in results if abs(r["gap"] - gap) < 0.001 and abs(r["rr"] - rr) < 0.001]
            if cell:
                best = max(cell, key=lambda r: r["calmar"])
                mark = "*" if best["neg_full"] == 0 else " "
                print(f" {best['calmar']:>6.2f}{mark}", end="")
            else:
                print("     n/a ", end="")
        print()
    print("* = 0 negative full years")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f}m)")
    print(f"\nR11 reference: Calmar 13.05, DD -12.8R, 15.1 R/yr (gap=1.25%, maxgap=5%, rr=2.5, tp1=0.25)")
    print(f"v2 reference:  Calmar 8.66,  DD -9.7R,   7.7 R/yr (stop=5.75%, rr=1.5, tp1=0.20)")


if __name__ == "__main__":
    main()
