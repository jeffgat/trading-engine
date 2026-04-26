#!/usr/bin/env python3
"""Diagnose a TradingView ORB export against a reverse-engineered Hunter ORB model.

This is intentionally a research diagnostic, not a production strategy engine.
It checks the visible settings from the TradingView screenshots against an
exported trade list and local NQ 1-second market data.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


POINT_VALUE = 20.0
ROUND_TRIP_COMMISSION = 3.60

ORB_START = "09:30"
ORB_SIGNAL_END = "09:40"  # 09:30, 09:35, 09:40 bars form the 09:30-09:45 ORB.
SIGNAL_START = "09:45"
SIGNAL_END = "10:55"  # next-bar entries land no later than 11:00.

ALLOWED_WEEKDAYS = {0, 2, 3, 4}  # Mon, Wed, Thu, Fri. Tuesday disabled in screenshots.
BODY_MIN_PCT = 55.0
REJECTION_WICK_MAX_PCT = 20.0
SL_BUFFER_POINTS = 1.0
TARGET_RR = 2.0
LARGE_SL_THRESHOLD_POINTS = 50.0
REDUCED_TARGET_RR = 1.0


@dataclass(frozen=True)
class ExportTrade:
    trade_no: int
    side: str
    entry_dt: pd.Timestamp
    exit_dt: pd.Timestamp
    entry_price: float
    exit_price: float
    qty: float
    pnl_usd: float
    mfe_usd: float
    mae_usd: float
    entry_signal: str
    exit_signal: str


@dataclass(frozen=True)
class TradeDiagnostic:
    trade_no: int
    side: str
    entry_dt: str
    exit_dt: str
    entry_price: float
    exit_price: float
    qty: float
    pnl_usd: float
    exit_signal: str
    signal_dt: str | None
    data_offset_points: float | None
    orb_high: float | None
    orb_low: float | None
    signal_open: float | None
    signal_high: float | None
    signal_low: float | None
    signal_close: float | None
    body_pct: float | None
    rejection_wick_pct: float | None
    crossed_orb_on_close: bool | None
    inferred_stop: float | None
    inferred_risk_points: float | None
    inferred_rr: float | None
    inferred_target: float | None
    expected_exit_price: float | None
    exit_error_points: float | None


@dataclass(frozen=True)
class CandidateDiagnostic:
    entry_dt: str
    signal_dt: str
    side: str
    accepted_in_export: bool
    blocked_by_export_position: bool
    body_pct: float
    rejection_wick_pct: float
    breakout_extension_pct_of_orb: float
    volume_ratio_sma20: float | None
    ema9_direction_pass: bool | None
    ema200_direction_pass: bool | None


def parse_export(path: Path) -> list[ExportTrade]:
    rows_by_trade: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows_by_trade[int(row["Trade #"])].append(row)

    trades: list[ExportTrade] = []
    for trade_no, rows in sorted(rows_by_trade.items()):
        entries = [row for row in rows if row["Type"].startswith("Entry")]
        exits = [row for row in rows if row["Type"].startswith("Exit")]
        if len(entries) != 1 or len(exits) != 1:
            raise ValueError(f"Trade {trade_no} is not a clean entry/exit pair: {rows}")

        entry = entries[0]
        exit_ = exits[0]
        side = "long" if "long" in entry["Type"].lower() else "short"
        trades.append(
            ExportTrade(
                trade_no=trade_no,
                side=side,
                entry_dt=pd.Timestamp(entry["Date and time"]),
                exit_dt=pd.Timestamp(exit_["Date and time"]),
                entry_price=float(entry["Price USD"]),
                exit_price=float(exit_["Price USD"]),
                qty=float(entry["Size (qty)"]),
                pnl_usd=float(entry["Net P&L USD"]),
                mfe_usd=float(entry["Favorable excursion USD"]),
                mae_usd=float(entry["Adverse excursion USD"]),
                entry_signal=entry["Signal"],
                exit_signal=exit_["Signal"],
            )
        )
    return trades


def load_5m_from_1s(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    table = pq.read_table(path, filters=[("datetime", ">=", start), ("datetime", "<", end)])
    df = table.to_pandas().sort_index()
    if df.empty:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

    bars = (
        df.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    bars["vol_sma20"] = bars["volume"].rolling(20).mean()
    bars["ema9"] = bars["close"].ewm(span=9, adjust=False).mean()
    bars["ema200"] = bars["close"].ewm(span=200, adjust=False).mean()
    return bars


def load_tradingview_5m_csv(path: Path, timezone: str = "America/New_York") -> pd.DataFrame:
    """Load a TradingView OHLC CSV exported from the chart data window.

    TradingView exports Unix timestamps in UTC. Strategy settings in this
    investigation use New York time, so the index is converted to New York and
    made timezone-naive to match the strategy tester export timestamps.
    """
    df = pd.read_csv(path)
    required = {"time", "open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"TradingView CSV is missing columns: {sorted(missing)}")

    index = pd.to_datetime(df["time"], unit="s", utc=True).dt.tz_convert(timezone).dt.tz_localize(None)
    bars = df.assign(datetime=index).set_index("datetime").sort_index()
    bars = bars[["open", "high", "low", "close"]].astype(float)
    if "volume" in df.columns:
        bars["volume"] = df["volume"].astype(float).values
    else:
        bars["volume"] = math.nan
    bars["vol_sma20"] = bars["volume"].rolling(20).mean()
    bars["ema9"] = bars["close"].ewm(span=9, adjust=False).mean()
    bars["ema200"] = bars["close"].ewm(span=200, adjust=False).mean()
    return bars


def orb_levels_by_day(bars: pd.DataFrame) -> dict[Any, tuple[float, float]]:
    levels: dict[Any, tuple[float, float]] = {}
    for day, group in bars.groupby(bars.index.date):
        orb = group.between_time(ORB_START, ORB_SIGNAL_END)
        if len(orb) >= 3:
            levels[day] = (float(orb["high"].max()), float(orb["low"].min()))
    return levels


def body_and_rejection(row: pd.Series, side: str) -> tuple[float, float]:
    candle_range = float(row.high - row.low)
    if candle_range <= 0:
        return 0.0, 100.0
    body_pct = abs(float(row.close - row.open)) / candle_range * 100.0
    if side == "long":
        rejection = (float(row.high) - max(float(row.open), float(row.close))) / candle_range * 100.0
    else:
        rejection = (min(float(row.open), float(row.close)) - float(row.low)) / candle_range * 100.0
    return body_pct, rejection


def diagnose_trades(
    trades: list[ExportTrade],
    bars: pd.DataFrame,
    levels: dict[Any, tuple[float, float]],
) -> list[TradeDiagnostic]:
    diagnostics: list[TradeDiagnostic] = []

    for trade in trades:
        signal_dt = trade.entry_dt - pd.Timedelta(minutes=5)
        if trade.entry_dt not in bars.index or signal_dt not in bars.index or trade.entry_dt.date() not in levels:
            diagnostics.append(
                TradeDiagnostic(
                    trade_no=trade.trade_no,
                    side=trade.side,
                    entry_dt=str(trade.entry_dt),
                    exit_dt=str(trade.exit_dt),
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    qty=trade.qty,
                    pnl_usd=trade.pnl_usd,
                    exit_signal=trade.exit_signal,
                    signal_dt=None,
                    data_offset_points=None,
                    orb_high=None,
                    orb_low=None,
                    signal_open=None,
                    signal_high=None,
                    signal_low=None,
                    signal_close=None,
                    body_pct=None,
                    rejection_wick_pct=None,
                    crossed_orb_on_close=None,
                    inferred_stop=None,
                    inferred_risk_points=None,
                    inferred_rr=None,
                    inferred_target=None,
                    expected_exit_price=None,
                    exit_error_points=None,
                )
            )
            continue

        current_bar = bars.loc[trade.entry_dt]
        signal_bar = bars.loc[signal_dt]
        offset = trade.entry_price - float(current_bar.open)

        signal_open = float(signal_bar.open) + offset
        signal_high = float(signal_bar.high) + offset
        signal_low = float(signal_bar.low) + offset
        signal_close = float(signal_bar.close) + offset
        orb_high, orb_low = levels[trade.entry_dt.date()]
        orb_high += offset
        orb_low += offset

        body_pct, rejection_pct = body_and_rejection(signal_bar, trade.side)
        crossed = signal_close > orb_high if trade.side == "long" else signal_close < orb_low

        if trade.side == "long":
            stop = signal_low - SL_BUFFER_POINTS
            risk = trade.entry_price - stop
            rr = REDUCED_TARGET_RR if risk >= LARGE_SL_THRESHOLD_POINTS else TARGET_RR
            target = trade.entry_price + risk * rr
        else:
            stop = signal_high + SL_BUFFER_POINTS
            risk = stop - trade.entry_price
            rr = REDUCED_TARGET_RR if risk >= LARGE_SL_THRESHOLD_POINTS else TARGET_RR
            target = trade.entry_price - risk * rr

        expected_exit = None
        exit_error = None
        if trade.exit_signal != "Max Hold Time":
            expected_exit = target if trade.pnl_usd > 0 else stop
            exit_error = trade.exit_price - expected_exit

        diagnostics.append(
            TradeDiagnostic(
                trade_no=trade.trade_no,
                side=trade.side,
                entry_dt=str(trade.entry_dt),
                exit_dt=str(trade.exit_dt),
                entry_price=trade.entry_price,
                exit_price=trade.exit_price,
                qty=trade.qty,
                pnl_usd=trade.pnl_usd,
                exit_signal=trade.exit_signal,
                signal_dt=str(signal_dt),
                data_offset_points=round(offset, 6),
                orb_high=round(orb_high, 6),
                orb_low=round(orb_low, 6),
                signal_open=round(signal_open, 6),
                signal_high=round(signal_high, 6),
                signal_low=round(signal_low, 6),
                signal_close=round(signal_close, 6),
                body_pct=round(body_pct, 6),
                rejection_wick_pct=round(rejection_pct, 6),
                crossed_orb_on_close=crossed,
                inferred_stop=round(stop, 6),
                inferred_risk_points=round(risk, 6),
                inferred_rr=rr,
                inferred_target=round(target, 6),
                expected_exit_price=round(expected_exit, 6) if expected_exit is not None else None,
                exit_error_points=round(exit_error, 6) if exit_error is not None else None,
            )
        )

    return diagnostics


def active_export_position(entry_dt: pd.Timestamp, trades: list[ExportTrade]) -> bool:
    for trade in trades:
        if trade.entry_dt.date() == entry_dt.date() and trade.entry_dt < entry_dt <= trade.exit_dt:
            return True
    return False


def build_base_candidates(
    trades: list[ExportTrade],
    bars: pd.DataFrame,
    levels: dict[Any, tuple[float, float]],
) -> list[CandidateDiagnostic]:
    accepted = {(trade.entry_dt, trade.side) for trade in trades if trade.entry_dt in bars.index}
    candidates: list[CandidateDiagnostic] = []

    for day, group in bars.groupby(bars.index.date):
        if pd.Timestamp(day).weekday() not in ALLOWED_WEEKDAYS or day not in levels:
            continue
        orb_high, orb_low = levels[day]
        orb_range = max(orb_high - orb_low, 1e-9)
        signal_bars = group.between_time(SIGNAL_START, SIGNAL_END)
        for signal_dt, row in signal_bars.iterrows():
            group_pos = group.index.get_loc(signal_dt)
            if group_pos == 0:
                continue
            previous_close = float(group.iloc[group_pos - 1].close)

            raw_sides: list[str] = []
            if float(row.close) > orb_high and previous_close <= orb_high:
                raw_sides.append("long")
            if float(row.close) < orb_low and previous_close >= orb_low:
                raw_sides.append("short")

            for side in raw_sides:
                body_pct, rejection_pct = body_and_rejection(row, side)
                if body_pct < BODY_MIN_PCT or rejection_pct > REJECTION_WICK_MAX_PCT:
                    continue

                entry_dt = signal_dt + pd.Timedelta(minutes=5)
                accepted_in_export = (entry_dt, side) in accepted
                blocked = active_export_position(entry_dt, trades) and not accepted_in_export
                if blocked:
                    # Useful for diagnostics, but not a true false-positive candidate.
                    pass

                extension_pct = (
                    (float(row.close) - orb_high) / orb_range * 100.0
                    if side == "long"
                    else (orb_low - float(row.close)) / orb_range * 100.0
                )
                vol_ratio = None
                if pd.notna(row.vol_sma20) and float(row.vol_sma20) != 0:
                    vol_ratio = float(row.volume / row.vol_sma20)

                candidates.append(
                    CandidateDiagnostic(
                        entry_dt=str(entry_dt),
                        signal_dt=str(signal_dt),
                        side=side,
                        accepted_in_export=accepted_in_export,
                        blocked_by_export_position=blocked,
                        body_pct=round(body_pct, 6),
                        rejection_wick_pct=round(rejection_pct, 6),
                        breakout_extension_pct_of_orb=round(extension_pct, 6),
                        volume_ratio_sma20=round(vol_ratio, 6) if vol_ratio is not None else None,
                        ema9_direction_pass=bool(row.close > row.ema9) if side == "long" else bool(row.close < row.ema9),
                        ema200_direction_pass=bool(row.close > row.ema200) if side == "long" else bool(row.close < row.ema200),
                    )
                )

    return candidates


def summarize(
    trades: list[ExportTrade],
    trade_diagnostics: list[TradeDiagnostic],
    candidates: list[CandidateDiagnostic],
    bars: pd.DataFrame,
    data_label: str,
) -> dict[str, Any]:
    with_data = [diag for diag in trade_diagnostics if diag.signal_dt is not None]
    non_max_errors = [
        abs(diag.exit_error_points)
        for diag in with_data
        if diag.exit_error_points is not None and diag.exit_signal != "Max Hold Time"
    ]
    accepted_with_data = {
        (diag.entry_dt, diag.side)
        for diag in with_data
        if pd.Timestamp(diag.entry_dt) in bars.index
    }
    unblocked_candidates = [cand for cand in candidates if not cand.blocked_by_export_position]
    candidate_set = {(cand.entry_dt, cand.side) for cand in unblocked_candidates}

    return {
        "export": {
            "trades": len(trades),
            "date_start": str(min(trade.entry_dt for trade in trades)),
            "date_end": str(max(trade.entry_dt for trade in trades)),
            "net_pnl_usd": round(sum(trade.pnl_usd for trade in trades), 2),
            "win_rate": round(sum(trade.pnl_usd > 0 for trade in trades) / len(trades), 6),
            "side_counts": dict(Counter(trade.side for trade in trades)),
            "qty_counts": dict(Counter(str(trade.qty) for trade in trades)),
            "exit_signal_counts": dict(Counter(trade.exit_signal for trade in trades)),
            "weekday_counts": dict(Counter(trade.entry_dt.day_name() for trade in trades)),
        },
        "price_data": {
            "source": data_label,
            "bars": len(bars),
            "start": str(bars.index.min()) if not bars.empty else None,
            "end": str(bars.index.max()) if not bars.empty else None,
            "export_trades_with_price_data": len(with_data),
            "export_trades_missing_price_data": len(trades) - len(with_data),
        },
        "exit_geometry_hypothesis": {
            "model": "next-bar entry; stop at breakout candle opposite wick +/- 1 point; target 2R unless risk >= 50 points, then 1R",
            "non_max_exits_tested": len(non_max_errors),
            "median_abs_error_points": round(float(pd.Series(non_max_errors).median()), 6) if non_max_errors else None,
            "mean_abs_error_points": round(float(pd.Series(non_max_errors).mean()), 6) if non_max_errors else None,
            "max_abs_error_points": round(max(non_max_errors), 6) if non_max_errors else None,
            "within_1_point": sum(error <= 1.0 for error in non_max_errors),
            "within_2_points": sum(error <= 2.0 for error in non_max_errors),
            "within_5_points": sum(error <= 5.0 for error in non_max_errors),
            "rr_counts": dict(Counter(str(diag.inferred_rr) for diag in with_data)),
        },
        "base_entry_hypothesis": {
            "model": "close crosses ORB high/low during entry window; body >= 55%; rejection wick <= 20%; no Tuesday; no new trade while export position is open",
            "unblocked_candidates": len(unblocked_candidates),
            "accepted_matched": len(accepted_with_data & candidate_set),
            "accepted_missing": sorted(list(accepted_with_data - candidate_set))[:20],
            "remaining_false_positive_candidates": sorted(list(candidate_set - accepted_with_data))[:50],
            "remaining_false_positive_count": len(candidate_set - accepted_with_data),
            "blocked_by_export_position": sum(cand.blocked_by_export_position for cand in candidates),
        },
    }


def write_csv(path: Path, rows: list[Any]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="TradingView Strategy Tester CSV export")
    parser.add_argument("--data-1s", default=Path("data/raw/NQ_1s.parquet"), type=Path)
    parser.add_argument(
        "--tv-5m",
        type=Path,
        default=None,
        help="Optional TradingView OHLC 5-minute CSV. If provided, this replaces local 1s-resampled data.",
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    trades = parse_export(args.csv)
    if args.tv_5m is not None:
        bars = load_tradingview_5m_csv(args.tv_5m)
        data_label = f"TradingView 5m CSV: {args.tv_5m}"
    else:
        start = pd.Timestamp(min(trade.entry_dt for trade in trades).date())
        end = pd.Timestamp(max(trade.entry_dt for trade in trades).date()) + pd.Timedelta(days=1)
        bars = load_5m_from_1s(args.data_1s, start, end)
        data_label = f"Local 1s resampled to 5m: {args.data_1s}"
    levels = orb_levels_by_day(bars)

    trade_diagnostics = diagnose_trades(trades, bars, levels)
    candidates = build_base_candidates(trades, bars, levels)
    summary = summarize(trades, trade_diagnostics, candidates, bars, data_label)

    print(json.dumps(summary, indent=2, default=str))

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        write_csv(args.output_dir / "trade_diagnostics.csv", trade_diagnostics)
        write_csv(args.output_dir / "candidate_diagnostics.csv", candidates)


if __name__ == "__main__":
    main()
