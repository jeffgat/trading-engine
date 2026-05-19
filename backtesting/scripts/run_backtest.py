#!/usr/bin/env python3
"""Run a single backtest with default or custom parameters.

Usage:
    python scripts/run_backtest.py --data NQ_5m.csv
    python scripts/run_backtest.py --data NQ_5m.csv --start 2020-01-01 --end 2025-01-01
    python scripts/run_backtest.py --data NQ_5m.csv --rr 3.0 --ny-stop-atr-pct 12.0
    python scripts/run_backtest.py --data NQ_5m.csv --instrument ES
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, ib_config, with_overrides, NY_SESSION, ASIA_SESSION, LDN_SESSION, IB_NY_SESSION
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument, NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NAMES, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result


def main():
    parser = argparse.ArgumentParser(description="Run ORB+FVG backtest")
    parser.add_argument("--data", required=True, help="Data file name (in data/raw/) or full path")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol (NQ, ES, YM, MNQ)")
    # Overridable strategy params
    parser.add_argument("--rr", type=float, default=None)
    parser.add_argument("--tp1-ratio", type=float, default=None)
    parser.add_argument("--runner-trail-mode", default=None, choices=["", "step_r", "risk", "atr"])
    parser.add_argument("--runner-trail-trigger-r", type=float, default=None)
    parser.add_argument("--runner-trail-stop-r", type=float, default=None)
    parser.add_argument("--runner-trail-step-r", type=float, default=None)
    parser.add_argument("--runner-trail-gap-r", type=float, default=None)
    parser.add_argument("--runner-trail-atr-pct", type=float, default=None)
    parser.add_argument("--risk-usd", type=float, default=None)
    parser.add_argument("--atr-length", type=int, default=None)
    parser.add_argument("--ny-stop-atr-pct", type=float, default=None)
    parser.add_argument("--ny-min-gap-atr-pct", type=float, default=None)
    parser.add_argument("--ny-stop-orb-pct", type=float, default=None)
    parser.add_argument("--ny-min-gap-orb-pct", type=float, default=None)
    parser.add_argument("--asia-stop-atr-pct", type=float, default=None)
    parser.add_argument("--asia-min-gap-atr-pct", type=float, default=None)
    parser.add_argument("--asia-stop-orb-pct", type=float, default=None)
    parser.add_argument("--asia-min-gap-orb-pct", type=float, default=None)
    parser.add_argument("--ldn-stop-atr-pct", type=float, default=None)
    parser.add_argument("--ldn-min-gap-atr-pct", type=float, default=None)
    parser.add_argument("--ldn-stop-orb-pct", type=float, default=None)
    parser.add_argument("--ldn-min-gap-orb-pct", type=float, default=None)

    # Session selection
    parser.add_argument("--sessions", default="NY", help="Comma-separated: NY,Asia,LDN")

    # Strategy type
    parser.add_argument("--strategy", default=None, choices=["continuation", "reversal", "inversion", "cisd", "ib"],
                        help="Strategy type: continuation (default), reversal (flip direction), inversion (wait for FVG invalidation), cisd (ORB sweep + displacement reversal), or ib (initial balance mean-reversion)")
    parser.add_argument("--direction", default=None, choices=["both", "long", "short"],
                        help="Direction filter: both (default), long, or short")

    # Experiment labeling
    parser.add_argument("--name", default=None, help="Label for this run (e.g. 'atr_stops_baseline')")
    parser.add_argument("--notes", default=None, help="Free-text notes (e.g. 'testing wider stops')")

    # Output control
    parser.add_argument("--no-trades", action="store_true", help="Exclude trade list from output")
    parser.add_argument("--quiet", action="store_true", help="Minimal output")
    parser.add_argument("--plot", action="store_true", help="Show equity curve and monthly returns")
    parser.add_argument("--sma-gate", type=int, default=None, metavar="PERIOD",
                        help="Apply SMA trend gate post-trade (e.g. --sma-gate 20)")
    parser.add_argument("--orb-minutes", type=int, default=None, choices=[5, 10, 15, 30],
                        help="ORB window duration in minutes (overrides orb_end and entry_start for all sessions)")
    parser.add_argument("--impulse-close-filter", action="store_true",
                        help="Allow FVGs inside ORB range when impulse candle closes outside")
    parser.add_argument("--set", action="append", default=[],
                        help="Set arbitrary config param: name=value (e.g. --set asia_flat_start=00:00)")

    args = parser.parse_args()

    # Build config
    instrument = get_instrument(args.instrument)

    if args.strategy == "ib":
        config = ib_config(instrument)
    else:
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
    if args.runner_trail_mode is not None:
        overrides["runner_trail_mode"] = args.runner_trail_mode
    if args.runner_trail_trigger_r is not None:
        overrides["runner_trail_trigger_r"] = args.runner_trail_trigger_r
    if args.runner_trail_stop_r is not None:
        overrides["runner_trail_stop_r"] = args.runner_trail_stop_r
    if args.runner_trail_step_r is not None:
        overrides["runner_trail_step_r"] = args.runner_trail_step_r
    if args.runner_trail_gap_r is not None:
        overrides["runner_trail_gap_r"] = args.runner_trail_gap_r
    if args.runner_trail_atr_pct is not None:
        overrides["runner_trail_atr_pct"] = args.runner_trail_atr_pct
    if args.risk_usd is not None:
        overrides["risk_usd"] = args.risk_usd
    if args.atr_length is not None:
        overrides["atr_length"] = args.atr_length

    if args.ny_stop_atr_pct is not None:
        overrides["ny_stop_atr_pct"] = args.ny_stop_atr_pct
    if args.ny_min_gap_atr_pct is not None:
        overrides["ny_min_gap_atr_pct"] = args.ny_min_gap_atr_pct
    if args.ny_stop_orb_pct is not None:
        overrides["ny_stop_orb_pct"] = args.ny_stop_orb_pct
    if args.ny_min_gap_orb_pct is not None:
        overrides["ny_min_gap_orb_pct"] = args.ny_min_gap_orb_pct
    if args.asia_stop_atr_pct is not None:
        overrides["asia_stop_atr_pct"] = args.asia_stop_atr_pct
    if args.asia_min_gap_atr_pct is not None:
        overrides["asia_min_gap_atr_pct"] = args.asia_min_gap_atr_pct
    if args.asia_stop_orb_pct is not None:
        overrides["asia_stop_orb_pct"] = args.asia_stop_orb_pct
    if args.asia_min_gap_orb_pct is not None:
        overrides["asia_min_gap_orb_pct"] = args.asia_min_gap_orb_pct
    if args.ldn_stop_atr_pct is not None:
        overrides["ldn_stop_atr_pct"] = args.ldn_stop_atr_pct
    if args.ldn_min_gap_atr_pct is not None:
        overrides["ldn_min_gap_atr_pct"] = args.ldn_min_gap_atr_pct
    if args.ldn_stop_orb_pct is not None:
        overrides["ldn_stop_orb_pct"] = args.ldn_stop_orb_pct
    if args.ldn_min_gap_orb_pct is not None:
        overrides["ldn_min_gap_orb_pct"] = args.ldn_min_gap_orb_pct
    if args.strategy is not None:
        overrides["strategy"] = args.strategy
    if args.direction is not None:
        overrides["direction_filter"] = args.direction
    if args.name is not None:
        overrides["name"] = args.name
    if args.notes is not None:
        overrides["notes"] = args.notes
    if args.impulse_close_filter:
        overrides["impulse_close_filter"] = True

    if overrides:
        config = with_overrides(config, **overrides)

    # Apply arbitrary --set overrides (e.g. --set asia_flat_start=00:00)
    if args.set:
        fixed_overrides = {}
        for spec in args.set:
            name, val_str = spec.split("=", 1)
            try:
                val = int(val_str)
            except ValueError:
                try:
                    val = float(val_str)
                except ValueError:
                    val = val_str
            fixed_overrides[name] = val
        config = with_overrides(config, **fixed_overrides)

    # Override ORB window duration if specified
    if args.orb_minutes is not None:
        from dataclasses import replace as dc_replace
        from datetime import datetime, timedelta
        new_sessions = []
        for sess in config.sessions:
            orb_start_dt = datetime.strptime(sess.orb_start, "%H:%M")
            new_orb_end = (orb_start_dt + timedelta(minutes=args.orb_minutes)).strftime("%H:%M")
            new_sessions.append(dc_replace(sess, orb_end=new_orb_end, entry_start=new_orb_end))
        config = dc_replace(config, sessions=tuple(new_sessions))

    # Load data
    if not args.quiet:
        print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    t_load = time.time() - t0

    if not args.quiet:
        print(f"  {len(df):,} bars loaded ({df.index[0].date()} to {df.index[-1].date()}) [{t_load:.1f}s]")

    # Load 1m data for bar magnifier (always on — falls back to 5m if unavailable)
    df_1m = None
    try:
        t0_1m = time.time()
        df_1m = load_1m_for_5m(args.data, start=args.start, end=args.end)
        t_1m = time.time() - t0_1m
        if not args.quiet:
            print(f"  {len(df_1m):,} 1m bars loaded [{t_1m:.1f}s]")
    except FileNotFoundError:
        if not args.quiet:
            print("  1m data not found, falling back to 5m simulation")

    # Run backtest
    if not args.quiet:
        print(f"Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, config, start_date=args.start, df_1m=df_1m)
    t_sim = time.time() - t0

    # Apply SMA trend gate if requested
    if args.sma_gate is not None:
        from orb_backtest.analysis.gates import apply_sma_trend_gate
        pre_count = len([t for t in trades if t.exit_type != EXIT_NO_FILL])
        trades = apply_sma_trend_gate(trades, df, sma_period=args.sma_gate)
        post_count = len([t for t in trades if t.exit_type != EXIT_NO_FILL])
        if not args.quiet:
            print(f"  SMA{args.sma_gate} trend gate: {pre_count} → {post_count} trades ({pre_count - post_count} filtered)")

    # Compute metrics
    metrics = compute_metrics(trades)

    if not args.quiet:
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"  {len(trades)} signals, {len(filled)} filled trades [{t_sim:.1f}s]")
        print()
        _print_summary(metrics)

    # Auto-save to experiment DB (viewable in frontend dashboard)
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    if not args.quiet:
        print(f"Results saved: {result_id}")
        print("View in dashboard → Backtests tab")

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
    print(f"  Net R:            {m['total_r']:.1f}R")
    print(f"  Avg R:            {m['avg_r']:.3f}R")
    print(f"  Avg win R:        {m['avg_win_r']:.3f}R")
    print(f"  Avg loss R:       {m['avg_loss_r']:.3f}R")
    print()
    print(f"  Profit factor:    {m['profit_factor']:.2f}")
    print(f"  Max DD (R):       {m['max_drawdown_r']:.1f}R")
    print(f"  Sharpe ratio:     {m['sharpe_ratio']:.3f}")
    print(f"  Sortino ratio:    {m['sortino_ratio']:.3f}")
    print(f"  Calmar ratio:     {m['calmar_ratio']:.3f}")
    print(f"  Max consec wins:  {m['max_consecutive_wins']}")
    print(f"  Max consec losses:{m['max_consecutive_losses']}")
    print()
    print(f"  Long trades:      {m['long_trades']} ({m['long_win_rate']:.1%} WR, {m['long_r']:.1f}R)")
    print(f"  Short trades:     {m['short_trades']} ({m['short_win_rate']:.1%} WR, {m['short_r']:.1f}R)")
    print()

    # Exit breakdown
    print("  Exit breakdown:")
    for exit_type, count in sorted(m["exit_breakdown"].items()):
        pct = count / m["total_signals"] * 100 if m["total_signals"] > 0 else 0
        print(f"    {exit_type:15s} {count:4d} ({pct:5.1f}%)")
    print()

    # R by year
    r_by_year = m.get("r_by_year", {})
    if r_by_year:
        print("  R by year:")
        for year, r in r_by_year.items():
            print(f"    {year}: {r:>8.1f}R")
    print("=" * 60)


if __name__ == "__main__":
    main()
