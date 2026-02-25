#!/usr/bin/env python3
"""ES Asia Continuation — Grid Sweep (post-R5 convergence).

R5 converged anchor:
  ORB: 20:00-20:10 (10m), entry until 03:00, flat 06:45-07:00
  stop=3.0%, min_gap_atr=0.5%, max_gap_pts=50, max_gap_atr=0 (off)
  rr=2.0, tp1=0.5, ATR=5, direction=long, ICF=OFF, continuation, 1s magnifier
  DOW gate: excl Thu
  Calmar: 21.24 | 1,178 trades | 59.6% WR | 223.1R | -10.5R DD | 0 neg years

Exhaustive grid: stop × rr × min_gap × tp1
DOW excl=Thu applied to all combos.
If winner differs from anchor → fine-tune → re-sweep.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10
DOW_EXCL = {3}  # excl Thu

ANCHOR_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:10",
    entry_start="20:10",
    entry_end="03:00",
    flat_start="06:45",
    flat_end="07:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=0.5,
    max_gap_points=50.0,
    max_gap_atr_pct=0.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=ES,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=5,
    impulse_close_filter=False,
    name="ES Asia Grid Sweep R1",
)

# Grid dimensions — centered around anchor with meaningful range
STOP_VALUES = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
RR_VALUES = [1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
GAP_VALUES = [0.25, 0.5, 0.75, 1.0]
TP1_VALUES = [0.3, 0.4, 0.5, 0.6]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    total_combos = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)
    print(f"ES Asia — Grid Sweep ({total_combos} combos)")
    print("=" * 110)
    print(f"Anchor: stop=3.0%, rr=2.0, gap=0.5%, tp1=0.5 → Calmar 21.24")
    print(f"Grid: stop={STOP_VALUES} × rr={RR_VALUES} × gap={GAP_VALUES} × tp1={TP1_VALUES}")
    print(f"DOW excl: Thu")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
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
                    trades = apply_dow_filter(trades, DOW_EXCL)
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
        is_anchor = (abs(stop - 3.0) < 0.01 and abs(rr - 2.0) < 0.01
                     and abs(gap - 0.5) < 0.01 and abs(tp1 - 0.5) < 0.01)
        marker = " <-- anchor" if is_anchor else ""
        print(f"  {i:>3} {stop:>5.1f} {rr:>4.2f} {gap:>5.2f} {tp1:>4.2f} "
              f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
              f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} {neg_str:>6}{marker}")
        if i <= 5 and "r_by_year" in m:
            years = sorted(m["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
            print(f"      R by year: {yr_str}")

    # Best with 0 neg years
    zero_neg = [(s, rr, g, t, m) for s, rr, g, t, m in results if len(neg_year_set(m)) == 0]
    if zero_neg:
        print(f"\n{'='*110}")
        print(f"  TOP 10 WITH 0 NEGATIVE YEARS ({len(zero_neg)}/{total_combos} total)")
        print(f"{'='*110}")
        print(f"  {'#':>3} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
              f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
              f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}")
        print(f"  {'─'*105}")
        for i, (stop, rr, gap, tp1, m) in enumerate(zero_neg[:10], 1):
            r_yr = m["total_r"] / DATA_YEARS
            is_anchor = (abs(stop - 3.0) < 0.01 and abs(rr - 2.0) < 0.01
                         and abs(gap - 0.5) < 0.01 and abs(tp1 - 0.5) < 0.01)
            marker = " <-- anchor" if is_anchor else ""
            print(f"  {i:>3} {stop:>5.1f} {rr:>4.2f} {gap:>5.2f} {tp1:>4.2f} "
                  f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
                  f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
                  f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}")
            if i <= 5 and "r_by_year" in m:
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

    # Where does anchor rank?
    anchor_rank = None
    for i, (stop, rr, gap, tp1, m) in enumerate(results, 1):
        if (abs(stop - 3.0) < 0.01 and abs(rr - 2.0) < 0.01
                and abs(gap - 0.5) < 0.01 and abs(tp1 - 0.5) < 0.01):
            anchor_rank = i
            break
    if anchor_rank:
        print(f"\n  Anchor rank: #{anchor_rank}/{total_combos}")

    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
