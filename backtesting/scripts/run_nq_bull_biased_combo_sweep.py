#!/usr/bin/env python3
"""Constrained bull-biased portfolio sweep from the former generalist seeds.

This pass keeps the bull-specialist V1 winner fixed, limits Asia candidates to
the cleaner Asia LSI neighborhood, and only considers selected NY LSI variants.
It explicitly excludes the broad Asia continuation leg because that family
pulled the portfolio back toward a generalist payout profile.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    DEFAULT_HOLDOUT_START,
    bull_market_rank_key,
    build_nq_ny_regime_calendar,
    evaluate_bull_market_windows,
    trading_dates_from_calendar,
)
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from run_nq_asia_lsi_4leg_combo_sweep import make_nq_asia_lsi_combo_candidates  # noqa: E402
from run_nq_bull_portfolio_addon_sweep import (  # noqa: E402
    build_funded_profile,
    candidate_row,
    make_bull_winner_config,
    regime_contribution_summary,
    run_bull_winner,
    run_general_leg,
)
from run_nq_bull_specialist_combo_resolution import merge_trade_streams  # noqa: E402
from run_nq_ny_lsi_4leg_combo_sweep import make_nq_ny_lsi_combo_candidates  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_biased_combo_sweep"

ASIA_CANDIDATE_NAMES = (
    "nq_asia_lsi_rr1.75",
    "nq_asia_lsi_left8_right3",
    "nq_asia_lsi_left5_right3",
    "nq_asia_lsi_end2300",
    "nq_asia_lsi",
    "nq_asia_lsi_tp0.6",
)

NY_CANDIDATE_NAMES = (
    "none",
    "nq_ny_lsi_propfirm_2x_profile",
    "nq_ny_lsi_thu_only_excl",
    "nq_ny_lsi_end1400",
    "nq_ny_lsi_tp0.2",
)


def ranking_key(row: dict) -> tuple:
    year_windows_stub = {
        "survives_bull_v1": row["survives_bull_v1"],
        "acceptance_net_r": row["acceptance_net_r"],
        "acceptance_rejection_separation": row["acceptance_rejection_separation"],
        "holdout_2025_latest": {
            "payout_rate": row["holdout_payout_rate"],
            "breach_rate": row["holdout_breach_rate"],
            "average_days_to_payout": row["holdout_average_days_to_payout"],
        },
    }
    legs = row["portfolio_legs"].count("+") + 1
    return (
        *bull_market_rank_key(year_windows_stub),
        float(row["combo_bull_minus_bear_net_r"]),
        float(row["holdout_ev_per_start_usd"] or 0.0),
        -legs,
    )


def select_candidates(candidates, names: tuple[str, ...]) -> list:
    index = {cfg.name: cfg for cfg in candidates}
    return [index[name] for name in names if name != "none" and name in index]


def write_summary(output_dir: Path, ranking_df: pd.DataFrame) -> None:
    best = ranking_df.iloc[0].to_dict()
    best_two_leg = ranking_df[ranking_df["portfolio_type"] == "2-leg"].iloc[0].to_dict()
    best_three_leg = ranking_df[ranking_df["portfolio_type"] == "3-leg"].iloc[0].to_dict()

    lines = [
        "# NQ Bull-Biased Combo Sweep",
        "",
        "## Setup",
        "",
        "- Fixed core: `bull_specialist_v1_winner`.",
        "- Asia search space: selected `Asia LSI` neighborhood from the generalist strategy.",
        "- NY search space: selected `NY LSI` variants only.",
        "- `NQ Asia continuation` was intentionally excluded because it was too generalist in the prior pass.",
        "",
        "## Best Overall",
        "",
        f"- Portfolio: `{best['portfolio_legs']}`.",
        f"- Type: `{best['portfolio_type']}`.",
        f"- Acceptance `2024+` net R: `{best['acceptance_net_r']}`.",
        f"- Rejection `2022-2023` net R: `{best['rejection_net_r']}`.",
        f"- Holdout payout/breach: `{best['holdout_payout_rate']}` / `{best['holdout_breach_rate']}`.",
        f"- Holdout average days to payout: `{best['holdout_average_days_to_payout']}`.",
        f"- Combo bull/bear/sideways net R: `{best['combo_bull_net_r']}` / `{best['combo_bear_net_r']}` / `{best['combo_sideways_net_r']}`.",
        "",
        "## Best 2-Leg",
        "",
        f"- Portfolio: `{best_two_leg['portfolio_legs']}`.",
        f"- Holdout payout/breach: `{best_two_leg['holdout_payout_rate']}` / `{best_two_leg['holdout_breach_rate']}`.",
        f"- Acceptance/rejection: `{best_two_leg['acceptance_net_r']}` / `{best_two_leg['rejection_net_r']}`.",
        f"- Holdout average days to payout: `{best_two_leg['holdout_average_days_to_payout']}`.",
        "",
        "## Best 3-Leg",
        "",
        f"- Portfolio: `{best_three_leg['portfolio_legs']}`.",
        f"- Holdout payout/breach: `{best_three_leg['holdout_payout_rate']}` / `{best_three_leg['holdout_breach_rate']}`.",
        f"- Acceptance/rejection: `{best_three_leg['acceptance_net_r']}` / `{best_three_leg['rejection_net_r']}`.",
        f"- Holdout average days to payout: `{best_three_leg['holdout_average_days_to_payout']}`.",
        "",
        "## Interpretation",
        "",
        "- This pass is meant to find the next bull-biased portfolio path, not maximize generic payout speed.",
        "- The key comparison is whether the best 3-leg portfolio actually improves the bull-window profile versus the best 2-leg portfolio.",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull-Biased Combo Sweep")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start, end_date=args.end)
    eligible_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=False)
    funded_profile = build_funded_profile()

    bull_config = make_bull_winner_config()
    print("\nRunning fixed bull core...", flush=True)
    bull_trades = run_bull_winner(bull_config, df_5m, df_1m, df_1s, regime_calendar)

    all_asia_candidates = make_nq_asia_lsi_combo_candidates()
    asia_candidates = select_candidates(all_asia_candidates, ASIA_CANDIDATE_NAMES)
    all_ny_candidates = make_nq_ny_lsi_combo_candidates()
    ny_candidates = select_candidates(all_ny_candidates, NY_CANDIDATE_NAMES)

    print(f"\nRunning Asia LSI sweep ({len(asia_candidates)} candidates)...", flush=True)
    asia_results = run_sweep(
        df_5m,
        asia_candidates,
        n_workers=max(1, args.workers),
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    asia_trades_by_name = {
        cfg.name: run_general_leg(cfg, trades) for cfg, trades in asia_results
    }

    print(f"\nRunning NY LSI sweep ({len(ny_candidates)} candidates)...", flush=True)
    ny_results = run_sweep(
        df_5m,
        ny_candidates,
        n_workers=max(1, args.workers),
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    ny_trades_by_name = {
        cfg.name: run_general_leg(cfg, trades) for cfg, trades in ny_results
    }
    ny_trades_by_name["none"] = []

    rows: list[dict] = []
    for asia_name, asia_trades in asia_trades_by_name.items():
        for ny_name in NY_CANDIDATE_NAMES:
            ny_trades = ny_trades_by_name[ny_name]
            streams = [bull_trades, asia_trades]
            portfolio_legs = ["bull_specialist_v1_winner", asia_name]
            portfolio_type = "2-leg"
            if ny_name != "none":
                streams.append(ny_trades)
                portfolio_legs.append(ny_name)
                portfolio_type = "3-leg"
            combined_trades = merge_trade_streams(streams)
            year_windows = evaluate_bull_market_windows(
                specialist_name=" + ".join(portfolio_legs),
                trades=combined_trades,
                trading_dates=eligible_dates,
                funded_profile=funded_profile,
                holdout_start=args.holdout_start,
            )
            row = candidate_row(
                family="combo",
                config=next(cfg for cfg in asia_candidates if cfg.name == asia_name),
                year_windows=year_windows,
                combined_trades=combined_trades,
                add_on_trades=merge_trade_streams([asia_trades, ny_trades]),
                regime_calendar=regime_calendar,
            )
            row["portfolio_type"] = portfolio_type
            row["asia_leg"] = asia_name
            row["ny_leg"] = ny_name
            row["portfolio_legs"] = " + ".join(portfolio_legs)
            row["add_on_bull_minus_bear_net_r"] = round(
                regime_contribution_summary(merge_trade_streams([asia_trades, ny_trades]), regime_calendar)[
                    "bull_minus_bear_net_r"
                ],
                4,
            )
            rows.append(row)

    ranking_rows = sorted(rows, key=ranking_key, reverse=True)
    ranking_df = pd.DataFrame(ranking_rows)
    ranking_df.to_csv(output_dir / "combo_ranking.csv", index=False)

    best_two_leg = ranking_df[ranking_df["portfolio_type"] == "2-leg"].iloc[0].to_dict()
    best_three_leg = ranking_df[ranking_df["portfolio_type"] == "3-leg"].iloc[0].to_dict()
    best_overall = ranking_df.iloc[0].to_dict()

    (output_dir / "best_overall.json").write_text(json.dumps(best_overall, indent=2))
    (output_dir / "best_2leg.json").write_text(json.dumps(best_two_leg, indent=2))
    (output_dir / "best_3leg.json").write_text(json.dumps(best_three_leg, indent=2))
    write_summary(output_dir, ranking_df)

    print("\nTop candidates:")
    print(
        ranking_df[
            [
                "portfolio_type",
                "portfolio_legs",
                "survives_bull_v1",
                "acceptance_net_r",
                "rejection_net_r",
                "rejection_share_of_acceptance",
                "holdout_payout_rate",
                "holdout_breach_rate",
                "holdout_average_days_to_payout",
                "combo_bull_net_r",
                "combo_bear_net_r",
                "combo_sideways_net_r",
            ]
        ]
        .head(12)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
