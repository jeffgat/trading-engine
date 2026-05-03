#!/usr/bin/env python3
"""Reverse-engineer the N4A Gold-X v14.4 TradingView export.

This is a research diagnostic, not a production engine. It implements the
visible Gold-X settings guide semantics and compares them with an exported
TradingView strategy tester trade list plus local futures data.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq


DEFAULT_POINT_VALUE = 20.0
DEFAULT_ROUND_TRIP_COMMISSION = 3.60
INITIAL_CAPITAL = 10_000.0

ORB_START = "09:30"
ORB_END_BAR = "09:40"
CLASSIC_SIGNAL_START = "09:45"
# Last Classic signal bar whose next-bar strategy fill is still inside the
# guide's 09:45-10:50 New York entry window. The 10:50 signal bar would fill
# at 10:55; those were all local-only extras against the GC TradingView export.
CLASSIC_SIGNAL_END = "10:45"
FVG_BREAKOUT_START = "09:45"
FVG_BREAKOUT_END = "13:00"

CLASSIC_WEEKDAYS = {0, 3, 4}  # Mon, Thu, Fri
FVG_WEEKDAYS = {0, 1, 3}  # Mon, Tue, Thu

FVG_BARS_BEFORE = 2
FVG_BARS_AFTER = 2
FVG_MIN_SIZE_POINTS = 9.0
FVG_MAX_SIZE_POINTS = 60.0
FVG_MAX_ORB_DISTANCE_POINTS = 30.0
FVG_TARGET_RR = 2.0
FVG_MIN_STOP_POINTS = 10.0
FVG_MAX_WAIT_BARS = 30
FVG_MAX_WAIT_MINUTES = 200
FVG_SELECTION_COOLDOWN_MINUTES = 5
FVG_MAX_HOLD_MINUTES = 270
FVG_UT_KEY_VALUE = 2.0
FVG_UT_ATR_PERIOD = 40

CLASSIC_TARGET_SD = 1.0
CLASSIC_HARD_STOP_BUFFER_POINTS = 7.0
CLASSIC_OVEREXTENSION_MAX_PCT = 60.0
CLASSIC_COOLDOWN_MINUTES = 50
CLASSIC_MAX_HOLD_MINUTES = 180
CLASSIC_SQUEEZE_LENGTH = 100
CLASSIC_DIVERGENCE_LOOKBACK = 15
CLASSIC_RG_PERIOD = 30
CLASSIC_RG_MULT = 5.0
CLASSIC_TREND_FAST_EMA = 20
CLASSIC_TREND_SLOW_EMA = 50
CLASSIC_MOMENTUM_FAST_EMA = 8
CLASSIC_MOMENTUM_SLOW_EMA = 100
CLASSIC_MOMENTUM_SENSITIVITY = 250.0
CLASSIC_EMA_FILTER_LENGTH = 200
CLASSIC_EMA_CLOUD_PERIOD = 9
CLASSIC_EMA_CROSS_SENSITIVITY_HOURS = 4.0
CLASSIC_EMA_CROSS_MAX_CROSSES = 2


@dataclass(frozen=True)
class ExportTrade:
    trade_no: int
    family: str
    side: str
    entry_dt: pd.Timestamp
    exit_dt: pd.Timestamp
    entry_price: float
    exit_price: float
    qty: int
    pnl_usd: float
    mfe_usd: float
    mae_usd: float
    entry_signal: str
    exit_signal: str

    @property
    def gross_points(self) -> float:
        if self.side == "long":
            return self.exit_price - self.entry_price
        return self.entry_price - self.exit_price

    @property
    def duration_minutes(self) -> float:
        return (self.exit_dt - self.entry_dt).total_seconds() / 60.0


@dataclass(frozen=True)
class ClassicCandidate:
    family: str
    side: str
    signal_dt: pd.Timestamp
    entry_dt: pd.Timestamp
    orb_high: float
    orb_low: float
    orb_mid: float
    orb_range: float
    signal_close: float
    extension_pct: float


@dataclass(frozen=True)
class FVGSetup:
    family: str
    side: str
    breakout_dt: pd.Timestamp
    fvg_dt: pd.Timestamp
    selection_dt: pd.Timestamp
    entry_earliest_dt: pd.Timestamp
    entry_expiry_dt: pd.Timestamp
    orb_high: float
    orb_low: float
    fvg_bottom: float
    fvg_top: float
    entry_price: float
    natural_stop_price: float
    stop_price: float
    target_price: float
    risk_points: float
    fvg_size_points: float
    orb_distance_points: float


@dataclass(frozen=True)
class SimTrade:
    trade_no: int
    family: str
    side: str
    signal_dt: str
    entry_dt: str
    entry_bar_dt: str
    exit_dt: str
    exit_bar_dt: str
    entry_price: float
    exit_price: float
    stop_price: float | None
    target_price: float | None
    qty: int
    pnl_usd: float
    gross_points: float
    exit_signal: str
    setup_note: str


@dataclass(frozen=True)
class ExportDiagnostic:
    trade_no: int
    family: str
    side: str
    entry_dt: str
    exit_dt: str
    entry_signal: str
    exit_signal: str
    pnl_usd: float
    gross_points: float
    inferred_risk_points: float | None
    local_signal_dt: str | None
    local_model_match: bool
    model_note: str
    risk_error_points: float | None
    target_or_stop_error_points: float | None


def floor_5min(ts: pd.Timestamp) -> pd.Timestamp:
    return ts.floor("5min")


def read_export(path: Path) -> list[ExportTrade]:
    rows_by_trade: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows_by_trade[int(row["Trade #"])].append(row)

    trades: list[ExportTrade] = []
    for trade_no, rows in sorted(rows_by_trade.items()):
        entries = [row for row in rows if row["Type"].startswith("Entry")]
        exits = [row for row in rows if row["Type"].startswith("Exit")]
        if len(entries) != 1 or len(exits) != 1:
            raise ValueError(f"Trade {trade_no} is not a clean entry/exit pair")

        entry = entries[0]
        exit_ = exits[0]
        side = "long" if "long" in entry["Type"].lower() else "short"
        entry_signal = entry["Signal"]
        family = "fvg" if "FVG" in entry_signal else "classic"
        trades.append(
            ExportTrade(
                trade_no=trade_no,
                family=family,
                side=side,
                entry_dt=pd.Timestamp(entry["Date and time"]),
                exit_dt=pd.Timestamp(exit_["Date and time"]),
                entry_price=float(entry["Price USD"]),
                exit_price=float(exit_["Price USD"]),
                qty=int(float(entry["Size (qty)"])),
                pnl_usd=float(entry["Net P&L USD"]),
                mfe_usd=float(entry["Favorable excursion USD"]),
                mae_usd=float(entry["Adverse excursion USD"]),
                entry_signal=entry_signal,
                exit_signal=exit_["Signal"],
            )
        )
    return trades


def load_ohlcv(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        if "time" not in df.columns:
            raise ValueError(f"CSV {path} must contain a TradingView time column")
        df["datetime"] = (
            pd.to_datetime(df["time"], unit="s", utc=True)
            .dt.tz_convert("America/New_York")
            .dt.tz_localize(None)
        )
        df = df.sort_values("datetime").set_index("datetime")
        return df[(df.index >= start) & (df.index < end)]

    schema_names = pq.ParquetFile(path).schema.names
    if "datetime" in schema_names:
        table = pq.read_table(path, filters=[("datetime", ">=", start), ("datetime", "<", end)])
    else:
        table = pq.read_table(path)
    df = table.to_pandas()
    if df.empty:
        raise ValueError(f"No data loaded from {path} for {start} -> {end}")
    if "datetime" in df.columns:
        df = df.sort_values("datetime").set_index("datetime")
    else:
        df = df.sort_index()
    return df[(df.index >= start) & (df.index < end)]


def load_1s(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    return load_ohlcv(path, start, end)


def overlay_5m_frames(base: pd.DataFrame, overlays: Iterable[pd.DataFrame]) -> pd.DataFrame:
    frames = [base, *overlays]
    merged = pd.concat(frames, sort=False)
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()


def load_5m_from_1s_streaming(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Derive 5m bars from 1s parquet without loading the whole file at once."""
    parquet = pq.ParquetFile(path)
    datetime_col = parquet.schema.names.index("datetime")
    chunks: list[pd.DataFrame] = []
    for row_group_idx in range(parquet.num_row_groups):
        column = parquet.metadata.row_group(row_group_idx).column(datetime_col)
        stats = column.statistics
        if stats is not None and stats.has_min_max:
            if pd.Timestamp(stats.max) < start or pd.Timestamp(stats.min) >= end:
                continue
        table = parquet.read_row_group(row_group_idx)
        df = table.to_pandas()
        if "datetime" in df.columns:
            df = df.sort_values("datetime").set_index("datetime")
        else:
            df = df.sort_index()
        df = df[(df.index >= start) & (df.index < end)]
        if df.empty:
            continue
        chunks.append(resample_5m(df))

    if not chunks:
        raise ValueError(f"No 5m bars derived from {path} for {start} -> {end}")

    bars = pd.concat(chunks).sort_index()
    bars = (
        bars.groupby(level=0, sort=True)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    return bars


def resample_5m(df_1s: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1s.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


def iter_days(bars_5m: pd.DataFrame) -> Iterable[tuple[Any, pd.DataFrame]]:
    for day, group in bars_5m.groupby(bars_5m.index.date):
        yield day, group


def add_ut_bot_proxy(
    bars_5m: pd.DataFrame,
    *,
    key_value: float = FVG_UT_KEY_VALUE,
    atr_period: int = FVG_UT_ATR_PERIOD,
) -> pd.DataFrame:
    """Add a TradingView UT-Bot style trailing-stop direction.

    Gold-X captures UT state when an FVG is selected. This proxy follows the
    common Pine implementation using close as source, ATR RMA smoothing, and
    key-value * ATR as the trail distance.
    """
    bars = bars_5m.copy()
    prev_close = bars["close"].shift(1)
    true_range = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr = true_range.ewm(alpha=1.0 / atr_period, adjust=False, min_periods=atr_period).mean()

    stop_values: list[float] = []
    directions: list[int] = []
    prev_stop: float | None = None
    prev_src: float | None = None
    prev_direction = 0
    for src_value, atr_value in zip(bars["close"], atr):
        src = float(src_value)
        if pd.isna(atr_value):
            stop_values.append(float("nan"))
            directions.append(0)
            prev_src = src
            continue

        loss = float(key_value * atr_value)
        if prev_stop is None or pd.isna(prev_stop) or prev_src is None:
            stop = src - loss
        elif src > prev_stop and prev_src > prev_stop:
            stop = max(prev_stop, src - loss)
        elif src < prev_stop and prev_src < prev_stop:
            stop = min(prev_stop, src + loss)
        elif src > prev_stop:
            stop = src - loss
        else:
            stop = src + loss

        direction = prev_direction
        if prev_stop is not None and prev_src is not None:
            if prev_src < prev_stop and src > prev_stop:
                direction = 1
            elif prev_src > prev_stop and src < prev_stop:
                direction = -1
        if direction == 0:
            direction = 1 if src > stop else -1

        stop_values.append(stop)
        directions.append(direction)
        prev_stop = stop
        prev_src = src
        prev_direction = direction

    bars["ut_stop"] = stop_values
    bars["ut_direction"] = directions
    if "UT Bot Trail" in bars.columns:
        tv_trail = pd.to_numeric(bars["UT Bot Trail"], errors="coerce")
        tv_mask = tv_trail.notna()
        tv_direction = pd.Series(directions, index=bars.index, dtype="int64")
        tv_direction = tv_direction.mask(tv_mask & (bars["close"] > tv_trail), 1)
        tv_direction = tv_direction.mask(tv_mask & (bars["close"] < tv_trail), -1)
        bars.loc[tv_mask, "ut_stop"] = tv_trail.loc[tv_mask]
        bars.loc[tv_mask, "ut_direction"] = tv_direction.loc[tv_mask]
    return bars


def orb_for_day(group: pd.DataFrame) -> tuple[float, float, float, float] | None:
    orb = group.between_time(ORB_START, ORB_END_BAR)
    if len(orb) < 3:
        return None
    high = float(orb["high"].max())
    low = float(orb["low"].min())
    rng = high - low
    if rng <= 0:
        return None
    return high, low, (high + low) / 2.0, rng


def classic_quartile_stop(orb_high: float, orb_low: float, side: str) -> float:
    rng = orb_high - orb_low
    if side == "long":
        return orb_high - rng * 0.25
    return orb_low + rng * 0.25


def classic_hard_stop(orb_mid: float, side: str) -> float:
    if side == "long":
        return orb_mid - CLASSIC_HARD_STOP_BUFFER_POINTS
    return orb_mid + CLASSIC_HARD_STOP_BUFFER_POINTS


def classic_target(orb_high: float, orb_low: float, side: str) -> float:
    rng = orb_high - orb_low
    if side == "long":
        return orb_high + rng * CLASSIC_TARGET_SD
    return orb_low - rng * CLASSIC_TARGET_SD


def build_classic_candidates(
    bars_5m: pd.DataFrame,
    *,
    enable_overextension_filter: bool = True,
    enable_trend_proxy_filter: bool = False,
    enable_rg_filter: bool = False,
    enable_ema200_filter: bool = False,
    enable_ema9_cloud_filter: bool = False,
    enable_ema_cross_filter: bool = False,
    enable_tv_classic_shape_filter: bool = False,
    enable_squeeze_momentum_filter: bool = False,
    enable_wae_momentum_filter: bool = False,
    enable_divergence_filter: bool = False,
    ema_cross_hours: float = CLASSIC_EMA_CROSS_SENSITIVITY_HOURS,
    ema_cross_max_crosses: int = CLASSIC_EMA_CROSS_MAX_CROSSES,
    ema_cross_long_max_crosses: int | None = None,
    ema_cross_short_max_crosses: int | None = None,
    divergence_lookback: int = CLASSIC_DIVERGENCE_LOOKBACK,
) -> list[ClassicCandidate]:
    candidates: list[ClassicCandidate] = []
    needs_filter_columns = (
        enable_trend_proxy_filter
        or enable_rg_filter
        or enable_ema200_filter
        or enable_ema9_cloud_filter
        or enable_ema_cross_filter
        or enable_squeeze_momentum_filter
        or enable_wae_momentum_filter
        or enable_divergence_filter
    )
    source = (
        add_classic_filter_columns(
            bars_5m,
            ema_cross_hours=ema_cross_hours,
            divergence_lookback=divergence_lookback,
        )
        if needs_filter_columns
        else bars_5m
    )
    for day, group in iter_days(source):
        if pd.Timestamp(day).weekday() not in CLASSIC_WEEKDAYS:
            continue
        orb = orb_for_day(group)
        if orb is None:
            continue
        orb_high, orb_low, orb_mid, orb_range = orb

        signals = group.between_time(CLASSIC_SIGNAL_START, CLASSIC_SIGNAL_END)
        for signal_dt, row in signals.iterrows():
            pos = group.index.get_loc(signal_dt)
            if pos == 0:
                continue
            previous_close = float(group.iloc[pos - 1]["close"])
            sides: list[str] = []
            if float(row["close"]) > orb_high and previous_close <= orb_high:
                sides.append("long")
            if float(row["close"]) < orb_low and previous_close >= orb_low:
                sides.append("short")
            for side in sides:
                extension = (
                    (float(row["close"]) - orb_high) / orb_range * 100.0
                    if side == "long"
                    else (orb_low - float(row["close"])) / orb_range * 100.0
                )
                if enable_overextension_filter and extension > CLASSIC_OVEREXTENSION_MAX_PCT:
                    continue
                if enable_trend_proxy_filter and not classic_trend_proxy_pass(row, side):
                    continue
                if enable_rg_filter and not classic_rg_pass(row, side):
                    continue
                if enable_ema200_filter and not classic_ema200_pass(row, side):
                    continue
                if enable_ema9_cloud_filter and not classic_ema9_cloud_pass(row, side):
                    continue
                if enable_ema_cross_filter and not classic_ema_cross_pass(
                    row,
                    side,
                    ema_cross_max_crosses=ema_cross_max_crosses,
                    ema_cross_long_max_crosses=ema_cross_long_max_crosses,
                    ema_cross_short_max_crosses=ema_cross_short_max_crosses,
                ):
                    continue
                if enable_squeeze_momentum_filter and not classic_squeeze_momentum_pass(row, side):
                    continue
                if enable_wae_momentum_filter and not classic_wae_momentum_pass(row, side):
                    continue
                if enable_divergence_filter and not classic_divergence_pass(row, side):
                    continue
                if enable_tv_classic_shape_filter:
                    marker_col = "Shapes" if side == "long" else "Shapes.1"
                    marker_value = row.get(marker_col)
                    row_has_tv_markers = any(
                        _finite(row.get(column))
                        for column in ("Shapes", "Shapes.1")
                    )
                    if row_has_tv_markers and (not _finite(marker_value) or float(marker_value) == 0.0):
                        continue
                candidates.append(
                    ClassicCandidate(
                        family="classic",
                        side=side,
                        signal_dt=signal_dt,
                        entry_dt=signal_dt + pd.Timedelta(minutes=5),
                        orb_high=orb_high,
                        orb_low=orb_low,
                        orb_mid=orb_mid,
                        orb_range=orb_range,
                        signal_close=float(row["close"]),
                        extension_pct=extension,
                    )
                )
    return candidates


def add_classic_filter_columns(
    bars_5m: pd.DataFrame,
    *,
    ema_cross_hours: float = CLASSIC_EMA_CROSS_SENSITIVITY_HOURS,
    divergence_lookback: int = CLASSIC_DIVERGENCE_LOOKBACK,
) -> pd.DataFrame:
    """Add visible-guide Classic filter proxies.

    The exact Gold-X internals are private. These columns model the named
    filters from the settings guide with deterministic, point-in-time 5m values.
    """
    bars = bars_5m.copy()
    bars["classic_rg_filter"], bars["classic_rg_direction"] = range_filter_direction(
        bars["close"],
        period=CLASSIC_RG_PERIOD,
        multiplier=CLASSIC_RG_MULT,
    )
    if "Plot" in bars.columns:
        tv_rg_filter = pd.to_numeric(bars["Plot"], errors="coerce")
        tv_rg_mask = tv_rg_filter.notna()
        tv_rg_delta = tv_rg_filter.diff()
        tv_rg_step = pd.Series(pd.NA, index=bars.index, dtype="Float64")
        tv_rg_step = tv_rg_step.mask(tv_rg_delta > 0, 1).mask(tv_rg_delta < 0, -1)
        tv_rg_direction = tv_rg_step.ffill()
        fallback_direction = pd.Series(bars["classic_rg_direction"], index=bars.index)
        tv_rg_direction = tv_rg_direction.fillna(fallback_direction).fillna(0).astype("int64")
        bars.loc[tv_rg_mask, "classic_rg_filter"] = tv_rg_filter.loc[tv_rg_mask]
        bars.loc[tv_rg_mask, "classic_rg_direction"] = tv_rg_direction.loc[tv_rg_mask]
    bars["classic_trend_fast_ema"] = bars["close"].ewm(
        span=CLASSIC_TREND_FAST_EMA,
        adjust=False,
        min_periods=CLASSIC_TREND_FAST_EMA,
    ).mean()
    bars["classic_trend_slow_ema"] = bars["close"].ewm(
        span=CLASSIC_TREND_SLOW_EMA,
        adjust=False,
        min_periods=CLASSIC_TREND_SLOW_EMA,
    ).mean()
    highest = bars["high"].rolling(CLASSIC_SQUEEZE_LENGTH, min_periods=CLASSIC_SQUEEZE_LENGTH).max()
    lowest = bars["low"].rolling(CLASSIC_SQUEEZE_LENGTH, min_periods=CLASSIC_SQUEEZE_LENGTH).min()
    close_sma = bars["close"].rolling(CLASSIC_SQUEEZE_LENGTH, min_periods=CLASSIC_SQUEEZE_LENGTH).mean()
    squeeze_source = bars["close"] - (((highest + lowest) / 2.0 + close_sma) / 2.0)
    bars["classic_squeeze_momentum"] = rolling_linreg_last(squeeze_source, CLASSIC_SQUEEZE_LENGTH)
    prior_high = bars["high"].shift(1).rolling(divergence_lookback, min_periods=divergence_lookback).max()
    prior_low = bars["low"].shift(1).rolling(divergence_lookback, min_periods=divergence_lookback).min()
    prior_momentum_high = (
        bars["classic_squeeze_momentum"]
        .shift(1)
        .rolling(divergence_lookback, min_periods=divergence_lookback)
        .max()
    )
    prior_momentum_low = (
        bars["classic_squeeze_momentum"]
        .shift(1)
        .rolling(divergence_lookback, min_periods=divergence_lookback)
        .min()
    )
    bars["classic_bearish_divergence"] = (bars["high"] >= prior_high) & (
        bars["classic_squeeze_momentum"] < prior_momentum_high
    )
    bars["classic_bullish_divergence"] = (bars["low"] <= prior_low) & (
        bars["classic_squeeze_momentum"] > prior_momentum_low
    )
    momentum_fast = bars["close"].ewm(
        span=CLASSIC_MOMENTUM_FAST_EMA,
        adjust=False,
        min_periods=CLASSIC_MOMENTUM_FAST_EMA,
    ).mean()
    momentum_slow = bars["close"].ewm(
        span=CLASSIC_MOMENTUM_SLOW_EMA,
        adjust=False,
        min_periods=CLASSIC_MOMENTUM_SLOW_EMA,
    ).mean()
    bars["classic_wae_momentum"] = (momentum_fast - momentum_slow).diff() * CLASSIC_MOMENTUM_SENSITIVITY
    bars["classic_ema200"] = bars["close"].ewm(
        span=CLASSIC_EMA_FILTER_LENGTH,
        adjust=False,
        min_periods=CLASSIC_EMA_FILTER_LENGTH,
    ).mean()
    bars["classic_ema9_high"] = bars["high"].ewm(
        span=CLASSIC_EMA_CLOUD_PERIOD,
        adjust=False,
        min_periods=CLASSIC_EMA_CLOUD_PERIOD,
    ).mean()
    bars["classic_ema9_close"] = bars["close"].ewm(
        span=CLASSIC_EMA_CLOUD_PERIOD,
        adjust=False,
        min_periods=CLASSIC_EMA_CLOUD_PERIOD,
    ).mean()

    side_vs_ema200 = pd.Series(0, index=bars.index, dtype="int64")
    side_vs_ema200 = side_vs_ema200.mask(bars["close"] > bars["classic_ema200"], 1)
    side_vs_ema200 = side_vs_ema200.mask(bars["close"] < bars["classic_ema200"], -1)
    prev_side = side_vs_ema200.shift(1)
    crosses = (side_vs_ema200 != prev_side) & (side_vs_ema200 != 0) & (prev_side != 0)
    lookback_bars = max(1, int(round(ema_cross_hours * 60.0 / 5.0)))
    bars["classic_ema200_cross_count"] = crosses.rolling(lookback_bars, min_periods=1).sum()
    return bars


def rolling_linreg_last(series: pd.Series, length: int) -> pd.Series:
    """TradingView-style linreg value at the end of each rolling window."""
    x = np.arange(length, dtype=float)
    sum_x = float(x.sum())
    sum_x2 = float((x * x).sum())
    denominator = length * sum_x2 - sum_x * sum_x
    sum_y = series.rolling(length, min_periods=length).sum()
    sum_xy = series.rolling(length, min_periods=length).apply(lambda values: float(np.dot(x, values)), raw=True)
    slope = (length * sum_xy - sum_x * sum_y) / denominator
    intercept = (sum_y - slope * sum_x) / length
    return intercept + slope * (length - 1)


def range_filter_direction(
    close: pd.Series,
    *,
    period: int,
    multiplier: float,
) -> tuple[list[float], list[int]]:
    """Approximate the common TradingView Range Filter direction."""
    abs_change = close.diff().abs()
    avg_range = abs_change.ewm(span=period, adjust=False, min_periods=period).mean()
    smooth_range = avg_range.ewm(span=period * 2 - 1, adjust=False, min_periods=period * 2 - 1).mean() * multiplier

    filter_values: list[float] = []
    directions: list[int] = []
    prev_filter: float | None = None
    prev_direction = 0
    for close_value, range_value in zip(close, smooth_range):
        price = float(close_value)
        if pd.isna(range_value):
            filter_values.append(float("nan"))
            directions.append(0)
            continue

        if prev_filter is None or pd.isna(prev_filter):
            current_filter = price
        elif price > prev_filter:
            current_filter = max(prev_filter, price - float(range_value))
        else:
            current_filter = min(prev_filter, price + float(range_value))

        direction = prev_direction
        if prev_filter is not None and not pd.isna(prev_filter):
            if current_filter > prev_filter:
                direction = 1
            elif current_filter < prev_filter:
                direction = -1
        if direction == 0:
            direction = 1 if price >= current_filter else -1

        filter_values.append(current_filter)
        directions.append(direction)
        prev_filter = current_filter
        prev_direction = direction
    return filter_values, directions


def _finite(value: Any) -> bool:
    return value is not None and not pd.isna(value)


def classic_trend_proxy_pass(row: pd.Series, side: str) -> bool:
    fast = row.get("classic_trend_fast_ema")
    slow = row.get("classic_trend_slow_ema")
    if not _finite(fast) or not _finite(slow):
        return False
    if side == "long":
        return float(fast) > float(slow)
    return float(fast) < float(slow)


def classic_rg_pass(row: pd.Series, side: str) -> bool:
    rg_filter = row.get("classic_rg_filter")
    rg_direction = row.get("classic_rg_direction")
    if not _finite(rg_filter) or not _finite(rg_direction):
        return False
    if side == "long":
        return int(rg_direction) > 0 and float(row["close"]) >= float(rg_filter)
    return int(rg_direction) < 0 and float(row["close"]) <= float(rg_filter)


def classic_ema200_pass(row: pd.Series, side: str) -> bool:
    ema200 = row.get("classic_ema200")
    if not _finite(ema200):
        return False
    if side == "long":
        return float(row["close"]) > float(ema200)
    return float(row["close"]) < float(ema200)


def classic_ema9_cloud_pass(row: pd.Series, side: str) -> bool:
    ema9_high = row.get("classic_ema9_high")
    ema9_close = row.get("classic_ema9_close")
    if not _finite(ema9_high) or not _finite(ema9_close):
        return False
    if side == "long":
        return float(row["close"]) > float(ema9_high)
    return float(row["close"]) < float(ema9_close)


def classic_ema_cross_pass(
    row: pd.Series,
    side: str,
    *,
    ema_cross_max_crosses: int,
    ema_cross_long_max_crosses: int | None = None,
    ema_cross_short_max_crosses: int | None = None,
) -> bool:
    cross_count = row.get("classic_ema200_cross_count")
    if not _finite(cross_count):
        return False
    side_cap = (
        ema_cross_long_max_crosses
        if side == "long" and ema_cross_long_max_crosses is not None
        else ema_cross_short_max_crosses
        if side == "short" and ema_cross_short_max_crosses is not None
        else ema_cross_max_crosses
    )
    return int(cross_count) <= side_cap


def classic_squeeze_momentum_pass(row: pd.Series, side: str) -> bool:
    momentum = row.get("classic_squeeze_momentum")
    if not _finite(momentum):
        return False
    if side == "long":
        return float(momentum) > 0.0
    return float(momentum) < 0.0


def classic_wae_momentum_pass(row: pd.Series, side: str) -> bool:
    momentum = row.get("classic_wae_momentum")
    if not _finite(momentum):
        return False
    if side == "long":
        return float(momentum) > 0.0
    return float(momentum) < 0.0


def classic_divergence_pass(row: pd.Series, side: str) -> bool:
    if side == "long":
        bearish = row.get("classic_bearish_divergence")
        return False if _finite(bearish) and bool(bearish) else True
    bullish = row.get("classic_bullish_divergence")
    return False if _finite(bullish) and bool(bullish) else True


def detect_fvg_at(group: pd.DataFrame, pos: int, side: str) -> tuple[float, float, float, float] | None:
    if pos < 2 or pos >= len(group):
        return None
    before = group.iloc[pos - 2]
    impulse = group.iloc[pos - 1]
    after = group.iloc[pos]
    if side == "long":
        if float(before["high"]) >= float(after["low"]):
            return None
        bottom = float(before["high"])
        top = float(after["low"])
        entry = top
        stop = float(impulse["low"])
    else:
        if float(before["low"]) <= float(after["high"]):
            return None
        top = float(before["low"])
        bottom = float(after["high"])
        entry = bottom
        stop = float(impulse["high"])
    return bottom, top, entry, stop


def make_fvg_setup(
    group: pd.DataFrame,
    breakout_pos: int,
    fvg_pos: int,
    side: str,
    orb_high: float,
    orb_low: float,
) -> FVGSetup | None:
    detected = detect_fvg_at(group, fvg_pos, side)
    if detected is None:
        return None
    bottom, top, entry, natural_stop = detected
    size = top - bottom
    if size < FVG_MIN_SIZE_POINTS or size > FVG_MAX_SIZE_POINTS:
        return None

    boundary = orb_high if side == "long" else orb_low
    distance = min(abs(bottom - boundary), abs(top - boundary))
    if distance > FVG_MAX_ORB_DISTANCE_POINTS:
        return None

    if side == "long":
        risk = entry - natural_stop
        stop = natural_stop if risk >= FVG_MIN_STOP_POINTS else entry - FVG_MIN_STOP_POINTS
        risk = entry - stop
        target = entry + risk * FVG_TARGET_RR
    else:
        risk = natural_stop - entry
        stop = natural_stop if risk >= FVG_MIN_STOP_POINTS else entry + FVG_MIN_STOP_POINTS
        risk = stop - entry
        target = entry - risk * FVG_TARGET_RR
    if risk <= 0:
        return None

    breakout_dt = group.index[breakout_pos]
    fvg_dt = group.index[fvg_pos]
    selection_dt = max(breakout_dt, fvg_dt)
    entry_earliest = selection_dt + pd.Timedelta(minutes=5)
    expiry_by_bars = entry_earliest + pd.Timedelta(minutes=FVG_MAX_WAIT_BARS * 5)
    expiry_by_time = selection_dt + pd.Timedelta(minutes=FVG_MAX_WAIT_MINUTES)

    return FVGSetup(
        family="fvg",
        side=side,
        breakout_dt=breakout_dt,
        fvg_dt=fvg_dt,
        selection_dt=selection_dt,
        entry_earliest_dt=entry_earliest,
        entry_expiry_dt=min(expiry_by_bars, expiry_by_time),
        orb_high=orb_high,
        orb_low=orb_low,
        fvg_bottom=bottom,
        fvg_top=top,
        entry_price=entry,
        natural_stop_price=natural_stop,
        stop_price=stop,
        target_price=target,
        risk_points=risk,
        fvg_size_points=size,
        orb_distance_points=distance,
    )


def build_fvg_setups(
    bars_5m: pd.DataFrame,
    *,
    enable_ut_filter: bool = False,
    first_setup_per_breakout: bool = False,
    enable_tv_fvg_shape_filter: bool = False,
) -> list[FVGSetup]:
    setups: list[FVGSetup] = []
    seen: set[tuple[str, pd.Timestamp, pd.Timestamp]] = set()
    source = add_ut_bot_proxy(bars_5m) if enable_ut_filter else bars_5m

    for day, group in iter_days(source):
        if pd.Timestamp(day).weekday() not in FVG_WEEKDAYS:
            continue
        orb = orb_for_day(group)
        if orb is None:
            continue
        orb_high, orb_low, _, _ = orb

        signal_bars = group.between_time(FVG_BREAKOUT_START, FVG_BREAKOUT_END)
        for breakout_dt, row in signal_bars.iterrows():
            breakout_pos = group.index.get_loc(breakout_dt)
            if breakout_pos == 0:
                continue
            previous_close = float(group.iloc[breakout_pos - 1]["close"])
            sides: list[str] = []
            if float(row["close"]) > orb_high and previous_close <= orb_high:
                sides.append("long")
            if float(row["close"]) < orb_low and previous_close >= orb_low:
                sides.append("short")

            for side in sides:
                start = max(2, breakout_pos - FVG_BARS_BEFORE)
                end = min(len(group) - 1, breakout_pos + FVG_BARS_AFTER)
                for fvg_pos in range(start, end + 1):
                    setup = make_fvg_setup(group, breakout_pos, fvg_pos, side, orb_high, orb_low)
                    if setup is None:
                        continue
                    if enable_tv_fvg_shape_filter:
                        marker_col = "Shapes.2" if side == "long" else "Shapes.3"
                        marker_row = group.iloc[fvg_pos]
                        marker_value = marker_row.get(marker_col)
                        row_has_tv_markers = any(
                            _finite(marker_row.get(column))
                            for column in ("Shapes.2", "Shapes.3")
                        )
                        if row_has_tv_markers and (not _finite(marker_value) or float(marker_value) == 0.0):
                            continue
                    if enable_ut_filter:
                        selection_row = group.loc[setup.selection_dt]
                        ut_direction = int(selection_row.get("ut_direction", 0) or 0)
                        if side == "long" and ut_direction != 1:
                            continue
                        if side == "short" and ut_direction != -1:
                            continue
                    key = (setup.side, setup.fvg_dt, setup.selection_dt)
                    if key in seen:
                        continue
                    seen.add(key)
                    setups.append(setup)
                    if first_setup_per_breakout:
                        break
    return sorted(setups, key=lambda item: (item.entry_earliest_dt, item.side, item.fvg_dt))


def find_fvg_fill(setup: FVGSetup, df_1s: pd.DataFrame) -> pd.Timestamp | None:
    scan = df_1s.loc[setup.entry_earliest_dt : setup.entry_expiry_dt]
    if scan.empty:
        return None
    if setup.side == "long":
        hits = scan[scan["low"] <= setup.entry_price]
    else:
        hits = scan[scan["high"] >= setup.entry_price]
    if hits.empty:
        return None
    return pd.Timestamp(hits.index[0])


def pnl_from_points(points: float, qty: int, point_value: float, commission: float) -> float:
    return points * point_value * qty - commission * qty


def simulate_classic_exit(
    candidate: ClassicCandidate,
    df_1s: pd.DataFrame,
    bars_5m: pd.DataFrame,
    trade_no: int,
    *,
    point_value: float,
    commission: float,
    qty: int = 1,
    intrabar_rows: bool = True,
) -> SimTrade | None:
    if candidate.entry_dt not in df_1s.index:
        start_slice = df_1s.loc[candidate.entry_dt : candidate.entry_dt + pd.Timedelta(minutes=5)]
        if start_slice.empty:
            return None
        entry_dt = pd.Timestamp(start_slice.index[0])
    else:
        entry_dt = candidate.entry_dt

    entry_price = float(df_1s.loc[entry_dt]["open"])
    target = classic_target(candidate.orb_high, candidate.orb_low, candidate.side)
    hard_stop = classic_hard_stop(candidate.orb_mid, candidate.side)
    quartile_stop = classic_quartile_stop(candidate.orb_high, candidate.orb_low, candidate.side)
    cutoff = entry_dt + pd.Timedelta(minutes=CLASSIC_MAX_HOLD_MINUTES)

    scan = df_1s.loc[entry_dt : cutoff + pd.Timedelta(minutes=10)]
    if scan.empty:
        return None

    exit_dt = pd.Timestamp(scan.index[-1])
    exit_price = float(scan.iloc[-1]["close"])
    exit_signal = "Max Hold Time (180m)"

    five_minute_closes = bars_5m.loc[floor_5min(entry_dt) : cutoff + pd.Timedelta(minutes=5)]
    close_exit_by_bar: dict[pd.Timestamp, tuple[pd.Timestamp, float]] = {}
    for bar_dt, row in five_minute_closes.iterrows():
        if bar_dt < floor_5min(entry_dt):
            continue
        close_dt = bar_dt + pd.Timedelta(minutes=5)
        if close_dt <= entry_dt:
            continue
        close_price = float(row["close"])
        if candidate.side == "long" and close_price <= quartile_stop:
            close_exit_by_bar[bar_dt] = (close_dt, close_price)
        elif candidate.side == "short" and close_price >= quartile_stop:
            close_exit_by_bar[bar_dt] = (close_dt, close_price)

    if not intrabar_rows:
        for ts, row in scan.iterrows():
            bar_dt = pd.Timestamp(ts)
            if candidate.side == "long":
                hit_target = float(row["high"]) >= target
                hit_hard_stop = float(row["low"]) <= hard_stop
            else:
                hit_target = float(row["low"]) <= target
                hit_hard_stop = float(row["high"]) >= hard_stop

            if hit_target or hit_hard_stop:
                exit_dt = bar_dt
                if hit_hard_stop and hit_target:
                    exit_price = hard_stop
                    exit_signal = "SL Q1" if candidate.side == "long" else "SL Q4"
                elif hit_hard_stop:
                    exit_price = hard_stop
                    exit_signal = "SL Q1" if candidate.side == "long" else "SL Q4"
                else:
                    exit_price = target
                    exit_signal = "TP SD1.0"
                break

            close_exit = close_exit_by_bar.get(bar_dt)
            if close_exit is not None:
                exit_dt, exit_price = close_exit
                exit_signal = "SL Q1" if candidate.side == "long" else "SL Q4"
                break

            if bar_dt >= cutoff:
                exit_dt = bar_dt + pd.Timedelta(minutes=5)
                exit_price = float(row["close"])
                exit_signal = "Max Hold Time (180m)"
                break

        gross_points = exit_price - entry_price if candidate.side == "long" else entry_price - exit_price
        pnl = pnl_from_points(gross_points, qty, point_value, commission)
        return SimTrade(
            trade_no=trade_no,
            family="classic",
            side=candidate.side,
            signal_dt=str(candidate.signal_dt),
            entry_dt=str(entry_dt),
            entry_bar_dt=str(floor_5min(entry_dt)),
            exit_dt=str(exit_dt),
            exit_bar_dt=str(floor_5min(exit_dt)),
            entry_price=round(entry_price, 2),
            exit_price=round(exit_price, 2),
            stop_price=round(hard_stop, 2),
            target_price=round(target, 2),
            qty=qty,
            pnl_usd=round(pnl, 2),
            gross_points=round(gross_points, 2),
            exit_signal=exit_signal,
            setup_note=f"ext={candidate.extension_pct:.2f}",
        )

    for ts, row in scan.iterrows():
        if candidate.side == "long":
            hit_target = float(row["high"]) >= target
            hit_hard_stop = float(row["low"]) <= hard_stop
        else:
            hit_target = float(row["low"]) <= target
            hit_hard_stop = float(row["high"]) >= hard_stop

        if hit_target or hit_hard_stop:
            exit_dt = pd.Timestamp(ts)
            if hit_hard_stop and hit_target:
                exit_price = hard_stop
                exit_signal = "SL Q1" if candidate.side == "long" else "SL Q4"
            elif hit_hard_stop:
                exit_price = hard_stop
                exit_signal = "SL Q1" if candidate.side == "long" else "SL Q4"
            else:
                exit_price = target
                exit_signal = "TP SD1.0"
            break

        bar_dt = floor_5min(pd.Timestamp(ts))
        if ts >= bar_dt + pd.Timedelta(minutes=5) - pd.Timedelta(seconds=1):
            close_exit = close_exit_by_bar.get(bar_dt)
            if close_exit is not None:
                exit_dt, exit_price = close_exit
                exit_signal = "SL Q1" if candidate.side == "long" else "SL Q4"
                break

        if pd.Timestamp(ts) >= cutoff:
            exit_dt = pd.Timestamp(ts)
            exit_price = float(row["close"])
            exit_signal = "Max Hold Time (180m)"
            break

    gross_points = exit_price - entry_price if candidate.side == "long" else entry_price - exit_price
    pnl = pnl_from_points(gross_points, qty, point_value, commission)
    return SimTrade(
        trade_no=trade_no,
        family="classic",
        side=candidate.side,
        signal_dt=str(candidate.signal_dt),
        entry_dt=str(entry_dt),
        entry_bar_dt=str(floor_5min(entry_dt)),
        exit_dt=str(exit_dt),
        exit_bar_dt=str(floor_5min(exit_dt)),
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        stop_price=round(hard_stop, 2),
        target_price=round(target, 2),
        qty=qty,
        pnl_usd=round(pnl, 2),
        gross_points=round(gross_points, 2),
        exit_signal=exit_signal,
        setup_note=f"ext={candidate.extension_pct:.2f}",
    )


def simulate_fvg_exit(
    setup: FVGSetup,
    fill_dt: pd.Timestamp,
    df_1s: pd.DataFrame,
    trade_no: int,
    *,
    point_value: float,
    commission: float,
    qty: int = 1,
    intrabar_rows: bool = True,
) -> SimTrade | None:
    cutoff = fill_dt + pd.Timedelta(minutes=FVG_MAX_HOLD_MINUTES)
    scan = df_1s.loc[fill_dt : cutoff + pd.Timedelta(minutes=10)]
    if scan.empty:
        return None

    exit_dt = pd.Timestamp(scan.index[-1])
    exit_price = float(scan.iloc[-1]["close"])
    exit_signal = "Max Hold Time (270m)"

    if not intrabar_rows:
        for ts, row in scan.iterrows():
            bar_dt = pd.Timestamp(ts)
            if setup.side == "long":
                hit_stop = float(row["low"]) <= setup.stop_price
                hit_target = float(row["high"]) >= setup.target_price
            else:
                hit_stop = float(row["high"]) >= setup.stop_price
                hit_target = float(row["low"]) <= setup.target_price
            if hit_stop or hit_target:
                exit_dt = bar_dt
                if hit_stop and hit_target:
                    exit_price = setup.stop_price
                elif hit_stop:
                    exit_price = setup.stop_price
                else:
                    exit_price = setup.target_price
                exit_signal = "FVG Main Exit"
                break
            if bar_dt >= cutoff:
                exit_dt = bar_dt + pd.Timedelta(minutes=5)
                exit_price = float(row["close"])
                exit_signal = "Max Hold Time (270m)"
                break

        gross_points = exit_price - setup.entry_price if setup.side == "long" else setup.entry_price - exit_price
        pnl = pnl_from_points(gross_points, qty, point_value, commission)
        return SimTrade(
            trade_no=trade_no,
            family="fvg",
            side=setup.side,
            signal_dt=str(setup.selection_dt),
            entry_dt=str(fill_dt),
            entry_bar_dt=str(floor_5min(fill_dt)),
            exit_dt=str(exit_dt),
            exit_bar_dt=str(floor_5min(exit_dt)),
            entry_price=round(setup.entry_price, 2),
            exit_price=round(exit_price, 2),
            stop_price=round(setup.stop_price, 2),
            target_price=round(setup.target_price, 2),
            qty=qty,
            pnl_usd=round(pnl, 2),
            gross_points=round(gross_points, 2),
            exit_signal=exit_signal,
            setup_note=(
                f"breakout={setup.breakout_dt}, fvg={setup.fvg_dt}, "
                f"size={setup.fvg_size_points:.2f}, risk={setup.risk_points:.2f}"
            ),
        )

    for ts, row in scan.iterrows():
        if setup.side == "long":
            hit_stop = float(row["low"]) <= setup.stop_price
            hit_target = float(row["high"]) >= setup.target_price
        else:
            hit_stop = float(row["high"]) >= setup.stop_price
            hit_target = float(row["low"]) <= setup.target_price
        if hit_stop or hit_target:
            exit_dt = pd.Timestamp(ts)
            if hit_stop and hit_target:
                exit_price = setup.stop_price
            elif hit_stop:
                exit_price = setup.stop_price
            else:
                exit_price = setup.target_price
            exit_signal = "FVG Main Exit"
            break
        if pd.Timestamp(ts) >= cutoff:
            exit_dt = pd.Timestamp(ts)
            exit_price = float(row["close"])
            exit_signal = "Max Hold Time (270m)"
            break

    gross_points = exit_price - setup.entry_price if setup.side == "long" else setup.entry_price - exit_price
    pnl = pnl_from_points(gross_points, qty, point_value, commission)
    return SimTrade(
        trade_no=trade_no,
        family="fvg",
        side=setup.side,
        signal_dt=str(setup.selection_dt),
        entry_dt=str(fill_dt),
        entry_bar_dt=str(floor_5min(fill_dt)),
        exit_dt=str(exit_dt),
        exit_bar_dt=str(floor_5min(exit_dt)),
        entry_price=round(setup.entry_price, 2),
        exit_price=round(exit_price, 2),
        stop_price=round(setup.stop_price, 2),
        target_price=round(setup.target_price, 2),
        qty=qty,
        pnl_usd=round(pnl, 2),
        gross_points=round(gross_points, 2),
        exit_signal=exit_signal,
        setup_note=(
            f"breakout={setup.breakout_dt}, fvg={setup.fvg_dt}, "
            f"size={setup.fvg_size_points:.2f}, risk={setup.risk_points:.2f}"
        ),
    )


def run_core_replication(
    df_exec: pd.DataFrame,
    *,
    bars_5m: pd.DataFrame | None = None,
    intrabar_rows: bool = True,
    point_value: float = DEFAULT_POINT_VALUE,
    commission: float = DEFAULT_ROUND_TRIP_COMMISSION,
    enable_classic_overextension_filter: bool = True,
    enable_classic_trend_proxy_filter: bool = False,
    enable_classic_rg_filter: bool = False,
    enable_classic_ema200_filter: bool = False,
    enable_classic_ema9_cloud_filter: bool = False,
    enable_classic_ema_cross_filter: bool = False,
    enable_classic_tv_shape_filter: bool = False,
    enable_classic_squeeze_momentum_filter: bool = False,
    enable_classic_wae_momentum_filter: bool = False,
    enable_classic_divergence_filter: bool = False,
    classic_ema_cross_hours: float = CLASSIC_EMA_CROSS_SENSITIVITY_HOURS,
    classic_ema_cross_max_crosses: int = CLASSIC_EMA_CROSS_MAX_CROSSES,
    classic_ema_cross_long_max_crosses: int | None = None,
    classic_ema_cross_short_max_crosses: int | None = None,
    classic_divergence_lookback: int = CLASSIC_DIVERGENCE_LOOKBACK,
    enable_fvg_ut_filter: bool = False,
    enable_fvg_first_setup_per_breakout: bool = False,
    enable_fvg_tv_shape_filter: bool = False,
    fvg_after_classic_cooldown_minutes: float = 0.0,
    fvg_after_classic_exit_cooldown_minutes: float = 0.0,
) -> tuple[list[SimTrade], dict[str, Any]]:
    if bars_5m is None:
        bars_5m = resample_5m(df_exec) if intrabar_rows else df_exec
    classic_candidates = build_classic_candidates(
        bars_5m,
        enable_overextension_filter=enable_classic_overextension_filter,
        enable_trend_proxy_filter=enable_classic_trend_proxy_filter,
        enable_rg_filter=enable_classic_rg_filter,
        enable_ema200_filter=enable_classic_ema200_filter,
        enable_ema9_cloud_filter=enable_classic_ema9_cloud_filter,
        enable_ema_cross_filter=enable_classic_ema_cross_filter,
        enable_tv_classic_shape_filter=enable_classic_tv_shape_filter,
        enable_squeeze_momentum_filter=enable_classic_squeeze_momentum_filter,
        enable_wae_momentum_filter=enable_classic_wae_momentum_filter,
        enable_divergence_filter=enable_classic_divergence_filter,
        ema_cross_hours=classic_ema_cross_hours,
        ema_cross_max_crosses=classic_ema_cross_max_crosses,
        ema_cross_long_max_crosses=classic_ema_cross_long_max_crosses,
        ema_cross_short_max_crosses=classic_ema_cross_short_max_crosses,
        divergence_lookback=classic_divergence_lookback,
    )
    fvg_setups = build_fvg_setups(
        bars_5m,
        enable_ut_filter=enable_fvg_ut_filter,
        first_setup_per_breakout=enable_fvg_first_setup_per_breakout,
        enable_tv_fvg_shape_filter=enable_fvg_tv_shape_filter,
    )

    candidate_events: list[tuple[pd.Timestamp, int, Any, pd.Timestamp | None]] = []
    for candidate in classic_candidates:
        candidate_events.append((candidate.entry_dt, 0, candidate, None))
    fills_by_setup: dict[FVGSetup, pd.Timestamp | None] = {}
    for setup in fvg_setups:
        fill_dt = find_fvg_fill(setup, df_exec)
        fills_by_setup[setup] = fill_dt
        if fill_dt is not None:
            candidate_events.append((fill_dt, 1, setup, fill_dt))

    candidate_events.sort(key=lambda item: (item[0], item[1]))

    trades: list[SimTrade] = []
    trade_no = 1
    open_until: pd.Timestamp | None = None
    last_classic_entry: pd.Timestamp | None = None
    last_classic_exit: pd.Timestamp | None = None
    last_fvg_selection: pd.Timestamp | None = None

    for event_dt, _, candidate, fill_dt in candidate_events:
        if open_until is not None and event_dt <= open_until:
            continue
        if isinstance(candidate, ClassicCandidate):
            if last_classic_entry is not None:
                minutes = (candidate.entry_dt - last_classic_entry).total_seconds() / 60.0
                if minutes < CLASSIC_COOLDOWN_MINUTES:
                    continue
            trade = simulate_classic_exit(
                candidate,
                df_exec,
                bars_5m,
                trade_no,
                point_value=point_value,
                commission=commission,
                intrabar_rows=intrabar_rows,
            )
            if trade is None:
                continue
            last_classic_entry = pd.Timestamp(trade.entry_dt)
            last_classic_exit = pd.Timestamp(trade.exit_dt)
        else:
            assert isinstance(candidate, FVGSetup)
            assert fill_dt is not None
            if fvg_after_classic_cooldown_minutes > 0 and last_classic_entry is not None:
                minutes = (candidate.selection_dt - last_classic_entry).total_seconds() / 60.0
                if 0 <= minutes < fvg_after_classic_cooldown_minutes:
                    continue
            if fvg_after_classic_exit_cooldown_minutes > 0 and last_classic_exit is not None:
                minutes = (candidate.selection_dt - last_classic_exit).total_seconds() / 60.0
                if 0 <= minutes < fvg_after_classic_exit_cooldown_minutes:
                    continue
            if last_fvg_selection is not None:
                minutes = (candidate.selection_dt - last_fvg_selection).total_seconds() / 60.0
                if minutes < FVG_SELECTION_COOLDOWN_MINUTES:
                    continue
            trade = simulate_fvg_exit(
                candidate,
                fill_dt,
                df_exec,
                trade_no,
                point_value=point_value,
                commission=commission,
                intrabar_rows=intrabar_rows,
            )
            if trade is None:
                continue
            last_fvg_selection = candidate.selection_dt

        trades.append(trade)
        trade_no += 1
        open_until = pd.Timestamp(trade.exit_dt)

    diagnostics = {
        "classic_candidates": len(classic_candidates),
        "fvg_setups": len(fvg_setups),
        "fvg_setups_with_fill": sum(fill_dt is not None for fill_dt in fills_by_setup.values()),
        "candidate_events": len(candidate_events),
        "enable_fvg_first_setup_per_breakout": enable_fvg_first_setup_per_breakout,
        "enable_fvg_tv_shape_filter": enable_fvg_tv_shape_filter,
        "fvg_after_classic_cooldown_minutes": fvg_after_classic_cooldown_minutes,
        "fvg_after_classic_exit_cooldown_minutes": fvg_after_classic_exit_cooldown_minutes,
        "enable_classic_tv_shape_filter": enable_classic_tv_shape_filter,
        "enable_classic_squeeze_momentum_filter": enable_classic_squeeze_momentum_filter,
        "enable_classic_wae_momentum_filter": enable_classic_wae_momentum_filter,
        "enable_classic_divergence_filter": enable_classic_divergence_filter,
        "classic_divergence_lookback": classic_divergence_lookback,
    }
    return trades, diagnostics


def metrics_from_pnl(pnls: list[float], initial_capital: float = INITIAL_CAPITAL) -> dict[str, Any]:
    if not pnls:
        return {
            "trades": 0,
            "net_pnl_usd": 0.0,
            "win_rate": None,
            "profit_factor": None,
            "max_closed_drawdown_usd": 0.0,
        }
    gross_profit = sum(value for value in pnls if value > 0)
    gross_loss = -sum(value for value in pnls if value < 0)
    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    for value in pnls:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(pnls),
        "net_pnl_usd": round(sum(pnls), 2),
        "win_rate": round(sum(value > 0 for value in pnls) / len(pnls), 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "gross_profit_usd": round(gross_profit, 2),
        "gross_loss_usd": round(gross_loss, 2),
        "max_closed_drawdown_usd": round(max_dd, 2),
    }


def summarize_export(trades: list[ExportTrade]) -> dict[str, Any]:
    by_family: dict[str, Any] = {}
    for family in ["classic", "fvg"]:
        subset = [trade for trade in trades if trade.family == family]
        by_family[family] = {
            **metrics_from_pnl([trade.pnl_usd for trade in subset]),
            "side_counts": dict(Counter(trade.side for trade in subset)),
            "exit_signal_counts": dict(Counter(trade.exit_signal for trade in subset)),
            "weekday_counts": dict(Counter(trade.entry_dt.day_name() for trade in subset)),
            "time_min": str(min((trade.entry_dt for trade in subset), default="")),
            "time_max": str(max((trade.entry_dt for trade in subset), default="")),
        }
    return {
        "overall": metrics_from_pnl([trade.pnl_usd for trade in trades]),
        "date_start": str(min(trade.entry_dt for trade in trades)),
        "date_end": str(max(trade.exit_dt for trade in trades)),
        "qty_counts": dict(Counter(str(trade.qty) for trade in trades)),
        "family_counts": dict(Counter(trade.family for trade in trades)),
        "by_family": by_family,
        "settings_guide_defaults_that_match_export": {
            "orb_logic_mode": "Both",
            "session": "New York, ORB 09:30-09:45",
            "classic_days": "Mon, Thu, Fri",
            "revised_fvg_days": "Mon, Tue, Thu",
            "classic_entry_signal_window": "09:45-10:45 signal bars, next-bar entries through 10:50",
            "fvg_selection_window": "09:45-13:00, later fills allowed by 30-bar/200-minute validity",
            "fvg_mode": "Aggressive, 2 bars before/after breakout",
            "fvg_size_filter": "9 to 60 points",
            "fvg_target": "2.0R with partial TP and BE off",
            "position_sizing": "Export evidence is fixed 1 contract sizing; commission should be passed from the TradingView Properties tab.",
        },
    }


def infer_export_risk(trade: ExportTrade) -> float | None:
    if trade.family != "fvg" or trade.exit_signal != "FVG Main Exit":
        return None
    points = trade.gross_points
    if points > 0:
        return points / FVG_TARGET_RR
    return -points


def diagnose_export_against_core(trades: list[ExportTrade], bars_5m: pd.DataFrame) -> list[ExportDiagnostic]:
    classic_by_key = {
        (candidate.entry_dt, candidate.side): candidate
        for candidate in build_classic_candidates(bars_5m, enable_overextension_filter=False)
    }
    fvg_by_fill_key: dict[tuple[pd.Timestamp, str], list[FVGSetup]] = defaultdict(list)
    # For export geometry diagnostics, a 5m fill-bar match is enough. We do not
    # need the 1s fill timestamp, only the setup risk implied by a retest in that
    # entry bar.
    for setup in build_fvg_setups(bars_5m):
        fvg_by_fill_key[(setup.entry_earliest_dt, setup.side)].append(setup)
        for offset in range(0, FVG_MAX_WAIT_BARS + 1):
            fill_bar = setup.entry_earliest_dt + pd.Timedelta(minutes=5 * offset)
            if fill_bar > setup.entry_expiry_dt:
                break
            fvg_by_fill_key[(fill_bar, setup.side)].append(setup)

    diagnostics: list[ExportDiagnostic] = []
    for trade in trades:
        inferred_risk = infer_export_risk(trade)
        if trade.family == "classic":
            candidate = classic_by_key.get((trade.entry_dt, trade.side))
            note = "classic next-bar ORB cross found" if candidate else "no raw classic ORB cross at entry-5m"
            error = None
            if candidate and trade.exit_signal == "TP SD1.0":
                local_entry = candidate.entry_dt
                if local_entry in bars_5m.index:
                    offset = trade.entry_price - float(bars_5m.loc[local_entry]["open"])
                    expected = classic_target(candidate.orb_high, candidate.orb_low, trade.side) + offset
                    error = trade.exit_price - expected
            diagnostics.append(
                ExportDiagnostic(
                    trade_no=trade.trade_no,
                    family=trade.family,
                    side=trade.side,
                    entry_dt=str(trade.entry_dt),
                    exit_dt=str(trade.exit_dt),
                    entry_signal=trade.entry_signal,
                    exit_signal=trade.exit_signal,
                    pnl_usd=trade.pnl_usd,
                    gross_points=round(trade.gross_points, 6),
                    inferred_risk_points=None,
                    local_signal_dt=str(candidate.signal_dt) if candidate else None,
                    local_model_match=candidate is not None,
                    model_note=note,
                    risk_error_points=None,
                    target_or_stop_error_points=round(error, 6) if error is not None else None,
                )
            )
            continue

        possible = fvg_by_fill_key.get((trade.entry_dt, trade.side), [])
        best: FVGSetup | None = None
        risk_error = None
        if inferred_risk is not None and possible:
            best = min(possible, key=lambda setup: abs(setup.risk_points - inferred_risk))
            risk_error = best.risk_points - inferred_risk
        elif possible:
            best = possible[0]
        note = "fvg setup found on fill bar" if best else "no aggressive FVG setup mapped to fill bar"
        diagnostics.append(
            ExportDiagnostic(
                trade_no=trade.trade_no,
                family=trade.family,
                side=trade.side,
                entry_dt=str(trade.entry_dt),
                exit_dt=str(trade.exit_dt),
                entry_signal=trade.entry_signal,
                exit_signal=trade.exit_signal,
                pnl_usd=trade.pnl_usd,
                gross_points=round(trade.gross_points, 6),
                inferred_risk_points=round(inferred_risk, 6) if inferred_risk is not None else None,
                local_signal_dt=str(best.selection_dt) if best else None,
                local_model_match=best is not None,
                model_note=note,
                risk_error_points=round(risk_error, 6) if risk_error is not None else None,
                target_or_stop_error_points=None,
            )
        )
    return diagnostics


def compare_sim_to_export(sim_trades: list[SimTrade], export_trades: list[ExportTrade]) -> dict[str, Any]:
    export_counter = Counter((trade.family, trade.side, trade.entry_dt) for trade in export_trades)
    sim_counter = Counter((trade.family, trade.side, pd.Timestamp(trade.entry_bar_dt)) for trade in sim_trades)
    matched = sum((export_counter & sim_counter).values())

    by_family: dict[str, Any] = {}
    for family in ["classic", "fvg"]:
        e_counter = Counter((trade.side, trade.entry_dt) for trade in export_trades if trade.family == family)
        s_counter = Counter((trade.side, pd.Timestamp(trade.entry_bar_dt)) for trade in sim_trades if trade.family == family)
        fam_matched = sum((e_counter & s_counter).values())
        by_family[family] = {
            "export_trades": sum(e_counter.values()),
            "sim_trades": sum(s_counter.values()),
            "entry_side_time_matches": fam_matched,
            "recall_vs_export": round(fam_matched / sum(e_counter.values()), 6) if e_counter else None,
            "precision_vs_sim": round(fam_matched / sum(s_counter.values()), 6) if s_counter else None,
            "first_missing_export_entries": [
                {"side": key[0], "entry_dt": str(key[1]), "missing_count": count}
                for key, count in list((e_counter - s_counter).items())[:20]
            ],
            "first_extra_sim_entries": [
                {"side": key[0], "entry_dt": str(key[1]), "extra_count": count}
                for key, count in list((s_counter - e_counter).items())[:20]
            ],
        }

    return {
        "entry_side_time_matches": matched,
        "recall_vs_export": round(matched / len(export_trades), 6) if export_trades else None,
        "precision_vs_sim": round(matched / len(sim_trades), 6) if sim_trades else None,
        "by_family": by_family,
    }


def write_csv_rows(path: Path, rows: list[Any]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        first = rows[0]
        fields = list(asdict(first).keys()) if hasattr(first, "__dataclass_fields__") else list(first.keys())
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row) if hasattr(row, "__dataclass_fields__") else row)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", required=True, type=Path, help="TradingView strategy tester CSV")
    parser.add_argument("--data-5m", default=Path("data/raw/GC_5m.parquet"), type=Path)
    parser.add_argument("--data-1s", default=Path("data/raw/GC_1s.parquet"), type=Path)
    parser.add_argument(
        "--overlay-5m-csv",
        action="append",
        type=Path,
        default=[],
        help="Optional TradingView 5m CSV window(s) to overlay on top of the local 5m data",
    )
    parser.add_argument("--use-1s", action="store_true", help="Use 1s data for fills/exits instead of 5m bars")
    parser.add_argument("--output-dir", type=Path, default=Path("data/results/goldx_reverse_engineer_20260426"))
    parser.add_argument("--run-sim", action="store_true", help="Also run the first-pass core replication")
    parser.add_argument(
        "--disable-classic-overextension-filter",
        action="store_true",
        help="Disable the guide's 60%% max breakout-to-SD1 filter in the first-pass sim",
    )
    parser.add_argument(
        "--enable-fvg-ut-filter",
        action="store_true",
        help="Enable the guide's Revised/FVG UT Bot directional filter proxy",
    )
    parser.add_argument(
        "--enable-fvg-first-setup-per-breakout",
        action="store_true",
        help="Freeze the first valid Revised/FVG setup for a breakout instead of letting later nearby gaps compete",
    )
    parser.add_argument(
        "--enable-fvg-tv-shape-filter",
        action="store_true",
        help="When TradingView marker columns are present, require Shapes.2 for long FVGs and Shapes.3 for short FVGs",
    )
    parser.add_argument(
        "--fvg-after-classic-cooldown-minutes",
        type=float,
        default=0.0,
        help="Block Revised/FVG selections this many minutes after the latest Classic entry",
    )
    parser.add_argument(
        "--fvg-after-classic-exit-cooldown-minutes",
        type=float,
        default=0.0,
        help="Block Revised/FVG selections this many minutes after the latest Classic exit",
    )
    parser.add_argument(
        "--enable-classic-trend-proxy-filter",
        action="store_true",
        help="Enable a Classic trend proxy using EMA20/EMA50 direction",
    )
    parser.add_argument(
        "--enable-classic-rg-filter",
        action="store_true",
        help="Enable the Classic Range Filter proxy using the visible period/mult settings",
    )
    parser.add_argument(
        "--enable-classic-ema200-filter",
        action="store_true",
        help="Enable a Classic EMA200 directional filter proxy",
    )
    parser.add_argument(
        "--enable-classic-ema9-cloud-filter",
        action="store_true",
        help="Enable a Classic EMA9 high/low cloud directional filter proxy",
    )
    parser.add_argument(
        "--enable-classic-ema-cross-filter",
        action="store_true",
        help="Enable a Classic EMA200 cross-frequency filter proxy",
    )
    parser.add_argument(
        "--enable-classic-tv-shape-filter",
        action="store_true",
        help="When TradingView marker columns are present, require Shapes for long Classic and Shapes.1 for short Classic",
    )
    parser.add_argument(
        "--enable-classic-squeeze-momentum-filter",
        action="store_true",
        help="Enable a Classic 100-bar squeeze momentum direction proxy",
    )
    parser.add_argument(
        "--enable-classic-wae-momentum-filter",
        action="store_true",
        help="Enable a Classic WAE-style EMA8/EMA100 momentum acceleration proxy",
    )
    parser.add_argument(
        "--enable-classic-divergence-filter",
        action="store_true",
        help="Enable a Classic price-vs-squeeze-momentum divergence proxy",
    )
    parser.add_argument(
        "--classic-ema-cross-hours",
        type=float,
        default=CLASSIC_EMA_CROSS_SENSITIVITY_HOURS,
        help="Lookback window for --enable-classic-ema-cross-filter",
    )
    parser.add_argument(
        "--classic-ema-cross-max-crosses",
        type=int,
        default=CLASSIC_EMA_CROSS_MAX_CROSSES,
        help="Maximum EMA200 crosses allowed inside the cross-frequency lookback",
    )
    parser.add_argument(
        "--classic-ema-cross-long-max-crosses",
        type=int,
        default=None,
        help="Optional long-side override for --classic-ema-cross-max-crosses",
    )
    parser.add_argument(
        "--classic-ema-cross-short-max-crosses",
        type=int,
        default=None,
        help="Optional short-side override for --classic-ema-cross-max-crosses",
    )
    parser.add_argument(
        "--classic-divergence-lookback",
        type=int,
        default=CLASSIC_DIVERGENCE_LOOKBACK,
        help="Lookback bars for --enable-classic-divergence-filter",
    )
    parser.add_argument("--point-value", type=float, default=DEFAULT_POINT_VALUE)
    parser.add_argument("--commission", type=float, default=DEFAULT_ROUND_TRIP_COMMISSION)
    args = parser.parse_args()

    trades = read_export(args.csv)
    start = pd.Timestamp(min(trade.entry_dt for trade in trades).date())
    end = pd.Timestamp(max(trade.exit_dt for trade in trades).date()) + pd.Timedelta(days=1)
    if args.use_1s:
        df_exec = load_1s(args.data_1s, start, end)
        bars_5m = resample_5m(df_exec)
        data_path = args.data_1s
        intrabar_rows = True
    else:
        if args.data_5m.exists():
            df_exec = load_ohlcv(args.data_5m, start, end)
            data_path = args.data_5m
        else:
            df_exec = load_5m_from_1s_streaming(args.data_1s, start, end)
            data_path = args.data_1s
        if args.overlay_5m_csv:
            overlays = [load_ohlcv(path, start, end) for path in args.overlay_5m_csv]
            df_exec = overlay_5m_frames(df_exec, overlays)
        bars_5m = df_exec
        intrabar_rows = False

    diagnostics = diagnose_export_against_core(trades, bars_5m)
    summary: dict[str, Any] = {
        "export": summarize_export(trades),
        "local_data": {
            "path": str(data_path),
            "overlay_5m_csv": [str(path) for path in args.overlay_5m_csv],
            "derived_from_1s": bool((not args.use_1s) and (not args.data_5m.exists())),
            "start": str(df_exec.index.min()),
            "end": str(df_exec.index.max()),
            "rows": len(df_exec),
            "execution_mode": "1s intrabar" if intrabar_rows else "5m bar-level",
            "bars_5m": len(bars_5m),
        },
        "export_geometry_diagnostics": {
            "classic_raw_orb_cross_matches": sum(
                diag.family == "classic" and diag.local_model_match for diag in diagnostics
            ),
            "classic_trades": sum(diag.family == "classic" for diag in diagnostics),
            "classic_tp_sd1_median_abs_error_points": None,
            "fvg_fill_bar_setup_matches": sum(diag.family == "fvg" and diag.local_model_match for diag in diagnostics),
            "fvg_trades": sum(diag.family == "fvg" for diag in diagnostics),
            "fvg_risk_median_abs_error_points": None,
            "fvg_risk_within_1_point": sum(
                diag.family == "fvg"
                and diag.risk_error_points is not None
                and abs(diag.risk_error_points) <= 1.0
                for diag in diagnostics
            ),
        },
    }

    classic_errors = [
        abs(diag.target_or_stop_error_points)
        for diag in diagnostics
        if diag.family == "classic" and diag.target_or_stop_error_points is not None
    ]
    fvg_errors = [
        abs(diag.risk_error_points)
        for diag in diagnostics
        if diag.family == "fvg" and diag.risk_error_points is not None
    ]
    if classic_errors:
        summary["export_geometry_diagnostics"]["classic_tp_sd1_median_abs_error_points"] = round(
            float(pd.Series(classic_errors).median()), 6
        )
    if fvg_errors:
        summary["export_geometry_diagnostics"]["fvg_risk_median_abs_error_points"] = round(
            float(pd.Series(fvg_errors).median()), 6
        )

    if args.run_sim:
        sim_trades, sim_diagnostics = run_core_replication(
            df_exec,
            bars_5m=bars_5m,
            intrabar_rows=intrabar_rows,
            point_value=args.point_value,
            commission=args.commission,
            enable_classic_overextension_filter=not args.disable_classic_overextension_filter,
            enable_classic_trend_proxy_filter=args.enable_classic_trend_proxy_filter,
            enable_classic_rg_filter=args.enable_classic_rg_filter,
            enable_classic_ema200_filter=args.enable_classic_ema200_filter,
            enable_classic_ema9_cloud_filter=args.enable_classic_ema9_cloud_filter,
            enable_classic_ema_cross_filter=args.enable_classic_ema_cross_filter,
            enable_classic_tv_shape_filter=args.enable_classic_tv_shape_filter,
            enable_classic_squeeze_momentum_filter=args.enable_classic_squeeze_momentum_filter,
            enable_classic_wae_momentum_filter=args.enable_classic_wae_momentum_filter,
            enable_classic_divergence_filter=args.enable_classic_divergence_filter,
            classic_ema_cross_hours=args.classic_ema_cross_hours,
            classic_ema_cross_max_crosses=args.classic_ema_cross_max_crosses,
            classic_ema_cross_long_max_crosses=args.classic_ema_cross_long_max_crosses,
            classic_ema_cross_short_max_crosses=args.classic_ema_cross_short_max_crosses,
            classic_divergence_lookback=args.classic_divergence_lookback,
            enable_fvg_ut_filter=args.enable_fvg_ut_filter,
            enable_fvg_first_setup_per_breakout=args.enable_fvg_first_setup_per_breakout,
            enable_fvg_tv_shape_filter=args.enable_fvg_tv_shape_filter,
            fvg_after_classic_cooldown_minutes=args.fvg_after_classic_cooldown_minutes,
            fvg_after_classic_exit_cooldown_minutes=args.fvg_after_classic_exit_cooldown_minutes,
        )
        summary["first_pass_replication"] = {
            "assumptions": {
                "point_value": args.point_value,
                "commission": args.commission,
                "qty": 1,
                "classic_filters_implemented": (
                    "ORB cross, active days, optional 60%% overextension, 50m cooldown"
                    + (
                        ", EMA20/EMA50 trend proxy"
                        if args.enable_classic_trend_proxy_filter
                        else ""
                    )
                    + (", Range Filter proxy" if args.enable_classic_rg_filter else "")
                    + (", EMA200 directional proxy" if args.enable_classic_ema200_filter else "")
                    + (", EMA9 high/close cloud proxy" if args.enable_classic_ema9_cloud_filter else "")
                    + (
                        ", EMA200 cross-frequency proxy"
                        if args.enable_classic_ema_cross_filter
                        else ""
                    )
                    + (
                        ", exact TradingView Classic shape markers where exported"
                        if args.enable_classic_tv_shape_filter
                        else ""
                    )
                    + (
                        ", 100-bar squeeze momentum direction proxy"
                        if args.enable_classic_squeeze_momentum_filter
                        else ""
                    )
                    + (
                        ", WAE-style EMA8/EMA100 momentum acceleration proxy"
                        if args.enable_classic_wae_momentum_filter
                        else ""
                    )
                    + (
                        ", price-vs-squeeze-momentum divergence proxy"
                        if args.enable_classic_divergence_filter
                        else ""
                    )
                ),
                "classic_filters_not_implemented": (
                    ", ".join(
                        name
                        for name, implemented in (
                            ("squeeze", args.enable_classic_squeeze_momentum_filter),
                            ("WAE", args.enable_classic_wae_momentum_filter),
                            ("divergence", args.enable_classic_divergence_filter),
                            ("range filter/proprietary internals", False),
                        )
                        if not implemented
                    )
                    if (
                        args.enable_classic_trend_proxy_filter
                        or args.enable_classic_rg_filter
                        or args.enable_classic_ema200_filter
                        or args.enable_classic_ema9_cloud_filter
                        or args.enable_classic_ema_cross_filter
                        or args.enable_classic_squeeze_momentum_filter
                        or args.enable_classic_wae_momentum_filter
                        or args.enable_classic_divergence_filter
                    )
                    else "EMA cross, squeeze, WAE, divergence, range filter/proprietary internals"
                ),
                "classic_trend_proxy_enabled": args.enable_classic_trend_proxy_filter,
                "classic_rg_filter_enabled": args.enable_classic_rg_filter,
                "classic_rg_period": CLASSIC_RG_PERIOD,
                "classic_rg_mult": CLASSIC_RG_MULT,
                "classic_rg_tv_plot_override": "Plot" in bars_5m.columns,
                "classic_ema200_filter_enabled": args.enable_classic_ema200_filter,
                "classic_ema9_cloud_filter_enabled": args.enable_classic_ema9_cloud_filter,
                "classic_ema_cross_filter_enabled": args.enable_classic_ema_cross_filter,
                "classic_ema_cross_hours": args.classic_ema_cross_hours,
                "classic_ema_cross_max_crosses": args.classic_ema_cross_max_crosses,
                "classic_ema_cross_long_max_crosses": args.classic_ema_cross_long_max_crosses,
                "classic_ema_cross_short_max_crosses": args.classic_ema_cross_short_max_crosses,
                "classic_tv_shape_filter_enabled": args.enable_classic_tv_shape_filter,
                "classic_squeeze_momentum_filter_enabled": args.enable_classic_squeeze_momentum_filter,
                "classic_squeeze_length": CLASSIC_SQUEEZE_LENGTH,
                "classic_wae_momentum_filter_enabled": args.enable_classic_wae_momentum_filter,
                "classic_momentum_fast_ema": CLASSIC_MOMENTUM_FAST_EMA,
                "classic_momentum_slow_ema": CLASSIC_MOMENTUM_SLOW_EMA,
                "classic_momentum_sensitivity": CLASSIC_MOMENTUM_SENSITIVITY,
                "classic_divergence_filter_enabled": args.enable_classic_divergence_filter,
                "classic_divergence_lookback": args.classic_divergence_lookback,
                "fvg_filters_implemented": (
                    "Aggressive FVG geometry, size, ORB distance, retest validity, cooldown"
                    + (", UT Bot directional proxy" if args.enable_fvg_ut_filter else "")
                    + (
                        ", first setup frozen per breakout"
                        if args.enable_fvg_first_setup_per_breakout
                        else ""
                    )
                    + (
                        ", exact TradingView FVG shape markers where exported"
                        if args.enable_fvg_tv_shape_filter
                        else ""
                    )
                    + (
                        f", blocked {args.fvg_after_classic_cooldown_minutes:g}m after Classic entry"
                        if args.fvg_after_classic_cooldown_minutes > 0
                        else ""
                    )
                    + (
                        f", blocked {args.fvg_after_classic_exit_cooldown_minutes:g}m after Classic exit"
                        if args.fvg_after_classic_exit_cooldown_minutes > 0
                        else ""
                    )
                ),
                "fvg_filters_not_implemented": (
                    "ATR HEMA optional filter"
                    if args.enable_fvg_ut_filter
                    else "UT Bot directional filter, ATR HEMA optional filter"
                ),
                "fvg_ut_filter_enabled": args.enable_fvg_ut_filter,
                "fvg_ut_key_value": FVG_UT_KEY_VALUE,
                "fvg_ut_atr_period": FVG_UT_ATR_PERIOD,
                "fvg_first_setup_per_breakout_enabled": args.enable_fvg_first_setup_per_breakout,
                "fvg_tv_shape_filter_enabled": args.enable_fvg_tv_shape_filter,
                "fvg_after_classic_cooldown_minutes": args.fvg_after_classic_cooldown_minutes,
                "fvg_after_classic_exit_cooldown_minutes": args.fvg_after_classic_exit_cooldown_minutes,
            },
            "candidate_diagnostics": sim_diagnostics,
            "metrics": metrics_from_pnl([trade.pnl_usd for trade in sim_trades]),
            "family_counts": dict(Counter(trade.family for trade in sim_trades)),
            "exit_signal_counts": dict(Counter(trade.exit_signal for trade in sim_trades)),
            "comparison_to_export": compare_sim_to_export(sim_trades, trades),
        }

    print(json.dumps(summary, indent=2, default=str))

    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
        write_csv_rows(args.output_dir / "export_trade_diagnostics.csv", diagnostics)
        if args.run_sim:
            write_csv_rows(args.output_dir / "sim_trades.csv", sim_trades)


if __name__ == "__main__":
    main()
