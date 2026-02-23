#!/usr/bin/env python3
"""ES NY ORB Continuation — Grid Sweep R1 (post variable sweep convergence).

Structural params locked from R1-R6 variable sweeps:
  ORB: 09:30-09:55 (25m)
  entry_end: 13:00
  flat: 15:50
  ATR: 3
  direction: long
  ICF: ON
  DOW: none (no exclusion)
  maxgap: OFF (insensitive)
  magnifier: 1s

Grid: stop × rr × gap × tp1
  stop: [3.0, 3.5, 4.0, 5.0]
  rr: [3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
  gap: [0.5, 1.0, 1.5, 2.0, 2.5]
  tp1: [0.2, 0.25, 0.3, 0.35, 0.4, 0.5]

Total: 4 × 6 × 5 × 6 = 720 combos
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

BASE_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:55",
    entry_start="09:55",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,       # will be overridden
    min_gap_atr_pct=1.5,    # will be overridden
    max_gap_points=9999.0,  # OFF
)

BASE_CONFIG = StrategyConfig(
    sessions=(BASE_SESSION,),
    instrument=ES,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.5,
    tp1_ratio=0.3,
    atr_length=3,
    impulse_close_filter=True,
)

STOP_VALUES = [3.0, 3.5, 4.0, 5.0]
RR_VALUES = [3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
GAP_VALUES = [0.5, 1.0, 1.5, 2.0, 2.5]
TP1_VALUES = [0.2, 0.25, 0.3, 0.35, 0.4, 0.5]


def neg_year_count(m):
    if "r_by_year" not in m:
        return 0
    current_year = str(datetime.now().year)
    return sum(1 for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year)


def main():
    total = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)
    print(f"ES NY Grid Sweep R1 — {total} combos")
    print("=" * 100)

    print("Loading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t_start:.1f}s]")

    results = []
    count = 0
    t_sweep = time.time()

    for stop in STOP_VALUES:
        for rr in RR_VALUES:
            for gap in GAP_VALUES:
                for tp1 in TP1_VALUES:
                    count += 1
                    sess = replace(BASE_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
                    config = replace(BASE_CONFIG, sessions=(sess,), rr=rr, tp1_ratio=tp1)
                    trades = run_backtest(df_5m, config, start_date=START_DATE,
                                         df_1m=df_1m, df_1s=df_1s)
                    m = compute_metrics(trades)
                    neg = neg_year_count(m)
                    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
                    results.append({
                        "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
                        "trades": m["total_trades"], "wr": m["win_rate"],
                        "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
                        "net_r": m["total_r"], "r_yr": r_yr,
                        "dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
                        "neg_years": neg, "r_by_year": m.get("r_by_year", {}),
                    })

                    if count % 50 == 0:
                        elapsed = time.time() - t_sweep
                        rate = count / elapsed * 60
                        eta = (total - count) / (count / elapsed) / 60
                        print(f"  [{count}/{total}] {elapsed:.0f}s ({rate:.0f}/min) ETA: {eta:.1f}m")

    elapsed = time.time() - t_sweep
    print(f"\n  Grid complete: {total} combos in {elapsed:.0f}s ({elapsed/60:.1f}m)")

    # ── RESULTS ──────────────────────────────────────────────────────
    # Sort by Calmar descending
    results.sort(key=lambda x: x["calmar"], reverse=True)

    # Top 20 by Calmar (all)
    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR (all combos)")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>4} {'gap':>4} {'tp1':>4} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
          f"{'Net R':>7} {'R/yr':>6} {'DD':>6} {'Calmar':>7} {'Neg':>3}")
    print(f"  {'─'*105}")
    for i, r in enumerate(results[:20], 1):
        print(f"  {i:>3} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>4.1f} {r['tp1']:>4.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
              f"{r['net_r']:>7.1f} {r['r_yr']:>6.1f} {r['dd']:>6.1f} {r['calmar']:>7.2f} {r['neg_years']:>3}")

    # Top 20 with 0 negative years
    zero_neg = [r for r in results if r["neg_years"] == 0]
    zero_neg.sort(key=lambda x: x["calmar"], reverse=True)
    print(f"\n{'='*110}")
    print(f"  TOP 20 BY CALMAR (0 negative years only) — {len(zero_neg)}/{total} qualify")
    print(f"{'='*110}")
    print(f"  {'#':>3} {'stop':>5} {'rr':>4} {'gap':>4} {'tp1':>4} "
          f"{'Trades':>6} {'WR':>5} {'PF':>5} {'Sharpe':>6} "
          f"{'Net R':>7} {'R/yr':>6} {'DD':>6} {'Calmar':>7}")
    print(f"  {'─'*105}")
    for i, r in enumerate(zero_neg[:20], 1):
        yrs = sorted(r["r_by_year"].items())
        yr_str = " ".join(f"{yr}:{v:+.0f}" for yr, v in yrs)
        print(f"  {i:>3} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>4.1f} {r['tp1']:>4.2f} "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} {r['sharpe']:>6.2f} "
              f"{r['net_r']:>7.1f} {r['r_yr']:>6.1f} {r['dd']:>6.1f} {r['calmar']:>7.2f}")
        print(f"      {yr_str}")

    # Summary stats
    print(f"\n{'='*110}")
    print(f"  GRID SUMMARY")
    print(f"{'='*110}")
    print(f"  Total combos: {total}")
    print(f"  Zero neg years: {len(zero_neg)} ({len(zero_neg)/total*100:.0f}%)")
    profitable = sum(1 for r in results if r["net_r"] > 0)
    print(f"  Profitable: {profitable} ({profitable/total*100:.0f}%)")
    high_calmar = sum(1 for r in results if r["calmar"] > 10)
    print(f"  Calmar > 10: {high_calmar} ({high_calmar/total*100:.0f}%)")

    total_time = time.time() - t_start
    print(f"\n  Total runtime: {total_time:.0f}s ({total_time/60:.1f}m)")


if __name__ == "__main__":
    main()
