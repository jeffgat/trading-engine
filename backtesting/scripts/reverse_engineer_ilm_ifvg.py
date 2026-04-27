#!/usr/bin/env python3
"""Reverse-engineer the N4A ILM/iFVG TradingView export.

This is a research diagnostic, not a production backtester. It keeps all
outputs under an ILM-specific results directory and compares the exported
TradingView trades to simple local hypotheses built from the settings guide:

    liquidity sweep -> opposite FVG -> inverted FVG -> entry

The local NQ data is unadjusted while the TradingView NQ1! export appears
back-adjusted for older years, so entry parity is scored by timestamp/side
rather than absolute price.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pyarrow.parquet as pq


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EXPORT = Path(
    "/Users/jeffreygatbonton/Downloads/"
    "N4A.ILM_iFVG_Strategy_v22.7_CME_MINI_NQ1!_2026-04-26_1e128.csv"
)
DEFAULT_NQ_1S = ROOT / "data" / "raw" / "NQ_1s.parquet"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / "ilm_ifvg_reverse_engineering"

NQ_POINT_VALUE = 20.0
MNQ_POINT_VALUE = 2.0
TV_ROUND_TRIP_COMMISSION = 5.70
INITIAL_CAPITAL = 10_000.0

ASIA = ("20:00", "00:00")
LONDON = ("02:00", "05:00")
PRE_NY = ("08:30", "09:30")
NY_AM = ("09:30", "11:30")
ENTRY_WINDOWS = (("02:00", "05:00"), ("08:30", "11:00"))
ALLOWED_WEEKDAYS = {0, 1, 2, 4}  # Mon, Tue, Wed, Fri. Thursday is OFF in the guide.
SWING_LENGTH = 2
UT_KEY_VALUE = 3.0
UT_ATR_PERIOD = 30
STRUCTURE_BREACHES = 3
ALGO_REVERSAL_LOOKBACK = 2
ALGO_CANDLE_LOOKBACK = 10
ALGO_CONFIRM_WITHIN = 3
ALGO_TREND_MA_PERIOD = 50
ALGO_MA_STEP_PERIOD = 33
ALGO_VOLUME_MA_PERIOD = 20
ALGO_REVERSAL_ZONE_FRACTION = 0.35
TV_REVERSAL_MIN_DISTANCE_POINTS = 10.0


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
    exit_signal: str


@dataclass(frozen=True)
class Level:
    name: str
    direction: str  # "high" levels create short setups; "low" levels create long setups.
    price: float


@dataclass(frozen=True)
class Candidate:
    side: str
    signal_dt: pd.Timestamp
    entry_dt: pd.Timestamp
    entry_price: float
    source: str
    sweep_dt: pd.Timestamp
    sweep_price: float
    fvg_dt: pd.Timestamp
    gap_top: float
    gap_bottom: float
    gap_size: float
    impulse_high: float
    impulse_low: float
    bars_sweep_to_gap: int
    bars_sweep_to_entry: int
    atr: float
    stop_price: float
    target_price: float
    risk_points: float


@dataclass(frozen=True)
class SimTrade:
    trade_no: int
    side: str
    signal_dt: str
    entry_dt: str
    exit_dt: str
    entry_price: float
    exit_price: float
    qty: int
    pnl_nq_usd: float
    pnl_mnq_usd: float
    exit_signal: str
    source: str
    sweep_dt: str
    fvg_dt: str
    stop_price: float
    target_price: float
    risk_points: float
    atr: float


def parse_export(path: Path) -> list[ExportTrade]:
    rows_by_trade: dict[int, list[dict[str, str]]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            rows_by_trade[int(row["Trade #"])].append(row)

    trades: list[ExportTrade] = []
    for trade_no, rows in sorted(rows_by_trade.items()):
        entry = next(row for row in rows if row["Type"].startswith("Entry"))
        exit_ = next(row for row in rows if row["Type"].startswith("Exit"))
        trades.append(
            ExportTrade(
                trade_no=trade_no,
                side="long" if "long" in entry["Type"].lower() else "short",
                entry_dt=pd.Timestamp(entry["Date and time"]),
                exit_dt=pd.Timestamp(exit_["Date and time"]),
                entry_price=float(entry["Price USD"]),
                exit_price=float(exit_["Price USD"]),
                qty=float(entry["Size (qty)"]),
                pnl_usd=float(entry["Net P&L USD"]),
                mfe_usd=float(entry["Favorable excursion USD"]),
                mae_usd=float(entry["Adverse excursion USD"]),
                exit_signal=exit_["Signal"],
            )
        )
    return trades


def load_tradingview_5m_csv(path: Path) -> pd.DataFrame:
    """Load a TradingView OHLC export and preserve any indicator columns.

    TradingView writes UNIX timestamps in UTC. The strategy settings and trade
    export timestamps are New York wall-clock time, so the diagnostic keeps a
    naive America/New_York DatetimeIndex for direct entry-time matching.
    """
    bars = pd.read_csv(path)
    if "time" not in bars.columns:
        raise ValueError(f"{path} must contain TradingView's `time` column")
    bars["datetime"] = (
        pd.to_datetime(bars["time"], unit="s", utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    bars = bars.sort_values("datetime").set_index("datetime")
    if "volume" not in bars.columns:
        # The ILM export window omits volume. Keep the indicator/entry probes
        # usable; volume-confirmation variants should not be evaluated on this.
        bars["volume"] = 1.0
    return bars


def export_metrics(trades: list[ExportTrade]) -> dict[str, Any]:
    pnl = [trade.pnl_usd for trade in trades]
    gross_profit = sum(value for value in pnl if value > 0)
    gross_loss = -sum(value for value in pnl if value < 0)
    equity = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    max_intratrade_dd = 0.0
    for trade in trades:
        max_intratrade_dd = max(max_intratrade_dd, peak - (equity + trade.mae_usd))
        equity += trade.pnl_usd
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(trades),
        "net_pnl_nq_usd": round(sum(pnl), 2),
        "net_pnl_mnq_scaled_usd": round(sum(pnl) * (MNQ_POINT_VALUE / NQ_POINT_VALUE), 2),
        "wins": sum(value > 0 for value in pnl),
        "losses": sum(value < 0 for value in pnl),
        "win_rate": round(sum(value > 0 for value in pnl) / len(pnl), 6) if pnl else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "max_closed_drawdown_usd": round(max_dd, 2),
        "max_intratrade_drawdown_usd": round(max_intratrade_dd, 2),
        "side_counts": dict(Counter(trade.side for trade in trades)),
        "exit_signal_counts": dict(Counter(trade.exit_signal for trade in trades)),
        "qty_counts": dict(Counter(str(trade.qty) for trade in trades)),
    }


def _row_group_overlaps(parquet_file: pq.ParquetFile, row_group: int, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    names = parquet_file.schema.names
    idx = names.index("datetime")
    stats = parquet_file.metadata.row_group(row_group).column(idx).statistics
    return pd.Timestamp(stats.max) >= start and pd.Timestamp(stats.min) < end


def build_5m_cache(source: Path, cache_path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    if cache_path.exists():
        bars = pd.read_parquet(cache_path)
        if not isinstance(bars.index, pd.DatetimeIndex):
            bars.index = pd.to_datetime(bars.index)
        return bars[(bars.index >= start) & (bars.index < end)].copy()

    parquet_file = pq.ParquetFile(source)
    chunks: list[pd.DataFrame] = []
    for row_group in range(parquet_file.num_row_groups):
        if not _row_group_overlaps(parquet_file, row_group, start, end):
            continue
        table = parquet_file.read_row_group(row_group, columns=["open", "high", "low", "close", "volume", "datetime"])
        df = table.to_pandas().sort_index()
        if not isinstance(df.index, pd.DatetimeIndex):
            df = df.set_index("datetime")
        df = df[(df.index >= start) & (df.index < end)]
        if df.empty:
            continue
        chunks.append(
            df.resample("5min", label="left", closed="left")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna()
        )

    if not chunks:
        raise ValueError(f"No 1s rows loaded from {source} for {start} -> {end}")

    partial = pd.concat(chunks).sort_index()
    bars = (
        partial.groupby(partial.index)
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .sort_index()
    )
    bars.to_parquet(cache_path)
    return bars


def wma(series: pd.Series, length: int) -> pd.Series:
    weights = pd.Series(range(1, length + 1), dtype=float)
    denom = float(weights.sum())
    return series.rolling(length).apply(lambda values: float((values * weights).sum() / denom), raw=True)


def ut_bot_direction(close: pd.Series, atr: pd.Series, *, key_value: float) -> tuple[list[float], list[int]]:
    stop_values: list[float] = []
    directions: list[int] = []
    prev_stop: float | None = None
    prev_src: float | None = None
    prev_direction = 0
    for src_value, atr_value in zip(close, atr):
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
    return stop_values, directions


def market_structure_state(bars: pd.DataFrame) -> list[int]:
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    events_by_confirmation: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for i in range(SWING_LENGTH, len(bars) - SWING_LENGTH):
        high_window = highs[i - SWING_LENGTH : i + SWING_LENGTH + 1]
        low_window = lows[i - SWING_LENGTH : i + SWING_LENGTH + 1]
        if highs[i] == high_window.max() and (high_window == highs[i]).sum() == 1:
            events_by_confirmation[i + SWING_LENGTH].append(("high", float(highs[i])))
        if lows[i] == low_window.min() and (low_window == lows[i]).sum() == 1:
            events_by_confirmation[i + SWING_LENGTH].append(("low", float(lows[i])))

    recent_highs: list[float] = []
    recent_lows: list[float] = []
    states: list[int] = []
    for i in range(len(bars)):
        for kind, value in events_by_confirmation.get(i, []):
            if kind == "high":
                recent_highs.append(value)
                recent_highs = recent_highs[-STRUCTURE_BREACHES:]
            else:
                recent_lows.append(value)
                recent_lows = recent_lows[-STRUCTURE_BREACHES:]

        state = 0
        if len(recent_highs) >= STRUCTURE_BREACHES and len(recent_lows) >= STRUCTURE_BREACHES:
            highs_rising = all(a < b for a, b in zip(recent_highs, recent_highs[1:]))
            lows_rising = all(a < b for a, b in zip(recent_lows, recent_lows[1:]))
            highs_falling = all(a > b for a, b in zip(recent_highs, recent_highs[1:]))
            lows_falling = all(a > b for a, b in zip(recent_lows, recent_lows[1:]))
            if highs_rising and lows_rising:
                state = 1
            elif highs_falling and lows_falling:
                state = -1
        states.append(state)
    return states


def market_structure_breach_states(bars: pd.DataFrame) -> tuple[list[int], list[int]]:
    """Approximate the guide's H/L breach confirmation structure setting.

    The screenshots show Structure Source=H/L and Breaches for Confirmation=3.
    This tracks confirmed swing highs/lows, then counts high/low breaches over
    the same 100-bar horizon used by the sweep cutoff.
    """
    highs = bars["high"].to_numpy()
    lows = bars["low"].to_numpy()
    events_by_confirmation: dict[int, list[tuple[str, float]]] = defaultdict(list)
    for i in range(SWING_LENGTH, len(bars) - SWING_LENGTH):
        high_window = highs[i - SWING_LENGTH : i + SWING_LENGTH + 1]
        low_window = lows[i - SWING_LENGTH : i + SWING_LENGTH + 1]
        if highs[i] == high_window.max() and (high_window == highs[i]).sum() == 1:
            events_by_confirmation[i + SWING_LENGTH].append(("high", float(highs[i])))
        if lows[i] == low_window.min() and (low_window == lows[i]).sum() == 1:
            events_by_confirmation[i + SWING_LENGTH].append(("low", float(lows[i])))

    latest_high = float("nan")
    latest_low = float("nan")
    high_breaches: deque[int] = deque()
    low_breaches: deque[int] = deque()
    roll_states: list[int] = []
    last_breach_states: list[int] = []
    last_breach_side = 0
    for i, row in enumerate(bars.itertuples()):
        for kind, value in events_by_confirmation.get(i, []):
            if kind == "high":
                latest_high = value
            else:
                latest_low = value

        if not math.isnan(latest_high) and float(row.high) > latest_high:
            high_breaches.append(i)
            last_breach_side = 1
        if not math.isnan(latest_low) and float(row.low) < latest_low:
            low_breaches.append(i)
            last_breach_side = -1
        while high_breaches and i - high_breaches[0] > 100:
            high_breaches.popleft()
        while low_breaches and i - low_breaches[0] > 100:
            low_breaches.popleft()

        if len(high_breaches) >= STRUCTURE_BREACHES and len(high_breaches) > len(low_breaches):
            roll_states.append(1)
        elif len(low_breaches) >= STRUCTURE_BREACHES and len(low_breaches) > len(high_breaches):
            roll_states.append(-1)
        else:
            roll_states.append(0)

        if len(high_breaches) >= STRUCTURE_BREACHES and last_breach_side == 1:
            last_breach_states.append(1)
        elif len(low_breaches) >= STRUCTURE_BREACHES and last_breach_side == -1:
            last_breach_states.append(-1)
        else:
            last_breach_states.append(0)

    return roll_states, last_breach_states


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    prev_close = out["close"].shift(1)
    tr = pd.concat(
        [
            out["high"] - out["low"],
            (out["high"] - prev_close).abs(),
            (out["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    out["atr12_wma"] = wma(tr, 12)
    out["mid100"] = (out["high"].rolling(100).max() + out["low"].rolling(100).min()) / 2.0
    out["mid200"] = (out["high"].rolling(200).max() + out["low"].rolling(200).min()) / 2.0
    out["ut_atr30"] = tr.ewm(alpha=1 / UT_ATR_PERIOD, adjust=False, min_periods=UT_ATR_PERIOD).mean()
    out["ut_stop_long"] = out["close"] - 3.0 * out["ut_atr30"]
    out["ut_stop_short"] = out["close"] + 3.0 * out["ut_atr30"]
    out["ut_stop"], out["ut_direction"] = ut_bot_direction(out["close"], out["ut_atr30"], key_value=UT_KEY_VALUE)
    out["structure_state"] = market_structure_state(out)
    out["structure_breach_roll"], out["structure_breach_last"] = market_structure_breach_states(out)
    out["algo_trend_ma"] = out["close"].ewm(
        span=ALGO_TREND_MA_PERIOD,
        adjust=False,
        min_periods=ALGO_TREND_MA_PERIOD,
    ).mean()
    out["algo_step_ma"] = out["close"].ewm(
        span=ALGO_MA_STEP_PERIOD,
        adjust=False,
        min_periods=ALGO_MA_STEP_PERIOD,
    ).mean()
    out["algo_volume_ma"] = out["volume"].rolling(ALGO_VOLUME_MA_PERIOD).mean()
    algo_high = out["high"].rolling(ALGO_CANDLE_LOOKBACK).max()
    algo_low = out["low"].rolling(ALGO_CANDLE_LOOKBACK).min()
    algo_range = algo_high - algo_low
    volume_ok = out["volume"] > out["algo_volume_ma"]
    bullish_raw = (out["close"] > out["open"]) & volume_ok & (out["close"] < out["algo_trend_ma"])
    bearish_raw = (out["close"] < out["open"]) & volume_ok & (out["close"] > out["algo_trend_ma"])
    bullish_zone_raw = bullish_raw & (out["close"] <= algo_low + algo_range * ALGO_REVERSAL_ZONE_FRACTION)
    bearish_zone_raw = bearish_raw & (out["close"] >= algo_high - algo_range * ALGO_REVERSAL_ZONE_FRACTION)
    out["algo_bullish_reversal"] = (
        bullish_raw.rolling(ALGO_CONFIRM_WITHIN, min_periods=1).max().fillna(False).astype(bool)
    )
    out["algo_bearish_reversal"] = (
        bearish_raw.rolling(ALGO_CONFIRM_WITHIN, min_periods=1).max().fillna(False).astype(bool)
    )
    out["algo_bullish_zone_reversal"] = (
        bullish_zone_raw.rolling(ALGO_CONFIRM_WITHIN, min_periods=1).max().fillna(False).astype(bool)
    )
    out["algo_bearish_zone_reversal"] = (
        bearish_zone_raw.rolling(ALGO_CONFIRM_WITHIN, min_periods=1).max().fillna(False).astype(bool)
    )
    return out


def between_any(ts: pd.Timestamp, windows: Iterable[tuple[str, str]]) -> bool:
    t = ts.time()
    for start_s, end_s in windows:
        start = pd.Timestamp(f"{ts.date()} {start_s}").time()
        end = pd.Timestamp(f"{ts.date()} {end_s}").time()
        if start <= t <= end:
            return True
    return False


def in_session(ts: pd.Timestamp, start_s: str, end_s: str) -> bool:
    t = ts.time()
    start = pd.Timestamp(f"{ts.date()} {start_s}").time()
    end = pd.Timestamp(f"{ts.date()} {end_s}").time()
    if start_s > end_s:
        return t >= start or t < end
    return start <= t < end


def session_levels(bars: pd.DataFrame, start_s: str, end_s: str, prefix: str) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    for day, group in bars.groupby(bars.index.date):
        if start_s > end_s:
            session = group[group.index.map(lambda ts: in_session(ts, start_s, end_s))]
        else:
            session = group.between_time(start_s, end_s, inclusive="left")
        if session.empty:
            continue
        if start_s > end_s:
            available_from = pd.Timestamp(day) + pd.Timedelta(days=1)
            if end_s != "00:00":
                available_from = pd.Timestamp(f"{available_from.date()} {end_s}")
        else:
            available_from = pd.Timestamp(f"{day} {end_s}")
        records.append(
            {
                "available_from": available_from,
                f"{prefix}_high": float(session["high"].max()),
                f"{prefix}_low": float(session["low"].min()),
            }
        )
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(records).set_index("available_from").sort_index()


def daily_levels(bars: pd.DataFrame) -> pd.DataFrame:
    daily = bars.groupby(bars.index.date).agg({"high": "max", "low": "min"})
    daily.index = pd.to_datetime(daily.index)
    out = pd.DataFrame(index=daily.index + pd.Timedelta(days=1))
    out["pdh"] = daily["high"].to_numpy()
    out["pdl"] = daily["low"].to_numpy()
    return out.sort_index()


def weekly_levels(bars: pd.DataFrame) -> pd.DataFrame:
    by_week = bars.groupby(bars.index.to_period("W-SUN")).agg({"high": "max", "low": "min"})
    rows: list[dict[str, Any]] = []
    for period, row in by_week.iterrows():
        available = pd.Timestamp(period.end_time.date()) + pd.Timedelta(days=1)
        rows.append({"available_from": available, "pwh": float(row.high), "pwl": float(row.low)})
    return pd.DataFrame(rows).set_index("available_from").sort_index() if rows else pd.DataFrame()


def add_level_columns(bars: pd.DataFrame) -> pd.DataFrame:
    out = bars.copy()
    out.index = pd.DatetimeIndex(out.index).as_unit("ns")
    level_frames = [
        session_levels(bars, *ASIA, "asia"),
        session_levels(bars, *LONDON, "london"),
        session_levels(bars, *PRE_NY, "preny"),
        daily_levels(bars),
        weekly_levels(bars),
    ]
    for levels in level_frames:
        if levels.empty:
            continue
        levels.index = pd.DatetimeIndex(levels.index).as_unit("ns")
        out = pd.merge_asof(
            out.sort_index(),
            levels.sort_index(),
            left_index=True,
            right_index=True,
            direction="backward",
        )
    return out


def fvg_at(bars: pd.DataFrame, idx: int, min_gap_points: float, max_gap_points: float | None) -> dict[str, Any] | None:
    if idx < 2:
        return None
    before = bars.iloc[idx - 2]
    impulse = bars.iloc[idx - 1]
    after = bars.iloc[idx]
    bullish_size = float(after.low - before.high)
    if (
        before.high < after.low
        and before.high < impulse.high
        and before.low < after.low
        and bullish_size >= min_gap_points
        and (max_gap_points is None or bullish_size <= max_gap_points)
    ):
        return {
            "kind": "bullish",
            "top": float(after.low),
            "bottom": float(before.high),
            "size": bullish_size,
            "impulse_high": float(impulse.high),
            "impulse_low": float(impulse.low),
        }
    bearish_size = float(before.low - after.high)
    if (
        before.low > after.high
        and before.low > impulse.low
        and before.high > after.high
        and bearish_size >= min_gap_points
        and (max_gap_points is None or bearish_size <= max_gap_points)
    ):
        return {
            "kind": "bearish",
            "top": float(before.low),
            "bottom": float(after.high),
            "size": bearish_size,
            "impulse_high": float(impulse.high),
            "impulse_low": float(impulse.low),
        }
    return None


def active_levels(row: pd.Series, sources: tuple[str, ...]) -> list[Level]:
    levels: list[Level] = []
    source_columns = {
        "asia": ("asia_high", "asia_low"),
        "london": ("london_high", "london_low"),
        "preny": ("preny_high", "preny_low"),
        "pd": ("pdh", "pdl"),
        "pw": ("pwh", "pwl"),
    }
    for source in sources:
        high_col, low_col = source_columns[source]
        high = row.get(high_col)
        low = row.get(low_col)
        if high is not None and not pd.isna(high):
            levels.append(Level(f"{source}_high", "high", float(high)))
        if low is not None and not pd.isna(low):
            levels.append(Level(f"{source}_low", "low", float(low)))
    return levels


def passes_filters(row: pd.Series, side: str, filters: tuple[str, ...]) -> bool:
    if "premium_discount" in filters:
        mid100 = row.get("mid100")
        if pd.isna(mid100):
            return False
        if side == "long" and not (float(row.close) <= float(mid100)):
            return False
        if side == "short" and not (float(row.close) >= float(mid100)):
            return False
    if "macro_premium_discount" in filters:
        mid200 = row.get("mid200")
        if pd.isna(mid200):
            return False
        if side == "long" and not (float(row.close) <= float(mid200)):
            return False
        if side == "short" and not (float(row.close) >= float(mid200)):
            return False
    if "ut_proxy" in filters:
        direction = row.get("ut_direction")
        if pd.isna(direction):
            return False
        if side == "long" and int(direction) != 1:
            return False
        if side == "short" and int(direction) != -1:
            return False
    if "tv_ub_filter" in filters:
        ub_filter = row.get("UB-Filter")
        if pd.isna(ub_filter):
            return False
        if side == "long" and not (float(row.close) > float(ub_filter)):
            return False
        if side == "short" and not (float(row.close) < float(ub_filter)):
            return False
    if "tv_reversal_ma_mean_revert" in filters:
        reversal_ma = row.get("Reversal MA")
        if pd.isna(reversal_ma):
            return False
        if side == "long" and not (float(row.close) < float(reversal_ma)):
            return False
        if side == "short" and not (float(row.close) > float(reversal_ma)):
            return False
    if "tv_reversal_ma_min_distance" in filters:
        reversal_ma = row.get("Reversal MA")
        if pd.isna(reversal_ma):
            return False
        if abs(float(row.close) - float(reversal_ma)) < TV_REVERSAL_MIN_DISTANCE_POINTS:
            return False
    if "market_structure" in filters:
        state = row.get("structure_state")
        if pd.isna(state):
            return False
        if side == "long" and int(state) != 1:
            return False
        if side == "short" and int(state) != -1:
            return False
    if "market_structure_breach_contra" in filters:
        state = row.get("structure_breach_last")
        if pd.isna(state):
            return False
        if side == "long" and int(state) != -1:
            return False
        if side == "short" and int(state) != 1:
            return False
    if "algo_reversal_proxy" in filters:
        if side == "long" and not bool(row.get("algo_bullish_reversal", False)):
            return False
        if side == "short" and not bool(row.get("algo_bearish_reversal", False)):
            return False
    if "algo_reversal_zone_proxy" in filters:
        if side == "long" and not bool(row.get("algo_bullish_zone_reversal", False)):
            return False
        if side == "short" and not bool(row.get("algo_bearish_zone_reversal", False)):
            return False
    return True


def build_candidates(
    bars: pd.DataFrame,
    *,
    sources: tuple[str, ...],
    max_bars_after_sweep: int,
    fvg_window_bars: int,
    min_gap_points: float,
    max_gap_points: float | None,
    entry_timing: str,
    filters: tuple[str, ...],
    inversion_lookback_bars: int | None = None,
    sweep_cutoff_lookback_bars: int | None = None,
    max_sweeps_per_major_level: int = 2,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    active_setup: dict[str, Any] | None = None
    traded_levels: Counter[str] = Counter()
    sweep_history: dict[str, deque[int]] = defaultdict(deque)

    for i, (ts, row) in enumerate(bars.iterrows()):
        if ts.weekday() not in ALLOWED_WEEKDAYS:
            active_setup = None
            continue
        if not between_any(ts, ENTRY_WINDOWS):
            if active_setup is not None and ts.time() > pd.Timestamp(f"{ts.date()} 11:00").time():
                active_setup = None
            continue

        if active_setup is not None:
            age = i - int(active_setup["sweep_idx"])
            if age > max_bars_after_sweep:
                active_setup = None
            else:
                wanted_kind = "bullish" if active_setup["side"] == "short" else "bearish"
                gap = fvg_at(bars, i, min_gap_points, max_gap_points)
                if gap and gap["kind"] == wanted_kind:
                    impulse_idx = i - 1
                    if abs(impulse_idx - int(active_setup["sweep_idx"])) <= fvg_window_bars:
                        active_setup = {**active_setup, "gap": gap, "gap_idx": i, "gap_ts": ts}

                gap = active_setup.get("gap")
                if gap:
                    if (
                        inversion_lookback_bars is not None
                        and i - int(active_setup["gap_idx"]) > inversion_lookback_bars
                    ):
                        active_setup = None
                        continue
                    side = str(active_setup["side"])
                    inverted = (side == "short" and float(row.close) < float(gap["bottom"])) or (
                        side == "long" and float(row.close) > float(gap["top"])
                    )
                    if inverted and passes_filters(row, side, filters):
                        signal_idx = i
                        entry_idx = i + 1 if entry_timing == "next_open" else i
                        if entry_idx < len(bars):
                            entry_row = bars.iloc[entry_idx]
                            entry_ts = bars.index[entry_idx]
                            entry_price = float(entry_row.open) if entry_timing == "next_open" else float(row.close)
                            atr = float(row.atr12_wma)
                            if not math.isnan(atr) and atr > 0:
                                risk_points = 1.6 * atr
                                stop = entry_price - risk_points if side == "long" else entry_price + risk_points
                                target = entry_price + 2.0 * risk_points if side == "long" else entry_price - 2.0 * risk_points
                                candidates.append(
                                    Candidate(
                                        side=side,
                                        signal_dt=bars.index[signal_idx],
                                        entry_dt=entry_ts,
                                        entry_price=entry_price,
                                        source=str(active_setup["source"]),
                                        sweep_dt=bars.index[int(active_setup["sweep_idx"])],
                                        sweep_price=float(active_setup["sweep_price"]),
                                        fvg_dt=pd.Timestamp(active_setup["gap_ts"]),
                                        gap_top=float(gap["top"]),
                                        gap_bottom=float(gap["bottom"]),
                                        gap_size=float(gap["size"]),
                                        impulse_high=float(gap["impulse_high"]),
                                        impulse_low=float(gap["impulse_low"]),
                                        bars_sweep_to_gap=int(active_setup["gap_idx"]) - int(active_setup["sweep_idx"]),
                                        bars_sweep_to_entry=entry_idx - int(active_setup["sweep_idx"]),
                                        atr=atr,
                                        stop_price=stop,
                                        target_price=target,
                                        risk_points=risk_points,
                                    )
                                )
                                traded_levels[str(active_setup["level_key"])] += 1
                                active_setup = None
                                continue

        if active_setup is None:
            for level in active_levels(row, sources):
                level_key = f"{level.name}:{level.price:.2f}"
                high_swept = level.direction == "high" and float(row.high) > level.price
                low_swept = level.direction == "low" and float(row.low) < level.price
                if not high_swept and not low_swept:
                    continue

                if sweep_cutoff_lookback_bars is None:
                    if traded_levels[level_key] >= max_sweeps_per_major_level:
                        continue
                else:
                    history = sweep_history[level_key]
                    while history and i - history[0] > sweep_cutoff_lookback_bars:
                        history.popleft()
                    if len(history) >= max_sweeps_per_major_level:
                        continue
                    history.append(i)

                if high_swept:
                    active_setup = {
                        "side": "short",
                        "source": level.name,
                        "level_key": level_key,
                        "sweep_idx": i,
                        "sweep_price": level.price,
                    }
                    break
                if low_swept:
                    active_setup = {
                        "side": "long",
                        "source": level.name,
                        "level_key": level_key,
                        "sweep_idx": i,
                        "sweep_price": level.price,
                    }
                    break

    return candidates


def simulate_candidates(
    bars: pd.DataFrame,
    candidates: list[Candidate],
    *,
    max_hold_minutes: int = 90,
    cooldown_bars: int = 3,
    max_trades_per_day: int = 3,
) -> list[SimTrade]:
    trades: list[SimTrade] = []
    open_until: pd.Timestamp | None = None
    cooldown_until: pd.Timestamp | None = None
    trades_by_day: Counter[str] = Counter()
    trade_no = 1

    for candidate in sorted(candidates, key=lambda c: c.entry_dt):
        day_key = str(candidate.entry_dt.date())
        if trades_by_day[day_key] >= max_trades_per_day:
            continue
        if open_until is not None and candidate.entry_dt <= open_until:
            continue
        if cooldown_until is not None and candidate.entry_dt <= cooldown_until:
            continue
        if candidate.entry_dt not in bars.index:
            continue

        start_pos = bars.index.get_loc(candidate.entry_dt)
        max_exit_dt = candidate.entry_dt + pd.Timedelta(minutes=max_hold_minutes)
        scan = bars.iloc[start_pos :].loc[:max_exit_dt]
        if scan.empty:
            continue

        exit_dt = scan.index[-1]
        exit_price = float(scan.iloc[-1].close)
        exit_signal = "TIME LIMIT"

        for j, (ts, row) in enumerate(scan.iterrows()):
            if candidate.side == "long":
                hit_stop = float(row.low) <= candidate.stop_price
                hit_target = float(row.high) >= candidate.target_price
            else:
                hit_stop = float(row.high) >= candidate.stop_price
                hit_target = float(row.low) <= candidate.target_price

            if hit_stop or hit_target:
                exit_dt = ts
                if hit_stop and hit_target:
                    exit_price = candidate.stop_price
                    exit_signal = "SL_TIE"
                elif hit_stop:
                    exit_price = candidate.stop_price
                    exit_signal = "SL"
                else:
                    exit_price = candidate.target_price
                    exit_signal = "TP"
                break

        gross_points = (
            exit_price - candidate.entry_price
            if candidate.side == "long"
            else candidate.entry_price - exit_price
        )
        pnl_nq = gross_points * NQ_POINT_VALUE - TV_ROUND_TRIP_COMMISSION
        pnl_mnq = gross_points * MNQ_POINT_VALUE - TV_ROUND_TRIP_COMMISSION
        trades.append(
            SimTrade(
                trade_no=trade_no,
                side=candidate.side,
                signal_dt=str(candidate.signal_dt),
                entry_dt=str(candidate.entry_dt),
                exit_dt=str(exit_dt),
                entry_price=round(candidate.entry_price, 2),
                exit_price=round(exit_price, 2),
                qty=1,
                pnl_nq_usd=round(pnl_nq, 2),
                pnl_mnq_usd=round(pnl_mnq, 2),
                exit_signal=exit_signal,
                source=candidate.source,
                sweep_dt=str(candidate.sweep_dt),
                fvg_dt=str(candidate.fvg_dt),
                stop_price=round(candidate.stop_price, 2),
                target_price=round(candidate.target_price, 2),
                risk_points=round(candidate.risk_points, 2),
                atr=round(candidate.atr, 4),
            )
        )
        trade_no += 1
        trades_by_day[day_key] += 1
        open_until = exit_dt
        cooldown_idx = min(len(bars) - 1, bars.index.get_loc(exit_dt) + cooldown_bars)
        cooldown_until = bars.index[cooldown_idx]

    return trades


def sim_metrics(trades: list[SimTrade]) -> dict[str, Any]:
    if not trades:
        return {}
    pnl = [trade.pnl_nq_usd for trade in trades]
    gross_profit = sum(value for value in pnl if value > 0)
    gross_loss = -sum(value for value in pnl if value < 0)
    equity = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_dd = 0.0
    for trade in trades:
        equity += trade.pnl_nq_usd
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "trades": len(trades),
        "net_pnl_nq_usd": round(sum(pnl), 2),
        "net_pnl_mnq_scaled_usd": round(sum(trade.pnl_mnq_usd for trade in trades), 2),
        "wins": sum(value > 0 for value in pnl),
        "losses": sum(value < 0 for value in pnl),
        "win_rate": round(sum(value > 0 for value in pnl) / len(pnl), 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "max_closed_drawdown_usd": round(max_dd, 2),
        "side_counts": dict(Counter(trade.side for trade in trades)),
        "exit_signal_counts": dict(Counter(trade.exit_signal for trade in trades)),
        "source_counts": dict(Counter(trade.source for trade in trades)),
    }


def parity(sim: list[SimTrade], export: list[ExportTrade]) -> dict[str, Any]:
    sim_keys = {(pd.Timestamp(trade.entry_dt), trade.side) for trade in sim}
    export_keys = {(trade.entry_dt, trade.side) for trade in export}
    matched = sim_keys & export_keys

    sim_by_key = {(pd.Timestamp(trade.entry_dt), trade.side): trade for trade in sim}
    export_by_key = {(trade.entry_dt, trade.side): trade for trade in export}
    matched_deltas = []
    for key in sorted(matched):
        sim_trade = sim_by_key[key]
        export_trade = export_by_key[key]
        matched_deltas.append(
            {
                "entry_dt": str(key[0]),
                "side": key[1],
                "tv_trade_no": export_trade.trade_no,
                "sim_trade_no": sim_trade.trade_no,
                "tv_exit_dt": str(export_trade.exit_dt),
                "sim_exit_dt": sim_trade.exit_dt,
                "tv_pnl_usd": export_trade.pnl_usd,
                "sim_pnl_nq_usd": sim_trade.pnl_nq_usd,
                "pnl_delta_usd": round(sim_trade.pnl_nq_usd - export_trade.pnl_usd, 2),
            }
        )

    return {
        "matched_entries": len(matched),
        "tv_trades": len(export),
        "sim_trades": len(sim),
        "recall": round(len(matched) / len(export), 6) if export else 0.0,
        "precision": round(len(matched) / len(sim), 6) if sim else 0.0,
        "missing_count": len(export_keys - sim_keys),
        "extra_count": len(sim_keys - export_keys),
        "missing_export_entries": [
            {"entry_dt": str(dt), "side": side} for dt, side in sorted(export_keys - sim_keys)[:100]
        ],
        "extra_sim_entries": [
            {"entry_dt": str(dt), "side": side} for dt, side in sorted(sim_keys - export_keys)[:100]
        ],
        "matched_deltas": matched_deltas[:100],
    }


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_report(path: Path, summary: dict[str, Any]) -> None:
    best = summary["best_variant"]
    export = summary["export_metrics"]
    sim = best["sim_metrics"]
    lines = [
        "# ILM / iFVG Reverse Engineering Guide-Filter Probe",
        "",
        "## Inferred Anchors",
        "",
        "- TradingView export groups into 111 logical trades, all qty 1.",
        "- Export P&L uses NQ point value ($20/pt) with $5.70 round-trip commission.",
        "- MNQ execution scaling is roughly one-tenth of gross NQ point P&L, but commission treatment must be confirmed.",
        "- Weekday filter excludes Thursday; export has no Thursday trades.",
        "- Time-limit exits are exactly 90 minutes after entry.",
        "- Guide defaults: entry 02:00-11:00 NY, sweep+iFVG required, ATR(12 WMA) stop x1.6, target 2R, BE/partial off.",
        "",
        "## Export Metrics",
        "",
        f"- Trades: {export['trades']}",
        f"- Net P&L: ${export['net_pnl_nq_usd']:,.2f} NQ / ${export['net_pnl_mnq_scaled_usd']:,.2f} MNQ-scaled",
        f"- Win rate: {export['win_rate'] * 100:.2f}%",
        f"- Profit factor: {export['profit_factor']}",
        f"- Max equity drawdown from export MAE: ${export['max_intratrade_drawdown_usd']:,.2f}",
        f"- Max closed-trade drawdown: ${export['max_closed_drawdown_usd']:,.2f}",
        f"- Exit signals: `{export['exit_signal_counts']}`",
        "",
        "## Best Local Variant",
        "",
        f"- Name: `{best['name']}`",
        f"- Params: `{best['params']}`",
        f"- Entry recall: {best['parity']['recall'] * 100:.2f}% ({best['parity']['matched_entries']}/{best['parity']['tv_trades']})",
        f"- Entry precision: {best['parity']['precision'] * 100:.2f}% ({best['parity']['matched_entries']}/{best['parity']['sim_trades']})",
        f"- Sim trades: {sim.get('trades', 0)}",
        f"- Sim NQ P&L: ${sim.get('net_pnl_nq_usd', 0):,.2f}",
        f"- Sim win rate: {sim.get('win_rate', 0) * 100:.2f}%",
        f"- Sim PF: {sim.get('profit_factor')}",
        f"- Sources: `{sim.get('source_counts', {})}`",
        "",
        "## What Matched / Failed",
        "",
        "- The scaffold reproduces the guide's core sweep -> FVG -> inversion lifecycle and confirms several export-level execution anchors.",
        "- Price-level parity is intentionally not used because local NQ history is unadjusted while the TradingView NQ1! export is back-adjusted in older years.",
        "- The guide-like inversion7 variant materially improves entry recall, which suggests the exported strategy really is centered on sweep -> FVG -> 7-bar iFVG confirmation.",
        "- The broad Algo Inversion proxy improves precision at a modest recall cost; the stricter 10-candle zone proxy is much cleaner but misses too many exported entries.",
        "- Rolling 100-bar sweep cutoff is now modeled; it has only a small effect, so it is not the main missing selectivity gate.",
        "- The trend-following HH/HL/LH/LL proxy is too strict when combined with the other guide filters; a contrarian breach-state probe is more plausible for this sweep-reversal entry, but still does not fully explain the export.",
        "- Precision remains low, so the remaining gap is selectivity: the exact Algo Inversion/reversal filter and market-structure state are still not replicated.",
        "- Exit parity is also first-pass only: the script uses 5-minute OHLC path assumptions for ATR stop/2R/90-minute exits, while TradingView uses bar magnifier/intrabar fills.",
        "",
        "## Recommended Next Tests",
        "",
        "1. Refine the Algo Inversion proxy against the exact v22.7 behavior: lookback=2, candle lookback=10, confirm within=3, volume confirmation, EMA trend MA=50, MA step=33.",
        "2. Continue market-structure probing around breach timing: TradingView appears to reject trend-following HH/HL semantics for many true export trades.",
        "3. Rebuild with more TradingView 5-minute history if available, then add 1-second exit replay after entry recall/precision are closer.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_tradingview_window_probe(
    tv_5m_csv: Path,
    export_trades: list[ExportTrade],
    output_dir: Path,
) -> dict[str, Any]:
    raw_bars = load_tradingview_5m_csv(tv_5m_csv)
    bars = add_level_columns(add_indicators(raw_bars))
    window_export = [
        trade
        for trade in export_trades
        if raw_bars.index.min() <= trade.entry_dt <= raw_bars.index.max()
    ]
    if not window_export:
        return {
            "tv_5m_csv": str(tv_5m_csv),
            "rows": len(raw_bars),
            "start": str(raw_bars.index.min()),
            "end": str(raw_bars.index.max()),
            "export_trades_in_window": 0,
            "variants": [],
            "best_variant": None,
        }

    base_params = {
        "sources": ("asia", "london", "preny", "pd", "pw"),
        "max_bars_after_sweep": 25,
        "fvg_window_bars": 25,
        "min_gap_points": 0.25,
        "max_gap_points": None,
        "entry_timing": "next_open",
        "inversion_lookback_bars": 7,
        "sweep_cutoff_lookback_bars": 100,
        "max_sweeps_per_major_level": 2,
    }
    variants = [
        {"name": "tv_basic", **base_params, "filters": ()},
        {"name": "tv_pd_only", **base_params, "filters": ("premium_discount",)},
        {"name": "tv_pd_ut_proxy", **base_params, "filters": ("premium_discount", "ut_proxy")},
        {"name": "tv_pd_exact_ub", **base_params, "filters": ("premium_discount", "tv_ub_filter")},
        {
            "name": "tv_pd_exact_ub_reversal_ma",
            **base_params,
            "filters": ("premium_discount", "tv_ub_filter", "tv_reversal_ma_mean_revert"),
        },
        {
            "name": "tv_pd_exact_ub_reversal_ma_min10",
            **base_params,
            "filters": (
                "premium_discount",
                "tv_ub_filter",
                "tv_reversal_ma_mean_revert",
                "tv_reversal_ma_min_distance",
            ),
        },
        {
            "name": "tv_pd_ut_proxy_reversal_ma",
            **base_params,
            "filters": ("premium_discount", "ut_proxy", "tv_reversal_ma_mean_revert"),
        },
        {
            "name": "tv_pd_ut_proxy_reversal_ma_min10",
            **base_params,
            "filters": (
                "premium_discount",
                "ut_proxy",
                "tv_reversal_ma_mean_revert",
                "tv_reversal_ma_min_distance",
            ),
        },
        {
            "name": "tv_pd_ut_proxy_reversal_ma_min10_inv5",
            **base_params,
            "filters": (
                "premium_discount",
                "ut_proxy",
                "tv_reversal_ma_mean_revert",
                "tv_reversal_ma_min_distance",
            ),
            "inversion_lookback_bars": 5,
        },
        {
            "name": "tv_pd_exact_ub_reversal_ma_min10_sweepgap4",
            **base_params,
            "filters": (
                "premium_discount",
                "tv_ub_filter",
                "tv_reversal_ma_mean_revert",
                "tv_reversal_ma_min_distance",
            ),
            "_candidate_min_bars_sweep_to_gap": 4,
        },
    ]

    variant_results: list[dict[str, Any]] = []
    for variant in variants:
        name = str(variant["name"])
        params = {key: value for key, value in variant.items() if key != "name"}
        candidate_min_bars_sweep_to_gap = params.pop("_candidate_min_bars_sweep_to_gap", None)
        candidates = [
            candidate
            for candidate in build_candidates(bars, **params)
            if raw_bars.index.min() <= candidate.entry_dt <= raw_bars.index.max()
        ]
        if candidate_min_bars_sweep_to_gap is not None:
            candidates = [
                candidate
                for candidate in candidates
                if candidate.bars_sweep_to_gap >= int(candidate_min_bars_sweep_to_gap)
            ]
            params["_candidate_min_bars_sweep_to_gap"] = candidate_min_bars_sweep_to_gap
        sim_trades = simulate_candidates(bars, candidates)
        result = {
            "name": name,
            "params": {key: (list(value) if isinstance(value, tuple) else value) for key, value in params.items()},
            "candidate_count": len(candidates),
            "sim_metrics": sim_metrics(sim_trades),
            "parity": parity(sim_trades, window_export),
            "sim_trades": [asdict(trade) for trade in sim_trades],
        }
        variant_results.append(result)

    best = max(
        variant_results,
        key=lambda item: (
            item["parity"]["matched_entries"],
            item["parity"]["precision"],
            -abs(item["sim_metrics"].get("trades", 0) - len(window_export)),
        ),
    )
    write_csv(output_dir / "ilm_ifvg_tv_window_best_sim_trades.csv", best["sim_trades"])

    return {
        "tv_5m_csv": str(tv_5m_csv),
        "rows": len(raw_bars),
        "start": str(raw_bars.index.min()),
        "end": str(raw_bars.index.max()),
        "export_trades_in_window": len(window_export),
        "export_entries": [
            {"trade_no": trade.trade_no, "entry_dt": str(trade.entry_dt), "side": trade.side}
            for trade in window_export
        ],
        "indicator_columns_present": {
            "UB-Filter": "UB-Filter" in raw_bars.columns,
            "Reversal MA": "Reversal MA" in raw_bars.columns,
        },
        "variants": [
            {key: value for key, value in result.items() if key != "sim_trades"}
            for result in variant_results
        ],
        "best_variant": {key: value for key, value in best.items() if key != "sim_trades"},
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    export_trades = parse_export(args.export_csv)
    export_start = min(t.entry_dt for t in export_trades)
    export_end = max(t.exit_dt for t in export_trades)
    start = export_start - pd.Timedelta(days=10)
    end = export_end + pd.Timedelta(days=5)
    cache_path = output_dir / f"nq_5m_cache_{start:%Y%m%d}_{end:%Y%m%d}.parquet"

    bars = build_5m_cache(args.nq_1s, cache_path, start, end)
    bars = add_level_columns(add_indicators(bars))

    variants = [
        {
            "name": "guide_basic_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 7,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": (),
        },
        {
            "name": "guide_basic_close",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 7,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "close",
            "filters": (),
        },
        {
            "name": "local_pine_like_next_open",
            "sources": ("asia", "london", "pd"),
            "max_bars_after_sweep": 30,
            "fvg_window_bars": 10,
            "min_gap_points": 5.0,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": (),
        },
        {
            "name": "local_pine_like_ut_next_open",
            "sources": ("asia", "london", "pd"),
            "max_bars_after_sweep": 30,
            "fvg_window_bars": 10,
            "min_gap_points": 5.0,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("ut_proxy",),
        },
        {
            "name": "guide_like_inversion7_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy"),
            "inversion_lookback_bars": 7,
        },
        {
            "name": "guide_like_rolling_cutoff_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy"),
            "inversion_lookback_bars": 7,
            "sweep_cutoff_lookback_bars": 100,
            "max_sweeps_per_major_level": 2,
        },
        {
            "name": "guide_like_algo_reversal_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy", "algo_reversal_proxy"),
            "inversion_lookback_bars": 7,
        },
        {
            "name": "guide_like_algo_rolling_cutoff_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy", "algo_reversal_proxy"),
            "inversion_lookback_bars": 7,
            "sweep_cutoff_lookback_bars": 100,
            "max_sweeps_per_major_level": 2,
        },
        {
            "name": "guide_like_algo_breach_contra_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy", "algo_reversal_proxy", "market_structure_breach_contra"),
            "inversion_lookback_bars": 7,
        },
        {
            "name": "guide_like_algo_reversal_zone_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy", "algo_reversal_zone_proxy"),
            "inversion_lookback_bars": 7,
        },
        {
            "name": "guide_like_algo_zone_rolling_cutoff_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "ut_proxy", "algo_reversal_zone_proxy"),
            "inversion_lookback_bars": 7,
            "sweep_cutoff_lookback_bars": 100,
            "max_sweeps_per_major_level": 2,
        },
        {
            "name": "guide_like_full_filters_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 25,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "macro_premium_discount", "ut_proxy", "market_structure"),
            "inversion_lookback_bars": 7,
        },
        {
            "name": "guide_pd_proxy_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 7,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount",),
        },
        {
            "name": "guide_pd_macro_next_open",
            "sources": ("asia", "london", "preny", "pd", "pw"),
            "max_bars_after_sweep": 25,
            "fvg_window_bars": 7,
            "min_gap_points": 0.25,
            "max_gap_points": None,
            "entry_timing": "next_open",
            "filters": ("premium_discount", "macro_premium_discount"),
        },
    ]

    variant_results: list[dict[str, Any]] = []
    for variant in variants:
        params = {key: value for key, value in variant.items() if key != "name"}
        candidates = build_candidates(bars, **params)
        candidates = [candidate for candidate in candidates if export_start <= candidate.entry_dt <= export_end]
        sim_trades = simulate_candidates(bars, candidates)
        result = {
            "name": variant["name"],
            "params": {key: (list(value) if isinstance(value, tuple) else value) for key, value in params.items()},
            "candidate_count": len(candidates),
            "sim_metrics": sim_metrics(sim_trades),
            "parity": parity(sim_trades, export_trades),
            "sim_trades": [asdict(trade) for trade in sim_trades],
        }
        variant_results.append(result)

    best = max(
        variant_results,
        key=lambda item: (
            item["parity"]["matched_entries"],
            item["parity"]["precision"],
            -abs(item["sim_metrics"].get("trades", 0) - len(export_trades)),
        ),
    )

    summary = {
        "inputs": {
            "export_csv": str(args.export_csv),
            "nq_1s": str(args.nq_1s),
            "cache_path": str(cache_path),
            "local_data_note": "Local NQ data is unadjusted; TradingView NQ1! export appears back-adjusted before 2026.",
        },
        "export_metrics": export_metrics(export_trades),
        "variants": [
            {key: value for key, value in result.items() if key != "sim_trades"} for result in variant_results
        ],
        "best_variant": {key: value for key, value in best.items() if key != "sim_trades"},
    }
    if args.tv_5m_csv is not None:
        summary["tradingview_window_probe"] = run_tradingview_window_probe(
            args.tv_5m_csv,
            export_trades,
            output_dir,
        )

    (output_dir / "ilm_ifvg_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_csv(output_dir / "ilm_ifvg_export_trades.csv", [asdict(trade) for trade in export_trades])
    write_csv(output_dir / "ilm_ifvg_best_sim_trades.csv", best["sim_trades"])
    write_report(output_dir / "ilm_ifvg_report.md", summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-csv", type=Path, default=DEFAULT_EXPORT)
    parser.add_argument("--nq-1s", type=Path, default=DEFAULT_NQ_1S)
    parser.add_argument(
        "--tv-5m-csv",
        type=Path,
        default=None,
        help="Optional TradingView 5m OHLC+indicator CSV for a visible-window parity probe",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    summary = run(args)
    print(json.dumps(summary["best_variant"], indent=2))


if __name__ == "__main__":
    main()
