#!/usr/bin/env python3
"""NQ NY Continuation — Stop ORB% vs ATR% Head-to-Head Comparison.

Compares two stop-sizing approaches on the NQ NY production config:
  1. ATR-based: stop_dist = (stop_atr_pct / 100) * daily_atr  (current default)
  2. ORB-based: stop_dist = (stop_orb_pct / 100) * orb_range  (new alternative)

The ORB range is the actual session structure the strategy trades off,
so it may be a more relevant reference than a backward-looking 14-day ATR.
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# NQ NY production anchor
ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=6.75,
    min_gap_atr_pct=2.5,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    rr=3.25,
    tp1_ratio=0.55,
    atr_length=14,
)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0

def calmar(m):
    return m.get("calmar_ratio", 0.0)

def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def run_and_measure(df, config, df_1m, df_1s):
    trades = run_backtest(df, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return trades, compute_metrics(trades)


def print_sweep_table(results, dim_name, anchor_value=None):
    print(f"\n{'='*95}")
    print(f"  DIMENSION: {dim_name}" + (f" (anchor = {anchor_value})" if anchor_value else ""))
    print(f"{'='*95}")
    print(f"  {'Value':<15s} {'Trades':>7s} {'WR':>7s} {'PF':>7s} {'Sharpe':>8s} "
          f"{'Net R':>8s} {'R/yr':>7s} {'MaxDD':>8s} {'Calmar':>8s} {'NegYr':>6s}")
    print(f"  {'-'*15} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*6}")
    for val, m in results:
        marker = " <<<" if anchor_value is not None and str(val) == str(anchor_value) else ""
        print(f"  {str(val):<15s} {m['total_trades']:>7d} {m['win_rate']:>6.1%} "
              f"{m['profit_factor']:>7.2f} {m['sharpe_ratio']:>8.3f} "
              f"{m['total_r']:>7.1f}R {r_per_year(m):>6.1f}R "
              f"{m['max_drawdown_r']:>7.1f}R {calmar(m):>8.2f} "
              f"{neg_years(m):>5d}{marker}")


if __name__ == "__main__":
    print("=" * 95)
    print("  NQ NY CONTINUATION — STOP ORB% vs ATR% COMPARISON")
    print("=" * 95)
    print(f"  Anchor: NQ NY prod config — stop_atr=6.75%, rr=3.25, tp1=0.55, gap=2.5%, max_gap=25%ATR")
    print(f"  ORB 09:30-09:45, entry until 13:00, flat 15:50, ATR=14, both dirs\n")

    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(NQ.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(NQ.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(NQ.data_file, start=START_DATE)
    print(f"  Data loaded in {time.time()-t0:.1f}s\n", flush=True)

    # --- ATR% sweep (reference) ---
    print("  Running ATR% stop sweep...", flush=True)
    t1 = time.time()
    atr_results = []
    for v in [3, 5, 6.75, 8, 10, 12, 15]:
        sess = replace(ANCHOR_SESSION, stop_atr_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        atr_results.append((f"ATR {v}%", m))
    print(f"  ATR sweep done in {time.time()-t1:.1f}s", flush=True)
    print_sweep_table(atr_results, "Stop ATR%", "ATR 6.75%")

    # --- ORB% sweep ---
    print("\n  Running ORB% stop sweep...", flush=True)
    t2 = time.time()
    orb_results = []
    for v in [25, 50, 75, 100, 125, 150, 200]:
        # Disable ATR stop (set to 0 doesn't work since it would give 0 stop_dist),
        # instead set stop_orb_pct which takes priority when > 0
        sess = replace(ANCHOR_SESSION, stop_orb_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        orb_results.append((f"ORB {v}%", m))
    print(f"  ORB sweep done in {time.time()-t2:.1f}s", flush=True)
    print_sweep_table(orb_results, "Stop ORB%")

    # --- Combined comparison ---
    all_results = atr_results + orb_results
    print_sweep_table(all_results, "All Stop Methods (ATR vs ORB)")

    # --- Best from each ---
    best_atr = max(atr_results, key=lambda x: calmar(x[1]))
    best_orb = max(orb_results, key=lambda x: calmar(x[1]))

    print(f"\n{'='*95}")
    print(f"  BEST BY CALMAR")
    print(f"{'='*95}")
    print(f"  ATR-based: {best_atr[0]} — Calmar={calmar(best_atr[1]):.2f}, "
          f"Sharpe={best_atr[1]['sharpe_ratio']:.3f}, Net R={best_atr[1]['total_r']:.1f}, "
          f"MaxDD={best_atr[1]['max_drawdown_r']:.1f}R, Trades={best_atr[1]['total_trades']}")
    print(f"  ORB-based: {best_orb[0]} — Calmar={calmar(best_orb[1]):.2f}, "
          f"Sharpe={best_orb[1]['sharpe_ratio']:.3f}, Net R={best_orb[1]['total_r']:.1f}, "
          f"MaxDD={best_orb[1]['max_drawdown_r']:.1f}R, Trades={best_orb[1]['total_trades']}")

    total_time = time.time() - t0
    print(f"\n  Total time: {total_time:.0f}s")
