#!/usr/bin/env python3
"""NQ Asia Short Grid Sweep R1 -- 4D grid centered on converged R3 anchor.

Anchor (from variable sweeps R1-R3):
  ORB: 20:00-20:10, entry until 23:00, flat 23:00-07:00
  stop=5.0%, rr=2.5, gap=1.0%, tp1=0.6
  ATR=30, direction=short, ICF=ON, continuation, 1s magnifier
  DOW gate: excl Thu

Grid: stop x rr x gap x tp1
If winner differs from anchor (Calmar delta > 0.5) -> re-run variable sweeps.
"""

import sys
import time
from collections import defaultdict
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
START_YEAR = str(2016)
INSTRUMENT_NAME = "NQ"
SESSION_NAME = "Asia"

ANCHOR_STOP = 5.0
ANCHOR_RR = 2.5
ANCHOR_GAP = 1.0
ANCHOR_TP1 = 0.6

DOW_EXCL = {3}  # excl Thursday

ANCHOR_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:10",
    entry_start="20:10",
    entry_end="23:00",
    flat_start="23:00",
    flat_end="07:00",
    stop_atr_pct=ANCHOR_STOP,
    min_gap_atr_pct=ANCHOR_GAP,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="short",
    rr=ANCHOR_RR,
    tp1_ratio=ANCHOR_TP1,
    atr_length=30,
    impulse_close_filter=True,
    name="NQ Asia Short Grid Sweep R1",
)

# Grid dimensions -- narrow range centered on anchor
STOPS = [3.5, 4.0, 5.0, 6.0, 7.0]
RRS   = [2.0, 2.25, 2.5, 2.75, 3.0]
GAPS  = [0.75, 0.9, 1.0, 1.25, 1.5]
TP1S  = [0.4, 0.5, 0.6, 0.7]

GRID = list(product(STOPS, RRS, GAPS, TP1S))
print(f"Grid size: {len(GRID)} combos ({len(STOPS)}x{len(RRS)}x{len(GAPS)}x{len(TP1S)})")


MIN_STOP_TICKS = 10


def median_stop_ticks(trades):
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


def neg_year_set(rby: dict) -> set:
    current_year = str(datetime.now().year)
    return {yr for yr, r in rby.items() if r < 0 and str(yr) != current_year}


def main():
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} SHORT -- Grid Sweep R1 ({len(GRID)} combos)")
    print("=" * 110)
    print(f"Anchor: stop={ANCHOR_STOP}%, rr={ANCHOR_RR}, gap={ANCHOR_GAP}%, tp1={ANCHOR_TP1}")
    print(f"Grid: stop={STOPS} x rr={RRS} x gap={GAPS} x tp1={TP1S}")
    print(f"DOW excl: {DOW_EXCL}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        print("  WARNING: 1m data not found — using 5m only")
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | 1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time() - t0:.1f}s]")

    results = []
    skipped = 0
    t_start = time.time()

    for i, (stop, rr, gap, tp1) in enumerate(GRID):
        sess = replace(ANCHOR_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
        cfg = replace(ANCHOR, sessions=(sess,), rr=rr, tp1_ratio=tp1)
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        if DOW_EXCL:
            trades = apply_dow_filter(trades, DOW_EXCL)
        if median_stop_ticks(trades) < MIN_STOP_TICKS:
            skipped += 1
            continue
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in (START_YEAR, str(datetime.now().year))}
        neg_yrs = sum(1 for r in full_years.values() if r < 0)
        n_years = max(len(full_years), 1)
        calmar = m.get("calmar_ratio", 0)

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "avg_annual": m["total_r"] / n_years,
            "max_dd": m["max_drawdown_r"], "calmar": calmar,
            "neg_yrs": neg_yrs,
            "neg_list": ",".join(y for y, r in sorted(full_years.items()) if r < 0),
            "r_by_year": rby,
        })

        if (i + 1) % 50 == 0 or i == len(GRID) - 1:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            eta = (len(GRID) - i - 1) / rate
            print(f"  {i+1}/{len(GRID)} done [{elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s]", flush=True)

    total_time = time.time() - t_start
    print(f"\n  Grid complete in {total_time:.1f}s ({total_time / 60:.1f}m)")
    print(f"  Skipped {skipped} combos (median stop < {MIN_STOP_TICKS} ticks)")

    results.sort(key=lambda x: x["calmar"], reverse=True)

    HDR = (f"  {'#':>4} {'Stop':>5} {'RR':>4} {'Gap':>5} {'TP1':>4} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
           f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")

    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR")
    print(f"{'='*110}")
    print(HDR)
    print(f"  {'-'*105}")

    for rank, r in enumerate(results[:20], 1):
        is_anchor = (abs(r["stop"] - ANCHOR_STOP) < 0.01 and abs(r["rr"] - ANCHOR_RR) < 0.01
                     and abs(r["gap"] - ANCHOR_GAP) < 0.01 and abs(r["tp1"] - ANCHOR_TP1) < 0.01)
        marker = " <<< ANCHOR" if is_anchor else ""
        print(f"  {rank:>4} {r['stop']:>5.2f} {r['rr']:>4.1f} {r['gap']:>5.2f} {r['tp1']:>4.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3} {r['neg_list']}{marker}")
        if rank <= 5:
            years = sorted(r["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
            print(f"        R by year: {yr_str}")

    # Warn if winner is at grid boundary
    winner = results[0]
    edge_warnings = []
    if winner["stop"] in (STOPS[0], STOPS[-1]):
        edge_warnings.append(f"stop={winner['stop']}")
    if winner["rr"] in (RRS[0], RRS[-1]):
        edge_warnings.append(f"rr={winner['rr']}")
    if winner["gap"] in (GAPS[0], GAPS[-1]):
        edge_warnings.append(f"gap={winner['gap']}")
    if winner["tp1"] in (TP1S[0], TP1S[-1]):
        edge_warnings.append(f"tp1={winner['tp1']}")
    if edge_warnings:
        print(f"\n  WARNING: Winner at grid boundary on: {', '.join(edge_warnings)}")
        print("  Consider expanding the grid in those dimensions before trusting this result.")

    # Top 20 with 0 negative years
    zero_neg = [r for r in results if r["neg_yrs"] == 0]
    print(f"\n  Combos with 0 negative years: {len(zero_neg)}/{len(results)}")
    if zero_neg:
        print(f"\n{'='*110}")
        print(f"  TOP 20 WITH 0 NEGATIVE YEARS (by Calmar)")
        print(f"{'='*110}")
        print(HDR)
        print(f"  {'-'*105}")
        for rank, r in enumerate(zero_neg[:20], 1):
            is_anchor = (abs(r["stop"] - ANCHOR_STOP) < 0.01 and abs(r["rr"] - ANCHOR_RR) < 0.01
                         and abs(r["gap"] - ANCHOR_GAP) < 0.01 and abs(r["tp1"] - ANCHOR_TP1) < 0.01)
            marker = " <<< ANCHOR" if is_anchor else ""
            print(f"  {rank:>4} {r['stop']:>5.2f} {r['rr']:>4.1f} {r['gap']:>5.2f} {r['tp1']:>4.2f} "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
                  f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
                  f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}{marker}")
            if rank <= 5:
                years = sorted(r["r_by_year"].items())
                yr_str = "  ".join(f"{yr}:{v:+.0f}" for yr, v in years)
                print(f"        R by year: {yr_str}")

    # Anchor rank
    anchor_rank = None
    anchor_calmar = 0
    for rank, r in enumerate(results, 1):
        if (abs(r["stop"] - ANCHOR_STOP) < 0.01 and abs(r["rr"] - ANCHOR_RR) < 0.01
                and abs(r["gap"] - ANCHOR_GAP) < 0.01 and abs(r["tp1"] - ANCHOR_TP1) < 0.01):
            anchor_rank = rank
            anchor_calmar = r["calmar"]
            break
    if anchor_rank:
        print(f"\n  Anchor rank: #{anchor_rank}/{len(results)} (Calmar {anchor_calmar:.2f})")

    # Dimension dominance (top 20)
    print(f"\n{'='*110}")
    print(f"  DIMENSION DOMINANCE (top 20)")
    print(f"{'='*110}")
    for dim_name, dim_values, dim_key in [
        ("stop", STOPS, "stop"), ("rr", RRS, "rr"),
        ("gap", GAPS, "gap"), ("tp1", TP1S, "tp1"),
    ]:
        counts = defaultdict(int)
        for r in results[:20]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")

    # Decision
    if results:
        winner_calmar = results[0]["calmar"]
        if anchor_rank and abs(winner_calmar - anchor_calmar) > 0.5:
            print(f"\n  *** GRID WINNER DIFFERS FROM ANCHOR (Calmar delta = "
                  f"{winner_calmar - anchor_calmar:+.2f}) ***")
            print(f"  --> Update anchor to grid winner and re-run variable sweeps")
        else:
            print(f"\n  Grid confirms anchor (Calmar delta <= 0.5). Proceed to robust pipeline.")

    print(f"\n  Total runtime: {total_time:.0f}s ({total_time / 60:.1f}m)")


if __name__ == "__main__":
    main()
