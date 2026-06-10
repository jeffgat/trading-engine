#!/usr/bin/env python3
"""Annotate NQ NY ORB gap trades with MBP-1 top-of-book features.

This is a diagnostic lab for the ALPHA_V2 NQ_NY-RR2 thesis. It joins exact
execution replay trades to reconstructed 5m ORB/FVG setup events, then scores
local DataBento MBP-1 windows around gap creation, gap revisit, and entry.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
ET = ZoneInfo("America/New_York")
MIN_TICK = 0.25
SYMBOL = "NQ"
PROFILE = "NQ_NY_ORB_NEUTRAL_ROLLING_GATE"
RUN_SLUG = "nq_ny_orb_gap_orderbook_feature_lab_20260609"

DEFAULT_EXACT_RESULTS = (
    ROOT
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2021_20260609"
    / "artifacts"
    / "exact_replay_results.json",
    ROOT
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2025_holdout_20260609"
    / "artifacts"
    / "holdout_results.json",
    ROOT
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2026_ytd_20260609"
    / "artifacts"
    / "exact_replay_2026_ytd.json",
)
DEFAULT_BAR_5M = ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_5m.parquet"
DEFAULT_BAR_1S = ROOT / "data" / "raw" / "NQ_1s.parquet"
DEFAULT_ORDERBOOK_ROOT = ROOT / "data" / "raw" / "orderbook" / SYMBOL
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG

DBN_WINDOW_RE = re.compile(
    r"(?P<symbol>[A-Z]+)_(?P<schema>mbp\d+)_(?P<stype>[^_]+)_"
    r"(?P<start_date>\d{8})_(?P<start_time>\d{6})_to_"
    r"(?P<end_date>\d{8})_(?P<end_time>\d{6})_ET\.dbn\.zst$"
)


@dataclass(frozen=True)
class OrderbookFile:
    path: Path
    start_et: datetime
    end_et: datetime

    def overlaps(self, start: datetime, end: datetime) -> bool:
        return self.start_et < end and self.end_et > start


@dataclass(frozen=True)
class GapSetup:
    setup_found: bool
    orb_high: float | None = None
    orb_low: float | None = None
    orb_range: float | None = None
    gap_bar_time: datetime | None = None
    impulse_bar_time: datetime | None = None
    before_bar_time: datetime | None = None
    signal_end: datetime | None = None
    armed_at: datetime | None = None
    gap_top: float | None = None
    gap_bottom: float | None = None
    reconstructed_gap_size: float | None = None
    fvg_match_reason: str = ""


def _load_databento():
    try:
        import databento as db  # type: ignore
    except ImportError as exc:
        raise SystemExit("databento is required. Run `uv sync --extra data` in backtesting/.") from exc
    return db


def to_et(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize(ET)
    else:
        ts = ts.tz_convert(ET)
    return ts.to_pydatetime()


def et_datetime(day: str, hhmm: str) -> datetime:
    hour, minute = (int(part) for part in hhmm.split(":", 1))
    return datetime.fromisoformat(day).replace(hour=hour, minute=minute, tzinfo=ET)


def ns_to_et(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC).astimezone(ET)


def parse_dbn_price(value: Any) -> float | None:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if price <= 0.0:
        return None
    return price / 1_000_000_000 if abs(price) >= 1_000_000.0 else price


def level_price(level: Any, *, pretty_attr: str, raw_attr: str) -> float | None:
    pretty = getattr(level, pretty_attr, None)
    if pretty is not None:
        return parse_dbn_price(pretty)
    return parse_dbn_price(getattr(level, raw_attr, None))


def _parquet_frame(path: Path, *, start: datetime, end: datetime) -> pd.DataFrame:
    start_naive = pd.Timestamp(start).tz_convert(ET).tz_localize(None).to_pydatetime()
    end_naive = pd.Timestamp(end).tz_convert(ET).tz_localize(None).to_pydatetime()
    frame = pd.read_parquet(
        path,
        filters=[("datetime", ">=", start_naive), ("datetime", "<", end_naive)],
    )
    if not isinstance(frame.index, pd.DatetimeIndex):
        frame = frame.set_index("datetime") if "datetime" in frame.columns else frame
        frame.index = pd.to_datetime(frame.index)
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize(ET)
    else:
        frame.index = frame.index.tz_convert(ET)
    return frame.sort_index()


def load_exact_trades(paths: list[Path]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = json.loads(path.read_text())
        result = payload.get("result", payload)
        period = "unknown"
        if "2025_holdout" in str(path):
            period = "2025_holdout"
        elif "2026_ytd" in str(path):
            period = "2026_ytd"
        elif "2021_20260609" in str(path):
            period = "2021_2024_pre_holdout"
        for idx, trade in enumerate(result.get("trades") or []):
            if trade.get("session") != "NQ_NY" or trade.get("direction") != "long":
                continue
            row = dict(trade)
            row["source_path"] = str(path)
            row["period"] = period
            row["trade_uid"] = (
                f"{period}:{row.get('date')}:{idx}:"
                f"{row.get('entry_time')}:{row.get('entry_price')}"
            )
            rows.append(row)

    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame["entry_dt"] = frame["entry_time"].map(to_et)
    frame["exit_dt"] = frame["exit_time"].map(to_et)
    frame["r_multiple"] = pd.to_numeric(frame["r_multiple"], errors="coerce")
    frame["risk_points"] = pd.to_numeric(frame["risk_points"], errors="coerce")
    frame["entry_price"] = pd.to_numeric(frame["entry_price"], errors="coerce")
    frame["gap_size"] = pd.to_numeric(frame["gap_size"], errors="coerce")
    return frame.sort_values(["entry_dt", "trade_uid"]).reset_index(drop=True)


def parse_orderbook_files(orderbook_dir: Path) -> list[OrderbookFile]:
    files: list[OrderbookFile] = []
    for path in sorted(orderbook_dir.glob("*.dbn.zst")):
        match = DBN_WINDOW_RE.match(path.name)
        if match is None:
            continue
        start = datetime.strptime(
            f"{match.group('start_date')} {match.group('start_time')}",
            "%Y%m%d %H%M%S",
        ).replace(tzinfo=ET)
        end = datetime.strptime(
            f"{match.group('end_date')} {match.group('end_time')}",
            "%Y%m%d %H%M%S",
        ).replace(tzinfo=ET)
        files.append(OrderbookFile(path=path, start_et=start, end_et=end))
    return files


def find_orderbook_file(files: list[OrderbookFile], *, start: datetime, end: datetime) -> OrderbookFile | None:
    candidates = [item for item in files if item.overlaps(start, end)]
    if not candidates:
        return None
    covering = [item for item in candidates if item.start_et <= start and item.end_et >= end]
    if covering:
        return min(covering, key=lambda item: item.end_et - item.start_et)
    return max(candidates, key=lambda item: min(item.end_et, end) - max(item.start_et, start))


def load_top_of_book(path: Path, *, start: datetime, end: datetime) -> pd.DataFrame:
    db = _load_databento()
    start_ns = int(start.astimezone(UTC).timestamp() * 1_000_000_000)
    end_ns = int(end.astimezone(UTC).timestamp() * 1_000_000_000)
    rows: list[dict[str, Any]] = []

    def on_record(record: Any) -> None:
        ts_event = int(record.ts_event)
        if ts_event < start_ns:
            return
        if ts_event >= end_ns:
            raise StopIteration
        levels = getattr(record, "levels", None)
        if not levels:
            return
        top = levels[0]
        bid = level_price(top, pretty_attr="pretty_bid_px", raw_attr="bid_px")
        ask = level_price(top, pretty_attr="pretty_ask_px", raw_attr="ask_px")
        if bid is None or ask is None or ask < bid:
            return
        bid_size = getattr(top, "bid_sz", np.nan)
        ask_size = getattr(top, "ask_sz", np.nan)
        rows.append(
            {
                "timestamp": ns_to_et(ts_event),
                "bid": float(bid),
                "ask": float(ask),
                "bid_size": float(bid_size) if bid_size is not None else np.nan,
                "ask_size": float(ask_size) if ask_size is not None else np.nan,
            }
        )

    store = db.DBNStore.from_file(path)
    try:
        store.replay(on_record)
    except StopIteration:
        pass

    if not rows:
        return pd.DataFrame(
            columns=["bid", "ask", "bid_size", "ask_size", "mid", "spread", "l1_imbalance"]
        )
    frame = pd.DataFrame(rows).drop_duplicates("timestamp", keep="last")
    frame = frame.set_index("timestamp").sort_index()
    frame["mid"] = (frame["bid"] + frame["ask"]) / 2.0
    frame["spread"] = frame["ask"] - frame["bid"]
    denom = frame["bid_size"] + frame["ask_size"]
    frame["l1_imbalance"] = np.where(denom > 0, (frame["bid_size"] - frame["ask_size"]) / denom, np.nan)
    return frame


def reconstruct_gap_setup(trade: pd.Series, bars_5m_path: Path) -> GapSetup:
    day = str(trade["date"])
    day_start = et_datetime(day, "09:25")
    day_end = et_datetime(day, "13:05")
    frame = _parquet_frame(bars_5m_path, start=day_start, end=day_end)
    if frame.empty:
        return GapSetup(setup_found=False, fvg_match_reason="missing_5m_bars")

    orb_mask = (frame.index.time >= time(9, 30)) & (frame.index.time < time(9, 45))
    orb = frame.loc[orb_mask]
    if orb.empty:
        return GapSetup(setup_found=False, fvg_match_reason="missing_orb_bars")
    orb_high = float(orb["high"].max())
    orb_low = float(orb["low"].min())
    orb_range = orb_high - orb_low

    entry_price = float(trade["entry_price"])
    gap_size = float(trade["gap_size"])
    entry_dt = trade["entry_dt"]
    scan = frame[(frame.index.time >= time(9, 45)) & (frame.index.time < time(13, 0))]
    scan = scan[scan.index + pd.Timedelta(minutes=5) <= pd.Timestamp(entry_dt) + pd.Timedelta(milliseconds=1)]

    best: tuple[str, pd.Timestamp] | None = None
    for ts in scan.index:
        idx = frame.index.get_loc(ts)
        if not isinstance(idx, int) or idx < 2:
            continue
        bar0 = frame.iloc[idx]
        bar1 = frame.iloc[idx - 1]
        bar2 = frame.iloc[idx - 2]
        if not (
            float(bar2.high) < float(bar0.low)
            and float(bar2.high) < float(bar1.high)
            and float(bar2.low) < float(bar0.low)
        ):
            continue
        reconstructed_entry = float(bar0.low)
        reconstructed_gap = reconstructed_entry - float(bar2.high)
        if reconstructed_entry <= orb_high:
            continue
        entry_match = math.isclose(reconstructed_entry, entry_price, abs_tol=0.01)
        gap_match = math.isclose(reconstructed_gap, gap_size, abs_tol=0.01)
        if entry_match and gap_match:
            best = ("entry_and_gap_match", ts)
            break
        if entry_match and best is None:
            best = ("entry_match_only", ts)

    if best is None:
        return GapSetup(
            setup_found=False,
            orb_high=orb_high,
            orb_low=orb_low,
            orb_range=orb_range,
            fvg_match_reason="no_matching_fvg",
        )

    reason, ts = best
    idx = frame.index.get_loc(ts)
    bar0 = frame.iloc[idx]
    bar2 = frame.iloc[idx - 2]
    gap_top = float(bar0.low)
    gap_bottom = float(bar2.high)
    signal_end = ts.to_pydatetime() + timedelta(minutes=5)
    return GapSetup(
        setup_found=True,
        orb_high=orb_high,
        orb_low=orb_low,
        orb_range=orb_range,
        gap_bar_time=ts.to_pydatetime(),
        impulse_bar_time=frame.index[idx - 1].to_pydatetime(),
        before_bar_time=frame.index[idx - 2].to_pydatetime(),
        signal_end=signal_end,
        armed_at=signal_end,
        gap_top=gap_top,
        gap_bottom=gap_bottom,
        reconstructed_gap_size=gap_top - gap_bottom,
        fvg_match_reason=reason,
    )


def window_slice(frame: pd.DataFrame, *, start: datetime, end: datetime) -> pd.DataFrame:
    if frame.empty or end <= start:
        return frame.iloc[0:0].copy()
    return frame[(frame.index >= pd.Timestamp(start)) & (frame.index < pd.Timestamp(end))]


def coverage(frame: pd.DataFrame, *, start: datetime, end: datetime) -> float:
    if frame.empty or end <= start:
        return 0.0
    seconds = max((end - start).total_seconds(), 1.0)
    span = max((frame.index[-1].to_pydatetime() - frame.index[0].to_pydatetime()).total_seconds(), 0.0)
    return float(min(span / seconds, 1.0))


def empty_feature(prefix: str) -> dict[str, Any]:
    return {
        f"{prefix}_sample_count": 0,
        f"{prefix}_coverage": 0.0,
        f"{prefix}_mid_velocity_ticks_per_sec": np.nan,
        f"{prefix}_mid_move_ticks": np.nan,
        f"{prefix}_mid_range_ticks": np.nan,
        f"{prefix}_spread_mean_ticks": np.nan,
        f"{prefix}_spread_last_ticks": np.nan,
        f"{prefix}_spread_widen_ticks": np.nan,
        f"{prefix}_l1_imbalance_mean": np.nan,
        f"{prefix}_l1_imbalance_last": np.nan,
        f"{prefix}_bid_dominance_pct": np.nan,
        f"{prefix}_bid_size_delta": np.nan,
        f"{prefix}_ask_size_delta": np.nan,
        f"{prefix}_update_rate_per_sec": 0.0,
    }


def book_features(frame: pd.DataFrame, *, start: datetime, end: datetime, prefix: str, direction: int = 1) -> dict[str, Any]:
    window = window_slice(frame, start=start, end=end)
    if len(window) < 2:
        return empty_feature(prefix)
    seconds = max((end - start).total_seconds(), 1.0)
    mid = window["mid"].astype(float)
    spread = window["spread"].astype(float) / MIN_TICK
    imbalance = window["l1_imbalance"].astype(float)
    bid_size = window["bid_size"].astype(float)
    ask_size = window["ask_size"].astype(float)
    return {
        f"{prefix}_sample_count": int(len(window)),
        f"{prefix}_coverage": round(coverage(window, start=start, end=end), 6),
        f"{prefix}_mid_velocity_ticks_per_sec": float(direction * ((mid.iloc[-1] - mid.iloc[0]) / MIN_TICK) / seconds),
        f"{prefix}_mid_move_ticks": float(direction * ((mid.iloc[-1] - mid.iloc[0]) / MIN_TICK)),
        f"{prefix}_mid_range_ticks": float((mid.max() - mid.min()) / MIN_TICK),
        f"{prefix}_spread_mean_ticks": float(spread.mean()),
        f"{prefix}_spread_last_ticks": float(spread.iloc[-1]),
        f"{prefix}_spread_widen_ticks": float(spread.iloc[-1] - spread.iloc[0]),
        f"{prefix}_l1_imbalance_mean": float(imbalance.mean()),
        f"{prefix}_l1_imbalance_last": float(imbalance.iloc[-1]),
        f"{prefix}_bid_dominance_pct": float(imbalance.gt(0).mean() * 100.0),
        f"{prefix}_bid_size_delta": float(bid_size.iloc[-1] - bid_size.iloc[0]),
        f"{prefix}_ask_size_delta": float(ask_size.iloc[-1] - ask_size.iloc[0]),
        f"{prefix}_update_rate_per_sec": float(len(window) / seconds),
    }


def price_features(frame: pd.DataFrame, *, start: datetime, end: datetime, prefix: str, direction: int = 1) -> dict[str, Any]:
    window = window_slice(frame, start=start, end=end)
    if len(window) < 2:
        return {
            f"{prefix}_price_sample_count": int(len(window)),
            f"{prefix}_price_velocity_ticks_per_sec": np.nan,
            f"{prefix}_price_move_ticks": np.nan,
            f"{prefix}_price_range_ticks": np.nan,
            f"{prefix}_price_volume": np.nan,
        }
    seconds = max((end - start).total_seconds(), 1.0)
    first = float(window["open"].iloc[0])
    last = float(window["close"].iloc[-1])
    high = float(window["high"].max())
    low = float(window["low"].min())
    return {
        f"{prefix}_price_sample_count": int(len(window)),
        f"{prefix}_price_velocity_ticks_per_sec": float(direction * ((last - first) / MIN_TICK) / seconds),
        f"{prefix}_price_move_ticks": float(direction * ((last - first) / MIN_TICK)),
        f"{prefix}_price_range_ticks": float((high - low) / MIN_TICK),
        f"{prefix}_price_volume": float(window["volume"].sum()),
    }


def mfe_mae_features(trade: pd.Series, bars_1s_path: Path) -> dict[str, Any]:
    entry_dt = trade["entry_dt"]
    exit_dt = trade["exit_dt"]
    if exit_dt <= entry_dt:
        return {"mfe_r": np.nan, "mae_r": np.nan, "time_to_mfe_seconds": np.nan}
    frame = _parquet_frame(bars_1s_path, start=entry_dt, end=exit_dt + timedelta(seconds=1))
    if frame.empty:
        return {"mfe_r": np.nan, "mae_r": np.nan, "time_to_mfe_seconds": np.nan}
    entry = float(trade["entry_price"])
    risk = float(trade["risk_points"])
    if risk <= 0:
        return {"mfe_r": np.nan, "mae_r": np.nan, "time_to_mfe_seconds": np.nan}
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    favorable = max(0.0, float(high.max()) - entry)
    adverse = max(0.0, entry - float(low.min()))
    mfe_ts = high.idxmax()
    return {
        "mfe_r": float(favorable / risk),
        "mae_r": float(adverse / risk),
        "time_to_mfe_seconds": int((pd.Timestamp(mfe_ts) - pd.Timestamp(entry_dt)).total_seconds()),
    }


def build_windows_row(row: dict[str, Any]) -> dict[str, Any]:
    start = row.get("orderbook_needed_start")
    end = row.get("orderbook_needed_end")
    return {
        "symbol": SYMBOL,
        "date": row.get("date"),
        "start": start,
        "end": end,
        "reason": "nq_ny_orb_gap_orderbook_lab",
        "trade_uid": row.get("trade_uid"),
    }


def analyze_rows(frame: pd.DataFrame) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "rows": int(len(frame)),
        "setup_found": int(frame["setup_found"].sum()) if "setup_found" in frame else 0,
        "orderbook_file_found": int(frame["orderbook_file_found"].sum()) if "orderbook_file_found" in frame else 0,
    }
    if "pre_entry_30s_sample_count" not in frame:
        summary["scored_rows"] = 0
        return summary
    scored = frame[frame["pre_entry_30s_sample_count"].fillna(0) >= 2].copy()
    summary["scored_rows"] = int(len(scored))
    if scored.empty:
        return summary

    features = [
        "gap_create_last30s_mid_velocity_ticks_per_sec",
        "gap_create_last30s_l1_imbalance_mean",
        "pre_entry_30s_mid_velocity_ticks_per_sec",
        "pre_entry_30s_l1_imbalance_mean",
        "pre_entry_10s_mid_velocity_ticks_per_sec",
        "pre_entry_10s_l1_imbalance_mean",
        "post_entry_30s_mid_velocity_ticks_per_sec",
    ]
    groups: dict[str, dict[str, Any]] = {}
    for name, group in (
        ("winners", scored[scored["r_multiple"] > 0]),
        ("losers", scored[scored["r_multiple"] <= 0]),
        ("mfe_ge_2r", scored[scored["mfe_r"] >= 2.0]),
        ("mfe_lt_1r", scored[scored["mfe_r"] < 1.0]),
    ):
        groups[name] = {"count": int(len(group))}
        if group.empty:
            continue
        groups[name]["avg_r"] = float(group["r_multiple"].mean())
        groups[name]["avg_mfe_r"] = float(group["mfe_r"].mean())
        for feature in features:
            if feature in group:
                groups[name][feature] = float(group[feature].mean())
    summary["groups"] = groups

    correlations: dict[str, dict[str, float]] = {}
    for feature in features:
        if feature not in scored:
            continue
        clean = scored[[feature, "r_multiple", "mfe_r"]].dropna()
        if len(clean) < 3 or clean[feature].nunique() < 2:
            continue
        correlations[feature] = {
            "corr_r": float(clean[feature].corr(clean["r_multiple"])),
            "corr_mfe_r": float(clean[feature].corr(clean["mfe_r"])),
        }
    summary["correlations"] = correlations
    return summary


def write_markdown(summary: dict[str, Any], output_path: Path) -> None:
    groups = summary.get("groups") or {}
    correlations = summary.get("correlations") or {}
    lines = [
        "# NQ NY ORB Gap Order Book Feature Lab",
        "",
        f"- Profile: `{PROFILE}`",
        "- Scope: diagnostic only, no live filter promotion.",
        f"- Rows: `{summary.get('rows', 0)}`",
        f"- Setup reconstructed: `{summary.get('setup_found', 0)}`",
        f"- Order book files found: `{summary.get('orderbook_file_found', 0)}`",
        f"- Scored rows: `{summary.get('scored_rows', 0)}`",
        "",
        "## Group Means",
        "",
        "| Group | Count | Avg R | Avg MFE R | Pre-entry 30s mid vel | Pre-entry 30s L1 imbalance |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in ("winners", "losers", "mfe_ge_2r", "mfe_lt_1r"):
        group = groups.get(name) or {}
        lines.append(
            "| {name} | {count} | {avg_r:.3f} | {avg_mfe:.3f} | {vel:.6f} | {imb:.6f} |".format(
                name=name,
                count=int(group.get("count", 0)),
                avg_r=float(group.get("avg_r", 0.0) or 0.0),
                avg_mfe=float(group.get("avg_mfe_r", 0.0) or 0.0),
                vel=float(group.get("pre_entry_30s_mid_velocity_ticks_per_sec", 0.0) or 0.0),
                imb=float(group.get("pre_entry_30s_l1_imbalance_mean", 0.0) or 0.0),
            )
        )
    lines.extend(["", "## Feature Correlations", ""])
    if correlations:
        lines.extend(["| Feature | Corr R | Corr MFE R |", "|---|---:|---:|"])
        for feature, vals in correlations.items():
            lines.append(f"| `{feature}` | {vals['corr_r']:.4f} | {vals['corr_mfe_r']:.4f} |")
    else:
        lines.append("Not enough scored rows for stable correlations.")
    lines.extend(
        [
            "",
            "## Causality Notes",
            "",
            "- `gap_create_*` windows end at the FVG signal close.",
            "- `pre_entry_*` windows end at the exact fill timestamp.",
            "- `post_entry_*` windows are diagnostics only and must not be used as entry filters.",
        ]
    )
    output_path.write_text("\n".join(lines) + "\n")


def run(args: argparse.Namespace) -> int:
    exact_inputs = args.exact_result_json
    if exact_inputs is None:
        exact_inputs = [str(path) for path in DEFAULT_EXACT_RESULTS if path.exists()]
    exact_paths = [Path(path) for path in exact_inputs]
    trades = load_exact_trades(exact_paths)
    if trades.empty:
        raise SystemExit("No NQ_NY long trades found in exact result JSON files.")
    if args.start_date:
        trades = trades[trades["entry_dt"] >= et_datetime(args.start_date, "00:00")]
    if args.end_date:
        trades = trades[trades["entry_dt"] < et_datetime(args.end_date, "00:00")]
    if args.max_trades:
        trades = trades.head(args.max_trades)

    orderbook_dir = Path(args.orderbook_root) / args.schema
    orderbook_files = parse_orderbook_files(orderbook_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    needed_windows: list[dict[str, Any]] = []
    book_cache: dict[Path, pd.DataFrame] = {}

    for _, trade in trades.iterrows():
        setup = reconstruct_gap_setup(trade, Path(args.bars_5m))
        entry_dt = trade["entry_dt"]
        end_needed = max(entry_dt + timedelta(minutes=5), et_datetime(str(trade["date"]), "10:30"))
        start_needed = et_datetime(str(trade["date"]), "09:30")
        row: dict[str, Any] = {
            "profile": PROFILE,
            "trade_uid": trade["trade_uid"],
            "period": trade["period"],
            "date": trade["date"],
            "entry_time": entry_dt.isoformat(),
            "exit_time": trade["exit_dt"].isoformat(),
            "exit_type": trade["exit_type"],
            "r_multiple": float(trade["r_multiple"]),
            "entry_price": float(trade["entry_price"]),
            "risk_points": float(trade["risk_points"]),
            "gap_size": float(trade["gap_size"]),
            "orderbook_schema": args.schema,
            "orderbook_needed_start": start_needed.isoformat(),
            "orderbook_needed_end": end_needed.isoformat(),
            **asdict(setup),
        }
        row.update(mfe_mae_features(trade, Path(args.bars_1s)))
        for key in ("gap_bar_time", "impulse_bar_time", "before_bar_time", "signal_end", "armed_at"):
            if isinstance(row.get(key), datetime):
                row[key] = row[key].isoformat()

        if not setup.setup_found or setup.signal_end is None or setup.armed_at is None:
            row["orderbook_file_found"] = False
            row["orderbook_path"] = ""
            rows.append(row)
            needed_windows.append(build_windows_row(row))
            continue

        ob_file = find_orderbook_file(orderbook_files, start=start_needed, end=end_needed)
        row["orderbook_file_found"] = ob_file is not None
        row["orderbook_path"] = str(ob_file.path) if ob_file else ""
        if ob_file is None:
            rows.append(row)
            needed_windows.append(build_windows_row(row))
            continue

        if ob_file.path not in book_cache:
            book_cache[ob_file.path] = load_top_of_book(ob_file.path, start=ob_file.start_et, end=ob_file.end_et)
        book = book_cache[ob_file.path]

        price_start = setup.gap_bar_time
        price_end = entry_dt + timedelta(minutes=2)
        price_1s = _parquet_frame(Path(args.bars_1s), start=price_start, end=price_end)

        windows = [
            ("gap_create_5m", setup.gap_bar_time, setup.signal_end),
            ("gap_create_last30s", setup.signal_end - timedelta(seconds=30), setup.signal_end),
            ("gap_create_last10s", setup.signal_end - timedelta(seconds=10), setup.signal_end),
            ("revisit_full", setup.armed_at, entry_dt),
            ("pre_entry_30s", entry_dt - timedelta(seconds=30), entry_dt),
            ("pre_entry_10s", entry_dt - timedelta(seconds=10), entry_dt),
            ("post_entry_30s", entry_dt, entry_dt + timedelta(seconds=30)),
            ("post_entry_60s", entry_dt, entry_dt + timedelta(seconds=60)),
        ]
        for prefix, start, end in windows:
            row.update(book_features(book, start=start, end=end, prefix=prefix, direction=1))
            row.update(price_features(price_1s, start=start, end=end, prefix=prefix, direction=1))
        rows.append(row)

    result = pd.DataFrame(rows)
    result_path = output_dir / "trade_orderbook_gap_features.csv"
    result.to_csv(result_path, index=False)

    windows = pd.DataFrame(needed_windows).drop_duplicates() if needed_windows else pd.DataFrame(
        columns=["symbol", "date", "start", "end", "reason", "trade_uid"]
    )
    windows_path = output_dir / "missing_orderbook_windows.csv"
    windows.to_csv(windows_path, index=False)

    summary = analyze_rows(result)
    summary.update(
        {
            "run_slug": output_dir.name,
            "profile": PROFILE,
            "schema": args.schema,
            "exact_result_json": [str(path) for path in exact_paths],
            "output_csv": str(result_path),
            "missing_windows_csv": str(windows_path),
            "local_orderbook_files": len(orderbook_files),
        }
    )
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str) + "\n")
    write_markdown(summary, output_dir / "summary.md")
    print(json.dumps(summary, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exact-result-json",
        action="append",
        default=None,
        help="Exact replay JSON to annotate. Can be passed multiple times.",
    )
    parser.add_argument("--schema", default="mbp-1", choices=["mbp-1", "mbp-10"])
    parser.add_argument("--orderbook-root", type=Path, default=DEFAULT_ORDERBOOK_ROOT)
    parser.add_argument("--bars-5m", type=Path, default=DEFAULT_BAR_5M)
    parser.add_argument("--bars-1s", type=Path, default=DEFAULT_BAR_1S)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--start-date", default=None, help="Inclusive ET date YYYY-MM-DD.")
    parser.add_argument("--end-date", default=None, help="Exclusive ET date YYYY-MM-DD.")
    parser.add_argument("--max-trades", type=int, default=None)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
