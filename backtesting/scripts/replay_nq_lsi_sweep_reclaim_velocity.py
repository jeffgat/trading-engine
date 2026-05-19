#!/usr/bin/env python3
"""No-fetch sweep-reclaim velocity replay for NQ NY LSI candidates.

This is the first no-extra-DataBento branch from the discretionary signal
roadmap. It reuses existing frozen LSI candidate trades and local 1-second
OHLCV data to test whether a price-action proxy for "violent rejection from a
watched level" has validation-to-holdout signal as a risk-tier overlay.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as ds


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_ny_lsi_sweep_reclaim_velocity_20260515"
DEFAULT_INPUT_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_feature_lab_20260514"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_SWEEP_RECLAIM_VELOCITY_20260515.md"
DEFAULT_ONE_SECOND_PATH = ROOT / "data" / "raw" / "NQ_1s.parquet"
TICK_SIZE = 0.25


FEATURE_SPECS: tuple[dict[str, str], ...] = (
    {
        "feature": "pre_signal_reclaim_score",
        "family": "sweep-reclaim",
        "timing": "entry_safe_before_signal_bar",
        "description": "Sweep depth, reclaim speed, and follow-through measured only up to signal_start.",
    },
    {
        "feature": "confirm_reclaim_score",
        "family": "sweep-reclaim",
        "timing": "causal_at_signal_close",
        "description": "Sweep depth, reclaim speed, hold ratio, and follow-through through signal_end.",
    },
    {
        "feature": "confirm_reclaim_velocity_ticks_per_second",
        "family": "sweep-reclaim",
        "timing": "causal_at_signal_close",
        "description": "Depth divided by seconds from adverse extreme to reclaim.",
    },
    {
        "feature": "confirm_post_reclaim_move_ticks",
        "family": "sweep-reclaim",
        "timing": "causal_at_signal_close",
        "description": "Directional move from anchor into signal_end after reclaim.",
    },
    {
        "feature": "compression_expansion_confirm_score",
        "family": "compression-expansion",
        "timing": "causal_at_signal_close",
        "description": "Low pre-sweep 60s range followed by directional signal-end expansion.",
    },
    {
        "feature": "trapped_reversal_confirm_score",
        "family": "failed-continuation",
        "timing": "causal_at_signal_close",
        "description": "Adverse sweep depth that quickly reclaims and expands back in trade direction.",
    },
    {
        "feature": "post_reclaim_30s_score",
        "family": "post-confirm-diagnostic",
        "timing": "post_confirm_management_only",
        "description": "30s follow-through after reclaim; diagnostic for management, not entry.",
    },
    {
        "feature": "post_reclaim_60s_score",
        "family": "post-confirm-diagnostic",
        "timing": "post_confirm_management_only",
        "description": "60s follow-through after reclaim; diagnostic for management, not entry.",
    },
)


WEIGHT_PROFILES: tuple[dict[str, float | str], ...] = (
    {
        "profile": "tier_0p5_1_1p5",
        "low": 0.5,
        "mid": 1.0,
        "high": 1.5,
        "description": "Primary exploratory sizing: weak 0.5x, normal 1.0x, strong 1.5x.",
    },
    {
        "profile": "tier_0p75_1_1p25",
        "low": 0.75,
        "mid": 1.0,
        "high": 1.25,
        "description": "Conservative sizing stress.",
    },
    {
        "profile": "tier_0_1_1p5",
        "low": 0.0,
        "mid": 1.0,
        "high": 1.5,
        "description": "Skip weak tier, keep normal/strong sizing.",
    },
)


BASE_COLUMNS = (
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
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--one-second-path", type=Path, default=DEFAULT_ONE_SECOND_PATH)
    return parser.parse_args()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


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
    r = np.asarray(pd.Series(values).dropna(), dtype=float)
    if len(r) == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "max_dd_r": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "max_consec_losses": 0,
        }
    wins = r > 0
    losses = r < 0
    gross_win = float(r[wins].sum()) if wins.any() else 0.0
    gross_loss = float(r[losses].sum()) if losses.any() else 0.0
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) else 0.0
    std = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    avg = float(r.mean())
    sharpe = avg / std * math.sqrt(252) if std > 0.0 else 0.0
    current_losses = 0
    max_losses = 0
    for value in r:
        if value < 0.0:
            current_losses += 1
            max_losses = max(max_losses, current_losses)
        else:
            current_losses = 0
    return {
        "trades": int(len(r)),
        "win_rate": float(wins.mean()),
        "total_r": float(equity[-1]),
        "avg_r": avg,
        "max_dd_r": max_dd,
        "profit_factor": abs(gross_win / gross_loss) if gross_loss else 0.0,
        "sharpe": sharpe,
        "calmar": float(equity[-1] / abs(max_dd)) if max_dd else 0.0,
        "max_consec_losses": int(max_losses),
    }


def add_prefixed_metrics(row: dict[str, Any], prefix: str, values: pd.Series | np.ndarray) -> None:
    for key, value in r_metrics(values).items():
        row[f"{prefix}_{key}"] = value


def load_trade_inputs(input_dir: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for period, filename in (
        ("validation", "validation_feature_lab.csv"),
        ("holdout", "holdout_feature_lab.csv"),
    ):
        path = input_dir / filename
        frame = pd.read_csv(path)
        frame["period"] = period
        frames.append(frame)
    trades = pd.concat(frames, ignore_index=True)
    for column in BASE_COLUMNS:
        if column not in trades.columns:
            trades[column] = pd.NA
    trades = trades[list(BASE_COLUMNS)].copy()
    trades["r_multiple"] = pd.to_numeric(trades["r_multiple"], errors="coerce")
    trades["direction"] = pd.to_numeric(trades["direction"], errors="coerce").astype("Int64")
    trades["trade_date"] = pd.to_datetime(trades["date"], errors="coerce")
    trades["year"] = trades["trade_date"].dt.year
    trades["month"] = trades["trade_date"].dt.to_period("M").astype(str)
    return trades.dropna(subset=["date", "direction", "r_multiple"]).reset_index(drop=True)


class OneSecondDayReader:
    def __init__(self, path: Path) -> None:
        self.dataset = ds.dataset(path, format="parquet")

    def load_day(self, day: str) -> pd.DataFrame:
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
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = table.to_pandas()
        if "datetime" in frame.columns:
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("datetime")))
        else:
            frame.index = pd.DatetimeIndex(pd.to_datetime(frame.index))
        frame = frame.sort_index()
        for column in ("open", "high", "low", "close"):
            frame[column] = frame[column].astype("float32")
        frame["volume"] = frame["volume"].astype("float32")
        return frame


def nearest_close_before(frame: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    if frame.empty:
        return None
    loc = frame.index.searchsorted(ts, side="left") - 1
    if loc < 0:
        loc = frame.index.searchsorted(ts, side="right")
        if loc >= len(frame):
            return None
    return float(frame["close"].iloc[loc])


def close_at_or_before(frame: pd.DataFrame, ts: pd.Timestamp) -> float | None:
    if frame.empty:
        return None
    loc = frame.index.searchsorted(ts, side="right") - 1
    if loc < 0:
        return None
    return float(frame["close"].iloc[loc])


def window_frame(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if frame.empty or end <= start:
        return frame.iloc[0:0]
    return frame[(frame.index >= start) & (frame.index < end)]


def direction_crossed(close: pd.Series, anchor: float, direction: int) -> pd.Series:
    if direction > 0:
        return close >= anchor
    return close <= anchor


def directional_move_ticks(start_price: float | None, end_price: float | None, direction: int) -> float:
    if start_price is None or end_price is None:
        return float("nan")
    return float(direction * (end_price - start_price) / TICK_SIZE)


def range_ticks(frame: pd.DataFrame) -> float:
    if frame.empty:
        return float("nan")
    return float((frame["high"].max() - frame["low"].min()) / TICK_SIZE)


def score_reclaim_window(
    *,
    day_frame: pd.DataFrame,
    direction: int,
    anchor_price: float,
    sweep_start: pd.Timestamp,
    horizon_end: pd.Timestamp,
    follow_seconds: int,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "scored": False,
        "sweep_depth_ticks": 0.0,
        "reclaim_seconds": float("nan"),
        "reclaim_velocity_ticks_per_second": 0.0,
        "post_reclaim_move_ticks": 0.0,
        "hold_ratio_after_reclaim": 0.0,
        "score": 0.0,
    }
    sweep_window = window_frame(day_frame, sweep_start, horizon_end)
    if sweep_window.empty:
        return out

    if direction > 0:
        extreme_idx = sweep_window["low"].idxmin()
        extreme_price = float(sweep_window.loc[extreme_idx, "low"])
        depth_ticks = max((anchor_price - extreme_price) / TICK_SIZE, 0.0)
    else:
        extreme_idx = sweep_window["high"].idxmax()
        extreme_price = float(sweep_window.loc[extreme_idx, "high"])
        depth_ticks = max((extreme_price - anchor_price) / TICK_SIZE, 0.0)

    after_extreme = sweep_window[sweep_window.index >= extreme_idx]
    crossed = direction_crossed(after_extreme["close"], anchor_price, direction)
    if not bool(crossed.any()):
        out.update({"scored": True, "sweep_depth_ticks": float(depth_ticks)})
        return out

    reclaim_time = crossed[crossed].index[0]
    reclaim_seconds = max((reclaim_time - extreme_idx).total_seconds(), 0.0)
    follow_end = min(horizon_end, reclaim_time + pd.Timedelta(seconds=follow_seconds))
    follow_frame = window_frame(day_frame, reclaim_time, follow_end)
    if follow_frame.empty:
        end_price = close_at_or_before(day_frame, horizon_end)
        hold_ratio = 0.0
    else:
        end_price = float(follow_frame["close"].iloc[-1])
        hold_ratio = float(direction_crossed(follow_frame["close"], anchor_price, direction).mean())

    move_ticks = directional_move_ticks(anchor_price, end_price, direction)
    positive_move = max(move_ticks, 0.0) if np.isfinite(move_ticks) else 0.0
    velocity = depth_ticks / max(reclaim_seconds, 1.0) if depth_ticks > 0.0 else 0.0
    score = positive_move * hold_ratio * min(depth_ticks / 8.0, 3.0) / math.sqrt(reclaim_seconds + 1.0)
    out.update(
        {
            "scored": True,
            "sweep_depth_ticks": float(depth_ticks),
            "reclaim_seconds": float(reclaim_seconds),
            "reclaim_velocity_ticks_per_second": float(velocity),
            "post_reclaim_move_ticks": float(move_ticks) if np.isfinite(move_ticks) else 0.0,
            "hold_ratio_after_reclaim": hold_ratio,
            "score": float(score),
        }
    )
    return out


def score_trade(row: pd.Series, day_frame: pd.DataFrame) -> dict[str, Any]:
    direction = int(row["direction"])
    signal_start = parse_ts(row["signal_start"])
    signal_end = parse_ts(row["signal_end"])
    sweep_time = parse_ts(row["lsi_sweep_time"])
    if signal_start is None or signal_end is None:
        return {"price_feature_status": "missing_signal_time"}
    if sweep_time is None:
        sweep_time = signal_start - pd.Timedelta(seconds=60)

    anchor_time = max(sweep_time - pd.Timedelta(seconds=1), pd.Timestamp(str(row["date"])))
    anchor_price = nearest_close_before(day_frame, sweep_time)
    if anchor_price is None:
        anchor_price = close_at_or_before(day_frame, sweep_time)
    if anchor_price is None:
        return {"price_feature_status": "missing_anchor_price"}

    pre_start = max(sweep_time - pd.Timedelta(seconds=60), pd.Timestamp(str(row["date"])))
    pre_frame = window_frame(day_frame, pre_start, sweep_time)
    pre_range = range_ticks(pre_frame)

    signal_end_price = close_at_or_before(day_frame, signal_end)
    signal_start_price = close_at_or_before(day_frame, signal_start)
    confirm_dir_move_ticks = directional_move_ticks(anchor_price, signal_end_price, direction)
    pre_signal_dir_move_ticks = directional_move_ticks(anchor_price, signal_start_price, direction)

    pre = score_reclaim_window(
        day_frame=day_frame,
        direction=direction,
        anchor_price=anchor_price,
        sweep_start=sweep_time,
        horizon_end=signal_start,
        follow_seconds=30,
    )
    confirm = score_reclaim_window(
        day_frame=day_frame,
        direction=direction,
        anchor_price=anchor_price,
        sweep_start=sweep_time,
        horizon_end=signal_end,
        follow_seconds=60,
    )
    post30 = score_reclaim_window(
        day_frame=day_frame,
        direction=direction,
        anchor_price=anchor_price,
        sweep_start=sweep_time,
        horizon_end=signal_end + pd.Timedelta(seconds=30),
        follow_seconds=30,
    )
    post60 = score_reclaim_window(
        day_frame=day_frame,
        direction=direction,
        anchor_price=anchor_price,
        sweep_start=sweep_time,
        horizon_end=signal_end + pd.Timedelta(seconds=60),
        follow_seconds=60,
    )

    compression = 1.0 / max(pre_range, 1.0) if np.isfinite(pre_range) else 0.0
    confirm_positive_move = max(confirm_dir_move_ticks, 0.0) if np.isfinite(confirm_dir_move_ticks) else 0.0
    trapped_score = (
        min(confirm["sweep_depth_ticks"] / 8.0, 3.0)
        * max(confirm["reclaim_velocity_ticks_per_second"], 0.0)
        * max(confirm["hold_ratio_after_reclaim"], 0.0)
        * math.sqrt(confirm_positive_move + 1.0)
    )
    return {
        "price_feature_status": "scored",
        "anchor_time": anchor_time.isoformat(),
        "anchor_price": float(anchor_price),
        "pre_60s_range_ticks": float(pre_range) if np.isfinite(pre_range) else float("nan"),
        "pre_signal_dir_move_ticks": float(pre_signal_dir_move_ticks)
        if np.isfinite(pre_signal_dir_move_ticks)
        else float("nan"),
        "confirm_dir_move_ticks": float(confirm_dir_move_ticks)
        if np.isfinite(confirm_dir_move_ticks)
        else float("nan"),
        "pre_signal_sweep_depth_ticks": pre["sweep_depth_ticks"],
        "pre_signal_reclaim_seconds": pre["reclaim_seconds"],
        "pre_signal_reclaim_velocity_ticks_per_second": pre["reclaim_velocity_ticks_per_second"],
        "pre_signal_post_reclaim_move_ticks": pre["post_reclaim_move_ticks"],
        "pre_signal_hold_ratio_after_reclaim": pre["hold_ratio_after_reclaim"],
        "pre_signal_reclaim_score": pre["score"],
        "confirm_sweep_depth_ticks": confirm["sweep_depth_ticks"],
        "confirm_reclaim_seconds": confirm["reclaim_seconds"],
        "confirm_reclaim_velocity_ticks_per_second": confirm["reclaim_velocity_ticks_per_second"],
        "confirm_post_reclaim_move_ticks": confirm["post_reclaim_move_ticks"],
        "confirm_hold_ratio_after_reclaim": confirm["hold_ratio_after_reclaim"],
        "confirm_reclaim_score": confirm["score"],
        "compression_expansion_confirm_score": compression * confirm_positive_move,
        "trapped_reversal_confirm_score": float(trapped_score),
        "post_reclaim_30s_move_ticks": post30["post_reclaim_move_ticks"],
        "post_reclaim_30s_score": post30["score"],
        "post_reclaim_60s_move_ticks": post60["post_reclaim_move_ticks"],
        "post_reclaim_60s_score": post60["score"],
    }


def build_feature_frame(trades: pd.DataFrame, reader: OneSecondDayReader) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for day, group in trades.groupby("date", sort=True):
        day_frame = reader.load_day(str(day))
        for _, trade in group.iterrows():
            base = trade.to_dict()
            base.update(score_trade(trade, day_frame))
            rows.append(base)
    frame = pd.DataFrame(rows)
    for spec in FEATURE_SPECS:
        frame[spec["feature"]] = pd.to_numeric(frame[spec["feature"]], errors="coerce").fillna(0.0)
    return frame


def threshold_rows(feature_frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    validation = feature_frame[feature_frame["period"] == "validation"]
    for candidate, group in validation.groupby("candidate"):
        scored = group[group["price_feature_status"] == "scored"]
        for spec in FEATURE_SPECS:
            values = pd.to_numeric(scored[spec["feature"]], errors="coerce").replace(
                [np.inf, -np.inf], np.nan
            ).dropna()
            if values.empty:
                continue
            rows.append(
                {
                    "candidate": candidate,
                    "feature": spec["feature"],
                    "family": spec["family"],
                    "timing": spec["timing"],
                    "description": spec["description"],
                    "validation_rows": int(len(values)),
                    "low_threshold_q33": float(values.quantile(0.33)),
                    "high_threshold_q66": float(values.quantile(0.66)),
                    "feature_min": float(values.min()),
                    "feature_median": float(values.median()),
                    "feature_max": float(values.max()),
                    "zero_share": float((values == 0.0).mean()),
                }
            )
    return pd.DataFrame(rows)


def assign_tiers(values: pd.Series, low: float, high: float) -> pd.Series:
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    tiers = pd.Series(pd.NA, index=values.index, dtype="string")
    tiers[clean < low] = "low"
    tiers[(clean >= low) & (clean < high)] = "mid"
    tiers[clean >= high] = "high"
    return tiers


def tier_weight(tier: Any, profile: dict[str, float | str]) -> float:
    if pd.isna(tier):
        return float("nan")
    if tier == "low":
        return float(profile["low"])
    if tier == "mid":
        return float(profile["mid"])
    if tier == "high":
        return float(profile["high"])
    return float("nan")


def build_replays(
    feature_frame: pd.DataFrame,
    thresholds: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    trade_replays: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    tier_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    for _, threshold in thresholds.iterrows():
        candidate = threshold["candidate"]
        feature = threshold["feature"]
        for profile in WEIGHT_PROFILES:
            for period in ("validation", "holdout"):
                subset = feature_frame[
                    (feature_frame["candidate"] == candidate)
                    & (feature_frame["period"] == period)
                    & (feature_frame["price_feature_status"] == "scored")
                ].copy()
                if subset.empty:
                    continue
                subset[feature] = pd.to_numeric(subset[feature], errors="coerce").fillna(0.0)
                subset["feature"] = feature
                subset["feature_family"] = threshold["family"]
                subset["feature_timing"] = threshold["timing"]
                subset["feature_value"] = subset[feature]
                subset["feature_tier"] = assign_tiers(
                    subset[feature],
                    float(threshold["low_threshold_q33"]),
                    float(threshold["high_threshold_q66"]),
                )
                subset["weight_profile"] = profile["profile"]
                subset["risk_weight"] = subset["feature_tier"].map(
                    lambda tier: tier_weight(tier, profile)
                )
                subset["active_trade"] = subset["risk_weight"] > 0.0
                subset["weighted_r"] = subset["r_multiple"] * subset["risk_weight"]
                active = subset[subset["active_trade"]]

                row: dict[str, Any] = {
                    "period": period,
                    "candidate": candidate,
                    "feature": feature,
                    "feature_family": threshold["family"],
                    "feature_timing": threshold["timing"],
                    "weight_profile": profile["profile"],
                    "low_weight": profile["low"],
                    "mid_weight": profile["mid"],
                    "high_weight": profile["high"],
                    "low_threshold_q33": threshold["low_threshold_q33"],
                    "high_threshold_q66": threshold["high_threshold_q66"],
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
                        "No extra historical fetch required; live support still needs this "
                        "1s price-action feature implemented in the execution engine."
                    ),
                    "exact_replay_required": True,
                }
                add_prefixed_metrics(row, "baseline", subset["r_multiple"])
                add_prefixed_metrics(row, "weighted", active["weighted_r"])
                row["weighted_avg_r_per_1x_risk"] = (
                    float(active["weighted_r"].sum() / active["risk_weight"].sum())
                    if len(active) and float(active["risk_weight"].sum()) > 0.0
                    else 0.0
                )
                row["delta_total_r"] = float(row["weighted_total_r"] - row["baseline_total_r"])
                row["delta_avg_r"] = float(row["weighted_avg_r"] - row["baseline_avg_r"])
                row["delta_avg_r_per_1x_risk"] = float(
                    row["weighted_avg_r_per_1x_risk"] - row["baseline_avg_r"]
                )
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
                            "period": period,
                            "candidate": candidate,
                            "feature": feature,
                            "feature_family": threshold["family"],
                            "feature_timing": threshold["timing"],
                            "weight_profile": profile["profile"],
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

                for month, month_group in active.groupby("month"):
                    monthly_rows.append(
                        {
                            "period": period,
                            "candidate": candidate,
                            "feature": feature,
                            "weight_profile": profile["profile"],
                            "month": month,
                            "trades": int(len(month_group)),
                            "weighted_r": float(month_group["weighted_r"].sum()),
                            "baseline_r": float(month_group["r_multiple"].sum()),
                            "avg_weight": float(month_group["risk_weight"].mean()),
                        }
                    )

                trade_replays.append(
                    subset[
                        [
                            "period",
                            "candidate",
                            "feature",
                            "feature_family",
                            "feature_timing",
                            "feature_value",
                            "feature_tier",
                            "weight_profile",
                            "risk_weight",
                            "active_trade",
                            "weighted_r",
                            "r_multiple",
                            "date",
                            "signal_start",
                            "signal_end",
                            "fill_time",
                            "direction",
                            "confirmation",
                            "entry_price",
                            "risk_points",
                            "trade_uid",
                        ]
                    ]
                )

    return (
        pd.concat(trade_replays, ignore_index=True) if trade_replays else pd.DataFrame(),
        pd.DataFrame(summary_rows),
        pd.DataFrame(tier_rows),
        pd.DataFrame(monthly_rows),
    )


def build_orderbook_correlation(input_dir: Path, feature_frame: pd.DataFrame) -> pd.DataFrame:
    orderbook_frames: list[pd.DataFrame] = []
    for period, filename in (
        ("validation", "validation_feature_lab.csv"),
        ("holdout", "holdout_feature_lab.csv"),
    ):
        path = input_dir / filename
        frame = pd.read_csv(path)
        frame["period"] = period
        orderbook_frames.append(frame)
    orderbook = pd.concat(orderbook_frames, ignore_index=True)

    orderbook_features = [
        column
        for column in (
            "pre_confirm_30s_pressure_score",
            "confirm_last_10s_mid_velocity_ticks_per_second",
        )
        if column in orderbook.columns
    ]
    price_features = [
        "trapped_reversal_confirm_score",
        "confirm_reclaim_velocity_ticks_per_second",
        "post_reclaim_60s_score",
    ]
    if not orderbook_features:
        return pd.DataFrame()

    merge_cols = ["trade_uid", "candidate", "period"]
    merged = feature_frame.merge(
        orderbook[merge_cols + orderbook_features],
        on=merge_cols,
        how="left",
    )
    rows: list[dict[str, Any]] = []
    period_groups = [("combined", merged)]
    period_groups.extend((period, group) for period, group in merged.groupby("period"))
    for period, period_group in period_groups:
        for candidate, group in period_group.groupby("candidate"):
            for orderbook_feature in orderbook_features:
                for price_feature in price_features:
                    x = pd.to_numeric(group[orderbook_feature], errors="coerce").replace(
                        [np.inf, -np.inf], np.nan
                    )
                    y = pd.to_numeric(group[price_feature], errors="coerce").replace(
                        [np.inf, -np.inf], np.nan
                    )
                    valid = x.notna() & y.notna()
                    if int(valid.sum()) < 5:
                        continue
                    rows.append(
                        {
                            "period": period,
                            "candidate": candidate,
                            "orderbook_feature": orderbook_feature,
                            "price_feature": price_feature,
                            "n": int(valid.sum()),
                            "pearson": float(x[valid].corr(y[valid])),
                            "spearman": float(x[valid].corr(y[valid], method="spearman")),
                        }
                    )
    return pd.DataFrame(rows)


def select_top(summary: pd.DataFrame) -> pd.DataFrame:
    primary = summary[summary["weight_profile"] == "tier_0p5_1_1p5"].copy()
    holdout = primary[primary["period"] == "holdout"].copy()
    validation = primary[primary["period"] == "validation"].copy()
    key_cols = ["candidate", "feature", "weight_profile"]
    merged = holdout.merge(
        validation[
            key_cols
            + [
                "weighted_total_r",
                "baseline_total_r",
                "weighted_avg_r_per_1x_risk",
                "baseline_avg_r",
                "delta_avg_r_per_1x_risk",
                "risk_tier_read",
            ]
        ],
        on=key_cols,
        suffixes=("_holdout", "_validation"),
    )
    merged["passes_validation_and_holdout"] = (
        (merged["delta_avg_r_per_1x_risk_validation"] > 0.0)
        & (merged["delta_avg_r_per_1x_risk_holdout"] > 0.0)
        & (merged["active_tier_count"] > 1)
    )
    merged = merged.sort_values(
        [
            "passes_validation_and_holdout",
            "delta_avg_r_per_1x_risk_holdout",
            "delta_total_r",
            "weighted_total_r_holdout",
        ],
        ascending=[False, False, False, False],
    )
    return merged


def write_report(
    report_path: Path,
    *,
    feature_frame: pd.DataFrame,
    thresholds: pd.DataFrame,
    summary: pd.DataFrame,
    tier_breakdown: pd.DataFrame,
    correlation: pd.DataFrame,
    top: pd.DataFrame,
    output_dir: Path,
) -> None:
    primary = summary[summary["weight_profile"] == "tier_0p5_1_1p5"].copy()
    holdout_top = top.head(12)
    lines = [
        "# NQ NY LSI Sweep-Reclaim Velocity Replay",
        "",
        "- Objective: test no-extra-fetch price-action proxies for the discretionary idea that violent sweep/reclaim reversals are stronger.",
        "- Data: existing frozen LSI candidate trade CSVs plus local `NQ_1s.parquet`; no DataBento fetch.",
        "- Thresholds: validation-only terciles by candidate and feature, replayed unchanged on holdout.",
        "- Primary sizing profile: low `0.5x`, mid `1.0x`, high `1.5x`.",
        "- Deployability: `research_only` until implemented in the live/exact execution path, but the data requirement is 1s price bars rather than paid MBP-10 depth.",
        "",
        "## Best Primary Holdout Reads",
        "",
        "| Candidate | Feature | Timing | Val Base R | Val Tier R | Holdout Base R | Holdout Tier R | Holdout Per-1x Avg | Read |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for _, row in holdout_top.iterrows():
        lines.append(
            f"| `{row['candidate']}` | `{row['feature']}` | `{row['feature_timing']}` | "
            f"{row['baseline_total_r_validation']:.2f} | {row['weighted_total_r_validation']:.2f} | "
            f"{row['baseline_total_r_holdout']:.2f} | {row['weighted_total_r_holdout']:.2f} | "
            f"{row['weighted_avg_r_per_1x_risk_holdout']:.3f} | `{row['risk_tier_read_holdout']}` |"
        )

    lines.extend(
        [
            "",
            "## Primary Summary",
            "",
            "| Period | Candidate | Feature | Timing | Trades | Base R | Tier R | Delta R | Base Avg | Per-1x Avg | Tiers | Read |",
            "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    display = primary.sort_values(
        ["period", "candidate", "delta_avg_r_per_1x_risk", "delta_total_r"],
        ascending=[True, True, False, False],
    )
    for _, row in display.iterrows():
        lines.append(
            f"| {row['period']} | `{row['candidate']}` | `{row['feature']}` | `{row['feature_timing']}` | "
            f"{int(row['source_trades'])} | {row['baseline_total_r']:.2f} | {row['weighted_total_r']:.2f} | "
            f"{row['delta_total_r']:.2f} | {row['baseline_avg_r']:.3f} | "
            f"{row['weighted_avg_r_per_1x_risk']:.3f} | {int(row['active_tier_count'])} | "
            f"`{row['risk_tier_read']}` |"
        )

    lines.extend(
        [
            "",
            "## Holdout Tier Breakdown For Best Reads",
            "",
            "| Candidate | Feature | Tier | Trades | Feature Range | Base Avg R | Base R | Weight | Weighted R |",
            "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    best_pairs = {
        (row["candidate"], row["feature"])
        for _, row in holdout_top[holdout_top["passes_validation_and_holdout"]].head(5).iterrows()
    }
    if not best_pairs:
        best_pairs = {(row["candidate"], row["feature"]) for _, row in holdout_top.head(5).iterrows()}
    tier_display = tier_breakdown[
        (tier_breakdown["period"] == "holdout")
        & (tier_breakdown["weight_profile"] == "tier_0p5_1_1p5")
        & tier_breakdown.apply(lambda item: (item["candidate"], item["feature"]) in best_pairs, axis=1)
    ].copy()
    tier_order = {"low": 0, "mid": 1, "high": 2}
    if not tier_display.empty:
        tier_display["tier_order"] = tier_display["tier"].map(tier_order)
        tier_display = tier_display.sort_values(["candidate", "feature", "tier_order"])
    for _, row in tier_display.iterrows():
        lines.append(
            f"| `{row['candidate']}` | `{row['feature']}` | {row['tier']} | {int(row['trades'])} | "
            f"{row['min_feature_value']:.3f}-{row['max_feature_value']:.3f} | "
            f"{row['base_avg_r']:.3f} | {row['base_total_r']:.2f} | {row['weight']:.2f} | "
            f"{row['weighted_total_r']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Orderbook Relationship Check",
            "",
            "| Candidate | Orderbook Feature | Price Feature | N | Pearson | Spearman |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    if correlation.empty:
        lines.append("| n/a | n/a | n/a | 0 | 0.000 | 0.000 |")
    else:
        corr_display = correlation[
            (correlation["period"] == "combined")
            & (
                correlation["orderbook_feature"]
                == "pre_confirm_30s_pressure_score"
            )
        ].copy()
        corr_display["abs_spearman"] = corr_display["spearman"].abs()
        corr_display = corr_display.sort_values("abs_spearman", ascending=False).head(12)
        for _, row in corr_display.iterrows():
            lines.append(
                f"| `{row['candidate']}` | `{row['orderbook_feature']}` | `{row['price_feature']}` | "
                f"{int(row['n'])} | {row['pearson']:.3f} | {row['spearman']:.3f} |"
            )

    lines.extend(
        [
            "",
            "## Feature Coverage",
            "",
            f"- Scored rows: `{int((feature_frame['price_feature_status'] == 'scored').sum())}` / `{len(feature_frame)}`.",
            f"- Candidates: `{feature_frame['candidate'].nunique()}`.",
            f"- Threshold rows: `{len(thresholds)}`.",
            "",
            "## Interpretation",
            "",
            "- This replay is a price-action proxy, not an order-book replacement. If a feature works here, it suggests we can test more history before spending more MBP-10 budget.",
            "- Entry-safe features use information up to `signal_start`; signal-close features use information through `signal_end`; post-confirm features are diagnostics for management only.",
            "- Treat improvements that only appear in post-confirm diagnostics as hold/add/reduce ideas, not entry rules.",
            "- Any promotion still needs exact execution replay with dynamic sizing.",
            "",
            "## Output Files",
            "",
            f"- `{output_dir / 'trade_sweep_reclaim_features.csv'}`",
            f"- `{output_dir / 'frozen_thresholds.csv'}`",
            f"- `{output_dir / 'risk_tier_summary.csv'}`",
            f"- `{output_dir / 'tier_breakdown.csv'}`",
            f"- `{output_dir / 'monthly_breakdown.csv'}`",
            f"- `{output_dir / 'top_features.csv'}`",
            f"- `{output_dir / 'orderbook_price_correlation.csv'}`",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI sweep-reclaim velocity replay", flush=True)
    trades = load_trade_inputs(args.input_dir)
    print(f"Loaded {len(trades):,} frozen trade rows", flush=True)
    reader = OneSecondDayReader(args.one_second_path)
    feature_frame = build_feature_frame(trades, reader)
    thresholds = threshold_rows(feature_frame)
    trade_replay, summary, tier_breakdown, monthly = build_replays(feature_frame, thresholds)
    correlation = build_orderbook_correlation(args.input_dir, feature_frame)
    top = select_top(summary)

    feature_path = args.output_dir / "trade_sweep_reclaim_features.csv"
    threshold_path = args.output_dir / "frozen_thresholds.csv"
    replay_path = args.output_dir / "trade_risk_tier_replay.csv"
    summary_path = args.output_dir / "risk_tier_summary.csv"
    tier_path = args.output_dir / "tier_breakdown.csv"
    monthly_path = args.output_dir / "monthly_breakdown.csv"
    top_path = args.output_dir / "top_features.csv"
    correlation_path = args.output_dir / "orderbook_price_correlation.csv"

    feature_frame.to_csv(feature_path, index=False)
    thresholds.to_csv(threshold_path, index=False)
    trade_replay.to_csv(replay_path, index=False)
    summary.to_csv(summary_path, index=False)
    tier_breakdown.to_csv(tier_path, index=False)
    monthly.to_csv(monthly_path, index=False)
    top.to_csv(top_path, index=False)
    correlation.to_csv(correlation_path, index=False)

    payload = {
        "run_slug": RUN_SLUG,
        "input_dir": str(args.input_dir),
        "one_second_path": str(args.one_second_path),
        "output_dir": str(args.output_dir),
        "report_path": str(args.report_path),
        "rows": {
            "trade_inputs": int(len(trades)),
            "features": int(len(feature_frame)),
            "thresholds": int(len(thresholds)),
            "summary": int(len(summary)),
            "trade_replay": int(len(trade_replay)),
        },
        "outputs": {
            "features": str(feature_path),
            "thresholds": str(threshold_path),
            "trade_replay": str(replay_path),
            "summary": str(summary_path),
            "tier_breakdown": str(tier_path),
            "monthly_breakdown": str(monthly_path),
            "top_features": str(top_path),
            "orderbook_price_correlation": str(correlation_path),
            "report": str(args.report_path),
        },
    }
    save_json(args.output_dir / "summary.json", payload)
    write_report(
        args.report_path,
        feature_frame=feature_frame,
        thresholds=thresholds,
        summary=summary,
        tier_breakdown=tier_breakdown,
        correlation=correlation,
        top=top,
        output_dir=args.output_dir,
    )
    print(f"Wrote {summary_path}", flush=True)
    print(f"Wrote {args.report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
