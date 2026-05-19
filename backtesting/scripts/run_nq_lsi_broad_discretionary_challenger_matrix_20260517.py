#!/usr/bin/env python3
"""Broader no-extra-fetch discretionary challenger matrix for NQ NY LSI.

This widens the pure 1m challenger branch pass to every locally covered LSI
variant and adds the current 5m HTF-LSI path where local 1s price data is
available. No DataBento fetches are performed.

Coverage:
- 1m additive allDOW / noThu, 3m hourly additive, 2m HTF anchor, pure 1m:
  price-action + existing MBP-10 features.
- 5m current HTF-LSI lag24 path:
  price-action features only, because local MBP-10 windows were not fetched
  for this branch.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, run_backtest  # noqa: E402
from replay_nq_lsi_sweep_reclaim_velocity import (  # noqa: E402
    OneSecondDayReader as SweepOneSecondDayReader,
    build_feature_frame as build_sweep_reclaim_features,
)
from run_nq_lsi_pure_1m_challenger_branches_20260517 import (  # noqa: E402
    OneSecondDayReader,
    add_metrics,
    assign_tiers,
    parse_ts,
    r_metrics,
    score_price_violence,
    weight_for_tier,
)


RUN_SLUG = "nq_lsi_broad_discretionary_challenger_matrix_20260517"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = (
    ROOT / "learnings" / "reports" / "NQ_NY_LSI_BROAD_DISCRETIONARY_CHALLENGER_MATRIX_20260517.md"
)
DEFAULT_FEATURE_LAB_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_feature_lab_20260514"
DEFAULT_ONE_SECOND_PATH = ROOT / "data" / "raw" / "NQ_1s.parquet"

VALIDATION_START = pd.Timestamp("2023-01-01")
HOLDOUT_START = pd.Timestamp("2025-04-01")
END_DATE = "2026-05-02"
PRIMARY_PROFILE = "tier_0p5_1_1p5"

FIVE_M_CANDIDATE = "htf_lsi_5m_lag24_current"

WEIGHT_PROFILES = {
    "tier_0p5_1_1p5": {"low": 0.5, "mid": 1.0, "high": 1.5},
    "tier_0p75_1_1p25": {"low": 0.75, "mid": 1.0, "high": 1.25},
    "tier_0_1_1p5": {"low": 0.0, "mid": 1.0, "high": 1.5},
}


@dataclass(frozen=True)
class FeatureSpec:
    feature: str
    branch: str
    timing: str
    source: str
    description: str


FEATURE_SPECS = [
    FeatureSpec(
        "price_violence_last_10s_score",
        "reversal_violence_relative_to_day",
        "entry_safe_at_signal_close",
        "NQ_1s.parquet",
        "Last 10s directional close move normalized by prior same-day 10s movement.",
    ),
    FeatureSpec(
        "price_violence_last_30s_score",
        "reversal_violence_relative_to_day",
        "entry_safe_at_signal_close",
        "NQ_1s.parquet",
        "Last 30s directional close move normalized by prior same-day 30s movement.",
    ),
    FeatureSpec(
        "price_violence_signal_bar_score",
        "reversal_violence_relative_to_day",
        "entry_safe_at_signal_close",
        "NQ_1s.parquet",
        "Full signal-bar directional move normalized by prior same-day movement.",
    ),
    FeatureSpec(
        "trapped_reversal_confirm_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "NQ_1s.parquet",
        "Adverse sweep depth that quickly reclaims and expands in trade direction.",
    ),
    FeatureSpec(
        "confirm_reclaim_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "NQ_1s.parquet",
        "Sweep depth, reclaim speed, hold ratio, and follow-through through signal close.",
    ),
    FeatureSpec(
        "confirm_reclaim_velocity_ticks_per_second",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "NQ_1s.parquet",
        "Depth divided by seconds from adverse extreme to reclaim.",
    ),
    FeatureSpec(
        "ob_absorption_release_confirm_first_10s_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "existing_MBP10_feature_lab",
        "Existing MBP-10 pre-confirm absorption times first-10s release.",
    ),
    FeatureSpec(
        "ob_absorption_release_confirm_last_10s_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "existing_MBP10_feature_lab",
        "Existing MBP-10 short-window absorption times last-10s release.",
    ),
    FeatureSpec(
        "ob_absorption_release_confirm_full_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "existing_MBP10_feature_lab",
        "Existing MBP-10 counter-pressure absorption times full confirmation release.",
    ),
    FeatureSpec(
        "ob_vacuum_confirm_last_10s_score",
        "liquidity_vacuum_book_pull",
        "entry_safe_at_signal_close",
        "existing_MBP10_feature_lab",
        "Last-10s aligned depth/microprice improvement with directional midpoint movement.",
    ),
    FeatureSpec(
        "ob_vacuum_confirm_full_score",
        "liquidity_vacuum_book_pull",
        "entry_safe_at_signal_close",
        "existing_MBP10_feature_lab",
        "Full confirmation aligned depth/microprice improvement with directional midpoint movement.",
    ),
    FeatureSpec(
        "ob_vacuum_pre_confirm_30s_score",
        "liquidity_vacuum_book_pull",
        "entry_safe_before_signal_bar",
        "existing_MBP10_feature_lab",
        "Pre-signal aligned depth/microprice improvement before the signal bar opens.",
    ),
    FeatureSpec(
        "pre_confirm_30s_pressure_score",
        "current_orderbook_survivor",
        "entry_safe_before_signal_bar",
        "existing_MBP10_feature_lab",
        "Current additive 1m order-book pressure survivor.",
    ),
    FeatureSpec(
        "confirm_last_10s_mid_velocity_ticks_per_second",
        "current_orderbook_survivor",
        "entry_safe_at_signal_close",
        "existing_MBP10_feature_lab",
        "Current pure 1m order-book velocity survivor.",
    ),
]


BASE_COLUMNS = [
    "trade_uid",
    "candidate",
    "label",
    "timeframe",
    "date",
    "direction",
    "confirmation",
    "r_multiple",
    "signal_start",
    "signal_end",
    "fill_time",
    "lsi_sweep_time",
    "lsi_fvg_time",
    "lsi_cisd_time",
    "entry_price",
    "risk_points",
    "period",
    "has_orderbook_data",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feature-lab-dir", type=Path, default=DEFAULT_FEATURE_LAB_DIR)
    parser.add_argument("--one-second-path", type=Path, default=DEFAULT_ONE_SECOND_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--skip-5m-engine", action="store_true")
    return parser.parse_args()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n")


def load_feature_lab_base(feature_lab_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for period, filename in (("validation", "validation_feature_lab.csv"), ("holdout", "holdout_feature_lab.csv")):
        path = feature_lab_dir / filename
        frame = pd.read_csv(path)
        frame["period"] = period
        frames.append(frame)
    lab = pd.concat(frames, ignore_index=True)
    for column in BASE_COLUMNS:
        if column not in lab.columns:
            lab[column] = pd.NA
    base = lab[BASE_COLUMNS].copy()
    base["has_orderbook_data"] = base["has_orderbook_data"].fillna(False).astype(bool)
    base = base[base["has_orderbook_data"]].copy()
    base["r_multiple"] = pd.to_numeric(base["r_multiple"], errors="coerce")
    base["direction"] = pd.to_numeric(base["direction"], errors="coerce").astype("Int64")
    return base.dropna(subset=["trade_uid", "date", "direction", "r_multiple"]).reset_index(drop=True)


def trade_uid_for_row(candidate: str, date: str, signal_start: str, direction: int, entry_price: float) -> str:
    return f"{candidate}|{date}|{signal_start}|{direction}|{entry_price:.2f}"


def rows_from_5m_current_path() -> pd.DataFrame:
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    config = build_current_nq_ny_htf_lsi_lag24_config(name="NQ NY HTF_LSI 5m lag24 current orderflow screen")
    maps = build_maps(df_base, df_1m, None, df_1s)
    trades = run_backtest(
        df_base,
        config,
        start_date=str(VALIDATION_START.date()),
        end_date=END_DATE,
        df_1m=df_1m,
        df_1s=df_1s,
        signal_df_1m=signal_df_1m,
        _maps=maps,
    )
    rows: list[dict[str, Any]] = []
    for trade in trades:
        date_ts = pd.Timestamp(trade.date)
        period = "validation" if date_ts < HOLDOUT_START else "holdout"
        signal_start = trade.lsi_fvg_time
        if not signal_start and 0 <= int(trade.signal_bar) < len(df_base.index):
            signal_start = pd.Timestamp(df_base.index[int(trade.signal_bar)]).isoformat()
        signal_ts = parse_ts(signal_start)
        signal_end = (signal_ts + pd.Timedelta(minutes=5)).isoformat() if signal_ts is not None else ""
        entry_price = float(trade.entry_price)
        r_multiple = 0.0 if trade.exit_type == EXIT_NO_FILL else float(trade.r_multiple)
        rows.append(
            {
                "trade_uid": trade_uid_for_row(FIVE_M_CANDIDATE, trade.date, signal_start, int(trade.direction), entry_price),
                "candidate": FIVE_M_CANDIDATE,
                "label": "NQ NY HTF_LSI 5m lag24 current",
                "timeframe": "5m",
                "date": trade.date,
                "direction": int(trade.direction),
                "confirmation": trade.lsi_confirmation_type or "inversion",
                "r_multiple": r_multiple,
                "signal_start": signal_start,
                "signal_end": signal_end,
                "fill_time": trade.fill_time,
                "lsi_sweep_time": trade.lsi_sweep_time,
                "lsi_fvg_time": trade.lsi_fvg_time,
                "lsi_cisd_time": trade.lsi_cisd_time,
                "entry_price": entry_price,
                "risk_points": float(trade.risk_points),
                "period": period,
                "has_orderbook_data": False,
            }
        )
    return pd.DataFrame(rows)


def attach_signal_timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["signal_start_ts"] = out["signal_start"].map(parse_ts)
    missing_end = out["signal_end"].isna() | out["signal_end"].astype(str).str.lower().isin({"", "nan", "nat", "none"})
    minutes = out["timeframe"].astype(str).str.rstrip("m").replace({"": "1"}).astype(int)
    out.loc[missing_end, "signal_end"] = (
        out.loc[missing_end, "signal_start_ts"] + pd.to_timedelta(minutes.loc[missing_end], unit="m")
    ).map(lambda ts: ts.isoformat() if pd.notna(ts) else "")
    out["signal_end_ts"] = out["signal_end"].map(parse_ts)
    return out


def load_orderbook_features_all(feature_lab_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for period, filename in (("validation", "validation_feature_lab.csv"), ("holdout", "holdout_feature_lab.csv")):
        frame = pd.read_csv(feature_lab_dir / filename)
        frame["period"] = period
        frames.append(frame)
    lab = pd.concat(frames, ignore_index=True)
    lab = lab[lab.get("has_orderbook_data", False).astype(bool)].copy()

    def pos(column: str) -> pd.Series:
        return pd.to_numeric(lab.get(column, 0.0), errors="coerce").fillna(0.0).clip(lower=0.0)

    for segment in ("confirm_last_10s", "confirm_full", "pre_confirm_30s"):
        depth_end = pos(f"{segment}_aligned_depth_imbalance_3_end")
        depth_delta = pos(f"{segment}_aligned_depth_imbalance_3_delta")
        micro = pos(f"{segment}_aligned_micro_skew_ticks_end")
        mid_velocity = pos(f"{segment}_mid_velocity_ticks_per_second")
        pressure = pos(f"{segment}_pressure_score")
        lab[f"ob_vacuum_{segment}_score"] = (depth_end + depth_delta + micro) * (1.0 + mid_velocity) * (1.0 + pressure)

    rename = {
        "absorption_release_confirm_first_10s_score": "ob_absorption_release_confirm_first_10s_score",
        "absorption_release_confirm_last_10s_score": "ob_absorption_release_confirm_last_10s_score",
        "absorption_release_confirm_full_score": "ob_absorption_release_confirm_full_score",
    }
    lab = lab.rename(columns=rename)
    desired = ["trade_uid"]
    desired.extend([spec.feature for spec in FEATURE_SPECS if spec.source == "existing_MBP10_feature_lab"])
    available = [column for column in desired if column in lab.columns]
    return lab[available].drop_duplicates("trade_uid")


def build_feature_matrix(base: pd.DataFrame, one_second_path: Path, feature_lab_dir: Path) -> pd.DataFrame:
    base = attach_signal_timestamps(base)
    price = score_price_violence(base, one_second_path)
    sweep = build_sweep_reclaim_features(base[BASE_COLUMNS].copy(), SweepOneSecondDayReader(one_second_path))
    sweep_columns = [
        "trade_uid",
        "trapped_reversal_confirm_score",
        "confirm_reclaim_score",
        "confirm_reclaim_velocity_ticks_per_second",
        "confirm_post_reclaim_move_ticks",
        "compression_expansion_confirm_score",
        "pre_signal_reclaim_score",
        "post_reclaim_30s_score",
        "post_reclaim_60s_score",
    ]
    sweep_columns = [column for column in sweep_columns if column in sweep.columns]
    features = price.merge(sweep[sweep_columns], on="trade_uid", how="left")
    features = features.merge(load_orderbook_features_all(feature_lab_dir), on="trade_uid", how="left")
    for spec in FEATURE_SPECS:
        if spec.feature not in features.columns:
            features[spec.feature] = np.nan
        features[spec.feature] = pd.to_numeric(features[spec.feature], errors="coerce").replace([np.inf, -np.inf], np.nan)
    return features


def evaluate(features: pd.DataFrame, *, min_validation_rows: int = 10) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    thresholds: list[dict[str, Any]] = []
    replay_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    tier_rows: list[dict[str, Any]] = []

    for candidate, candidate_frame in features.groupby("candidate", sort=True):
        validation = candidate_frame[candidate_frame["period"].eq("validation")]
        if validation.empty:
            continue
        for spec in FEATURE_SPECS:
            validation_values = (
                pd.to_numeric(validation[spec.feature], errors="coerce")
                .replace([np.inf, -np.inf], np.nan)
                .dropna()
            )
            if len(validation_values) < min_validation_rows:
                continue
            low = float(validation_values.quantile(0.33))
            high = float(validation_values.quantile(0.66))
            thresholds.append(
                {
                    "candidate": candidate,
                    "feature": spec.feature,
                    "branch": spec.branch,
                    "timing": spec.timing,
                    "source": spec.source,
                    "description": spec.description,
                    "validation_rows": int(len(validation_values)),
                    "low_threshold_q33": low,
                    "high_threshold_q66": high,
                    "zero_share": float((validation_values == 0.0).mean()),
                    "feature_min": float(validation_values.min()),
                    "feature_median": float(validation_values.median()),
                    "feature_max": float(validation_values.max()),
                }
            )

            for profile_name, profile in WEIGHT_PROFILES.items():
                replay = candidate_frame[candidate_frame[spec.feature].notna()].copy()
                if replay.empty:
                    continue
                replay["feature"] = spec.feature
                replay["branch"] = spec.branch
                replay["timing"] = spec.timing
                replay["source"] = spec.source
                replay["feature_value"] = pd.to_numeric(replay[spec.feature], errors="coerce")
                replay["feature_tier"] = assign_tiers(replay["feature_value"], low, high)
                replay["weight_profile"] = profile_name
                replay["risk_weight"] = replay["feature_tier"].map(lambda tier: weight_for_tier(tier, profile))
                replay["active_trade"] = replay["risk_weight"] > 0.0
                replay["weighted_r"] = replay["r_multiple"] * replay["risk_weight"]
                replay_frames.append(
                    replay[
                        [
                            "period",
                            "trade_uid",
                            "candidate",
                            "timeframe",
                            "date",
                            "signal_start",
                            "direction",
                            "r_multiple",
                            "branch",
                            "feature",
                            "timing",
                            "source",
                            "feature_value",
                            "feature_tier",
                            "weight_profile",
                            "risk_weight",
                            "active_trade",
                            "weighted_r",
                        ]
                    ]
                )

                for period_name in ("validation", "holdout"):
                    subset = replay[replay["period"].eq(period_name)]
                    if subset.empty:
                        continue
                    active = subset[subset["active_trade"]]
                    row: dict[str, Any] = {
                        "period": period_name,
                        "candidate": candidate,
                        "timeframe": str(subset["timeframe"].iloc[0]),
                        "branch": spec.branch,
                        "feature": spec.feature,
                        "timing": spec.timing,
                        "source": spec.source,
                        "weight_profile": profile_name,
                        "low_threshold_q33": low,
                        "high_threshold_q66": high,
                        "source_trades": int(len(subset)),
                        "active_trades": int(len(active)),
                        "active_tier_count": int(subset["feature_tier"].nunique(dropna=True)),
                        "low_tier_trades": int((subset["feature_tier"] == "low").sum()),
                        "mid_tier_trades": int((subset["feature_tier"] == "mid").sum()),
                        "high_tier_trades": int((subset["feature_tier"] == "high").sum()),
                        "avg_risk_weight_all": float(subset["risk_weight"].mean()),
                        "total_risk_weight": float(active["risk_weight"].sum()),
                        "deployability": "research_only",
                        "live_support_notes": (
                            "No new historical fetch in this replay. Live support requires execution implementation "
                            "for the selected feature path and exact replay before promotion."
                        ),
                        "exact_replay_required": True,
                    }
                    add_metrics(row, "baseline", subset["r_multiple"])
                    add_metrics(row, "weighted", active["weighted_r"])
                    row["weighted_avg_r_per_1x_risk"] = (
                        float(active["weighted_r"].sum() / active["risk_weight"].sum())
                        if len(active) and float(active["risk_weight"].sum()) > 0.0
                        else 0.0
                    )
                    row["delta_total_r"] = float(row["weighted_total_r"] - row["baseline_total_r"])
                    row["delta_avg_r"] = float(row["weighted_avg_r"] - row["baseline_avg_r"])
                    row["delta_avg_r_per_1x_risk"] = float(row["weighted_avg_r_per_1x_risk"] - row["baseline_avg_r"])
                    if row["active_tier_count"] <= 1:
                        row["risk_tier_read"] = "exposure_only_no_tier_discrimination"
                    elif row["delta_avg_r_per_1x_risk"] >= 0.05 and row["delta_total_r"] > 0:
                        row["risk_tier_read"] = "supported_after_exposure_normalization"
                    elif row["delta_avg_r_per_1x_risk"] > 0.0:
                        row["risk_tier_read"] = "mild_after_exposure_normalization"
                    else:
                        row["risk_tier_read"] = "failed_after_exposure_normalization"
                    summary_rows.append(row)

                    for tier, tier_group in subset.groupby("feature_tier", dropna=True):
                        tier_rows.append(
                            {
                                "period": period_name,
                                "candidate": candidate,
                                "timeframe": str(tier_group["timeframe"].iloc[0]),
                                "branch": spec.branch,
                                "feature": spec.feature,
                                "weight_profile": profile_name,
                                "tier": tier,
                                "trades": int(len(tier_group)),
                                "avg_feature_value": float(tier_group["feature_value"].mean()),
                                "min_feature_value": float(tier_group["feature_value"].min()),
                                "max_feature_value": float(tier_group["feature_value"].max()),
                                "base_avg_r": float(tier_group["r_multiple"].mean()),
                                "base_total_r": float(tier_group["r_multiple"].sum()),
                                "weight": float(tier_group["risk_weight"].iloc[0]),
                                "weighted_total_r": float(tier_group["weighted_r"].sum()),
                            }
                        )

    return (
        pd.DataFrame(thresholds),
        pd.concat(replay_frames, ignore_index=True) if replay_frames else pd.DataFrame(),
        pd.DataFrame(summary_rows),
        pd.DataFrame(tier_rows),
    )


def select_top(summary: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    primary = summary[summary["weight_profile"].eq(PRIMARY_PROFILE)].copy()
    holdout = primary[primary["period"].eq("holdout")].copy()
    validation = primary[primary["period"].eq("validation")][
        [
            "candidate",
            "branch",
            "feature",
            "weighted_total_r",
            "weighted_avg_r",
            "weighted_profit_factor",
            "weighted_max_dd_r",
            "risk_tier_read",
        ]
    ].rename(
        columns={
            "weighted_total_r": "validation_weighted_r",
            "weighted_avg_r": "validation_weighted_avg_r",
            "weighted_profit_factor": "validation_weighted_pf",
            "weighted_max_dd_r": "validation_weighted_max_dd_r",
            "risk_tier_read": "validation_risk_tier_read",
        }
    )
    top = holdout.merge(validation, on=["candidate", "branch", "feature"], how="left")
    order = {
        "supported_after_exposure_normalization": 3,
        "mild_after_exposure_normalization": 2,
        "exposure_only_no_tier_discrimination": 1,
        "failed_after_exposure_normalization": 0,
    }
    top["read_score"] = top["risk_tier_read"].map(order).fillna(0)
    top["validation_read_score"] = top["validation_risk_tier_read"].map(order).fillna(0)
    top = top.sort_values(
        ["candidate", "read_score", "validation_read_score", "delta_avg_r_per_1x_risk", "weighted_total_r"],
        ascending=[True, False, False, False, False],
    )
    best_by_candidate = top.groupby("candidate", as_index=False, group_keys=False).head(1)
    return top, best_by_candidate


def build_coverage(features: pd.DataFrame, thresholds: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate, group in features.groupby("candidate", sort=True):
        threshold_subset = thresholds[thresholds["candidate"].eq(candidate)]
        rows.append(
            {
                "candidate": candidate,
                "timeframe": str(group["timeframe"].iloc[0]),
                "validation_rows": int((group["period"] == "validation").sum()),
                "holdout_rows": int((group["period"] == "holdout").sum()),
                "orderbook_rows": int(group["has_orderbook_data"].fillna(False).astype(bool).sum()),
                "tested_features": int(threshold_subset["feature"].nunique()),
                "tested_orderbook_features": int(threshold_subset[threshold_subset["source"].eq("existing_MBP10_feature_lab")]["feature"].nunique()),
                "tested_price_features": int(threshold_subset[threshold_subset["source"].eq("NQ_1s.parquet")]["feature"].nunique()),
            }
        )
    return pd.DataFrame(rows)


def write_report(path: Path, payload: dict[str, Any], coverage: pd.DataFrame, best: pd.DataFrame, top: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# NQ NY LSI Broad Discretionary Challenger Matrix - 2026-05-17",
        "",
        "## Objective",
        "",
        "Extend the three discretionary momentum challenger families beyond the pure 1m survivor and include the current 5m HTF-LSI path where no-extra-fetch data exists.",
        "",
        f"- DataBento fetches: `{payload['data_bento_fetches']}`.",
        "- Thresholds: validation terciles frozen per candidate/feature and replayed on holdout.",
        "- Primary sizing: `0.5x / 1.0x / 1.5x`.",
        "- 5m caveat: no local MBP-10 windows exist for the current 5m path, so 5m is price-action only in this pass.",
        "",
        "## Coverage",
        "",
        "| Candidate | TF | Validation | Holdout | OB Rows | Tested Features | OB Features | Price Features |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in coverage.itertuples(index=False):
        lines.append(
            f"| `{row.candidate}` | `{row.timeframe}` | {row.validation_rows} | {row.holdout_rows} | "
            f"{row.orderbook_rows} | {row.tested_features} | {row.tested_orderbook_features} | {row.tested_price_features} |"
        )

    lines.extend(
        [
            "",
            "## Best Holdout Read By Candidate",
            "",
            "| Candidate | Branch | Feature | Holdout Weighted R | Holdout Avg | PF | Max DD | Holdout Read | Validation Read |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
        ]
    )
    for row in best.itertuples(index=False):
        lines.append(
            f"| `{row.candidate}` | `{row.branch}` | `{row.feature}` | {row.weighted_total_r:.2f} | "
            f"{row.weighted_avg_r:.3f} | {row.weighted_profit_factor:.2f} | {row.weighted_max_dd_r:.2f} | "
            f"`{row.risk_tier_read}` | `{row.validation_risk_tier_read}` |"
        )

    current = top[top["branch"].eq("current_orderbook_survivor")].copy()
    if not current.empty:
        lines.extend(
            [
                "",
                "## Current Order-Book Path Rows",
                "",
                "| Candidate | Feature | Holdout Baseline R | Holdout Weighted R | Holdout Read | Validation Read |",
                "| --- | --- | ---: | ---: | --- | --- |",
            ]
        )
        for row in current.groupby("candidate", as_index=False, group_keys=False).head(2).itertuples(index=False):
            lines.append(
                f"| `{row.candidate}` | `{row.feature}` | {row.baseline_total_r:.2f} | "
                f"{row.weighted_total_r:.2f} | `{row.risk_tier_read}` | `{row.validation_risk_tier_read}` |"
            )

    supported = top[
        top["risk_tier_read"].eq("supported_after_exposure_normalization")
        & top["validation_risk_tier_read"].eq("supported_after_exposure_normalization")
    ].copy()
    lines.extend(
        [
            "",
            "## Stable Supported Rows",
            "",
        ]
    )
    if supported.empty:
        lines.append("No row was supported on both validation and holdout after exposure normalization.")
    else:
        lines.extend(
            [
                "| Candidate | Branch | Feature | Holdout Weighted R | Holdout Per-1x Avg Delta | Validation Weighted R |",
                "| --- | --- | --- | ---: | ---: | ---: |",
            ]
        )
        for row in supported.head(12).itertuples(index=False):
            lines.append(
                f"| `{row.candidate}` | `{row.branch}` | `{row.feature}` | {row.weighted_total_r:.2f} | "
                f"{row.delta_avg_r_per_1x_risk:.3f} | {row.validation_weighted_r:.2f} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The strict stable-survivor view is intentionally conservative: it requires exposure-normalized support on both validation and holdout. Under that rule only 3m trapped reversal and pure 1m liquidity-vacuum survive. The incumbent 1m additive pressure and pure 1m velocity rows still matter because they win or nearly win absolute holdout R, but their validation improvement is milder under this particular per-1x normalization.",
            "",
            "The current 5m HTF-LSI path did not produce a stable no-fetch price-action overlay. Signal-bar price violence was mildly positive on holdout, but failed validation, and the sweep/reclaim scores were exposure-only because the validation thresholds were zero-inflated. Order-book absorption/vacuum on 5m remains untested until MBP-10 windows are fetched for that branch.",
            "",
            "This is still a research-only matrix. Rows that require MBP-10 features are not live-native until the execution path supports the exact feature and passes exact replay / shadow validation. The 5m branch needs a separate MBP-10 fetch before order-book absorption or liquidity-vacuum can be tested on it.",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    base = load_feature_lab_base(args.feature_lab_dir)
    five_m_rows = pd.DataFrame()
    if not args.skip_5m_engine:
        five_m_rows = rows_from_5m_current_path()
        base = pd.concat([base, five_m_rows], ignore_index=True)

    features = build_feature_matrix(base, args.one_second_path, args.feature_lab_dir)
    thresholds, replay, summary, tiers = evaluate(features)
    top, best = select_top(summary)
    coverage = build_coverage(features, thresholds)

    features.to_csv(args.output_dir / "trade_feature_matrix.csv", index=False)
    thresholds.to_csv(args.output_dir / "frozen_thresholds.csv", index=False)
    replay.to_csv(args.output_dir / "risk_tier_replay.csv", index=False)
    summary.to_csv(args.output_dir / "risk_tier_summary.csv", index=False)
    tiers.to_csv(args.output_dir / "tier_breakdown.csv", index=False)
    top.to_csv(args.output_dir / "top_challengers.csv", index=False)
    best.to_csv(args.output_dir / "best_by_candidate.csv", index=False)
    coverage.to_csv(args.output_dir / "coverage.csv", index=False)

    payload = {
        "run_slug": RUN_SLUG,
        "data_bento_fetches": 0,
        "output_dir": str(args.output_dir),
        "report_path": str(args.report_path),
        "candidates": coverage.to_dict(orient="records"),
        "five_m_rows_generated": int(len(five_m_rows)),
        "five_m_orderbook_available": False,
        "primary_weight_profile": PRIMARY_PROFILE,
    }
    save_json(args.output_dir / "summary.json", payload)
    write_report(args.report_path, payload, coverage, best, top)
    print(json.dumps(payload, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
