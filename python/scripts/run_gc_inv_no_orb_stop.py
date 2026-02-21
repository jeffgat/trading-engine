#!/usr/bin/env python3
"""No-ORB GC — sweep stop ATR%.

Fixes QM=100%, entry_end=20:00, rr=3.5, longs only.
Tests stop_atr_pct: 9, 10, 11, 12, 13, 14, 15, 16, 17%
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

QM        = 100.0
RR        = 3.5
TP1       = 0.2
ATR_LEN   = 50
BE        = 10
MIN_GAP   = 1.0
MAX_GAP   = 25.0
STOP_VALS = [9.0, 10.0, 11.0, 12.0, 13.0, 14.0, 15.0, 16.0, 17.0]


def make_config(stop):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="20:00",
        flat_start="20:00", flat_end="20:05",
        stop_atr_pct=stop, min_gap_atr_pct=MIN_GAP,
        max_gap_points=MAX_GAP, qualifying_move_atr_pct=QM,
    )
    return StrategyConfig(
        rr=RR, tp1_ratio=TP1, risk_usd=5000.0,
        atr_length=ATR_LEN,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def main():
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    results = []
    t0 = time.time()

    for stop in STOP_VALS:
        cfg = make_config(stop)
        trades = run_backtest_no_orb(df, cfg, start_date="2016-01-01", df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

        if len(filled) < 10:
            results.append({"stop": stop, "trades": len(filled),
                             "wr": 0, "net_r": 0, "max_dd": 0, "sharpe": 0, "pf": 0})
            continue

        m = compute_metrics(filled)
        dd = round(m["max_drawdown_r"], 1)
        nr = round(m["total_r"], 1)

        yearly = defaultdict(list)
        for t in filled:
            yearly[t.date[:4]].append(t.r_multiple)
        monthly = defaultdict(list)
        for t in filled:
            monthly[t.date[:7]].append(t.r_multiple)
        worst_month = min((sum(v) for v in monthly.values()), default=0)

        results.append({
            "stop": stop,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "net_r": nr, "max_dd": dd,
            "sharpe": round(m["sharpe_ratio"], 3),
            "pf": round(m["profit_factor"], 2),
            "r_per_dd": round(nr / abs(dd), 1) if dd < 0 else 999,
            "worst_month": round(worst_month, 1),
            "mcl": m["max_consecutive_losses"],
            "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        })
        print(f"  stop={stop:.0f}%: {m['total_trades']} trades, "
              f"{nr}R, {dd}R DD, Sharpe {m['sharpe_ratio']:.3f}")

    print(f"\nDone in {time.time()-t0:.0f}s\n")

    print("=" * 100)
    print("NO-ORB GC — STOP ATR% SWEEP (QM=100%, entry_end=20:00, rr=3.5, longs)")
    print("=" * 100)
    hdr = (f"{'Stop%':>6} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | "
           f"{'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5} | "
           f"{'WorstMo':>7} | {'MCL':>4}")
    print(hdr)
    print("-" * 100)
    for r in results:
        marker = " ***" if r.get("max_dd", 0) >= -10.0 and r.get("net_r", 0) > 0 else ""
        print(f"{r['stop']:>6.0f} | {r['trades']:>6} | {r.get('wr', 0):>5.1%} | "
              f"{r.get('net_r', 0):>7.1f} | {r.get('max_dd', 0):>7.1f} | "
              f"{r.get('r_per_dd', 0):>5.1f} | {r.get('sharpe', 0):>7.3f} | "
              f"{r.get('pf', 0):>5.2f} | {r.get('worst_month', 0):>7.1f} | "
              f"{r.get('mcl', 0):>4}{marker}")

    best = max(results, key=lambda r: r.get("sharpe", 0))
    print(f"\nBest stop: {best['stop']:.0f}% — {best['trades']} trades, "
          f"{best['net_r']}R, {best['max_dd']}R DD, Sharpe {best['sharpe']:.3f}")


if __name__ == "__main__":
    main()
