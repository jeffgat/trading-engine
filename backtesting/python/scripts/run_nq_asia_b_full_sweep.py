#!/usr/bin/env python3
"""NQ Asia Config B — Full variable sweep.

Anchor: stop=4.0%, gap=1.25%, maxgap=5.0%, rr=2.0, tp1=0.35, atr=14, be=0,
        ORB 10m, entry≤22:30, both dirs, no-Thursday
Baseline B: 1560 trades, 62.8% WR, 168.0R net, 15.3R/yr, -12.9R DD, Sharpe 1.829

Tests:
  1. Day-of-week analysis (1 backtest, sliced by day)
  2. Full grid sweep:
       asia_min_gap_atr_pct: [0.5, 0.75, 1.0, 1.25]
       rr:                   [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
       tp1_ratio:            [0.25, 0.30, 0.35, 0.40, 0.45]
       asia_entry_end:       ["21:00", "21:30", "22:00", "22:30", "23:00"]

Total: 4 × 8 × 5 × 5 = 800 combos
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
    "asia_min_gap_atr_pct": [0.5, 0.75, 1.0, 1.25],
    "rr":                   [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
    "tp1_ratio":            [0.25, 0.30, 0.35, 0.40, 0.45],
    "asia_entry_end":       ["21:00", "21:30", "22:00", "22:30", "23:00"],
}

DAYS = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


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
        min_gap_atr_pct=1.25,
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


# ── Day-of-week analysis ──────────────────────────────────────────────────────

def day_of_week_analysis(df, df_1m):
    print("\n" + "=" * 70)
    print("SECTION 1: DAY-OF-WEEK ANALYSIS")
    print("=" * 70)
    print("Config B (all days, no gate applied)")

    cfg = base_config()
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"Total filled trades (all days): {len(filled)}")

    print(f"\n{'Day':>5} | {'Trades':>6} | {'WR':>6} | {'Total R':>8} | {'R/trade':>8} | {'DD R':>7} | {'NegFYr':>6}")
    print("-" * 65)

    for d, name in DAYS.items():
        day_trades = [t for t in filled if pd.Timestamp(t.date).dayofweek == d]
        if not day_trades:
            continue
        wins = sum(1 for t in day_trades if t.r_multiple > 0)
        total_r = sum(t.r_multiple for t in day_trades)
        wr = wins / len(day_trades)
        r_per_trade = total_r / len(day_trades)

        # per-day drawdown
        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        for t in day_trades:
            equity += t.r_multiple
            if equity > peak:
                peak = equity
            dd = equity - peak
            if dd < max_dd:
                max_dd = dd

        # negative full years for this day only
        by_year = {}
        for t in day_trades:
            yr = str(pd.Timestamp(t.date).year)
            by_year[yr] = by_year.get(yr, 0) + t.r_multiple
        neg_full = sum(1 for yr, r in by_year.items() if r < 0 and yr in FULL_YEARS)

        marker = "  <-- REMOVE?" if r_per_trade < 0 else ""
        print(f"{name:>5} | {len(day_trades):>6} | {wr:>5.1%} | {total_r:>8.1f} | "
              f"{r_per_trade:>8.4f} | {max_dd:>7.1f} | {neg_full:>6}{marker}")

    # also show cumulative R by day across years
    print(f"\nCumulative R by day-of-week and year:")
    years = sorted(FULL_YEARS)
    hdr = f"  {'Day':>5} |" + "".join(f" {yr:>7} |" for yr in years)
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))
    for d, name in DAYS.items():
        day_trades = [t for t in filled if pd.Timestamp(t.date).dayofweek == d]
        by_year = {}
        for t in day_trades:
            yr = str(pd.Timestamp(t.date).year)
            by_year[yr] = by_year.get(yr, 0) + t.r_multiple
        row = f"  {name:>5} |"
        for yr in years:
            val = by_year.get(yr, 0.0)
            flag = "*" if val < 0 else " "
            row += f" {val:>6.1f}{flag}|"
        print(row)

    print("\n  * = negative year for that day")


# ── Full sweep ────────────────────────────────────────────────────────────────

def extract_row(config, metrics):
    sess = config.sessions[0]
    r_by_year = metrics.get("r_by_year", {})
    neg_full = {yr: round(r, 1) for yr, r in r_by_year.items()
                if r < 0 and yr in FULL_YEARS}
    full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
    avg_annual = round(sum(full_year_r) / len(full_year_r), 1) if full_year_r else 0
    return {
        "gap":        sess.min_gap_atr_pct,
        "rr":         config.rr,
        "tp1":        config.tp1_ratio,
        "entry_end":  sess.entry_end,
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
    f"{'#':>3} | {'gap%':>5} | {'rr':>4} | {'tp1':>4} | {'end':>5} | "
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
            f"{i:>3} | {r['gap']:>5.2f} | {r['rr']:>4.1f} | {r['tp1']:>4.2f} | {r['entry_end']:>5} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
            f"{r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | {r['calmar']:>7.2f} | {neg}"
        )


def marginal(results, key, label, values):
    print(f"\n  {label}:")
    print(f"  {'Value':>6} | {'Sharpe':>7} | {'Avg/Yr':>7} | {'Net R':>7} | {'DD R':>6} | {'NegFYr':>6}")
    print("  " + "-" * 52)
    for v in values:
        subset = [r for r in results if r[key] == v]
        if not subset:
            continue
        n = len(subset)
        print(f"  {str(v):>6} | "
              f"{sum(r['sharpe'] for r in subset)/n:>7.3f} | "
              f"{sum(r['avg_annual'] for r in subset)/n:>7.1f} | "
              f"{sum(r['net_r'] for r in subset)/n:>7.1f} | "
              f"{sum(r['max_dd_r'] for r in subset)/n:>6.1f} | "
              f"{sum(r['neg_full'] for r in subset)/n:>6.2f}")


def main():
    print("NQ Asia Config B — Full Variable Sweep")
    print("Anchor: stop=4.0%, gap=1.25%, maxgap=5.0%, ORB 10m, ATR 14, be=0")
    print("Baseline B: 168.0R, 15.3R/yr, -12.9R DD, Sharpe 1.829 (no-Thursday)")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]")

    # Section 1: Day-of-week
    day_of_week_analysis(df, df_1m)

    # Section 2: Full grid sweep
    print("\n" + "=" * 70)
    print("SECTION 2: FULL GRID SWEEP (800 combos)")
    print("=" * 70)

    configs = generate_param_grid(base_config(), PARAM_RANGES)
    print(describe_grid(PARAM_RANGES))
    print(f"\nRunning {len(configs)} configs with 8 workers...", flush=True)

    t1 = time.time()
    raw = run_sweep(
        df, configs, n_workers=8, start_date=START_DATE, df_1m=df_1m,
        progress_fn=lambda done, total: print(
            f"\r  {done}/{total}", end="", flush=True
        ) if done % 50 == 0 or done == total else None,
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

    by_sharpe  = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    by_annual  = sorted(results, key=lambda r: r["avg_annual"], reverse=True)
    by_dd      = sorted(results, key=lambda r: r["max_dd_r"], reverse=True)
    clean      = sorted(
        [r for r in results if r["neg_full"] == 0],
        key=lambda r: r["avg_annual"], reverse=True,
    )
    sweet_spot = sorted(
        [r for r in results if r["max_dd_r"] >= -13.0
         and r["avg_annual"] >= 13.0 and r["neg_full"] == 0],
        key=lambda r: r["sharpe"], reverse=True,
    )

    print_table(by_sharpe,  "Best Sharpe")
    print_table(by_annual,  "Best Avg Annual R")
    print_table(by_dd,      "Best DD (least negative)")
    print_table(clean,      "0 Negative Full Years, by Avg Annual R")
    print_table(sweet_spot, "Sweet Spot: DD ≥ -13R, Avg/Yr ≥ 13R, 0 neg years")

    # Marginal analysis
    print("\n" + "=" * 70)
    print("MARGINAL ANALYSIS")
    print("=" * 70)
    marginal(results, "gap",       "min_gap_atr_pct",  PARAM_RANGES["asia_min_gap_atr_pct"])
    marginal(results, "rr",        "rr",               PARAM_RANGES["rr"])
    marginal(results, "tp1",       "tp1_ratio",        PARAM_RANGES["tp1_ratio"])
    marginal(results, "entry_end", "entry_end",        PARAM_RANGES["asia_entry_end"])

    # rr × tp1 heatmap (at baseline gap=1.25, entry_end=22:30)
    rr_vals  = PARAM_RANGES["rr"]
    tp1_vals = PARAM_RANGES["tp1_ratio"]
    for gap in [1.25, 0.75]:
        for ee in ["22:30", "21:30"]:
            subset = [r for r in results if r["gap"] == gap and r["entry_end"] == ee]
            if not subset:
                continue
            print(f"\n--- Avg Annual R grid (rr × tp1) at gap={gap}, entry_end={ee} ---")
            print(f"{'tp1→':>6}", end="")
            for tp1 in tp1_vals:
                print(f" {tp1:>6.2f}", end="")
            print()
            print("-" * (7 + 7 * len(tp1_vals)))
            for rr in rr_vals:
                print(f"rr={rr:<4}", end="")
                for tp1 in tp1_vals:
                    row = next((r for r in subset if r["rr"] == rr and r["tp1"] == tp1), None)
                    val = f"{row['avg_annual']:>6.1f}" if row else "   n/a"
                    print(f" {val}", end="")
                print()

            print(f"\n--- DD grid (rr × tp1) at gap={gap}, entry_end={ee} ---")
            print(f"{'tp1→':>6}", end="")
            for tp1 in tp1_vals:
                print(f" {tp1:>6.2f}", end="")
            print()
            print("-" * (7 + 7 * len(tp1_vals)))
            for rr in rr_vals:
                print(f"rr={rr:<4}", end="")
                for tp1 in tp1_vals:
                    row = next((r for r in subset if r["rr"] == rr and r["tp1"] == tp1), None)
                    val = f"{row['max_dd_r']:>6.1f}" if row else "   n/a"
                    print(f" {val}", end="")
                print()

    # Year-by-year for sweet spot #1 (or #1 Sharpe if no sweet spot)
    top = sweet_spot[0] if sweet_spot else by_sharpe[0]
    label = "Sweet Spot #1" if sweet_spot else "#1 Sharpe"
    print(f"\n--- Year-by-year: {label} "
          f"(gap={top['gap']}, rr={top['rr']}, tp1={top['tp1']}, end={top['entry_end']}) ---")
    print(f"  Net R={top['net_r']}, Avg/Yr={top['avg_annual']}, "
          f"DD={top['max_dd_r']}R, Sharpe={top['sharpe']}")
    for yr, yr_r in sorted(top["r_by_year"].items()):
        flag = " <-- NEG" if yr_r < 0 and yr in FULL_YEARS else ""
        print(f"  {yr}: {yr_r:>7.1f}R{flag}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
