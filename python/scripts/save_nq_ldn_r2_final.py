#!/usr/bin/env python3
"""Save NQ LDN R2 Final config to DB.

Config: stop=8.0%, rr=2.25, gap=1.5%, tp1=0.6, ORB=15m (03:00-03:15),
        entry≤08:25, flat=08:20, ATR=14, direction=both, ICF=ON, 1s magnifier

Full-history (2016-2026): 2,034 trades, 44.8% WR, PF 1.05,
  51.4R (5.1 R/yr), DD -45.6R, Calmar 1.13, 1 neg year (2016)

Fixed-param WF: 6/6 folds profitable, combined OOS +62.0R, Calmar 0.41
Hold-out (2025+): 216 trades, Sharpe 0.58, PF 1.09, +9.1R
Verdict: MARGINAL GO
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics


def make_config():
    sess = SessionConfig(
        name="LDN",
        orb_start="03:00",
        orb_end="03:15",
        entry_start="03:15",
        entry_end="08:25",
        flat_start="08:20",
        flat_end="08:25",
        stop_atr_pct=8.0,
        min_gap_atr_pct=1.5,
        max_gap_points=20.0,
        max_gap_atr_pct=0.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=2.25,
        tp1_ratio=0.6,
        atr_length=14,
        impulse_close_filter=True,
        name="NQ LDN R2 Final",
        notes=(
            "Marginal GO from R1-R2 variable sweep optimization with 1s magnifier. "
            "R1 adopted max_gap_points=20 + ICF=ON. R2 fully converged. "
            "Grid sweep: 576 combos, best ≤1-neg-year: stop=8.0/rr=2.25/gap=1.5/tp1=0.6. "
            "Fixed-param WF: 6/6 folds profitable, combined OOS +62.0R (10.3 R/yr), Calmar 0.41. "
            "Hold-out 2025+: 216 trades, Sharpe 0.58, PF 1.09, +9.1R. "
            "Verdict: MARGINAL GO — hold-out barely clears Sharpe 0.5 threshold."
        ),
    )


def main():
    print("Saving NQ LDN R2 Final to DB")
    print("=" * 60)

    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    config = make_config()
    print("Running backtest...")
    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)

    m = compute_metrics(trades)
    print(f"\n  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  R/yr: {m['total_r'] / 10:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year: {yr_str}")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
