#!/usr/bin/env python3
"""Run grid sweep optimization across parameter combinations.

Usage:
    # Sweep stop ATR% and min gap ATR%
    python scripts/run_optimize.py --data NQ_5m.csv \
        --sweep ny_stop_atr_pct=5:25:1 \
        --sweep ny_min_gap_atr_pct=0.5:3.0:0.25

    # Sweep R:R and TP1 ratio
    python scripts/run_optimize.py --data NQ_5m.csv \
        --sweep rr=1.5:4.0:0.5 \
        --sweep tp1_ratio=0.3:0.7:0.1

    # With date range and custom output
    python scripts/run_optimize.py --data NQ_5m.csv \
        --start 2018-01-01 --end 2025-01-01 \
        --sweep ny_stop_atr_pct=8:20:2 \
        --output sweep_results.json \
        --heatmap
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import default_config, NY_SESSION
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid, linspace_range, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import grid_results_to_dict


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
    parser.add_argument("--sweep", action="append", required=True,
                        help="Parameter sweep spec: name=start:stop:step or name=v1,v2,v3")
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--heatmap", action="store_true", help="Generate heatmap visualization")
    parser.add_argument("--workers", type=int, default=None, help="Number of parallel workers")
    parser.add_argument("--metric", default="sharpe_ratio",
                        help="Metric for heatmap coloring (default: sharpe_ratio)")

    args = parser.parse_args()

    # Parse sweep specs
    param_ranges = {}
    for spec in args.sweep:
        name, values = parse_sweep(spec)
        param_ranges[name] = values

    # Build base config
    instrument = get_instrument(args.instrument)
    base_config = default_config(instrument)

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

    results = run_sweep(df, configs, n_workers=args.workers, progress_fn=progress)
    t_sweep = time.time() - t0
    print(f"\n  Completed in {t_sweep:.1f}s ({len(configs) / t_sweep:.1f} runs/s)")
    print()

    # Find and print best results
    scored = []
    for config, trades in results:
        m = compute_metrics(trades)
        scored.append((config, trades, m))

    scored_with_trades = [(c, t, m) for c, t, m in scored if m["total_trades"] > 0]

    if scored_with_trades:
        # Best by Sharpe
        best_sharpe = max(scored_with_trades, key=lambda x: x[2]["sharpe_ratio"])
        _print_best("Best by Sharpe Ratio", best_sharpe[0], best_sharpe[2], param_ranges.keys())

        # Best by total PnL
        best_pnl = max(scored_with_trades, key=lambda x: x[2]["total_pnl_usd"])
        _print_best("Best by Total PnL", best_pnl[0], best_pnl[2], param_ranges.keys())

        # Best by profit factor
        best_pf = max(scored_with_trades, key=lambda x: x[2]["profit_factor"])
        _print_best("Best by Profit Factor", best_pf[0], best_pf[2], param_ranges.keys())
    else:
        print("No trades filled across any configuration!")

    # Save results
    if args.output:
        grid_dict = grid_results_to_dict(results)
        with open(args.output, "w") as f:
            json.dump(grid_dict, f, indent=2, default=str)
        print(f"\nResults saved to: {args.output}")

    # Generate heatmap
    if args.heatmap and len(param_ranges) >= 2:
        keys = list(param_ranges.keys())
        try:
            from orb_backtest.viz.heatmap import plot_sweep_heatmap
            plot_sweep_heatmap(
                results=[(c, compute_metrics(t)) for c, t in results],
                x_param=keys[0],
                y_param=keys[1],
                metric=args.metric,
                param_ranges=param_ranges,
            )
            print(f"\nHeatmap saved.")
        except ImportError:
            print("\nHeatmap visualization not available (missing matplotlib/seaborn).")


def _print_best(title: str, config: StrategyConfig, metrics: dict, sweep_keys) -> None:
    """Print a best-result summary."""
    print(f"  {title}:")

    # Show swept param values
    for key in sweep_keys:
        val = _get_param_value(config, key)
        print(f"    {key} = {val}")

    print(f"    Trades: {metrics['total_trades']} | Win rate: {metrics['win_rate']:.1%}")
    print(f"    PnL: ${metrics['total_pnl_usd']:,.2f} | PF: {metrics['profit_factor']:.2f}")
    print(f"    Sharpe: {metrics['sharpe_ratio']:.3f} | Max DD: ${metrics['max_drawdown_usd']:,.2f}")
    print(f"    Avg R: {metrics['avg_r']:.3f}")
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
