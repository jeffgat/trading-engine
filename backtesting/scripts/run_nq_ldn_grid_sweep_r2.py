#!/usr/bin/env python3
"""NQ LDN Continuation — Grid Sweep (post-R2 convergence).

R2 converged anchor:
  ORB: 03:00-03:15 (15m), entry until 08:25, flat 08:20-08:25
  stop=10.0%, min_gap_atr=1.0%, max_gap_pts=20, max_gap_atr=0 (off)
  rr=2.0, tp1=0.5, ATR=14, direction=both, ICF=ON, continuation, 1s magnifier
  DOW gate: none
  Calmar: 1.12

Exhaustive grid: stop × rr × min_gap × tp1
If winner differs from anchor → fine-tune → re-sweep.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

ANCHOR_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:15",
    entry_start="03:15",
    entry_end="08:25",
    flat_start="08:20",
    flat_end="08:25",
    stop_atr_pct=10.0,
    min_gap_atr_pct=1.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    impulse_close_filter=True,
    name="NQ LDN Grid Sweep",
)

# Grid dimensions
STOP_VALUES = [5.0, 7.0, 8.0, 10.0, 12.0, 15.0]
RR_VALUES = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
GAP_VALUES = [0.75, 1.0, 1.25, 1.5]
TP1_VALUES = [0.3, 0.4, 0.5, 0.6]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    total_combos = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)
    print(f"NQ LDN — Grid Sweep ({total_combos} combos)")
    print("=" * 100)
    print(f"Anchor: stop=10%, rr=2.0, gap=1.0%, tp1=0.5 → Calmar 1.12")
    print(f"Grid: stop={STOP_VALUES} × rr={RR_VALUES} × gap={GAP_VALUES} × tp1={TP1_VALUES}")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t_start:.1f}s]")

    results = []
    done = 0

    for stop in STOP_VALUES:
        for rr in RR_VALUES:
            for gap in GAP_VALUES:
                for tp1 in TP1_VALUES:
                    sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
                    config = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
                    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
                    m = compute_metrics(trades)
                    results.append((stop, rr, gap, tp1, m))
                    done += 1
                    if done % 50 == 0:
                        elapsed = time.time() - t_start
                        print(f"  {done}/{total_combos} ({elapsed:.0f}s)", flush=True)

    elapsed = time.time() - t_start
    print(f"\n  Grid complete: {done} combos in {elapsed:.0f}s ({elapsed / 60:.1f}m)")

    # Sort by Calmar
    results.sort(key=lambda x: x[4]["calmar_ratio"], reverse=True)

    # Print top 20
    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")
    print(f"  {'─'*105}")

    for i, (stop, rr, gap, tp1, m) in enumerate(results[:20], 1):
        r_yr = m["total_r"] / DATA_YEARS
        neg = neg_year_set(m)
        neg_str = str(len(neg))
        is_anchor = (abs(stop - 10.0) < 0.01 and abs(rr - 2.0) < 0.01
                     and abs(gap - 1.0) < 0.01 and abs(tp1 - 0.5) < 0.01)
        marker = " <-- anchor" if is_anchor else ""
        print(f"  {i:>3} {stop:>5.1f} {rr:>4.2f} {gap:>5.2f} {tp1:>4.2f} "
              f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
              f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} {neg_str:>6}{marker}")

    # Best with 0 neg years
    zero_neg = [(s, rr, g, t, m) for s, rr, g, t, m in results if len(neg_year_set(m)) == 0]
    if zero_neg:
        print(f"\n{'='*110}")
        print(f"  TOP 10 WITH 0 NEGATIVE YEARS")
        print(f"{'='*110}")
        print(f"  {'#':>3} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
              f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
              f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}")
        print(f"  {'─'*105}")
        for i, (stop, rr, gap, tp1, m) in enumerate(zero_neg[:10], 1):
            r_yr = m["total_r"] / DATA_YEARS
            is_anchor = (abs(stop - 10.0) < 0.01 and abs(rr - 2.0) < 0.01
                         and abs(gap - 1.0) < 0.01 and abs(tp1 - 0.5) < 0.01)
            marker = " <-- anchor" if is_anchor else ""
            print(f"  {i:>3} {stop:>5.1f} {rr:>4.2f} {gap:>5.2f} {tp1:>4.2f} "
                  f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
                  f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
                  f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}")
            # Print years for top 3
            if i <= 3 and "r_by_year" in m:
                years = sorted(m["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
                print(f"      R by year: {yr_str}")

    # Best with ≤1 neg year
    one_neg = [(s, rr, g, t, m) for s, rr, g, t, m in results if len(neg_year_set(m)) <= 1]
    if one_neg and len(zero_neg) < 5:
        print(f"\n{'='*110}")
        print(f"  TOP 10 WITH ≤1 NEGATIVE YEAR")
        print(f"{'='*110}")
        print(f"  {'#':>3} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
              f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
              f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")
        print(f"  {'─'*105}")
        for i, (stop, rr, gap, tp1, m) in enumerate(one_neg[:10], 1):
            r_yr = m["total_r"] / DATA_YEARS
            neg = neg_year_set(m)
            print(f"  {i:>3} {stop:>5.1f} {rr:>4.2f} {gap:>5.2f} {tp1:>4.2f} "
                  f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
                  f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
                  f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} {sorted(neg)}")
            if i <= 3 and "r_by_year" in m:
                years = sorted(m["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
                print(f"      R by year: {yr_str}")

    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
