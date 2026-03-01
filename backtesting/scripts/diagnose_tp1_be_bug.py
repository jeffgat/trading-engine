#!/usr/bin/env python3
"""Diagnose TP1→BE same-bar skip bug.

Theory: With tp1_ratio=0.10, TP1 is only 0.175R from entry. On many bars,
TP1 fires and `continue` skips the BE stop check. Trades that should exit
as TP1_BE (tiny win ~0.09R) survive to become TP1_TP2 (big win).

This script:
1. Runs the NQ Asia R5 config
2. Shows exit type breakdown + avg R per exit type
3. Checks how many trades have fill_bar == exit_bar (same-bar TP1)
4. Compares tp1_ratio=0.10 vs 0.50 to show the inflation effect
"""

import sys
import time
from collections import defaultdict

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {3}

SESS = SessionConfig(
    name="Asia",
    orb_start="20:00", orb_end="20:10", entry_start="20:10",
    entry_end="00:00", flat_start="01:00", flat_end="07:00",
    stop_atr_pct=3.7, min_gap_atr_pct=0.90,
)


def run_with_tp1(df_5m, df_1m, df_1s, tp1_ratio, label):
    config = StrategyConfig(
        sessions=(SESS,), instrument=NQ, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
        rr=1.75, tp1_ratio=tp1_ratio, atr_length=5, name=label,
    )
    trades = run_backtest(df_5m, config, start_date="2016-01-01",
                          df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)
    return trades, config


def analyze_trades(trades, label):
    print(f"\n{'=' * 80}")
    print(f"  {label}")
    print(f"{'=' * 80}")

    m = compute_metrics(trades)
    print(f"  Trades: {m['total_trades']}  WR: {m['win_rate']:.1%}  "
          f"PF: {m['profit_factor']:.2f}  Sharpe: {m['sharpe_ratio']:.2f}  "
          f"Net R: {m['total_r']:.1f}  DD: {m['max_drawdown_r']:.1f}  "
          f"Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Avg R: {m['avg_r']:.4f}  Avg Win R: {m['avg_win_r']:.4f}  "
          f"Avg Loss R: {m['avg_loss_r']:.4f}")

    # Exit type breakdown
    filled = [t for t in trades if t.exit_type != 0]
    exit_groups = defaultdict(list)
    for t in filled:
        exit_groups[EXIT_NAMES.get(t.exit_type, "?")].append(t)

    print(f"\n  Exit Type Breakdown:")
    print(f"  {'Type':<12} {'Count':>6} {'%':>7} {'Avg R':>8} {'Med R':>8} "
          f"{'WR':>7} {'Tot R':>8}")
    print(f"  {'-' * 65}")

    import numpy as np
    for et in ["sl", "tp1_tp2", "tp1_be", "tp1_eod", "eod", "tp2_single"]:
        group = exit_groups.get(et, [])
        if not group:
            continue
        rs = [t.r_multiple for t in group]
        wins = sum(1 for r in rs if r > 0)
        avg_r = np.mean(rs)
        med_r = np.median(rs)
        wr = wins / len(group) if group else 0
        tot_r = sum(rs)
        pct = len(group) / len(filled) * 100
        print(f"  {et:<12} {len(group):>6} {pct:>6.1f}% {avg_r:>8.4f} "
              f"{med_r:>8.4f} {wr:>6.1%} {tot_r:>8.1f}")

    # Same-bar analysis (fill_bar == exit_bar)
    same_bar = [t for t in filled if t.fill_bar == t.exit_bar and t.fill_bar >= 0]
    print(f"\n  Same-bar trades (fill_bar == exit_bar): {len(same_bar)} "
          f"({len(same_bar)/len(filled)*100:.1f}%)")
    if same_bar:
        sb_exits = defaultdict(int)
        for t in same_bar:
            sb_exits[EXIT_NAMES.get(t.exit_type, "?")] += 1
        for et, cnt in sorted(sb_exits.items(), key=lambda x: -x[1]):
            print(f"    {et}: {cnt}")

    # How close is TP1 to entry? Show risk_pts vs TP1 distance
    if filled:
        tp1_dists = []
        for t in filled:
            if t.direction == 1:
                tp1_dist = t.tp1_price - t.entry_price
            else:
                tp1_dist = t.entry_price - t.tp1_price
            tp1_dists.append(tp1_dist / t.risk_points if t.risk_points > 0 else 0)
        print(f"\n  TP1 distance from entry: {np.mean(tp1_dists):.4f}R "
              f"(median: {np.median(tp1_dists):.4f}R)")

    return m


def main():
    print("TP1→BE Same-Bar Bug Diagnostic")
    print("=" * 80)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    # Test 1: Current R5 config (tp1=0.10)
    trades_010, _ = run_with_tp1(df_5m, df_1m, df_1s, 0.10, "tp1=0.10")
    m010 = analyze_trades(trades_010, "tp1_ratio=0.10 (R5 config)")

    # Test 2: Normal tp1 ratio (0.50)
    trades_050, _ = run_with_tp1(df_5m, df_1m, df_1s, 0.50, "tp1=0.50")
    m050 = analyze_trades(trades_050, "tp1_ratio=0.50 (normal)")

    # Comparison
    print(f"\n{'=' * 80}")
    print(f"  COMPARISON")
    print(f"{'=' * 80}")
    print(f"  {'Metric':<15} {'tp1=0.10':>12} {'tp1=0.50':>12} {'Delta':>12}")
    print(f"  {'-' * 55}")
    for key, label in [
        ("total_trades", "Trades"),
        ("win_rate", "Win Rate"),
        ("profit_factor", "PF"),
        ("sharpe_ratio", "Sharpe"),
        ("total_r", "Net R"),
        ("max_drawdown_r", "Max DD"),
        ("calmar_ratio", "Calmar"),
        ("avg_r", "Avg R"),
    ]:
        v1 = m010[key]
        v2 = m050[key]
        if key == "win_rate":
            print(f"  {label:<15} {v1:>11.1%} {v2:>11.1%} {v1-v2:>+11.1%}")
        elif key in ("avg_r",):
            print(f"  {label:<15} {v1:>12.4f} {v2:>12.4f} {v1-v2:>+12.4f}")
        else:
            print(f"  {label:<15} {v1:>12.2f} {v2:>12.2f} {v1-v2:>+12.2f}")

    print(f"\n  Runtime: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
