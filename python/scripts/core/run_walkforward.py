#!/usr/bin/env python3
"""Run walk-forward optimization to validate parameter stability.

Splits data into rolling in-sample (IS) and out-of-sample (OOS) windows.
Optimizes on IS, tests on OOS, rolls forward. Combines all OOS results
to measure true out-of-sample performance.

Optionally applies an SMA trend gate (with-trend filter) and runs
Monte Carlo simulation on the combined OOS trades.

Results are auto-saved to the experiment DB and viewable in the frontend dashboard.

Usage:
    # Basic walk-forward with 12m IS, 3m OOS, stepping 3m
    python scripts/core/run_walkforward.py --data NQ_5m.csv \
        --start 2020-01-01 --end 2026-01-01 \
        --sweep rr=2.0:3.5:0.5 --sweep ny_stop_atr_pct=5:20:5

    # CL with SMA20 gate, 24m IS, 6m OOS
    python scripts/core/run_walkforward.py --data CL_5m.csv --instrument CL --sessions NY \
        --start 2015-01-01 --end 2026-02-15 \
        --is-months 24 --oos-months 6 --step-months 6 \
        --objective sharpe --sma-gate 20 --workers 8 \
        --sweep rr=2.5:4.5:0.5 \
        --sweep tp1_ratio=0.5:0.75:0.05 \
        --sweep ny_stop_atr_pct=1.5:3.5:0.5 \
        --sweep ny_min_gap_atr_pct=2.0:4.0:0.5 \
        --name "CL WF: 24m IS, 6m OOS, SMA20 gate"
"""

import argparse
import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from orb_backtest.config import (
    default_config,
    with_overrides,
    NY_SESSION,
    ASIA_SESSION,
    LDN_SESSION,
)
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import linspace_range, describe_grid
from orb_backtest.optimize.objectives import OBJECTIVE_MAP, VALID_OBJECTIVES
from orb_backtest.optimize.walkforward import run_walkforward, generate_windows
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import (
    results_to_dict,
    save_optimization_result,
    _trades_to_minimal,
)


def parse_sweep(spec: str) -> tuple[str, list[float]]:
    """Parse sweep spec like 'rr=1.5:4.0:0.5' into (name, values)."""
    name, range_str = spec.split("=", 1)
    parts = range_str.split(":")
    if len(parts) == 3:
        start, stop, step = float(parts[0]), float(parts[1]), float(parts[2])
        return name, linspace_range(start, stop, step)
    else:
        return name, [float(v) for v in range_str.split(",")]


def main():
    parser = argparse.ArgumentParser(
        description="Run walk-forward optimization for ORB+FVG strategy"
    )
    parser.add_argument("--data", required=True, help="Data file name or path")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--instrument", default="NQ", help="Instrument symbol")
    parser.add_argument(
        "--sessions", default="NY", help="Comma-separated: NY,Asia,LDN"
    )
    parser.add_argument(
        "--sweep",
        action="append",
        required=True,
        help="Parameter sweep spec: name=start:stop:step or name=v1,v2,v3",
    )
    parser.add_argument(
        "--workers", type=int, default=None, help="Number of parallel workers"
    )
    parser.add_argument("--name", default=None, help="Label for this run")

    # Walk-forward specific
    parser.add_argument(
        "--is-months", type=int, default=12, help="In-sample window (months)"
    )
    parser.add_argument(
        "--oos-months", type=int, default=3, help="Out-of-sample window (months)"
    )
    parser.add_argument(
        "--step-months", type=int, default=3, help="Roll-forward step (months)"
    )
    parser.add_argument(
        "--anchored",
        action="store_true",
        help="Use anchored (expanding) IS window",
    )
    parser.add_argument(
        "--objective",
        default="sharpe",
        choices=VALID_OBJECTIVES,
        help="Optimization objective (default: sharpe)",
    )
    parser.add_argument(
        "--sma-gate",
        type=int,
        default=None,
        metavar="PERIOD",
        help="Apply SMA trend gate (with-trend filter) using this SMA period",
    )
    parser.add_argument(
        "--mc-sims",
        type=int,
        default=10000,
        help="Monte Carlo simulations on combined OOS (0 to skip, default: 10000)",
    )

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

    # Print header
    mode = "Anchored" if args.anchored else "Rolling"
    print("Walk-Forward Optimization")
    print(
        f"  IS: {args.is_months} months | OOS: {args.oos_months} months | "
        f"Step: {args.step_months} months | Mode: {mode}"
    )
    print(f"  Objective: {args.objective}")
    if args.sma_gate:
        print(f"  SMA Gate: {args.sma_gate}-period with-trend filter")
    print()
    print(describe_grid(param_ranges))
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

    # Create gate_factory if --sma-gate specified
    gate_factory = None
    if args.sma_gate:
        print(f"Using SMA({args.sma_gate}) with-trend gate")
        from orb_backtest.analysis.gates import create_sma_gate_factory
        gate_factory = create_sma_gate_factory(sma_period=args.sma_gate)
        print()

    # Preview folds
    wf_start = args.start or df.index[0].strftime("%Y-%m-%d")
    data_end = df.index[-1].strftime("%Y-%m-%d")
    windows = generate_windows(
        wf_start, data_end, args.is_months, args.oos_months,
        args.step_months, args.anchored,
    )
    print(f"Generated {len(windows)} walk-forward folds")
    print()

    if not windows:
        print("ERROR: No valid folds. Data range too short for the specified windows.")
        sys.exit(1)

    # Run walk-forward
    t0 = time.time()

    try:
        result = run_walkforward(
            df,
            base_config,
            param_ranges,
            is_months=args.is_months,
            oos_months=args.oos_months,
            step_months=args.step_months,
            anchored=args.anchored,
            objective=args.objective,
            n_workers=args.workers,
            start_date=args.start,
            progress_fn=_make_fold_progress(t0, param_ranges),
            gate_factory=gate_factory,
        )
    except ValueError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    t_total = time.time() - t0
    print(f"\n  Completed in {t_total:.1f}s")
    print()

    # Print per-fold summary table
    obj_key = OBJECTIVE_MAP[args.objective]
    print("=" * 90)
    print("WALK-FORWARD RESULTS")
    print("=" * 90)
    print()

    # Fold table header
    param_cols = list(param_ranges.keys())
    param_header = " | ".join(f"{p:>12s}" for p in param_cols)
    print(
        f"  {'Fold':>4s} | {'IS Period':<23s} | {'OOS Period':<23s} | "
        f"{'IS ' + args.objective:>12s} | {'OOS ' + args.objective:>12s} | "
        f"{'OOS Trades':>10s} | {'Efficiency':>10s} | {param_header}"
    )
    print("  " + "-" * (88 + 15 * len(param_cols)))

    for fold in result.folds:
        is_period = f"{fold.is_start[:7]} → {fold.is_end[:7]}"
        oos_period = f"{fold.oos_start[:7]} → {fold.oos_end[:7]}"
        is_val = fold.is_objective_value
        oos_val = fold.oos_objective_value
        eff = oos_val / is_val if is_val != 0 else 0
        oos_trades = fold.oos_metrics["total_trades"]
        param_vals = " | ".join(
            f"{fold.best_params.get(p, 0):>12.2f}" for p in param_cols
        )
        print(
            f"  {fold.fold_index + 1:>4d} | {is_period:<23s} | {oos_period:<23s} | "
            f"{is_val:>12.3f} | {oos_val:>12.3f} | "
            f"{oos_trades:>10d} | {eff:>10.2f} | {param_vals}"
        )

    print()

    # Combined OOS summary
    m = result.combined_oos_metrics
    risk_usd = base_config.risk_usd
    n_folds = len(result.folds)
    total_oos_days = sum(
        (
            datetime.datetime.strptime(f.oos_end, "%Y-%m-%d")
            - datetime.datetime.strptime(f.oos_start, "%Y-%m-%d")
        ).days
        for f in result.folds
    )
    oos_years = total_oos_days / 365.25
    r_per_year = (m["total_pnl_usd"] / risk_usd) / oos_years if oos_years > 0 else 0

    print(f"  Combined OOS Performance:")
    print(f"    Folds completed:     {n_folds}")
    print(f"    Combined OOS trades: {m['total_trades']}")
    print(f"    OOS span:            {oos_years:.1f} years")
    print(f"    Win rate:            {m['win_rate']:.1%}")
    print(f"    Total PnL:           ${m['total_pnl_usd']:,.2f} ({m['total_pnl_usd'] / risk_usd:.1f}R)")
    print(f"    R/year:              {r_per_year:.1f}")
    print(f"    Profit factor:       {m['profit_factor']:.2f}")
    print(f"    Sharpe ratio:        {m['sharpe_ratio']:.3f}")
    print(f"    Sortino ratio:       {m['sortino_ratio']:.3f}")
    print(f"    Calmar ratio:        {m['calmar_ratio']:.2f}")
    print(f"    Max drawdown:        ${m['max_drawdown_usd']:,.2f} ({m['max_drawdown_usd'] / risk_usd:.1f}R)")
    print(f"    Avg R:               {m['avg_r']:.3f}")
    print()
    print(f"  Walk-Forward Efficiency: {result.walk_forward_efficiency:.2f}")
    print(f"    (avg OOS {args.objective} / avg IS {args.objective})")
    print()

    # Save results
    output = _build_output(result, param_ranges, base_config, args)
    result_id = save_optimization_result(output)
    print(f"Results saved: {result_id}")
    print("View in dashboard -> Optimizations tab")
    print()

    # Monte Carlo on combined OOS trades
    if args.mc_sims > 0 and m["total_trades"] > 0:
        _run_monte_carlo(result.combined_oos_trades, args.mc_sims, risk_usd)


def _run_monte_carlo(trades, n_sims, risk_usd):
    """Run bootstrap Monte Carlo on combined OOS trades and print results."""
    from orb_backtest.engine.simulator import EXIT_NO_FILL

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if len(filled) < 10:
        print("Skipping Monte Carlo: too few OOS trades for meaningful bootstrap")
        return

    r_multiples = np.array([t.r_multiple for t in filled])
    n_trades = len(r_multiples)
    rng = np.random.default_rng(42)

    print(f"Running Monte Carlo ({n_sims:,} bootstrap paths, {n_trades} trades)...")
    t0 = time.time()

    # Bootstrap: resample with replacement
    indices = rng.integers(0, n_trades, size=(n_sims, n_trades))
    paths = r_multiples[indices]

    # Cumulative equity per path
    equity = np.cumsum(paths, axis=1)
    final_pnl = equity[:, -1]

    # Max drawdown per path
    running_max = np.maximum.accumulate(equity, axis=1)
    drawdowns = equity - running_max
    max_dd = np.min(drawdowns, axis=1)

    # Sharpe per path
    mean_r = np.mean(paths, axis=1)
    std_r = np.std(paths, axis=1, ddof=1)
    sharpe = np.where(std_r > 0, mean_r / std_r * np.sqrt(252), 0.0)

    t_mc = time.time() - t0

    # Actual values
    actual_equity = np.cumsum(r_multiples)
    actual_final = actual_equity[-1]
    actual_peak = np.maximum.accumulate(actual_equity)
    actual_dd = float(np.min(actual_equity - actual_peak))
    actual_std = float(np.std(r_multiples, ddof=1))
    actual_sharpe = (
        float(np.mean(r_multiples)) / actual_std * np.sqrt(252)
        if actual_std > 0 else 0.0
    )

    # Ruin probability (DD below -8R)
    ruin_threshold = -8.0
    ruin_prob = float(np.mean(max_dd < ruin_threshold))

    print(f"  Completed in {t_mc:.1f}s")
    print()
    print("=" * 60)
    print(f"MONTE CARLO RESULTS (bootstrap, {n_sims:,} sims)")
    print("=" * 60)
    print(f"  Trades: {n_trades}")
    print()

    def _pct(arr, p):
        return float(np.percentile(arr, p))

    print(f"  Final PnL (R-multiples):")
    print(f"    5th:    {_pct(final_pnl, 5):>8.2f}R")
    print(f"    25th:   {_pct(final_pnl, 25):>8.2f}R")
    print(f"    50th:   {_pct(final_pnl, 50):>8.2f}R  (median)")
    print(f"    75th:   {_pct(final_pnl, 75):>8.2f}R")
    print(f"    95th:   {_pct(final_pnl, 95):>8.2f}R")
    print(f"    Actual: {actual_final:>8.2f}R")
    print()

    print(f"  Max Drawdown (R-multiples):")
    print(f"    5th:    {_pct(max_dd, 5):>8.2f}R  (worst case)")
    print(f"    25th:   {_pct(max_dd, 25):>8.2f}R")
    print(f"    50th:   {_pct(max_dd, 50):>8.2f}R  (median)")
    print(f"    75th:   {_pct(max_dd, 75):>8.2f}R")
    print(f"    95th:   {_pct(max_dd, 95):>8.2f}R  (best case)")
    print(f"    Actual: {actual_dd:>8.2f}R")
    print()

    print(f"  Sharpe Ratio:")
    print(f"    5th:    {_pct(sharpe, 5):>8.3f}")
    print(f"    25th:   {_pct(sharpe, 25):>8.3f}")
    print(f"    50th:   {_pct(sharpe, 50):>8.3f}  (median)")
    print(f"    75th:   {_pct(sharpe, 75):>8.3f}")
    print(f"    95th:   {_pct(sharpe, 95):>8.3f}")
    print(f"    Actual: {actual_sharpe:>8.3f}")
    print()

    print(f"  Ruin probability: {ruin_prob:.1%}")
    print(f"    (P(max drawdown < {ruin_threshold}R))")
    print("=" * 60)


def _make_fold_progress(global_t0, param_ranges):
    """Create a progress callback that prints fold-level progress."""
    grid_size = 1
    for v in param_ranges.values():
        grid_size *= len(v)

    def progress_fn(fold_idx, total_folds, status):
        elapsed = time.time() - global_t0
        if status == "done":
            print(
                f"\r  Fold {fold_idx + 1}/{total_folds}: done"
                f" [{elapsed:.0f}s elapsed]"
                "                              ",
                end="\n",
                flush=True,
            )
        else:
            print(
                f"\r  Fold {fold_idx + 1}/{total_folds}: {status}"
                f" ({grid_size} combos)"
                "                    ",
                end="",
                flush=True,
            )

    return progress_fn


def _build_output(result, param_ranges, base_config, args) -> dict:
    """Build frontend-compatible output dict from WalkForwardResult."""
    # Combined OOS as the primary result for frontend compatibility
    combined_dict = results_to_dict(
        result.combined_oos_trades, result.folds[0].best_config, include_trades=False
    )

    # Build best_by_* from combined OOS metrics
    best_entry = {
        "config": combined_dict["config"],
        "summary": result.combined_oos_metrics,
    }

    # Build fold details for metadata
    fold_details = []
    for fold in result.folds:
        fold_details.append({
            "fold_index": fold.fold_index,
            "is_start": fold.is_start,
            "is_end": fold.is_end,
            "oos_start": fold.oos_start,
            "oos_end": fold.oos_end,
            "best_params": fold.best_params,
            "is_metrics": fold.is_metrics,
            "oos_metrics": fold.oos_metrics,
            "is_objective_value": fold.is_objective_value,
            "oos_objective_value": fold.oos_objective_value,
        })

    # Build all_results: one entry per fold's OOS
    all_results = []
    trades_by_combo = []
    for fold in result.folds:
        fold_dict = results_to_dict(
            fold.oos_trades, fold.best_config, include_trades=False
        )
        all_results.append(fold_dict)
        trades_by_combo.append(_trades_to_minimal(fold.oos_trades))

    # Determine best_by_* across folds
    filled = [r for r in all_results if r["summary"]["total_trades"] > 0]
    best_by_sharpe = max(filled, key=lambda r: r["summary"]["sharpe_ratio"]) if filled else None
    best_by_pnl = max(filled, key=lambda r: r["summary"]["total_pnl_usd"]) if filled else None
    best_by_pf = max(filled, key=lambda r: r["summary"]["profit_factor"]) if filled else None
    best_by_calmar = max(filled, key=lambda r: r["summary"].get("calmar_ratio", 0)) if filled else None

    output = {
        "total_combinations": len(result.folds),
        "swept_params": {k: [float(v) for v in vs] for k, vs in param_ranges.items()},
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "best_by_calmar": best_by_calmar,
        "all_results": all_results,
        "trades_by_combo": trades_by_combo,
        "date_start": result.folds[0].oos_start if result.folds else "",
        "date_end": result.folds[-1].oos_end if result.folds else "",
        "run_type": "walkforward",
        "walkforward": {
            "is_months": result.is_months,
            "oos_months": result.oos_months,
            "step_months": result.step_months,
            "anchored": result.anchored,
            "objective": result.objective,
            "total_folds": len(result.folds),
            "walk_forward_efficiency": round(result.walk_forward_efficiency, 4),
            "is_avg_objective": round(
                sum(f.is_objective_value for f in result.folds) / len(result.folds), 4
            ),
            "oos_avg_objective": round(
                sum(f.oos_objective_value for f in result.folds) / len(result.folds), 4
            ),
            "combined_oos_metrics": result.combined_oos_metrics,
            "folds": fold_details,
        },
    }

    if args.sma_gate:
        output["walkforward"]["sma_gate"] = args.sma_gate

    if args.name:
        output["name"] = args.name

    return output


if __name__ == "__main__":
    main()
