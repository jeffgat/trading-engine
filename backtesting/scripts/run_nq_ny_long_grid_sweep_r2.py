#!/usr/bin/env python3
"""NQ NY Continuation — Grid Sweep R2 (Longs-Only Fresh Start).

Narrow 4D grid around converged R9 anchor:
  stop=[6,6.5,7,7.5,8], rr=[2.75,3.0,3.25,3.5,3.75], gap=[2.0,2.5,3.0], tp1=[0.35,0.4,0.45,0.5,0.55]
  Total: 5 × 5 × 3 × 5 = 375 combos

Structural params held fixed:
  ORB: 09:30-09:50 (20m), entry until 12:00, flat 15:30-16:00
  ATR=12, ICF=ON, direction=long, continuation, 1s magnifier
  DOW gate: excl Fri
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10
MIN_TP1_RATIO = 0.2

# Grid dimensions — narrow around R9 anchor
STOP_VALUES = [6.0, 6.5, 7.0, 7.5, 8.0]
RR_VALUES = [2.75, 3.0, 3.25, 3.5, 3.75]
GAP_VALUES = [2.0, 2.5, 3.0]
TP1_VALUES = [0.35, 0.4, 0.45, 0.5, 0.55]

DOW_EXCL = {4}  # excl Friday

# Base session config
BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="12:00",
    flat_start="15:30",
    flat_end="16:00",
    stop_atr_pct=7.0,
    min_gap_atr_pct=2.5,
)

# Base strategy config
BASE_STRATEGY = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.25,
    tp1_ratio=0.45,
    atr_length=12,
    impulse_close_filter=True,
    name="NQ NY Long Grid R2",
)

# Anchor values
ANCHOR_STOP = 7.0
ANCHOR_RR = 3.25
ANCHOR_GAP = 2.5
ANCHOR_TP1 = 0.45


def median_stop_ticks(trades):
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def main():
    total_combos = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)
    print(f"NQ NY ORB — Grid Sweep R2 (Longs-Only)")
    print(f"=" * 100)
    print(f"Grid: stop={STOP_VALUES} × rr={RR_VALUES} × gap={GAP_VALUES} × tp1={TP1_VALUES}")
    print(f"Total combos: {total_combos}")
    print(f"Structural: 20m ORB, entry<=12:00, flat=15:30, ATR=12, ICF=ON, excl Fri, long-only")
    print(f"Anchor: stop={ANCHOR_STOP}, rr={ANCHOR_RR}, gap={ANCHOR_GAP}, tp1={ANCHOR_TP1}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    results = []
    skipped_ticks = 0
    skipped_tp1 = 0
    done = 0

    combos = list(product(STOP_VALUES, RR_VALUES, GAP_VALUES, TP1_VALUES))

    for stop, rr, gap, tp1 in combos:
        done += 1

        if tp1 < MIN_TP1_RATIO:
            skipped_tp1 += 1
            continue

        sess = replace(BASE_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
        cfg = replace(BASE_STRATEGY, sessions=(sess,), rr=rr, tp1_ratio=tp1)

        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        trades = apply_dow_filter(trades, DOW_EXCL)

        med_ticks = median_stop_ticks(trades)
        if med_ticks < 10:
            skipped_ticks += 1
            continue

        m = compute_metrics(trades)
        neg_yrs = neg_year_set(m)
        n_neg = len(neg_yrs)
        r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "r_yr": r_yr,
            "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
            "n_neg": n_neg, "neg_yrs": sorted(neg_yrs),
            "med_ticks": med_ticks,
            "r_by_year": m.get("r_by_year", {}),
        })

        if done % 50 == 0:
            elapsed = time.time() - t0
            rate = done / elapsed
            eta = (total_combos - done) / rate if rate > 0 else 0
            print(f"  [{done}/{total_combos}] {elapsed:.0f}s elapsed, "
                  f"{rate:.1f} combo/s, ETA {eta:.0f}s | "
                  f"results={len(results)}, skip_ticks={skipped_ticks}, skip_tp1={skipped_tp1}")

    elapsed = time.time() - t0
    print(f"\n{'='*100}")
    print(f"  GRID COMPLETE — {len(results)} valid results from {total_combos} combos "
          f"({skipped_ticks} skipped <10 ticks, {skipped_tp1} skipped tp1<{MIN_TP1_RATIO})")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*100}")

    results.sort(key=lambda x: x["calmar"], reverse=True)

    # -- Top 20 by Calmar (all combos) ----------------------------------------
    print(f"\n  TOP 20 BY CALMAR (all combos):")
    print(f"  {'Rank':>4} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'Neg':>4} {'Neg Yrs'}")
    print(f"  {'----'*20}")
    for i, r in enumerate(results[:20], 1):
        is_anchor = (abs(r["stop"] - ANCHOR_STOP) < 0.01 and
                     abs(r["rr"] - ANCHOR_RR) < 0.01 and
                     abs(r["gap"] - ANCHOR_GAP) < 0.01 and
                     abs(r["tp1"] - ANCHOR_TP1) < 0.01)
        marker = " <<<" if is_anchor else ""
        neg_str = ",".join(str(y) for y in r["neg_yrs"]) if r["neg_yrs"] else "none"
        print(f"  {i:>4} {r['stop']:>5.1f} {r['rr']:>5.2f} {r['gap']:>5.1f} {r['tp1']:>5.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
              f"{r['net_r']:>7.1f} {r['r_yr']:>6.1f} {r['max_dd']:>6.1f} {r['calmar']:>7.2f} "
              f"{r['n_neg']:>4} {neg_str}{marker}")

    # -- Top 20 by Calmar (0 neg years only) -----------------------------------
    zero_neg = [r for r in results if r["n_neg"] == 0]
    print(f"\n  TOP 20 BY CALMAR (0 negative full years only — {len(zero_neg)}/{len(results)} combos):")
    print(f"  {'Rank':>4} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} {'Net R':>7} "
          f"{'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}")
    print(f"  {'----'*20}")
    for i, r in enumerate(zero_neg[:20], 1):
        is_anchor = (abs(r["stop"] - ANCHOR_STOP) < 0.01 and
                     abs(r["rr"] - ANCHOR_RR) < 0.01 and
                     abs(r["gap"] - ANCHOR_GAP) < 0.01 and
                     abs(r["tp1"] - ANCHOR_TP1) < 0.01)
        marker = " <<<" if is_anchor else ""
        print(f"  {i:>4} {r['stop']:>5.1f} {r['rr']:>5.2f} {r['gap']:>5.1f} {r['tp1']:>5.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
              f"{r['net_r']:>7.1f} {r['r_yr']:>6.1f} {r['max_dd']:>6.1f} {r['calmar']:>7.2f}{marker}")

    # -- Top 5 year-by-year breakdown ------------------------------------------
    print(f"\n  TOP 5 (0 neg years) — Year-by-Year Breakdown:")
    for i, r in enumerate(zero_neg[:5], 1):
        rby = r["r_by_year"]
        yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in sorted(rby.items()))
        print(f"  #{i} stop={r['stop']}, rr={r['rr']}, gap={r['gap']}, tp1={r['tp1']} "
              f"| Calmar={r['calmar']:.2f}, Net R={r['net_r']:.1f}, DD={r['max_dd']:.1f}")
        print(f"     {yr_str}")

    # -- Anchor rank -----------------------------------------------------------
    anchor_rank_all = None
    anchor_rank_zero = None
    for i, r in enumerate(results, 1):
        if (abs(r["stop"] - ANCHOR_STOP) < 0.01 and abs(r["rr"] - ANCHOR_RR) < 0.01 and
                abs(r["gap"] - ANCHOR_GAP) < 0.01 and abs(r["tp1"] - ANCHOR_TP1) < 0.01):
            anchor_rank_all = i
            break
    for i, r in enumerate(zero_neg, 1):
        if (abs(r["stop"] - ANCHOR_STOP) < 0.01 and abs(r["rr"] - ANCHOR_RR) < 0.01 and
                abs(r["gap"] - ANCHOR_GAP) < 0.01 and abs(r["tp1"] - ANCHOR_TP1) < 0.01):
            anchor_rank_zero = i
            break

    print(f"\n  ANCHOR RANK:")
    print(f"    Overall: #{anchor_rank_all}/{len(results)} (stop={ANCHOR_STOP}, rr={ANCHOR_RR}, "
          f"gap={ANCHOR_GAP}, tp1={ANCHOR_TP1})")
    print(f"    0-neg-years: #{anchor_rank_zero}/{len(zero_neg)}")

    # -- Grid summary ----------------------------------------------------------
    n_profitable = sum(1 for r in results if r["net_r"] > 0)
    print(f"\n  GRID SUMMARY:")
    print(f"    Total combos tested: {len(results)}")
    print(f"    Skipped (<10 tick stop): {skipped_ticks}")
    print(f"    Skipped (tp1 < {MIN_TP1_RATIO}): {skipped_tp1}")
    print(f"    With 0 neg years: {len(zero_neg)} ({100*len(zero_neg)/len(results):.0f}%)")
    print(f"    Profitable: {n_profitable} ({100*n_profitable/len(results):.0f}%)")

    # -- Decision --------------------------------------------------------------
    if zero_neg:
        grid_winner = zero_neg[0]
        anchor_entry = next((r for r in results
                             if abs(r["stop"] - ANCHOR_STOP) < 0.01 and
                             abs(r["rr"] - ANCHOR_RR) < 0.01 and
                             abs(r["gap"] - ANCHOR_GAP) < 0.01 and
                             abs(r["tp1"] - ANCHOR_TP1) < 0.01), None)
        if anchor_entry:
            delta = grid_winner["calmar"] - anchor_entry["calmar"]
            print(f"\n  DECISION:")
            print(f"    Grid winner (0-neg): stop={grid_winner['stop']}, rr={grid_winner['rr']}, "
                  f"gap={grid_winner['gap']}, tp1={grid_winner['tp1']} | Calmar={grid_winner['calmar']:.2f}")
            print(f"    Anchor: Calmar={anchor_entry['calmar']:.2f}")
            print(f"    Delta: {delta:+.2f}")
            if delta > 0.5:
                print(f"    => ADOPT grid winner (delta > 0.5) — return to variable sweeps")
            else:
                print(f"    => KEEP anchor (delta <= 0.5) — proceed to robust pipeline")


if __name__ == "__main__":
    main()
