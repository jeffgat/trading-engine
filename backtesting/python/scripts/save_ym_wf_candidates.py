#!/usr/bin/env python3
"""Save the two WF-validated YM NY candidates to the experiments DB.

Candidates:
1. 5m ORB + 11:30 cutoff + ATR10 (best risk-adjusted)
2. 5m ORB + 13:00 cutoff + ATR10 (best absolute returns)

Uses base swept params: rr=4.0, stop=4.0, gap=1.5 (WF center values).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result


def make_config(orb_end, entry_end, name, notes):
    """Build a StrategyConfig for YM NY with specified structural params."""
    instrument = get_instrument("YM")
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=orb_end,
        entry_start=orb_end,  # entry starts when ORB ends
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=1.5,
        max_gap_points=100.0,
    )
    return StrategyConfig(
        rr=4.0,
        tp1_ratio=0.55,
        atr_length=10,
        sessions=(session,),
        instrument=instrument,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
        name=name,
        notes=notes,
    )


CANDIDATES = [
    make_config(
        "09:35", "11:30",
        name="YM NY 5m ORB 11:30 ATR10 (WF Validated)",
        notes=(
            "WF Validated: 12m IS, 3m OOS, 35 folds, rolling. "
            "Combined OOS: Sharpe 2.275, Sortino 5.055, Calmar 17.37, "
            "338.1R total, 19.8R max DD, PF 1.39, 1345 trades, AvgR 0.255, WF Eff 0.79. "
            "Best risk-adjusted of 5 candidates tested."
        ),
    ),
    make_config(
        "09:35", "13:00",
        name="YM NY 5m ORB 13:00 ATR10 (WF Validated)",
        notes=(
            "WF Validated: 12m IS, 3m OOS, 35 folds, rolling. "
            "Combined OOS: Sharpe 2.224, Sortino 4.903, Calmar 18.94, "
            "403.6R total, 21.7R max DD, PF 1.38, 1658 trades, AvgR 0.247, WF Eff 0.84. "
            "Best absolute returns and WF efficiency of 5 candidates tested."
        ),
    ),
]


def main():
    print("Loading YM data...")
    df = load_5m_data("YM_5m.csv")
    print(f"  {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})")
    print()

    for cfg in CANDIDATES:
        print(f"Running: {cfg.name}")
        trades = run_backtest(df, cfg, start_date="2016-03-01")
        result = results_to_dict(
            trades, cfg,
            include_trades=True,
            include_equity_curve=True,
        )
        result_id = save_backtest_result(result)
        n_filled = sum(1 for t in trades if t.exit_type != 0)
        print(f"  Saved: {result_id} ({n_filled} filled trades)")

    print()
    print("Done!")


if __name__ == "__main__":
    main()
