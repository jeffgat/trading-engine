#!/usr/bin/env python3
"""Run a single backtest with default or custom parameters.

Usage:
    python scripts/run_backtest.py --data NQ_5m.csv
    python scripts/run_backtest.py --data NQ_5m.csv --start 2020-01-01 --end 2025-01-01
    python scripts/run_backtest.py --data NQ_5m.csv --rr 3.0 --ny-stop-atr-pct 12.0
    python scripts/run_backtest.py --data NQ_5m.csv --instrument ES --output results.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, with_overrides, NY_SESSION, ASIA_SESSION, LDN_SESSION
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument, NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NAMES, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_json, results_to_dict, save_results, save_backtest_result


def main():
    parser = argparse.ArgumentParser(description="Run ORB+FVG backtest")
    parser.add_argument("--data", required=True, help="Data file name (in data/raw/) or full path")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol (NQ, ES, YM, MNQ)")
    parser.add_argument("--output", default=None, help="Output JSON file path")

    # Overridable strategy params
    parser.add_argument("--rr", type=float, default=None)
    parser.add_argument("--tp1-ratio", type=float, default=None)
    parser.add_argument("--risk-usd", type=float, default=None)
    parser.add_argument("--atr-length", type=int, default=None)
    parser.add_argument("--be-offset-ticks", type=int, default=None)
    parser.add_argument("--ny-stop-atr-pct", type=float, default=None)
    parser.add_argument("--ny-min-gap-atr-pct", type=float, default=None)
    parser.add_argument("--ny-max-gap-points", type=float, default=None)
    parser.add_argument("--asia-stop-atr-pct", type=float, default=None)
    parser.add_argument("--asia-min-gap-atr-pct", type=float, default=None)
    parser.add_argument("--asia-max-gap-points", type=float, default=None)
    parser.add_argument("--ldn-stop-atr-pct", type=float, default=None)
    parser.add_argument("--ldn-min-gap-atr-pct", type=float, default=None)
    parser.add_argument("--ldn-max-gap-points", type=float, default=None)

    # Session selection
    parser.add_argument("--sessions", default="NY", help="Comma-separated: NY,Asia,LDN")

    # Experiment labeling
    parser.add_argument("--name", default=None, help="Label for this run (e.g. 'atr_stops_baseline')")
    parser.add_argument("--notes", default=None, help="Free-text notes (e.g. 'testing wider stops')")

    # Output control
    parser.add_argument("--no-trades", action="store_true", help="Exclude trade list from output")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--plot", action="store_true", help="Show equity curve and monthly returns")

    args = parser.parse_args()

    # Build config
    instrument = get_instrument(args.instrument)

    session_map = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}
    sessions = tuple(session_map[s.strip()] for s in args.sessions.split(","))

    config = default_config(instrument)
    config = with_overrides(config, sessions=sessions)

    # Apply overrides
    overrides = {}
    if args.rr is not None:
        overrides["rr"] = args.rr
    if args.tp1_ratio is not None:
        overrides["tp1_ratio"] = args.tp1_ratio
    if args.risk_usd is not None:
        overrides["risk_usd"] = args.risk_usd
    if args.atr_length is not None:
        overrides["atr_length"] = args.atr_length
    if args.be_offset_ticks is not None:
        overrides["be_offset_ticks"] = args.be_offset_ticks
    if args.ny_stop_atr_pct is not None:
        overrides["ny_stop_atr_pct"] = args.ny_stop_atr_pct
    if args.ny_min_gap_atr_pct is not None:
        overrides["ny_min_gap_atr_pct"] = args.ny_min_gap_atr_pct
    if args.ny_max_gap_points is not None:
        overrides["ny_max_gap_points"] = args.ny_max_gap_points
    if args.asia_stop_atr_pct is not None:
        overrides["asia_stop_atr_pct"] = args.asia_stop_atr_pct
    if args.asia_min_gap_atr_pct is not None:
        overrides["asia_min_gap_atr_pct"] = args.asia_min_gap_atr_pct
    if args.asia_max_gap_points is not None:
        overrides["asia_max_gap_points"] = args.asia_max_gap_points
    if args.ldn_stop_atr_pct is not None:
        overrides["ldn_stop_atr_pct"] = args.ldn_stop_atr_pct
    if args.ldn_min_gap_atr_pct is not None:
        overrides["ldn_min_gap_atr_pct"] = args.ldn_min_gap_atr_pct
    if args.ldn_max_gap_points is not None:
        overrides["ldn_max_gap_points"] = args.ldn_max_gap_points
    if args.name is not None:
        overrides["name"] = args.name
    if args.notes is not None:
        overrides["notes"] = args.notes

    if overrides:
        config = with_overrides(config, **overrides)

    # Load data
    if not args.quiet:
        print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    t_load = time.time() - t0

    if not args.quiet:
        print(f"  {len(df):,} bars loaded ({df.index[0].date()} to {df.index[-1].date()}) [{t_load:.1f}s]")

    # Run backtest
    if not args.quiet:
        print(f"Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, config, start_date=args.start)
    t_sim = time.time() - t0

    # Compute metrics
    metrics = compute_metrics(trades)

    if not args.quiet:
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"  {len(trades)} signals, {len(filled)} filled trades [{t_sim:.1f}s]")
        print()
        _print_summary(metrics)

    # Auto-save to data/results/ (viewable in frontend dashboard)
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    if not args.quiet:
        print(f"Results saved: {result_id}")
        print("View in dashboard → Backtests tab")

    # Optional explicit output path
    if args.output:
        save_results(trades, config, args.output, include_trades=not args.no_trades)
        if not args.quiet:
            print(f"Also saved to: {args.output}")

    # Plot equity curve and monthly returns
    if args.plot:
        from orb_backtest.viz.equity import plot_equity_curve, plot_monthly_returns
        plot_equity_curve(trades, title=f"ORB+FVG — {args.instrument} ({args.start or 'all'} to {args.end or 'now'})")
        plot_monthly_returns(trades, title=f"Monthly Returns — {args.instrument}")


def _print_summary(m: dict) -> None:
    """Print a formatted summary to stdout."""
    print("=" * 60)
    print("BACKTEST RESULTS")
    print("=" * 60)
    print(f"  Signals:          {m['total_signals']}")
    print(f"  Filled trades:    {m['total_trades']}")
    print(f"  No fills:         {m['no_fills']}")
    print()
    print(f"  Win rate:         {m['win_rate']:.1%}")
    print(f"  Wins / Losses:    {m['win_count']} / {m['loss_count']}")
    print(f"  Total PnL:        ${m['total_pnl_usd']:,.2f}")
    print(f"  Avg PnL/trade:    ${m['avg_pnl_usd']:,.2f}")
    print(f"  Avg win:          ${m['avg_win_usd']:,.2f}")
    print(f"  Avg loss:         ${m['avg_loss_usd']:,.2f}")
    print(f"  Largest win:      ${m['largest_win_usd']:,.2f}")
    print(f"  Largest loss:     ${m['largest_loss_usd']:,.2f}")
    print()
    print(f"  Profit factor:    {m['profit_factor']:.2f}")
    print(f"  Avg R:            {m['avg_r']:.3f}R")
    print(f"  Avg win R:        {m['avg_win_r']:.3f}R")
    print(f"  Avg loss R:       {m['avg_loss_r']:.3f}R")
    print(f"  Max drawdown:     ${m['max_drawdown_usd']:,.2f}")
    print(f"  Sharpe ratio:     {m['sharpe_ratio']:.3f}")
    print(f"  Sortino ratio:    {m['sortino_ratio']:.3f}")
    print(f"  Max consec wins:  {m['max_consecutive_wins']}")
    print(f"  Max consec losses:{m['max_consecutive_losses']}")
    print()
    print(f"  Long trades:      {m['long_trades']} ({m['long_win_rate']:.1%} WR, ${m['long_pnl_usd']:,.2f})")
    print(f"  Short trades:     {m['short_trades']} ({m['short_win_rate']:.1%} WR, ${m['short_pnl_usd']:,.2f})")
    print()

    # Exit breakdown
    print("  Exit breakdown:")
    for exit_type, count in sorted(m["exit_breakdown"].items()):
        pct = count / m["total_signals"] * 100 if m["total_signals"] > 0 else 0
        print(f"    {exit_type:15s} {count:4d} ({pct:5.1f}%)")
    print()

    # PnL by year
    if m["pnl_by_year"]:
        print("  PnL by year:")
        for year, pnl in m["pnl_by_year"].items():
            print(f"    {year}: ${pnl:>10,.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
