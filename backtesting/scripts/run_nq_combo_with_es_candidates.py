#!/usr/bin/env python3
"""Evaluate whether leading ES continuation legs improve the balanced NQ combo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_TP1_TP2, TradeResult, run_backtest  # noqa: E402


BASE_INPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_papertrade_balanced"
OUTPUT_DIR = ROOT / "data" / "results" / "nq_combo_with_es_candidates"
HOLDOUT_START = "2025-01-01"


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def build_funded_profile() -> FundedFirstPayoutProfile:
    return FundedFirstPayoutProfile(
        challenge_fee=150.0,
        starting_balance_usd=50_000.0,
        trailing_drawdown_usd=2_000.0,
        max_trailing_breach_usd=50_000.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
        risk_post_payout_usd=250.0,
    )


def make_es_asia_final_config() -> StrategyConfig:
    session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="03:00",
        flat_start="07:00",
        flat_end="07:00",
        stop_orb_pct=125.0,
        min_gap_atr_pct=0.5,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        excluded_days=(),
        name="ES Asia Cont Long 2016-2026 Final",
        notes="Conditional-go ES Asia continuation long from ES learnings.",
    )


def make_es_ny_final_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.25,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        excluded_days=(3,),
        name="ES NY Cont Long 2016-2026 Final",
        notes="Conditional-go ES NY continuation long from ES learnings.",
    )


def load_base_combo_trades(path: Path) -> list[TradeResult]:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["fill_time_sort"] = df["fill_time"].fillna("")
    trades: list[TradeResult] = []
    for _, row in df.sort_values(["date", "fill_time_sort", "signal_bar", "fill_bar"]).iterrows():
        trades.append(
            TradeResult(
                date=row["date"].strftime("%Y-%m-%d"),
                session=str(row["session"]),
                direction=int(row["direction"]),
                signal_bar=int(row["signal_bar"]),
                fill_bar=int(row["fill_bar"]),
                entry_price=float(row["entry_price"]),
                stop_price=float(row["stop_price"]),
                tp1_price=float(row["tp1_price"]),
                tp2_price=float(row["tp2_price"]),
                exit_type=EXIT_TP1_TP2,
                exit_bar=int(row["exit_bar"]),
                pnl_points=float(row["pnl_points"]),
                pnl_usd=float(row["pnl_usd"]),
                r_multiple=float(row["r_multiple"]),
                qty=float(row["qty"]),
                half_qty=float(row["half_qty"]),
                gap_size=float(row["gap_size"]),
                risk_points=float(row["risk_points"]),
                fill_time=str(row["fill_time"]),
                exit_time=str(row["exit_time"]),
            )
        )
    return trades


def merge_trade_streams(streams: list[list[TradeResult]]) -> list[TradeResult]:
    merged: list[TradeResult] = []
    for trades in streams:
        merged.extend(trades)
    return sorted(merged, key=lambda t: (t.date, t.fill_time or "", t.signal_bar, t.fill_bar, t.exit_time or ""))


def evaluate_combo(
    combo_name: str,
    trades: list[TradeResult],
    all_dates: list[str],
    holdout_dates: list[str],
    profile: FundedFirstPayoutProfile,
) -> dict:
    holdout_trades = [trade for trade in trades if trade.date >= HOLDOUT_START]
    outcomes = simulate_funded_first_payouts(combo_name, trades, all_dates, profile)
    holdout_outcomes = simulate_funded_first_payouts(combo_name, holdout_trades, holdout_dates, profile)
    scorecard = build_funded_first_payout_scorecard(outcomes, profile)
    holdout_scorecard = build_funded_first_payout_scorecard(holdout_outcomes, profile)
    forecast = build_funded_first_payout_forecast(outcomes, horizons_days=(20, 30, 45))
    holdout_forecast = build_funded_first_payout_forecast(holdout_outcomes, horizons_days=(20, 30, 45))
    timeline = {row["horizon_days"]: row for row in forecast["timeline"]}
    holdout_timeline = {row["horizon_days"]: row for row in holdout_forecast["timeline"]}

    return {
        "combo_name": combo_name,
        "filled_trades": len(trades),
        "payout_rate": scorecard["payout_rate"],
        "breach_rate": scorecard["breach_rate"],
        "average_days_to_payout": scorecard["average_days_to_payout"],
        "average_first_payout_amount_usd": scorecard["average_first_payout_amount_usd"],
        "ev_per_start_usd": scorecard["ev_per_start_usd"],
        "resolved_by_day_20": timeline[20]["resolved_rate_by_horizon"],
        "resolved_by_day_30": timeline[30]["resolved_rate_by_horizon"],
        "resolved_by_day_45": timeline[45]["resolved_rate_by_horizon"],
        "holdout_payout_rate": holdout_scorecard["payout_rate"],
        "holdout_breach_rate": holdout_scorecard["breach_rate"],
        "holdout_average_days_to_payout": holdout_scorecard["average_days_to_payout"],
        "holdout_ev_per_start_usd": holdout_scorecard["ev_per_start_usd"],
        "holdout_resolved_by_day_20": holdout_timeline[20]["resolved_rate_by_horizon"],
        "holdout_resolved_by_day_30": holdout_timeline[30]["resolved_rate_by_horizon"],
        "holdout_resolved_by_day_45": holdout_timeline[45]["resolved_rate_by_horizon"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=str(BASE_INPUT_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Combo With ES Candidates")
    print("=" * 72)
    print(f"Input dir:  {input_dir}")
    print(f"Output dir: {output_dir}")

    print("\nLoading base NQ combo trades...", flush=True)
    base_trades = load_base_combo_trades(input_dir / "combo_trades.csv")

    print("Loading NQ calendar...", flush=True)
    nq_df_5m = load_5m_data(NQ.data_file, start="2016-01-01")
    regime_calendar = build_nq_ny_regime_calendar(nq_df_5m, start_date="2016-01-01")
    all_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=True)
    holdout_dates = [d for d in all_dates if d >= HOLDOUT_START]
    profile = build_funded_profile()

    print("Loading ES data...", flush=True)
    es_df_5m = load_5m_data(ES.data_file, start="2016-01-01")
    try:
        es_df_1m = load_1m_for_5m(ES.data_file, start="2016-01-01")
    except FileNotFoundError:
        es_df_1m = None
    es_df_1s = load_1s_for_5m(ES.data_file, start="2016-01-01")

    print("Running ES candidate legs...", flush=True)
    es_asia_cfg = make_es_asia_final_config()
    es_ny_cfg = make_es_ny_final_config()
    es_asia_trades = run_backtest(es_df_5m, es_asia_cfg, start_date="2016-01-01", df_1m=es_df_1m, df_1s=es_df_1s)
    es_ny_trades = run_backtest(es_df_5m, es_ny_cfg, start_date="2016-01-01", df_1m=es_df_1m, df_1s=es_df_1s)
    es_asia_trades = apply_dow_filter(es_asia_trades, set(es_asia_cfg.excluded_days))
    es_ny_trades = apply_dow_filter(es_ny_trades, set(es_ny_cfg.excluded_days))

    combos = {
        "nq_balanced_base": base_trades,
        "nq_balanced_plus_es_asia": merge_trade_streams([base_trades, es_asia_trades]),
        "nq_balanced_plus_es_ny": merge_trade_streams([base_trades, es_ny_trades]),
        "nq_balanced_plus_es_asia_plus_es_ny": merge_trade_streams([base_trades, es_asia_trades, es_ny_trades]),
    }

    rows = []
    for combo_name, trades in combos.items():
        rows.append(evaluate_combo(combo_name, trades, all_dates, holdout_dates, profile))

    ranking_df = pd.DataFrame(rows).sort_values(
        ["holdout_payout_rate", "holdout_breach_rate", "resolved_by_day_30", "ev_per_start_usd"],
        ascending=[False, True, False, False],
    )
    ranking_df.to_csv(output_dir / "combo_es_candidate_ranking.csv", index=False)

    best = ranking_df.iloc[0]
    summary_lines = [
        "# NQ Combo With ES Candidates",
        "",
        "## Base Route",
        "",
        "- Starting point: `bull_specialist + nq_asia + nq_asia_lsi + nq_ny_lsi`.",
        "",
        "## ES Candidates",
        "",
        "- `es_asia`: ES Asia continuation long from ES learnings final config.",
        "- `es_ny`: ES NY continuation long from ES learnings final config.",
        "",
        "## Best Candidate",
        "",
        f"- Combo: `{best['combo_name']}`.",
        f"- Payout rate: `{best['payout_rate']}` | breach rate `{best['breach_rate']}`.",
        f"- Average days to payout: `{best['average_days_to_payout']}`.",
        f"- Resolved by day 30: `{best['resolved_by_day_30']}`.",
        f"- Holdout payout rate: `{best['holdout_payout_rate']}` | holdout breach `{best['holdout_breach_rate']}`.",
        f"- Holdout EV/start: `${best['holdout_ev_per_start_usd']}`.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    write_json(
        output_dir / "combo_es_candidate_details.json",
        {
            "profile": profile.__dict__,
            "es_asia_config": {
                "name": es_asia_cfg.name,
                "excluded_days": list(es_asia_cfg.excluded_days),
            },
            "es_ny_config": {
                "name": es_ny_cfg.name,
                "excluded_days": list(es_ny_cfg.excluded_days),
            },
            "rows": rows,
        },
    )

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
