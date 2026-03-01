#!/usr/bin/env python3
"""Focused sweep for 6B LDN Inversion ORB30 short — tp1/stop."""

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
    "tp1_ratio": [0.10, 0.15, 0.20, 0.25, 0.30],
    "ldn_stop_atr_pct": [8.0, 10.0, 12.0, 15.0],
}

FIXED = {"rr": 4.0, "atr_length": 50}


def main():
    instrument = get_instrument("6B")
    df = load_5m_data("6B_5m.csv")
    df_1m = load_1m_for_5m("6B_5m.csv")
    print(f"Loaded {len(df):,} 5m bars, {len(df_1m):,} 1m bars\n")

    param_names = list(SWEEP.keys())
    param_values = list(SWEEP.values())
    combos = list(product(*param_values))
    print(f"Sweep: {len(combos)} combos (short-only, ORB30, rr={FIXED['rr']}, atr={FIXED['atr_length']})\n")

    results = []
    t0 = time.time()

    for ci, combo in enumerate(combos):
        params = dict(zip(param_names, combo))
        # Separate session-prefixed from direct params
        sess_params = {k: v for k, v in params.items() if k.startswith("ldn_")}
        direct_params = {k: v for k, v in params.items() if not k.startswith("ldn_")}

        base = default_config(instrument)
        base = with_overrides(base, sessions=(LDN_ORB30,),
            strategy="inversion", use_bar_magnifier=True,
            direction_filter="short", **FIXED, **direct_params)
        base = with_overrides(base, **sess_params)

        trades = run_backtest(df, base, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 10:
            continue

        m = compute_metrics(filled)
        results.append({
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

        if (ci + 1) % 20 == 0:
            print(f"  {ci + 1}/{len(combos)} [{time.time() - t0:.0f}s]")

    print(f"\nCompleted {len(results)} results in {time.time() - t0:.0f}s\n")

    # Sort by DD
    results.sort(key=lambda r: r["max_dd_r"], reverse=True)

    hdr = f"{'tp1':>5} | {'stop%':>5} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Max DD':>7} | {'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'MCL':>4}"
    print("=" * 110)
    print("TOP 25 BY MAX DD (least drawdown) — Short-only")
    print("=" * 110)
    print(hdr)
    print("-" * 110)
    for r in results[:25]:
        print(
            f"{r['tp1_ratio']:>5.2f} | {r['ldn_stop_atr_pct']:>5.1f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | {r['max_consec_l']:>4}"
        )

    # Filter viable
    viable = [r for r in results if r["net_r"] > 0 and r["pf"] >= 1.0]
    viable.sort(key=lambda r: r["max_dd_r"], reverse=True)
    print(f"\n{'='*110}")
    print(f"ALL PROFITABLE CONFIGS SORTED BY DD ({len(viable)} of {len(results)})")
    print(f"{'='*110}")
    print(hdr)
    print("-" * 110)
    for r in viable[:40]:
        marker = " ***" if r["max_dd_r"] > -15 else ""
        print(
            f"{r['tp1_ratio']:>5.2f} | {r['ldn_stop_atr_pct']:>5.1f} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>7.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | {r['max_consec_l']:>4}{marker}"
        )


if __name__ == "__main__":
    main()
