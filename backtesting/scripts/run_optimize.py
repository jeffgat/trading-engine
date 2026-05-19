#!/usr/bin/env python3
"""Run grid sweep optimization across parameter combinations.

Results are auto-saved to the main DB and viewable in the frontend dashboard.

Usage:
    # Sweep stop ATR% and min gap ATR%
    python scripts/run_optimize.py --data NQ_5m.csv \
        --sweep ny_stop_atr_pct=5:25:1 \
        --sweep ny_min_gap_atr_pct=0.5:3.0:0.25

    # Sweep R:R and TP1 ratio
    python scripts/run_optimize.py --data NQ_5m.csv \
        --sweep rr=1.5:4.0:0.5 \
        --sweep tp1_ratio=0.3:0.7:0.1

    # With date range
    python scripts/run_optimize.py --data NQ_5m.csv \
        --start 2018-01-01 --end 2025-01-01 \
        --sweep ny_stop_atr_pct=8:20:2
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, NY_SESSION, ASIA_SESSION, LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid, linspace_range, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import grid_results_to_dict, save_optimization_result
from orb_backtest.experiments import log_sweep_runs


def parse_sweep(spec: str) -> tuple[str, list[float]]:
    """Parse sweep spec like 'rr=1.5:4.0:0.5' into (name, [1.5, 2.0, 2.5, 3.0, 3.5, 4.0])."""
    name, range_str = spec.split("=", 1)
    parts = range_str.split(":")
    if len(parts) == 3:
        start, stop, step = float(parts[0]), float(parts[1]), float(parts[2])
        return name, linspace_range(start, stop, step)
    else:
        # Comma-separated values: rr=1.5,2.0,2.5
        return name, [float(v) for v in range_str.split(",")]


def main():
    parser = argparse.ArgumentParser(description="Run ORB+FVG parameter optimization sweep")
    parser.add_argument("--data", required=True, help="Data file name or path")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument("--sessions", default="NY", help="Comma-separated: NY,Asia,LDN")
    parser.add_argument("--sweep", action="append", required=True,
                        help="Parameter sweep spec: name=start:stop:step or name=v1,v2,v3")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers")
    parser.add_argument("--strategy", default=None, choices=["continuation", "reversal", "inversion"],
                        help="Strategy type: continuation (default), reversal (flip direction), or inversion (wait for FVG to be invalidated then reverse)")
    parser.add_argument("--direction", default=None, choices=["both", "long", "short"],
                        help="Direction filter: both (default), long, or short")
    parser.add_argument("--sma-gate", type=int, default=None, metavar="PERIOD",
                        help="Apply SMA trend gate post-sweep (e.g. --sma-gate 20)")
    parser.add_argument("--impulse-close-filter", action="store_true",
                        help="Allow FVGs inside ORB range when impulse candle closes outside")
    parser.add_argument("--orb-minutes", type=int, default=None, choices=[5, 10, 15, 20, 25, 30],
                        help="ORB window duration in minutes (overrides orb_end and entry_start)")
    parser.add_argument("--entry-end", default=None, metavar="HH:MM",
                        help="Override entry_end for all sessions (e.g. --entry-end 12:00)")
    parser.add_argument("--flat-start", default=None, metavar="HH:MM",
                        help="Override flat_start for all sessions (e.g. --flat-start 15:50)")
    parser.add_argument("--use-1s", action="store_true",
                        help="Load 1s bar data for highest-precision fill simulation (GC). "
                             "Defaults to --workers 1 to avoid IPC overhead with large 1s arrays.")
    parser.add_argument("--set", action="append", default=[],
                        help="Lock a param to a fixed value: name=value (e.g. --set rr=3.6)")
    parser.add_argument("--name", default=None, help="Label for this sweep (saved to main DB)")

    args = parser.parse_args()

    # Parse sweep specs
    param_ranges = {}
    for spec in args.sweep:
        name, values = parse_sweep(spec)
        param_ranges[name] = values

    # Build base config
    instrument = get_instrument(args.instrument)
    session_map = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}
    sessions = tuple(session_map[s.strip()] for s in args.sessions.split(","))
    base_config = default_config(instrument)
    base_config = with_overrides(base_config, sessions=sessions)
    if args.strategy:
        base_config = with_overrides(base_config, strategy=args.strategy)
    if args.direction:
        base_config = with_overrides(base_config, direction_filter=args.direction)
    if args.impulse_close_filter:
        base_config = with_overrides(base_config, impulse_close_filter=True)

    # Override ORB window duration and/or session time bounds
    from dataclasses import replace as dc_replace
    from datetime import datetime, timedelta
    if args.orb_minutes is not None or args.entry_end is not None or args.flat_start is not None:
        new_sessions = []
        for sess in base_config.sessions:
            updates = {}
            if args.orb_minutes is not None:
                orb_start_dt = datetime.strptime(sess.orb_start, "%H:%M")
                new_orb_end = (orb_start_dt + timedelta(minutes=args.orb_minutes)).strftime("%H:%M")
                updates["orb_end"] = new_orb_end
                updates["entry_start"] = new_orb_end
            if args.entry_end is not None:
                updates["entry_end"] = args.entry_end
            if args.flat_start is not None:
                updates["flat_start"] = args.flat_start
            new_sessions.append(dc_replace(sess, **updates))
        base_config = dc_replace(base_config, sessions=tuple(new_sessions))

    # Apply fixed param overrides (--set name=value)
    if args.set:
        fixed_overrides = {}
        for spec in args.set:
            name, val_str = spec.split("=", 1)
            # Attempt int, then float, then string
            try:
                val = int(val_str)
            except ValueError:
                try:
                    val = float(val_str)
                except ValueError:
                    val = val_str
            fixed_overrides[name] = val
        base_config = with_overrides(base_config, **fixed_overrides)

    # Generate grid
    configs = generate_param_grid(base_config, param_ranges)
    print(describe_grid(param_ranges))
    print()

    # Load data
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    t_load = time.time() - t0
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{t_load:.1f}s]")

    # Load 1m data for bar magnifier (always on — falls back to 5m if unavailable)
    df_1m = None
    try:
        t0_1m = time.time()
        df_1m = load_1m_for_5m(args.data, start=args.start, end=args.end)
        t_1m = time.time() - t0_1m
        print(f"  {len(df_1m):,} 1m bars loaded [{t_1m:.1f}s]")
    except FileNotFoundError:
        print("  1m data not found, falling back to 5m simulation")

    # Load 1s data if requested (GC only — required for tight ATR stops <3%)
    df_1s = None
    if args.use_1s:
        from orb_backtest.data.loader import load_1s_for_5m
        t0_1s = time.time()
        df_1s = load_1s_for_5m(args.data, start=args.start, end=args.end)
        if df_1s is not None:
            print(f"  {len(df_1s):,} 1s bars loaded [{time.time() - t0_1s:.1f}s]")
            if args.workers is None:
                args.workers = 1  # avoid pickling ~1GB maps to each subprocess
                print(f"  --use-1s: defaulting to --workers 1 (avoids IPC overhead with large 1s maps)")
        else:
            print("  1s data not found — continuing with 1m only")

    print()

    # Run sweep
    print(f"Running {len(configs):,} backtests...")
    t0 = time.time()

    def progress(done, total):
        pct = done / total * 100
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"\r  [{done}/{total}] {pct:.0f}% | {rate:.1f} runs/s | ETA: {eta:.0f}s", end="", flush=True)

    results = run_sweep(df, configs, n_workers=args.workers, progress_fn=progress, start_date=args.start, df_1m=df_1m, df_1s=df_1s)
    t_sweep = time.time() - t0
    print(f"\n  Completed in {t_sweep:.1f}s ({len(configs) / t_sweep:.1f} runs/s)")

    # Apply SMA trend gate if requested
    if args.sma_gate is not None:
        from orb_backtest.analysis.gates import apply_sma_trend_gate
        print(f"  Applying SMA{args.sma_gate} trend gate to all {len(results)} results...")
        results = [(config, apply_sma_trend_gate(trades, df, sma_period=args.sma_gate))
                    for config, trades in results]

    print()

    # Find and print best results
    scored = []
    for config, trades in results:
        m = compute_metrics(trades)
        scored.append((config, trades, m))

    scored_with_trades = [(c, t, m) for c, t, m in scored if m["total_trades"] > 0]

    if scored_with_trades:
        # Best by Calmar (primary objective)
        best_calmar = max(scored_with_trades, key=lambda x: x[2]["calmar_ratio"])
        _print_best("Best by Calmar Ratio", best_calmar[0], best_calmar[2], param_ranges.keys())

        # Best by Sharpe
        best_sharpe = max(scored_with_trades, key=lambda x: x[2]["sharpe_ratio"])
        _print_best("Best by Sharpe Ratio", best_sharpe[0], best_sharpe[2], param_ranges.keys())

        # Best by Net R
        best_r = max(scored_with_trades, key=lambda x: x[2]["total_r"])
        _print_best("Best by Net R", best_r[0], best_r[2], param_ranges.keys())
    else:
        print("No trades filled across any configuration!")

    # Auto-save to main DB (viewable in frontend dashboard)
    grid_dict = grid_results_to_dict(results, swept_params=param_ranges)
    if args.name:
        grid_dict["name"] = args.name
    result_id = save_optimization_result(grid_dict)

    # Log individual sweep runs to main DB
    try:
        n_logged = log_sweep_runs(results, result_id)
        print(f"  Logged {n_logged} experiment rows to DB")
    except Exception as e:
        print(f"  Warning: experiment logging failed: {e}")

    print(f"Results saved: {result_id}")
    print("View in dashboard → Optimizations tab")


def _print_best(title: str, config: StrategyConfig, metrics: dict, sweep_keys) -> None:
    """Print a best-result summary."""
    print(f"  {title}:")

    # Show swept param values
    for key in sweep_keys:
        val = _get_param_value(config, key)
        print(f"    {key} = {val}")

    print(f"    Trades: {metrics['total_trades']} | Win rate: {metrics['win_rate']:.1%}")
    print(f"    Net R: {metrics['total_r']:.1f}R | PF: {metrics['profit_factor']:.2f}")
    print(f"    Sharpe: {metrics['sharpe_ratio']:.3f} | Calmar: {metrics['calmar_ratio']:.3f}")
    print(f"    Max DD: {metrics['max_drawdown_r']:.1f}R | Avg R: {metrics['avg_r']:.3f}")
    print()


def _get_param_value(config: StrategyConfig, key: str):
    """Extract a parameter value from config, supporting session-prefixed keys."""
    for sess_prefix in ("ny_", "asia_", "ldn_"):
        if key.startswith(sess_prefix):
            param = key[len(sess_prefix):]
            sess_name = sess_prefix.rstrip("_").upper()
            if sess_name == "NY":
                sess_name = "NY"
            for s in config.sessions:
                if s.name.upper() == sess_name:
                    return getattr(s, param, None)
            return None
    return getattr(config, key, None)


if __name__ == "__main__":
    main()
