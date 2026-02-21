#!/usr/bin/env python3
"""NQ Asia Config C — Volatility regime filter sweep.

Problem: Walk-forward fold 4 (OOS 2022) lost -40.7R when WF selected
aggressive params. Our fixed config handled 2022 at +10.9R, but we want
to test whether an ATR-based volatility gate can make the strategy more
robust across regimes.

Filter: skip trading on days where daily ATR > threshold × rolling_mean_ATR(window).
High ATR = high-volatility regime (2022-style rate-hike choppiness).

Anchor: stop=3.9%, gap=0.75%, maxgap=5.0%, rr=2.0, tp1=0.35,
        ORB 10m, ATR 14, be=0, entry≤22:30, both dirs, no-Thursday

Sweep:
  window:    [10, 20, 50] days rolling mean
  threshold: [1.1, 1.2, 1.3, 1.4, 1.5, 2.0] × rolling mean ATR
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.signals.daily_atr import compute_daily_atr
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
FULL_YEARS = [str(y) for y in range(2015, 2026)]

WINDOWS    = [10, 20, 50]
THRESHOLDS = [1.1, 1.2, 1.3, 1.4, 1.5, 2.0]


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config():
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="22:30",
        stop_atr_pct=3.9,
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


def build_atr_lookup(df, atr_length=14, window=20):
    """Build date → (daily_atr, rolling_mean_atr) lookup."""
    atr_arr = compute_daily_atr(df, length=atr_length)
    atr_series = pd.Series(atr_arr, index=df.index)

    # One ATR value per calendar date (first bar of each day)
    daily_atr = atr_series.resample("1D").first().dropna()

    # Rolling mean (min_periods = half the window to avoid too many NaNs early on)
    rolling_mean = daily_atr.rolling(window=window, min_periods=max(1, window // 2)).mean()

    lookup = {}
    for dt in daily_atr.index:
        key = dt.date()
        atr_val  = daily_atr[dt]
        mean_val = rolling_mean[dt]
        lookup[key] = (float(atr_val), float(mean_val) if not np.isnan(mean_val) else np.nan)

    return lookup


def make_vol_gate(atr_lookup, threshold):
    """Return a gate function that drops trades on high-ATR days."""
    def gate(trades):
        result = []
        for t in trades:
            key = pd.Timestamp(t.date).date()
            if key in atr_lookup:
                atr_val, mean_val = atr_lookup[key]
                if not np.isnan(mean_val) and atr_val > threshold * mean_val:
                    continue  # skip — high-vol day
            result.append(t)
        return result
    return gate


def summarise(trades, label=""):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if len(filled) < 5:
        return None
    m = compute_metrics(trades)
    r_by_year   = m.get("r_by_year", {})
    full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
    avg_annual  = round(sum(full_year_r) / len(full_year_r), 1) if full_year_r else 0
    neg_full    = {yr: round(r, 1) for yr, r in r_by_year.items()
                   if r < 0 and yr in FULL_YEARS}
    return {
        "label":      label,
        "trades":     m["total_trades"],
        "wr":         m["win_rate"],
        "net_r":      round(m["total_r"], 1),
        "avg_annual": avg_annual,
        "max_dd_r":   round(m["max_drawdown_r"], 1),
        "calmar":     round(m.get("calmar_ratio", 0), 2),
        "neg_full":   len(neg_full),
        "neg_detail": neg_full,
        "r_by_year":  r_by_year,
    }


def print_summary_table(rows):
    hdr = (f"{'Label':>20} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | "
           f"{'Avg/Yr':>7} | {'DD R':>6} | {'Calmar':>7} | {'NegFYr':>6}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        if r is None:
            continue
        neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
        print(f"{r['label']:>20} | {r['trades']:>6} | {r['wr']:>5.1%} | "
              f"{r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | "
              f"{r['max_dd_r']:>6.1f} | {r['calmar']:>7.2f} | {neg}")


def print_year_grid(rows, years):
    # Header
    print(f"{'Label':>20} |" + "".join(f" {yr:>7} |" for yr in years) + " Trades |")
    print("-" * (22 + 10 * len(years) + 9))
    for r in rows:
        if r is None:
            continue
        row = f"{r['label']:>20} |"
        for yr in years:
            val  = r["r_by_year"].get(yr, 0.0)
            flag = "*" if val < 0 else " "
            row += f" {val:>6.1f}{flag}|"
        row += f" {r['trades']:>6} |"
        print(row)
    print("  * = negative year")


def trades_filtered_by_year(all_trades, gated_trades, years):
    """Show how many trades were removed per year by the filter."""
    all_by_year  = {}
    gate_by_year = {}
    gate_set     = set(id(t) for t in gated_trades)
    for t in all_trades:
        yr = str(pd.Timestamp(t.date).year)
        all_by_year[yr]  = all_by_year.get(yr, 0) + 1
        if id(t) in gate_set:
            gate_by_year[yr] = gate_by_year.get(yr, 0) + 1
    print(f"  {'Year':>5} | {'Total':>6} | {'Kept':>6} | {'Removed':>7} | {'Remove%':>8}")
    print("  " + "-" * 42)
    for yr in sorted(years):
        total   = all_by_year.get(yr, 0)
        kept    = gate_by_year.get(yr, 0)
        removed = total - kept
        pct     = removed / total if total > 0 else 0
        print(f"  {yr:>5} | {total:>6} | {kept:>6} | {removed:>7} | {pct:>7.1%}")


def main():
    print("NQ Asia Config C — Volatility Regime Filter Sweep")
    print("Filter: skip days where daily ATR > threshold × rolling_mean_ATR")
    print("Anchor: stop=3.9%, gap=0.75%, maxgap=5%, rr=2.0, tp1=0.35, be=0, no-Thu")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]")

    cfg = build_config()

    # Run baseline once
    print("\nRunning baseline backtest...", flush=True)
    raw_trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
    base_trades = no_thursday_gate(raw_trades)
    base = summarise(base_trades, "baseline")

    print(f"  {base['trades']} trades | {base['net_r']}R | {base['avg_annual']}R/yr | "
          f"DD {base['max_dd_r']}R | Calmar {base['calmar']}")

    years = sorted(FULL_YEARS)
    all_rows = [base]

    # Sweep window × threshold
    for window in WINDOWS:
        print(f"\nBuilding ATR lookup (window={window})...", flush=True)
        atr_lookup = build_atr_lookup(df, atr_length=14, window=window)

        rows_this_window = []
        for thresh in THRESHOLDS:
            vol_gate    = make_vol_gate(atr_lookup, thresh)
            gated       = vol_gate(base_trades)
            label       = f"w{window}_t{thresh}"
            r = summarise(gated, label)
            if r:
                rows_this_window.append(r)

        print(f"\n--- Window={window} days ---")
        print_summary_table(rows_this_window)
        all_rows.extend(rows_this_window)

    # Year-by-year grid for all results
    print("\n\n=== YEAR-BY-YEAR R GRID ===")
    print_year_grid(all_rows, years)

    # Highlight best candidates (0 neg years, highest avg_annual)
    clean = sorted(
        [r for r in all_rows if r and r["neg_full"] == 0],
        key=lambda r: r["avg_annual"], reverse=True,
    )
    print(f"\n\n=== CLEAN CONFIGS (0 neg full years), by Avg Annual R ===")
    print_summary_table(clean[:10])

    # Show trade removal breakdown for the best filter
    if len(clean) > 1:  # index 0 is baseline
        best = next((r for r in clean if r["label"] != "baseline"), None)
        if best:
            label_parts = best["label"].split("_")
            w = int(label_parts[0][1:])
            t = float(label_parts[1][1:])
            atr_lookup = build_atr_lookup(df, atr_length=14, window=w)
            vol_gate   = make_vol_gate(atr_lookup, t)
            gated      = vol_gate(base_trades)

            print(f"\n=== TRADE REMOVAL: {best['label']} (w={w}, thresh={t}) ===")
            trades_filtered_by_year(base_trades, gated, years)

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
