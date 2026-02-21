#!/usr/bin/env python3
"""Diagnostic: analyze BE offset mechanics on 6B trades."""

import sys
from collections import Counter
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, with_overrides, LDN_SESSION
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD, EXIT_TP2_SINGLE

LDN_ORB30 = replace(LDN_SESSION, orb_end="03:30", entry_start="03:30")


def main():
    instrument = get_instrument("6B")
    df = load_5m_data("6B_5m.csv")
    df_1m = load_1m_for_5m("6B_5m.csv")

    base = default_config(instrument)
    base = with_overrides(base, sessions=(LDN_ORB30,),
        strategy="inversion", use_bar_magnifier=True,
        direction_filter="short", rr=4.0, atr_length=50)
    base = with_overrides(base, ldn_stop_atr_pct=12.0,
        tp1_ratio=0.10)

    trades = run_backtest(df, base, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    print(f"Total filled trades: {len(filled)}")
    print(f"Point value: ${instrument.point_value:,.0f}")
    print()

    # Exit type breakdown
    exit_names = {EXIT_SL: "SL", EXIT_TP1_TP2: "TP1+TP2", EXIT_TP1_BE: "TP1+BE",
                  EXIT_TP1_EOD: "TP1+EOD", EXIT_EOD: "EOD", EXIT_TP2_SINGLE: "TP2_SINGLE"}
    counts = Counter(t.exit_type for t in filled)
    print("Exit breakdown:")
    for et, name in exit_names.items():
        n = counts.get(et, 0)
        print(f"  {name:>12s}: {n:>5d} ({n/len(filled):.1%})")
    print()

    # Analyze stop distances (risk_pts)
    risk_pts_list = []
    for t in filled:
        risk_pts = abs(t.entry_price - t.stop_price)
        risk_pts_list.append(risk_pts)

    risk_pts_arr = np.array(risk_pts_list)
    risk_pips = risk_pts_arr / 0.0001

    print("Stop distance (risk) distribution:")
    print(f"  Mean:   {risk_pts_arr.mean():.5f} ({risk_pips.mean():.1f} pips)")
    print(f"  Median: {np.median(risk_pts_arr):.5f} ({np.median(risk_pips):.1f} pips)")
    print(f"  Min:    {risk_pts_arr.min():.5f} ({risk_pips.min():.1f} pips)")
    print(f"  Max:    {risk_pts_arr.max():.5f} ({risk_pips.max():.1f} pips)")
    print(f"  p10:    {np.percentile(risk_pts_arr, 10):.5f} ({np.percentile(risk_pips, 10):.1f} pips)")
    print(f"  p25:    {np.percentile(risk_pts_arr, 25):.5f} ({np.percentile(risk_pips, 25):.1f} pips)")
    print(f"  p75:    {np.percentile(risk_pts_arr, 75):.5f} ({np.percentile(risk_pips, 75):.1f} pips)")
    print(f"  p90:    {np.percentile(risk_pts_arr, 90):.5f} ({np.percentile(risk_pips, 90):.1f} pips)")
    print()

    # Analyze TP1+BE exit trades specifically
    be_trades = [t for t in filled if t.exit_type == EXIT_TP1_BE]
    if be_trades:
        be_r_multiples = np.array([t.r_multiple for t in be_trades])
        print(f"TP1+BE exit trades ({len(be_trades)}):")
        print(f"  Mean R-multiple:   {be_r_multiples.mean():.3f}R")
        print(f"  Median R-multiple: {np.median(be_r_multiples):.3f}R")
        print(f"  Min R-multiple:    {be_r_multiples.min():.3f}R")
        print(f"  Max R-multiple:    {be_r_multiples.max():.3f}R")
        print(f"  Std R-multiple:    {be_r_multiples.std():.3f}R")
        print()

        # Break down what the TP1+BE exit actually yields
        for t in be_trades[:5]:
            risk_pts = abs(t.entry_price - t.stop_price)
            print(f"  Trade {t.date}: entry={t.entry_price:.5f}, stop={t.stop_price:.5f}, "
                  f"risk={risk_pts:.5f} ({risk_pts/0.0001:.0f} pips), "
                  f"actual_R={t.r_multiple:.3f}")
        print()

    # PnL breakdown by exit type
    print("PnL contribution by exit type:")
    for et, name in exit_names.items():
        subset = [t for t in filled if t.exit_type == et]
        if subset:
            total_r = sum(t.r_multiple for t in subset)
            avg_r = total_r / len(subset)
            print(f"  {name:>12s}: {len(subset):>4d} trades, total {total_r:>8.1f}R, avg {avg_r:>6.3f}R")

    # Compare to what this strategy would look like with a proportional BE
    print()
    print("=" * 70)
    print("COUNTERFACTUAL: What if BE was proportional to risk (e.g., 0.5R)?")
    print("=" * 70)
    # With a 0.5R BE: offset = 0.5 * risk_pts per trade
    # This would lock in much less profit
    for be_r_target in [0.0, 0.25, 0.50, 1.0]:
        theoretical_net_r = 0.0
        for t in filled:
            risk_pts = abs(t.entry_price - t.stop_price)
            if t.exit_type == EXIT_TP1_BE:
                # Recalculate: half at TP1 (0.4R) + half at BE (be_r_target)
                tp1_contrib = 0.5 * (4.0 * 0.10)  # = 0.2R
                be_contrib = 0.5 * be_r_target
                theoretical_net_r += tp1_contrib + be_contrib
            else:
                theoretical_net_r += t.r_multiple

        print(f"  BE at {be_r_target:.2f}R: Net R = {theoretical_net_r:.1f}R "
              f"(vs actual {sum(t.r_multiple for t in filled):.1f}R)")


if __name__ == "__main__":
    main()
