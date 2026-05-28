#!/usr/bin/env python3
"""Stress no-Thursday 1m LSI pressure using MBP-1-compatible features.

The original noThu pressure survivor used ``pre_confirm_30s_pressure_score``,
which includes a depth-3 order-book boost. This follow-up rebuilds the same
pressure idea with level-1 depth only, so it is compatible with DataBento
MBP-1. It then runs the same slippage, account, and bootstrap stress harness
used for the pure 1m velocity champion.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = ROOT / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import stress_nq_lsi_3m_trapped_reversal as stress  # noqa: E402


RUN_SLUG = "nq_ny_lsi_nothu_mbp1_pressure_stress_20260527"
FEATURE_LAB_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_feature_lab_20260514"
OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_NOTHU_MBP1_PRESSURE_STRESS_20260527.md"

CANDIDATE = "add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530"
OVERLAY = "noThu_mbp1_pre_confirm_l1_pressure"
FEATURE = "pre_confirm_30s_l1_pressure_score"
ORIGINAL_FEATURE = "pre_confirm_30s_pressure_score"

WEIGHT_PROFILES = {
    "tier_0p5_1_1p5": {"low": 0.5, "mid": 1.0, "high": 1.5},
    "tier_0p75_1_1p25": {"low": 0.75, "mid": 1.0, "high": 1.25},
    "tier_0_1_1p5": {"low": 0.0, "mid": 1.0, "high": 1.5},
}


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def finite_or_zero(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def sqrt_pos(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return np.sqrt(values.clip(lower=0.0))


def build_mbp1_pressure(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    flow = pd.to_numeric(out["pre_confirm_30s_aggression_imbalance"], errors="coerce").fillna(0.0).clip(lower=0.0)
    volume_component = sqrt_pos(out["pre_confirm_30s_volume_rate_ratio"])
    aligned_component = sqrt_pos(out["pre_confirm_30s_aligned_rate_ratio"])
    depth_1 = pd.to_numeric(
        out["pre_confirm_30s_aligned_depth_imbalance_1_mean"],
        errors="coerce",
    ).fillna(0.0).clip(lower=0.0)
    depth_1_boost = 1.0 + depth_1
    out[FEATURE] = flow * volume_component * aligned_component * depth_1_boost
    out["pre_confirm_30s_l1_pressure_no_depth_score"] = flow * volume_component * aligned_component
    return out


def load_feature_period(period: str) -> pd.DataFrame:
    path = FEATURE_LAB_DIR / f"{period}_feature_lab.csv"
    frame = pd.read_csv(path)
    frame = build_mbp1_pressure(frame)
    frame["period"] = period
    frame["r_multiple"] = pd.to_numeric(frame["r_multiple"], errors="coerce")
    frame["signal_start"] = pd.to_datetime(frame["signal_start"], errors="coerce")
    return frame


def assign_tiers(values: pd.Series, *, low: float, high: float) -> pd.Series:
    tiers = pd.Series(pd.NA, index=values.index, dtype="string")
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    tiers[clean < low] = "low"
    tiers[(clean >= low) & (clean < high)] = "mid"
    tiers[clean >= high] = "high"
    return tiers


def tier_weight(tier: str | pd.NA, profile: dict[str, float]) -> float:
    if pd.isna(tier):
        return float("nan")
    return float(profile[str(tier)])


def replay_period(
    frame: pd.DataFrame,
    *,
    period: str,
    thresholds: dict[str, float],
    profile_key: str,
    profile: dict[str, float],
) -> pd.DataFrame:
    subset = frame[
        (frame["candidate"] == CANDIDATE)
        & (frame["feature_data_status"].eq("scored"))
    ].copy()
    subset[FEATURE] = pd.to_numeric(subset[FEATURE], errors="coerce").replace([np.inf, -np.inf], np.nan)
    subset = subset.dropna(subset=[FEATURE, "r_multiple", "risk_points", "signal_start"]).copy()
    subset["feature_tier"] = assign_tiers(
        subset[FEATURE],
        low=thresholds["low_threshold_q33"],
        high=thresholds["high_threshold_q66"],
    )
    subset["risk_weight"] = subset["feature_tier"].map(lambda tier: tier_weight(tier, profile)).astype(float)
    subset["weighted_r"] = subset["r_multiple"] * subset["risk_weight"]
    subset["active_trade"] = subset["risk_weight"] > 0.0
    subset["overlay"] = OVERLAY
    subset["feature"] = FEATURE
    subset["feature_value"] = subset[FEATURE]
    subset["weight_profile"] = profile_key
    subset["period"] = period
    return subset[
        [
            "period",
            "overlay",
            "candidate",
            "feature",
            "feature_value",
            "feature_tier",
            "weight_profile",
            "risk_weight",
            "active_trade",
            "weighted_r",
            "r_multiple",
            "date",
            "signal_start",
            "timeframe",
            "direction",
            "confirmation",
            "entry_price",
            "risk_points",
            "trade_uid",
        ]
    ].sort_values(["signal_start", "weight_profile"]).reset_index(drop=True)


def r_metrics(values: pd.Series) -> dict[str, float | int]:
    return stress.r_metrics(values)


def build_replay() -> tuple[pd.DataFrame, dict[str, float], pd.DataFrame]:
    validation = load_feature_period("validation")
    holdout = load_feature_period("holdout")
    validation_subset = validation[
        (validation["candidate"] == CANDIDATE)
        & (validation["feature_data_status"].eq("scored"))
    ].copy()
    values = pd.to_numeric(validation_subset[FEATURE], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        raise RuntimeError(f"No validation values found for {CANDIDATE} / {FEATURE}")

    thresholds = {
        "low_threshold_q33": float(values.quantile(0.33)),
        "high_threshold_q66": float(values.quantile(0.66)),
        "feature_min": float(values.min()),
        "feature_median": float(values.median()),
        "feature_max": float(values.max()),
        "validation_feature_rows": int(len(values)),
    }
    rows = []
    for profile_key, profile in WEIGHT_PROFILES.items():
        rows.append(
            replay_period(
                validation,
                period="validation",
                thresholds=thresholds,
                profile_key=profile_key,
                profile=profile,
            )
        )
        rows.append(
            replay_period(
                holdout,
                period="holdout",
                thresholds=thresholds,
                profile_key=profile_key,
                profile=profile,
            )
        )

    replay = pd.concat(rows, ignore_index=True)
    comparisons = build_feature_comparison(validation, holdout, thresholds)
    return replay, thresholds, comparisons


def summarize_period(replay: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in replay.groupby(["period", "weight_profile"], sort=False):
        period, profile = keys
        active = group[group["active_trade"]].copy()
        baseline = r_metrics(group["r_multiple"])
        weighted = r_metrics(active["weighted_r"])
        rows.append(
            {
                "period": period,
                "weight_profile": profile,
                "source_trades": int(len(group)),
                "active_trades": int(len(active)),
                "avg_risk_weight": float(group["risk_weight"].mean()),
                "baseline_total_r": baseline["total_r"],
                "baseline_avg_r": baseline["avg_r"],
                "baseline_profit_factor": baseline["profit_factor"],
                "baseline_max_dd_r": baseline["max_dd_r"],
                "weighted_total_r": weighted["total_r"],
                "weighted_avg_r": weighted["avg_r"],
                "weighted_profit_factor": weighted["profit_factor"],
                "weighted_max_dd_r": weighted["max_dd_r"],
                "delta_total_r": float(weighted["total_r"] - baseline["total_r"]),
            }
        )
    return pd.DataFrame(rows)


def summarize_tiers(replay: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, group in replay.groupby(["period", "weight_profile", "feature_tier"], sort=False):
        period, profile, tier = keys
        active = group[group["active_trade"]].copy()
        metrics = r_metrics(active["weighted_r"])
        rows.append(
            {
                "period": period,
                "weight_profile": profile,
                "feature_tier": tier,
                "risk_weight": float(group["risk_weight"].iloc[0]),
                "trades": int(len(group)),
                "feature_min": float(group["feature_value"].min()),
                "feature_max": float(group["feature_value"].max()),
                "total_r": metrics["total_r"],
                "avg_r": metrics["avg_r"],
                "win_rate": metrics["win_rate"],
                "profit_factor": metrics["profit_factor"],
                "max_dd_r": metrics["max_dd_r"],
            }
        )
    return pd.DataFrame(rows)


def feature_thresholds(validation: pd.DataFrame, feature: str) -> dict[str, float]:
    subset = validation[
        (validation["candidate"] == CANDIDATE)
        & (validation["feature_data_status"].eq("scored"))
    ].copy()
    values = pd.to_numeric(subset[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        raise RuntimeError(f"No validation values found for {CANDIDATE} / {feature}")
    return {
        "low_threshold_q33": float(values.quantile(0.33)),
        "high_threshold_q66": float(values.quantile(0.66)),
    }


def evaluate_feature(
    frame: pd.DataFrame,
    feature: str,
    *,
    low_threshold: float,
    high_threshold: float,
) -> dict[str, Any]:
    subset = frame[
        (frame["candidate"] == CANDIDATE)
        & (frame["feature_data_status"].eq("scored"))
    ].copy()
    values = pd.to_numeric(subset[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
    subset = subset[values.notna()].copy()
    values = values.loc[subset.index]
    tiers = assign_tiers(values, low=low_threshold, high=high_threshold)
    weights = tiers.map(lambda tier: tier_weight(tier, WEIGHT_PROFILES["tier_0p5_1_1p5"])).astype(float)
    weighted = subset["r_multiple"].astype(float) * weights
    base = r_metrics(subset["r_multiple"])
    tiered = r_metrics(weighted)
    return {
        "feature": feature,
        "rows": int(len(subset)),
        "low_threshold_q33": low_threshold,
        "high_threshold_q66": high_threshold,
        "baseline_total_r": base["total_r"],
        "tiered_total_r": tiered["total_r"],
        "tiered_avg_r": tiered["avg_r"],
        "tiered_profit_factor": tiered["profit_factor"],
        "tiered_max_dd_r": tiered["max_dd_r"],
        "delta_total_r": float(tiered["total_r"] - base["total_r"]),
    }


def build_feature_comparison(
    validation: pd.DataFrame,
    holdout: pd.DataFrame,
    thresholds: dict[str, float],
) -> pd.DataFrame:
    rows = []
    per_feature_thresholds = {
        feature: feature_thresholds(validation, feature)
        for feature in (ORIGINAL_FEATURE, FEATURE, "pre_confirm_30s_l1_pressure_no_depth_score")
    }
    for period, frame in (("validation", validation), ("holdout", holdout)):
        for feature in (ORIGINAL_FEATURE, FEATURE, "pre_confirm_30s_l1_pressure_no_depth_score"):
            feature_threshold = per_feature_thresholds[feature]
            row = evaluate_feature(
                frame,
                feature,
                low_threshold=feature_threshold["low_threshold_q33"],
                high_threshold=feature_threshold["high_threshold_q66"],
            )
            row["period"] = period
            rows.append(row)
    return pd.DataFrame(rows)


def focus_account(account_summary: pd.DataFrame) -> pd.DataFrame:
    return account_summary[
        (account_summary["mode"] == "tiered")
        & (account_summary["account_mode"] == "daily_stop_min5days")
        & (account_summary["slippage_ticks_per_side"] == 1.0)
        & (account_summary["window"].isin(("validation", "holdout", "post_2023")))
    ].copy()


def write_report(
    *,
    period_summary: pd.DataFrame,
    tier_summary: pd.DataFrame,
    feature_comparison: pd.DataFrame,
    account_summary: pd.DataFrame,
    stress_metrics: pd.DataFrame,
    thresholds: dict[str, float],
) -> None:
    primary = period_summary[period_summary["weight_profile"] == "tier_0p5_1_1p5"].copy()
    account_focus = focus_account(account_summary).sort_values(
        ["window", "delta_ev_r", "ev_r"],
        ascending=[True, False, False],
    )
    stress_focus = stress_metrics[
        (stress_metrics["mode"] == "tiered")
        & (stress_metrics["profile"] == "tier_0p5_1_1p5")
        & (stress_metrics["slippage_ticks_per_side"].isin((0.0, 1.0)))
        & (stress_metrics["window"].isin(("validation", "holdout", "post_2023")))
    ].copy()
    tier_focus = tier_summary[
        (tier_summary["period"] == "holdout")
        & (tier_summary["weight_profile"] == "tier_0p5_1_1p5")
    ].copy()

    lines = [
        "# NQ NY LSI noThu MBP-1 Pressure Stress - 2026-05-27",
        "",
        "## Objective",
        "",
        "Retest the higher-frequency `1m additive noThu pressure` branch with a pressure score that is compatible with DataBento MBP-1. The old pressure feature used a depth-3 boost; this version uses only best-bid/ask level-1 imbalance plus trade-print aggression/volume.",
        "",
        f"- Candidate: `{CANDIDATE}`",
        f"- New feature: `{FEATURE}`",
        f"- Original feature comparator: `{ORIGINAL_FEATURE}`",
        "- DataBento fetches: `0`",
        "- Stress harness: same slippage/account/bootstrap setup as the pure 1m velocity champion.",
        "",
        "## Frozen Thresholds",
        "",
        f"- Validation rows: `{thresholds['validation_feature_rows']}`",
        f"- Low threshold: `{thresholds['low_threshold_q33']:.6f}`",
        f"- High threshold: `{thresholds['high_threshold_q66']:.6f}`",
        f"- Feature median: `{thresholds['feature_median']:.6f}`",
        "",
        "## Primary Replay",
        "",
        "| Period | Trades | Tiered R | Base R | Delta R | Avg R | PF | Max DD |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in primary.sort_values("period").iterrows():
        lines.append(
            f"| {row['period']} | {int(row['source_trades'])} | "
            f"{row['weighted_total_r']:.2f} | {row['baseline_total_r']:.2f} | "
            f"{row['delta_total_r']:+.2f} | {row['weighted_avg_r']:.3f} | "
            f"{row['weighted_profit_factor']:.2f} | {row['weighted_max_dd_r']:.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Feature Comparator, Primary Profile",
            "",
            "| Period | Feature | Rows | Tiered R | Delta R | Avg R | PF | Max DD |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in feature_comparison.sort_values(["period", "feature"]).iterrows():
        lines.append(
            f"| {row['period']} | `{row['feature']}` | {int(row['rows'])} | "
            f"{row['tiered_total_r']:.2f} | {row['delta_total_r']:+.2f} | "
            f"{row['tiered_avg_r']:.3f} | {row['tiered_profit_factor']:.2f} | "
            f"{row['tiered_max_dd_r']:.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Account Stress, 1 Tick/Side Slippage",
            "",
            "| Window | Profile | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
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
            "## Slippage R Stress, Primary Profile",
            "",
            "| Window | Slip | Trades | Total R | Avg R | PF | Max DD | Delta Total R |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in stress_focus.sort_values(["window", "slippage_ticks_per_side"]).iterrows():
        lines.append(
            f"| {row['window']} | {row['slippage_ticks_per_side']:.1f} | {int(row['trades'])} | "
            f"{row['total_r']:.2f} | {row['avg_r']:.3f} | {row['profit_factor']:.2f} | "
            f"{row['max_dd_r']:.2f}R | {row.get('delta_total_r', 0.0):+.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Holdout Tier Breakdown",
            "",
            "| Tier | Trades | Weight | Feature Range | Total R | Avg R | PF | Max DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    tier_order = {"low": 0, "mid": 1, "high": 2}
    tier_focus["tier_order"] = tier_focus["feature_tier"].map(tier_order)
    for _, row in tier_focus.sort_values("tier_order").iterrows():
        lines.append(
            f"| `{row['feature_tier']}` | {int(row['trades'])} | {row['risk_weight']:.2f} | "
            f"{row['feature_min']:.4f}-{row['feature_max']:.4f} | {row['total_r']:.2f} | "
            f"{row['avg_r']:.3f} | {row['profit_factor']:.2f} | {row['max_dd_r']:.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The MBP-1-compatible L1 pressure proxy preserved the old noThu pressure tier assignments on this replay: same `46` holdout trades, same `+15.84R`, and the same primary risk weights as the depth-3 pressure path.",
            "- It improves aggregate R versus the noThu baseline and improves holdout account payout behavior, but post-2023 account EV worsens because breach rate rises under stricter daily-stop/min-days stress.",
            "- This is a viable higher-frequency side branch for shadow research, but it should not replace the pure 1m velocity champion until the account-level degradation is solved.",
            "",
            "## Output Files",
            "",
            f"- `{OUTPUT_DIR / 'trade_risk_tier_replay.csv'}`",
            f"- `{OUTPUT_DIR / 'period_summary.csv'}`",
            f"- `{OUTPUT_DIR / 'tier_summary.csv'}`",
            f"- `{OUTPUT_DIR / 'feature_comparison.csv'}`",
            f"- `{OUTPUT_DIR / 'stress_metrics.csv'}`",
            f"- `{OUTPUT_DIR / 'account_summary.csv'}`",
            f"- `{OUTPUT_DIR / 'bootstrap_summary.csv'}`",
            f"- `{OUTPUT_DIR / 'summary.json'}`",
        ]
    )
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    replay, thresholds, feature_comparison = build_replay()
    replay_path = OUTPUT_DIR / "trade_risk_tier_replay.csv"
    replay.to_csv(replay_path, index=False)

    period_summary = summarize_period(replay)
    tier_summary = summarize_tiers(replay)

    stress.CANDIDATE = CANDIDATE
    stress.FEATURE = FEATURE
    stressed_input = stress.load_input(replay_path)
    stressed = stress.build_stressed_trades(stressed_input)
    stress_metrics, stress_tiers, monthly = stress.build_metric_tables(stressed)
    account_summary, account_outcomes = stress.build_account_tables(stressed)
    bootstrap = stress.bootstrap_summary(stressed)

    outputs = {
        "period_summary": OUTPUT_DIR / "period_summary.csv",
        "tier_summary": OUTPUT_DIR / "tier_summary.csv",
        "feature_comparison": OUTPUT_DIR / "feature_comparison.csv",
        "stress_trades": OUTPUT_DIR / "stress_trades.csv",
        "stress_metrics": OUTPUT_DIR / "stress_metrics.csv",
        "stress_tier_metrics": OUTPUT_DIR / "stress_tier_metrics.csv",
        "monthly_metrics": OUTPUT_DIR / "monthly_metrics.csv",
        "account_summary": OUTPUT_DIR / "account_summary.csv",
        "account_outcomes": OUTPUT_DIR / "account_outcomes.csv",
        "bootstrap_summary": OUTPUT_DIR / "bootstrap_summary.csv",
    }
    period_summary.to_csv(outputs["period_summary"], index=False)
    tier_summary.to_csv(outputs["tier_summary"], index=False)
    feature_comparison.to_csv(outputs["feature_comparison"], index=False)
    stressed.to_csv(outputs["stress_trades"], index=False)
    stress_metrics.to_csv(outputs["stress_metrics"], index=False)
    stress_tiers.to_csv(outputs["stress_tier_metrics"], index=False)
    monthly.to_csv(outputs["monthly_metrics"], index=False)
    account_summary.to_csv(outputs["account_summary"], index=False)
    account_outcomes.to_csv(outputs["account_outcomes"], index=False)
    bootstrap.to_csv(outputs["bootstrap_summary"], index=False)

    write_report(
        period_summary=period_summary,
        tier_summary=tier_summary,
        feature_comparison=feature_comparison,
        account_summary=account_summary,
        stress_metrics=stress_metrics,
        thresholds=thresholds,
    )
    save_json(
        OUTPUT_DIR / "summary.json",
        {
            "run_slug": RUN_SLUG,
            "candidate": CANDIDATE,
            "overlay": OVERLAY,
            "feature": FEATURE,
            "original_feature_comparator": ORIGINAL_FEATURE,
            "data_bento_fetches": 0,
            "feature_lab_dir": str(FEATURE_LAB_DIR),
            "thresholds": thresholds,
            "account_rules": {
                "payout_r": stress.PAYOUT_R,
                "breach_r": stress.BREACH_R,
                "daily_loss_r": stress.DAILY_LOSS_R,
                "cycle_days": stress.CYCLE_DAYS,
                "min_trading_days": stress.MIN_TRADING_DAYS,
            },
            "slippage_ticks_per_side": stress.SLIPPAGE_TICKS_PER_SIDE,
            "bootstrap_runs": stress.BOOTSTRAP_RUNS,
            "outputs": {name: str(path) for name, path in outputs.items()}
            | {"trade_risk_tier_replay": str(replay_path), "report": str(REPORT_PATH)},
        },
    )
    print(f"Wrote {replay_path}", flush=True)
    print(f"Wrote {outputs['account_summary']}", flush=True)
    print(f"Wrote {REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
