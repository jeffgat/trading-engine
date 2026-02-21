#!/usr/bin/env python3
"""Save the 4 GC Inversion v9 combo test results to the experiments DB."""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.results.export import results_to_dict, save_backtest_result

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"


def build_session(qualifying_move_atr_pct=0.0):
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=9.0,
        min_gap_atr_pct=1.0,
        max_gap_points=25.0,
        qualifying_move_atr_pct=qualifying_move_atr_pct,
    )


def build_config(name, notes, qualifying_move_atr_pct=0.0):
    session = build_session(qualifying_move_atr_pct=qualifying_move_atr_pct)
    return StrategyConfig(
        rr=3.5,
        tp1_ratio=0.2,
        risk_usd=5000.0,
        atr_length=50,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(session,),
        instrument=GC,
        strategy="inversion",
        direction_filter="long",
        use_bar_magnifier=True,
        half_days=HALF_DAYS,
        excluded_dates=EXCLUDED,
        name=name,
        notes=notes,
    )


def main():
    print("Loading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")

    runs = [
        {
            "name": "GC NY Inversion Longs v8 Baseline",
            "notes": "v8 GO config. rr=3.5, tp1=0.2, atr=50, entry 09:35-15:00, stop 9.0%, gap 1.0%, magnifier ON. No additional filters.",
            "qm_pct": 0.0,
            "exclude_fri": False,
        },
        {
            "name": "GC NY Inversion Longs v8 + 10% QM",
            "notes": "v8 + 10% qualifying sweep depth. Requires ORB low sweep to extend at least 10% of ATR below ORB low before accepting inversion long.",
            "qm_pct": 10.0,
            "exclude_fri": False,
        },
        {
            "name": "GC NY Inversion Longs v8 + No Fridays",
            "notes": "v8 + Friday exclusion. Removes Friday trades which had 46.3% WR and 0.06 avg R.",
            "qm_pct": 0.0,
            "exclude_fri": True,
        },
        {
            "name": "GC NY Inversion Longs v8 + 10% QM + No Fridays",
            "notes": "v8 + both filters: 10% qualifying sweep + Friday exclusion. v9 candidate.",
            "qm_pct": 10.0,
            "exclude_fri": True,
        },
    ]

    for run in runs:
        print(f"\nRunning: {run['name']}...")
        config = build_config(
            name=run["name"],
            notes=run["notes"],
            qualifying_move_atr_pct=run["qm_pct"],
        )

        if run["qm_pct"] > 0:
            trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)
        else:
            trades = run_backtest(df, config, start_date=START, df_1m=df_1m)

        if run["exclude_fri"]:
            trades = [
                t for t in trades
                if t.exit_type == EXIT_NO_FILL
                or datetime.strptime(t.date, "%Y-%m-%d").weekday() != 4
            ]

        result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
        result_id = save_backtest_result(result)
        m = result["summary"]
        print(f"  Saved: {result_id}")
        print(f"  Trades: {m['total_trades']}, WR: {m['win_rate']:.1%}, Net R: {m['total_r']:.1f}, DD: {m['max_drawdown_r']:.1f}")

    print("\nDone — all 4 saved.")


if __name__ == "__main__":
    main()
