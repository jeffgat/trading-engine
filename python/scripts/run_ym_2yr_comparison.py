#!/usr/bin/env python3
"""Compare new WF candidates vs old WF Validated on past 2 years (2024-2026)."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics


def make_config(orb_end, entry_start, entry_end, atr_length, label):
    instrument = get_instrument("YM")
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=orb_end,
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=1.5,
        max_gap_points=100.0,
    )
    return StrategyConfig(
        rr=4.0,
        tp1_ratio=0.55,
        atr_length=atr_length,
        sessions=(session,),
        instrument=instrument,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
        name=label,
    )


CONFIGS = [
    make_config("09:45", "09:45", "13:00", 14, "Old: 15m ORB + 13:00 + ATR14"),
    make_config("09:35", "09:35", "11:30", 10, "New: 5m ORB + 11:30 + ATR10"),
    make_config("09:35", "09:35", "13:00", 10, "New: 5m ORB + 13:00 + ATR10"),
]


def main():
    print("Loading YM data...")
    df = load_5m_data("YM_5m.csv")
    print(f"  {len(df):,} bars")
    print()

    start_date = "2024-01-01"

    print("=" * 110)
    print(f"YM NY — PAST 2 YEARS ({start_date} to present)")
    print("=" * 110)
    print()

    results = []
    for cfg in CONFIGS:
        trades = run_backtest(df, cfg, start_date=start_date)
        m = compute_metrics(trades)
        filled = [t for t in trades if t.exit_type != 0]
        risk_usd = cfg.risk_usd
        total_r = m["total_pnl_usd"] / risk_usd
        dd_r = abs(m["max_drawdown_usd"]) / risk_usd

        results.append({
            "name": cfg.name,
            "trades": m["total_trades"],
            "win_rate": m["win_rate"],
            "total_r": total_r,
            "sharpe": m["sharpe_ratio"],
            "sortino": m["sortino_ratio"],
            "calmar": m["calmar_ratio"],
            "pf": m["profit_factor"],
            "dd_r": dd_r,
            "avg_r": m["avg_r"],
            "metrics": m,
            "filled": filled,
        })

    # Summary table
    print(
        f"  {'Config':<35s} | {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} | "
        f"{'PnL(R)':>8} {'DD(R)':>6} {'PF':>5} {'WR':>6} {'Trd':>5} {'AvgR':>6}"
    )
    print("  " + "-" * 105)
    for r in results:
        print(
            f"  {r['name']:<35s} | {r['sharpe']:7.3f} {r['sortino']:8.3f} {r['calmar']:7.2f} | "
            f"{r['total_r']:>7.1f}R {r['dd_r']:6.1f} {r['pf']:5.2f} {r['win_rate']:5.1f}% {r['trades']:5d} {r['avg_r']:6.3f}"
        )

    # Exit type breakdown
    print()
    print("  Exit Type Breakdown:")
    print(f"  {'Config':<35s} | {'SL':>5} {'TP1+TP2':>7} {'TP1+BE':>7} {'TP1+EOD':>7} {'EOD':>5} {'NoFill':>6}")
    print("  " + "-" * 80)
    for r in results:
        m = r["metrics"]
        exits = m.get("exit_type_breakdown", {})
        print(
            f"  {r['name']:<35s} | "
            f"{exits.get('stop_loss', 0):>5} "
            f"{exits.get('tp1_tp2', 0):>7} "
            f"{exits.get('tp1_be', 0):>7} "
            f"{exits.get('tp1_eod', 0):>7} "
            f"{exits.get('eod', 0):>5} "
            f"{exits.get('no_fill', 0):>6}"
        )

    # Monthly R breakdown for the past 2 years
    print()
    print("  Monthly R:")
    from collections import defaultdict
    for r in results:
        monthly = defaultdict(float)
        for t in r["filled"]:
            month_key = t.date[:7]  # YYYY-MM
            monthly[month_key] += t.r_multiple

        months = sorted(monthly.keys())
        print(f"\n  {r['name']}:")
        # Print in rows of 6
        for i in range(0, len(months), 6):
            chunk = months[i:i+6]
            header = "    " + " ".join(f"{m:>8s}" for m in chunk)
            values = "    " + " ".join(f"{monthly[m]:>8.1f}" for m in chunk)
            print(header)
            print(values)

    print()
    print("Done!")


if __name__ == "__main__":
    main()
