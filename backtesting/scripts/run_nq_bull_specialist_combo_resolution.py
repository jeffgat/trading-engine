#!/usr/bin/env python3
"""Evaluate funded-account resolution speed for NQ multi-leg combos.

The fast-payout bull specialist is treated as the mandatory core leg.
We then add existing NQ legs from the repo and measure whether the
combined funded account resolves faster without an unacceptable breach lift.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile,
    apply_bull_hh_hl_vwap_gate,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_TP1_TP2, run_backtest


OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_resolution"
TP1_EXIT_TYPES = {EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD}
HOLDOUT_START = "2025-01-01"


def make_bull_specialist_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=6.0,
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
        tp1_ratio=0.6,
        atr_length=12,
        impulse_close_filter=False,
        excluded_days=(4,),
        name="bull_specialist_fast_payout",
        notes="Bull specialist fast payout winner.",
    )


def make_nq_asia_config() -> StrategyConfig:
    session = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="22:30",
        flat_start="04:00",
        flat_end="07:00",
        stop_orb_pct=100.0,
        min_gap_orb_pct=10.0,
    )
    return StrategyConfig(
        rr=6.0,
        tp1_ratio=0.3,
        atr_length=5,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=NQ,
        direction_filter="long",
        excluded_days=(1,),
        name="nq_asia_cont",
        notes="Existing NQ Asia continuation leg.",
    )


def make_nq_ldn_config() -> StrategyConfig:
    session = SessionConfig(
        name="LDN",
        orb_start="03:00",
        orb_end="03:30",
        entry_start="03:30",
        entry_end="08:25",
        flat_start="08:20",
        flat_end="08:25",
        stop_atr_pct=1.5,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        rr=6.0,
        tp1_ratio=0.7,
        atr_length=10,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=NQ,
        direction_filter="long",
        name="nq_ldn_cont",
        notes="Existing NQ LDN continuation leg.",
    )


def make_nq_asia_lsi_config() -> StrategyConfig:
    session = SessionConfig(
        name="Asia",
        rth_start="20:00",
        entry_start="20:40",
        entry_end="23:30",
        flat_start="04:00",
        flat_end="07:00",
        min_gap_atr_pct=1.75,
    )
    return StrategyConfig(
        strategy="lsi",
        rr=2.0,
        tp1_ratio=0.7,
        atr_length=40,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=NQ,
        direction_filter="long",
        lsi_n_left=8,
        lsi_n_right=2,
        lsi_fvg_window_left=15,
        lsi_fvg_window_right=2,
        lsi_entry_mode="close",
        name="nq_asia_lsi",
        notes="Existing NQ Asia LSI leg.",
    )


def make_nq_ny_lsi_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    return StrategyConfig(
        strategy="lsi",
        rr=3.0,
        tp1_ratio=0.3,
        atr_length=10,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=NQ,
        direction_filter="long",
        excluded_days=(2, 3),
        lsi_n_left=8,
        lsi_n_right=60,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=5,
        lsi_entry_mode="fvg_limit",
        name="nq_ny_lsi",
        notes="Existing NQ NY LSI leg.",
    )


def apply_g5_gate(ldn_trades, asia_legs_trades):
    asia_tp1_dates = set()
    for trades in asia_legs_trades:
        for trade in trades:
            if trade.exit_type == EXIT_NO_FILL:
                continue
            if trade.exit_type in TP1_EXIT_TYPES:
                asia_date = datetime.strptime(trade.date, "%Y-%m-%d")
                ldn_date = asia_date + timedelta(days=1)
                while ldn_date.weekday() >= 5:
                    ldn_date += timedelta(days=1)
                asia_tp1_dates.add(ldn_date.strftime("%Y-%m-%d"))

    kept = []
    for trade in ldn_trades:
        if trade.exit_type == EXIT_NO_FILL or trade.date not in asia_tp1_dates:
            kept.append(trade)
    return kept


def run_leg(label, config, df_5m, df_1m, df_1s, regime_calendar):
    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)

    if label == "bull_specialist":
        trades = apply_dow_filter(trades, set(config.excluded_days))
        trades = apply_bull_hh_hl_vwap_gate(trades, df_5m, config.sessions[0])
        trades = filter_trades_by_low_confidence(trades, regime_calendar, include_low_confidence=False)
        trades = filter_trades_by_regime(trades, regime_calendar, include={"bull"})
    elif label == "nq_asia":
        trades = apply_dow_filter(trades, set(config.excluded_days))
    elif label == "nq_ny_lsi":
        trades = apply_dow_filter(trades, set(config.excluded_days))

    return trades


def merge_trade_streams(streams: list[list]) -> list:
    merged = []
    for trades in streams:
        merged.extend(trades)
    return sorted(merged, key=lambda t: (t.date, t.fill_time or "", t.signal_bar, t.fill_bar, t.exit_time or ""))


def combo_scorecard(outcomes: pd.DataFrame) -> dict:
    resolved = outcomes[outcomes["outcome"].isin(["payout", "breach"])].copy()
    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    return {
        "resolved_rate": round(len(resolved) / len(outcomes), 4) if len(outcomes) else 0.0,
        "average_days_to_resolution": round(float(resolved["calendar_days_to_outcome"].mean()), 2) if not resolved.empty else None,
        "median_days_to_resolution": round(float(resolved["calendar_days_to_outcome"].median()), 2) if not resolved.empty else None,
        "average_days_to_breach": round(float(breaches["calendar_days_to_outcome"].mean()), 2) if not breaches.empty else None,
        "average_days_to_payout": round(float(payouts["calendar_days_to_outcome"].mean()), 2) if not payouts.empty else None,
    }


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull Specialist Combo Resolution")
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
    all_start_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=True)
    holdout_start_dates = [d for d in all_start_dates if pd.Timestamp(d) >= pd.Timestamp(HOLDOUT_START)]

    funded_profile = FundedFirstPayoutProfile(
        challenge_fee=150.0,
        starting_balance_usd=50_000.0,
        trailing_drawdown_usd=2_000.0,
        max_trailing_breach_usd=50_000.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
        risk_post_payout_usd=250.0,
    )

    leg_configs = {
        "bull_specialist": make_bull_specialist_config(),
        "nq_asia": make_nq_asia_config(),
        "nq_ldn": make_nq_ldn_config(),
        "nq_asia_lsi": make_nq_asia_lsi_config(),
        "nq_ny_lsi": make_nq_ny_lsi_config(),
    }

    print("\nRunning leg backtests...", flush=True)
    leg_trades = {}
    for label, config in leg_configs.items():
        leg_trades[label] = run_leg(label, config, df_5m, df_1m, df_1s, regime_calendar)

    if "nq_ldn" in leg_trades:
        asia_reference_streams = [
            leg_trades[name] for name in ("nq_asia", "nq_asia_lsi") if name in leg_trades
        ]
        leg_trades["nq_ldn"] = apply_g5_gate(leg_trades["nq_ldn"], asia_reference_streams)

    optional_legs = ["nq_asia", "nq_ldn", "nq_asia_lsi", "nq_ny_lsi"]
    combo_defs = []
    for r in range(0, len(optional_legs) + 1):
        for extra in combinations(optional_legs, r):
            combo_defs.append(("bull_specialist",) + extra)

    rows = []
    details = {}
    for combo in combo_defs:
        combo_name = " + ".join(combo)
        combined = merge_trade_streams([leg_trades[name] for name in combo])
        holdout_combined = [t for t in combined if t.date >= HOLDOUT_START]

        outcomes = simulate_funded_first_payouts(combo_name, combined, all_start_dates, funded_profile)
        holdout_outcomes = simulate_funded_first_payouts(combo_name, holdout_combined, holdout_start_dates, funded_profile)
        score = build_funded_first_payout_scorecard(outcomes, funded_profile)
        holdout_score = build_funded_first_payout_scorecard(holdout_outcomes, funded_profile)
        resolution = combo_scorecard(outcomes)
        holdout_resolution = combo_scorecard(holdout_outcomes)

        filled_count = sum(1 for t in combined if t.exit_type != EXIT_NO_FILL)
        rows.append(
            {
                "combo_name": combo_name,
                "n_legs": len(combo),
                "filled_trades": filled_count,
                "payout_rate": score["payout_rate"],
                "breach_rate": score["breach_rate"],
                "open_rate": score["open_rate"],
                "average_days_to_payout": score["average_days_to_payout"],
                "average_days_to_resolution": resolution["average_days_to_resolution"],
                "average_days_to_breach": resolution["average_days_to_breach"],
                "average_first_payout_amount_usd": score["average_first_payout_amount_usd"],
                "ev_per_start_usd": score["ev_per_start_usd"],
                "holdout_payout_rate": holdout_score["payout_rate"],
                "holdout_breach_rate": holdout_score["breach_rate"],
                "holdout_average_days_to_payout": holdout_score["average_days_to_payout"],
                "holdout_average_days_to_resolution": holdout_resolution["average_days_to_resolution"],
                "holdout_ev_per_start_usd": holdout_score["ev_per_start_usd"],
            }
        )
        details[combo_name] = {
            "legs": list(combo),
            "scorecard": score,
            "resolution": resolution,
            "holdout_scorecard": holdout_score,
            "holdout_resolution": holdout_resolution,
        }

    ranking_df = pd.DataFrame(rows).sort_values(
        by=[
            "average_days_to_resolution",
            "payout_rate",
            "ev_per_start_usd",
            "holdout_payout_rate",
        ],
        ascending=[True, False, False, False],
    )
    ranking_df.to_csv(output_dir / "combo_ranking.csv", index=False)

    practical_df = ranking_df[
        (ranking_df["ev_per_start_usd"] > 0)
        & (ranking_df["holdout_payout_rate"] > 0)
        & ranking_df["average_first_payout_amount_usd"].fillna(0) >= 300
    ].copy()
    practical_df.to_csv(output_dir / "combo_ranking_practical.csv", index=False)

    best = practical_df.iloc[0] if not practical_df.empty else ranking_df.iloc[0]

    summary_lines = [
        "# NQ Bull Specialist Combo Resolution",
        "",
        "## Funded Account Model",
        "",
        "- Challenge cost: `$150`.",
        "- Starting balance: `$50,000`.",
        "- Trailing drawdown: `$2,000`, updated from highest realized EOD balance.",
        "- Trailing breach cap: never above `$50,000`.",
        "- First withdrawable payout: everything above `$52,000`.",
        "- Risk: `$500` per trade before first payout, `$250` after.",
        "",
        "## Combo Search",
        "",
        "- Bull specialist fast-payout winner was mandatory in every combo.",
        "- Optional added legs: `nq_asia`, `nq_ldn`, `nq_asia_lsi`, `nq_ny_lsi`.",
        f"- Combos tested: `{len(combo_defs)}`.",
        "",
        "## Best Practical Combo",
        "",
        f"- Combo: `{best['combo_name']}`.",
        f"- Filled trades: `{int(best['filled_trades'])}`.",
        f"- Payout rate: `{best['payout_rate']}` | breach rate `{best['breach_rate']}`.",
        f"- Average days to payout: `{best['average_days_to_payout']}`.",
        f"- Average days to resolution: `{best['average_days_to_resolution']}`.",
        f"- Average first payout amount: `{best['average_first_payout_amount_usd']}`.",
        f"- EV per start: `{best['ev_per_start_usd']}`.",
        f"- Holdout payout rate: `{best['holdout_payout_rate']}` | holdout EV/start `{best['holdout_ev_per_start_usd']}`.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    write_json(
        output_dir / "combo_details.json",
        {
            "funded_profile": funded_profile.__dict__,
            "details": details,
        },
    )

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
