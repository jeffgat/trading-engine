#!/usr/bin/env python3
"""NQ Asia Continuation — Baseline.

Default ASIA_SESSION config from config.py.
  ORB: 20:00-20:15, entry until 23:15, flat 06:45-07:00
  stop=5.25%, min_gap_atr=0.9%, max_gap_pts=50.0
  rr=2.5, tp1=0.5, ATR=14, direction=both, continuation, 1s magnifier

Pass criteria: >100 trades AND PF >1.0.
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10  # 2016-2025 (10 full calendar years)

SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:15",
    entry_start="20:15",
    entry_end="23:15",
    flat_start="06:45",
    flat_end="07:00",
    stop_atr_pct=5.25,
    min_gap_atr_pct=0.9,
)

CONFIG = StrategyConfig(
    sessions=(SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.5,
    tp1_ratio=0.5,
    atr_length=14,
    impulse_close_filter=False,
    name="NQ Asia Baseline (fresh)",
)


def main():
    print("NQ Asia Continuation — Baseline")
    print("=" * 80)
    print(f"Config: rr={CONFIG.rr}, tp1={CONFIG.tp1_ratio}, stop={SESSION.stop_atr_pct}%")
    print(f"  ORB: {SESSION.orb_start}-{SESSION.orb_end}, entry<={SESSION.entry_end}, "
          f"flat={SESSION.flat_start}, ATR={CONFIG.atr_length}, dir={CONFIG.direction_filter}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        print("  WARNING: 1m data not found")
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    print("\nRunning backtest...", flush=True)
    t1 = time.time()
    trades = run_backtest(df_5m, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(f"  {len(trades)} trades [{time.time()-t1:.1f}s]")

    m = compute_metrics(trades)

    # Print results
    print(f"\n{'='*80}")
    print(f"  BASELINE RESULTS")
    print(f"{'='*80}")
    print(f"  Trades:  {m['total_trades']}")
    print(f"  WR:      {m['win_rate']:.1%}")
    print(f"  PF:      {m['profit_factor']:.2f}")
    print(f"  Sharpe:  {m['sharpe_ratio']:.3f}")
    print(f"  Net R:   {m['total_r']:.1f}")
    print(f"  R/yr:    {m['total_r'] / DATA_YEARS:.1f}")
    print(f"  Max DD:  {m['max_drawdown_r']:.1f}")
    print(f"  Calmar:  {m['calmar_ratio']:.2f}")

    # R by year
    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:")
        for yr, r in sorted(rby.items()):
            marker = " ***" if r < 0 else ""
            print(f"    {yr}: {r:+.1f}{marker}")

    # Pass/fail
    print(f"\n{'='*80}")
    trades_ok = m["total_trades"] > 100
    pf_ok = m["profit_factor"] > 1.0
    print(f"  Trades > 100: {'PASS' if trades_ok else 'FAIL'} ({m['total_trades']})")
    print(f"  PF > 1.0:     {'PASS' if pf_ok else 'FAIL'} ({m['profit_factor']:.2f})")

    if trades_ok and pf_ok:
        print(f"\n  >>> BASELINE PASS — proceed to variable sweeps")
    else:
        print(f"\n  >>> BASELINE FAIL — record NO-GO in learnings")

    print(f"\n  Runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
