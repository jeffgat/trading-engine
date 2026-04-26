#!/usr/bin/env python3
"""Run a Hunter/Classic ORB replication against NQ 1s data.

The goal is parity research against the TradingView N4A ORB export, not a
production strategy module. It implements the rules inferred from screenshots,
the settings guide, and exported trades.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq


POINT_VALUE = 20.0
COMMISSION_PER_CONTRACT_ROUND_TRIP = 3.60
INITIAL_CAPITAL = 10_000.0

ORB_START = "09:30"
ORB_SIGNAL_END = "09:40"
SIGNAL_START = "09:45"
SIGNAL_END = "10:55"
ALLOWED_WEEKDAYS = {0, 2, 3, 4}  # Mon, Wed, Thu, Fri.

BODY_MIN_PCT = 55.0
REJECTION_WICK_MAX_PCT = 20.0
SL_BUFFER_POINTS = 1.0
HUNTER_TARGET_RR = 2.0
LARGE_SL_THRESHOLD_POINTS = 50.0
REDUCED_TARGET_RR = 1.0
MAX_REENTRIES_AFTER_LOSS = 1
MAX_HOLD_MINUTES = 270
MAX_RISK_USD = 350.0
MAX_CONTRACTS = 20
DEFAULT_REENTRY_POLICY = "after_each_loss"
DEFAULT_EMA15_SOURCE = "close"
DEFAULT_EMA15_TIMING = "confirmed_prev"
DEFAULT_EMA15_TOLERANCE_POINTS = 2.0
DEFAULT_ALLOW_SAME_BAR_WIN_REENTRY = False
DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES = 5.0
DEFAULT_REENTRY_MAX_EXTENSION_PCT: float | None = None
DEFAULT_ENABLE_FAST_REENTRY_EXHAUSTION_FILTER = False
DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_MINUTES = 10.1
DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_EXTENSION_PCT = 12.0
DEFAULT_FAST_REENTRY_EXHAUSTION_MIN_EMA15_DISTANCE = 50.0


@dataclass(frozen=True)
class ExportTrade:
    trade_no: int
    side: str
    entry_dt: pd.Timestamp
    exit_dt: pd.Timestamp
    entry_price: float
    exit_price: float
    qty: int
    pnl_usd: float
    mfe_usd: float
    mae_usd: float
    exit_signal: str


@dataclass(frozen=True)
class Candidate:
    signal_dt: pd.Timestamp
    entry_dt: pd.Timestamp
    side: str
    orb_high: float
    orb_low: float
    signal_open: float
    signal_high: float
    signal_low: float
    signal_close: float
    body_pct: float
    rejection_wick_pct: float
    extension_pct: float
    ema15_distance_points: float | None = None


@dataclass(frozen=True)
class SimTrade:
    trade_no: int
    side: str
    signal_dt: str
    entry_dt: str
    exit_dt: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    risk_points: float
    rr: float
    qty: int
    pnl_usd: float
    mfe_usd: float
    mae_usd: float
    exit_signal: str
    body_pct: float
    rejection_wick_pct: float
    extension_pct: float


def read_export(path: Path) -> list[ExportTrade]:
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
                qty=int(float(entry["Size (qty)"])),
                pnl_usd=float(entry["Net P&L USD"]),
                mfe_usd=float(entry["Favorable excursion USD"]),
                mae_usd=float(entry["Adverse excursion USD"]),
                exit_signal=exit_["Signal"],
            )
        )
    return trades


def load_1s(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    table = pq.read_table(path, filters=[("datetime", ">=", start), ("datetime", "<", end)])
    df = table.to_pandas().sort_index()
    if df.empty:
        raise ValueError(f"No 1s rows loaded from {path} for {start} -> {end}")
    return df


def resample_5m(df_1s: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1s.resample("5min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )


def body_rejection(row: pd.Series, side: str) -> tuple[float, float]:
    candle_range = float(row.high - row.low)
    if candle_range <= 0:
        return 0.0, 100.0
    body_pct = abs(float(row.close - row.open)) / candle_range * 100.0
    if side == "long":
        rejection_pct = (float(row.high) - max(float(row.open), float(row.close))) / candle_range * 100.0
    else:
        rejection_pct = (min(float(row.open), float(row.close)) - float(row.low)) / candle_range * 100.0
    return body_pct, rejection_pct


def ema_source(df: pd.DataFrame, source: str) -> pd.Series:
    if source == "close":
        return df["close"]
    if source == "hl2":
        return (df["high"] + df["low"]) / 2.0
    if source == "hlc3":
        return (df["high"] + df["low"] + df["close"]) / 3.0
    if source == "ohlc4":
        return (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    raise ValueError(f"Unknown EMA15 source: {source}")


def add_ema15_bias(
    bars_5m: pd.DataFrame,
    length: int,
    *,
    source: str,
    timing: str,
) -> pd.DataFrame:
    bars = bars_5m.copy()
    bars_15m = (
        bars.resample("15min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    ema_15m = ema_source(bars_15m, source).ewm(span=length, adjust=False).mean()
    if timing == "current_final":
        ema_values = ema_15m.reindex(bars.index, method="ffill")
    elif timing == "confirmed_prev":
        ema_values = ema_15m.shift(1).reindex(bars.index, method="ffill")
    else:
        raise ValueError(f"Unknown EMA15 timing: {timing}")
    bars["ema15_bias"] = ema_values
    return bars


def build_candidates(
    bars_5m: pd.DataFrame,
    *,
    ema15_close_bias_length: int | None = None,
    ema15_max_distance: float | None = None,
    ema15_source: str = DEFAULT_EMA15_SOURCE,
    ema15_timing: str = DEFAULT_EMA15_TIMING,
    ema15_tolerance_points: float = DEFAULT_EMA15_TOLERANCE_POINTS,
) -> list[Candidate]:
    if ema15_close_bias_length is not None:
        bars_5m = add_ema15_bias(
            bars_5m,
            ema15_close_bias_length,
            source=ema15_source,
            timing=ema15_timing,
        )

    candidates: list[Candidate] = []
    for day, group in bars_5m.groupby(bars_5m.index.date):
        if pd.Timestamp(day).weekday() not in ALLOWED_WEEKDAYS:
            continue

        orb = group.between_time(ORB_START, ORB_SIGNAL_END)
        if len(orb) < 3:
            continue
        orb_high = float(orb.high.max())
        orb_low = float(orb.low.min())
        orb_range = max(orb_high - orb_low, 1e-9)

        for signal_dt, row in group.between_time(SIGNAL_START, SIGNAL_END).iterrows():
            pos = group.index.get_loc(signal_dt)
            if pos == 0:
                continue
            previous_close = float(group.iloc[pos - 1].close)
            raw_sides: list[str] = []
            if float(row.close) > orb_high and previous_close <= orb_high:
                raw_sides.append("long")
            if float(row.close) < orb_low and previous_close >= orb_low:
                raw_sides.append("short")

            for side in raw_sides:
                ema15_distance_points = None
                if ema15_close_bias_length is not None:
                    ema_value = float(row.ema15_bias)
                    if side == "long":
                        distance = float(row.close) - ema_value
                        if distance < -ema15_tolerance_points:
                            continue
                        if ema15_max_distance is not None and distance > ema15_max_distance:
                            continue
                    else:
                        distance = ema_value - float(row.close)
                        if distance < -ema15_tolerance_points:
                            continue
                        if ema15_max_distance is not None and distance > ema15_max_distance:
                            continue
                    ema15_distance_points = distance

                body_pct, rejection_pct = body_rejection(row, side)
                if body_pct < BODY_MIN_PCT or rejection_pct > REJECTION_WICK_MAX_PCT:
                    continue
                extension_pct = (
                    (float(row.close) - orb_high) / orb_range * 100.0
                    if side == "long"
                    else (orb_low - float(row.close)) / orb_range * 100.0
                )
                candidates.append(
                    Candidate(
                        signal_dt=signal_dt,
                        entry_dt=signal_dt + pd.Timedelta(minutes=5),
                        side=side,
                        orb_high=orb_high,
                        orb_low=orb_low,
                        signal_open=float(row.open),
                        signal_high=float(row.high),
                        signal_low=float(row.low),
                        signal_close=float(row.close),
                        body_pct=body_pct,
                        rejection_wick_pct=rejection_pct,
                        extension_pct=extension_pct,
                        ema15_distance_points=ema15_distance_points,
                    )
                )
    return candidates


def contracts_for_risk(risk_points: float) -> int:
    if risk_points <= 0:
        return 1
    raw = int(MAX_RISK_USD // (risk_points * POINT_VALUE))
    return max(1, min(MAX_CONTRACTS, raw))


def simulate_exit(candidate: Candidate, df_1s: pd.DataFrame, trade_no: int) -> SimTrade | None:
    if candidate.entry_dt not in df_1s.index:
        start_slice = df_1s.loc[candidate.entry_dt : candidate.entry_dt + pd.Timedelta(minutes=5)]
        if start_slice.empty:
            return None
        entry_dt = start_slice.index[0]
    else:
        entry_dt = candidate.entry_dt

    entry_price = float(df_1s.loc[entry_dt].open)
    if candidate.side == "long":
        stop_price = candidate.signal_low - SL_BUFFER_POINTS
        risk_points = entry_price - stop_price
        rr = REDUCED_TARGET_RR if risk_points >= LARGE_SL_THRESHOLD_POINTS else HUNTER_TARGET_RR
        target_price = entry_price + risk_points * rr
    else:
        stop_price = candidate.signal_high + SL_BUFFER_POINTS
        risk_points = stop_price - entry_price
        rr = REDUCED_TARGET_RR if risk_points >= LARGE_SL_THRESHOLD_POINTS else HUNTER_TARGET_RR
        target_price = entry_price - risk_points * rr

    if risk_points <= 0:
        return None

    qty = contracts_for_risk(risk_points)
    max_hold_cutoff = entry_dt + pd.Timedelta(minutes=MAX_HOLD_MINUTES)
    scan = df_1s.loc[entry_dt : max_hold_cutoff + pd.Timedelta(minutes=10)]
    if scan.empty:
        return None

    mfe_points = 0.0
    mae_points = 0.0
    exit_dt = scan.index[-1]
    exit_price = float(scan.iloc[-1].close)
    exit_signal = "Max Hold Time"

    for ts, row in scan.iterrows():
        if candidate.side == "long":
            mfe_points = max(mfe_points, float(row.high) - entry_price)
            mae_points = min(mae_points, float(row.low) - entry_price)
            hit_stop = float(row.low) <= stop_price
            hit_target = float(row.high) >= target_price
        else:
            mfe_points = max(mfe_points, entry_price - float(row.low))
            mae_points = min(mae_points, entry_price - float(row.high))
            hit_stop = float(row.high) >= stop_price
            hit_target = float(row.low) <= target_price

        if hit_stop or hit_target:
            exit_dt = ts
            if hit_stop and hit_target:
                # Conservative tie-breaker. TradingView bar magnifier has a path;
                # same-second OHLC does not, so stop-first avoids optimistic ties.
                exit_price = stop_price
            elif hit_stop:
                exit_price = stop_price
            else:
                exit_price = target_price
            exit_signal = "Hunter 2R"
            break

        if ts >= max_hold_cutoff:
            exit_dt = ts
            exit_price = float(row.close)
            exit_signal = "Max Hold Time"
            break

    gross_points = exit_price - entry_price if candidate.side == "long" else entry_price - exit_price
    pnl_usd = gross_points * POINT_VALUE * qty - COMMISSION_PER_CONTRACT_ROUND_TRIP * qty
    return SimTrade(
        trade_no=trade_no,
        side=candidate.side,
        signal_dt=str(candidate.signal_dt),
        entry_dt=str(entry_dt),
        exit_dt=str(exit_dt),
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        stop_price=round(stop_price, 2),
        target_price=round(target_price, 2),
        risk_points=round(risk_points, 2),
        rr=rr,
        qty=qty,
        pnl_usd=round(pnl_usd, 2),
        mfe_usd=round(mfe_points * POINT_VALUE * qty, 2),
        mae_usd=round(mae_points * POINT_VALUE * qty, 2),
        exit_signal=exit_signal,
        body_pct=round(candidate.body_pct, 4),
        rejection_wick_pct=round(candidate.rejection_wick_pct, 4),
        extension_pct=round(candidate.extension_pct, 4),
    )


def can_take_candidate(
    candidate: Candidate,
    day_trades: list[SimTrade],
    open_until: pd.Timestamp | None,
    reentry_policy: str,
    *,
    allow_same_bar_win_reentry: bool = DEFAULT_ALLOW_SAME_BAR_WIN_REENTRY,
    same_bar_win_reentry_max_minutes: float = DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
    reentry_max_extension_pct: float | None = DEFAULT_REENTRY_MAX_EXTENSION_PCT,
    enable_fast_reentry_exhaustion_filter: bool = DEFAULT_ENABLE_FAST_REENTRY_EXHAUSTION_FILTER,
    fast_reentry_exhaustion_max_minutes: float = DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_MINUTES,
    fast_reentry_exhaustion_max_extension_pct: float = DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_EXTENSION_PCT,
    fast_reentry_exhaustion_min_ema15_distance: float = DEFAULT_FAST_REENTRY_EXHAUSTION_MIN_EMA15_DISTANCE,
) -> bool:
    if open_until is not None and candidate.entry_dt <= open_until:
        return False
    if not day_trades:
        return True

    if reentry_max_extension_pct is not None and candidate.extension_pct > reentry_max_extension_pct:
        return False

    last_trade = day_trades[-1]
    last_trade_lost = last_trade.pnl_usd < 0 and last_trade.exit_signal == "Hunter 2R"
    last_trade_won = last_trade.pnl_usd > 0 and last_trade.exit_signal == "Hunter 2R"
    last_entry_dt = pd.Timestamp(last_trade.entry_dt)
    last_exit_dt = pd.Timestamp(last_trade.exit_dt)
    minutes_from_last_exit = (candidate.entry_dt - last_exit_dt).total_seconds() / 60.0
    same_bar_win = (
        last_trade_won
        and (last_exit_dt - last_entry_dt).total_seconds() / 60.0 <= same_bar_win_reentry_max_minutes
    )
    if (
        enable_fast_reentry_exhaustion_filter
        and last_trade_lost
        and minutes_from_last_exit <= fast_reentry_exhaustion_max_minutes
        and candidate.extension_pct <= fast_reentry_exhaustion_max_extension_pct
        and candidate.ema15_distance_points is not None
        and candidate.ema15_distance_points >= fast_reentry_exhaustion_min_ema15_distance
    ):
        return False

    if reentry_policy == "legacy_one_reentry_after_loss":
        allowed_by_policy = len(day_trades) == 1 and last_trade_lost
    elif reentry_policy == "after_each_loss":
        allowed_by_policy = last_trade_lost
    elif reentry_policy == "all_nonoverlap":
        allowed_by_policy = True
    else:
        raise ValueError(
            "Unknown reentry_policy. Expected one of: "
            "legacy_one_reentry_after_loss, after_each_loss, all_nonoverlap"
        )

    return allowed_by_policy or (allow_same_bar_win_reentry and same_bar_win)


def run_strategy(
    df_1s: pd.DataFrame,
    *,
    ema15_close_bias_length: int | None = None,
    ema15_max_distance: float | None = None,
    ema15_source: str = DEFAULT_EMA15_SOURCE,
    ema15_timing: str = DEFAULT_EMA15_TIMING,
    ema15_tolerance_points: float = DEFAULT_EMA15_TOLERANCE_POINTS,
    reentry_policy: str = DEFAULT_REENTRY_POLICY,
    allow_same_bar_win_reentry: bool = DEFAULT_ALLOW_SAME_BAR_WIN_REENTRY,
    same_bar_win_reentry_max_minutes: float = DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
    reentry_max_extension_pct: float | None = DEFAULT_REENTRY_MAX_EXTENSION_PCT,
    enable_fast_reentry_exhaustion_filter: bool = DEFAULT_ENABLE_FAST_REENTRY_EXHAUSTION_FILTER,
    fast_reentry_exhaustion_max_minutes: float = DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_MINUTES,
    fast_reentry_exhaustion_max_extension_pct: float = DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_EXTENSION_PCT,
    fast_reentry_exhaustion_min_ema15_distance: float = DEFAULT_FAST_REENTRY_EXHAUSTION_MIN_EMA15_DISTANCE,
) -> tuple[list[SimTrade], list[Candidate]]:
    bars_5m = resample_5m(df_1s)
    candidates = build_candidates(
        bars_5m,
        ema15_close_bias_length=ema15_close_bias_length,
        ema15_max_distance=ema15_max_distance,
        ema15_source=ema15_source,
        ema15_timing=ema15_timing,
        ema15_tolerance_points=ema15_tolerance_points,
    )
    candidates_by_day: dict[Any, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_day[candidate.entry_dt.date()].append(candidate)

    trades: list[SimTrade] = []
    trade_no = 1
    for day in sorted(candidates_by_day):
        day_candidates = sorted(candidates_by_day[day], key=lambda c: c.entry_dt)
        day_trades: list[SimTrade] = []
        open_until: pd.Timestamp | None = None

        for candidate in day_candidates:
            if not can_take_candidate(
                candidate,
                day_trades,
                open_until,
                reentry_policy,
                allow_same_bar_win_reentry=allow_same_bar_win_reentry,
                same_bar_win_reentry_max_minutes=same_bar_win_reentry_max_minutes,
                reentry_max_extension_pct=reentry_max_extension_pct,
                enable_fast_reentry_exhaustion_filter=enable_fast_reentry_exhaustion_filter,
                fast_reentry_exhaustion_max_minutes=fast_reentry_exhaustion_max_minutes,
                fast_reentry_exhaustion_max_extension_pct=fast_reentry_exhaustion_max_extension_pct,
                fast_reentry_exhaustion_min_ema15_distance=fast_reentry_exhaustion_min_ema15_distance,
            ):
                continue

            trade = simulate_exit(candidate, df_1s, trade_no)
            if trade is None:
                continue
            trades.append(trade)
            day_trades.append(trade)
            trade_no += 1
            open_until = pd.Timestamp(trade.exit_dt)

    return trades, candidates


def metrics(trades: list[SimTrade]) -> dict[str, Any]:
    if not trades:
        return {}
    pnl = [trade.pnl_usd for trade in trades]
    gross_profit = sum(x for x in pnl if x > 0)
    gross_loss = -sum(x for x in pnl if x < 0)
    equity = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_closed_dd = 0.0
    max_intratrade_dd = 0.0
    max_intratrade_dd_pct = 0.0
    for trade in trades:
        trough = equity + min(0.0, trade.mae_usd)
        intratrade_dd = peak - trough
        if intratrade_dd > max_intratrade_dd:
            max_intratrade_dd = intratrade_dd
            max_intratrade_dd_pct = intratrade_dd / peak * 100.0 if peak else 0.0
        equity += trade.pnl_usd
        peak = max(peak, equity)
        max_closed_dd = max(max_closed_dd, peak - equity)

    return {
        "trades": len(trades),
        "net_pnl_usd": round(sum(pnl), 2),
        "return_pct_on_10k": round(sum(pnl) / INITIAL_CAPITAL * 100.0, 4),
        "wins": sum(x > 0 for x in pnl),
        "win_rate": round(sum(x > 0 for x in pnl) / len(pnl), 6),
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss else None,
        "max_closed_drawdown_usd": round(max_closed_dd, 2),
        "max_intratrade_drawdown_usd": round(max_intratrade_dd, 2),
        "max_intratrade_drawdown_pct": round(max_intratrade_dd_pct, 4),
        "side_counts": dict(Counter(trade.side for trade in trades)),
        "exit_counts": dict(Counter(trade.exit_signal for trade in trades)),
        "qty_counts": dict(Counter(str(trade.qty) for trade in trades)),
    }


def export_metrics(export_trades: list[ExportTrade]) -> dict[str, Any]:
    pnl = [trade.pnl_usd for trade in export_trades]
    gross_profit = sum(x for x in pnl if x > 0)
    gross_loss = -sum(x for x in pnl if x < 0)
    equity = INITIAL_CAPITAL
    peak = INITIAL_CAPITAL
    max_closed_dd = 0.0
    max_intratrade_dd = 0.0
    max_intratrade_dd_pct = 0.0
    for trade in export_trades:
        trough = equity + min(0.0, trade.mae_usd)
        intratrade_dd = peak - trough
        if intratrade_dd > max_intratrade_dd:
            max_intratrade_dd = intratrade_dd
            max_intratrade_dd_pct = intratrade_dd / peak * 100.0 if peak else 0.0
        equity += trade.pnl_usd
        peak = max(peak, equity)
        max_closed_dd = max(max_closed_dd, peak - equity)

    return {
        "trades": len(export_trades),
        "net_pnl_usd": round(sum(pnl), 2),
        "return_pct_on_10k": round(sum(pnl) / INITIAL_CAPITAL * 100.0, 4),
        "wins": sum(x > 0 for x in pnl),
        "win_rate": round(sum(x > 0 for x in pnl) / len(pnl), 6),
        "profit_factor": round(gross_profit / gross_loss, 6),
        "max_closed_drawdown_usd": round(max_closed_dd, 2),
        "max_intratrade_drawdown_usd": round(max_intratrade_dd, 2),
        "max_intratrade_drawdown_pct": round(max_intratrade_dd_pct, 4),
        "side_counts": dict(Counter(trade.side for trade in export_trades)),
        "exit_counts": dict(Counter(trade.exit_signal for trade in export_trades)),
        "qty_counts": dict(Counter(str(trade.qty) for trade in export_trades)),
    }


def compare_trades(sim_trades: list[SimTrade], export_trades: list[ExportTrade]) -> dict[str, Any]:
    sim_keys = {(pd.Timestamp(t.signal_dt) + pd.Timedelta(minutes=5), t.side) for t in sim_trades}
    export_keys = {(t.entry_dt, t.side) for t in export_trades}
    matched = sim_keys & export_keys
    return {
        "matched_entries": len(matched),
        "missing_export_entries": sorted([str(item) for item in export_keys - sim_keys])[:100],
        "extra_sim_entries": sorted([str(item) for item in sim_keys - export_keys])[:100],
        "missing_count": len(export_keys - sim_keys),
        "extra_count": len(sim_keys - export_keys),
    }


def write_csv(path: Path, trades: list[SimTrade]) -> None:
    if not trades:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(trades[0]).keys()))
        writer.writeheader()
        for trade in trades:
            writer.writerow(asdict(trade))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-1s", type=Path, default=Path("data/raw/NQ_1s.parquet"))
    parser.add_argument("--export-csv", type=Path, default=None)
    parser.add_argument("--start", default="2025-04-28")
    parser.add_argument("--end", default="2026-04-25")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ema15-close-bias-length", type=int, default=None)
    parser.add_argument("--ema15-max-distance", type=float, default=None)
    parser.add_argument(
        "--ema15-source",
        choices=["close", "hl2", "hlc3", "ohlc4"],
        default=DEFAULT_EMA15_SOURCE,
    )
    parser.add_argument(
        "--ema15-timing",
        choices=["confirmed_prev", "current_final"],
        default=DEFAULT_EMA15_TIMING,
        help=(
            "HTF EMA alignment. 'confirmed_prev' uses the last completed 15m EMA value; "
            "'current_final' uses the final value of the current 15m bucket."
        ),
    )
    parser.add_argument(
        "--ema15-tolerance-points",
        type=float,
        default=DEFAULT_EMA15_TOLERANCE_POINTS,
        help="Allowed wrong-side distance from the 15m EMA bias line before rejecting a candidate.",
    )
    parser.add_argument(
        "--reentry-policy",
        choices=["legacy_one_reentry_after_loss", "after_each_loss", "all_nonoverlap"],
        default=DEFAULT_REENTRY_POLICY,
        help=(
            "Hunter same-day re-entry state policy. The current inferred target is "
            "'after_each_loss': allow the next non-overlapping candidate after each losing Hunter exit."
        ),
    )
    parser.add_argument(
        "--allow-same-bar-win-reentry",
        action="store_true",
        default=DEFAULT_ALLOW_SAME_BAR_WIN_REENTRY,
        help=(
            "Also allow a same-day reentry after a winning Hunter exit when the win completes within "
            "--same-bar-win-reentry-max-minutes. This is a parity probe for the TradingView Hunter mode."
        ),
    )
    parser.add_argument(
        "--same-bar-win-reentry-max-minutes",
        type=float,
        default=DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
        help="Maximum entry-to-exit duration, in minutes, for a winning Hunter trade to qualify as same-bar.",
    )
    parser.add_argument(
        "--reentry-max-extension-pct",
        type=float,
        default=DEFAULT_REENTRY_MAX_EXTENSION_PCT,
        help="Optional ORB-extension cap applied only to same-day reentries, not first trades of the day.",
    )
    parser.add_argument(
        "--enable-fast-reentry-exhaustion-filter",
        action="store_true",
        default=DEFAULT_ENABLE_FAST_REENTRY_EXHAUSTION_FILTER,
        help=(
            "Parity probe: after a losing Hunter exit, reject very fast reentries that are still close "
            "to the ORB break but already far from the 15m EMA bias line."
        ),
    )
    parser.add_argument(
        "--fast-reentry-exhaustion-max-minutes",
        type=float,
        default=DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_MINUTES,
        help="Maximum minutes after a losing Hunter exit for the fast-reentry exhaustion filter.",
    )
    parser.add_argument(
        "--fast-reentry-exhaustion-max-extension-pct",
        type=float,
        default=DEFAULT_FAST_REENTRY_EXHAUSTION_MAX_EXTENSION_PCT,
        help="Maximum ORB extension percent for the fast-reentry exhaustion filter.",
    )
    parser.add_argument(
        "--fast-reentry-exhaustion-min-ema15-distance",
        type=float,
        default=DEFAULT_FAST_REENTRY_EXHAUSTION_MIN_EMA15_DISTANCE,
        help="Minimum 15m EMA distance, in points, for the fast-reentry exhaustion filter.",
    )
    args = parser.parse_args()

    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    df_1s = load_1s(args.data_1s, start, end)
    sim_trades, candidates = run_strategy(
        df_1s,
        ema15_close_bias_length=args.ema15_close_bias_length,
        ema15_max_distance=args.ema15_max_distance,
        ema15_source=args.ema15_source,
        ema15_timing=args.ema15_timing,
        ema15_tolerance_points=args.ema15_tolerance_points,
        reentry_policy=args.reentry_policy,
        allow_same_bar_win_reentry=args.allow_same_bar_win_reentry,
        same_bar_win_reentry_max_minutes=args.same_bar_win_reentry_max_minutes,
        reentry_max_extension_pct=args.reentry_max_extension_pct,
        enable_fast_reentry_exhaustion_filter=args.enable_fast_reentry_exhaustion_filter,
        fast_reentry_exhaustion_max_minutes=args.fast_reentry_exhaustion_max_minutes,
        fast_reentry_exhaustion_max_extension_pct=args.fast_reentry_exhaustion_max_extension_pct,
        fast_reentry_exhaustion_min_ema15_distance=args.fast_reentry_exhaustion_min_ema15_distance,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "sim_trades.csv", sim_trades)

    summary: dict[str, Any] = {
        "config": {
            "start": args.start,
            "end": args.end,
            "data_1s": str(args.data_1s),
            "available_data_start": str(df_1s.index.min()),
            "available_data_end": str(df_1s.index.max()),
            "initial_capital": INITIAL_CAPITAL,
            "max_risk_usd": MAX_RISK_USD,
            "point_value": POINT_VALUE,
            "ema15_close_bias_length": args.ema15_close_bias_length,
            "ema15_max_distance": args.ema15_max_distance,
            "ema15_source": args.ema15_source,
            "ema15_timing": args.ema15_timing,
            "ema15_tolerance_points": args.ema15_tolerance_points,
            "reentry_policy": args.reentry_policy,
            "allow_same_bar_win_reentry": args.allow_same_bar_win_reentry,
            "same_bar_win_reentry_max_minutes": args.same_bar_win_reentry_max_minutes,
            "reentry_max_extension_pct": args.reentry_max_extension_pct,
            "enable_fast_reentry_exhaustion_filter": args.enable_fast_reentry_exhaustion_filter,
            "fast_reentry_exhaustion_max_minutes": args.fast_reentry_exhaustion_max_minutes,
            "fast_reentry_exhaustion_max_extension_pct": args.fast_reentry_exhaustion_max_extension_pct,
            "fast_reentry_exhaustion_min_ema15_distance": args.fast_reentry_exhaustion_min_ema15_distance,
        },
        "candidate_count": len(candidates),
        "sim_metrics": metrics(sim_trades),
    }

    if args.export_csv is not None:
        export_trades_all = read_export(args.export_csv)
        export_trades_window = [
            trade for trade in export_trades_all if df_1s.index.min() <= trade.entry_dt <= df_1s.index.max()
        ]
        summary["export_metrics_full_csv"] = export_metrics(export_trades_all)
        summary["export_metrics_available_data_window"] = export_metrics(export_trades_window)
        summary["comparison_available_data_window"] = compare_trades(sim_trades, export_trades_window)

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
