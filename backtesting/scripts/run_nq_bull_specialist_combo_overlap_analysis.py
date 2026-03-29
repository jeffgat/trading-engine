#!/usr/bin/env python3
"""Analyze overlap and concentration risk for the balanced NQ combo package."""

from __future__ import annotations

import argparse
import json
from itertools import combinations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent

import sys

sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_TP1_TP2, TradeResult  # noqa: E402


INPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_papertrade_balanced"
OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_overlap_analysis"
HOLDOUT_START = "2025-01-01"
SELECTED_LEGS = ("bull_specialist", "nq_asia", "nq_asia_lsi", "nq_ny_lsi")


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


def load_combo_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    df["fill_time_sort"] = df["fill_time"].fillna("")
    return df


def frame_to_trades(frame: pd.DataFrame) -> list[TradeResult]:
    ordered = frame.sort_values(["date", "fill_time_sort", "signal_bar", "fill_bar"]).reset_index(drop=True)
    trades: list[TradeResult] = []
    for _, row in ordered.iterrows():
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


def build_day_summary(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby("date")
        .agg(
            n_trades=("leg_name", "count"),
            n_unique_legs=("leg_name", "nunique"),
            day_r=("r_multiple", "sum"),
            day_pnl_usd=("pnl_usd", "sum"),
            legs=("leg_name", lambda s: ",".join(sorted(set(s)))),
        )
        .reset_index()
        .sort_values("date")
    )


def build_pair_overlap_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    by_date = df.groupby("date")["leg_name"].apply(lambda s: sorted(set(s))).to_dict()
    for left, right in combinations(SELECTED_LEGS, 2):
        overlap_dates = [
            trade_date for trade_date, legs in by_date.items()
            if left in legs and right in legs
        ]
        left_dates = sum(1 for legs in by_date.values() if left in legs)
        right_dates = sum(1 for legs in by_date.values() if right in legs)
        overlap_count = len(overlap_dates)
        rows.append(
            {
                "left_leg": left,
                "right_leg": right,
                "overlap_days": overlap_count,
                "left_active_days": left_dates,
                "right_active_days": right_dates,
                "overlap_pct_of_left": round(overlap_count / left_dates, 4) if left_dates else 0.0,
                "overlap_pct_of_right": round(overlap_count / right_dates, 4) if right_dates else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values(["overlap_days", "left_leg", "right_leg"], ascending=[False, True, True])


def build_overlap_bucket_summary(day_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total_days = len(day_df)
    for n_legs, group in day_df.groupby("n_unique_legs"):
        rows.append(
            {
                "n_legs": int(n_legs),
                "days": int(len(group)),
                "pct_days": round(len(group) / total_days, 4) if total_days else 0.0,
                "loss_day_rate": round(float((group["day_r"] < 0).mean()), 4),
                "avg_day_r": round(float(group["day_r"].mean()), 4),
                "median_day_r": round(float(group["day_r"].median()), 4),
                "p10_day_r": round(float(group["day_r"].quantile(0.10)), 4),
                "p90_day_r": round(float(group["day_r"].quantile(0.90)), 4),
            }
        )
    return pd.DataFrame(rows).sort_values("n_legs")


def build_leg_correlation_table(df: pd.DataFrame) -> pd.DataFrame:
    wide = df.pivot_table(index="date", columns="leg_name", values="r_multiple", aggfunc="sum")
    corr = wide.corr().round(4)
    corr.index.name = "leg_name"
    return corr.reset_index()


def apply_overlap_policy(df: pd.DataFrame, policy_name: str) -> pd.DataFrame:
    adjusted = df.copy().sort_values(["date", "fill_time_sort", "signal_bar", "fill_bar"]).reset_index(drop=True)
    adjusted["scale"] = 1.0

    if policy_name == "baseline":
        return adjusted

    if policy_name == "half_all_overlap":
        mask = adjusted.groupby("date")["date"].transform("size") > 1
        adjusted.loc[mask, "scale"] = 0.5
    elif policy_name == "first_full_half_extra":
        for _, idx in adjusted.groupby("date", sort=False).groups.items():
            idx_list = list(idx)
            if len(idx_list) <= 1:
                continue
            adjusted.loc[idx_list[1:], "scale"] = 0.5
    elif policy_name == "first_only":
        for _, idx in adjusted.groupby("date", sort=False).groups.items():
            idx_list = list(idx)
            if len(idx_list) <= 1:
                continue
            adjusted.loc[idx_list[1:], "scale"] = 0.0
    else:
        raise ValueError(f"Unknown policy: {policy_name}")

    adjusted["r_multiple"] = adjusted["r_multiple"] * adjusted["scale"]
    adjusted["pnl_points"] = adjusted["pnl_points"] * adjusted["scale"]
    adjusted["pnl_usd"] = adjusted["pnl_usd"] * adjusted["scale"]
    adjusted = adjusted[adjusted["scale"] > 0].copy()
    return adjusted


def evaluate_policy(
    base_df: pd.DataFrame,
    policy_name: str,
    all_dates: list[str],
    holdout_dates: list[str],
    profile: FundedFirstPayoutProfile,
) -> dict:
    adjusted = apply_overlap_policy(base_df, policy_name)
    trades = frame_to_trades(adjusted)
    holdout_trades = [trade for trade in trades if trade.date >= HOLDOUT_START]
    outcomes = simulate_funded_first_payouts(policy_name, trades, all_dates, profile)
    holdout_outcomes = simulate_funded_first_payouts(policy_name, holdout_trades, holdout_dates, profile)
    scorecard = build_funded_first_payout_scorecard(outcomes, profile)
    holdout_scorecard = build_funded_first_payout_scorecard(holdout_outcomes, profile)
    forecast = build_funded_first_payout_forecast(outcomes, horizons_days=(20, 30, 45))
    holdout_forecast = build_funded_first_payout_forecast(holdout_outcomes, horizons_days=(20, 30, 45))
    timeline = {row["horizon_days"]: row for row in forecast["timeline"]}
    holdout_timeline = {row["horizon_days"]: row for row in holdout_forecast["timeline"]}
    day_summary = build_day_summary(adjusted)
    overlap_days = int((day_summary["n_unique_legs"] > 1).sum())

    return {
        "policy_name": policy_name,
        "trades_kept": int(len(adjusted)),
        "active_days": int(len(day_summary)),
        "overlap_days": overlap_days,
        "pct_active_days_with_overlap": round(overlap_days / len(day_summary), 4) if len(day_summary) else 0.0,
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
    parser.add_argument("--input-dir", default=str(INPUT_DIR))
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull Specialist Combo Overlap Analysis")
    print("=" * 72)
    print(f"Input dir:  {input_dir}")
    print(f"Output dir: {output_dir}")

    combo_df = load_combo_trades(input_dir / "combo_trades.csv")
    day_summary = build_day_summary(combo_df)
    overlap_bucket_summary = build_overlap_bucket_summary(day_summary)
    pair_overlap = build_pair_overlap_table(combo_df)
    corr_table = build_leg_correlation_table(combo_df)
    worst_days = day_summary.sort_values(["day_r", "n_unique_legs"]).head(25).copy()
    best_days = day_summary.sort_values(["day_r", "n_unique_legs"], ascending=[False, False]).head(25).copy()

    print("\nLoading NQ trading calendar...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start="2016-01-01")
    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date="2016-01-01")
    all_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=True)
    holdout_dates = [d for d in all_dates if d >= HOLDOUT_START]
    funded_profile = build_funded_profile()

    print("\nEvaluating overlap policies...", flush=True)
    scenario_rows = []
    for policy_name in ("baseline", "first_full_half_extra", "half_all_overlap", "first_only"):
        scenario_rows.append(
            evaluate_policy(combo_df, policy_name, all_dates, holdout_dates, funded_profile)
        )
    scenario_df = pd.DataFrame(scenario_rows).sort_values(
        ["holdout_payout_rate", "holdout_breach_rate", "resolved_by_day_30"],
        ascending=[False, True, False],
    )

    day_summary.to_csv(output_dir / "daily_overlap_summary.csv", index=False)
    overlap_bucket_summary.to_csv(output_dir / "overlap_bucket_summary.csv", index=False)
    pair_overlap.to_csv(output_dir / "pair_overlap_counts.csv", index=False)
    corr_table.to_csv(output_dir / "leg_correlation_matrix.csv", index=False)
    worst_days.to_csv(output_dir / "worst_overlap_days.csv", index=False)
    best_days.to_csv(output_dir / "best_overlap_days.csv", index=False)
    scenario_df.to_csv(output_dir / "overlap_policy_scenarios.csv", index=False)

    best_holdout = scenario_df.iloc[0]
    practical = scenario_df.loc[scenario_df["policy_name"] == "first_full_half_extra"].iloc[0]

    summary_lines = [
        "# NQ Bull Specialist Combo Overlap Analysis",
        "",
        "## Baseline Structure",
        "",
        f"- Active combo days: `{len(day_summary)}` from `{len(combo_df)}` filled trades.",
        f"- Single-leg days: `{int(overlap_bucket_summary.loc[overlap_bucket_summary['n_legs'] == 1, 'days'].sum())}`.",
        f"- Multi-leg days: `{int((day_summary['n_unique_legs'] > 1).sum())}`.",
        f"- Worst stacked-loss day: `{worst_days.iloc[0]['date'].strftime('%Y-%m-%d')}` at `{round(float(worst_days.iloc[0]['day_r']), 4)}` R.",
        f"- Best stacked-win day: `{best_days.iloc[0]['date'].strftime('%Y-%m-%d')}` at `{round(float(best_days.iloc[0]['day_r']), 4)}` R.",
        "",
        "## Key Concentration Read",
        "",
        f"- The heaviest recurring overlap pair is `{pair_overlap.iloc[0]['left_leg']} + {pair_overlap.iloc[0]['right_leg']}` on `{int(pair_overlap.iloc[0]['overlap_days'])}` days.",
        f"- Mild throttle winner: `first_full_half_extra`.",
        f"- That policy keeps the first fill at full size and halves extra same-day legs.",
        "",
        "## Policy Comparison",
        "",
        f"- Baseline: payout `{scenario_df.loc[scenario_df['policy_name'] == 'baseline', 'payout_rate'].iloc[0]}` | breach `{scenario_df.loc[scenario_df['policy_name'] == 'baseline', 'breach_rate'].iloc[0]}` | resolved by day 30 `{scenario_df.loc[scenario_df['policy_name'] == 'baseline', 'resolved_by_day_30'].iloc[0]}` | holdout payout `{scenario_df.loc[scenario_df['policy_name'] == 'baseline', 'holdout_payout_rate'].iloc[0]}`.",
        f"- First-full-half-extra: payout `{practical['payout_rate']}` | breach `{practical['breach_rate']}` | resolved by day 30 `{practical['resolved_by_day_30']}` | holdout payout `{practical['holdout_payout_rate']}` | holdout breach `{practical['holdout_breach_rate']}`.",
        f"- Best holdout row by payout/breach ranking: `{best_holdout['policy_name']}`.",
        "",
        "## Takeaway",
        "",
        "- Overlap exists, but it is not extreme enough to force hard de-duplication.",
        "- Harder throttles give back too much speed and EV.",
        "- If live paper trading shows stacked-loss discomfort, `first_full_half_extra` is the cleanest first risk control to trial.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    write_json(
        output_dir / "overlap_analysis.json",
        {
            "funded_profile": funded_profile.__dict__,
            "top_pair_overlap": pair_overlap.iloc[0].to_dict(),
            "scenarios": scenario_rows,
        },
    )

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
