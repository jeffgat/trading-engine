#!/usr/bin/env python3
"""Run and save the current bull-specialist V1 winner to the backtest DB.

This saves the routed specialist, not the raw continuation stream:
- config winner: rr=3.0, tp1=0.5, stop=7.0, entry_end=12:30
- Friday exclusion
- no low-confidence days
- bull-regime only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    build_nq_ny_regime_calendar,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import run_backtest  # noqa: E402
from orb_backtest.experiments import query_runs  # noqa: E402
from orb_backtest.results.export import results_to_dict, save_backtest_result  # noqa: E402


def make_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:30",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.5,
        atr_length=12,
        impulse_close_filter=False,
        excluded_days=(4,),
        name="NQ Bull Specialist V1 Winner Routed",
        notes=(
            "Bull-specialist V1 winner from the fixed-window study. "
            "Routed variant: Friday exclusion, no low-confidence days, bull-regime only. "
            "Winner config rr=3.0, tp1=0.5, stop_atr=7.0, entry_end=12:30. "
            "Selected because 2024+ acceptance net R materially exceeded 2022-2023 rejection net R "
            "while holdout payout exceeded breach."
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument(
        "--name",
        default="NQ Bull Specialist V1 Winner Routed",
        help="Backtest name shown in dashboard",
    )
    args = parser.parse_args()

    print("Saving NQ Bull Specialist V1 Winner")
    print("=" * 72)

    cfg = make_config()
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)

    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start, end_date=args.end)

    trades = run_backtest(
        df_5m,
        cfg,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    trades = apply_dow_filter(trades, set(cfg.excluded_days))
    trades = filter_trades_by_low_confidence(
        trades,
        regime_calendar,
        include_low_confidence=False,
    )
    trades = filter_trades_by_regime(
        trades,
        regime_calendar,
        include={"bull"},
    )

    result = results_to_dict(
        trades,
        cfg,
        include_trades=True,
        include_equity_curve=True,
    )
    result["name"] = args.name
    result["notes"] = (
        cfg.notes
        + " Saved from run_nq_bull_specialist_v1.py winner package. "
        + "Routing: regime_gate=bull_no_low_confidence, structure_gate=none, window=2020-latest."
    )
    result["config"]["regime_gate"] = "bull_no_low_confidence"
    result["config"]["structure_gate"] = "none"
    result["config"]["specialist_family"] = "bull_market_specialist_v1"
    result["config"]["source_result_dir"] = str(ROOT / "data" / "results" / "nq_bull_specialist_v1")

    result_id = save_backtest_result(result)
    loaded = next(
        (row for row in query_runs(limit=25) if row.get("result_file") == result_id),
        None,
    )

    print(f"Saved: {result_id}")
    print(
        "Verified:"
        f" name={loaded.get('experiment_name')!r}"
        f" total_trades={loaded.get('total_trades')}"
        f" total_r={loaded.get('total_r')}"
    )


if __name__ == "__main__":
    main()
