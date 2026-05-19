#!/usr/bin/env python3
"""Save NQ NY Long R11 Final to the main DB.

Config: stop=7.0%, rr=3.5, gap=2.5%, tp1=0.4, ORB=20m (09:30-09:50),
        entry<=12:00, flat=15:30, ATR=12, direction=long, excl-Fri, ICF=OFF, 1s magnifier

Full-history (2016-2026): 561 trades, 53.3% WR, PF 1.51, Sharpe 2.90,
  135.0R (13.5 R/yr), DD -6.0R, Calmar 22.51, 0 negative years

WF: 7 folds, WF efficiency 0.551, stability 1.000 (high), combined OOS +56.8R
Hold-out (2025+): 54 trades, Sharpe 2.90, PF 1.52, +13.1R
Monte Carlo: 99.1% survival at -25R ruin
Verdict: CONDITIONAL — 4/5 passed. Phase 3 (avg annual R 8.1 < 12.0) failed.
"""

import argparse
import sys
import time

import pandas as pd

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {4}  # excl Friday
DEFAULT_START = "2016-04-17"
DEFAULT_END_EXCLUSIVE = "2026-03-25"


def make_config():
    sess = SessionConfig(
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
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        impulse_close_filter=False,
        name="NQ NY Cont Long R11 Final 2016-2026",
        notes=(
            "Fresh optimization on fixed engine (TP1+BE same-bar exit bug fix, commit 6079ad4). "
            "11 rounds variable sweeps + 3 grid sweeps. "
            "Anchor ranked #1/375 in Grid R3. "
            "Pipeline: CONDITIONAL (4/5 — Phase 3 avg annual R 8.1 < 12.0 on WF OOS). "
            "WF stability 1.000 (high), MC survival 99.1% at -25R. "
            "DOW filter: excl Friday (applied post-backtest)."
        ),
    )


def _load_1m_with_fallback(filename: str, start: str | None, end: str | None):
    try:
        return load_1m_for_5m(filename, start=start, end=end)
    except FileNotFoundError:
        df_1s = load_1s_for_5m(filename, start=start, end=end)
        df_1m = (
            df_1s.resample("1min")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna(subset=["open"])
        )
        return df_1m


def main():
    parser = argparse.ArgumentParser(description="Save NQ NY ORB R11 Final to the main DB.")
    parser.add_argument("--name", default=None, help="Dashboard experiment name override.")
    parser.add_argument("--start", default=DEFAULT_START, help="Inclusive start date.")
    parser.add_argument("--end-exclusive", default=DEFAULT_END_EXCLUSIVE, help="Exclusive end date.")
    args = parser.parse_args()

    config = make_config()
    if args.name:
        from dataclasses import replace

        config = replace(config, name=args.name)

    print(f"Saving: {config.name}")
    print(f"Config: stop=7.0% | rr=3.5 | gap=2.5% | tp1=0.4 | ATR=12")
    print(f"Long only | DOW excl Fri | ICF off | 1s mag")
    print(f"Date window: {args.start} <= trade date < {args.end_exclusive}")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv", start=args.start)
    df_1m = _load_1m_with_fallback("NQ_5m.csv", start=args.start, end=args.end_exclusive)
    df_1s = load_1s_for_5m("NQ_5m.csv", start=args.start, end=args.end_exclusive)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    print("\nRunning backtest...", flush=True)
    t0 = time.time()
    trades = run_backtest(df_5m, config, start_date=args.start, end_date=args.end_exclusive, df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time()-t0:.1f}s")

    print(f"\n  Trades: {m['total_trades']}")
    print(f"  WR: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}")

    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:")
        for yr, r in sorted(rby.items()):
            print(f"    {yr}: {r:+.1f}R")

    # Median stop check
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    med_stop = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0
    print(f"\n  Median stop: {med_stop:.1f} ticks")
    if med_stop < 10:
        print("  ERROR: Median stop < 10 ticks — NOT saving!")
        return

    print("\nSaving to DB...", flush=True)
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved! Result ID: {result_id}")
    print(f"  Experiment name: {config.name}")


if __name__ == "__main__":
    main()
