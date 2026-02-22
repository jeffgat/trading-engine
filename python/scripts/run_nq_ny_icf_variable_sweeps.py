#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps on best ICF=ON config.

Best clean ICF=ON config from grid sweep:
  stop=9.0%, rr=4.0, gap=3.5%, tp1=0.3, orb=20m, ATR=12, dir=both
  Calmar 12.46, 0 neg years

Sweep 4 high-leverage variables:
  1. entry_end (12:00 – 15:30)
  2. tp1_ratio (0.15 – 0.50)
  3. ATR length (5 – 20)
  4. direction (both, long, short)
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=3.5,
    max_gap_points=100.0,
)

BASE = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=4.0,
    tp1_ratio=0.3,
    atr_length=12,
    impulse_close_filter=True,
    name="NQ NY ICF var sweep",
)


def run_and_metric(df_5m, df_1m, df_1s, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return trades, compute_metrics(trades)


HDR = (
    f"    {'#':>3} {'Variable':>20} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}"
)


def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(HDR)
    print(f"    {'─'*85}")


def print_row(i, label, m, is_base=False):
    marker = " <-- anchor" if is_base else ""
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    print(
        f"    {i:>3} {label:>20} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}"
    )


def print_years(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"      R by year: {yr_str}")


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    print("NQ NY ORB — Variable sweeps on best ICF=ON config")
    print("=" * 90)
    print(f"Anchor: stop=9.0%, rr=4.0, gap=3.5%, tp1=0.3, orb=20m, ATR=12, dir=both, ICF=ON")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t0:.1f}s]")

    all_results = []

    # ── 0. ANCHOR BASELINE ────────────────────────────────────────────
    print_header("0. ANCHOR BASELINE (ICF=ON)")
    _, m_anchor = run_and_metric(df_5m, df_1m, df_1s, BASE)
    print_row(0, "ANCHOR", m_anchor, is_base=True)
    print_years(m_anchor)
    anchor_calmar = m_anchor["calmar_ratio"]
    anchor_neg = neg_year_set(m_anchor)
    print(f"      Negative years: {sorted(anchor_neg) if anchor_neg else 'none'}")

    # ── 1. ENTRY END TIME ─────────────────────────────────────────────
    entry_ends = ["12:00", "13:00", "14:00", "14:30", "15:00", "15:30"]
    print_header("1. ENTRY END TIME (anchor=15:30)")
    for i, ee in enumerate(entry_ends, 1):
        sess = replace(BASE_SESSION, entry_end=ee)
        config = replace(BASE, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"end={ee}", m, is_base=(ee == "15:30"))
        print_years(m)
        all_results.append(("entry_end", ee, m))

    # ── 2. TP1 RATIO ─────────────────────────────────────────────────
    tp1_values = [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]
    print_header("2. TP1 RATIO (anchor=0.30)")
    for i, tp1 in enumerate(tp1_values, 1):
        config = replace(BASE, tp1_ratio=tp1)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"tp1={tp1:.2f}", m, is_base=(tp1 == 0.30))
        print_years(m)
        all_results.append(("tp1_ratio", tp1, m))

    # ── 3. ATR LENGTH ─────────────────────────────────────────────────
    atr_values = [5, 7, 10, 12, 14, 16, 20]
    print_header("3. ATR LENGTH (anchor=12)")
    for i, atr in enumerate(atr_values, 1):
        config = replace(BASE, atr_length=atr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"atr={atr}", m, is_base=(atr == 12))
        print_years(m)
        all_results.append(("atr_length", atr, m))

    # ── 4. DIRECTION ──────────────────────────────────────────────────
    print_header("4. DIRECTION (anchor=both)")
    for i, d in enumerate(["both", "long", "short"], 1):
        config = replace(BASE, direction_filter=d)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"dir={d}", m, is_base=(d == "both"))
        print_years(m)
        all_results.append(("direction", d, m))

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Best value per dimension (by Calmar)")
    print(f"  ICF=ON Anchor Calmar: {anchor_calmar:.2f} | R20 ICF=OFF Calmar: 16.36")
    print(f"{'='*90}")
    print(f"  {'Variable':<20} {'Best Value':>12} {'Calmar':>8} {'Δ':>6} {'R/yr':>6} "
          f"{'DD':>6} {'NewNeg':>8}")
    print(f"  {'─'*70}")

    from collections import defaultdict
    by_var = defaultdict(list)
    for var, val, m in all_results:
        by_var[var].append((val, m))

    for var in ["entry_end", "tp1_ratio", "atr_length", "direction"]:
        if var not in by_var:
            continue
        best_val, best_m = max(by_var[var], key=lambda x: x[1]["calmar_ratio"])
        delta = best_m["calmar_ratio"] - anchor_calmar
        r_yr = best_m["total_r"] / DATA_YEARS
        best_neg = neg_year_set(best_m)
        new_neg = best_neg - anchor_neg
        new_neg_str = str(sorted(new_neg)) if new_neg else "none"
        print(f"  {var:<20} {str(best_val):>12} {best_m['calmar_ratio']:>8.2f} "
              f"{delta:>+6.2f} {r_yr:>6.1f} {best_m['max_drawdown_r']:>6.1f} "
              f"{new_neg_str:>8}")

    # Can any combination close the gap to R20 ICF=OFF (16.36)?
    print(f"\n  Gap to R20 ICF=OFF: {16.36 - anchor_calmar:.2f} Calmar points")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
