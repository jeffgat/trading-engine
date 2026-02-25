#!/usr/bin/env python3
"""Sweep max_gap_points for YM NY 5m ORB + ATR10.

Tests on both 11:30 and 13:00 cutoff candidates.
Values: 25, 50, 75, 100, 150, 200, 0 (no limit).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics


def make_config(entry_end, max_gap_points):
    instrument = get_instrument("YM")
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=1.5,
        max_gap_points=max_gap_points,
    )
    return StrategyConfig(
        rr=4.0,
        tp1_ratio=0.55,
        atr_length=10,
        sessions=(session,),
        instrument=instrument,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def run_and_report(label, cfg, df):
    trades = run_backtest(df, cfg, start_date="2016-03-01")
    m = compute_metrics(trades)
    risk_usd = cfg.risk_usd
    total_r = m["total_pnl_usd"] / risk_usd
    dd_r = abs(m["max_drawdown_usd"]) / risk_usd
    return {
        "label": label,
        "trades": m["total_trades"],
        "win_rate": m["win_rate"],
        "total_r": total_r,
        "sharpe": m["sharpe_ratio"],
        "sortino": m["sortino_ratio"],
        "calmar": m["calmar_ratio"],
        "pf": m["profit_factor"],
        "dd_r": dd_r,
        "avg_r": m["avg_r"],
    }


def print_table(title, results):
    print(f"\n{'=' * 105}")
    print(title)
    print("=" * 105)
    print(
        f"  {'Config':<30s} | {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} | "
        f"{'PnL(R)':>8} {'DD(R)':>6} {'PF':>5} {'WR':>6} {'Trd':>5} {'AvgR':>6}"
    )
    print("  " + "-" * 100)
    for r in results:
        print(
            f"  {r['label']:<30s} | {r['sharpe']:7.3f} {r['sortino']:8.3f} {r['calmar']:7.2f} | "
            f"{r['total_r']:>7.1f}R {r['dd_r']:6.1f} {r['pf']:5.2f} {r['win_rate']:5.1f}% {r['trades']:5d} {r['avg_r']:6.3f}"
        )


def main():
    print("Loading YM data...")
    t0 = time.time()
    df = load_5m_data("YM_5m.csv")
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time()-t0:.1f}s]")

    gap_values = [25, 50, 75, 100, 150, 200, 0]  # 0 = no limit

    for entry_end, cutoff_label in [("11:30", "11:30"), ("13:00", "13:00")]:
        results = []
        print(f"\nSweeping max_gap_points for {cutoff_label} cutoff...")
        for gap in gap_values:
            label = f"max_gap={gap}pts" if gap > 0 else "max_gap=none"
            cfg = make_config(entry_end, max_gap_points=float(gap))
            r = run_and_report(label, cfg, df)
            results.append(r)
            print(f"  {label}: Sharpe={r['sharpe']:.3f} Trades={r['trades']} AvgR={r['avg_r']:.3f} DD={r['dd_r']:.1f}R")

        print_table(f"MAX GAP POINTS SWEEP — {cutoff_label} CUTOFF", results)

    print("\nDone!")


if __name__ == "__main__":
    main()
