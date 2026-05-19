#!/usr/bin/env python3
"""Feature lab for NQ NY LSI order-book momentum.

This expands the first MBP-10 impulse pass from one blunt confirmation-bar
aggregate into smaller causal windows: pre-confirm absorption, early/late
confirmation release, and post-confirm follow-through diagnostics.

The script does not fetch DataBento data. It reuses the downloaded DBN files
referenced by the existing trade_orderbook_impulse.csv artifacts.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_nq_ny_lsi_cisd_candidate_validation as val
import run_nq_ny_lsi_orderbook_impulse as impulse


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_ny_lsi_orderbook_feature_lab_20260514"
DEFAULT_VALIDATION_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_impulse_validation_full_20260514"
    / "trade_orderbook_impulse.csv"
)
DEFAULT_HOLDOUT_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_impulse_20260513"
    / "trade_orderbook_impulse.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_ORDERBOOK_FEATURE_LAB_20260514.md"
ET_TZ = impulse.ET_TZ
TICK_SIZE = impulse.TICK_SIZE


@dataclasses.dataclass(frozen=True)
class SegmentDef:
    name: str
    start: pd.Timestamp | None
    end: pd.Timestamp | None
    entry_safe: bool
    description: str


@dataclasses.dataclass(frozen=True)
class FeatureSpec:
    column: str
    family: str
    entry_safe: bool


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
    "matched_orderbook_file",
    "has_orderbook_data",
)

SEGMENT_FEATURE_SUFFIXES = (
    "release_score",
    "pressure_score",
    "burst_release_score",
    "mid_velocity_ratio",
    "mid_velocity_ticks_per_second",
    "mid_move_ticks",
    "monotonic_efficiency",
    "aligned_burst_5s_ratio",
    "aligned_burst_1s_ratio",
    "aligned_run_volume_ratio",
    "counter_suppression_score",
    "aligned_depth_imbalance_3_mean",
    "aligned_depth_imbalance_3_delta",
    "aligned_micro_skew_ticks_end",
)


def parse_ts(value: Any) -> pd.Timestamp | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return None
    ts = pd.Timestamp(text)
    if ts.tzinfo is not None:
        return ts.tz_convert(ET_TZ).tz_localize(None)
    return ts


def safe_ratio(numerator: float, denominator: float, *, cap: float = 100.0) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator <= 0.0:
        return float("nan")
    return float(min(max(numerator / denominator, 0.0), cap))


def finite_or_zero(value: float) -> float:
    return float(value) if np.isfinite(value) else 0.0


def clean_input_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "has_orderbook_data" in frame.columns:
        frame["has_orderbook_data"] = frame["has_orderbook_data"].astype(str).str.lower().eq("true")
    else:
        frame["has_orderbook_data"] = False
    frame["r_multiple"] = pd.to_numeric(frame["r_multiple"], errors="coerce")
    return frame


def segment_slice(
    frame: pd.DataFrame,
    *,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    file_start: pd.Timestamp | None,
    file_end: pd.Timestamp | None,
) -> tuple[pd.DataFrame, float, bool]:
    if start is None or end is None or end <= start:
        return frame.iloc[0:0], 0.0, False

    desired_seconds = max((end - start).total_seconds(), 1.0)
    clipped_start = max(start, file_start) if file_start is not None else start
    clipped_end = min(end, file_end) if file_end is not None else end
    if clipped_end <= clipped_start:
        return frame.iloc[0:0], 0.0, False

    covered_seconds = max((clipped_end - clipped_start).total_seconds(), 0.0)
    coverage = float(min(covered_seconds / desired_seconds, 1.0))
    subset = frame[(frame["event_time"] >= clipped_start) & (frame["event_time"] < clipped_end)]
    return subset, coverage, coverage >= 0.8


def mid_values(frame: pd.DataFrame) -> np.ndarray:
    return impulse.valid_mid(frame)


def trade_stats(frame: pd.DataFrame, *, direction: int) -> dict[str, float | int]:
    if frame.empty:
        return {
            "trade_events": 0,
            "total_aggressor_volume": 0.0,
            "aligned_aggressor_volume": 0.0,
            "counter_aggressor_volume": 0.0,
            "aligned_signed_aggressor_volume": 0.0,
            "aligned_run_max_events": 0,
            "aligned_run_max_volume": 0.0,
            "counter_run_max_events": 0,
            "counter_run_max_volume": 0.0,
            "aligned_burst_1s_max": 0.0,
            "aligned_burst_5s_max": 0.0,
        }

    trades = frame[frame["action_str"] == "T"]
    if trades.empty:
        return {
            "trade_events": 0,
            "total_aggressor_volume": 0.0,
            "aligned_aggressor_volume": 0.0,
            "counter_aggressor_volume": 0.0,
            "aligned_signed_aggressor_volume": 0.0,
            "aligned_run_max_events": 0,
            "aligned_run_max_volume": 0.0,
            "counter_run_max_events": 0,
            "counter_run_max_volume": 0.0,
            "aligned_burst_1s_max": 0.0,
            "aligned_burst_5s_max": 0.0,
        }

    size = trades["size"].to_numpy(dtype=np.float64, copy=False)
    side = trades["side_str"].to_numpy()
    side_sign = np.where(side == "B", 1, np.where(side == "A", -1, 0))
    aligned_sign = direction * side_sign
    aligned_mask = aligned_sign > 0
    counter_mask = aligned_sign < 0
    aligned_volume = float(size[aligned_mask].sum())
    counter_volume = float(size[counter_mask].sum())

    aligned_run_events = 0
    aligned_run_volume = 0.0
    counter_run_events = 0
    counter_run_volume = 0.0
    current_sign = 0
    current_events = 0
    current_volume = 0.0

    for sign, trade_size in zip(aligned_sign, size, strict=False):
        sign = int(np.sign(sign))
        if sign == 0:
            continue
        if sign != current_sign:
            if current_sign > 0:
                aligned_run_events = max(aligned_run_events, current_events)
                aligned_run_volume = max(aligned_run_volume, current_volume)
            elif current_sign < 0:
                counter_run_events = max(counter_run_events, current_events)
                counter_run_volume = max(counter_run_volume, current_volume)
            current_sign = sign
            current_events = 1
            current_volume = float(trade_size)
        else:
            current_events += 1
            current_volume += float(trade_size)

    if current_sign > 0:
        aligned_run_events = max(aligned_run_events, current_events)
        aligned_run_volume = max(aligned_run_volume, current_volume)
    elif current_sign < 0:
        counter_run_events = max(counter_run_events, current_events)
        counter_run_volume = max(counter_run_volume, current_volume)

    event_time = pd.to_datetime(trades["event_time"])
    aligned_size = pd.Series(np.where(aligned_mask, size, 0.0), index=event_time)
    if aligned_size.empty:
        burst_1s = 0.0
        burst_5s = 0.0
    else:
        by_second = aligned_size.groupby(aligned_size.index.floor("s")).sum()
        burst_1s = float(by_second.max()) if not by_second.empty else 0.0
        full_index = pd.date_range(by_second.index.min(), by_second.index.max(), freq="s")
        by_second = by_second.reindex(full_index, fill_value=0.0)
        burst_5s = float(by_second.rolling(5, min_periods=1).sum().max()) if not by_second.empty else 0.0

    return {
        "trade_events": int(len(trades)),
        "total_aggressor_volume": aligned_volume + counter_volume,
        "aligned_aggressor_volume": aligned_volume,
        "counter_aggressor_volume": counter_volume,
        "aligned_signed_aggressor_volume": aligned_volume - counter_volume,
        "aligned_run_max_events": int(aligned_run_events),
        "aligned_run_max_volume": float(aligned_run_volume),
        "counter_run_max_events": int(counter_run_events),
        "counter_run_max_volume": float(counter_run_volume),
        "aligned_burst_1s_max": burst_1s,
        "aligned_burst_5s_max": burst_5s,
    }


def score_segment(
    event: pd.DataFrame,
    baseline: pd.DataFrame,
    *,
    direction: int,
    duration_seconds: float,
    baseline_seconds: float,
) -> dict[str, float | int]:
    event_trades = trade_stats(event, direction=direction)
    baseline_trades = trade_stats(baseline, direction=direction)

    event_mid = mid_values(event)
    baseline_mid = mid_values(baseline)
    if len(event_mid) >= 2:
        mid_move_ticks = float(direction * ((event_mid[-1] - event_mid[0]) / TICK_SIZE))
        mid_path_ticks = float(np.nansum(np.abs(np.diff(event_mid))) / TICK_SIZE)
        mid_range_ticks = float((np.nanmax(event_mid) - np.nanmin(event_mid)) / TICK_SIZE)
    else:
        mid_move_ticks = float("nan")
        mid_path_ticks = float("nan")
        mid_range_ticks = float("nan")

    if len(baseline_mid) >= 2:
        baseline_mid_path_ticks = float(np.nansum(np.abs(np.diff(baseline_mid))) / TICK_SIZE)
        baseline_mid_net_ticks = float(abs((baseline_mid[-1] - baseline_mid[0]) / TICK_SIZE))
    else:
        baseline_mid_path_ticks = 0.0
        baseline_mid_net_ticks = 0.0

    duration_seconds = max(float(duration_seconds), 1.0)
    baseline_seconds = max(float(baseline_seconds), 1.0)
    total_volume = float(event_trades["total_aggressor_volume"])
    aligned_volume = float(event_trades["aligned_aggressor_volume"])
    counter_volume = float(event_trades["counter_aggressor_volume"])
    aligned_signed_volume = float(event_trades["aligned_signed_aggressor_volume"])
    baseline_total_volume = float(baseline_trades["total_aggressor_volume"])

    total_volume_rate = total_volume / duration_seconds
    aligned_volume_rate = aligned_volume / duration_seconds
    counter_volume_rate = counter_volume / duration_seconds
    baseline_total_volume_rate = baseline_total_volume / baseline_seconds
    baseline_path_velocity = baseline_mid_path_ticks / baseline_seconds
    baseline_net_velocity = baseline_mid_net_ticks / baseline_seconds

    mid_velocity = mid_move_ticks / duration_seconds if np.isfinite(mid_move_ticks) else float("nan")
    volume_rate_ratio = safe_ratio(total_volume_rate, baseline_total_volume_rate)
    aligned_rate_ratio = safe_ratio(aligned_volume_rate, baseline_total_volume_rate)
    counter_rate_ratio = safe_ratio(counter_volume_rate, baseline_total_volume_rate)
    mid_velocity_ratio = safe_ratio(max(finite_or_zero(mid_velocity), 0.0), baseline_path_velocity)
    mid_net_velocity_ratio = safe_ratio(max(finite_or_zero(mid_velocity), 0.0), baseline_net_velocity)
    aggression_imbalance = aligned_signed_volume / total_volume if total_volume > 0.0 else float("nan")
    counter_aggression_ratio = safe_ratio(counter_volume, aligned_volume, cap=100.0)
    counter_suppression_score = 1.0 / (1.0 + finite_or_zero(counter_aggression_ratio))
    monotonic_efficiency = safe_ratio(max(finite_or_zero(mid_move_ticks), 0.0), mid_path_ticks, cap=1.0)
    aligned_run_volume_ratio = safe_ratio(float(event_trades["aligned_run_max_volume"]), total_volume, cap=1.0)
    aligned_burst_1s_ratio = safe_ratio(float(event_trades["aligned_burst_1s_max"]), baseline_total_volume_rate)
    aligned_burst_5s_ratio = safe_ratio(float(event_trades["aligned_burst_5s_max"]), baseline_total_volume_rate * 5.0)

    depth_1 = impulse.aligned_depth_stats(event, direction=direction, levels=1)
    depth_3 = impulse.aligned_depth_stats(event, direction=direction, levels=3)
    depth_10 = impulse.aligned_depth_stats(event, direction=direction, levels=10)
    micro = impulse.aligned_microprice_stats(event, direction=direction)
    depth_boost = 1.0 + max(finite_or_zero(depth_3["aligned_depth_imbalance_3_mean"]), 0.0)
    flow_component = max(finite_or_zero(aggression_imbalance), 0.0)
    volume_component = math.sqrt(max(finite_or_zero(volume_rate_ratio), 0.0))
    price_component = max(finite_or_zero(mid_velocity_ratio), 0.0)
    aligned_rate_component = math.sqrt(max(finite_or_zero(aligned_rate_ratio), 0.0))
    burst_component = math.sqrt(max(finite_or_zero(aligned_burst_5s_ratio), 0.0))
    efficiency_boost = 1.0 + max(finite_or_zero(monotonic_efficiency), 0.0)

    release_score = flow_component * volume_component * price_component * depth_boost * efficiency_boost
    pressure_score = flow_component * volume_component * aligned_rate_component * depth_boost
    burst_release_score = flow_component * burst_component * price_component * depth_boost * efficiency_boost

    counter_imbalance = max(-finite_or_zero(aggression_imbalance), 0.0)
    counter_mid_move_ticks = max(-finite_or_zero(mid_move_ticks), 0.0)
    counter_mid_velocity = counter_mid_move_ticks / duration_seconds
    absorption_score = (
        counter_imbalance
        * math.sqrt(max(finite_or_zero(volume_rate_ratio), 0.0))
        * math.sqrt(max(finite_or_zero(counter_rate_ratio), 0.0))
        / (1.0 + max(counter_mid_velocity, 0.0))
    )

    out: dict[str, float | int] = {
        "event_rows": int(len(event)),
        "trade_events": int(event_trades["trade_events"]),
        "total_aggressor_volume": total_volume,
        "aligned_aggressor_volume": aligned_volume,
        "counter_aggressor_volume": counter_volume,
        "aligned_signed_aggressor_volume": aligned_signed_volume,
        "total_volume_rate": total_volume_rate,
        "aligned_volume_rate": aligned_volume_rate,
        "counter_volume_rate": counter_volume_rate,
        "volume_rate_ratio": volume_rate_ratio,
        "aligned_rate_ratio": aligned_rate_ratio,
        "counter_rate_ratio": counter_rate_ratio,
        "aggression_imbalance": aggression_imbalance,
        "counter_aggression_ratio": counter_aggression_ratio,
        "counter_suppression_score": counter_suppression_score,
        "mid_move_ticks": mid_move_ticks,
        "mid_path_ticks": mid_path_ticks,
        "mid_range_ticks": mid_range_ticks,
        "mid_velocity_ticks_per_second": mid_velocity,
        "mid_velocity_ratio": mid_velocity_ratio,
        "mid_net_velocity_ratio": mid_net_velocity_ratio,
        "monotonic_efficiency": monotonic_efficiency,
        "aligned_run_max_events": int(event_trades["aligned_run_max_events"]),
        "aligned_run_max_volume": float(event_trades["aligned_run_max_volume"]),
        "aligned_run_volume_ratio": aligned_run_volume_ratio,
        "aligned_burst_1s_max": float(event_trades["aligned_burst_1s_max"]),
        "aligned_burst_5s_max": float(event_trades["aligned_burst_5s_max"]),
        "aligned_burst_1s_ratio": aligned_burst_1s_ratio,
        "aligned_burst_5s_ratio": aligned_burst_5s_ratio,
        "release_score": release_score,
        "pressure_score": pressure_score,
        "burst_release_score": burst_release_score,
        "absorption_score": absorption_score,
    }
    out.update(depth_1)
    out.update(depth_3)
    out.update(depth_10)
    out.update(micro)
    return out


def nan_segment_stats() -> dict[str, float | int]:
    keys = (
        "event_rows",
        "trade_events",
        "total_aggressor_volume",
        "aligned_aggressor_volume",
        "counter_aggressor_volume",
        "aligned_signed_aggressor_volume",
        "total_volume_rate",
        "aligned_volume_rate",
        "counter_volume_rate",
        "volume_rate_ratio",
        "aligned_rate_ratio",
        "counter_rate_ratio",
        "aggression_imbalance",
        "counter_aggression_ratio",
        "counter_suppression_score",
        "mid_move_ticks",
        "mid_path_ticks",
        "mid_range_ticks",
        "mid_velocity_ticks_per_second",
        "mid_velocity_ratio",
        "mid_net_velocity_ratio",
        "monotonic_efficiency",
        "aligned_run_max_events",
        "aligned_run_max_volume",
        "aligned_run_volume_ratio",
        "aligned_burst_1s_max",
        "aligned_burst_5s_max",
        "aligned_burst_1s_ratio",
        "aligned_burst_5s_ratio",
        "release_score",
        "pressure_score",
        "burst_release_score",
        "absorption_score",
        "aligned_depth_imbalance_1_mean",
        "aligned_depth_imbalance_1_start",
        "aligned_depth_imbalance_1_end",
        "aligned_depth_imbalance_1_delta",
        "aligned_depth_imbalance_3_mean",
        "aligned_depth_imbalance_3_start",
        "aligned_depth_imbalance_3_end",
        "aligned_depth_imbalance_3_delta",
        "aligned_depth_imbalance_10_mean",
        "aligned_depth_imbalance_10_start",
        "aligned_depth_imbalance_10_end",
        "aligned_depth_imbalance_10_delta",
        "aligned_micro_skew_ticks_mean",
        "aligned_micro_skew_ticks_end",
    )
    return {key: float("nan") for key in keys}


def build_segments(row: pd.Series) -> list[SegmentDef]:
    signal_start = parse_ts(row.get("signal_start"))
    signal_end = parse_ts(row.get("signal_end"))
    fvg_time = parse_ts(row.get("lsi_fvg_time"))
    sweep_time = parse_ts(row.get("lsi_sweep_time"))
    cisd_time = parse_ts(row.get("lsi_cisd_time"))
    if signal_start is None or signal_end is None:
        return []

    first_5 = min(signal_start + pd.Timedelta(seconds=5), signal_end)
    first_10 = min(signal_start + pd.Timedelta(seconds=10), signal_end)
    last_10 = max(signal_end - pd.Timedelta(seconds=10), signal_start)
    return [
        SegmentDef("pre_confirm_30s", signal_start - pd.Timedelta(seconds=30), signal_start, True, "30s before signal close window"),
        SegmentDef("pre_confirm_10s", signal_start - pd.Timedelta(seconds=10), signal_start, True, "10s before signal close window"),
        SegmentDef("sweep_to_fvg", sweep_time, fvg_time, True, "sweep-to-FVG formation window when covered by sparse DBN"),
        SegmentDef("fvg_to_confirm", fvg_time, signal_start, True, "FVG-to-confirmation lead-in window when covered by sparse DBN"),
        SegmentDef("cisd_to_confirm", cisd_time, signal_start, True, "CISD-to-confirmation lead-in window when present"),
        SegmentDef("confirm_first_5s", signal_start, first_5, True, "first 5 seconds of confirmation bar"),
        SegmentDef("confirm_first_10s", signal_start, first_10, True, "first 10 seconds of confirmation bar"),
        SegmentDef("confirm_last_10s", last_10, signal_end, True, "last 10 seconds before signal close"),
        SegmentDef("confirm_full", signal_start, signal_end, True, "full confirmation bar"),
        SegmentDef("post_confirm_10s", signal_end, signal_end + pd.Timedelta(seconds=10), False, "10s post-entry follow-through diagnostic"),
        SegmentDef("post_confirm_30s", signal_end, signal_end + pd.Timedelta(seconds=30), False, "30s post-entry follow-through diagnostic"),
    ]


def base_lab_row(row: pd.Series, *, period: str) -> dict[str, Any]:
    out = {column: row.get(column) for column in BASE_COLUMNS if column in row.index}
    out["period"] = period
    return out


def score_trade_row(frame: pd.DataFrame, row: pd.Series, *, period: str, baseline_seconds: int) -> dict[str, Any]:
    out = base_lab_row(row, period=period)
    direction = int(row["direction"])
    signal_start = parse_ts(row.get("signal_start"))
    file_start = parse_ts(row.get("orderbook_file_start"))
    file_end = parse_ts(row.get("orderbook_file_end"))

    if not bool(row.get("has_orderbook_data")) or signal_start is None:
        out["feature_data_status"] = "missing_orderbook"
        return out

    baseline_start = signal_start - pd.Timedelta(seconds=baseline_seconds)
    baseline, baseline_coverage, baseline_ok = segment_slice(
        frame,
        start=baseline_start,
        end=signal_start,
        file_start=file_start,
        file_end=file_end,
    )
    baseline_duration = max(len(baseline), 1)
    if baseline_ok and baseline_start is not None:
        baseline_duration = max((min(signal_start, file_end or signal_start) - max(baseline_start, file_start or baseline_start)).total_seconds(), 1.0)

    out["baseline_coverage"] = baseline_coverage
    out["feature_data_status"] = "scored"
    segment_status: dict[str, str] = {}
    segment_entry_safe: dict[str, bool] = {}

    for segment in build_segments(row):
        event, coverage, ok = segment_slice(
            frame,
            start=segment.start,
            end=segment.end,
            file_start=file_start,
            file_end=file_end,
        )
        segment_status[segment.name] = "scored" if ok and baseline_ok else "insufficient_coverage"
        segment_entry_safe[segment.name] = segment.entry_safe
        prefix = f"{segment.name}_"
        out[f"{prefix}coverage"] = coverage
        out[f"{prefix}entry_safe"] = segment.entry_safe
        if ok and baseline_ok and segment.start is not None and segment.end is not None:
            duration = max((min(segment.end, file_end or segment.end) - max(segment.start, file_start or segment.start)).total_seconds(), 1.0)
            stats = score_segment(
                event,
                baseline,
                direction=direction,
                duration_seconds=duration,
                baseline_seconds=baseline_duration,
            )
        else:
            stats = nan_segment_stats()
        for key, value in stats.items():
            out[f"{prefix}{key}"] = value

    pre30 = out.get("pre_confirm_30s_absorption_score", float("nan"))
    pre10 = out.get("pre_confirm_10s_absorption_score", float("nan"))
    confirm_10 = out.get("confirm_first_10s_release_score", float("nan"))
    confirm_last = out.get("confirm_last_10s_release_score", float("nan"))
    confirm_full = out.get("confirm_full_release_score", float("nan"))
    post10 = out.get("post_confirm_10s_release_score", float("nan"))
    post30 = out.get("post_confirm_30s_release_score", float("nan"))
    out["absorption_release_confirm_first_10s_score"] = finite_or_zero(pre30) * finite_or_zero(confirm_10)
    out["absorption_release_confirm_last_10s_score"] = finite_or_zero(pre10) * finite_or_zero(confirm_last)
    out["absorption_release_confirm_full_score"] = max(finite_or_zero(pre30), finite_or_zero(pre10)) * finite_or_zero(confirm_full)
    out["absorption_release_post_confirm_10s_score"] = finite_or_zero(pre30) * finite_or_zero(post10)
    out["absorption_release_post_confirm_30s_score"] = finite_or_zero(pre30) * finite_or_zero(post30)
    out["segment_status_json"] = json.dumps(segment_status, sort_keys=True)
    out["segment_entry_safe_json"] = json.dumps(segment_entry_safe, sort_keys=True)
    return out


def score_period_features(
    source_csv: Path,
    *,
    period: str,
    baseline_seconds: int,
    max_files: int | None,
) -> pd.DataFrame:
    source = clean_input_frame(source_csv)
    rows: list[dict[str, Any]] = []
    scored = source[source["has_orderbook_data"] & source["matched_orderbook_file"].notna()].copy()
    missing = source[~(source["has_orderbook_data"] & source["matched_orderbook_file"].notna())].copy()
    for _, row in missing.iterrows():
        out = base_lab_row(row, period=period)
        out["feature_data_status"] = "missing_orderbook"
        rows.append(out)

    paths = list(scored["matched_orderbook_file"].dropna().unique())
    if max_files is not None:
        paths = paths[:max_files]
    path_allowlist = set(paths)
    skipped = scored[~scored["matched_orderbook_file"].isin(path_allowlist)]
    for _, row in skipped.iterrows():
        out = base_lab_row(row, period=period)
        out["feature_data_status"] = "skipped_by_max_files"
        rows.append(out)

    print(f"{period}: scoring {len(path_allowlist):,} DBN files for {len(scored[scored['matched_orderbook_file'].isin(path_allowlist)]):,} rows", flush=True)
    for idx, path_text in enumerate(paths, start=1):
        path = Path(path_text)
        group = scored[scored["matched_orderbook_file"] == path_text]
        t0 = time.time()
        frame = impulse.read_orderbook_frame(path)
        for _, trade_row in group.iterrows():
            rows.append(score_trade_row(frame, trade_row, period=period, baseline_seconds=baseline_seconds))
        print(
            f"  {period:<10} {idx:>3}/{len(paths):<3} {path.name:<62} "
            f"{len(frame):>8,} rows {len(group):>2} fills [{time.time() - t0:.1f}s]",
            flush=True,
        )

    return pd.DataFrame(rows).sort_values(["signal_start", "candidate"]).reset_index(drop=True)


def feature_specs(frame: pd.DataFrame) -> list[FeatureSpec]:
    specs: list[FeatureSpec] = []
    entry_safe_by_segment: dict[str, bool] = {
        "pre_confirm_30s": True,
        "pre_confirm_10s": True,
        "sweep_to_fvg": True,
        "fvg_to_confirm": True,
        "cisd_to_confirm": True,
        "confirm_first_5s": True,
        "confirm_first_10s": True,
        "confirm_last_10s": True,
        "confirm_full": True,
        "post_confirm_10s": False,
        "post_confirm_30s": False,
    }
    for segment, entry_safe in entry_safe_by_segment.items():
        for suffix in SEGMENT_FEATURE_SUFFIXES:
            column = f"{segment}_{suffix}"
            if column in frame.columns:
                specs.append(FeatureSpec(column=column, family=segment, entry_safe=entry_safe))

    combo_specs = {
        "absorption_release_confirm_first_10s_score": ("absorption_release", True),
        "absorption_release_confirm_last_10s_score": ("absorption_release", True),
        "absorption_release_confirm_full_score": ("absorption_release", True),
        "absorption_release_post_confirm_10s_score": ("post_entry_absorption_release", False),
        "absorption_release_post_confirm_30s_score": ("post_entry_absorption_release", False),
    }
    for column, (family, entry_safe) in combo_specs.items():
        if column in frame.columns:
            specs.append(FeatureSpec(column=column, family=family, entry_safe=entry_safe))
    return specs


def metrics_for(values: pd.Series | np.ndarray) -> dict[str, Any]:
    arr = pd.Series(values).dropna().to_numpy(dtype=float)
    return val.r_metrics(arr)


def threshold_grid(values: pd.Series, column: str) -> list[tuple[str, float, str]]:
    clean = values.replace([np.inf, -np.inf], np.nan).dropna()
    if clean.empty:
        return []
    return [
        (f"{column}_skip_bottom_20", float(clean.quantile(0.20)), "validation_quantile"),
        (f"{column}_skip_bottom_30", float(clean.quantile(0.30)), "validation_quantile"),
        (f"{column}_skip_bottom_40", float(clean.quantile(0.40)), "validation_quantile"),
        (f"{column}_top_50", float(clean.quantile(0.50)), "validation_quantile"),
        (f"{column}_top_40", float(clean.quantile(0.60)), "validation_quantile"),
        (f"{column}_top_30", float(clean.quantile(0.70)), "validation_quantile"),
        (f"{column}_top_20", float(clean.quantile(0.80)), "validation_quantile"),
    ]


def add_metric_prefix(row: dict[str, Any], prefix: str, values: pd.Series | np.ndarray) -> None:
    row.update({f"{prefix}_{key}": value for key, value in metrics_for(values).items()})


def weighted_returns(frame: pd.DataFrame, *, column: str, low: float, high: float) -> pd.Series:
    values = frame[column].replace([np.inf, -np.inf], np.nan)
    weights = pd.Series(np.nan, index=frame.index, dtype=float)
    weights[values < low] = 0.5
    weights[(values >= low) & (values < high)] = 1.0
    weights[values >= high] = 1.5
    return frame["r_multiple"] * weights


def evaluate_features(
    validation: pd.DataFrame,
    holdout: pd.DataFrame,
    specs: list[FeatureSpec],
    *,
    min_validation_trades: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    baselines: list[dict[str, Any]] = []
    for period, frame in (("validation", validation), ("holdout", holdout)):
        for candidate, group in frame.groupby("candidate"):
            scored = group[group["feature_data_status"].eq("scored")]
            row: dict[str, Any] = {
                "period": period,
                "candidate": candidate,
                "total_rows": int(len(group)),
                "scored_rows": int(len(scored)),
                "feature_coverage": float(len(scored) / len(group)) if len(group) else 0.0,
            }
            add_metric_prefix(row, "all", group["r_multiple"])
            add_metric_prefix(row, "scored", scored["r_multiple"])
            baselines.append(row)

    baseline_df = pd.DataFrame(baselines)
    rows: list[dict[str, Any]] = []
    candidates = sorted(set(validation["candidate"].dropna()) | set(holdout["candidate"].dropna()))
    for candidate in candidates:
        validation_candidate = validation[validation["candidate"] == candidate].copy()
        holdout_candidate = holdout[holdout["candidate"] == candidate].copy()
        validation_base = metrics_for(validation_candidate[validation_candidate["feature_data_status"].eq("scored")]["r_multiple"])
        holdout_base = metrics_for(holdout_candidate[holdout_candidate["feature_data_status"].eq("scored")]["r_multiple"])

        for spec in specs:
            if spec.column not in validation_candidate.columns or spec.column not in holdout_candidate.columns:
                continue
            validation_values = validation_candidate[spec.column].replace([np.inf, -np.inf], np.nan)
            holdout_values = holdout_candidate[spec.column].replace([np.inf, -np.inf], np.nan)
            for gate, threshold, threshold_source in threshold_grid(validation_values, spec.column):
                validation_gate = validation_candidate[validation_values >= threshold]
                if len(validation_gate) < min_validation_trades:
                    continue
                holdout_gate = holdout_candidate[holdout_values >= threshold]
                row = {
                    "candidate": candidate,
                    "feature": spec.column,
                    "feature_family": spec.family,
                    "entry_safe": spec.entry_safe,
                    "rule_type": "threshold",
                    "gate": gate,
                    "threshold": threshold,
                    "threshold_high": float("nan"),
                    "threshold_source": threshold_source,
                    "validation_feature_rows": int(validation_values.notna().sum()),
                    "holdout_feature_rows": int(holdout_values.notna().sum()),
                    "validation_trade_retention": float(len(validation_gate) / validation_values.notna().sum()) if validation_values.notna().sum() else 0.0,
                    "holdout_trade_retention": float(len(holdout_gate) / holdout_values.notna().sum()) if holdout_values.notna().sum() else 0.0,
                }
                add_metric_prefix(row, "validation", validation_gate["r_multiple"])
                add_metric_prefix(row, "holdout", holdout_gate["r_multiple"])
                row["validation_delta_avg_r"] = float(row["validation_avg_r"] - validation_base["avg_r"])
                row["validation_delta_calmar"] = float(row["validation_calmar"] - validation_base["calmar"])
                row["holdout_delta_avg_r"] = float(row["holdout_avg_r"] - holdout_base["avg_r"])
                row["holdout_delta_calmar"] = float(row["holdout_calmar"] - holdout_base["calmar"])
                rows.append(row)

            clean = validation_values.dropna()
            if len(clean) >= min_validation_trades:
                low = float(clean.quantile(0.33))
                high = float(clean.quantile(0.66))
                validation_weighted = weighted_returns(validation_candidate, column=spec.column, low=low, high=high)
                holdout_weighted = weighted_returns(holdout_candidate, column=spec.column, low=low, high=high)
                if int(validation_weighted.notna().sum()) >= min_validation_trades:
                    row = {
                        "candidate": candidate,
                        "feature": spec.column,
                        "feature_family": spec.family,
                        "entry_safe": spec.entry_safe,
                        "rule_type": "risk_tier_0p5_1_1p5",
                        "gate": f"{spec.column}_risk_tier_0p5_1_1p5",
                        "threshold": low,
                        "threshold_high": high,
                        "threshold_source": "validation_terciles",
                        "validation_feature_rows": int(validation_weighted.notna().sum()),
                        "holdout_feature_rows": int(holdout_weighted.notna().sum()),
                        "validation_trade_retention": 1.0,
                        "holdout_trade_retention": 1.0,
                    }
                    add_metric_prefix(row, "validation", validation_weighted)
                    add_metric_prefix(row, "holdout", holdout_weighted)
                    row["validation_delta_avg_r"] = float(row["validation_avg_r"] - validation_base["avg_r"])
                    row["validation_delta_calmar"] = float(row["validation_calmar"] - validation_base["calmar"])
                    row["holdout_delta_avg_r"] = float(row["holdout_avg_r"] - holdout_base["avg_r"])
                    row["holdout_delta_calmar"] = float(row["holdout_calmar"] - holdout_base["calmar"])
                    rows.append(row)

    gates = pd.DataFrame(rows)
    selected_rows: list[dict[str, Any]] = []
    if not gates.empty:
        for candidate, group in gates[gates["entry_safe"]].groupby("candidate"):
            ranked = group.sort_values(
                ["validation_calmar", "validation_profit_factor", "validation_total_r", "validation_trades"],
                ascending=[False, False, False, False],
            )
            selected_rows.append({**ranked.iloc[0].to_dict(), "selection_status": "selected_entry_safe_by_validation"})
    selected = pd.DataFrame(selected_rows)
    return gates, selected, baseline_df


def best_survivors(gates: pd.DataFrame, *, entry_safe: bool) -> pd.DataFrame:
    if gates.empty:
        return gates
    eligible = gates[
        (gates["entry_safe"].eq(entry_safe))
        & (gates["validation_delta_avg_r"] > 0)
        & (gates["holdout_delta_avg_r"] > 0)
        & (gates["holdout_trades"] >= 8)
    ].copy()
    if eligible.empty:
        return eligible
    return eligible.sort_values(
        ["holdout_delta_avg_r", "holdout_calmar", "validation_delta_avg_r", "holdout_total_r"],
        ascending=[False, False, False, False],
    ).head(12)


def risk_tier_survivors(gates: pd.DataFrame) -> pd.DataFrame:
    if gates.empty:
        return gates
    eligible = gates[
        (gates["entry_safe"].eq(True))
        & (gates["rule_type"].eq("risk_tier_0p5_1_1p5"))
        & (gates["validation_delta_avg_r"] > 0)
        & (gates["holdout_delta_avg_r"] > 0)
        & (gates["holdout_trades"] >= 20)
    ].copy()
    if eligible.empty:
        return eligible
    return eligible.sort_values(
        ["holdout_delta_avg_r", "holdout_calmar", "validation_delta_avg_r", "holdout_total_r"],
        ascending=[False, False, False, False],
    ).head(12)


def format_profit_factor(row: pd.Series, *, prefix: str) -> str:
    value = float(row.get(f"{prefix}_profit_factor", 0.0))
    avg_r = float(row.get(f"{prefix}_avg_r", 0.0))
    win_rate = float(row.get(f"{prefix}_win_rate", 0.0))
    if value == 0.0 and avg_r > 0.0 and win_rate >= 1.0:
        return "inf"
    return f"{value:.3f}"


def write_report(
    *,
    path: Path,
    gates: pd.DataFrame,
    selected: pd.DataFrame,
    baselines: pd.DataFrame,
    validation_csv: Path,
    holdout_csv: Path,
    output_dir: Path,
    min_validation_trades: int,
) -> None:
    validation_total = int(baselines[baselines["period"] == "validation"]["total_rows"].sum())
    validation_scored = int(baselines[baselines["period"] == "validation"]["scored_rows"].sum())
    holdout_total = int(baselines[baselines["period"] == "holdout"]["total_rows"].sum())
    holdout_scored = int(baselines[baselines["period"] == "holdout"]["scored_rows"].sum())
    entry_survivors = best_survivors(gates, entry_safe=True)
    post_survivors = best_survivors(gates, entry_safe=False)
    risk_survivors = risk_tier_survivors(gates)

    lines = [
        "# NQ NY LSI Order-Book Feature Lab",
        "",
        "- Objective: retest the discretionary momentum idea with smaller order-book windows instead of one blunt confirmation-bar aggregate.",
        "- Data source: existing DataBento MBP-10 DBN files only; this run does not refetch data.",
        f"- Validation CSV: `{validation_csv}`.",
        f"- Holdout CSV: `{holdout_csv}`.",
        f"- Output directory: `{output_dir}`.",
        f"- Minimum validation trades per tested rule: `{min_validation_trades}`.",
        f"- Validation feature coverage: `{validation_scored}/{validation_total}` rows.",
        f"- Holdout feature coverage: `{holdout_scored}/{holdout_total}` rows.",
        "- Entry-safe features end no later than the signal/confirmation close. Post-confirm features are diagnostics only.",
        "",
        "## Validation-Selected Entry-Safe Rules",
        "",
        "| Candidate | Rule | Feature | Val Trades | Val Avg R | Val R | Holdout Trades | Holdout Avg R | Holdout R | Holdout Delta Avg R |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    if selected.empty:
        lines.append("| n/a | n/a | n/a | 0 | 0.000 | 0.00 | 0 | 0.000 | 0.00 | 0.000 |")
    else:
        for _, row in selected.sort_values("candidate").iterrows():
            lines.append(
                f"| `{row['candidate']}` | `{row['rule_type']}` | `{row['feature']}` | "
                f"{int(row['validation_trades'])} | {float(row['validation_avg_r']):.3f} | "
                f"{float(row['validation_total_r']):.2f} | {int(row['holdout_trades'])} | "
                f"{float(row['holdout_avg_r']):.3f} | {float(row['holdout_total_r']):.2f} | "
                f"{float(row['holdout_delta_avg_r']):.3f} |"
            )

    lines.extend(
        [
            "",
            "## Entry-Safe Holdout Survivors",
            "",
            "These rows are diagnostic because they are sorted after seeing holdout, but they tell us which feature families deserve the next frozen test.",
            "",
            "| Candidate | Rule | Feature | Val Avg R | Holdout Trades | Holdout Avg R | Holdout Delta Avg R | Holdout PF |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if entry_survivors.empty:
        lines.append("| n/a | n/a | n/a | 0.000 | 0 | 0.000 | 0.000 | 0.000 |")
    else:
        for _, row in entry_survivors.iterrows():
            lines.append(
                f"| `{row['candidate']}` | `{row['rule_type']}` | `{row['feature']}` | "
                f"{float(row['validation_avg_r']):.3f} | {int(row['holdout_trades'])} | "
                f"{float(row['holdout_avg_r']):.3f} | {float(row['holdout_delta_avg_r']):.3f} | "
                f"{format_profit_factor(row, prefix='holdout')} |"
            )

    lines.extend(
        [
            "",
            "## Entry-Safe Risk-Tier Survivors",
            "",
            "These apply 0.5x / 1.0x / 1.5x risk by validation terciles, so they keep trade count instead of hard-filtering entries.",
            "",
            "| Candidate | Feature | Val Avg R | Holdout Trades | Holdout Avg R | Holdout Delta Avg R | Holdout R |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if risk_survivors.empty:
        lines.append("| n/a | n/a | 0.000 | 0 | 0.000 | 0.000 | 0.00 |")
    else:
        for _, row in risk_survivors.iterrows():
            lines.append(
                f"| `{row['candidate']}` | `{row['feature']}` | "
                f"{float(row['validation_avg_r']):.3f} | {int(row['holdout_trades'])} | "
                f"{float(row['holdout_avg_r']):.3f} | {float(row['holdout_delta_avg_r']):.3f} | "
                f"{float(row['holdout_total_r']):.2f} |"
            )

    lines.extend(
        [
            "",
            "## Post-Confirm Diagnostics",
            "",
            "These are not entry filters. They are included to check whether later follow-through matches the manual read of a strong reversal.",
            "",
            "| Candidate | Rule | Feature | Val Avg R | Holdout Trades | Holdout Avg R | Holdout Delta Avg R |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    if post_survivors.empty:
        lines.append("| n/a | n/a | n/a | 0.000 | 0 | 0.000 | 0.000 |")
    else:
        for _, row in post_survivors.iterrows():
            lines.append(
                f"| `{row['candidate']}` | `{row['rule_type']}` | `{row['feature']}` | "
                f"{float(row['validation_avg_r']):.3f} | {int(row['holdout_trades'])} | "
                f"{float(row['holdout_avg_r']):.3f} | {float(row['holdout_delta_avg_r']):.3f} |"
            )

    lines.extend(
        [
            "",
            "## Baselines",
            "",
            "| Period | Candidate | Rows | Scored | Coverage | Scored PF | Scored Avg R | Scored R |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in baselines.sort_values(["period", "candidate"]).iterrows():
        lines.append(
            f"| {row['period']} | `{row['candidate']}` | {int(row['total_rows'])} | "
            f"{int(row['scored_rows'])} | {float(row['feature_coverage']):.1%} | "
            f"{float(row['scored_profit_factor']):.3f} | {float(row['scored_avg_r']):.3f} | "
            f"{float(row['scored_total_r']):.2f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- Treat the validation-selected table as the honest replay read.",
            "- Treat the holdout-survivor table as feature-family discovery only; it should seed a smaller frozen follow-up, not a production rule.",
            "- Post-confirm rows can validate the discretionary intuition, but they are not causal entry gates unless converted into a later add/hold/scale rule.",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-csv", type=Path, default=DEFAULT_VALIDATION_CSV)
    parser.add_argument("--holdout-csv", type=Path, default=DEFAULT_HOLDOUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--baseline-seconds", type=int, default=120)
    parser.add_argument("--min-validation-trades", type=int, default=20)
    parser.add_argument("--max-files", type=int, default=None, help="Debug limit per period.")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI order-book feature lab", flush=True)
    validation = score_period_features(
        args.validation_csv,
        period="validation",
        baseline_seconds=args.baseline_seconds,
        max_files=args.max_files,
    )
    holdout = score_period_features(
        args.holdout_csv,
        period="holdout",
        baseline_seconds=args.baseline_seconds,
        max_files=args.max_files,
    )

    validation_path = args.output_dir / "validation_feature_lab.csv"
    holdout_path = args.output_dir / "holdout_feature_lab.csv"
    validation.to_csv(validation_path, index=False)
    holdout.to_csv(holdout_path, index=False)

    specs = feature_specs(pd.concat([validation.head(1), holdout.head(1)], ignore_index=True))
    gates, selected, baselines = evaluate_features(
        validation,
        holdout,
        specs,
        min_validation_trades=args.min_validation_trades,
    )
    gates_path = args.output_dir / "feature_gate_replay.csv"
    selected_path = args.output_dir / "selected_entry_safe_replay.csv"
    baselines_path = args.output_dir / "baseline_coverage.csv"
    gates.to_csv(gates_path, index=False)
    selected.to_csv(selected_path, index=False)
    baselines.to_csv(baselines_path, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "validation_csv": str(args.validation_csv),
        "holdout_csv": str(args.holdout_csv),
        "baseline_seconds": args.baseline_seconds,
        "min_validation_trades": args.min_validation_trades,
        "feature_specs": len(specs),
        "validation_rows": int(len(validation)),
        "validation_scored_rows": int(validation["feature_data_status"].eq("scored").sum()),
        "holdout_rows": int(len(holdout)),
        "holdout_scored_rows": int(holdout["feature_data_status"].eq("scored").sum()),
        "outputs": {
            "validation_feature_lab": str(validation_path),
            "holdout_feature_lab": str(holdout_path),
            "feature_gate_replay": str(gates_path),
            "selected_entry_safe_replay": str(selected_path),
            "baseline_coverage": str(baselines_path),
            "report": str(args.report_path),
        },
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    write_report(
        path=args.report_path,
        gates=gates,
        selected=selected,
        baselines=baselines,
        validation_csv=args.validation_csv,
        holdout_csv=args.holdout_csv,
        output_dir=args.output_dir,
        min_validation_trades=args.min_validation_trades,
    )
    print(f"Wrote {validation_path}", flush=True)
    print(f"Wrote {holdout_path}", flush=True)
    print(f"Wrote {gates_path}", flush=True)
    print(f"Wrote {selected_path}", flush=True)
    print(f"Wrote {baselines_path}", flush=True)
    print(f"Wrote {args.report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
