#!/usr/bin/env python3
"""RTY NY Grid Sweep R1 — 4D grid search centered on R4 anchor.

Anchor: direction=long, stop=2.5%, rr=4.0, gap=0.5%, tp1=0.5, ATR=14, 15m ORB, entry≤12:00
Grid: stop × rr × gap × tp1

Selection criteria:
  1. Sort by Calmar (primary)
  2. Flag combos with 0 negative full years
  3. Report top 20 overall and top combos with 0 neg years
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from itertools import product

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import RTY
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=2.5,
    min_gap_atr_pct=0.5,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=RTY,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=4.0,
    tp1_ratio=0.5,
    atr_length=14,
    impulse_close_filter=False,
    name="RTY NY Grid R1",
)

# Grid dimensions
STOPS  = [2.0, 2.5, 3.0, 3.5]
RRS    = [3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
GAPS   = [0.5, 0.75, 1.0]
TP1S   = [0.4, 0.5, 0.6]

GRID = list(product(STOPS, RRS, GAPS, TP1S))
print(f"Grid size: {len(GRID)} combos ({len(STOPS)}×{len(RRS)}×{len(GAPS)}×{len(TP1S)})")


def main():
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | {time.time()-t0:.1f}s")
    print()

    results = []
    t_start = time.time()

    for i, (stop, rr, gap, tp1) in enumerate(GRID):
        cfg = with_overrides(ANCHOR, ny_stop_atr_pct=stop, rr=rr, ny_min_gap_atr_pct=gap, tp1_ratio=tp1)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        m = compute_metrics(trades)

        rby = m.get("r_by_year", {})
        full_years = {y: r for y, r in rby.items() if y not in ("2016", "2026")}
        neg_yrs = sum(1 for r in full_years.values() if r < 0)
        n_years = max(len(full_years), 1)
        avg_annual = m["total_r"] / n_years
        calmar = avg_annual / abs(m["max_drawdown_r"]) if m["max_drawdown_r"] != 0 else 0

        results.append({
            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
            "net_r": m["total_r"], "avg_annual": avg_annual,
            "max_dd": m["max_drawdown_r"], "calmar": calmar,
            "neg_yrs": neg_yrs,
            "neg_list": ",".join(y for y, r in sorted(full_years.items()) if r < 0),
        })

        if (i + 1) % 50 == 0 or i == len(GRID) - 1:
            elapsed = time.time() - t_start
            rate = (i + 1) / elapsed
            eta = (len(GRID) - i - 1) / rate
            print(f"  {i+1}/{len(GRID)} done [{elapsed:.0f}s, {rate:.1f}/s, ETA {eta:.0f}s]")

    total_time = time.time() - t_start
    print(f"\n  Grid complete in {total_time:.1f}s")
    print()

    # Sort by Calmar
    results.sort(key=lambda x: x["calmar"], reverse=True)

    # ── Top 20 overall ──
    HDR = (f"  {'Rank':>4} {'stop':>5} {'rr':>4} {'gap':>5} {'tp1':>4} "
           f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} {'Net R':>7} "
           f"{'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}")

    print("=" * 100)
    print("  TOP 20 BY CALMAR")
    print("=" * 100)
    print(HDR)
    for rank, r in enumerate(results[:20], 1):
        is_anchor = (r["stop"] == 2.5 and r["rr"] == 4.0 and r["gap"] == 0.5 and r["tp1"] == 0.5)
        marker = " <<< ANCHOR" if is_anchor else ""
        print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.2f} {r['tp1']:>4.1f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
              f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
              f"{r['calmar']:>7.2f} {r['neg_yrs']:>3} {r['neg_list']}{marker}")
    print()

    # ── Top combos with 0 neg years ──
    zero_neg = [r for r in results if r["neg_yrs"] == 0]
    print(f"  Combos with 0 negative years: {len(zero_neg)}/{len(results)}")
    print()
    if zero_neg:
        print("=" * 100)
        print("  TOP 20 WITH 0 NEGATIVE YEARS (by Calmar)")
        print("=" * 100)
        print(HDR)
        for rank, r in enumerate(zero_neg[:20], 1):
            is_anchor = (r["stop"] == 2.5 and r["rr"] == 4.0 and r["gap"] == 0.5 and r["tp1"] == 0.5)
            marker = " <<< ANCHOR" if is_anchor else ""
            print(f"  {rank:>4} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.2f} {r['tp1']:>4.1f} "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.3f} "
                  f"{r['net_r']:>7.1f} {r['avg_annual']:>6.1f} {r['max_dd']:>6.1f} "
                  f"{r['calmar']:>7.2f} {r['neg_yrs']:>3}{marker}")
        print()

    # ── Anchor rank ──
    for rank, r in enumerate(results, 1):
        if r["stop"] == 2.5 and r["rr"] == 4.0 and r["gap"] == 0.5 and r["tp1"] == 0.5:
            print(f"  Anchor rank: #{rank}/{len(results)}")
            break

    # ── Dimension dominance ──
    print()
    print("=" * 100)
    print("  DIMENSION DOMINANCE (top 20)")
    print("=" * 100)
    for dim_name, dim_values, dim_key in [
        ("stop", STOPS, "stop"), ("rr", RRS, "rr"),
        ("gap", GAPS, "gap"), ("tp1", TP1S, "tp1")
    ]:
        counts = defaultdict(int)
        for r in results[:20]:
            counts[r[dim_key]] += 1
        parts = "  ".join(f"{v}={counts.get(v, 0)}" for v in dim_values)
        print(f"  {dim_name}: {parts}")
    print()


if __name__ == "__main__":
    main()
