#!/usr/bin/env python3
"""Score NQ NY LSI candidates with DataBento MBP-10 order-book impulse.

This is the first true order-book pass for the discretionary "momentum"
concept: aggressive one-way trade flow, quick aligned price displacement, and
book imbalance around the LSI confirmation bar.

The downloaded MBP-10 windows are sparse and centered on known candidate
trades, so gates produced by this script are diagnostic only unless the same
feature is later frozen on a pre-holdout period and re-tested out of sample.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import databento as db
import numpy as np
import pandas as pd

import run_nq_ny_lsi_cisd_candidate_validation as val
import run_nq_ny_lsi_orderflow_impulse_proxy as proxy
from orb_backtest.engine.simulator import EXIT_NO_FILL


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_ny_lsi_orderbook_impulse_20260513"
OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_ORDERBOOK_IMPULSE_20260513.md"
DEFAULT_ORDERBOOK_DIR = ROOT / "data" / "raw" / "orderbook" / "NQ" / "mbp-10"
ET_TZ = "America/New_York"
TICK_SIZE = 0.25

SCORE_COLUMNS = (
    "impulse_score",
    "pressure_score",
    "price_impulse_score",
    "aggression_imbalance",
    "aligned_aggression_rate_ratio",
    "mid_velocity_ratio",
    "aligned_depth_imbalance_3_mean",
)


@dataclasses.dataclass(frozen=True)
class OrderbookFile:
    path: Path
    start: pd.Timestamp
    end: pd.Timestamp
    bytes: int
    chunk: int | None = None


@dataclasses.dataclass(frozen=True)
class TradeWindow:
    trade_uid: str
    candidate: str
    label: str
    timeframe: str
    date: str
    direction: int
    confirmation: str
    r_multiple: float
    signal_start: pd.Timestamp
    signal_end: pd.Timestamp
    fill_time: str
    lsi_sweep_time: str
    lsi_fvg_time: str
    lsi_cisd_time: str
    entry_price: float
    risk_points: float


def parse_utc_to_et_naive(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.tz_convert(ET_TZ).tz_localize(None)


def parse_naive_ts(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    return pd.Timestamp(value).tz_localize(None)


def safe_ratio(numerator: float, denominator: float, *, cap: float = 50.0) -> float:
    if not np.isfinite(numerator) or not np.isfinite(denominator) or denominator <= 0.0:
        return float("nan")
    return float(min(max(numerator / denominator, 0.0), cap))


def finite_or_zero(value: float) -> float:
    return float(value) if np.isfinite(value) else 0.0


def read_manifest(orderbook_dir: Path, *, min_bytes: int = 1024) -> list[OrderbookFile]:
    manifest_path = orderbook_dir / "manifest.jsonl"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing DataBento manifest: {manifest_path}")

    by_path: dict[Path, OrderbookFile] = {}
    with manifest_path.open() as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("status") != "downloaded":
                continue
            path = Path(row.get("output_path", ""))
            if not path.exists() or "limit1000" in path.name:
                continue
            size = int(path.stat().st_size)
            if size < min_bytes:
                continue
            by_path[path] = OrderbookFile(
                path=path,
                start=parse_utc_to_et_naive(row["start"]),
                end=parse_utc_to_et_naive(row["end"]),
                bytes=size,
                chunk=row.get("chunk"),
            )
    return sorted(by_path.values(), key=lambda item: (item.start, item.end, item.path.name))


def build_trade_windows(*, start: str, end: str | None) -> list[TradeWindow]:
    data = proxy.load_signal_data()
    candidates = proxy.build_candidate_runs()
    rows: list[TradeWindow] = []

    print("Rebuilding LSI candidate fills", flush=True)
    for candidate in candidates:
        trades = proxy.run_candidate(candidate, data)
        df = data[candidate.timeframe]
        delta = proxy.timeframe_delta(candidate.timeframe)
        for trade in trades:
            if trade.exit_type == EXIT_NO_FILL or trade.signal_bar < 0 or trade.signal_bar >= len(df):
                continue
            if trade.date < start or (end is not None and trade.date >= end):
                continue
            signal_start = pd.Timestamp(df.index[trade.signal_bar]).tz_localize(None)
            signal_end = signal_start + delta
            uid = "|".join(
                [
                    candidate.key,
                    trade.date,
                    signal_start.isoformat(),
                    str(int(trade.direction)),
                    f"{float(trade.entry_price):.2f}",
                    str(trade.exit_type),
                ]
            )
            rows.append(
                TradeWindow(
                    trade_uid=uid,
                    candidate=candidate.key,
                    label=candidate.label,
                    timeframe=candidate.timeframe,
                    date=trade.date,
                    direction=int(trade.direction),
                    confirmation=str(trade.lsi_confirmation_type),
                    r_multiple=float(trade.r_multiple),
                    signal_start=signal_start,
                    signal_end=signal_end,
                    fill_time=str(trade.fill_time),
                    lsi_sweep_time=str(trade.lsi_sweep_time),
                    lsi_fvg_time=str(trade.lsi_fvg_time),
                    lsi_cisd_time=str(trade.lsi_cisd_time),
                    entry_price=float(trade.entry_price),
                    risk_points=float(trade.risk_points),
                )
            )
    rows.sort(key=lambda item: (item.signal_start, item.candidate, item.trade_uid))
    return rows


def match_trades_to_files(
    trades: list[TradeWindow],
    files: list[OrderbookFile],
) -> tuple[dict[Path, list[TradeWindow]], list[TradeWindow]]:
    assignments: dict[Path, list[TradeWindow]] = defaultdict(list)
    missing: list[TradeWindow] = []
    for trade in trades:
        matches = [
            item
            for item in files
            if item.start <= trade.signal_start and item.end >= trade.signal_end
        ]
        if not matches:
            missing.append(trade)
            continue
        best = min(matches, key=lambda item: (item.end - item.start, item.bytes))
        assignments[best.path].append(trade)
    return assignments, missing


def read_orderbook_frame(path: Path) -> pd.DataFrame:
    store = db.DBNStore.from_file(path)
    obj = store.to_df()
    if hasattr(obj, "__next__"):
        pieces = list(obj)
        frame = pd.concat(pieces, axis=0) if pieces else pd.DataFrame()
    else:
        frame = obj
    if frame.empty:
        return frame

    event_time = (
        pd.to_datetime(frame["ts_event"], utc=True)
        .dt.tz_convert(ET_TZ)
        .dt.tz_localize(None)
    )
    frame = frame.copy()
    frame["event_time"] = event_time.to_numpy()
    frame["action_str"] = frame["action"].astype(str)
    frame["side_str"] = frame["side"].astype(str)
    return frame.sort_values("event_time", kind="mergesort")


def valid_mid(frame: pd.DataFrame) -> np.ndarray:
    if frame.empty:
        return np.array([], dtype=np.float64)
    bid = frame["bid_px_00"].to_numpy(dtype=np.float64, copy=False)
    ask = frame["ask_px_00"].to_numpy(dtype=np.float64, copy=False)
    valid = np.isfinite(bid) & np.isfinite(ask) & (bid > 0.0) & (ask > 0.0) & (ask >= bid)
    return ((bid[valid] + ask[valid]) / 2.0).astype(np.float64, copy=False)


def trade_aggression(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {
            "trade_events": 0,
            "buy_aggressor_volume": 0.0,
            "sell_aggressor_volume": 0.0,
            "total_aggressor_volume": 0.0,
            "signed_aggressor_volume": 0.0,
        }
    trades = frame[frame["action_str"] == "T"]
    if trades.empty:
        return {
            "trade_events": 0,
            "buy_aggressor_volume": 0.0,
            "sell_aggressor_volume": 0.0,
            "total_aggressor_volume": 0.0,
            "signed_aggressor_volume": 0.0,
        }
    size = trades["size"].to_numpy(dtype=np.float64, copy=False)
    side = trades["side_str"].to_numpy()
    buy = float(size[side == "B"].sum())
    sell = float(size[side == "A"].sum())
    return {
        "trade_events": int(len(trades)),
        "buy_aggressor_volume": buy,
        "sell_aggressor_volume": sell,
        "total_aggressor_volume": buy + sell,
        "signed_aggressor_volume": buy - sell,
    }


def aligned_depth_stats(frame: pd.DataFrame, *, direction: int, levels: int) -> dict[str, float]:
    prefix = f"aligned_depth_imbalance_{levels}"
    if frame.empty:
        return {
            f"{prefix}_mean": float("nan"),
            f"{prefix}_start": float("nan"),
            f"{prefix}_end": float("nan"),
            f"{prefix}_delta": float("nan"),
        }
    bid_cols = [f"bid_sz_{idx:02d}" for idx in range(levels) if f"bid_sz_{idx:02d}" in frame.columns]
    ask_cols = [f"ask_sz_{idx:02d}" for idx in range(levels) if f"ask_sz_{idx:02d}" in frame.columns]
    if not bid_cols or not ask_cols:
        return {
            f"{prefix}_mean": float("nan"),
            f"{prefix}_start": float("nan"),
            f"{prefix}_end": float("nan"),
            f"{prefix}_delta": float("nan"),
        }

    bid = frame[bid_cols].to_numpy(dtype=np.float64, copy=False).sum(axis=1)
    ask = frame[ask_cols].to_numpy(dtype=np.float64, copy=False).sum(axis=1)
    denom = bid + ask
    valid = np.isfinite(denom) & (denom > 0.0)
    if not bool(valid.any()):
        return {
            f"{prefix}_mean": float("nan"),
            f"{prefix}_start": float("nan"),
            f"{prefix}_end": float("nan"),
            f"{prefix}_delta": float("nan"),
        }
    imbalance = direction * ((bid[valid] - ask[valid]) / denom[valid])
    return {
        f"{prefix}_mean": float(np.nanmean(imbalance)),
        f"{prefix}_start": float(imbalance[0]),
        f"{prefix}_end": float(imbalance[-1]),
        f"{prefix}_delta": float(imbalance[-1] - imbalance[0]),
    }


def aligned_microprice_stats(frame: pd.DataFrame, *, direction: int) -> dict[str, float]:
    if frame.empty:
        return {
            "aligned_micro_skew_ticks_mean": float("nan"),
            "aligned_micro_skew_ticks_end": float("nan"),
        }
    bid = frame["bid_px_00"].to_numpy(dtype=np.float64, copy=False)
    ask = frame["ask_px_00"].to_numpy(dtype=np.float64, copy=False)
    bid_sz = frame["bid_sz_00"].to_numpy(dtype=np.float64, copy=False)
    ask_sz = frame["ask_sz_00"].to_numpy(dtype=np.float64, copy=False)
    denom = bid_sz + ask_sz
    valid = (
        np.isfinite(bid)
        & np.isfinite(ask)
        & np.isfinite(denom)
        & (bid > 0.0)
        & (ask > 0.0)
        & (ask >= bid)
        & (denom > 0.0)
    )
    if not bool(valid.any()):
        return {
            "aligned_micro_skew_ticks_mean": float("nan"),
            "aligned_micro_skew_ticks_end": float("nan"),
        }
    mid = (bid[valid] + ask[valid]) / 2.0
    micro = (bid[valid] * ask_sz[valid] + ask[valid] * bid_sz[valid]) / denom[valid]
    skew = direction * ((micro - mid) / TICK_SIZE)
    return {
        "aligned_micro_skew_ticks_mean": float(np.nanmean(skew)),
        "aligned_micro_skew_ticks_end": float(skew[-1]),
    }


def base_trade_row(trade: TradeWindow) -> dict[str, Any]:
    return {
        "trade_uid": trade.trade_uid,
        "candidate": trade.candidate,
        "label": trade.label,
        "timeframe": trade.timeframe,
        "date": trade.date,
        "direction": trade.direction,
        "confirmation": trade.confirmation,
        "r_multiple": trade.r_multiple,
        "signal_start": trade.signal_start.isoformat(),
        "signal_end": trade.signal_end.isoformat(),
        "fill_time": trade.fill_time,
        "lsi_sweep_time": trade.lsi_sweep_time,
        "lsi_fvg_time": trade.lsi_fvg_time,
        "lsi_cisd_time": trade.lsi_cisd_time,
        "entry_price": trade.entry_price,
        "risk_points": trade.risk_points,
    }


def missing_trade_row(trade: TradeWindow) -> dict[str, Any]:
    row = base_trade_row(trade)
    row.update(
        {
            "matched_orderbook_file": "",
            "has_orderbook_data": False,
            "event_rows": 0,
            "event_trade_events": 0,
            "baseline_rows": 0,
            "impulse_score": float("nan"),
            "pressure_score": float("nan"),
            "price_impulse_score": float("nan"),
        }
    )
    return row


def score_trade(
    frame: pd.DataFrame,
    trade: TradeWindow,
    *,
    orderbook_file: OrderbookFile,
    baseline_seconds: int,
) -> dict[str, Any]:
    event_start = trade.signal_start
    event_end = trade.signal_end
    baseline_start = max(orderbook_file.start, event_start - pd.Timedelta(seconds=baseline_seconds))
    event_duration = max((event_end - event_start).total_seconds(), 1.0)
    baseline_duration = max((event_start - baseline_start).total_seconds(), 1.0)

    event = frame[(frame["event_time"] >= event_start) & (frame["event_time"] < event_end)]
    baseline = frame[(frame["event_time"] >= baseline_start) & (frame["event_time"] < event_start)]
    event_mid = valid_mid(event)
    baseline_mid = valid_mid(baseline)
    event_aggr = trade_aggression(event)
    baseline_aggr = trade_aggression(baseline)

    event_total_volume = float(event_aggr["total_aggressor_volume"])
    event_signed_volume = float(event_aggr["signed_aggressor_volume"])
    baseline_total_volume = float(baseline_aggr["total_aggressor_volume"])
    baseline_signed_volume = float(baseline_aggr["signed_aggressor_volume"])
    aligned_signed_volume = trade.direction * event_signed_volume
    aligned_baseline_signed_volume = trade.direction * baseline_signed_volume

    if len(event_mid) >= 2:
        mid_move_ticks = float(trade.direction * ((event_mid[-1] - event_mid[0]) / TICK_SIZE))
        mid_path_ticks = float(np.nansum(np.abs(np.diff(event_mid))) / TICK_SIZE)
        mid_range_ticks = float((np.nanmax(event_mid) - np.nanmin(event_mid)) / TICK_SIZE)
    else:
        mid_move_ticks = float("nan")
        mid_path_ticks = float("nan")
        mid_range_ticks = float("nan")

    if len(baseline_mid) >= 2:
        baseline_mid_net_ticks = float(abs((baseline_mid[-1] - baseline_mid[0]) / TICK_SIZE))
        baseline_mid_path_ticks = float(np.nansum(np.abs(np.diff(baseline_mid))) / TICK_SIZE)
    else:
        baseline_mid_net_ticks = 0.0
        baseline_mid_path_ticks = 0.0

    event_volume_rate = event_total_volume / event_duration
    baseline_volume_rate = baseline_total_volume / baseline_duration
    aligned_aggression_rate = aligned_signed_volume / event_duration
    baseline_abs_signed_rate = abs(aligned_baseline_signed_volume) / baseline_duration
    baseline_path_velocity = baseline_mid_path_ticks / baseline_duration
    baseline_net_velocity = baseline_mid_net_ticks / baseline_duration
    mid_velocity = mid_move_ticks / event_duration if np.isfinite(mid_move_ticks) else float("nan")

    volume_rate_ratio = safe_ratio(event_volume_rate, baseline_volume_rate)
    aligned_aggression_rate_ratio = safe_ratio(max(aligned_aggression_rate, 0.0), baseline_volume_rate)
    abs_signed_rate_ratio = safe_ratio(abs(aligned_aggression_rate), baseline_abs_signed_rate)
    mid_velocity_ratio = safe_ratio(max(mid_velocity, 0.0), baseline_path_velocity)
    mid_net_velocity_ratio = safe_ratio(max(mid_velocity, 0.0), baseline_net_velocity)
    aggression_imbalance = (
        aligned_signed_volume / event_total_volume
        if event_total_volume > 0.0
        else float("nan")
    )

    depth_1 = aligned_depth_stats(event, direction=trade.direction, levels=1)
    depth_3 = aligned_depth_stats(event, direction=trade.direction, levels=3)
    depth_10 = aligned_depth_stats(event, direction=trade.direction, levels=10)
    micro = aligned_microprice_stats(event, direction=trade.direction)

    flow_component = max(finite_or_zero(aggression_imbalance), 0.0)
    volume_component = math.sqrt(max(finite_or_zero(volume_rate_ratio), 0.0))
    price_component = max(finite_or_zero(mid_velocity_ratio), 0.0)
    pressure_component = math.sqrt(max(finite_or_zero(aligned_aggression_rate_ratio), 0.0))
    depth_boost = 1.0 + max(finite_or_zero(depth_3["aligned_depth_imbalance_3_mean"]), 0.0)

    impulse_score = flow_component * volume_component * price_component * depth_boost
    pressure_score = flow_component * volume_component * pressure_component * depth_boost
    price_impulse_score = volume_component * price_component * depth_boost

    row = base_trade_row(trade)
    row.update(
        {
            "matched_orderbook_file": str(orderbook_file.path),
            "orderbook_file_start": orderbook_file.start.isoformat(),
            "orderbook_file_end": orderbook_file.end.isoformat(),
            "orderbook_file_bytes": orderbook_file.bytes,
            "has_orderbook_data": bool(len(event) > 0),
            "event_rows": int(len(event)),
            "event_trade_events": int(event_aggr["trade_events"]),
            "baseline_rows": int(len(baseline)),
            "baseline_trade_events": int(baseline_aggr["trade_events"]),
            "event_duration_seconds": event_duration,
            "baseline_duration_seconds": baseline_duration,
            "buy_aggressor_volume": float(event_aggr["buy_aggressor_volume"]),
            "sell_aggressor_volume": float(event_aggr["sell_aggressor_volume"]),
            "total_aggressor_volume": event_total_volume,
            "signed_aggressor_volume": event_signed_volume,
            "aligned_signed_aggressor_volume": aligned_signed_volume,
            "baseline_total_aggressor_volume": baseline_total_volume,
            "baseline_signed_aggressor_volume": baseline_signed_volume,
            "event_volume_rate": event_volume_rate,
            "baseline_volume_rate": baseline_volume_rate,
            "volume_rate_ratio": volume_rate_ratio,
            "aligned_aggression_rate": aligned_aggression_rate,
            "aligned_aggression_rate_ratio": aligned_aggression_rate_ratio,
            "abs_signed_rate_ratio": abs_signed_rate_ratio,
            "aggression_imbalance": aggression_imbalance,
            "mid_move_ticks": mid_move_ticks,
            "mid_path_ticks": mid_path_ticks,
            "mid_range_ticks": mid_range_ticks,
            "mid_velocity_ticks_per_second": mid_velocity,
            "baseline_mid_net_ticks": baseline_mid_net_ticks,
            "baseline_mid_path_ticks": baseline_mid_path_ticks,
            "baseline_mid_path_velocity_ticks_per_second": baseline_path_velocity,
            "baseline_mid_net_velocity_ticks_per_second": baseline_net_velocity,
            "mid_velocity_ratio": mid_velocity_ratio,
            "mid_net_velocity_ratio": mid_net_velocity_ratio,
            "impulse_score": impulse_score,
            "pressure_score": pressure_score,
            "price_impulse_score": price_impulse_score,
        }
    )
    row.update(depth_1)
    row.update(depth_3)
    row.update(depth_10)
    row.update(micro)
    return row


def metric_row(
    candidate: str,
    gate: str,
    subset: pd.DataFrame,
    *,
    score_column: str | None = None,
    threshold: float | None = None,
    threshold_source: str | None = None,
) -> dict[str, Any]:
    metrics = val.r_metrics(subset["r_multiple"].to_numpy(dtype=float) if not subset.empty else [])
    row: dict[str, Any] = {
        "candidate": candidate,
        "gate": gate,
        "score_column": score_column,
        "threshold": threshold,
        "threshold_source": threshold_source,
        "feature_coverage": float(subset["has_orderbook_data"].mean()) if not subset.empty else 0.0,
    }
    row.update(metrics)
    if score_column and score_column in subset.columns and not subset.empty:
        values = subset[score_column].replace([np.inf, -np.inf], np.nan).dropna()
        row[f"{score_column}_median"] = float(values.median()) if not values.empty else float("nan")
        row[f"{score_column}_mean"] = float(values.mean()) if not values.empty else float("nan")
    row["cisd_trades"] = int((subset["confirmation"] == "cisd").sum()) if not subset.empty else 0
    row["inversion_trades"] = int((subset["confirmation"] == "inversion").sum()) if not subset.empty else 0
    row["long_trades"] = int((subset["direction"] == 1).sum()) if not subset.empty else 0
    row["short_trades"] = int((subset["direction"] == -1).sum()) if not subset.empty else 0
    return row


def build_gate_summary(trade_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate, group in trade_df.groupby("candidate"):
        group = group.sort_values("signal_start").copy()
        rows.append(metric_row(candidate, "baseline", group))
        for column in SCORE_COLUMNS:
            values = group[column].replace([np.inf, -np.inf], np.nan).dropna()
            if values.empty:
                continue
            thresholds: list[tuple[str, float, str]] = [
                (f"{column}_q50", float(values.quantile(0.50)), "same_period_diagnostic"),
                (f"{column}_q60", float(values.quantile(0.60)), "same_period_diagnostic"),
                (f"{column}_q70", float(values.quantile(0.70)), "same_period_diagnostic"),
                (f"{column}_q80", float(values.quantile(0.80)), "same_period_diagnostic"),
            ]
            if column in {"impulse_score", "pressure_score", "price_impulse_score"}:
                thresholds.extend(
                    [
                        (f"{column}_ge_0p5", 0.5, "absolute_diagnostic"),
                        (f"{column}_ge_1", 1.0, "absolute_diagnostic"),
                        (f"{column}_ge_2", 2.0, "absolute_diagnostic"),
                        (f"{column}_ge_3", 3.0, "absolute_diagnostic"),
                    ]
                )
            elif column == "aggression_imbalance":
                thresholds.extend(
                    [
                        (f"{column}_ge_0p25", 0.25, "absolute_diagnostic"),
                        (f"{column}_ge_0p50", 0.50, "absolute_diagnostic"),
                    ]
                )
            elif column == "aligned_depth_imbalance_3_mean":
                thresholds.extend(
                    [
                        (f"{column}_ge_0", 0.0, "absolute_diagnostic"),
                        (f"{column}_ge_0p10", 0.10, "absolute_diagnostic"),
                    ]
                )

            for gate, threshold, source in thresholds:
                gated = group[group[column] >= threshold]
                rows.append(
                    metric_row(
                        candidate,
                        gate,
                        gated,
                        score_column=column,
                        threshold=threshold,
                        threshold_source=source,
                    )
                )
    return pd.DataFrame(rows)


def bucket_summary(trade_df: pd.DataFrame, *, score_column: str = "impulse_score") -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for candidate, group in trade_df.groupby("candidate"):
        valid = group.replace([np.inf, -np.inf], np.nan).dropna(subset=[score_column])
        if len(valid) < 8:
            continue
        try:
            buckets = pd.qcut(valid[score_column], q=4, labels=("q1_low", "q2", "q3", "q4_high"), duplicates="drop")
        except ValueError:
            continue
        for bucket, subset in valid.groupby(buckets, observed=True):
            row = {
                "candidate": candidate,
                "score_column": score_column,
                "bucket": str(bucket),
                "min_score": float(subset[score_column].min()),
                "max_score": float(subset[score_column].max()),
            }
            row.update(val.r_metrics(subset["r_multiple"].to_numpy(dtype=float)))
            rows.append(row)
    return pd.DataFrame(rows)


def write_report(
    *,
    trade_df: pd.DataFrame,
    gate_df: pd.DataFrame,
    bucket_df: pd.DataFrame,
    orderbook_files: list[OrderbookFile],
    orderbook_dir: Path,
    missing_count: int,
    start: str,
    end: str | None,
    report_path: Path,
) -> None:
    lines = [
        "# NQ NY LSI Order-Book Impulse Diagnostic",
        "",
        "- Objective: test the discretionary reversal-momentum idea using true DataBento MBP-10 order-book data around 1m/2m/3m LSI candidate fills.",
        "- Feature: aligned aggressive trade volume, abnormal volume rate, aligned midpoint velocity, and top-of-book/depth imbalance during the signal confirmation bar.",
        f"- Scored trade window: `{start}` through `{end or 'latest available'}`.",
        f"- Data files used: `{len(orderbook_files)}` MBP-10 windows from `{orderbook_dir}`.",
        f"- Missing order-book matches: `{missing_count}` candidate fills.",
        "- Warning: thresholds below are same-period diagnostics on sparse windows. They are evidence for feature design, not deployable gates until frozen on pre-holdout data.",
        "",
        "## Best Diagnostic Gates",
        "",
        "| Candidate | Gate | Threshold | Trades | PF | Avg R | Total R | DD | Calmar |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    gates = gate_df[(gate_df["gate"] != "baseline") & (gate_df["trades"] >= 8)].copy()
    if gates.empty:
        lines.append("| n/a | n/a | n/a | 0 | 0.000 | 0.000 | 0.00 | 0.00 | 0.00 |")
    else:
        gates = gates.sort_values(
            ["candidate", "calmar", "profit_factor", "total_r", "trades"],
            ascending=[True, False, False, False, False],
        )
        for candidate, group in gates.groupby("candidate"):
            row = group.iloc[0]
            lines.append(
                f"| `{candidate}` | `{row['gate']}` | {float(row['threshold']):.3f} | "
                f"{int(row['trades'])} | {float(row['profit_factor']):.3f} | "
                f"{float(row['avg_r']):.3f} | {float(row['total_r']):.2f} | "
                f"{float(row['max_dd_r']):.2f} | {float(row['calmar']):.2f} |"
            )

    lines.extend(
        [
            "",
            "## Baselines",
            "",
            "| Candidate | Trades | PF | Avg R | Total R | DD | Calmar | Coverage |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in gate_df[gate_df["gate"] == "baseline"].sort_values("candidate").iterrows():
        lines.append(
            f"| `{row['candidate']}` | {int(row['trades'])} | {float(row['profit_factor']):.3f} | "
            f"{float(row['avg_r']):.3f} | {float(row['total_r']):.2f} | "
            f"{float(row['max_dd_r']):.2f} | {float(row['calmar']):.2f} | "
            f"{float(row['feature_coverage']):.1%} |"
        )

    lines.extend(
        [
            "",
            "## Impulse Score Quartiles",
            "",
            "| Candidate | Bucket | Trades | Score Range | PF | Avg R | Total R | DD |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    if bucket_df.empty:
        lines.append("| n/a | n/a | 0 | n/a | 0.000 | 0.000 | 0.00 | 0.00 |")
    else:
        for _, row in bucket_df.sort_values(["candidate", "bucket"]).iterrows():
            lines.append(
                f"| `{row['candidate']}` | {row['bucket']} | {int(row['trades'])} | "
                f"{float(row['min_score']):.3f}-{float(row['max_score']):.3f} | "
                f"{float(row['profit_factor']):.3f} | {float(row['avg_r']):.3f} | "
                f"{float(row['total_r']):.2f} | {float(row['max_dd_r']):.2f} |"
            )

    lines.extend(
        [
            "",
            "## Feature Distribution",
            "",
            "| Candidate | Trades | Impulse p50 | Impulse p75 | Pressure p50 | Mid Move p50 | Agg Imb p50 | Depth3 p50 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for candidate, group in trade_df.groupby("candidate"):
        lines.append(
            f"| `{candidate}` | {len(group)} | "
            f"{group['impulse_score'].median():.3f} | {group['impulse_score'].quantile(0.75):.3f} | "
            f"{group['pressure_score'].median():.3f} | {group['mid_move_ticks'].median():.3f} | "
            f"{group['aggression_imbalance'].median():.3f} | "
            f"{group['aligned_depth_imbalance_3_mean'].median():.3f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `impulse_score` is strict: it needs aligned aggression, abnormal volume, and aligned midpoint displacement.",
            "- `pressure_score` is looser: it rewards one-way aggression and book support even when price displacement is smaller.",
            "- A production rule should be selected from pre-holdout validation, then replayed on untouched holdout windows and exact execution data.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2025-04-01", help="Candidate trade start date inclusive.")
    parser.add_argument("--end", default="2026-05-02", help="Candidate trade end date exclusive.")
    parser.add_argument("--orderbook-dir", type=Path, default=DEFAULT_ORDERBOOK_DIR)
    parser.add_argument("--baseline-seconds", type=int, default=120)
    parser.add_argument("--max-files", type=int, default=None, help="Debug limit for DBN files.")
    parser.add_argument("--run-slug", default=RUN_SLUG)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--report-path", type=Path, default=None)
    args = parser.parse_args()

    output_dir = args.output_dir or (ROOT / "data" / "results" / args.run_slug)
    report_path = args.report_path or (ROOT / "learnings" / "reports" / f"{args.run_slug.upper()}.md")
    output_dir.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI DataBento MBP-10 order-book impulse diagnostic", flush=True)
    orderbook_files = read_manifest(args.orderbook_dir)
    if args.max_files is not None:
        orderbook_files = orderbook_files[: args.max_files]
    print(f"Loaded {len(orderbook_files):,} usable order-book file entries", flush=True)

    trade_windows = build_trade_windows(start=args.start, end=args.end)
    print(f"Candidate fills in requested window: {len(trade_windows):,}", flush=True)
    assignments, missing = match_trades_to_files(trade_windows, orderbook_files)
    print(
        f"Matched {len(trade_windows) - len(missing):,} fills across {len(assignments):,} DBN files; "
        f"missing {len(missing):,}",
        flush=True,
    )

    rows: list[dict[str, Any]] = [missing_trade_row(trade) for trade in missing]
    by_path = {item.path: item for item in orderbook_files}
    for idx, (path, trades) in enumerate(sorted(assignments.items(), key=lambda item: by_path[item[0]].start), start=1):
        file_info = by_path[path]
        t0 = time.time()
        frame = read_orderbook_frame(path)
        for trade in trades:
            rows.append(
                score_trade(
                    frame,
                    trade,
                    orderbook_file=file_info,
                    baseline_seconds=args.baseline_seconds,
                )
            )
        print(
            f"  scored {idx:>3}/{len(assignments):<3} {path.name:<62} "
            f"{len(frame):>8,} rows {len(trades):>2} fills [{time.time() - t0:.1f}s]",
            flush=True,
        )

    trade_df = pd.DataFrame(rows).sort_values(["signal_start", "candidate"]).reset_index(drop=True)
    gate_df = build_gate_summary(trade_df)
    bucket_df = bucket_summary(trade_df, score_column="impulse_score")

    trade_path = output_dir / "trade_orderbook_impulse.csv"
    gate_path = output_dir / "gate_summary.csv"
    bucket_path = output_dir / "impulse_bucket_summary.csv"
    trade_df.to_csv(trade_path, index=False)
    gate_df.to_csv(gate_path, index=False)
    bucket_df.to_csv(bucket_path, index=False)

    summary = {
        "run_slug": args.run_slug,
        "start": args.start,
        "end": args.end,
        "schema": "mbp-10",
        "orderbook_dir": str(args.orderbook_dir),
        "orderbook_files": len(orderbook_files),
        "candidate_fills": len(trade_windows),
        "matched_fills": len(trade_windows) - len(missing),
        "missing_fills": len(missing),
        "baseline_seconds": args.baseline_seconds,
        "feature_warning": "Sparse same-period diagnostic; freeze thresholds on pre-holdout data before production use.",
        "outputs": {
            "trade_orderbook_impulse_csv": str(trade_path),
            "gate_summary_csv": str(gate_path),
            "impulse_bucket_summary_csv": str(bucket_path),
            "report": str(report_path),
        },
    }
    save_json(output_dir / "summary.json", summary)
    write_report(
        trade_df=trade_df,
        gate_df=gate_df,
        bucket_df=bucket_df,
        orderbook_files=orderbook_files,
        orderbook_dir=args.orderbook_dir,
        missing_count=len(missing),
        start=args.start,
        end=args.end,
        report_path=report_path,
    )

    print(f"Wrote {trade_path}", flush=True)
    print(f"Wrote {gate_path}", flush=True)
    print(f"Wrote {bucket_path}", flush=True)
    print(f"Wrote {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
