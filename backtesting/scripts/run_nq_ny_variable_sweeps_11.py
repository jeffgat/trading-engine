#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 11: 3-way grid re-run with stop=9%.

Round 7 ran the gap × rr × tp1 grid at stop=10%. Round 9 discovered that
stop=9% massively improves rr=2.75 configs but not rr=2.0/2.5. The optimal
rr/tp1 surface likely looks different at stop=9%.

Grid:
  gap:  2.5, 3.0, 3.5
  rr:   2.0, 2.25, 2.5, 2.75, 3.0, 3.5
  tp1:  0.3, 0.4, 0.5, 0.6, 0.7

Total: 3 × 6 × 5 = 90 combos (long-only, stop=9%)

Base: long-only, 20m ORB, entry 09:50-15:00, stop=9%, magnifier
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)


def make_config(gap=3.0, rr=2.0, tp1=0.5, stop=9.0):
    sess = replace(NY_20M,
                   entry_start="09:50",
                   entry_end="15:00",
                   min_gap_atr_pct=gap,
                   stop_atr_pct=stop)
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=rr,
        tp1_ratio=tp1,
        name="NQ NY 3-way Grid stop=9%",
    )


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>45} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*110}")
    print(f"  {title}")
    print(f"{'='*110}")
    print(HDR)
    print("-" * 110)


def print_row(i, label, m, marker=""):
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>45} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
        f"{m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Round 11: 3-Way Grid with stop=9%")
    print("=" * 110)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    gaps = [2.5, 3.0, 3.5]
    rrs = [2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
    tp1s = [0.3, 0.4, 0.5, 0.6, 0.7]

    all_results = []  # (label, gap, rr, tp1, metrics, r_yr)

    # ── 1. FULL 3-WAY GRID AT STOP=9% ───────────────────────────────────
    print_header(f"1. GAP × RR × TP1 GRID (long, stop=9%, end=15:00) — {len(gaps)*len(rrs)*len(tp1s)} combos")
    idx = 1
    for gap in gaps:
        for rr in rrs:
            for tp1 in tp1s:
                config = make_config(gap=gap, rr=rr, tp1=tp1)
                m = run_and_metric(df_5m, df_1m, config)
                label = f"g={gap} rr={rr:.2f} tp1={tp1}"
                r_yr = m['total_r'] / DATA_YEARS
                all_results.append((label, gap, rr, tp1, m, r_yr))
                marker = ""
                if gap == 3.0 and rr == 2.75 and tp1 == 0.6:
                    marker = " <-- R10 best"
                print_row(idx, label, m, marker)
                idx += 1
            print()
        print(f"  --- gap={gap}% complete ---\n")

    # ── 2. TOP 20 BY CALMAR ─────────────────────────────────────────────
    print_header("2. TOP 20 BY CALMAR (stop=9% grid)")
    by_calmar = sorted(all_results, key=lambda x: x[4]['calmar_ratio'], reverse=True)
    for i, (label, gap, rr, tp1, m, r_yr) in enumerate(by_calmar[:20], 1):
        print_row(i, label, m)
        if i <= 10:
            print_year_breakdown(m)

    # ── 3. TOP 20 BY R/YEAR ─────────────────────────────────────────────
    print_header("3. TOP 20 BY R/YEAR (stop=9% grid)")
    by_r_yr = sorted(all_results, key=lambda x: x[5], reverse=True)
    for i, (label, gap, rr, tp1, m, r_yr) in enumerate(by_r_yr[:20], 1):
        print_row(i, label, m)
        if i <= 10:
            print_year_breakdown(m)

    # ── 4. TOP 10 BY CALMAR WHERE DD < 12R ──────────────────────────────
    print_header("4. TOP 10 BY CALMAR WHERE DD < 12R")
    low_dd = [r for r in all_results if abs(r[4]['max_drawdown_r']) < 12.0]
    low_dd_sorted = sorted(low_dd, key=lambda x: x[4]['calmar_ratio'], reverse=True)
    for i, (label, gap, rr, tp1, m, r_yr) in enumerate(low_dd_sorted[:10], 1):
        print_row(i, label, m)
        print_year_breakdown(m)

    # ── 5. COMPARE: STOP=9% vs STOP=10% FOR TOP COMBOS ──────────────────
    # Re-run the top 10 by Calmar at stop=10% for direct comparison
    print_header("5. HEAD-TO-HEAD: STOP=9% vs STOP=10% (top 10 combos)")
    seen = set()
    top_unique = []
    for label, gap, rr, tp1, m, r_yr in by_calmar:
        key = (gap, rr, tp1)
        if key not in seen:
            seen.add(key)
            top_unique.append((label, gap, rr, tp1, m, r_yr))
        if len(top_unique) >= 10:
            break

    idx = 1
    for label, gap, rr, tp1, m9, r_yr9 in top_unique:
        # stop=9%
        print_row(idx, f"[9%]  {label}", m9)
        idx += 1
        # stop=10%
        config10 = make_config(gap=gap, rr=rr, tp1=tp1, stop=10.0)
        m10 = run_and_metric(df_5m, df_1m, config10)
        print_row(idx, f"[10%] {label}", m10)
        calmar_diff = m9['calmar_ratio'] - m10['calmar_ratio']
        ryr_diff = (m9['total_r'] - m10['total_r']) / DATA_YEARS
        print(f"      >> Calmar delta: {calmar_diff:+.2f}  |  R/yr delta: {ryr_diff:+.1f}")
        idx += 1
        print()

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print(f"\n{'='*110}")
    print(f"  SUMMARY (all at stop=9%)")
    print(f"{'='*110}")

    best_calmar = by_calmar[0]
    best_r_yr = by_r_yr[0]
    best_prop = low_dd_sorted[0] if low_dd_sorted else by_calmar[0]

    print(f"\n  Best Calmar:      {best_calmar[0]:>40}  "
          f"R/yr={best_calmar[5]:.1f}  DD={best_calmar[4]['max_drawdown_r']:.1f}  "
          f"Calmar={best_calmar[4]['calmar_ratio']:.2f}")
    print(f"  Best R/year:      {best_r_yr[0]:>40}  "
          f"R/yr={best_r_yr[5]:.1f}  DD={best_r_yr[4]['max_drawdown_r']:.1f}  "
          f"Calmar={best_r_yr[4]['calmar_ratio']:.2f}")
    print(f"  Best Prop (<12R): {best_prop[0]:>40}  "
          f"R/yr={best_prop[5]:.1f}  DD={best_prop[4]['max_drawdown_r']:.1f}  "
          f"Calmar={best_prop[4]['calmar_ratio']:.2f}")

    # Count how many combos improved vs degraded at 9% vs their R7 (stop=10%) equivalent
    improved = sum(1 for _, _, rr, _, m, _ in all_results
                   if rr >= 2.5 and m['calmar_ratio'] > 12.0)
    print(f"\n  Combos with rr>=2.5 and Calmar>12 at stop=9%: {improved}")

    elapsed = time.time() - t_start
    print(f"\n{'='*110}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*110}")


if __name__ == "__main__":
    main()
