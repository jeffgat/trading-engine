#!/usr/bin/env python3
"""Replay frozen NQ NY LSI order-book risk-tier overlays.

This is the narrow follow-up to the feature lab. It does not search across
features. It freezes validation terciles for the selected order-book momentum
families and replays those unchanged on holdout.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_nq_ny_lsi_cisd_candidate_validation as val


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_ny_lsi_orderbook_risk_tiers_20260515"
DEFAULT_FEATURE_LAB_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_feature_lab_20260514"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_ORDERBOOK_RISK_TIERS_20260515.md"


@dataclasses.dataclass(frozen=True)
class OverlaySpec:
    key: str
    candidate: str
    feature: str
    family: str
    description: str


@dataclasses.dataclass(frozen=True)
class WeightProfile:
    key: str
    low: float
    mid: float
    high: float
    description: str


SPECS = (
    OverlaySpec(
        key="allDOW_additive_pre_confirm_pressure",
        candidate="add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530",
        feature="pre_confirm_30s_pressure_score",
        family="1m additive pressure",
        description="All-weekday 1m additive LSI/CISD, pre-confirm 30s pressure.",
    ),
    OverlaySpec(
        key="noThu_additive_pre_confirm_pressure",
        candidate="add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530",
        feature="pre_confirm_30s_pressure_score",
        family="1m additive pressure",
        description="No-Thursday 1m additive LSI/CISD, pre-confirm 30s pressure.",
    ),
    OverlaySpec(
        key="hourly_3m_absorption_release_first10",
        candidate="add_3m_hourly_atr12p5_b3_a7p5",
        feature="absorption_release_confirm_first_10s_score",
        family="3m absorption-release",
        description="3m hourly-sweep additive candidate, pre-confirm absorption times first-10s release.",
    ),
    OverlaySpec(
        key="hourly_3m_absorption_release_last10",
        candidate="add_3m_hourly_atr12p5_b3_a7p5",
        feature="absorption_release_confirm_last_10s_score",
        family="3m absorption-release",
        description="3m hourly-sweep additive candidate, pre-confirm absorption times last-10s release.",
    ),
    OverlaySpec(
        key="pure_1m_long_confirm_last_velocity",
        candidate="pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200",
        feature="confirm_last_10s_mid_velocity_ticks_per_second",
        family="1m pure long confirm-last velocity",
        description="Pure 1m long CISD candidate, final-10s aligned midpoint velocity.",
    ),
)

WEIGHT_PROFILES = (
    WeightProfile("tier_0p5_1_1p5", 0.5, 1.0, 1.5, "Primary sizing: weak 0.5x, normal 1.0x, strong 1.5x."),
    WeightProfile("tier_0p75_1_1p25", 0.75, 1.0, 1.25, "Conservative sizing stress."),
    WeightProfile("tier_0p5_1_2", 0.5, 1.0, 2.0, "Aggressive upside sizing stress."),
    WeightProfile("tier_0_1_1p5", 0.0, 1.0, 1.5, "Skip weak tercile, keep normal/strong sizing."),
)

ZERO_INFLATED_3M_FEATURES = (
    "absorption_release_confirm_first_10s_score",
    "absorption_release_confirm_last_10s_score",
    "absorption_release_confirm_full_score",
)


def clean_frame(path: Path, *, period: str) -> pd.DataFrame:
    frame = pd.read_csv(path).copy()
    r_multiple = pd.to_numeric(frame["r_multiple"], errors="coerce")
    signal_ts = pd.to_datetime(frame["signal_start"], errors="coerce")
    trade_date = pd.to_datetime(frame["date"], errors="coerce")
    return frame.assign(
        period=period,
        r_multiple=r_multiple,
        signal_ts=signal_ts,
        trade_date=trade_date,
        year=trade_date.dt.year,
        month=trade_date.dt.to_period("M").astype(str),
    ).copy()


def r_metrics(values: pd.Series | np.ndarray) -> dict[str, Any]:
    return val.r_metrics(pd.Series(values).dropna().to_numpy(dtype=float))


def add_prefix(row: dict[str, Any], prefix: str, values: pd.Series | np.ndarray) -> None:
    row.update({f"{prefix}_{key}": value for key, value in r_metrics(values).items()})


def assign_tiers(values: pd.Series, *, low_threshold: float, high_threshold: float) -> pd.Series:
    tiers = pd.Series(pd.NA, index=values.index, dtype="string")
    clean = values.replace([np.inf, -np.inf], np.nan)
    tiers[clean < low_threshold] = "low"
    tiers[(clean >= low_threshold) & (clean < high_threshold)] = "mid"
    tiers[clean >= high_threshold] = "high"
    return tiers


def tier_weight(tier: str | pd.NA, profile: WeightProfile) -> float:
    if pd.isna(tier):
        return float("nan")
    if tier == "low":
        return profile.low
    if tier == "mid":
        return profile.mid
    if tier == "high":
        return profile.high
    return float("nan")


def threshold_row(spec: OverlaySpec, validation: pd.DataFrame) -> dict[str, Any]:
    group = validation[
        (validation["candidate"] == spec.candidate)
        & (validation["feature_data_status"] == "scored")
    ].copy()
    if spec.feature not in group.columns:
        raise KeyError(f"Missing feature {spec.feature} in validation frame")
    values = pd.to_numeric(group[spec.feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        raise ValueError(f"No validation feature values for {spec.key}")
    return {
        "overlay": spec.key,
        "candidate": spec.candidate,
        "feature": spec.feature,
        "feature_family": spec.family,
        "description": spec.description,
        "validation_feature_rows": int(len(values)),
        "low_threshold_q33": float(values.quantile(0.33)),
        "high_threshold_q66": float(values.quantile(0.66)),
        "feature_min": float(values.min()),
        "feature_median": float(values.median()),
        "feature_max": float(values.max()),
    }


def build_trade_replay(
    frame: pd.DataFrame,
    *,
    period: str,
    spec: OverlaySpec,
    thresholds: dict[str, Any],
    profile: WeightProfile,
) -> pd.DataFrame:
    subset = frame[
        (frame["candidate"] == spec.candidate)
        & (frame["feature_data_status"] == "scored")
    ].copy()
    subset[spec.feature] = pd.to_numeric(subset[spec.feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
    subset = subset.dropna(subset=[spec.feature, "r_multiple"]).copy()
    tiers = assign_tiers(
        subset[spec.feature],
        low_threshold=float(thresholds["low_threshold_q33"]),
        high_threshold=float(thresholds["high_threshold_q66"]),
    )
    subset["overlay"] = spec.key
    subset["overlay_description"] = spec.description
    subset["feature"] = spec.feature
    subset["feature_value"] = subset[spec.feature]
    subset["feature_tier"] = tiers
    subset["weight_profile"] = profile.key
    subset["risk_weight"] = subset["feature_tier"].map(lambda item: tier_weight(item, profile)).astype(float)
    subset["weighted_r"] = subset["r_multiple"] * subset["risk_weight"]
    subset["active_trade"] = subset["risk_weight"] > 0.0
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
    ].sort_values(["signal_start", "candidate", "overlay"]).reset_index(drop=True)


def summarize_replay(replay: pd.DataFrame) -> dict[str, Any]:
    active = replay[replay["active_trade"]].copy()
    baseline = replay.copy()
    tier_counts = replay["feature_tier"].value_counts(dropna=True).to_dict()
    row: dict[str, Any] = {
        "source_trades": int(len(replay)),
        "active_trades": int(len(active)),
        "skipped_trades": int((~replay["active_trade"]).sum()),
        "active_tier_count": int(replay["feature_tier"].nunique(dropna=True)),
        "low_tier_trades": int(tier_counts.get("low", 0)),
        "mid_tier_trades": int(tier_counts.get("mid", 0)),
        "high_tier_trades": int(tier_counts.get("high", 0)),
        "avg_risk_weight_all": float(replay["risk_weight"].mean()) if len(replay) else 0.0,
        "avg_risk_weight_active": float(active["risk_weight"].mean()) if len(active) else 0.0,
        "total_risk_weight": float(active["risk_weight"].sum()) if len(active) else 0.0,
    }
    add_prefix(row, "baseline", baseline["r_multiple"])
    add_prefix(row, "weighted", active["weighted_r"])
    row["weighted_avg_r_per_1x_risk"] = (
        float(active["weighted_r"].sum() / active["risk_weight"].sum())
        if len(active) and float(active["risk_weight"].sum()) > 0.0
        else 0.0
    )
    row["delta_total_r"] = float(row["weighted_total_r"] - row["baseline_total_r"])
    row["delta_avg_r"] = float(row["weighted_avg_r"] - row["baseline_avg_r"])
    row["delta_avg_r_per_1x_risk"] = float(row["weighted_avg_r_per_1x_risk"] - row["baseline_avg_r"])
    row["delta_calmar"] = float(row["weighted_calmar"] - row["baseline_calmar"])
    if row["active_tier_count"] <= 1:
        row["risk_tier_read"] = "exposure_only_no_tier_discrimination"
    elif row["delta_avg_r_per_1x_risk"] >= 0.05:
        row["risk_tier_read"] = "supported_after_exposure_normalization"
    elif row["delta_avg_r_per_1x_risk"] > 0.0:
        row["risk_tier_read"] = "mild_after_exposure_normalization"
    else:
        row["risk_tier_read"] = "failed_after_exposure_normalization"
    return row


def build_summary(
    validation: pd.DataFrame,
    holdout: pd.DataFrame,
    thresholds: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, Any]] = []
    trade_rows: list[pd.DataFrame] = []
    tier_rows: list[dict[str, Any]] = []
    period_rows: list[dict[str, Any]] = []
    threshold_map = {row["overlay"]: row.to_dict() for _, row in thresholds.iterrows()}

    for spec in SPECS:
        for profile in WEIGHT_PROFILES:
            for period, frame in (("validation", validation), ("holdout", holdout)):
                replay = build_trade_replay(
                    frame,
                    period=period,
                    spec=spec,
                    thresholds=threshold_map[spec.key],
                    profile=profile,
                )
                trade_rows.append(replay)
                row = {
                    "period": period,
                    "overlay": spec.key,
                    "candidate": spec.candidate,
                    "feature": spec.feature,
                    "feature_family": spec.family,
                    "weight_profile": profile.key,
                    "weight_profile_description": profile.description,
                    "low_weight": profile.low,
                    "mid_weight": profile.mid,
                    "high_weight": profile.high,
                    "low_threshold_q33": threshold_map[spec.key]["low_threshold_q33"],
                    "high_threshold_q66": threshold_map[spec.key]["high_threshold_q66"],
                    "deployability": "research_only",
                    "live_support_notes": "Requires live MBP-10/order-book feature stream and execution-engine sizing support.",
                    "exact_replay_required": True,
                }
                row.update(summarize_replay(replay))
                summary_rows.append(row)

                for tier, tier_group in replay.groupby("feature_tier", dropna=True):
                    tier_row = {
                        "period": period,
                        "overlay": spec.key,
                        "candidate": spec.candidate,
                        "feature": spec.feature,
                        "weight_profile": profile.key,
                        "feature_tier": tier,
                        "risk_weight": float(tier_group["risk_weight"].iloc[0]) if len(tier_group) else math.nan,
                        "trades": int(len(tier_group)),
                        "feature_min": float(tier_group["feature_value"].min()),
                        "feature_max": float(tier_group["feature_value"].max()),
                    }
                    add_prefix(tier_row, "baseline", tier_group["r_multiple"])
                    add_prefix(tier_row, "weighted", tier_group[tier_group["active_trade"]]["weighted_r"])
                    tier_rows.append(tier_row)

                if profile.key == "tier_0p5_1_1p5":
                    for month, month_group in replay.groupby(replay["date"].str.slice(0, 7), dropna=True):
                        active_month = month_group[month_group["active_trade"]]
                        period_row = {
                            "period": period,
                            "month": month,
                            "overlay": spec.key,
                            "candidate": spec.candidate,
                            "feature": spec.feature,
                            "weight_profile": profile.key,
                            "source_trades": int(len(month_group)),
                            "active_trades": int(len(active_month)),
                            "avg_risk_weight": float(month_group["risk_weight"].mean()) if len(month_group) else 0.0,
                        }
                        add_prefix(period_row, "baseline", month_group["r_multiple"])
                        add_prefix(period_row, "weighted", active_month["weighted_r"])
                        period_rows.append(period_row)

    return (
        pd.DataFrame(summary_rows),
        pd.concat(trade_rows, ignore_index=True) if trade_rows else pd.DataFrame(),
        pd.DataFrame(tier_rows),
        pd.DataFrame(period_rows),
    )


def positive_tier_weights(values: pd.Series, *, low_threshold: float, high_threshold: float) -> tuple[pd.Series, pd.Series]:
    clean = values.replace([np.inf, -np.inf], np.nan)
    tiers = pd.Series(pd.NA, index=values.index, dtype="string")
    weights = pd.Series(np.nan, index=values.index, dtype=float)
    tiers[clean <= 0.0] = "zero"
    weights[clean <= 0.0] = 0.5
    tiers[(clean > 0.0) & (clean < low_threshold)] = "positive_low"
    weights[(clean > 0.0) & (clean < low_threshold)] = 0.75
    tiers[(clean >= low_threshold) & (clean < high_threshold)] = "positive_mid"
    weights[(clean >= low_threshold) & (clean < high_threshold)] = 1.0
    tiers[clean >= high_threshold] = "positive_high"
    weights[clean >= high_threshold] = 1.5
    return tiers, weights


def build_zero_inflated_absorption_check(validation: pd.DataFrame, holdout: pd.DataFrame) -> pd.DataFrame:
    candidate = "add_3m_hourly_atr12p5_b3_a7p5"
    rows: list[dict[str, Any]] = []
    for feature in ZERO_INFLATED_3M_FEATURES:
        validation_group = validation[
            (validation["candidate"] == candidate)
            & (validation["feature_data_status"] == "scored")
        ].copy()
        validation_values = pd.to_numeric(validation_group[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
        positive_values = validation_values[validation_values > 0.0].dropna()
        if len(positive_values) < 20:
            continue
        low_threshold = float(positive_values.quantile(0.33))
        high_threshold = float(positive_values.quantile(0.66))
        for period, frame in (("validation", validation), ("holdout", holdout)):
            group = frame[
                (frame["candidate"] == candidate)
                & (frame["feature_data_status"] == "scored")
            ].copy()
            values = pd.to_numeric(group[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
            group = group.dropna(subset=["r_multiple"]).copy()
            values = values.loc[group.index]
            tiers, weights = positive_tier_weights(values, low_threshold=low_threshold, high_threshold=high_threshold)
            weighted_r = group["r_multiple"].astype(float) * weights
            row: dict[str, Any] = {
                "period": period,
                "overlay": f"hourly_3m_positive_tier_{feature}",
                "candidate": candidate,
                "feature": feature,
                "threshold_method": "positive_only_terciles_zero_half_size",
                "positive_validation_rows": int(len(positive_values)),
                "positive_low_threshold_q33": low_threshold,
                "positive_high_threshold_q66": high_threshold,
                "avg_risk_weight": float(weights.mean()) if len(weights) else 0.0,
                "zero_trades": int((tiers == "zero").sum()),
                "positive_low_trades": int((tiers == "positive_low").sum()),
                "positive_mid_trades": int((tiers == "positive_mid").sum()),
                "positive_high_trades": int((tiers == "positive_high").sum()),
            }
            add_prefix(row, "baseline", group["r_multiple"])
            add_prefix(row, "weighted", weighted_r)
            total_weight = float(weights.sum())
            row["weighted_avg_r_per_1x_risk"] = float(weighted_r.sum() / total_weight) if total_weight > 0.0 else 0.0
            row["delta_total_r"] = float(row["weighted_total_r"] - row["baseline_total_r"])
            row["delta_avg_r"] = float(row["weighted_avg_r"] - row["baseline_avg_r"])
            row["delta_avg_r_per_1x_risk"] = float(row["weighted_avg_r_per_1x_risk"] - row["baseline_avg_r"])
            if row["delta_avg_r_per_1x_risk"] > 0.05:
                row["risk_tier_read"] = "supported_after_exposure_normalization"
            elif row["delta_avg_r_per_1x_risk"] > 0.0:
                row["risk_tier_read"] = "mild_after_exposure_normalization"
            else:
                row["risk_tier_read"] = "failed_after_exposure_normalization"
            rows.append(row)
    return pd.DataFrame(rows)


def format_pf(value: float, avg_r: float, win_rate: float) -> str:
    if value == 0.0 and avg_r > 0.0 and win_rate >= 1.0:
        return "inf"
    return f"{value:.3f}"


def combined_positive_check_read(validation_row: pd.Series, holdout_row: pd.Series) -> str:
    val_delta = float(validation_row["delta_avg_r_per_1x_risk"])
    holdout_delta = float(holdout_row["delta_avg_r_per_1x_risk"])
    if val_delta <= 0.0:
        return "validation_failed"
    if holdout_delta <= 0.0:
        return "holdout_failed"
    if val_delta >= 0.05 and holdout_delta >= 0.05:
        return "supported_after_exposure_normalization"
    return "mild_after_exposure_normalization"


def write_report(
    *,
    path: Path,
    summary: pd.DataFrame,
    thresholds: pd.DataFrame,
    tier_breakdown: pd.DataFrame,
    zero_inflated_check: pd.DataFrame,
    output_dir: Path,
    feature_lab_dir: Path,
) -> None:
    primary = summary[summary["weight_profile"] == "tier_0p5_1_1p5"].copy()
    validation_primary = primary[primary["period"] == "validation"]
    holdout_primary = primary[primary["period"] == "holdout"]
    stress = summary[summary["period"] == "holdout"].copy()

    lines = [
        "# NQ NY LSI Order-Book Risk-Tier Replay",
        "",
        "- Objective: continue the promising order-book momentum signals as frozen risk-tier overlays, not hard filters.",
        f"- Input feature-lab directory: `{feature_lab_dir}`.",
        f"- Output directory: `{output_dir}`.",
        "- Thresholds: validation-only terciles for each selected candidate/feature pair.",
        "- Primary sizing: low tercile `0.5x`, middle tercile `1.0x`, high tercile `1.5x`.",
        "- DataBento: no fetch; this consumes existing local feature CSVs.",
        "- Deployability: `research_only` until live MBP-10 feature streaming and execution-engine sizing support exist.",
        "",
        "## Primary Frozen Replay",
        "",
        "| Overlay | Feature | Val Base R | Val Tier R | Holdout Base R | Holdout Tier R | Holdout Avg R | Per-1x Avg R | Tiers | Read |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in holdout_primary.sort_values("delta_total_r", ascending=False).iterrows():
        val_row = validation_primary[validation_primary["overlay"] == row["overlay"]].iloc[0]
        lines.append(
            f"| `{row['overlay']}` | `{row['feature']}` | "
            f"{float(val_row['baseline_total_r']):.2f} | {float(val_row['weighted_total_r']):.2f} | "
            f"{float(row['baseline_total_r']):.2f} | {float(row['weighted_total_r']):.2f} | "
            f"{float(row['weighted_avg_r']):.3f} | {float(row['weighted_avg_r_per_1x_risk']):.3f} | "
            f"{int(row['active_tier_count'])} | {row['risk_tier_read']} |"
        )

    lines.extend(
        [
            "",
            "## Holdout Stress Profiles",
            "",
            "| Overlay | Profile | Base R | Tier R | Delta R | Avg R | Per-1x Avg R | DD | PF |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in stress.sort_values(["overlay", "weight_profile"]).iterrows():
        lines.append(
            f"| `{row['overlay']}` | `{row['weight_profile']}` | "
            f"{float(row['baseline_total_r']):.2f} | {float(row['weighted_total_r']):.2f} | "
            f"{float(row['delta_total_r']):.2f} | {float(row['weighted_avg_r']):.3f} | "
            f"{float(row['weighted_avg_r_per_1x_risk']):.3f} | {float(row['weighted_max_dd_r']):.2f} | "
            f"{format_pf(float(row['weighted_profit_factor']), float(row['weighted_avg_r']), float(row['weighted_win_rate']))} |"
        )

    lines.extend(
        [
            "",
            "## 3m Absorption-Release Positive-Only Check",
            "",
            "The plain terciles are degenerate for 3m because most validation values are zero. This rescue check sizes zero/nonpositive values at 0.5x, then tiers only positive validation values.",
            "",
            "| Feature | Val Base R | Val Tier R | Val Per-1x Avg R | Holdout Base R | Holdout Tier R | Holdout Per-1x Avg R | Avg Weight | Combined Read |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    if zero_inflated_check.empty:
        lines.append("| n/a | 0.00 | 0.00 | 0.000 | 0.00 | 0.00 | 0.000 | 0.00 | n/a |")
    else:
        validation_zero = zero_inflated_check[zero_inflated_check["period"] == "validation"]
        holdout_zero = zero_inflated_check[zero_inflated_check["period"] == "holdout"]
        for _, row in holdout_zero.sort_values("feature").iterrows():
            val_row = validation_zero[validation_zero["feature"] == row["feature"]].iloc[0]
            lines.append(
                f"| `{row['feature']}` | "
                f"{float(val_row['baseline_total_r']):.2f} | {float(val_row['weighted_total_r']):.2f} | "
                f"{float(val_row['weighted_avg_r_per_1x_risk']):.3f} | "
                f"{float(row['baseline_total_r']):.2f} | {float(row['weighted_total_r']):.2f} | "
                f"{float(row['weighted_avg_r_per_1x_risk']):.3f} | {float(row['avg_risk_weight']):.2f} | "
                f"{combined_positive_check_read(val_row, row)} |"
            )

    lines.extend(
        [
            "",
            "## Holdout Tier Breakdown",
            "",
            "| Overlay | Tier | Trades | Weight | Feature Range | Base Avg R | Weighted R |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    tiers = tier_breakdown[
        (tier_breakdown["period"] == "holdout")
        & (tier_breakdown["weight_profile"] == "tier_0p5_1_1p5")
    ].copy()
    tier_order = {"low": 0, "mid": 1, "high": 2}
    tiers["tier_order"] = tiers["feature_tier"].map(tier_order)
    for _, row in tiers.sort_values(["overlay", "tier_order"]).iterrows():
        lines.append(
            f"| `{row['overlay']}` | {row['feature_tier']} | {int(row['trades'])} | "
            f"{float(row['risk_weight']):.2f} | {float(row['feature_min']):.4f}-{float(row['feature_max']):.4f} | "
            f"{float(row['baseline_avg_r']):.3f} | {float(row['weighted_total_r']):.2f} |"
        )

    lines.extend(
        [
            "",
            "## Frozen Thresholds",
            "",
            "| Overlay | Validation Rows | Low < q33 | High >= q66 | Feature Median |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in thresholds.sort_values("overlay").iterrows():
        lines.append(
            f"| `{row['overlay']}` | {int(row['validation_feature_rows'])} | "
            f"{float(row['low_threshold_q33']):.6f} | {float(row['high_threshold_q66']):.6f} | "
            f"{float(row['feature_median']):.6f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- This packet is a fixed follow-up on selected risk-tier families, not a fresh feature search.",
            "- The allDOW and noThursday overlays are overlapping variants of the same 1m additive family; do not combine them naively.",
            "- The 3m absorption-release first-10s and last-10s plain tercile overlays are exposure-only. The positive-only rescue check demotes first-10s, leaves full/last-10s only mildly positive per 1x risk, and reduces absolute holdout R because average risk drops.",
            "- Any deployment path requires implementing these features causally in the live engine before signal close and replaying exact execution with dynamic sizing.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-lab-dir", type=Path, default=DEFAULT_FEATURE_LAB_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    validation_path = args.feature_lab_dir / "validation_feature_lab.csv"
    holdout_path = args.feature_lab_dir / "holdout_feature_lab.csv"
    if not validation_path.exists() or not holdout_path.exists():
        raise FileNotFoundError(f"Missing feature lab CSVs in {args.feature_lab_dir}")

    print("NQ NY LSI order-book risk-tier replay", flush=True)
    validation = clean_frame(validation_path, period="validation")
    holdout = clean_frame(holdout_path, period="holdout")
    threshold_rows = [threshold_row(spec, validation) for spec in SPECS]
    thresholds = pd.DataFrame(threshold_rows)
    summary, trade_replay, tier_breakdown, monthly = build_summary(validation, holdout, thresholds)
    zero_inflated_check = build_zero_inflated_absorption_check(validation, holdout)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    thresholds_path = args.output_dir / "frozen_thresholds.csv"
    summary_path = args.output_dir / "risk_tier_summary.csv"
    trade_path = args.output_dir / "trade_risk_tier_replay.csv"
    tier_path = args.output_dir / "tier_breakdown.csv"
    monthly_path = args.output_dir / "monthly_breakdown.csv"
    zero_inflated_path = args.output_dir / "zero_inflated_absorption_check.csv"
    thresholds.to_csv(thresholds_path, index=False)
    summary.to_csv(summary_path, index=False)
    trade_replay.to_csv(trade_path, index=False)
    tier_breakdown.to_csv(tier_path, index=False)
    monthly.to_csv(monthly_path, index=False)
    zero_inflated_check.to_csv(zero_inflated_path, index=False)

    payload = {
        "run_slug": RUN_SLUG,
        "feature_lab_dir": str(args.feature_lab_dir),
        "specs": [dataclasses.asdict(spec) for spec in SPECS],
        "weight_profiles": [dataclasses.asdict(profile) for profile in WEIGHT_PROFILES],
        "outputs": {
            "frozen_thresholds": str(thresholds_path),
            "risk_tier_summary": str(summary_path),
            "trade_risk_tier_replay": str(trade_path),
            "tier_breakdown": str(tier_path),
            "monthly_breakdown": str(monthly_path),
            "zero_inflated_absorption_check": str(zero_inflated_path),
            "report": str(args.report_path),
        },
    }
    (args.output_dir / "summary.json").write_text(json.dumps(payload, indent=2, default=str))
    write_report(
        path=args.report_path,
        summary=summary,
        thresholds=thresholds,
        tier_breakdown=tier_breakdown,
        zero_inflated_check=zero_inflated_check,
        output_dir=args.output_dir,
        feature_lab_dir=args.feature_lab_dir,
    )
    print(f"Wrote {thresholds_path}", flush=True)
    print(f"Wrote {summary_path}", flush=True)
    print(f"Wrote {trade_path}", flush=True)
    print(f"Wrote {tier_path}", flush=True)
    print(f"Wrote {monthly_path}", flush=True)
    print(f"Wrote {zero_inflated_path}", flush=True)
    print(f"Wrote {args.report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
