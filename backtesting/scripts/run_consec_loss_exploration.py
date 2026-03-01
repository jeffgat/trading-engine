#!/usr/bin/env python3
"""Explore N (consecutive losses) and M (skip count) variations for the
consecutive loss gate.

Runs a wide sweep (N=1..8, M=1..10), outputs:
  1. Full grid sorted by Sharpe
  2. Heatmap-style N×M table for Sharpe, Total R, Max DD
  3. Per-session (NY / Asia) best combos
  4. Robustness check: how stable is each combo vs nearby params

Usage:
    python scripts/run_consec_loss_exploration.py
    python scripts/run_consec_loss_exploration.py --start 2016-01-01 --end 2026-01-01
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_continuation.config import production_config
from core.data.instruments import get_instrument
from core.data.loader import load_5m_data
from core.engine.simulator import run_backtest, EXIT_NO_FILL, TradeResult
from core.results.metrics import compute_metrics
from core.analysis.pre_trade_gates import (
    ConsecLossGateConfig, simulate_consec_loss_gate, sweep_consec_loss_gate,
)

# ── Sweep ranges ─────────────────────────────────────────────────────

N_RANGE = tuple(range(1, 9))       # 1..8 consecutive losses
M_RANGE = tuple(range(1, 11))      # 1..10 trades to skip


def main():
    parser = argparse.ArgumentParser(description="Consecutive loss gate N×M exploration")
    parser.add_argument("--data", default="NQ_5m.csv", help="Data file")
    parser.add_argument("--start", default="2016-01-01", help="Start date")
    parser.add_argument("--end", default="2026-01-01", help="End date")
    parser.add_argument("--instrument", default="NQ", help="Instrument")
    args = parser.parse_args()

    instrument = get_instrument(args.instrument)

    # ── Load data ────────────────────────────────────────────────────
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    # ── Run backtests per session ────────────────────────────────────
    all_trades: list[TradeResult] = []
    session_trades: dict[str, list[TradeResult]] = {}

    for config in production_config(instrument):
        sess_name = config.sessions[0].name
        print(f"\n  Running {sess_name} backtest...")
        t0 = time.time()
        trades = run_backtest(df, config, start_date=args.start)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"    {len(trades)} signals, {len(filled)} filled [{time.time() - t0:.1f}s]")
        all_trades.extend(trades)
        session_trades[sess_name] = trades

    all_trades.sort(key=lambda t: t.date)
    filled_total = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
    baseline = compute_metrics(all_trades)
    risk_usd = 5000.0

    print(f"\n  Combined: {len(filled_total)} filled trades")
    print(f"  Baseline: {baseline['total_pnl_usd']/risk_usd:.1f}R, "
          f"WR={baseline['win_rate']:.1%}, Sharpe={baseline['sharpe_ratio']:.3f}, "
          f"Max DD=${baseline['max_drawdown_usd']:,.0f}")

    # ── Full sweep ───────────────────────────────────────────────────
    print()
    print("=" * 90)
    print(f"CONSECUTIVE LOSS GATE — FULL SWEEP (N={N_RANGE[0]}..{N_RANGE[-1]}, M={M_RANGE[0]}..{M_RANGE[-1]})")
    print("=" * 90)

    results = sweep_consec_loss_gate(
        all_trades, n_losses_range=N_RANGE, skip_range=M_RANGE,
    )

    # Build lookup dict for heatmap
    grid = {}
    for r in results:
        grid[(r["n_losses"], r["skip_count"])] = r

    # ── Sorted table (top 30) ────────────────────────────────────────
    print(f"\n  Top 30 by Sharpe:")
    print(f"  {'N':>3} {'M':>3} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
          f"{'Sharpe':>8} {'Calmar':>8} {'MaxDD':>10} {'Skip':>5} {'Trig':>5} {'R/Skipped':>10}")
    print(f"  {'─'*3} {'─'*3} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*10} {'─'*5} {'─'*5} {'─'*10}")

    baseline_r = baseline['total_pnl_usd'] / risk_usd
    for r in results[:30]:
        r_cost = baseline_r - r["total_r"]
        r_per_skip = r_cost / r["skipped"] if r["skipped"] > 0 else 0
        print(f"  {r['n_losses']:>3} {r['skip_count']:>3} "
              f"{r['trades']:>7} {r['win_rate']:>5.1%} {r['total_r']:>8.1f} "
              f"{r['sharpe']:>8.3f} {r['calmar']:>8.3f} "
              f"${r['max_dd_usd']:>9,.0f} {r['skipped']:>5} {r['times_triggered']:>5} "
              f"{r_per_skip:>+9.3f}R")

    # ── Heatmaps ─────────────────────────────────────────────────────
    _print_heatmap("Sharpe", grid, lambda r: f"{r['sharpe']:6.3f}", baseline['sharpe_ratio'])
    _print_heatmap("Total R", grid, lambda r: f"{r['total_r']:6.1f}", baseline_r)
    _print_heatmap("Max DD ($K)", grid, lambda r: f"{r['max_dd_usd']/1000:6.0f}", baseline['max_drawdown_usd']/1000)
    _print_heatmap("Win Rate (%)", grid, lambda r: f"{r['win_rate']*100:5.1f}%", baseline['win_rate']*100)
    _print_heatmap("Trades Skipped", grid, lambda r: f"{r['skipped']:6d}", 0)
    _print_heatmap("Times Triggered", grid, lambda r: f"{r['times_triggered']:6d}", 0)

    # ── Robustness: neighbor stability ────────────────────────────────
    print()
    print("=" * 90)
    print("ROBUSTNESS — Neighbor Stability (avg Sharpe of 3×3 neighborhood)")
    print("=" * 90)
    print(f"  Top combos should have neighbors with similar Sharpe (no isolated peaks).\n")

    robust_scores = []
    for n in N_RANGE:
        for m in M_RANGE:
            if (n, m) not in grid:
                continue
            neighbors = []
            for dn in [-1, 0, 1]:
                for dm in [-1, 0, 1]:
                    key = (n + dn, m + dm)
                    if key in grid:
                        neighbors.append(grid[key]["sharpe"])
            if len(neighbors) >= 4:  # at least 4 neighbors (including self)
                avg_sharpe = sum(neighbors) / len(neighbors)
                min_sharpe = min(neighbors)
                robust_scores.append({
                    "n": n, "m": m,
                    "sharpe": grid[(n, m)]["sharpe"],
                    "neighbor_avg": avg_sharpe,
                    "neighbor_min": min_sharpe,
                    "neighbor_count": len(neighbors),
                    "total_r": grid[(n, m)]["total_r"],
                    "max_dd": grid[(n, m)]["max_dd_usd"],
                })

    robust_scores.sort(key=lambda x: x["neighbor_avg"], reverse=True)

    print(f"  {'N':>3} {'M':>3} {'Sharpe':>8} {'NbrAvg':>8} {'NbrMin':>8} {'NbrN':>5} {'TotalR':>8} {'MaxDD':>10}")
    print(f"  {'─'*3} {'─'*3} {'─'*8} {'─'*8} {'─'*8} {'─'*5} {'─'*8} {'─'*10}")
    for r in robust_scores[:15]:
        print(f"  {r['n']:>3} {r['m']:>3} "
              f"{r['sharpe']:>8.3f} {r['neighbor_avg']:>8.3f} {r['neighbor_min']:>8.3f} "
              f"{r['neighbor_count']:>5} {r['total_r']:>8.1f} ${r['max_dd']:>9,.0f}")

    # ── Per-session sweeps ───────────────────────────────────────────
    for sess_name in ["NY", "Asia"]:
        sess = session_trades.get(sess_name, [])
        if not sess:
            continue

        sess_filled = [t for t in sess if t.exit_type != EXIT_NO_FILL]
        sess_baseline = compute_metrics(sess)

        print()
        print("=" * 90)
        print(f"{sess_name} SESSION — Consecutive Loss Gate Sweep ({len(sess_filled)} trades)")
        print("=" * 90)
        print(f"  Baseline: {sess_baseline['total_pnl_usd']/risk_usd:.1f}R, "
              f"WR={sess_baseline['win_rate']:.1%}, Sharpe={sess_baseline['sharpe_ratio']:.3f}")

        sess_results = sweep_consec_loss_gate(
            sess, n_losses_range=N_RANGE, skip_range=M_RANGE,
        )

        sess_grid = {}
        for r in sess_results:
            sess_grid[(r["n_losses"], r["skip_count"])] = r

        print(f"\n  Top 15 by Sharpe:")
        print(f"  {'N':>3} {'M':>3} {'Trades':>7} {'WR':>6} {'TotalR':>8} "
              f"{'Sharpe':>8} {'Calmar':>8} {'MaxDD':>10} {'Skip':>5} {'Trig':>5}")
        print(f"  {'─'*3} {'─'*3} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*10} {'─'*5} {'─'*5}")
        for r in sess_results[:15]:
            print(f"  {r['n_losses']:>3} {r['skip_count']:>3} "
                  f"{r['trades']:>7} {r['win_rate']:>5.1%} {r['total_r']:>8.1f} "
                  f"{r['sharpe']:>8.3f} {r['calmar']:>8.3f} "
                  f"${r['max_dd_usd']:>9,.0f} {r['skipped']:>5} {r['times_triggered']:>5}")

        _print_heatmap(f"{sess_name} Sharpe", sess_grid,
                       lambda r: f"{r['sharpe']:6.3f}", sess_baseline['sharpe_ratio'])

    print()
    print("=" * 90)
    print("Done.")
    print("=" * 90)


def _print_heatmap(title: str, grid: dict, fmt_fn, baseline_val):
    """Print N×M heatmap."""
    print()
    print("-" * 90)
    print(f"  {title} Heatmap (N=rows, M=cols)    [Baseline: {baseline_val}]")
    print("-" * 90)

    # Header
    header = f"  {'N\\M':>5}"
    for m in M_RANGE:
        header += f" {'M='+str(m):>7}"
    print(header)
    print(f"  {'─'*5}" + f" {'─'*7}" * len(M_RANGE))

    for n in N_RANGE:
        row = f"  {'N='+str(n):>5}"
        for m in M_RANGE:
            key = (n, m)
            if key in grid:
                row += f" {fmt_fn(grid[key]):>7}"
            else:
                row += f" {'--':>7}"
        print(row)


if __name__ == "__main__":
    main()
