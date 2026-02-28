#!/usr/bin/env python3
"""Aggressive DD-reduction sweep for YM NY 5m ORB + 13:00 + ATR10.

Pushes harder: tighter stops, more selective gaps, smaller max gap, higher RR.
"""

import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics


def make_config(stop_atr_pct, min_gap_atr_pct, max_gap_points, rr):
    instrument = get_instrument("YM")
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
    )
    return StrategyConfig(
        rr=rr,
        tp1_ratio=0.55,
        atr_length=10,
        sessions=(session,),
        instrument=instrument,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def main():
    print("Loading YM data...")
    t0 = time.time()
    df = load_5m_data("YM_5m.csv")
    print(f"  {len(df):,} bars [{time.time()-t0:.1f}s]")

    stop_values = [2.5, 2.75, 3.0, 3.25, 3.5]
    gap_values = [1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
    maxgap_values = [25.0, 35.0, 50.0]
    rr_values = [4.0, 4.5]

    combos = list(product(stop_values, gap_values, maxgap_values, rr_values))
    print(f"  {len(combos)} combinations")
    print()

    results = []
    for i, (stop, gap, maxgap, rr) in enumerate(combos):
        cfg = make_config(stop, gap, maxgap, rr)
        trades = run_backtest(df, cfg, start_date="2016-03-01")
        m = compute_metrics(trades)
        risk_usd = cfg.risk_usd
        total_r = m["total_pnl_usd"] / risk_usd
        dd_r = abs(m["max_drawdown_usd"]) / risk_usd

        results.append({
            "stop": stop,
            "gap": gap,
            "maxgap": maxgap,
            "rr": rr,
            "trades": m["total_trades"],
            "win_rate": m["win_rate"],
            "total_r": total_r,
            "sharpe": m["sharpe_ratio"],
            "sortino": m["sortino_ratio"],
            "calmar": m["calmar_ratio"],
            "pf": m["profit_factor"],
            "dd_r": dd_r,
            "avg_r": m["avg_r"],
        })

        if (i + 1) % 36 == 0 or i == len(combos) - 1:
            print(f"  {i+1}/{len(combos)} done [{time.time()-t0:.0f}s]")

    # Best by DD with minimum quality
    viable = [r for r in results if r["sharpe"] >= 1.5 and r["trades"] >= 500 and r["pf"] >= 1.2]
    viable.sort(key=lambda r: r["dd_r"])

    print()
    print("=" * 130)
    print(f"TOP 25 BY LOWEST DD (Sharpe >= 1.5, PF >= 1.2, Trades >= 500) — {len(viable)} viable")
    print("=" * 130)
    print(
        f"  {'Stop':>5} {'Gap':>5} {'MaxGap':>6} {'RR':>4} | {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} | "
        f"{'PnL(R)':>8} {'DD(R)':>6} {'PF':>5} {'WR':>6} {'Trd':>5} {'AvgR':>6}"
    )
    print("  " + "-" * 115)
    for r in viable[:25]:
        print(
            f"  {r['stop']:>5.2f} {r['gap']:>5.2f} {r['maxgap']:>6.0f} {r['rr']:>4.1f} | "
            f"{r['sharpe']:7.3f} {r['sortino']:8.3f} {r['calmar']:7.2f} | "
            f"{r['total_r']:>7.1f}R {r['dd_r']:6.1f} {r['pf']:5.2f} {r['win_rate']:5.1f}% {r['trades']:5d} {r['avg_r']:6.3f}"
        )

    # Also show best Calmar (DD-adjusted returns)
    calmar_viable = [r for r in results if r["trades"] >= 500 and r["pf"] >= 1.2 and r["sharpe"] >= 1.5]
    calmar_viable.sort(key=lambda r: -r["calmar"])

    print()
    print("=" * 130)
    print(f"TOP 15 BY CALMAR (best return per unit DD)")
    print("=" * 130)
    print(
        f"  {'Stop':>5} {'Gap':>5} {'MaxGap':>6} {'RR':>4} | {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} | "
        f"{'PnL(R)':>8} {'DD(R)':>6} {'PF':>5} {'WR':>6} {'Trd':>5} {'AvgR':>6}"
    )
    print("  " + "-" * 115)
    for r in calmar_viable[:15]:
        print(
            f"  {r['stop']:>5.2f} {r['gap']:>5.2f} {r['maxgap']:>6.0f} {r['rr']:>4.1f} | "
            f"{r['sharpe']:7.3f} {r['sortino']:8.3f} {r['calmar']:7.2f} | "
            f"{r['total_r']:>7.1f}R {r['dd_r']:6.1f} {r['pf']:5.2f} {r['win_rate']:5.1f}% {r['trades']:5d} {r['avg_r']:6.3f}"
        )

    print("\nDone!")


if __name__ == "__main__":
    main()
