#!/usr/bin/env python3
"""ES LDN Continuation Both — Fresh Baseline (Full Optimization Step 1).

Uses default LDN session config and standard StrategyConfig defaults.
1s bar magnifier enabled. Full history 2016-01-01 to present.

Pass criteria: >100 trades AND profit factor >1.0.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

# -- Config -------------------------------------------------------------------

START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

ES_LDN_SESSION = SessionConfig(
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

BASELINE = StrategyConfig(
    rr=2.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=14,
    sessions=(ES_LDN_SESSION,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
    name="ES LDN Baseline",
)

# -- Helpers ------------------------------------------------------------------


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("  ES LDN CONTINUATION BOTH — BASELINE")
    print("=" * 70)
    print(f"  Start date: {START_DATE}")
    print(f"  ORB window: {ES_LDN_SESSION.orb_start}-{ES_LDN_SESSION.orb_end} (15m)")
    print(f"  Entry:      {ES_LDN_SESSION.entry_start}-{ES_LDN_SESSION.entry_end}")
    print(f"  Flat:       {ES_LDN_SESSION.flat_start}-{ES_LDN_SESSION.flat_end}")
    print(f"  Stop ATR:   {ES_LDN_SESSION.stop_atr_pct}%")
    print(f"  Min gap:    {ES_LDN_SESSION.min_gap_atr_pct}% ATR")
    print(f"  RR:         {BASELINE.rr}")
    print(f"  TP1:        {BASELINE.tp1_ratio}")
    print(f"  ATR len:    {BASELINE.atr_length}")
    print(f"  Direction:  {BASELINE.direction_filter}")
    print(f"  Strategy:   {BASELINE.strategy}")
    print(f"  Magnifier:  1s (with 1m/5m fallback)")
    print()

    # Load data
    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(ES.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(ES.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(ES.data_file, start=START_DATE)
    load_time = time.time() - t0

    print(f"  5m bars:  {len(df):,}")
    print(f"  1m bars:  {len(df_1m):,}" if df_1m is not None else "  1m bars:  None")
    print(f"  1s bars:  {len(df_1s):,}" if df_1s is not None else "  1s bars:  None")
    print(f"  Load time: {load_time:.1f}s")
    print()

    # Run backtest
    print("  Running backtest...", flush=True)
    t0 = time.time()
    trades = run_backtest(df, BASELINE, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    bt_time = time.time() - t0
    print(f"  Backtest time: {bt_time:.1f}s")

    # Compute metrics
    m = compute_metrics(trades)

    # Print results
    print()
    print("=" * 70)
    print("  BASELINE RESULTS")
    print("=" * 70)
    print(f"  {'Trades':<24s} {m['total_trades']:>10d}")
    print(f"  {'Win Rate':<24s} {m['win_rate']:>9.1%}")
    print(f"  {'Profit Factor':<24s} {m['profit_factor']:>10.2f}")
    print(f"  {'Net R':<24s} {m['total_r']:>9.1f}R")
    print(f"  {'R/yr':<24s} {r_per_year(m):>9.1f}R")
    print(f"  {'Max DD':<24s} {m['max_drawdown_r']:>9.1f}R")
    print(f"  {'Calmar':<24s} {m['calmar_ratio']:>10.2f}")
    print(f"  {'Sharpe':<24s} {m['sharpe_ratio']:>10.3f}")
    print(f"  {'Neg full years':<24s} {neg_years(m):>10d}")

    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:")
        for y, r in sorted(rby.items()):
            flag = " <--" if y in FULL_YEARS and r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")

    # Exit breakdown
    exits = m.get("exit_breakdown", {})
    if exits:
        print(f"\n  Exit breakdown:")
        for etype, count in sorted(exits.items()):
            print(f"    {etype}: {count}")

    # Pass/fail check
    print()
    print("=" * 70)
    print("  PASS CRITERIA")
    print("=" * 70)
    checks = {
        "Trades > 100": m["total_trades"] > 100,
        "Profit Factor > 1.0": m["profit_factor"] > 1.0,
    }
    all_pass = True
    for name, passed in checks.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")
        if not passed:
            all_pass = False

    if all_pass:
        print("\n  >>> BASELINE PASSED — proceed to Step 2 (variable sweeps)")
        print(f"  >>> Initial anchor: stop={ES_LDN_SESSION.stop_atr_pct}%, "
              f"rr={BASELINE.rr}, gap={ES_LDN_SESSION.min_gap_atr_pct}%, "
              f"tp1={BASELINE.tp1_ratio}, ATR={BASELINE.atr_length}, "
              f"ORB 15m, flat {ES_LDN_SESSION.flat_start}")
    else:
        print("\n  >>> BASELINE FAILED — record as NO-GO in learnings, stop workflow")
