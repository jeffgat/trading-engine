#!/usr/bin/env python3
"""Sweep GC NY no-ORB liquidity sweep inversions.

Tests inversion entries where price makes a significant sweep in ANY direction
during the session (not anchored to an ORB range), then reverses through an FVG.

Qualifying sweep measured from session's running opposite extreme:
- LONG: session low must be >= X% ATR below session high (price fell enough)
- SHORT: session high must be >= X% ATR above session low (price rose enough)
"""

import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_no_orb
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

SWEEP = {
    "qm": [20.0, 30.0, 40.0, 50.0, 60.0, 75.0, 100.0, 125.0, 150.0],
    "stop": [9.0, 11.0, 13.0, 15.0],
    "direction": ["long"],
}

FIXED_rr = 3.5
FIXED_tp1 = 0.2
FIXED_atr = 50
FIXED_be = 10
FIXED_min_gap = 1.0
FIXED_max_gap = 25.0


def make_config(qm, stop, direction):
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=FIXED_min_gap,
        max_gap_points=FIXED_max_gap,
        qualifying_move_atr_pct=qm,
    )
    return StrategyConfig(
        rr=FIXED_rr, tp1_ratio=FIXED_tp1, risk_usd=5000.0,
        atr_length=FIXED_atr,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter=direction,
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def main():
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    combos = list(product(SWEEP["qm"], SWEEP["stop"], SWEEP["direction"]))
    print(f"Sweep: {len(combos)} combos — QM% x Stop% x Direction\n")

    results = []
    t0 = time.time()

    for qm, stop, direction in combos:
        cfg = make_config(qm, stop, direction)
        trades = run_backtest_no_orb(df, cfg, start_date="2016-01-01", df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

        if len(filled) < 20:
            results.append({"qm": qm, "stop": stop, "dir": direction,
                             "trades": len(filled), "wr": 0, "net_r": 0,
                             "max_dd_r": 0, "sharpe": 0, "pf": 0, "r_per_dd": 0})
            continue

        m = compute_metrics(filled)
        dd = round(m["max_drawdown_r"], 1)
        nr = round(m["total_r"], 1)
        results.append({
            "qm": qm, "stop": stop, "dir": direction,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "net_r": nr, "max_dd_r": dd,
            "sharpe": round(m["sharpe_ratio"], 3),
            "pf": round(m["profit_factor"], 2),
            "r_per_dd": round(nr / abs(dd), 1) if dd < 0 else 999,
        })

    print(f"Completed in {time.time() - t0:.0f}s\n")

    viable = [r for r in results if r["net_r"] > 0 and r["pf"] >= 1.0 and r["trades"] >= 20]
    viable.sort(key=lambda r: r["sharpe"], reverse=True)

    print("=" * 110)
    print("NO-ORB LIQUIDITY SWEEP INVERSIONS — GC NY (rr=3.5, tp1=0.2, atr50, be10)")
    print(f"Profitable: {len(viable)} of {len(results)} configs")
    print("=" * 110)
    hdr = (f"{'QM%':>5} | {'Stop%':>5} | {'Dir':>5} | {'Trades':>6} | {'WR':>6} | "
           f"{'Net R':>7} | {'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5}")
    print(hdr)
    print("-" * 110)
    for r in viable[:40]:
        print(f"{r['qm']:>5.0f} | {r['stop']:>5.1f} | {r['dir']:>5} | {r['trades']:>6} | "
              f"{r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
              f"{r['r_per_dd']:>5.1f} | {r['sharpe']:>7.3f} | {r['pf']:>5.2f}")

    print(f"\n{'=' * 70}")
    print("BY DIRECTION (profitable configs)")
    print(f"{'=' * 70}")
    for d in ["long", "short", "both"]:
        sub = [r for r in viable if r["dir"] == d]
        if not sub:
            print(f"  {d:>5}: no profitable configs")
            continue
        print(f"  {d:>5}: {len(sub):2d} configs | "
              f"avg {sum(r['trades'] for r in sub)/len(sub):.0f} trades | "
              f"{sum(r['net_r'] for r in sub)/len(sub):.1f}R | "
              f"{sum(r['max_dd_r'] for r in sub)/len(sub):.1f}R DD | "
              f"Sharpe {sum(r['sharpe'] for r in sub)/len(sub):.3f}")

    print(f"\n{'=' * 70}")
    print("BY QM% (profitable configs, all directions)")
    print(f"{'=' * 70}")
    for qm in sorted(set(r["qm"] for r in results)):
        sub = [r for r in viable if r["qm"] == qm]
        if not sub:
            print(f"  QM={qm:>4.0f}%: no profitable configs")
            continue
        print(f"  QM={qm:>4.0f}%: {len(sub):2d} configs | "
              f"avg {sum(r['trades'] for r in sub)/len(sub):.0f} trades | "
              f"{sum(r['net_r'] for r in sub)/len(sub):.1f}R | "
              f"Sharpe {sum(r['sharpe'] for r in sub)/len(sub):.3f}")

    # Prop-viable candidates (DD within 10R)
    prop_viable = [r for r in viable if r["max_dd_r"] >= -10.0]
    print(f"\n{'=' * 70}")
    print("PROP-VIABLE (DD <= 10R)")
    print(f"{'=' * 70}")
    if prop_viable:
        prop_viable.sort(key=lambda r: r["sharpe"], reverse=True)
        print(hdr)
        print("-" * 110)
        for r in prop_viable:
            print(f"{r['qm']:>5.0f} | {r['stop']:>5.1f} | {r['dir']:>5} | {r['trades']:>6} | "
                  f"{r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
                  f"{r['r_per_dd']:>5.1f} | {r['sharpe']:>7.3f} | {r['pf']:>5.2f}")
    else:
        print("  None found.")

    print(f"\nv9 baseline (ORB-anchored, long only): 250 trades, 74.7R, -5.2R DD, Sharpe 3.80")
    if viable:
        b = viable[0]
        print(f"Best no-ORB: QM={b['qm']:.0f}% stop={b['stop']:.0f}% dir={b['dir']} | "
              f"{b['trades']} trades, {b['net_r']}R, {b['max_dd_r']}R DD, Sharpe {b['sharpe']:.3f}")


if __name__ == "__main__":
    main()
