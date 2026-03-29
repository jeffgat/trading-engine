#!/usr/bin/env python3
"""Optimize the NQ Asia LSI leg inside the fixed 4-leg funded-account combo."""

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
    FundedFirstPayoutProfile,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from run_nq_bull_specialist_combo_resolution import (  # noqa: E402
    HOLDOUT_START,
    make_bull_specialist_config,
    make_nq_asia_config,
    make_nq_asia_lsi_config,
    make_nq_ny_lsi_config,
    merge_trade_streams,
    run_leg,
)


OUTPUT_DIR = ROOT / "data" / "results" / "nq_asia_lsi_4leg_combo_sweep"


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


def make_nq_asia_lsi_fast_v2_config() -> StrategyConfig:
    session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:05",
        rth_start="20:00",
        entry_start="20:40",
        entry_end="23:30",
        flat_start="00:00",
        flat_end="01:00",
        min_gap_atr_pct=1.75,
    )
    return StrategyConfig(
        strategy="lsi",
        rr=1.75,
        tp1_ratio=0.7,
        atr_length=40,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=NQ,
        direction_filter="long",
        lsi_n_left=3,
        lsi_n_right=3,
        lsi_fvg_window_left=10,
        lsi_fvg_window_right=10,
        lsi_entry_mode="close",
        name="nq_asia_lsi_fast_v2",
        notes="Older FAST_V2 Asia LSI anchor.",
    )


def make_nq_asia_lsi_combo_candidates() -> list[StrategyConfig]:
    base = make_nq_asia_lsi_config()
    fast_v2 = make_nq_asia_lsi_fast_v2_config()
    session = base.sessions[0]

    candidates = [
        base,
        fast_v2,
        StrategyConfig(
            **{
                **base.__dict__,
                "rr": 1.75,
                "name": "nq_asia_lsi_rr1.75",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "rr": 2.25,
                "name": "nq_asia_lsi_rr2.25",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "tp1_ratio": 0.6,
                "name": "nq_asia_lsi_tp0.6",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "tp1_ratio": 0.8,
                "name": "nq_asia_lsi_tp0.8",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "sessions": (
                    SessionConfig(
                        **{
                            **session.__dict__,
                            "flat_start": "00:00",
                            "flat_end": "01:00",
                        }
                    ),
                ),
                "name": "nq_asia_lsi_flat0000",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "sessions": (
                    SessionConfig(
                        **{
                            **session.__dict__,
                            "entry_end": "23:00",
                        }
                    ),
                ),
                "name": "nq_asia_lsi_end2300",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "lsi_n_left": 5,
                "name": "nq_asia_lsi_left5_right2",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "lsi_n_left": 8,
                "lsi_n_right": 3,
                "name": "nq_asia_lsi_left8_right3",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "lsi_n_left": 5,
                "lsi_n_right": 3,
                "name": "nq_asia_lsi_left5_right3",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "lsi_fvg_window_left": 10,
                "lsi_fvg_window_right": 2,
                "name": "nq_asia_lsi_fvgl10_fvgr2",
            }
        ),
        StrategyConfig(
            **{
                **base.__dict__,
                "lsi_fvg_window_left": 15,
                "lsi_fvg_window_right": 5,
                "name": "nq_asia_lsi_fvgl15_fvgr5",
            }
        ),
    ]
    return candidates


def evaluate_combo(
    combo_name: str,
    trades,
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
        "filled_trades": len(trades),
        "payout_rate": scorecard["payout_rate"],
        "breach_rate": scorecard["breach_rate"],
        "open_rate": scorecard["open_rate"],
        "average_days_to_payout": scorecard["average_days_to_payout"],
        "median_days_to_payout": scorecard["median_days_to_payout"],
        "average_trades_to_payout": scorecard["average_trades_to_payout"],
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
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Asia LSI 4-Leg Combo Sweep")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start="2016-01-01")
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start="2016-01-01")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start="2016-01-01")

    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date="2016-01-01")
    all_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=True)
    holdout_dates = [d for d in all_dates if d >= HOLDOUT_START]
    funded_profile = build_funded_profile()

    print("\nRunning fixed legs once...", flush=True)
    fixed_leg_trades = {
        "bull_specialist": run_leg("bull_specialist", make_bull_specialist_config(), df_5m, df_1m, df_1s, regime_calendar),
        "nq_asia": run_leg("nq_asia", make_nq_asia_config(), df_5m, df_1m, df_1s, regime_calendar),
        "nq_ny_lsi": run_leg("nq_ny_lsi", make_nq_ny_lsi_config(), df_5m, df_1m, df_1s, regime_calendar),
    }

    print("\nSweeping NQ Asia LSI candidates...", flush=True)
    candidate_rows = []
    details = {}
    for config in make_nq_asia_lsi_combo_candidates():
        asia_lsi_trades = run_leg("nq_asia_lsi", config, df_5m, df_1m, df_1s, regime_calendar)
        combo_trades = merge_trade_streams(
            [
                fixed_leg_trades["bull_specialist"],
                fixed_leg_trades["nq_asia"],
                asia_lsi_trades,
                fixed_leg_trades["nq_ny_lsi"],
            ]
        )
        score = evaluate_combo(config.name, combo_trades, all_dates, holdout_dates, funded_profile)
        row = {
            "asia_lsi_candidate": config.name,
            "rr": config.rr,
            "tp1_ratio": config.tp1_ratio,
            "atr_length": config.atr_length,
            "entry_end": config.sessions[0].entry_end,
            "flat_start": config.sessions[0].flat_start,
            "min_gap_atr_pct": config.sessions[0].min_gap_atr_pct,
            "lsi_n_left": config.lsi_n_left,
            "lsi_n_right": config.lsi_n_right,
            "lsi_fvg_window_left": config.lsi_fvg_window_left,
            "lsi_fvg_window_right": config.lsi_fvg_window_right,
            **score,
        }
        candidate_rows.append(row)
        details[config.name] = row

    ranking_df = pd.DataFrame(candidate_rows).sort_values(
        by=[
            "holdout_payout_rate",
            "holdout_breach_rate",
            "holdout_resolved_by_day_30",
            "payout_rate",
            "breach_rate",
            "resolved_by_day_30",
            "ev_per_start_usd",
        ],
        ascending=[False, True, False, False, True, False, False],
    )
    ranking_df.to_csv(output_dir / "asia_lsi_combo_ranking.csv", index=False)

    practical_df = ranking_df[
        (ranking_df["ev_per_start_usd"] > 0)
        & (ranking_df["holdout_ev_per_start_usd"] > 0)
        & (ranking_df["holdout_payout_rate"] >= ranking_df["holdout_breach_rate"])
        & (ranking_df["average_first_payout_amount_usd"] >= 300)
    ].copy()
    practical_df.to_csv(output_dir / "asia_lsi_combo_ranking_practical.csv", index=False)

    best = practical_df.iloc[0] if not practical_df.empty else ranking_df.iloc[0]
    baseline = ranking_df.loc[ranking_df["asia_lsi_candidate"] == "nq_asia_lsi"].iloc[0]

    summary_lines = [
        "# NQ Asia LSI 4-Leg Combo Sweep",
        "",
        "## Fixed Combo Legs",
        "",
        "- `bull_specialist` fixed.",
        "- `nq_asia` fixed at the current combo winner.",
        "- `nq_ny_lsi` fixed.",
        "- Only `nq_asia_lsi` was re-optimized in this sweep.",
        "",
        "## Best Candidate",
        "",
        f"- Asia LSI candidate: `{best['asia_lsi_candidate']}`.",
        f"- Payout rate: `{best['payout_rate']}` | breach rate `{best['breach_rate']}`.",
        f"- Average days to payout: `{best['average_days_to_payout']}`.",
        f"- Resolved by day 30: `{best['resolved_by_day_30']}`.",
        f"- Holdout payout rate: `{best['holdout_payout_rate']}` | holdout breach `{best['holdout_breach_rate']}`.",
        f"- Holdout average days to payout: `{best['holdout_average_days_to_payout']}`.",
        f"- Holdout EV/start: `${best['holdout_ev_per_start_usd']}`.",
        "",
        "## Baseline Comparison",
        "",
        f"- Current combo Asia LSI anchor: `{baseline['asia_lsi_candidate']}`.",
        f"- Baseline holdout payout/breach: `{baseline['holdout_payout_rate']}` / `{baseline['holdout_breach_rate']}`.",
        f"- Baseline resolved by day 30: `{baseline['resolved_by_day_30']}`.",
        f"- Best candidate holdout payout/breach: `{best['holdout_payout_rate']}` / `{best['holdout_breach_rate']}`.",
        f"- Best candidate resolved by day 30: `{best['resolved_by_day_30']}`.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    write_json(
        output_dir / "asia_lsi_combo_details.json",
        {
            "funded_profile": funded_profile.__dict__,
            "details": details,
        },
    )

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
