#!/usr/bin/env python3
"""RTY Asia Continuation — Grid Sweep R1 (focused).

R4 anchor: stop=4.0%, rr=2.0, gap=0.9%, tp1=0.4, ATR=14, 15m ORB
           entry≤23:15, flat=06:45, long-only, excl Tue, 1s magnifier
           Calmar 5.77 | 715 trades | 58.9% WR | 70.6R | -12.2R DD

Focused grid around anchor sweet spot (320 combos).
Uses 1m magnifier for speed (variable sweeps already validated 1s structure).
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import RTY
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10
DOW_EXCL = {1}  # excl Tue

ANCHOR_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:15",
    entry_start="20:15",
    entry_end="23:15",
    flat_start="06:45",
    flat_end="07:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=0.9,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=RTY,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.4,
    atr_length=14,
    impulse_close_filter=False,
    name="RTY Asia Grid Sweep R1",
)

# Focused grid — tighter range around sweet spot
STOP_VALUES = [3.0, 3.5, 4.0, 4.5, 5.0]
RR_VALUES = [1.5, 2.0, 2.5, 3.0]
GAP_VALUES = [0.5, 0.75, 0.9, 1.0]
TP1_VALUES = [0.3, 0.4, 0.5, 0.6]


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    total_combos = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)
    print(f"RTY Asia — Grid Sweep ({total_combos} combos)")
    print("=" * 110)
    print(f"Anchor: stop=4.0%, rr=2.0, gap=0.9%, tp1=0.4 → Calmar 5.77")
    print(f"Grid: stop={STOP_VALUES} × rr={RR_VALUES} × gap={GAP_VALUES} × tp1={TP1_VALUES}")
    print(f"DOW excl: Tue")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    df_1s = None  # 1m magnifier for grid speed; 1s validated in variable sweeps
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: skipped [{time.time() - t_start:.1f}s]")

    results = []
    done = 0

    for stop in STOP_VALUES:
        stop_start = time.time()
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
        elapsed = time.time() - t_start
        stop_elapsed = time.time() - stop_start
        print(f"  stop={stop}%: {done}/{total_combos} ({stop_elapsed:.0f}s this stop, {elapsed:.0f}s total)", flush=True)

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
        is_anchor = (abs(stop - 4.0) < 0.01 and abs(rr - 2.0) < 0.01
                     and abs(gap - 0.9) < 0.01 and abs(tp1 - 0.4) < 0.01)
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
    print(f"\n{'='*110}")
    print(f"  TOP 10 WITH 0 NEGATIVE YEARS ({len(zero_neg)}/{total_combos} total)")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}")
    print(f"  {'─'*105}")
    for i, (stop, rr, gap, tp1, m) in enumerate(zero_neg[:10], 1):
        r_yr = m["total_r"] / DATA_YEARS
        is_anchor = (abs(stop - 4.0) < 0.01 and abs(rr - 2.0) < 0.01
                     and abs(gap - 0.9) < 0.01 and abs(tp1 - 0.4) < 0.01)
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
    print(f"\n{'='*110}")
    print(f"  TOP 10 WITH ≤1 NEGATIVE YEAR ({len(one_neg)}/{total_combos} total)")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
          f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")
    print(f"  {'─'*105}")
    for i, (stop, rr, gap, tp1, m) in enumerate(one_neg[:10], 1):
        r_yr = m["total_r"] / DATA_YEARS
        neg = neg_year_set(m)
        print(f"  {i:>3} {stop:>5.1f} {rr:>4.2f} {gap:>5.02f} {tp1:>4.2f} "
              f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>6.1f} "
              f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} {sorted(neg)}")

    # Where does anchor rank?
    anchor_rank = None
    for i, (stop, rr, gap, tp1, m) in enumerate(results, 1):
        if (abs(stop - 4.0) < 0.01 and abs(rr - 2.0) < 0.01
                and abs(gap - 0.9) < 0.01 and abs(tp1 - 0.4) < 0.01):
            anchor_rank = i
            break
    if anchor_rank:
        print(f"\n  Anchor rank: #{anchor_rank}/{total_combos}")

    # Surface analysis
    print(f"\n{'='*110}")
    print(f"  PARAMETER SURFACE — Top 20 value frequency")
    print(f"{'='*110}")
    from collections import Counter
    top20 = results[:20]
    for dim, values, idx in [
        ("stop", STOP_VALUES, 0), ("rr", RR_VALUES, 1),
        ("gap", GAP_VALUES, 2), ("tp1", TP1_VALUES, 3)
    ]:
        counts = Counter(r[idx] for r in top20)
        freq_str = "  ".join(f"{v}:{counts.get(v, 0)}" for v in values)
        print(f"  {dim:>5}: {freq_str}")

    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
