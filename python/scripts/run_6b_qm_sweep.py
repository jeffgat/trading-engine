#!/usr/bin/env python3
"""Sweep qualifying_move_atr_pct on 6B LDN Inversion Shorts GO config.

Tests whether requiring a minimum ORB sweep distance (as % of ATR) before
accepting an inversion signal improves results. GC sweet spot was 10%.
"""

import sys
import time
from dataclasses import replace
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, with_overrides, LDN_SESSION
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# Bake LDN defaults directly into the session to avoid with_overrides collision
LDN_ORB30 = replace(LDN_SESSION, orb_end="03:30", entry_start="03:30", min_gap_atr_pct=1.0)

# Winning config (fixed) — no ldn-prefixed params here
FIXED = {
    "rr": 4.0,
    "tp1_ratio": 0.10,
    "atr_length": 50,
}

SWEEP = {
    "ldn_qualifying_move_atr_pct": [0.0, 5.0, 10.0, 15.0, 20.0, 25.0],
    "ldn_stop_atr_pct": [8.0, 10.0, 12.0, 14.0],
}


def main():
    instrument = get_instrument("6B")
    df = load_5m_data("6B_5m.csv")
    df_1m = load_1m_for_5m("6B_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    param_names = list(SWEEP.keys())
    param_values = list(SWEEP.values())
    combos = list(product(*param_values))
    print(f"Sweep: {len(combos)} combos — QM% x Stop ATR%\n")

    results = []
    t0 = time.time()

    for ci, combo in enumerate(combos):
        params = dict(zip(param_names, combo))
        sess_params = {k: v for k, v in params.items() if k.startswith("ldn_")}

        base = default_config(instrument)
        base = with_overrides(base, sessions=(LDN_ORB30,),
            strategy="inversion", use_bar_magnifier=True,
            direction_filter="short", **FIXED)
        base = with_overrides(base, **sess_params)

        trades = run_backtest_qm(df, base, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 10:
            results.append({
                **params,
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
            **params,
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

    print(f"\nCompleted {len(results)} results in {time.time() - t0:.0f}s\n")

    # ---- Table 1: QM% impact at each stop level ----
    print("=" * 130)
    print("QUALIFYING MOVE ATR% SWEEP — 6B LDN Inversion Shorts (tp1=0.10, be=25, rr=4.0)")
    print("=" * 130)

    hdr = (f"{'QM%':>5} | {'Stop%':>5} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | "
           f"{'Max DD':>7} | {'R/DD':>5} | {'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'MCL':>4}")
    print(hdr)
    print("-" * 130)

    # Sort by QM% then stop
    results.sort(key=lambda r: (r["ldn_qualifying_move_atr_pct"], r["ldn_stop_atr_pct"]))
    for r in results:
        marker = " ***" if r["ldn_qualifying_move_atr_pct"] == 0 else ""
        print(
            f"{r['ldn_qualifying_move_atr_pct']:>5.0f} | {r['ldn_stop_atr_pct']:>5.1f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['r_per_dd']:>5.1f} | {r['sharpe']:>7.3f} | {r['pf']:>5.2f} | "
            f"{r['calmar']:>7.2f} | {r['max_consec_l']:>4}{marker}"
        )

    # ---- Table 2: Best QM% per stop level ----
    print(f"\n{'=' * 90}")
    print("BEST QM% PER STOP LEVEL (by R/DD ratio)")
    print(f"{'=' * 90}")

    for stop in sorted(set(r["ldn_stop_atr_pct"] for r in results)):
        subset = [r for r in results if r["ldn_stop_atr_pct"] == stop and r["net_r"] > 0]
        if not subset:
            continue
        best = max(subset, key=lambda r: r["r_per_dd"])
        baseline = next((r for r in results if r["ldn_stop_atr_pct"] == stop
                         and r["ldn_qualifying_move_atr_pct"] == 0), None)
        if baseline:
            delta_trades = best["trades"] - baseline["trades"]
            delta_r = best["net_r"] - baseline["net_r"]
            delta_dd = best["max_dd_r"] - baseline["max_dd_r"]
            print(f"  Stop {stop:>5.1f}%: Best QM={best['ldn_qualifying_move_atr_pct']:.0f}%  "
                  f"({delta_trades:+d} trades, {delta_r:+.1f}R, {delta_dd:+.1f}R DD)")

    # ---- Table 3: Aggregated by QM% (averaged across stops) ----
    print(f"\n{'=' * 90}")
    print("AVERAGED ACROSS STOP LEVELS")
    print(f"{'=' * 90}")
    print(f"{'QM%':>5} | {'Avg Trades':>10} | {'Avg Net R':>9} | {'Avg DD':>7} | {'Avg R/DD':>8} | {'Avg Sharpe':>10}")
    print("-" * 70)

    for qm in sorted(set(r["ldn_qualifying_move_atr_pct"] for r in results)):
        subset = [r for r in results if r["ldn_qualifying_move_atr_pct"] == qm]
        avg_trades = sum(r["trades"] for r in subset) / len(subset)
        avg_nr = sum(r["net_r"] for r in subset) / len(subset)
        avg_dd = sum(r["max_dd_r"] for r in subset) / len(subset)
        avg_rdd = sum(r["r_per_dd"] for r in subset) / len(subset)
        avg_sh = sum(r["sharpe"] for r in subset) / len(subset)
        marker = " ← baseline" if qm == 0 else ""
        print(f"{qm:>5.0f} | {avg_trades:>10.0f} | {avg_nr:>9.1f} | {avg_dd:>7.1f} | "
              f"{avg_rdd:>8.1f} | {avg_sh:>10.3f}{marker}")


if __name__ == "__main__":
    main()
