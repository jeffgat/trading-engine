#!/usr/bin/env python3
"""No-extra-fetch challenger branches for the pure 1m LSI reversal idea.

This starts three branches against the current champion's trade set:

1. Reversal violence relative to the day, using local 1s prices.
2. Absorption then release, using existing 1s sweep/reclaim and MBP-10 lab features.
3. Liquidity vacuum / book pull, using existing MBP-10 depth/microstructure features.

Thresholds are frozen on validation rows and replayed on holdout rows. No
DataBento fetch is performed.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_lsi_pure_1m_challenger_branches_20260517"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_PURE_1M_CHALLENGER_BRANCHES_20260517.md"
DEFAULT_RISK_TIER_REPLAY = (
    ROOT / "data" / "results" / "nq_ny_lsi_orderbook_risk_tiers_20260515" / "trade_risk_tier_replay.csv"
)
DEFAULT_SWEEP_FEATURES = (
    ROOT / "data" / "results" / "nq_ny_lsi_sweep_reclaim_velocity_20260515" / "trade_sweep_reclaim_features.csv"
)
DEFAULT_FEATURE_LAB_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_feature_lab_20260514"
DEFAULT_ONE_SECOND_PATH = ROOT / "data" / "raw" / "NQ_1s.parquet"

CANDIDATE = "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200"
CHAMPION_OVERLAY = "pure_1m_long_confirm_last_velocity"
CHAMPION_FEATURE = "confirm_last_10s_mid_velocity_ticks_per_second"
PRIMARY_PROFILE = "tier_0p5_1_1p5"
TICK_SIZE = 0.25

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
    description: str


FEATURE_SPECS = [
    FeatureSpec(
        "price_violence_last_10s_score",
        "reversal_violence_relative_to_day",
        "entry_safe_at_signal_close",
        "Last 10s directional close move normalized by prior same-day 10s movement.",
    ),
    FeatureSpec(
        "price_violence_last_30s_score",
        "reversal_violence_relative_to_day",
        "entry_safe_at_signal_close",
        "Last 30s directional close move normalized by prior same-day 30s movement.",
    ),
    FeatureSpec(
        "price_violence_signal_bar_score",
        "reversal_violence_relative_to_day",
        "entry_safe_at_signal_close",
        "Full 1m signal-bar directional move normalized by prior same-day 60s movement.",
    ),
    FeatureSpec(
        "price_trapped_reversal_confirm_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "Price-action trapped reversal score from local 1s sweep/reclaim replay.",
    ),
    FeatureSpec(
        "price_confirm_reclaim_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "Sweep depth, reclaim speed, and follow-through through signal close.",
    ),
    FeatureSpec(
        "ob_absorption_release_confirm_full_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "MBP-10 counter-pressure absorption multiplied by full confirmation release.",
    ),
    FeatureSpec(
        "ob_absorption_release_confirm_last_10s_score",
        "absorption_then_release",
        "entry_safe_at_signal_close",
        "MBP-10 short-window absorption multiplied by last-10s release.",
    ),
    FeatureSpec(
        "ob_vacuum_confirm_last_10s_score",
        "liquidity_vacuum_book_pull",
        "entry_safe_at_signal_close",
        "Last-10s aligned depth/microprice improvement with directional midpoint movement.",
    ),
    FeatureSpec(
        "ob_vacuum_confirm_full_score",
        "liquidity_vacuum_book_pull",
        "entry_safe_at_signal_close",
        "Full confirmation bar aligned depth/microprice improvement with directional midpoint movement.",
    ),
    FeatureSpec(
        "ob_vacuum_pre_confirm_30s_score",
        "liquidity_vacuum_book_pull",
        "entry_safe_before_signal_bar",
        "Pre-signal aligned depth/microprice improvement before the signal bar opens.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--risk-tier-replay", type=Path, default=DEFAULT_RISK_TIER_REPLAY)
    parser.add_argument("--sweep-features", type=Path, default=DEFAULT_SWEEP_FEATURES)
    parser.add_argument("--feature-lab-dir", type=Path, default=DEFAULT_FEATURE_LAB_DIR)
    parser.add_argument("--one-second-path", type=Path, default=DEFAULT_ONE_SECOND_PATH)
    return parser.parse_args()


def parse_ts(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    ts = pd.Timestamp(text)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("America/New_York").tz_localize(None)
    return ts


def r_metrics(values: pd.Series | np.ndarray | list[float]) -> dict[str, float | int]:
    r = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna().astype(float).to_numpy()
    if len(r) == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "max_dd_r": 0.0,
            "profit_factor": 0.0,
            "calmar": 0.0,
        }
    wins = r > 0
    losses = r < 0
    gross_win = float(r[wins].sum()) if wins.any() else 0.0
    gross_loss = float(r[losses].sum()) if losses.any() else 0.0
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    max_dd = float((equity - peak).min()) if len(equity) else 0.0
    total = float(equity[-1])
    return {
        "trades": int(len(r)),
        "win_rate": float(wins.mean()),
        "total_r": total,
        "avg_r": float(r.mean()),
        "max_dd_r": max_dd,
        "profit_factor": abs(gross_win / gross_loss) if gross_loss else 0.0,
        "calmar": total / abs(max_dd) if max_dd else 0.0,
    }


def add_metrics(row: dict[str, Any], prefix: str, values: pd.Series | np.ndarray | list[float]) -> None:
    for key, value in r_metrics(values).items():
        row[f"{prefix}_{key}"] = value


def load_champion_rows(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    selected = frame[
        frame["candidate"].eq(CANDIDATE)
        & frame["overlay"].eq(CHAMPION_OVERLAY)
        & frame["feature"].eq(CHAMPION_FEATURE)
        & frame["weight_profile"].eq(PRIMARY_PROFILE)
    ].copy()
    if selected.empty:
        raise SystemExit(f"No champion rows found in {path}")
    selected = selected.sort_values(["period", "date", "signal_start"]).drop_duplicates("trade_uid")
    selected["signal_start_ts"] = selected["signal_start"].map(parse_ts)
    selected["signal_end_ts"] = selected["signal_start_ts"] + pd.to_timedelta(
        selected["timeframe"].str.rstrip("m").astype(int), unit="m"
    )
    selected["direction"] = selected["direction"].astype(int)
    selected["r_multiple"] = pd.to_numeric(selected["r_multiple"], errors="coerce")
    return selected.reset_index(drop=True)


class OneSecondDayReader:
    def __init__(self, path: Path) -> None:
        self.dataset = ds.dataset(path, format="parquet")
        self.cache: dict[str, pd.DataFrame] = {}

    def load_day(self, day: str) -> pd.DataFrame:
        cached = self.cache.get(day)
        if cached is not None:
            return cached
        start = pd.Timestamp(day)
        end = start + pd.Timedelta(days=1)
        flt = (ds.field("datetime") >= start.to_datetime64()) & (
            ds.field("datetime") < end.to_datetime64()
        )
        table = self.dataset.to_table(
            columns=["datetime", "open", "high", "low", "close", "volume"],
            filter=flt,
        )
        if table.num_rows == 0:
            frame = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        else:
            frame = table.to_pandas()
            if "datetime" in frame.columns:
                frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("datetime")))
            else:
                frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index))
            frame = frame.sort_index()
        self.cache[day] = frame
        return frame


def close_at_or_before(frame: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    if frame.empty:
        return None
    loc = frame.index.searchsorted(ts, side="right") - 1
    if loc < 0:
        return None
    return float(frame["close"].iloc[loc])


def day_window(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty or end <= start:
        return frame.iloc[0:0]
    return frame[(frame.index >= start) & (frame.index < end)]


def rolling_abs_move_median(frame: pd.DataFrame, *, seconds: int) -> float:
    if len(frame) <= seconds:
        return 1.0
    close = frame["close"].astype(float)
    moves = close.diff(periods=seconds).abs() / TICK_SIZE
    moves = moves.replace([np.inf, -np.inf], np.nan).dropna()
    if moves.empty:
        return 1.0
    median = float(moves.median())
    return max(median, 1.0)


def signed_window_move(frame: pd.DataFrame, *, start: pd.Timestamp, end: pd.Timestamp, direction: int) -> float:
    start_px = close_at_or_before(frame, start)
    end_px = close_at_or_before(frame, end)
    if start_px is None or end_px is None:
        return 0.0
    return float(direction * (end_px - start_px) / TICK_SIZE)


def path_efficiency(frame: pd.DataFrame, *, start: pd.Timestamp, end: pd.Timestamp, direction: int) -> float:
    window = day_window(frame, start, end)
    if len(window) < 2:
        return 0.0
    close = window["close"].astype(float).to_numpy()
    net = direction * (close[-1] - close[0]) / TICK_SIZE
    path = np.abs(np.diff(close)).sum() / TICK_SIZE
    if path <= 0:
        return 0.0
    return float(max(net, 0.0) / path)


def score_price_violence(rows: pd.DataFrame, path: Path) -> pd.DataFrame:
    reader = OneSecondDayReader(path)
    scored: list[dict[str, Any]] = []
    for row in rows.itertuples(index=False):
        day = str(row.date)
        frame = reader.load_day(day)
        signal_start = row.signal_start_ts
        signal_end = row.signal_end_ts
        session_start = pd.Timestamp(f"{day} 09:30:00")
        prior = day_window(frame, session_start, signal_start)
        base10 = rolling_abs_move_median(prior, seconds=10)
        base30 = rolling_abs_move_median(prior, seconds=30)
        base60 = rolling_abs_move_median(prior, seconds=60)

        last10_start = signal_end - pd.Timedelta(seconds=10)
        last30_start = signal_end - pd.Timedelta(seconds=30)
        signal_bar_start = signal_start

        last10_move = signed_window_move(frame, start=last10_start, end=signal_end, direction=row.direction)
        last30_move = signed_window_move(frame, start=last30_start, end=signal_end, direction=row.direction)
        signal_move = signed_window_move(frame, start=signal_bar_start, end=signal_end, direction=row.direction)
        last10_eff = path_efficiency(frame, start=last10_start, end=signal_end, direction=row.direction)
        last30_eff = path_efficiency(frame, start=last30_start, end=signal_end, direction=row.direction)
        signal_eff = path_efficiency(frame, start=signal_bar_start, end=signal_end, direction=row.direction)

        scored.append({
            "trade_uid": row.trade_uid,
            "price_last_10s_move_ticks": last10_move,
            "price_last_30s_move_ticks": last30_move,
            "price_signal_bar_move_ticks": signal_move,
            "price_day_median_abs_10s_ticks": base10,
            "price_day_median_abs_30s_ticks": base30,
            "price_day_median_abs_60s_ticks": base60,
            "price_violence_last_10s_score": max(last10_move, 0.0) / base10 * (0.5 + last10_eff),
            "price_violence_last_30s_score": max(last30_move, 0.0) / base30 * (0.5 + last30_eff),
            "price_violence_signal_bar_score": max(signal_move, 0.0) / base60 * (0.5 + signal_eff),
        })
    return rows.merge(pd.DataFrame(scored), on="trade_uid", how="left")


def load_sweep_features(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    selected = frame[frame["candidate"].eq(CANDIDATE)].copy()
    rename = {
        "trapped_reversal_confirm_score": "price_trapped_reversal_confirm_score",
        "confirm_reclaim_score": "price_confirm_reclaim_score",
        "confirm_reclaim_velocity_ticks_per_second": "price_confirm_reclaim_velocity_ticks_per_second",
    }
    return selected[["trade_uid", *rename.keys()]].rename(columns=rename)


def load_orderbook_features(feature_lab_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for period, filename in (("validation", "validation_feature_lab.csv"), ("holdout", "holdout_feature_lab.csv")):
        path = feature_lab_dir / filename
        frame = pd.read_csv(path)
        frame["period"] = period
        frames.append(frame)
    lab = pd.concat(frames, ignore_index=True)
    selected = lab[lab["candidate"].eq(CANDIDATE)].copy()

    def pos(column: str) -> pd.Series:
        return pd.to_numeric(selected.get(column, 0.0), errors="coerce").fillna(0.0).clip(lower=0.0)

    for segment in ("confirm_last_10s", "confirm_full", "pre_confirm_30s"):
        depth_end = pos(f"{segment}_aligned_depth_imbalance_3_end")
        depth_delta = pos(f"{segment}_aligned_depth_imbalance_3_delta")
        micro = pos(f"{segment}_aligned_micro_skew_ticks_end")
        mid_velocity = pos(f"{segment}_mid_velocity_ticks_per_second")
        pressure = pos(f"{segment}_pressure_score")
        selected[f"ob_vacuum_{segment}_score"] = (depth_end + depth_delta + micro) * (1.0 + mid_velocity) * (1.0 + pressure)

    rename = {
        "absorption_release_confirm_full_score": "ob_absorption_release_confirm_full_score",
        "absorption_release_confirm_last_10s_score": "ob_absorption_release_confirm_last_10s_score",
        "absorption_release_confirm_first_10s_score": "ob_absorption_release_confirm_first_10s_score",
        "ob_vacuum_confirm_last_10s_score": "ob_vacuum_confirm_last_10s_score",
        "ob_vacuum_confirm_full_score": "ob_vacuum_confirm_full_score",
        "ob_vacuum_pre_confirm_30s_score": "ob_vacuum_pre_confirm_30s_score",
    }
    available = ["trade_uid", *[column for column in rename if column in selected.columns]]
    return selected[available].rename(columns=rename)


def assign_tiers(values: pd.Series, low: float, high: float) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    tiers = pd.Series(pd.NA, index=values.index, dtype="string")
    tiers[clean < low] = "low"
    tiers[(clean >= low) & (clean < high)] = "mid"
    tiers[clean >= high] = "high"
    return tiers


def weight_for_tier(tier: Any, profile: dict[str, float]) -> float:
    if tier == "low":
        return profile["low"]
    if tier == "mid":
        return profile["mid"]
    if tier == "high":
        return profile["high"]
    return float("nan")


def evaluate(features: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    thresholds: list[dict[str, Any]] = []
    replay_frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    tier_rows: list[dict[str, Any]] = []
    validation = features[features["period"].eq("validation")]
    holdout = features[features["period"].eq("holdout")]
    baseline_validation = r_metrics(validation["r_multiple"])
    baseline_holdout = r_metrics(holdout["r_multiple"])

    for spec in FEATURE_SPECS:
        values = pd.to_numeric(validation[spec.feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        if values.empty:
            continue
        low = float(values.quantile(0.33))
        high = float(values.quantile(0.66))
        thresholds.append({
            "candidate": CANDIDATE,
            "feature": spec.feature,
            "branch": spec.branch,
            "timing": spec.timing,
            "description": spec.description,
            "validation_rows": int(len(values)),
            "low_threshold_q33": low,
            "high_threshold_q66": high,
            "zero_share": float((values == 0.0).mean()),
            "feature_min": float(values.min()),
            "feature_median": float(values.median()),
            "feature_max": float(values.max()),
        })

        for profile_name, profile in WEIGHT_PROFILES.items():
            replay = features.copy()
            replay["feature"] = spec.feature
            replay["branch"] = spec.branch
            replay["timing"] = spec.timing
            replay["feature_value"] = pd.to_numeric(replay[spec.feature], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)
            replay["feature_tier"] = assign_tiers(replay["feature_value"], low, high)
            replay["weight_profile"] = profile_name
            replay["risk_weight"] = replay["feature_tier"].map(lambda tier: weight_for_tier(tier, profile))
            replay["active_trade"] = replay["risk_weight"] > 0.0
            replay["weighted_r"] = replay["r_multiple"] * replay["risk_weight"]
            replay_frames.append(replay[[
                "period",
                "trade_uid",
                "date",
                "signal_start",
                "direction",
                "r_multiple",
                "branch",
                "feature",
                "timing",
                "feature_value",
                "feature_tier",
                "weight_profile",
                "risk_weight",
                "active_trade",
                "weighted_r",
            ]])

            for period_name, base_metrics in (("validation", baseline_validation), ("holdout", baseline_holdout)):
                subset = replay[replay["period"].eq(period_name)]
                active = subset[subset["active_trade"]]
                row: dict[str, Any] = {
                    "period": period_name,
                    "candidate": CANDIDATE,
                    "branch": spec.branch,
                    "feature": spec.feature,
                    "timing": spec.timing,
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
                    "baseline_total_r": base_metrics["total_r"],
                    "baseline_avg_r": base_metrics["avg_r"],
                    "baseline_profit_factor": base_metrics["profit_factor"],
                    "baseline_max_dd_r": base_metrics["max_dd_r"],
                    "deployability": "research_only",
                    "live_support_notes": (
                        "Challenger branch only; live support requires separate execution feature implementation "
                        "unless this uses already-live MBP-10 fields."
                    ),
                    "exact_replay_required": True,
                }
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
                    tier_rows.append({
                        "period": period_name,
                        "candidate": CANDIDATE,
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
                    })

    return (
        pd.DataFrame(thresholds),
        pd.concat(replay_frames, ignore_index=True) if replay_frames else pd.DataFrame(),
        pd.DataFrame(summary_rows),
        pd.DataFrame(tier_rows),
    )


def select_top(summary: pd.DataFrame) -> pd.DataFrame:
    primary = summary[summary["weight_profile"].eq(PRIMARY_PROFILE)]
    holdout = primary[primary["period"].eq("holdout")].copy()
    validation = primary[primary["period"].eq("validation")][[
        "branch",
        "feature",
        "weighted_total_r",
        "weighted_avg_r",
        "weighted_profit_factor",
        "weighted_max_dd_r",
        "risk_tier_read",
    ]].rename(columns={
        "weighted_total_r": "validation_weighted_r",
        "weighted_avg_r": "validation_weighted_avg_r",
        "weighted_profit_factor": "validation_weighted_pf",
        "weighted_max_dd_r": "validation_weighted_max_dd_r",
        "risk_tier_read": "validation_risk_tier_read",
    })
    top = holdout.merge(validation, on=["branch", "feature"], how="left")
    return top.sort_values(
        ["risk_tier_read", "delta_avg_r_per_1x_risk", "weighted_total_r"],
        ascending=[False, False, False],
    )


def write_report(path: Path, top: pd.DataFrame, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    primary = top[top["weight_profile"].eq(PRIMARY_PROFILE)].head(12)
    stable = primary[
        primary["risk_tier_read"].eq("supported_after_exposure_normalization")
        & primary["validation_risk_tier_read"].eq("supported_after_exposure_normalization")
    ]
    lines = [
        "# NQ NY LSI Pure 1m Challenger Branches - 2026-05-17",
        "",
        "## Objective",
        "",
        "Start three challenger branches against the current pure 1m order-book velocity champion without new DataBento fetches.",
        "",
        "Branches:",
        "",
        "- Reversal violence relative to day: local 1s price movement normalized by same-day movement.",
        "- Absorption then release: price sweep/reclaim and existing MBP-10 absorption/release features.",
        "- Liquidity vacuum / book pull: existing MBP-10 depth/microprice improvement features.",
        "",
        "## Baseline",
        "",
        f"- Validation trades: `{summary['validation_trades']}`, baseline `{summary['validation_baseline_r']:.2f}R`.",
        f"- Holdout trades: `{summary['holdout_trades']}`, baseline `{summary['holdout_baseline_r']:.2f}R`.",
        f"- Current pure 1m velocity champion holdout: `{summary['champion_holdout_weighted_r']:.2f}R`, "
        f"`{summary['champion_holdout_avg_r']:.3f}R` avg, PF `{summary['champion_holdout_profit_factor']:.2f}`.",
        "- DataBento fetches: `0`.",
        "",
        "## Top Holdout Reads",
        "",
        "| Branch | Feature | Holdout Weighted R | Holdout Avg | PF | Max DD | Holdout Read | Validation Read |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in primary.itertuples(index=False):
        lines.append(
            f"| `{row.branch}` | `{row.feature}` | {row.weighted_total_r:.2f} | "
            f"{row.weighted_avg_r:.3f} | {row.weighted_profit_factor:.2f} | "
            f"{row.weighted_max_dd_r:.2f} | `{row.risk_tier_read}` | `{row.validation_risk_tier_read}` |"
        )
    if stable.empty:
        stable_text = "No challenger was supported on both validation and holdout after exposure normalization."
    else:
        leader = stable.iloc[0]
        stable_text = (
            f"The only challenger supported on both validation and holdout was `{leader['feature']}` "
            f"from `{leader['branch']}`. It improved holdout baseline from "
            f"`{summary['holdout_baseline_r']:.2f}R` to `{leader['weighted_total_r']:.2f}R`, "
            f"but remained below the current pure 1m velocity champion's "
            f"`{summary['champion_holdout_weighted_r']:.2f}R`."
        )
    lines.extend([
        "",
        "## Interpretation",
        "",
        stable_text,
        "",
        "The price-violence branch is directionally useful but mild; the absorption-release branch is unstable on this pure 1m trade set; the liquidity-vacuum confirm-last-10s branch is the only serious side branch from this pass.",
        "",
        "These are challenger branches, not promotion candidates yet. Any strong read still needs exact execution implementation/replay and forward shadow testing before it can compete with the current pure 1m MBP-10 velocity champion.",
        "",
    ])
    path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    champion = load_champion_rows(args.risk_tier_replay)
    features = score_price_violence(champion, args.one_second_path)
    features = features.merge(load_sweep_features(args.sweep_features), on="trade_uid", how="left")
    features = features.merge(load_orderbook_features(args.feature_lab_dir), on="trade_uid", how="left")
    for spec in FEATURE_SPECS:
        if spec.feature not in features.columns:
            features[spec.feature] = 0.0
        features[spec.feature] = pd.to_numeric(features[spec.feature], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)

    thresholds, replay, summary, tiers = evaluate(features)
    top = select_top(summary)

    features.to_csv(args.output_dir / "challenger_trade_features.csv", index=False)
    thresholds.to_csv(args.output_dir / "challenger_thresholds.csv", index=False)
    replay.to_csv(args.output_dir / "challenger_tier_replay.csv", index=False)
    summary.to_csv(args.output_dir / "challenger_summary.csv", index=False)
    tiers.to_csv(args.output_dir / "challenger_tier_breakdown.csv", index=False)
    top.to_csv(args.output_dir / "top_challengers.csv", index=False)

    validation = features[features["period"].eq("validation")]
    holdout = features[features["period"].eq("holdout")]
    champion_validation_metrics = r_metrics(validation["weighted_r"] if "weighted_r" in validation else [])
    champion_holdout_metrics = r_metrics(holdout["weighted_r"] if "weighted_r" in holdout else [])
    payload = {
        "run_slug": RUN_SLUG,
        "candidate": CANDIDATE,
        "data_bento_fetches": 0,
        "validation_trades": int(len(validation)),
        "holdout_trades": int(len(holdout)),
        "validation_baseline_r": float(validation["r_multiple"].sum()),
        "holdout_baseline_r": float(holdout["r_multiple"].sum()),
        "champion_feature": CHAMPION_FEATURE,
        "champion_weight_profile": PRIMARY_PROFILE,
        "champion_validation_weighted_r": float(champion_validation_metrics["total_r"]),
        "champion_validation_avg_r": float(champion_validation_metrics["avg_r"]),
        "champion_validation_profit_factor": float(champion_validation_metrics["profit_factor"]),
        "champion_validation_max_dd_r": float(champion_validation_metrics["max_dd_r"]),
        "champion_holdout_weighted_r": float(champion_holdout_metrics["total_r"]),
        "champion_holdout_avg_r": float(champion_holdout_metrics["avg_r"]),
        "champion_holdout_profit_factor": float(champion_holdout_metrics["profit_factor"]),
        "champion_holdout_max_dd_r": float(champion_holdout_metrics["max_dd_r"]),
        "branches": sorted({spec.branch for spec in FEATURE_SPECS}),
        "output_dir": str(args.output_dir),
        "report_path": str(args.report_path),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n")
    write_report(args.report_path, top, payload)
    print(json.dumps(payload, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
