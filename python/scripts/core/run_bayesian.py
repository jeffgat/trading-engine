#!/usr/bin/env python3
"""Run Bayesian optimization for ORB+FVG strategy parameters.

Uses a surrogate model (TPE or GP) to efficiently explore the parameter space.
Much more sample-efficient than grid search for high-dimensional spaces.

Results are auto-saved to the experiment DB and viewable in the frontend dashboard.

Usage:
    # Continuous parameter bounds (Optuna explores freely)
    python scripts/run_bayesian.py --data NQ_5m.csv \
        --param rr=1.5:4.0 --param ny_stop_atr_pct=5:25 \
        --n-trials 100

    # Discrete steps (like grid but guided by surrogate model)
    python scripts/run_bayesian.py --data NQ_5m.csv \
        --param rr=1.5:4.0:0.1 --param tp1_ratio=0.2:0.8:0.05 \
        --n-trials 50 --objective sharpe --seed 42

    # With date range and GP sampler
    python scripts/run_bayesian.py --data NQ_5m.csv \
        --start 2024-01-01 --end 2026-01-01 \
        --param rr=1.5:4.0:0.5 --param ny_stop_atr_pct=5:25:1 \
        --n-trials 100 --sampler gp --seed 42
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

try:
    import optuna  # noqa: F401
except ImportError:
    print("Bayesian optimization requires optuna. Install with:")
    print("  uv sync --extra optimize")
    sys.exit(1)

from orb_backtest.config import (
    default_config,
    with_overrides,
    NY_SESSION,
    ASIA_SESSION,
    LDN_SESSION,
)
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.bayesian import (
    parse_bayesian_param,
    run_bayesian,
    BayesianResult,
)
from orb_backtest.optimize.objectives import VALID_OBJECTIVES, OBJECTIVE_MAP
from orb_backtest.results.export import (
    results_to_dict,
    save_optimization_result,
    _trades_to_minimal,
)
from orb_backtest.results.metrics import compute_metrics


def main():
    parser = argparse.ArgumentParser(
        description="Run Bayesian optimization for ORB+FVG strategy"
    )
    parser.add_argument("--data", required=True, help="Data file name or path")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument(
        "--sessions", default="NY", help="Comma-separated: NY,Asia,LDN"
    )
    parser.add_argument(
        "--param",
        action="append",
        required=True,
        help="Parameter bounds: name=low:high or name=low:high:step",
    )
    parser.add_argument(
        "--n-trials", type=int, default=100, help="Number of Bayesian trials"
    )
    parser.add_argument(
        "--objective",
        default="sharpe",
        choices=VALID_OBJECTIVES,
        help="Optimization objective (default: sharpe)",
    )
    parser.add_argument(
        "--sampler",
        default="tpe",
        choices=["tpe", "gp"],
        help="Sampler: tpe (default) or gp",
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed")
    parser.add_argument("--name", default=None, help="Label for this run")
    parser.add_argument("--strategy", default=None, choices=["continuation", "reversal"],
                        help="Strategy type: continuation (default) or reversal")

    args = parser.parse_args()

    # Parse parameter definitions
    params = [parse_bayesian_param(spec) for spec in args.param]

    # Build base config
    instrument = get_instrument(args.instrument)
    session_map = {"NY": NY_SESSION, "Asia": ASIA_SESSION, "LDN": LDN_SESSION}
    sessions = tuple(session_map[s.strip()] for s in args.sessions.split(","))
    base_config = default_config(instrument)
    base_config = with_overrides(base_config, sessions=sessions)
    if args.strategy:
        base_config = with_overrides(base_config, strategy=args.strategy)

    # Print header
    sampler_name = {"tpe": "TPE", "gp": "Gaussian Process"}[args.sampler]
    print(f"Bayesian Optimization ({sampler_name})")
    print(f"  Objective: {args.objective} | Trials: {args.n_trials}")
    if args.seed is not None:
        print(f"  Seed: {args.seed}")
    print(f"  Parameters:")
    for p in params:
        step_str = f" step={p.step}" if p.step else " continuous"
        print(f"    {p.name}: [{p.low}, {p.high}]{step_str}")
    print()

    # Load data
    print(f"Loading data: {args.data}")
    t0 = time.time()
    df = load_5m_data(args.data, start=args.start, end=args.end)
    t_load = time.time() - t0
    print(
        f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) "
        f"[{t_load:.1f}s]"
    )
    print()

    # Run Bayesian optimization
    print(f"Running {args.n_trials} Bayesian trials...")
    t0 = time.time()

    def progress_fn(trial_num, total, best_val, trial_params):
        elapsed = time.time() - t0
        rate = trial_num / elapsed if elapsed > 0 else 0
        param_str = ", ".join(f"{k}={v:.2f}" for k, v in trial_params.items())

        # Get the latest trial's objective value
        latest_val = best_val  # Will be updated by the callback
        marker = ""
        # Check if this trial improved the best
        if trial_num == 1 or best_val > getattr(progress_fn, "_prev_best", float("-inf")):
            if hasattr(progress_fn, "_prev_best") and best_val > progress_fn._prev_best:
                marker = " ***"
            progress_fn._prev_best = best_val

        print(
            f"\r  Trial {trial_num:>{len(str(total))}}/{total} | "
            f"{param_str} | best {args.objective}: {best_val:.3f}{marker} | "
            f"{rate:.1f}/s"
            "          ",
            end="",
            flush=True,
        )

    progress_fn._prev_best = float("-inf")

    result = run_bayesian(
        df,
        base_config,
        params,
        n_trials=args.n_trials,
        objective=args.objective,
        sampler=args.sampler,
        start_date=args.start,
        seed=args.seed,
        progress_fn=progress_fn,
    )

    t_total = time.time() - t0
    print(f"\n  Completed in {t_total:.1f}s ({args.n_trials / t_total:.1f} trials/s)")
    print()

    # Print best trial
    best = result.best_trial
    risk_usd = base_config.risk_usd
    print(f"Best Trial (#{best.trial_number}):")
    for k, v in best.params.items():
        print(f"  {k} = {v:.4g}")
    m = best.metrics
    print(f"  Trades: {m['total_trades']} | Win rate: {m['win_rate']:.1%}")
    print(f"  PnL: ${m['total_pnl_usd']:,.2f} ({m['total_pnl_usd'] / risk_usd:.1f}R) | PF: {m['profit_factor']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f} | Max DD: ${m['max_drawdown_usd']:,.2f} ({m['max_drawdown_usd'] / risk_usd:.1f}R)")
    print(f"  Avg R: {m['avg_r']:.3f}")
    print()

    # Print top 5 trials
    obj_key = OBJECTIVE_MAP[args.objective]
    valid_trials = [t for t in result.trials if t.metrics["total_trades"] > 0]
    top_5 = sorted(valid_trials, key=lambda t: t.objective_value, reverse=True)[:5]

    print(f"Top 5 trials by {args.objective}:")
    for t in top_5:
        param_str = ", ".join(f"{k}={v:.2f}" for k, v in t.params.items())
        print(
            f"  #{t.trial_number:<4d} {param_str} | "
            f"{args.objective}={t.objective_value:.3f} | "
            f"PnL=${t.metrics['total_pnl_usd']:,.0f} | "
            f"PF={t.metrics['profit_factor']:.2f}"
        )
    print()

    # Save results
    output = _build_output(result, base_config, args)
    result_id = save_optimization_result(output)
    print(f"Results saved: {result_id}")
    print("View in dashboard → Optimizations tab")


def _build_output(result: BayesianResult, base_config, args) -> dict:
    """Build frontend-compatible output dict from BayesianResult."""
    # Build all_results: one entry per trial
    all_results = []
    trades_by_combo = []
    for trial in result.trials:
        trial_dict = results_to_dict([], trial.config, include_trades=False)
        trial_dict["summary"] = trial.metrics
        all_results.append(trial_dict)
        # No individual trades stored for Bayesian (too many trials)
        trades_by_combo.append([])

    # Build swept_params from unique values tried
    swept_params = {}
    for p in result.param_definitions:
        values = sorted(set(t.params[p.name] for t in result.trials))
        swept_params[p.name] = [float(v) for v in values]

    # Best by different metrics
    valid = [r for r in all_results if r["summary"]["total_trades"] > 0]
    best_by_sharpe = max(valid, key=lambda r: r["summary"]["sharpe_ratio"]) if valid else None
    best_by_pnl = max(valid, key=lambda r: r["summary"]["total_pnl_usd"]) if valid else None
    best_by_pf = max(valid, key=lambda r: r["summary"]["profit_factor"]) if valid else None
    best_by_calmar = max(valid, key=lambda r: r["summary"].get("calmar_ratio", 0)) if valid else None

    # Build convergence curve
    best_so_far = float("-inf")
    convergence = []
    for trial in result.trials:
        val = trial.objective_value
        best_so_far = max(best_so_far, val)
        convergence.append({
            "trial": trial.trial_number,
            "value": round(val, 4),
            "best_so_far": round(best_so_far, 4),
        })

    output = {
        "total_combinations": result.n_trials,
        "swept_params": swept_params,
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "best_by_calmar": best_by_calmar,
        "all_results": all_results,
        "trades_by_combo": trades_by_combo,
        "run_type": "bayesian",
        "bayesian": {
            "sampler": result.sampler,
            "objective": result.objective,
            "n_trials": result.n_trials,
            "seed": args.seed,
            "param_definitions": [
                {
                    "name": p.name,
                    "low": p.low,
                    "high": p.high,
                    "step": p.step,
                }
                for p in result.param_definitions
            ],
            "convergence": convergence,
        },
    }

    if args.name:
        output["name"] = args.name

    return output


if __name__ == "__main__":
    main()
