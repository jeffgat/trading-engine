#!/usr/bin/env python3
"""Structural sweep for 6B LDN Inversion ORB30 — DD reduction variables."""

import sys
import time
from dataclasses import replace
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, with_overrides, LDN_SESSION
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

LDN_ORB30 = replace(LDN_SESSION, orb_end="03:30", entry_start="03:30")

SWEEP = {
    "tp1_ratio": [0.15, 0.25, 0.35, 0.50],
    "atr_length": [30, 50],
    "ldn_max_gap_atr_pct": [0, 10, 20],
}

DIRECTIONS = ["both", "long", "short"]
FIXED_RR = 4.0
FIXED_STOP = 15.0


def main():
    instrument = get_instrument("6B")
    df = load_5m_data("6B_5m.csv")
    df_1m = load_1m_for_5m("6B_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    param_names = list(SWEEP.keys())
    param_values = list(SWEEP.values())
    combos = list(product(*param_values))
    total = len(combos) * len(DIRECTIONS)
    print(f"Sweep: {len(combos)} param combos x {len(DIRECTIONS)} directions = {total} runs\n")

    results = []
    t0 = time.time()

    for di, direction in enumerate(DIRECTIONS):
        for ci, combo in enumerate(combos):
            params = dict(zip(param_names, combo))
            run_num = di * len(combos) + ci + 1

            base = default_config(instrument)
            # Apply sessions first, then session-prefixed overrides separately
            base = with_overrides(base, sessions=(LDN_ORB30,),
                strategy="inversion", use_bar_magnifier=True,
                rr=FIXED_RR, direction_filter=direction)
            # Now apply session-prefixed and remaining params
            base = with_overrides(base,
                ldn_stop_atr_pct=FIXED_STOP, **params)

            trades = run_backtest(df, base, df_1m=df_1m)
            filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

            if len(filled) < 10:
                continue

            m = compute_metrics(filled)
            results.append({
                "direction": direction,
                **params,
                "trades": m["total_trades"],
                "wr": m["win_rate"],
                "net_r": round(m["total_r"], 1),
                "max_dd_r": round(m["max_drawdown_r"], 1),
                "sharpe": round(m["sharpe_ratio"], 3),
                "pf": round(m["profit_factor"], 2),
                "calmar": round(m["calmar_ratio"], 2),
                "max_consec_l": m["max_consecutive_losses"],
            })

            if run_num % 24 == 0 or run_num == total:
                elapsed = time.time() - t0
                print(f"  {run_num}/{total} [{elapsed:.0f}s]")

    elapsed = time.time() - t0
    print(f"\nCompleted {len(results)} results in {elapsed:.0f}s\n")

    # Sort by max_dd_r (least negative = best DD)
    results.sort(key=lambda r: r["max_dd_r"], reverse=True)

    # Print top 30 by DD
    print("=" * 140)
    print("TOP 30 BY MAX DD (least drawdown)")
    print("=" * 140)
    hdr = f"{'Dir':>5} | {'tp1':>5} | {'atr_l':>5} | {'gap%':>5} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Max DD':>7} | {'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'MCL':>4}"
    print(hdr)
    print("-" * 140)
    for r in results[:30]:
        print(
            f"{r['direction']:>5} | {r['tp1_ratio']:>5.2f} | "
            f"{r['atr_length']:>5} | {r['ldn_max_gap_atr_pct']:>5} | {r['trades']:>6} | "
            f"{r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | {r['max_consec_l']:>4}"
        )

    # Also sort by Calmar (risk-adjusted)
    results.sort(key=lambda r: r["calmar"], reverse=True)
    print()
    print("=" * 140)
    print("TOP 30 BY CALMAR (risk-adjusted return)")
    print("=" * 140)
    print(hdr)
    print("-" * 140)
    for r in results[:30]:
        print(
            f"{r['direction']:>5} | {r['tp1_ratio']:>5.2f} | "
            f"{r['atr_length']:>5} | {r['ldn_max_gap_atr_pct']:>5} | {r['trades']:>6} | "
            f"{r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | {r['max_consec_l']:>4}"
        )

    # Filter to DD better than -25R and print
    viable = [r for r in results if r["max_dd_r"] > -25 and r["net_r"] > 0]
    viable.sort(key=lambda r: r["calmar"], reverse=True)
    print(f"\n{'='*140}")
    print(f"VIABLE CANDIDATES (DD > -25R, Net R > 0): {len(viable)} of {len(results)}")
    print(f"{'='*140}")
    print(hdr)
    print("-" * 140)
    for r in viable[:20]:
        print(
            f"{r['direction']:>5} | {r['tp1_ratio']:>5.2f} | "
            f"{r['atr_length']:>5} | {r['ldn_max_gap_atr_pct']:>5} | {r['trades']:>6} | "
            f"{r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | {r['max_consec_l']:>4}"
        )


if __name__ == "__main__":
    main()
