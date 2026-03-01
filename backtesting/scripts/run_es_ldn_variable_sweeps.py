#!/usr/bin/env python3
"""ES LDN — Variable sweeps: max_gap_points, atr_length, ORB window, entry end.
Uses top base configs from prior sweep. BE offset=0, magnifier ON."""

import sys, time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"

# Top base combos to test each variable against
BASE_COMBOS = [
    {"rr": 3.0, "ldn_stop_atr_pct": 1.5, "ldn_min_gap_atr_pct": 1.5, "tp1_ratio": 0.5},   # best calmar
    {"rr": 3.0, "ldn_stop_atr_pct": 1.5, "ldn_min_gap_atr_pct": 2.0, "tp1_ratio": 0.5},   # best sharpe
    {"rr": 3.0, "ldn_stop_atr_pct": 1.5, "ldn_min_gap_atr_pct": 1.5, "tp1_ratio": 0.4},   # calmar #2
    {"rr": 3.5, "ldn_stop_atr_pct": 1.5, "ldn_min_gap_atr_pct": 1.5, "tp1_ratio": 0.5},   # high rr
    {"rr": 2.75, "ldn_stop_atr_pct": 1.5, "ldn_min_gap_atr_pct": 1.5, "tp1_ratio": 0.5},  # mid rr
]


def make_base(combo):
    config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        name="ES LDN Variable Sweep",
    )
    return with_overrides(config, **combo)


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return compute_metrics(trades)


def print_header(title):
    print(f"\n{'='*120}")
    print(f"  {title}")
    print(f"{'='*120}")
    print(f"{'#':>3} {'Variable':>12} {'Base':>5} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7}")
    print("-" * 120)


def print_row(i, var_label, base_idx, combo, m):
    print(f"{i:>3} {var_label:>12} {base_idx:>5} {combo['rr']:>5.2f} {combo['ldn_stop_atr_pct']:>5.1f} "
          f"{combo['ldn_min_gap_atr_pct']:>5.2f} {combo['tp1_ratio']:>5.2f} "
          f"{m['total_trades']:>7} {m['win_rate']:>5.1%} {m['profit_factor']:>6.2f} {m['sharpe_ratio']:>7.2f} "
          f"{m['total_r']:>7.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f}")


def main():
    print("ES LDN — Variable Sweeps")
    print("=" * 70)

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s")

    # ── 1. MAX GAP POINTS ─────────────────────────────────────────────
    max_gap_values = [10, 15, 20, 25, 30, 40, 50, 75, 100]
    print_header(f"MAX GAP POINTS SWEEP ({max_gap_values})")

    row_idx = 1
    for bi, combo in enumerate(BASE_COMBOS):
        for mg in max_gap_values:
            config = make_base(combo)
            sess = replace(config.sessions[0], max_gap_points=mg)
            config = replace(config, sessions=(sess,))
            m = run_and_metric(df_5m, df_1m, config)
            print_row(row_idx, f"maxgap={mg}", bi + 1, combo, m)
            row_idx += 1

    # ── 2. ATR LENGTH ──────────────────────────────────────────────────
    atr_values = [7, 10, 14, 20, 30, 50]
    print_header(f"ATR LENGTH SWEEP ({atr_values})")

    row_idx = 1
    for bi, combo in enumerate(BASE_COMBOS):
        for atr in atr_values:
            config = make_base(combo)
            config = replace(config, atr_length=atr)
            m = run_and_metric(df_5m, df_1m, config)
            print_row(row_idx, f"atr={atr}", bi + 1, combo, m)
            row_idx += 1

    # ── 3. ORB WINDOW ──────────────────────────────────────────────────
    orb_windows = [
        ("15m", "03:00", "03:15", "03:15"),
        ("30m", "03:00", "03:30", "03:30"),
        ("45m", "03:00", "03:45", "03:45"),
        ("60m", "03:00", "04:00", "04:00"),
    ]
    print_header(f"ORB WINDOW SWEEP (15m/30m/45m/60m)")

    row_idx = 1
    for bi, combo in enumerate(BASE_COMBOS):
        for label, orb_s, orb_e, entry_s in orb_windows:
            config = make_base(combo)
            sess = replace(config.sessions[0], orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
            config = replace(config, sessions=(sess,))
            m = run_and_metric(df_5m, df_1m, config)
            print_row(row_idx, f"orb={label}", bi + 1, combo, m)
            row_idx += 1

    # ── 4. ENTRY END TIME ──────────────────────────────────────────────
    entry_ends = ["05:00", "06:00", "07:00", "08:00", "08:25"]
    print_header(f"ENTRY END TIME SWEEP ({entry_ends})")

    row_idx = 1
    for bi, combo in enumerate(BASE_COMBOS):
        for ee in entry_ends:
            config = make_base(combo)
            sess = replace(config.sessions[0], entry_end=ee)
            config = replace(config, sessions=(sess,))
            m = run_and_metric(df_5m, df_1m, config)
            print_row(row_idx, f"end={ee}", bi + 1, combo, m)
            row_idx += 1

    print(f"\n{'='*70}")
    print(f"  ALL SWEEPS COMPLETE")
    print(f"{'='*70}")


if __name__ == "__main__":
    main()
