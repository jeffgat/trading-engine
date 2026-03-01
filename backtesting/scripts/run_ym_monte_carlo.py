#!/usr/bin/env python3
"""Monte Carlo stress test for YM NY WF-validated candidates.

Runs bootstrap (luck variance) and shuffle (path dependency) with 10,000 sims each.
Ruin thresholds: -8R (prop firm breach) and -10R (hard ceiling).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.simulate.monte_carlo import (
    MonteCarloConfig,
    run_monte_carlo,
)


def make_config(entry_end):
    instrument = get_instrument("YM")
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=1.5,
    )
    return StrategyConfig(
        rr=4.0,
        tp1_ratio=0.55,
        atr_length=10,
        sessions=(session,),
        instrument=instrument,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def print_mc_result(name, result, ruin_8r_prob):
    """Print a formatted Monte Carlo summary."""
    print(f"\n  {name}")
    print(f"  {'─' * 60}")
    print(f"  Method:       {result.method} ({result.n_simulations:,} sims, {result.n_trades} trades)")
    print()
    print(f"  {'Metric':<20s} | {'Actual':>8} | {'p5':>8} {'p25':>8} {'p50':>8} {'p75':>8} {'p95':>8}")
    print(f"  {'-'*20}-+-{'-'*8}-+-{'-'*8}-{'-'*8}-{'-'*8}-{'-'*8}-{'-'*8}")
    print(
        f"  {'Final PnL (R)':<20s} | {result.actual_final_pnl:>8.1f} | "
        f"{result.final_pnl_percentiles['p5']:>8.1f} "
        f"{result.final_pnl_percentiles['p25']:>8.1f} "
        f"{result.final_pnl_percentiles['p50']:>8.1f} "
        f"{result.final_pnl_percentiles['p75']:>8.1f} "
        f"{result.final_pnl_percentiles['p95']:>8.1f}"
    )
    print(
        f"  {'Max Drawdown (R)':<20s} | {result.actual_max_drawdown:>8.1f} | "
        f"{result.max_dd_percentiles['p5']:>8.1f} "
        f"{result.max_dd_percentiles['p25']:>8.1f} "
        f"{result.max_dd_percentiles['p50']:>8.1f} "
        f"{result.max_dd_percentiles['p75']:>8.1f} "
        f"{result.max_dd_percentiles['p95']:>8.1f}"
    )
    print(
        f"  {'Sharpe':<20s} | {result.actual_sharpe:>8.2f} | "
        f"{result.sharpe_percentiles['p5']:>8.2f} "
        f"{result.sharpe_percentiles['p25']:>8.2f} "
        f"{result.sharpe_percentiles['p50']:>8.2f} "
        f"{result.sharpe_percentiles['p75']:>8.2f} "
        f"{result.sharpe_percentiles['p95']:>8.2f}"
    )
    print()
    print(f"  Ruin probability (>{abs(result.ruin_threshold):.0f}R DD):  {result.ruin_probability:.1%}")
    print(f"  Ruin probability (>8R DD):    {ruin_8r_prob:.1%}")


def main():
    import numpy as np

    print("=" * 70)
    print("YM NY MONTE CARLO STRESS TEST")
    print("=" * 70)

    print("\nLoading YM data...")
    t0 = time.time()
    df = load_5m_data("YM_5m.csv")
    print(f"  {len(df):,} bars [{time.time()-t0:.1f}s]")

    candidates = [
        ("5m ORB + 11:30 + ATR10", make_config("11:30")),
        ("5m ORB + 13:00 + ATR10", make_config("13:00")),
    ]

    for name, cfg in candidates:
        print(f"\n{'=' * 70}")
        print(f"CANDIDATE: {name}")
        print("=" * 70)

        trades = run_backtest(df, cfg, start_date="2016-03-01")
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        print(f"  {len(filled)} filled trades")

        for method in ["bootstrap", "shuffle"]:
            mc_cfg = MonteCarloConfig(
                n_simulations=10000,
                method=method,
                seed=42,
            )

            t1 = time.time()
            # Run with -10R ruin threshold
            result = run_monte_carlo(trades, mc_cfg, ruin_threshold=-10.0)

            # Also compute 8R ruin probability
            r_multiples = np.array([t.r_multiple for t in filled])
            rng = np.random.default_rng(42)
            n_sims = 10000
            ruin_8r_count = 0
            for i in range(n_sims):
                if method == "bootstrap":
                    idx = rng.integers(0, len(r_multiples), size=len(r_multiples))
                    sim_r = r_multiples[idx]
                else:
                    sim_r = rng.permutation(r_multiples)
                eq = np.cumsum(sim_r)
                peak = np.maximum.accumulate(eq)
                dd = eq - peak
                if np.min(dd) < -8.0:
                    ruin_8r_count += 1
            ruin_8r_prob = ruin_8r_count / n_sims

            elapsed = time.time() - t1
            print_mc_result(f"{method.upper()} ({elapsed:.1f}s)", result, ruin_8r_prob)

    print(f"\n{'=' * 70}")
    print("Done!")


if __name__ == "__main__":
    main()
