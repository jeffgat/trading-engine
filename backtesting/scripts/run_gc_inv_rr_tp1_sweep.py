#!/usr/bin/env python3
"""Sweep rr × tp1_ratio for GC NY Inversion Longs v7 + magnifier.

Goal: find configs with WR >= 35% while keeping positive expectancy.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

GC_NY_INVERSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",
    entry_start="09:35",
    entry_end="14:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=1.25,
)

BASE_CONFIG = StrategyConfig(
    rr=5.0,
    tp1_ratio=0.9,
    risk_usd=5000.0,
    atr_length=30,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_INVERSION,),
    instrument=GC,
    strategy="inversion",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

PARAM_RANGES = {
    "rr": [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
    "tp1_ratio": [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
}


def main():
    print("Loading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")
    print()

    configs = generate_param_grid(BASE_CONFIG, PARAM_RANGES)
    print(f"Running {len(configs)} backtests (rr × tp1_ratio)...")
    t0 = time.time()

    def progress(done, total):
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        print(f"\r  [{done}/{total}] {done/total*100:.0f}% | {rate:.1f}/s", end="", flush=True)

    results = run_sweep(df, configs, n_workers=8, start_date="2016-01-01", df_1m=df_1m, progress_fn=progress)
    print(f"\n  Done in {time.time() - t0:.1f}s")
    print()

    # Score and sort
    scored = []
    for config, trades in results:
        m = compute_metrics(trades)
        scored.append((config.rr, config.tp1_ratio, m))

    # Print full grid: rows=rr, cols=tp1_ratio, cell=WR
    rr_vals = sorted(set(s[0] for s in scored))
    tp1_vals = sorted(set(s[1] for s in scored))

    # Build lookup
    lookup = {}
    for rr, tp1, m in scored:
        lookup[(rr, tp1)] = m

    # Win Rate grid
    print("WIN RATE (%) — rows: rr, cols: tp1_ratio")
    print(f"  {'rr':>5s}", end="")
    for tp1 in tp1_vals:
        print(f"  {tp1:>6.1f}", end="")
    print()
    print("  " + "-" * (7 + 8 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"  {rr:>5.1f}", end="")
        for tp1 in tp1_vals:
            m = lookup[(rr, tp1)]
            wr = m["win_rate"] * 100
            marker = "*" if wr >= 35 else " "
            print(f"  {wr:>5.1f}{marker}", end="")
        print()
    print("  (* = WR >= 35%)")
    print()

    # Net R grid
    print("NET R — rows: rr, cols: tp1_ratio")
    print(f"  {'rr':>5s}", end="")
    for tp1 in tp1_vals:
        print(f"  {tp1:>6.1f}", end="")
    print()
    print("  " + "-" * (7 + 8 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"  {rr:>5.1f}", end="")
        for tp1 in tp1_vals:
            m = lookup[(rr, tp1)]
            r = m["total_r"]
            print(f"  {r:>6.1f}", end="")
        print()
    print()

    # Sharpe grid
    print("SHARPE — rows: rr, cols: tp1_ratio")
    print(f"  {'rr':>5s}", end="")
    for tp1 in tp1_vals:
        print(f"  {tp1:>6.1f}", end="")
    print()
    print("  " + "-" * (7 + 8 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"  {rr:>5.1f}", end="")
        for tp1 in tp1_vals:
            m = lookup[(rr, tp1)]
            s = m["sharpe_ratio"]
            print(f"  {s:>6.3f}", end="")
        print()
    print()

    # Max DD grid
    print("MAX DD (R) — rows: rr, cols: tp1_ratio")
    print(f"  {'rr':>5s}", end="")
    for tp1 in tp1_vals:
        print(f"  {tp1:>6.1f}", end="")
    print()
    print("  " + "-" * (7 + 8 * len(tp1_vals)))
    for rr in rr_vals:
        print(f"  {rr:>5.1f}", end="")
        for tp1 in tp1_vals:
            m = lookup[(rr, tp1)]
            dd = m["max_drawdown_r"]
            print(f"  {dd:>6.1f}", end="")
        print()
    print()

    # Filter WR >= 35% and rank by Sharpe
    print("=" * 80)
    print("CANDIDATES WITH WR >= 35% (sorted by Sharpe)")
    print("=" * 80)
    candidates = [(rr, tp1, m) for rr, tp1, m in scored if m["win_rate"] >= 0.35 and m["total_r"] > 0]
    candidates.sort(key=lambda x: x[2]["sharpe_ratio"], reverse=True)

    if not candidates:
        print("  No configs with WR >= 35% and positive R found.")
    else:
        print(f"  {'rr':>5s} {'tp1':>5s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s} {'Avg R':>7s}")
        print(f"  {'-'*55}")
        for rr, tp1, m in candidates:
            print(f"  {rr:>5.1f} {tp1:>5.1f} {m['total_trades']:>7d} {m['win_rate']:>5.1%} {m['total_r']:>7.1f} "
                  f"{m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} {m['max_drawdown_r']:>7.1f} {m['avg_r']:>7.3f}")
    print()


if __name__ == "__main__":
    main()
