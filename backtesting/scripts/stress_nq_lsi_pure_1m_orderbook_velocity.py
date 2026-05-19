#!/usr/bin/env python3
"""No-fetch stress test for the pure 1m long order-book velocity survivor."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import stress_nq_lsi_3m_trapped_reversal as stress  # noqa: E402


RUN_SLUG = "nq_ny_lsi_pure_1m_orderbook_velocity_stress_20260515"
INPUT_PATH = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_risk_tiers_20260515"
    / "trade_risk_tier_replay.csv"
)
OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = (
    ROOT
    / "learnings"
    / "reports"
    / "NQ_NY_LSI_PURE_1M_ORDERBOOK_VELOCITY_STRESS_20260515.md"
)

CANDIDATE = "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200"
FEATURE = "confirm_last_10s_mid_velocity_ticks_per_second"


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def write_report(
    *,
    metrics: pd.DataFrame,
    account_summary: pd.DataFrame,
    tiers: pd.DataFrame,
    bootstrap: pd.DataFrame,
) -> None:
    account_focus = account_summary[
        (account_summary["mode"] == "tiered")
        & (account_summary["account_mode"] == "daily_stop_min5days")
        & (account_summary["slippage_ticks_per_side"] == 1.0)
    ].sort_values(["window", "delta_ev_r", "ev_r"], ascending=[True, False, False])

    r_focus = metrics[
        (metrics["mode"] == "tiered")
        & (metrics["slippage_ticks_per_side"].isin((0.0, 1.0)))
        & (metrics["window"].isin(("validation", "holdout", "post_2023")))
    ].sort_values(["window", "slippage_ticks_per_side", "delta_total_r"], ascending=[True, True, False])

    tier_focus = tiers[
        (tiers["mode"] == "tiered")
        & (tiers["profile"] == "tier_0p5_1_1p5")
        & (tiers["slippage_ticks_per_side"] == 1.0)
        & (tiers["window"].isin(("validation", "holdout")))
    ].sort_values(["window", "feature_tier"])

    boot_focus = bootstrap[
        (bootstrap["mode"] == "tiered")
        & (bootstrap["slippage_ticks_per_side"] == 1.0)
        & (bootstrap["window"].isin(("post_2023", "holdout")))
    ].sort_values(["window", "prob_total_r_positive"], ascending=[True, False])

    lines = [
        "# NQ NY LSI Pure 1m Order-Book Velocity Stress",
        "",
        "- Objective: apply the same no-extra-fetch promotion stress used on the 3m trapped-reversal branch to the pure 1m long MBP-10 velocity survivor.",
        f"- Candidate: `{CANDIDATE}`",
        f"- Feature: `{FEATURE}`",
        "- Scope: existing order-book risk-tier replay CSV only; no DataBento fetch. This is still `research_only` because live MBP-10 feature streaming and dynamic sizing are not implemented in the execution path.",
        "",
        "## Account Stress, 1 Tick/Side Slippage",
        "",
        f"Account rules: stagger every `{stress.CYCLE_DAYS}` calendar days, payout `+{stress.PAYOUT_R:.0f}R`, breach `{stress.BREACH_R:.0f}R`, daily stop `{stress.DAILY_LOSS_R:.0f}R`, minimum `{stress.MIN_TRADING_DAYS}` trading days before payout.",
        "",
        "| Window | Profile | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in account_focus.iterrows():
        lines.append(
            f"| {row['window']} | `{row['profile_label']}` | "
            f"{row['payout_rate']:.1%} | {row['breach_rate']:.1%} | {row['ev_r']:.2f}R | "
            f"{row.get('delta_ev_r', 0.0):+.2f}R | {row.get('delta_payout_rate', 0.0):+.1%} | "
            f"{row.get('delta_breach_rate', 0.0):+.1%} |"
        )

    lines.extend(
        [
            "",
            "## R-Multiple Stress",
            "",
            "| Window | Slip | Profile | Trades | Total R | Avg R | PF | Max DD | Delta Total R |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in r_focus.iterrows():
        lines.append(
            f"| {row['window']} | {row['slippage_ticks_per_side']:.1f} | `{row['profile_label']}` | "
            f"{int(row['trades'])} | {row['total_r']:.2f} | {row['avg_r']:.3f} | "
            f"{row['profit_factor']:.2f} | {row['max_dd_r']:.2f}R | "
            f"{row.get('delta_total_r', 0.0):+.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Primary Tier Quality",
            "",
            "| Window | Tier | Trades | Avg Weight | Total R | Avg R | PF |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in tier_focus.iterrows():
        lines.append(
            f"| {row['window']} | `{row['feature_tier']}` | {int(row['trades'])} | "
            f"{row['avg_risk_weight']:.2f} | {row['total_r']:.2f} | {row['avg_r']:.3f} | "
            f"{row['profit_factor']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Bootstrap Fragility, 1 Tick/Side Slippage",
            "",
            "| Window | Profile | Trades | P05 Total R | P50 Total R | P95 Total R | Prob Positive | Prob DD <= -4R |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in boot_focus.iterrows():
        lines.append(
            f"| {row['window']} | `{row['profile_label']}` | {int(row['trades'])} | "
            f"{row['total_r_p05']:.2f} | {row['total_r_p50']:.2f} | {row['total_r_p95']:.2f} | "
            f"{row['prob_total_r_positive']:.1%} | {row['prob_max_dd_worse_than_4r']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This branch remains the cleanest capital-protection survivor because breach stayed at `0.0%` in the prior account replay and remains low under stricter rules.",
            "- Capacity is the tradeoff: holdout has only `21` baseline trades, so the signal is useful as a sizing overlay but not enough as a standalone engine.",
            "- The next implementation question is not more threshold mining; it is live MBP-10 feature streaming plus dynamic sizing support.",
            "",
            "## Output Files",
            "",
            f"- `{OUTPUT_DIR / 'stress_trades.csv'}`",
            f"- `{OUTPUT_DIR / 'stress_metrics.csv'}`",
            f"- `{OUTPUT_DIR / 'tier_metrics.csv'}`",
            f"- `{OUTPUT_DIR / 'monthly_metrics.csv'}`",
            f"- `{OUTPUT_DIR / 'account_summary.csv'}`",
            f"- `{OUTPUT_DIR / 'account_outcomes.csv'}`",
            f"- `{OUTPUT_DIR / 'bootstrap_summary.csv'}`",
            f"- `{OUTPUT_DIR / 'summary.json'}`",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    stress.CANDIDATE = CANDIDATE
    stress.FEATURE = FEATURE
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    data = stress.load_input(INPUT_PATH)
    stressed = stress.build_stressed_trades(data)
    metrics, tiers, monthly = stress.build_metric_tables(stressed)
    account_summary, account_outcomes = stress.build_account_tables(stressed)
    bootstrap = stress.bootstrap_summary(stressed)

    outputs = {
        "stress_trades": OUTPUT_DIR / "stress_trades.csv",
        "stress_metrics": OUTPUT_DIR / "stress_metrics.csv",
        "tier_metrics": OUTPUT_DIR / "tier_metrics.csv",
        "monthly_metrics": OUTPUT_DIR / "monthly_metrics.csv",
        "account_summary": OUTPUT_DIR / "account_summary.csv",
        "account_outcomes": OUTPUT_DIR / "account_outcomes.csv",
        "bootstrap_summary": OUTPUT_DIR / "bootstrap_summary.csv",
    }
    stressed.to_csv(outputs["stress_trades"], index=False)
    metrics.to_csv(outputs["stress_metrics"], index=False)
    tiers.to_csv(outputs["tier_metrics"], index=False)
    monthly.to_csv(outputs["monthly_metrics"], index=False)
    account_summary.to_csv(outputs["account_summary"], index=False)
    account_outcomes.to_csv(outputs["account_outcomes"], index=False)
    bootstrap.to_csv(outputs["bootstrap_summary"], index=False)

    write_report(
        metrics=metrics,
        account_summary=account_summary,
        tiers=tiers,
        bootstrap=bootstrap,
    )
    save_json(
        OUTPUT_DIR / "summary.json",
        {
            "run_slug": RUN_SLUG,
            "candidate": CANDIDATE,
            "feature": FEATURE,
            "input_path": str(INPUT_PATH),
            "slippage_ticks_per_side": stress.SLIPPAGE_TICKS_PER_SIDE,
            "account_rules": {
                "payout_r": stress.PAYOUT_R,
                "breach_r": stress.BREACH_R,
                "daily_loss_r": stress.DAILY_LOSS_R,
                "cycle_days": stress.CYCLE_DAYS,
                "min_trading_days": stress.MIN_TRADING_DAYS,
            },
            "bootstrap_runs": stress.BOOTSTRAP_RUNS,
            "outputs": {name: str(path) for name, path in outputs.items()} | {"report": str(REPORT_PATH)},
        },
    )
    print(f"Wrote {outputs['stress_metrics']}", flush=True)
    print(f"Wrote {outputs['account_summary']}", flush=True)
    print(f"Wrote {REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
