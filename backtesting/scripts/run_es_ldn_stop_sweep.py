#!/usr/bin/env python3
"""ES LDN Continuation Both — Stop ATR % sweep (3-15%).

Anchor (R11): stop=6.0%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14, max_gap=20%ATR,
ORB 10m, entry 08:25, flat 08:20, DOW excl Mon, ICF off, 1s mag.
Post fill-bar fix engine. Sweep to see if wider stops help.
"""

import sys, time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, MON

START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]
DOW_EXCLUDED = {MON}

ANCHOR_SESSION = SessionConfig(
    name="LDN", orb_start="03:00", orb_end="03:10", entry_start="03:10",
    entry_end="08:25", flat_start="08:20", flat_end="08:25",
    stop_atr_pct=6.0, min_gap_atr_pct=1.0, max_gap_points=0.0,
)
ANCHOR = StrategyConfig(
    rr=4.0, tp1_ratio=0.5, risk_usd=5000.0, atr_length=14,
    sessions=(ANCHOR_SESSION,), instrument=ES, strategy="continuation",
    direction_filter="both", use_bar_magnifier=True,
)

def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)

def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0

def calmar(m): return m.get("calmar_ratio", 0.0)

if __name__ == "__main__":
    print("=" * 100)
    print("  ES LDN CONTINUATION BOTH — STOP ATR % SWEEP (Post Fill-Bar Fix)")
    print("=" * 100)
    print(f"  Anchor (R11): stop=6.0%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14, max_gap=20%ATR")
    print(f"  ORB 10m, entry 08:25, flat 08:20, DOW excl Mon, 1s mag")
    print(f"  Sweep: 5.5% to 6.5% ATR (0.1 increments)\n")

    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(ES.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(ES.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(ES.data_file, start=START_DATE)
    print(f"  Data loaded in {time.time()-t0:.1f}s\n", flush=True)

    stop_values = [round(5.5 + i * 0.1, 1) for i in range(11)]  # 5.5 to 6.5

    print(f"  {'Stop%':<8s} {'Trades':>7s} {'WR':>7s} {'PF':>7s} {'Sharpe':>8s} "
          f"{'Net R':>8s} {'R/yr':>7s} {'MaxDD':>8s} {'Calmar':>8s} {'NegYr':>6s}")
    print(f"  {'-'*8} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*6}")

    for stop in stop_values:
        sess = replace(ANCHOR_SESSION, stop_atr_pct=stop)
        config = replace(ANCHOR, sessions=(sess,))
        trades = run_backtest(df, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        trades = apply_dow_filter(trades, DOW_EXCLUDED)
        m = compute_metrics(trades)
        marker = " <<<" if stop == 6.0 else ""
        print(f"  {stop:<8.1f} {m['total_trades']:>7d} {m['win_rate']:>6.1%} "
              f"{m['profit_factor']:>7.2f} {m['sharpe_ratio']:>8.3f} "
              f"{m['total_r']:>7.1f}R {r_per_year(m):>6.1f}R "
              f"{m['max_drawdown_r']:>7.1f}R {calmar(m):>8.2f} "
              f"{neg_years(m):>5d}{marker}", flush=True)

        rby = m.get("r_by_year", {})
        if rby:
            parts = [f"{y}:{r:+.0f}" for y, r in sorted(rby.items())]
            print(f"           R/yr: {', '.join(parts)}")
