#!/usr/bin/env python3
"""Run Monte Carlo simulation for strategy robustness analysis.

Two modes:

1. Trade resampling (bootstrap/shuffle) — assess variance of observed results:
    python scripts/run_monte_carlo.py --data NQ_5m.csv --sessions NY \
        --method bootstrap --sims 2000 --seed 42

    python scripts/run_monte_carlo.py --result <backtest_id> \
        --method shuffle --sims 1000

2. Parameter-space LHS sampling — assess parameter sensitivity:
    python scripts/run_monte_carlo.py --data NQ_5m.csv --sessions NY \
        --param-sample \
        --param rr=1.5:4.0:0.5 --param ny_stop_atr_pct=5:25:1 \
        --sims 200 --workers 8
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from orb_backtest.config import (
    default_config,
    with_overrides,
    NY_SESSION,
    ASIA_SESSION,
    LDN_SESSION,
)
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.export import (
    load_backtest_result,
    save_optimization_result,
    results_to_dict,
)
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.simulate.monte_carlo import (
    run_monte_carlo,
    MonteCarloConfig,
    mc_result_to_dict,
)


SESSION_MAP = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}


def main():
    parser = argparse.ArgumentParser(
        description="Monte Carlo simulation for ORB+FVG strategy"
    )

    # Data source (either --data for live backtest or --result for saved)
    parser.add_argument("--data", default=None, help="Data file name or path")
    parser.add_argument("--result", default=None, help="Saved backtest result ID")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument("--sessions", default="NY", help="Comma-separated: NY,Asia,LDN")

    # MC config
    parser.add_argument(
        "--method", default="bootstrap",
        choices=["bootstrap", "shuffle", "block_bootstrap"],
    )
    parser.add_argument(
        "--block-length", type=int, default=None,
        help="Block length for block_bootstrap method (default: sqrt(n_trades))",
    )
    parser.add_argument("--sims", type=int, default=1000, help="Number of simulations")
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument(
        "--ruin-threshold", type=float, default=-8.0,
        help="Drawdown threshold for ruin probability (in R-multiples, default: -8.0)",
    )

    # LHS parameter sampling mode
    parser.add_argument(
        "--param-sample", action="store_true",
        help="Switch to LHS parameter-space sampling mode",
    )
    parser.add_argument(
        "--param", action="append", default=None,
        help="Parameter bounds: name=low:high or name=low:high:step (for --param-sample)",
    )
    parser.add_argument("--workers", type=int, default=None, help="Parallel workers (--param-sample)")

    # Output
    parser.add_argument("--output", default=None, help="Output JSON file path")
    parser.add_argument("--quiet", action="store_true")

    args = parser.parse_args()

    if args.param_sample:
        _run_param_sample(args)
    else:
        _run_trade_resample(args)


def _run_trade_resample(args):
    """Trade-level Monte Carlo (bootstrap or shuffle)."""
    # Get trades from either saved result or live backtest
    if args.result:
        if not args.quiet:
            print(f"Loading saved backtest: {args.result}")
        data = load_backtest_result(args.result)
        if data is None:
            print(f"Error: backtest '{args.result}' not found", file=sys.stderr)
            sys.exit(1)
        trades_dicts = data.get("trades", [])
        if not trades_dicts:
            print("Error: no trades in saved result", file=sys.stderr)
            sys.exit(1)
        trades = _reconstruct_trades(trades_dicts)
        if not args.quiet:
            filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
            print(f"  {len(filled)} filled trades loaded")
    elif args.data:
        trades = _run_backtest(args)
    else:
        print("Error: provide either --data or --result", file=sys.stderr)
        sys.exit(1)

    # Run Monte Carlo
    mc_config = MonteCarloConfig(
        n_simulations=args.sims,
        method=args.method,
        seed=args.seed,
        block_length=args.block_length,
    )

    if not args.quiet:
        print(f"\nRunning {args.sims:,} {args.method} simulations...")
    t0 = time.time()
    result = run_monte_carlo(trades, mc_config, ruin_threshold=args.ruin_threshold)
    t_mc = time.time() - t0

    if not args.quiet:
        print(f"  Completed in {t_mc:.1f}s")
        print()
        _print_mc_summary(result)

    # Save output
    if args.output:
        Path(args.output).write_text(json.dumps(mc_result_to_dict(result), indent=2))
        if not args.quiet:
            print(f"Results saved to: {args.output}")


def _run_param_sample(args):
    """LHS parameter-space Monte Carlo sampling."""
    if not args.data:
        print("Error: --data required for --param-sample", file=sys.stderr)
        sys.exit(1)
    if not args.param:
        print("Error: --param required for --param-sample", file=sys.stderr)
        sys.exit(1)

    try:
        from scipy.stats import qmc  # noqa: F401
    except ImportError:
        print("LHS parameter sampling requires scipy. Install with:")
        print("  uv sync --extra simulate")
        sys.exit(1)

    from orb_backtest.optimize.bayesian import parse_bayesian_param
    from orb_backtest.optimize.parallel import run_sweep
    from orb_backtest.results.export import grid_results_to_dict

    # Parse params
    params = [parse_bayesian_param(spec) for spec in args.param]

    # Build base config
    instrument = get_instrument(args.instrument)
    sessions = tuple(SESSION_MAP[s.strip()] for s in args.sessions.split(","))
    base_config = default_config(instrument)
    base_config = with_overrides(base_config, sessions=sessions)

    if not args.quiet:
        print(f"LHS Parameter-Space Monte Carlo")
        print(f"  Samples: {args.sims}")
        if args.seed is not None:
            print(f"  Seed: {args.seed}")
        print(f"  Parameters:")
        for p in params:
            step_str = f" step={p.step}" if p.step else " continuous"
            print(f"    {p.name}: [{p.low}, {p.high}]{step_str}")
        print()

    # Load data
    if not args.quiet:
        print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    if not args.quiet:
        print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")
        print()

    # Generate LHS configs
    from orb_backtest.optimize.lhs import generate_lhs_configs
    configs = generate_lhs_configs(base_config, params, n_samples=args.sims, seed=args.seed)
    if not args.quiet:
        print(f"Running {len(configs)} LHS-sampled backtests...")

    # Run sweep
    t0 = time.time()
    results = run_sweep(df, configs, n_workers=args.workers, start_date=args.start)
    t_sweep = time.time() - t0

    if not args.quiet:
        print(f"  Completed in {t_sweep:.1f}s ({len(configs) / t_sweep:.1f}/s)")
        print()

    # Build swept_params from param definitions
    swept_params = {}
    for p in params:
        values = sorted(set(
            round(getattr(c, p.name, None) or _get_session_param(c, p.name), 4)
            for c in configs
        ))
        swept_params[p.name] = values

    # Package as optimization result
    output = grid_results_to_dict(results, swept_params=swept_params)
    output["run_type"] = "lhs"
    output["date_start"] = str(df.index.min().date()) if len(df) > 0 else ""
    output["date_end"] = str(df.index.max().date()) if len(df) > 0 else ""

    result_id = save_optimization_result(output)
    if not args.quiet:
        # Print top results
        valid = [r for r in output["all_results"] if r["summary"]["total_trades"] > 0]
        if valid:
            top = sorted(valid, key=lambda r: r["summary"]["sharpe_ratio"], reverse=True)[:5]
            print(f"Top 5 by Sharpe:")
            for r in top:
                s = r["summary"]
                c = r["config"]
                param_str = ", ".join(f"{p.name}={c.get(p.name, '?')}" for p in params)
                print(
                    f"  {param_str} | Sharpe={s['sharpe_ratio']:.3f} | "
                    f"PnL=${s['total_pnl_usd']:,.0f} | PF={s['profit_factor']:.2f}"
                )
            print()

        print(f"Results saved: {result_id}")
        print("View in dashboard → Optimizations tab")


def _run_backtest(args):
    """Run a fresh backtest and return trades."""
    instrument = get_instrument(args.instrument)
    sessions = tuple(SESSION_MAP[s.strip()] for s in args.sessions.split(","))
    config = default_config(instrument)
    config = with_overrides(config, sessions=sessions)

    if not args.quiet:
        print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    if not args.quiet:
        print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time() - t0:.1f}s]")

    if not args.quiet:
        print("Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, config, start_date=args.start)
    if not args.quiet:
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"  {len(trades)} signals, {len(filled)} filled trades [{time.time() - t0:.1f}s]")

    return trades


def _reconstruct_trades(trades_dicts: list[dict]):
    """Reconstruct TradeResult objects from saved JSON trade dicts."""
    from orb_backtest.engine.simulator import TradeResult

    EXIT_NAME_TO_INT = {
        "no_fill": 0, "sl": 1, "tp1_tp2": 2, "tp1_be": 3,
        "tp1_eod": 4, "eod": 5, "tp2_single": 6,
    }

    results = []
    for t in trades_dicts:
        exit_type = t.get("exit_type", "no_fill")
        if isinstance(exit_type, str):
            exit_type = EXIT_NAME_TO_INT.get(exit_type, 0)

        results.append(TradeResult(
            date=t.get("date", ""),
            session=t.get("session", ""),
            direction=1 if t.get("direction") == "long" else -1,
            signal_bar=0,
            fill_bar=0 if exit_type != 0 else -1,
            entry_price=t.get("entry_price", 0.0),
            stop_price=t.get("stop_price", 0.0),
            tp1_price=t.get("tp1_price", 0.0),
            tp2_price=t.get("tp2_price", 0.0),
            exit_type=exit_type,
            exit_bar=0,
            pnl_points=t.get("pnl_points", 0.0),
            pnl_usd=t.get("pnl_usd", 0.0),
            r_multiple=t.get("r_multiple", 0.0),
            qty=t.get("qty", 0.0),
            half_qty=0.0,
            gap_size=t.get("gap_size", 0.0),
            risk_points=t.get("risk_points", 0.0),
            fill_time=t.get("fill_time", ""),
            exit_time=t.get("exit_time", ""),
        ))
    return results


def _get_session_param(config, param_name: str) -> float:
    """Extract session-prefixed param from config (e.g. ny_stop_atr_pct)."""
    for sess in config.sessions:
        prefix = sess.name.lower() + "_"
        if param_name.startswith(prefix):
            attr = param_name[len(prefix):]
            return getattr(sess, attr, 0.0)
    return 0.0


def _print_mc_summary(result):
    """Print Monte Carlo summary table."""
    print("=" * 60)
    print(f"MONTE CARLO RESULTS ({result.method}, {result.n_simulations:,} sims)")
    print("=" * 60)
    print(f"  Trades: {result.n_trades}")
    print()

    # Final PnL percentiles
    p = result.final_pnl_percentiles
    print(f"  Final PnL (R-multiples):")
    print(f"    5th:    {p['p5']:>8.2f}R")
    print(f"    25th:   {p['p25']:>8.2f}R")
    print(f"    50th:   {p['p50']:>8.2f}R  (median)")
    print(f"    75th:   {p['p75']:>8.2f}R")
    print(f"    95th:   {p['p95']:>8.2f}R")
    print(f"    Actual: {result.actual_final_pnl:>8.2f}R")
    print()

    # Max Drawdown percentiles
    p = result.max_dd_percentiles
    print(f"  Max Drawdown (R-multiples):")
    print(f"    5th:    {p['p5']:>8.2f}R  (worst case)")
    print(f"    25th:   {p['p25']:>8.2f}R")
    print(f"    50th:   {p['p50']:>8.2f}R  (median)")
    print(f"    75th:   {p['p75']:>8.2f}R")
    print(f"    95th:   {p['p95']:>8.2f}R  (best case)")
    print(f"    Actual: {result.actual_max_drawdown:>8.2f}R")
    print()

    # Sharpe percentiles
    p = result.sharpe_percentiles
    print(f"  Sharpe Ratio:")
    print(f"    5th:    {p['p5']:>8.3f}")
    print(f"    25th:   {p['p25']:>8.3f}")
    print(f"    50th:   {p['p50']:>8.3f}  (median)")
    print(f"    75th:   {p['p75']:>8.3f}")
    print(f"    95th:   {p['p95']:>8.3f}")
    print(f"    Actual: {result.actual_sharpe:>8.3f}")
    print()

    # Ruin probability
    print(f"  Ruin probability: {result.ruin_probability:.1%}")
    print(f"    (P(max drawdown < {result.ruin_threshold}R))")
    print("=" * 60)


if __name__ == "__main__":
    main()
