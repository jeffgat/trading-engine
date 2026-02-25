#!/usr/bin/env python3
"""Sweep qualifying_move_atr_pct on GC NY Inversion Longs v9 config.

Tests whether different ORB sweep thresholds (as % of ATR) affect quality.
v9 baseline uses 10%. GC longs require price to sweep BELOW orb_low by X% ATR
before accepting an inversion signal.
"""

import sys
import time
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

SWEEP = {
    "ny_qualifying_move_atr_pct": [0.0, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0],
    "ny_stop_atr_pct": [7.0, 9.0, 11.0, 13.0],
}


def make_config(qm_pct: float, stop_pct: float) -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=stop_pct,
        min_gap_atr_pct=1.0,
        max_gap_points=25.0,
        qualifying_move_atr_pct=qm_pct,
    )
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(session,),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def main():
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    qm_values = SWEEP["ny_qualifying_move_atr_pct"]
    stop_values = SWEEP["ny_stop_atr_pct"]
    combos = list(product(qm_values, stop_values))
    print(f"Sweep: {len(combos)} combos — QM% x Stop ATR%\n")

    results = []
    t0 = time.time()

    for qm, stop in combos:
        cfg = make_config(qm, stop)
        trades = run_backtest_qm(df, cfg, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

        if len(filled) < 10:
            results.append({
                "ny_qualifying_move_atr_pct": qm,
                "ny_stop_atr_pct": stop,
                "trades": len(filled),
                "wr": 0, "net_r": 0, "max_dd_r": 0,
                "sharpe": 0, "pf": 0, "calmar": 0,
                "max_consec_l": 0, "r_per_dd": 0,
            })
            continue

        m = compute_metrics(filled)
        dd = round(m["max_drawdown_r"], 1)
        nr = round(m["total_r"], 1)
        results.append({
            "ny_qualifying_move_atr_pct": qm,
            "ny_stop_atr_pct": stop,
            "trades": m["total_trades"],
            "wr": m["win_rate"],
            "net_r": nr,
            "max_dd_r": dd,
            "sharpe": round(m["sharpe_ratio"], 3),
            "pf": round(m["profit_factor"], 2),
            "calmar": round(m["calmar_ratio"], 2),
            "max_consec_l": m["max_consecutive_losses"],
            "r_per_dd": round(nr / abs(dd), 1) if dd < 0 else 999,
        })

    print(f"Completed {len(results)} results in {time.time() - t0:.0f}s\n")

    # ---- Table 1: Full grid ----
    print("=" * 135)
    print("QM ATR% SWEEP — GC NY Inversion Longs (rr=3.5, tp1=0.2, atr50, be10, min_gap=1.0)")
    print("=" * 135)
    hdr = (f"{'QM%':>5} | {'Stop%':>5} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | "
           f"{'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'MCL':>4}")
    print(hdr)
    print("-" * 135)

    results.sort(key=lambda r: (r["ny_qualifying_move_atr_pct"], r["ny_stop_atr_pct"]))
    for r in results:
        marker = " *** v9" if r["ny_qualifying_move_atr_pct"] == 10.0 else ""
        print(
            f"{r['ny_qualifying_move_atr_pct']:>5.0f} | {r['ny_stop_atr_pct']:>5.1f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['r_per_dd']:>5.1f} | {r['sharpe']:>7.3f} | {r['pf']:>5.2f} | "
            f"{r['calmar']:>7.2f} | {r['max_consec_l']:>4}{marker}"
        )

    # ---- Table 2: Best QM% per stop level ----
    print(f"\n{'=' * 100}")
    print("BEST QM% PER STOP LEVEL (by R/DD ratio)")
    print(f"{'=' * 100}")
    for stop in sorted(set(r["ny_stop_atr_pct"] for r in results)):
        subset = [r for r in results if r["ny_stop_atr_pct"] == stop and r["net_r"] > 0]
        if not subset:
            continue
        best = max(subset, key=lambda r: r["r_per_dd"])
        baseline = next((r for r in results if r["ny_stop_atr_pct"] == stop
                         and r["ny_qualifying_move_atr_pct"] == 0), None)
        v9 = next((r for r in results if r["ny_stop_atr_pct"] == stop
                   and r["ny_qualifying_move_atr_pct"] == 10.0), None)
        d_t = best["trades"] - (baseline["trades"] if baseline else 0)
        d_r = best["net_r"] - (baseline["net_r"] if baseline else 0)
        d_dd = best["max_dd_r"] - (baseline["max_dd_r"] if baseline else 0)
        v9_note = f"  (v9 QM=10: {v9['net_r']:.1f}R, DD={v9['max_dd_r']:.1f})" if v9 else ""
        print(f"  Stop {stop:>5.1f}%: Best QM={best['ny_qualifying_move_atr_pct']:.0f}%  "
              f"({d_t:+d} trades, {d_r:+.1f}R, {d_dd:+.1f}R DD vs no-gate){v9_note}")

    # ---- Table 3: Averaged across stop levels ----
    print(f"\n{'=' * 90}")
    print("AVERAGED ACROSS STOP LEVELS")
    print(f"{'=' * 90}")
    print(f"{'QM%':>5} | {'Avg Trades':>10} | {'Avg Net R':>9} | {'Avg DD':>7} | {'Avg R/DD':>8} | {'Avg Sharpe':>10}")
    print("-" * 70)

    for qm in sorted(set(r["ny_qualifying_move_atr_pct"] for r in results)):
        subset = [r for r in results if r["ny_qualifying_move_atr_pct"] == qm]
        avg_trades = sum(r["trades"] for r in subset) / len(subset)
        avg_nr = sum(r["net_r"] for r in subset) / len(subset)
        avg_dd = sum(r["max_dd_r"] for r in subset) / len(subset)
        avg_rdd = sum(r["r_per_dd"] for r in subset) / len(subset)
        avg_sh = sum(r["sharpe"] for r in subset) / len(subset)
        marker = " ← v9 (current)" if qm == 10.0 else (" ← no gate" if qm == 0 else "")
        print(f"{qm:>5.0f} | {avg_trades:>10.0f} | {avg_nr:>9.1f} | {avg_dd:>7.1f} | "
              f"{avg_rdd:>8.1f} | {avg_sh:>10.3f}{marker}")


if __name__ == "__main__":
    main()
