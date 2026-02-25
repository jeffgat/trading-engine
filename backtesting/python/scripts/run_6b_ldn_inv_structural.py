#!/usr/bin/env python3
"""6B LDN Inversion — Structural exploration by direction.

Tests inversion on LDN session with 1s magnifier.
Sweeps: direction (long/short/both) x ORB (15m/30m) x rr x stop x tp1 x atr.
"""

import sys
import time
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

SIX_B = get_instrument("6B")

LDN_ORB15 = LDN_SESSION
LDN_ORB30 = replace(LDN_SESSION, orb_end="03:30", entry_start="03:30")

START = "2016-01-01"

CONFIGS = []

for direction in ["both", "long", "short"]:
    for orb_label, session in [("ORB15", LDN_ORB15), ("ORB30", LDN_ORB30)]:
        for rr in [2.0, 3.0, 4.0]:
            for stop in [5.0, 10.0, 15.0]:
                for tp1 in [0.10, 0.30, 0.50]:
                    for atr in [14, 50]:
                        cfg = StrategyConfig(
                            rr=rr,
                            tp1_ratio=tp1,
                            risk_usd=5000.0,
                            atr_length=atr,
                            min_qty=1.0,
                            qty_step=1.0,
                            sessions=(session,),
                            instrument=SIX_B,
                            strategy="inversion",
                            direction_filter=direction,
                            use_bar_magnifier=True,
                            half_days=(),
                            excluded_dates=(),
                        )
                        label = f"{direction:>5s} {orb_label} rr={rr} stop={stop:>4.0f}% tp1={tp1:.2f} atr={atr}"
                        CONFIGS.append((label, cfg, {"ldn_stop_atr_pct": stop}))


def main():
    print("6B LDN Inversion — Structural Exploration")
    print(f"  Strategy: inversion | Directions: both, long, short | Magnifier: 1s")
    print(f"  Configs: {len(CONFIGS)}")
    print()

    print("Loading data...")
    t0 = time.time()
    df    = load_5m_data("6B_5m.csv")
    df_1m = load_1m_for_5m("6B_5m.csv")
    df_1s = load_1s_for_5m("6B_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} bars [{time.time()-t0:.1f}s]")
    print()

    all_results = []

    for direction in ["both", "long", "short"]:
        subset = [(l, c, o) for l, c, o in CONFIGS if l.startswith(f"{direction:>5s}")]
        results = []

        print(f"\n{'='*90}")
        print(f"  DIRECTION: {direction.upper()}")
        print(f"{'='*90}")
        header = (f"{'Config':<50s} {'Trades':>6s} {'WR':>6s} {'Net R':>8s} "
                  f"{'PF':>6s} {'Sharpe':>7s} {'Calmar':>7s} {'Max DD':>7s}")
        print(header)
        print("-" * len(header))

        for label, cfg, overrides in subset:
            cfg = with_overrides(cfg, **overrides)
            trades = run_backtest(df, cfg, start_date=START, df_1m=df_1m, df_1s=df_1s)
            m = compute_metrics(trades)
            results.append((label, m, trades))
            all_results.append((label, m, trades))
            print(f"{label:<50s} {m['total_trades']:>6d} {m['win_rate']:>5.1%} {m['total_r']:>8.1f} "
                  f"{m['profit_factor']:>6.2f} {m['sharpe_ratio']:>7.3f} {m['calmar_ratio']:>7.2f} {m['max_drawdown_r']:>7.1f}")

        print()
        print(f"  TOP 5 {direction.upper()} BY CALMAR:")
        ranked = sorted(results, key=lambda x: x[1]["calmar_ratio"], reverse=True)
        for label, m, _ in ranked[:5]:
            print(f"    {label:<50s}  Calmar={m['calmar_ratio']:.2f}  Net R={m['total_r']:.1f}  "
                  f"PF={m['profit_factor']:.2f}  Trades={m['total_trades']}  DD={m['max_drawdown_r']:.1f}")

        profitable = sum(1 for _, m, _ in results if m["total_r"] > 0)
        print(f"\n  Profitable {direction}: {profitable}/{len(results)}")

    # Global top 10
    print(f"\n\n{'='*90}")
    print(f"  GLOBAL TOP 10 BY CALMAR (all directions)")
    print(f"{'='*90}")
    ranked_all = sorted(all_results, key=lambda x: x[1]["calmar_ratio"], reverse=True)
    for i, (label, m, trades) in enumerate(ranked_all[:10]):
        # R by year
        rby = defaultdict(float)
        for t in trades:
            if t.exit_type != EXIT_NO_FILL:
                rby[t.date[:4]] += t.r_multiple
        neg_years = sum(1 for y, r in rby.items() if r < 0 and len(y) == 4)
        print(f"  {i+1:>2d}. {label:<50s}  Calmar={m['calmar_ratio']:.2f}  Net R={m['total_r']:.1f}  "
              f"PF={m['profit_factor']:.2f}  Trades={m['total_trades']}  DD={m['max_drawdown_r']:.1f}  NegYrs={neg_years}")

    # For the top config, print R by year
    if ranked_all:
        best_label, best_m, best_trades = ranked_all[0]
        print(f"\n  Best config R by year ({best_label}):")
        rby = defaultdict(float)
        for t in best_trades:
            if t.exit_type != EXIT_NO_FILL:
                rby[t.date[:4]] += t.r_multiple
        for y in sorted(rby):
            flag = " <--" if rby[y] < 0 else ""
            print(f"    {y}: {rby[y]:>8.1f}R{flag}")

    total_profitable = sum(1 for _, m, _ in all_results if m["total_r"] > 0)
    print(f"\n  Total profitable: {total_profitable}/{len(all_results)}")


if __name__ == "__main__":
    main()
