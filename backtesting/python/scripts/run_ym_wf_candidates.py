#!/usr/bin/env python3
"""Walk-forward validation of 5 YM NY candidate configs.

Candidates:
1. 5m ORB + 11:30 cutoff + ATR=10  (all findings combined)
2. 5m ORB + 13:00 cutoff + ATR=10  (without entry cutoff change)
3. 15m ORB + 11:30 cutoff + ATR=10 (without ORB change)
4. 15m ORB + 13:00 cutoff + ATR=10 (ATR change only)
5. 15m ORB + 13:00 cutoff + ATR=14 (baseline control)

Each fold sweeps: ny_stop_atr_pct, ny_min_gap_atr_pct, rr
WF settings: 12m IS, 3m OOS, 3m step, rolling, sharpe objective
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.objectives import OBJECTIVE_MAP
from orb_backtest.results.export import (
    results_to_dict,
    save_optimization_result,
    _trades_to_minimal,
)

# --- Candidate definitions ---

def make_config(orb_end, entry_start, entry_end, atr_length):
    """Build a StrategyConfig for YM NY with specified structural params."""
    instrument = get_instrument("YM")
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=orb_end,
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        # Defaults — will be overridden by sweep
        stop_atr_pct=4.0,
        min_gap_atr_pct=1.5,
    )
    return StrategyConfig(
        rr=4.0,  # swept
        tp1_ratio=0.55,
        atr_length=atr_length,
        sessions=(session,),
        instrument=instrument,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


CANDIDATES = [
    ("5m ORB + 11:30 + ATR10", make_config("09:35", "09:35", "11:30", 10)),
    ("5m ORB + 13:00 + ATR10", make_config("09:35", "09:35", "13:00", 10)),
    ("15m ORB + 11:30 + ATR10", make_config("09:45", "09:45", "11:30", 10)),
    ("15m ORB + 13:00 + ATR10", make_config("09:45", "09:45", "13:00", 10)),
    ("15m ORB + 13:00 + ATR14 (baseline)", make_config("09:45", "09:45", "13:00", 14)),
]

# Sweep ranges within each fold
PARAM_RANGES = {
    "rr": [3.5, 4.0, 4.5],
    "ny_stop_atr_pct": [3.5, 4.0, 4.5, 5.0],
    "ny_min_gap_atr_pct": [1.0, 1.25, 1.5, 1.75, 2.0],
}

# WF settings
IS_MONTHS = 12
OOS_MONTHS = 3
STEP_MONTHS = 3
OBJECTIVE = "sharpe"
N_WORKERS = 8


def run_candidate(name, base_config, df):
    """Run walk-forward for a single candidate and return the result."""
    grid_size = 1
    for v in PARAM_RANGES.values():
        grid_size *= len(v)

    global_t0 = time.time()

    def progress_fn(fold_idx, total_folds, status):
        elapsed = time.time() - global_t0
        if status == "done":
            print(
                f"\r  Fold {fold_idx + 1}/{total_folds}: done [{elapsed:.0f}s]"
                "                              ",
                end="\n",
                flush=True,
            )
        else:
            print(
                f"\r  Fold {fold_idx + 1}/{total_folds}: {status} ({grid_size} combos)"
                "                    ",
                end="",
                flush=True,
            )

    result = run_walkforward(
        df,
        base_config,
        PARAM_RANGES,
        is_months=IS_MONTHS,
        oos_months=OOS_MONTHS,
        step_months=STEP_MONTHS,
        anchored=False,
        objective=OBJECTIVE,
        n_workers=N_WORKERS,
        start_date="2016-03-01",
        progress_fn=progress_fn,
    )
    elapsed = time.time() - global_t0
    return result, elapsed


def print_fold_table(result, param_ranges):
    """Print per-fold summary."""
    param_cols = list(param_ranges.keys())
    param_header = " | ".join(f"{p:>10s}" for p in param_cols)
    print(
        f"  {'Fold':>4s} | {'IS Period':<23s} | {'OOS Period':<23s} | "
        f"{'IS Sharpe':>10s} | {'OOS Sharpe':>10s} | "
        f"{'OOS Trd':>7s} | {'Eff':>5s} | {param_header}"
    )
    print("  " + "-" * (85 + 13 * len(param_cols)))

    for fold in result.folds:
        is_period = f"{fold.is_start[:7]} -> {fold.is_end[:7]}"
        oos_period = f"{fold.oos_start[:7]} -> {fold.oos_end[:7]}"
        eff = fold.oos_objective_value / fold.is_objective_value if fold.is_objective_value else 0
        oos_trades = fold.oos_metrics["total_trades"]
        param_vals = " | ".join(
            f"{fold.best_params.get(p, 0):>10.2f}" for p in param_cols
        )
        print(
            f"  {fold.fold_index + 1:>4d} | {is_period:<23s} | {oos_period:<23s} | "
            f"{fold.is_objective_value:>10.3f} | {fold.oos_objective_value:>10.3f} | "
            f"{oos_trades:>7d} | {eff:>5.2f} | {param_vals}"
        )


def print_combined_summary(name, result, elapsed):
    """Print combined OOS summary for a candidate."""
    m = result.combined_oos_metrics
    risk_usd = 5000.0
    dd_r = abs(m["max_drawdown_usd"]) / risk_usd

    import datetime
    total_oos_days = sum(
        (datetime.datetime.strptime(f.oos_end, "%Y-%m-%d")
         - datetime.datetime.strptime(f.oos_start, "%Y-%m-%d")).days
        for f in result.folds
    )
    oos_years = total_oos_days / 365.25
    total_r = m["total_pnl_usd"] / risk_usd
    r_per_year = total_r / oos_years if oos_years > 0 else 0

    print(f"  Combined OOS ({oos_years:.1f} years, {len(result.folds)} folds):")
    print(f"    Trades:        {m['total_trades']}")
    print(f"    Win rate:      {m['win_rate']:.1%}")
    print(f"    Total PnL:     ${m['total_pnl_usd']:,.0f} ({total_r:.1f}R)")
    print(f"    R/year:        {r_per_year:.1f}")
    print(f"    Sharpe:        {m['sharpe_ratio']:.3f}")
    print(f"    Sortino:       {m['sortino_ratio']:.3f}")
    print(f"    Calmar:        {m['calmar_ratio']:.2f}")
    print(f"    Profit factor: {m['profit_factor']:.2f}")
    print(f"    Max drawdown:  ${m['max_drawdown_usd']:,.0f} ({dd_r:.1f}R)")
    print(f"    Avg R:         {m['avg_r']:.3f}")
    print(f"    WF Efficiency: {result.walk_forward_efficiency:.2f}")
    print(f"    Runtime:       {elapsed:.0f}s")


def main():
    print("=" * 80)
    print("YM NY WALK-FORWARD VALIDATION — 5 CANDIDATES")
    print("=" * 80)
    print(f"  IS: {IS_MONTHS}m | OOS: {OOS_MONTHS}m | Step: {STEP_MONTHS}m | Objective: {OBJECTIVE}")
    grid_size = 1
    for v in PARAM_RANGES.values():
        grid_size *= len(v)
    print(f"  Sweep: {grid_size} combos/fold")
    print(f"  Swept params: {list(PARAM_RANGES.keys())}")
    print()

    # Load data once
    print("Loading YM data...")
    t0 = time.time()
    df = load_5m_data("YM_5m.csv")
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()}) [{time.time()-t0:.1f}s]")
    print()

    all_results = []

    for i, (name, base_config) in enumerate(CANDIDATES):
        print("=" * 80)
        print(f"CANDIDATE {i+1}/5: {name}")
        print("=" * 80)
        print()

        result, elapsed = run_candidate(name, base_config, df)
        all_results.append((name, result, elapsed))

        print()
        print_fold_table(result, PARAM_RANGES)
        print()
        print_combined_summary(name, result, elapsed)
        print()

    # Final comparison table
    print()
    print("=" * 80)
    print("FINAL COMPARISON — ALL CANDIDATES")
    print("=" * 80)
    print()
    print(f"  {'Candidate':<35s} | {'Sharpe':>7} {'Sortino':>8} {'Calmar':>7} | {'PnL':>10} {'DD(R)':>6} {'PF':>5} {'WR':>6} {'Trd':>5} {'AvgR':>6} | {'WF Eff':>7}")
    print("  " + "-" * 120)

    for name, result, elapsed in all_results:
        m = result.combined_oos_metrics
        dd_r = abs(m["max_drawdown_usd"]) / 5000
        total_r = m["total_pnl_usd"] / 5000
        print(
            f"  {name:<35s} | {m['sharpe_ratio']:7.3f} {m['sortino_ratio']:8.3f} {m['calmar_ratio']:7.2f} | "
            f"{total_r:>9.1f}R {dd_r:6.1f} {m['profit_factor']:5.2f} {m['win_rate']:5.1f}% {m['total_trades']:5d} {m['avg_r']:6.3f} | "
            f"{result.walk_forward_efficiency:7.2f}"
        )

    print()
    print("Done!")


if __name__ == "__main__":
    main()
