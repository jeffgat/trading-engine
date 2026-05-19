"""Exact historical backtests using the live execution engines.

This runner replays local parquet data through the same ORBEngine / LSIEngine
state machines used in production, then serializes the filled trades into the
backtesting DB/frontend schema.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time as time_mod
import urllib.error
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .broker import MultiBroker, TradersPostClient
from .engine import Bar
from .feed import ATRCalculator, DailyHistoryTracker, ET
from .gates import normalize_regime_gates, set_daily_history_provider
from .main import (
    SESSION_CONFIGS,
    LSI_SESSION_CONFIGS,
    INSTRUMENTS,
    SIGNAL_TO_EXEC,
    build_engines,
    build_lsi_engines,
    load_exec_configs,
)
from .position_limits import ContractCapManager

ROOT = Path(__file__).resolve().parents[3]
RAW_DATA_DIR = ROOT / "backtesting" / "data" / "raw"
CACHE_DATA_DIRS = (
    ROOT / "backtesting" / "data" / "cache" / "nq_ny_lsi_cisd_sequence",
)
BACKTEST_REPORTING_RISK_USD = 5000.0

_INDEX_COL_CACHE: dict[Path, str] = {}
_EMPTY_TICK_FRAME = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
EXPERIMENTS_DB_URL = os.environ.get("EXPERIMENTS_DB_URL", "http://143.110.148.234:8100").rstrip("/")


def _parquet_index_column(path: Path) -> str:
    cached = _INDEX_COL_CACHE.get(path)
    if cached is not None:
        return cached
    names = list(pq.ParquetFile(path).schema_arrow.names)
    index_col = "datetime" if "datetime" in names else names[-1]
    _INDEX_COL_CACHE[path] = index_col
    return index_col


def _resolve_parquet_path(symbol: str, timeframe: str) -> Path:
    filename = f"{symbol}_{timeframe}.parquet"
    raw_path = RAW_DATA_DIR / filename
    if raw_path.exists():
        return raw_path
    for cache_dir in CACHE_DATA_DIRS:
        cache_path = cache_dir / filename
        if cache_path.exists():
            return cache_path
    return raw_path


def _read_parquet_frame(
    symbol: str,
    timeframe: str,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> pd.DataFrame:
    path = _resolve_parquet_path(symbol, timeframe)
    index_col = _parquet_index_column(path)
    filters: list[tuple[str, str, datetime]] = []
    if start is not None:
        filters.append((index_col, ">=", start.replace(tzinfo=None)))
    if end is not None:
        filters.append((index_col, "<", end.replace(tzinfo=None)))
    df = pd.read_parquet(path, filters=filters or None)
    if not isinstance(df.index, pd.DatetimeIndex):
        if index_col in df.columns:
            df = df.set_index(index_col)
        else:
            df.index = pd.to_datetime(df.index)
    df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize(ET)
    else:
        df.index = df.index.tz_convert(ET)
    return df.sort_index()


def _build_bar_events(symbol: str, frame: pd.DataFrame, *, bar_minutes: int) -> list[tuple[datetime, str, int, Bar]]:
    events: list[tuple[datetime, str, int, Bar]] = []
    for ts, row in frame.iterrows():
        bar = Bar(
            timestamp=ts.to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"] or 0),
        )
        close_time = ts.to_pydatetime() + timedelta(minutes=bar_minutes)
        events.append((close_time, symbol, bar_minutes, bar))
    return events


def _engine_bar_minutes(engine: Any) -> int:
    return int(getattr(engine, "base_bar_minutes", 5) or 5)


def _timeframe_for_minutes(bar_minutes: int) -> str:
    if bar_minutes == 1:
        return "1m"
    if bar_minutes == 3:
        return "3m"
    if bar_minutes == 5:
        return "5m"
    raise ValueError(f"Unsupported exact replay bar interval: {bar_minutes}m")


def _seed_daily_bars(symbol: str, replay_start: datetime, lookback_days: int = 90) -> list[tuple[date, float, float, float, float]]:
    seed_start = replay_start - timedelta(days=lookback_days)
    df_5m = _read_parquet_frame(symbol, "5m", start=seed_start, end=replay_start)
    if df_5m.empty:
        return []
    daily = df_5m.groupby(df_5m.index.date).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    )
    return [
        (d, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]))
        for d, row in daily.iterrows()
    ]


def _seed_ath_high(symbol: str, replay_start: datetime) -> float | None:
    df_5m = _read_parquet_frame(symbol, "5m", end=replay_start)
    if df_5m.empty:
        return None
    return float(df_5m["high"].max())


def _daily_history_provider_from_trackers(
    trackers: dict[str, DailyHistoryTracker],
):
    def _provider(symbol: str) -> list[tuple[date, float, float, float, float]]:
        tracker = trackers.get(symbol)
        if tracker is None:
            return []
        return tracker.snapshot(include_current=True)

    return _provider


def _active_for_ticks(engine: Any) -> bool:
    state = getattr(getattr(engine, "state", None), "value", "")
    return state in {"armed_limit", "filled", "managing"}


def _format_trade_date(session_date: str) -> str:
    if len(session_date) == 8 and session_date.isdigit():
        return f"{session_date[:4]}-{session_date[4:6]}-{session_date[6:8]}"
    return session_date


def _build_config_dict(profile_name: str, exec_config: Any) -> dict[str, Any]:
    config_dict: dict[str, Any] = {
        "instrument": "EXEC_PORTFOLIO",
        "strategy": "execution_exact_replay",
        "profile_name": profile_name,
        # Preserve the research backtester R denomination in saved history.
        "risk_usd": BACKTEST_REPORTING_RISK_USD,
    }

    for session_name, overrides in exec_config.session_overrides.items():
        merged = {**SESSION_CONFIGS.get(session_name, {}), **overrides}
        prefix = session_name.lower()
        regime_gates = normalize_regime_gates(
            merged.get("regime_gate"),
            merged.get("regime_gates"),
        )
        config_dict[f"{prefix}_entry_window"] = f"{merged['entry_start']}-{merged['entry_end']}"
        config_dict[f"{prefix}_flat_window"] = f"{merged['flat_start']}-{merged['flat_end']}"
        if "orb_start" in merged and "orb_end" in merged:
            config_dict[f"{prefix}_orb_window"] = f"{merged['orb_start']}-{merged['orb_end']}"
        for key in (
            "risk_usd",
            "atr_length",
            "rr",
            "tp1_ratio",
            "exit_mode",
            "stop_atr_pct",
            "stop_orb_pct",
            "min_gap_atr_pct",
            "min_gap_orb_pct",
            "ath_block_min_pct",
            "ath_block_max_pct",
            "runner_trail_mode",
            "runner_trail_trigger_r",
            "runner_trail_stop_r",
            "runner_trail_step_r",
            "runner_trail_gap_r",
            "runner_trail_atr_pct",
            "hunter_entry_basis",
        ):
            if key in merged:
                config_dict[f"{prefix}_{key}"] = merged[key]
        if regime_gates:
            config_dict[f"{prefix}_regime_gates"] = list(regime_gates)
            if len(regime_gates) == 1:
                config_dict[f"{prefix}_regime_gate"] = regime_gates[0]
        sess_instrument = merged.get("instrument", "NQ")
        exec_ticker = merged.get("exec_ticker") or SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, INSTRUMENTS.get(sess_instrument, {}))
        config_dict[f"{prefix}_exec_ticker"] = exec_ticker
        if exec_inst:
            config_dict[f"{prefix}_commission_per_contract"] = exec_inst["commission"]

    for session_name, overrides in exec_config.lsi_session_overrides.items():
        merged = {**LSI_SESSION_CONFIGS.get(session_name, {}), **overrides}
        prefix = session_name.lower()
        regime_gates = normalize_regime_gates(
            merged.get("regime_gate"),
            merged.get("regime_gates"),
        )
        config_dict[f"{prefix}_sweep_window"] = f"{merged.get('sweep_start', merged['entry_start'])}-{merged.get('sweep_end', merged['entry_end'])}"
        config_dict[f"{prefix}_entry_window"] = f"{merged['entry_start']}-{merged['entry_end']}"
        config_dict[f"{prefix}_flat_window"] = f"{merged['flat_start']}-{merged['flat_end']}"
        for key in (
            "risk_usd",
            "atr_length",
            "rr",
            "tp1_ratio",
            "exit_mode",
            "min_gap_atr_pct",
            "min_stop_points",
            "stop_atr_pct",
            "qty_multiplier",
            "lsi_entry_mode",
            "lsi_stop_mode",
            "lsi_target_mode",
            "lsi_confirmation_mode",
            "lsi_variant",
            "lsi_n_left",
            "lsi_n_right",
            "lsi_reset_swing_window_on_new_day",
            "fvg_window_left",
            "fvg_window_right",
            "cisd_min_leg_bars",
            "cisd_min_leg_atr_pct",
            "cisd_max_leg_bars",
            "base_bar_minutes",
            "htf_level_tf_minutes",
            "htf_n_left",
            "htf_trade_max_per_session",
            "max_fvg_to_inversion_bars",
        ):
            if key in merged:
                config_dict[f"{prefix}_{key}"] = merged[key]
        if regime_gates:
            config_dict[f"{prefix}_regime_gates"] = list(regime_gates)
            if len(regime_gates) == 1:
                config_dict[f"{prefix}_regime_gate"] = regime_gates[0]
        sess_instrument = merged.get("instrument", "NQ")
        exec_ticker = SIGNAL_TO_EXEC.get(sess_instrument, sess_instrument)
        exec_inst = INSTRUMENTS.get(exec_ticker, INSTRUMENTS.get(sess_instrument, {}))
        config_dict[f"{prefix}_exec_ticker"] = exec_ticker
        if exec_inst:
            config_dict[f"{prefix}_commission_per_contract"] = exec_inst["commission"]

    return config_dict


def _build_equity_curve(trades: list[dict], end_date: str) -> list[dict]:
    cumulative = 0.0
    curve: list[dict] = []
    ordered = sorted(
        trades,
        key=lambda trade: (
            trade.get("exit_time") or trade.get("entry_time") or "",
            trade["date"],
            trade["session"],
        ),
    )
    for trade in ordered:
        cumulative += float(trade["pnl_usd"])
        curve.append({
            "date": (trade.get("exit_time") or trade.get("entry_time") or trade["date"])[:10],
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(float(trade["pnl_usd"]), 2),
        })
    if curve:
        if curve[-1]["date"] != end_date:
            curve.append({
                "date": end_date,
                "pnl_cumulative": curve[-1]["pnl_cumulative"],
                "pnl_per_trade": 0.0,
            })
    else:
        curve.append({
            "date": end_date,
            "pnl_cumulative": 0.0,
            "pnl_per_trade": 0.0,
        })
    return curve


def _group_sum(trades: list[dict], key_fn, value_key: str) -> dict[str, float]:
    grouped: dict[str, float] = {}
    for trade in trades:
        key = key_fn(trade)
        grouped[key] = grouped.get(key, 0.0) + float(trade[value_key])
    return dict(sorted(grouped.items()))


def _compute_summary(trades: list[dict]) -> dict[str, Any]:
    if not trades:
        return {
            "total_signals": 0,
            "total_trades": 0,
            "no_fills": 0,
            "win_count": 0,
            "loss_count": 0,
            "be_count": 0,
            "win_rate": 0.0,
            "gross_pnl_usd": 0.0,
            "total_commission_usd": 0.0,
            "total_pnl_usd": 0.0,
            "avg_pnl_usd": 0.0,
            "avg_win_usd": 0.0,
            "avg_loss_usd": 0.0,
            "largest_win_usd": 0.0,
            "largest_loss_usd": 0.0,
            "profit_factor": 0.0,
            "avg_r": 0.0,
            "avg_net_r": 0.0,
            "avg_win_r": 0.0,
            "avg_loss_r": 0.0,
            "total_r": 0.0,
            "total_net_r": 0.0,
            "max_drawdown_usd": 0.0,
            "max_drawdown_pct": 0.0,
            "max_drawdown_r": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "max_consecutive_wins": 0,
            "max_consecutive_losses": 0,
            "exit_breakdown": {},
            "pnl_by_year": {},
            "pnl_by_month": {},
            "pnl_by_dow": {},
            "r_by_year": {},
            "long_trades": 0,
            "short_trades": 0,
            "long_win_rate": 0.0,
            "short_win_rate": 0.0,
            "long_pnl_usd": 0.0,
            "short_pnl_usd": 0.0,
            "long_r": 0.0,
            "short_r": 0.0,
        }

    pnl_usd = np.array([float(trade["pnl_usd"]) for trade in trades], dtype=float)
    r_values = np.array([float(trade["r_multiple"]) for trade in trades], dtype=float)
    net_r_values = np.array([
        float(trade.get("net_r_multiple", trade["r_multiple"]))
        for trade in trades
    ], dtype=float)
    gross_pnl_usd = np.array([
        float(trade.get("gross_pnl_usd", float(trade["pnl_usd"]) + float(trade.get("commission_usd", 0.0))))
        for trade in trades
    ], dtype=float)
    commission_usd = np.array([float(trade.get("commission_usd", 0.0)) for trade in trades], dtype=float)
    wins = pnl_usd > 0
    losses = pnl_usd < 0
    breakevens = pnl_usd == 0

    equity = np.cumsum(pnl_usd)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak
    max_dd = float(np.min(drawdown)) if len(drawdown) else 0.0
    max_dd_pct = 0.0
    if len(peak) and np.max(peak) > 0:
        dd_pct = drawdown / np.where(peak > 0, peak, 1.0) * 100.0
        max_dd_pct = float(np.min(dd_pct))

    r_equity = np.cumsum(r_values)
    r_peak = np.maximum.accumulate(r_equity)
    r_drawdown = r_equity - r_peak
    max_dd_r = float(np.min(r_drawdown)) if len(r_drawdown) else 0.0
    total_r = float(r_equity[-1]) if len(r_equity) else 0.0

    avg_r = float(np.mean(r_values)) if len(r_values) else 0.0
    std_r = float(np.std(r_values, ddof=1)) if len(r_values) > 1 else 0.0
    sharpe = (avg_r / std_r * np.sqrt(252.0)) if std_r > 0 else 0.0
    downside = np.minimum(r_values, 0.0)
    downside_std = float(np.sqrt(np.mean(downside ** 2))) if len(downside) else 0.0
    sortino = (avg_r / downside_std * np.sqrt(252.0)) if downside_std > 0 else 0.0
    calmar = (total_r / abs(max_dd_r)) if max_dd_r != 0 else 0.0

    exit_breakdown: dict[str, int] = {}
    for trade in trades:
        exit_breakdown[trade["exit_type"]] = exit_breakdown.get(trade["exit_type"], 0) + 1

    long_trades = [trade for trade in trades if trade["direction"] == "long"]
    short_trades = [trade for trade in trades if trade["direction"] == "short"]

    def _win_rate(items: list[dict]) -> float:
        if not items:
            return 0.0
        return sum(1 for item in items if float(item["pnl_usd"]) > 0) / len(items)

    def _max_consecutive(mask: np.ndarray) -> int:
        longest = 0
        current = 0
        for value in mask:
            if value:
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        return longest

    return {
        "total_signals": len(trades),
        "total_trades": len(trades),
        "no_fills": 0,
        "win_count": int(np.sum(wins)),
        "loss_count": int(np.sum(losses)),
        "be_count": int(np.sum(breakevens)),
        "win_rate": float(np.mean(wins)) if len(trades) else 0.0,
        "gross_pnl_usd": float(np.sum(gross_pnl_usd)),
        "total_commission_usd": float(np.sum(commission_usd)),
        "total_pnl_usd": float(np.sum(pnl_usd)),
        "avg_pnl_usd": float(np.mean(pnl_usd)) if len(trades) else 0.0,
        "avg_win_usd": float(np.mean(pnl_usd[wins])) if wins.any() else 0.0,
        "avg_loss_usd": float(np.mean(pnl_usd[losses])) if losses.any() else 0.0,
        "largest_win_usd": float(np.max(pnl_usd)) if len(trades) else 0.0,
        "largest_loss_usd": float(np.min(pnl_usd)) if len(trades) else 0.0,
        "profit_factor": abs(float(np.sum(pnl_usd[wins])) / float(np.sum(pnl_usd[losses]))) if losses.any() and float(np.sum(pnl_usd[losses])) != 0 else 0.0,
        "avg_r": avg_r,
        "avg_net_r": float(np.mean(net_r_values)) if len(trades) else 0.0,
        "avg_win_r": float(np.mean(r_values[wins])) if wins.any() else 0.0,
        "avg_loss_r": float(np.mean(r_values[losses])) if losses.any() else 0.0,
        "total_r": total_r,
        "total_net_r": float(np.sum(net_r_values)),
        "max_drawdown_usd": max_dd,
        "max_drawdown_pct": max_dd_pct,
        "max_drawdown_r": max_dd_r,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
        "max_consecutive_wins": _max_consecutive(wins),
        "max_consecutive_losses": _max_consecutive(losses),
        "exit_breakdown": exit_breakdown,
        "pnl_by_year": _group_sum(trades, lambda t: t["date"][:4], "pnl_usd"),
        "pnl_by_month": _group_sum(trades, lambda t: t["date"][:7], "pnl_usd"),
        "pnl_by_dow": _group_sum(
            trades,
            lambda t: datetime.fromisoformat(t["date"]).strftime("%a"),
            "pnl_usd",
        ),
        "r_by_year": _group_sum(trades, lambda t: t["date"][:4], "r_multiple"),
        "long_trades": len(long_trades),
        "short_trades": len(short_trades),
        "long_win_rate": _win_rate(long_trades),
        "short_win_rate": _win_rate(short_trades),
        "long_pnl_usd": float(sum(float(trade["pnl_usd"]) for trade in long_trades)),
        "short_pnl_usd": float(sum(float(trade["pnl_usd"]) for trade in short_trades)),
        "long_r": float(sum(float(trade["r_multiple"]) for trade in long_trades)),
        "short_r": float(sum(float(trade["r_multiple"]) for trade in short_trades)),
    }


def _slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _generate_result_id(result: dict) -> str:
    descriptor = _slugify(result.get("name", "exec-exact"))
    suffix = format(time_mod.time_ns() % (16**6), "06x")
    return f"bt-{descriptor}-{suffix}"


def _post_run(result: dict, result_id: str) -> None:
    payload = {
        "result_dict": result,
        "result_id": result_id,
        "run_type": "backtest",
    }
    req = urllib.request.Request(
        f"{EXPERIMENTS_DB_URL}/api/runs",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to save backtest to {EXPERIMENTS_DB_URL}: {exc}") from exc
    if not body.get("success"):
        raise RuntimeError(f"Remote save failed: {body.get('error')}")


@dataclass
class ReplayRecorder:
    """Collect filled trades from exact engine callbacks."""

    profile_name: str
    trade_history: list[Any]
    trades: list[dict]

    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self.trade_history = []
        self.trades = []

    def make_callback(self, engine: Any):
        def _record(record: Any) -> None:
            self.trade_history.append(record)
            levels = getattr(engine, "_levels", None)
            if levels is None:
                return
            risk_points = abs(float(levels.entry) - float(levels.stop))
            qty = float(levels.qty)
            r_multiple = float(record.r_result or 0.0)
            pnl_points = r_multiple * risk_points
            gross_pnl_usd = pnl_points * qty * float(engine.point_value)
            commission_per_contract = float(getattr(engine, "commission_per_contract", 0.0) or 0.0)
            commission_usd = 2.0 * qty * commission_per_contract
            pnl_usd = gross_pnl_usd - commission_usd
            gross_risk_usd = risk_points * qty * float(engine.point_value)
            net_r_multiple = pnl_usd / gross_risk_usd if gross_risk_usd > 0 else r_multiple
            trade = {
                "date": _format_trade_date(record.date),
                "session": record.session,
                "direction": "long" if record.direction == 1 else "short",
                "entry_price": round(float(levels.entry), 4),
                "stop_price": round(float(levels.stop), 4),
                "tp1_price": round(float(levels.tp1), 4),
                "tp2_price": round(float(levels.tp2), 4),
                "exit_type": record.exit_type,
                "pnl_usd": round(pnl_usd, 2),
                "net_pnl_usd": round(pnl_usd, 2),
                "gross_pnl_usd": round(gross_pnl_usd, 2),
                "commission_per_contract": round(commission_per_contract, 4),
                "commission_usd": round(commission_usd, 2),
                "pnl_points": round(pnl_points, 4),
                "r_multiple": round(r_multiple, 3),
                "net_r_multiple": round(net_r_multiple, 3),
                "qty": qty,
                "gap_size": round(float(getattr(levels, "gap_size", 0.0) or 0.0), 4),
                "risk_points": round(risk_points, 4),
                "entry_time": record.entry_timestamp,
                "exit_time": record.timestamp,
                "lsi_swept_level": getattr(engine, "_swept_level", None),
                "lsi_fvg_top": getattr(engine, "_fvg_top", None),
                "lsi_fvg_bottom": getattr(engine, "_fvg_bottom", None),
                "htf_level_time": getattr(engine, "_swept_level_time", None) if getattr(engine, "lsi_variant", "") == "htf-LSI" else None,
                "htf_level_price": getattr(engine, "_swept_level", None) if getattr(engine, "lsi_variant", "") == "htf-LSI" else None,
                "htf_level_side": getattr(engine, "_active_htf_level_side", "") if getattr(engine, "lsi_variant", "") == "htf-LSI" else None,
                "htf_level_tf_minutes": getattr(engine, "htf_level_tf_minutes", None) if getattr(engine, "lsi_variant", "") == "htf-LSI" else None,
                "fvg_to_inversion_bars": getattr(engine, "_fvg_to_inversion_bars", None),
                "sweep_to_inversion_bars": getattr(engine, "_sweep_to_inversion_bars", None),
                "lsi_fvg_time": None,
                "lsi_sweep_time": None,
                "entry_context": getattr(record, "entry_context", {}) or {},
            }
            self.trades.append(trade)

        return _record

    def asia_tp1_hit_for_date(self, date_str: str, *, config_name: str) -> bool:
        for record in self.trade_history:
            if record.config_name != config_name:
                continue
            if record.date != date_str:
                continue
            if record.session not in {"NQ_Asia", "ES_Asia"}:
                continue
            if record.tp1_hit:
                return True
        return False


class TickCache:
    """Small day-level cache for 1s parquet slices."""

    def __init__(self, max_days: int = 8) -> None:
        self.max_days = max_days
        self._cache: OrderedDict[tuple[str, date], pd.DataFrame] = OrderedDict()

    def _load_day(self, symbol: str, day: date) -> pd.DataFrame:
        key = (symbol, day)
        cached = self._cache.get(key)
        if cached is not None:
            self._cache.move_to_end(key)
            return cached

        start = datetime.combine(day, time.min, tzinfo=ET)
        end = start + timedelta(days=1)
        df = _read_parquet_frame(symbol, "1s", start=start, end=end)
        self._cache[key] = df
        self._cache.move_to_end(key)
        while len(self._cache) > self.max_days:
            self._cache.popitem(last=False)
        return df

    def interval(self, symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        if start >= end:
            return _EMPTY_TICK_FRAME

        frames: list[pd.DataFrame] = []
        day = start.date()
        last_day = end.date()
        while day <= last_day:
            frames.append(self._load_day(symbol, day))
            day += timedelta(days=1)
        if not frames:
            return _EMPTY_TICK_FRAME
        combined = pd.concat(frames)
        return combined[(combined.index >= start) & (combined.index < end)]


def _wire_nq_ny_overlap(orb_engines: list[Any], lsi_engines: list[Any]) -> None:
    orb_by_name = {engine.name: engine for engine in orb_engines}
    lsi_by_name = {engine.name: engine for engine in lsi_engines}
    nq_ny_orb = orb_by_name.get("NQ_NY")
    nq_ny_lsi = lsi_by_name.get("NQ_NY_LSI")
    if nq_ny_orb is None or nq_ny_lsi is None:
        return

    def _check(direction: int) -> bool:
        if direction != 1:
            return False
        levels = getattr(nq_ny_orb, "_levels", None)
        state = getattr(getattr(nq_ny_orb, "_state", None), "value", "")
        if state not in {"armed_limit", "filled", "managing"}:
            return False
        return bool(levels is not None and getattr(levels, "direction", 0) == -1)

    nq_ny_lsi.trade_overlap_check = _check


def _latest_timestamp(symbol: str, timeframe: str) -> datetime:
    path = _resolve_parquet_path(symbol, timeframe)
    index_col = _parquet_index_column(path)
    pf = pq.ParquetFile(path)
    table = pf.read_row_group(pf.num_row_groups - 1, columns=[index_col])
    timestamp = table.column(0)[len(table.column(0)) - 1].as_py()
    ts = pd.Timestamp(timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize(ET)
    else:
        ts = ts.tz_convert(ET)
    return ts.to_pydatetime()


def latest_common_end(symbols: list[str]) -> datetime:
    latest = [
        _latest_timestamp(symbol, timeframe)
        for symbol in symbols
        for timeframe in ("1m", "5m", "1s")
    ]
    return min(latest)


def _subtract_years(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(month=2, day=28, year=day.year - years)


def rolling_year_window_endpoints(end_dt: datetime, years: int) -> tuple[str, str]:
    end_date = end_dt.date()
    start_date = _subtract_years(end_date, years) + timedelta(days=1)
    return start_date.isoformat(), end_date.isoformat()


async def run_profile_backtest(
    *,
    config: dict,
    profile_name: str,
    start_date: str,
    end_date: str,
    latest_data_ts: datetime | None = None,
    label: str | None = None,
    dynamic_sizing_providers: dict[str, Callable[[Any], Any]] | None = None,
    dynamic_sizing_shadow: bool = True,
    profile_session_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict:
    exec_configs = {cfg.name: cfg for cfg in load_exec_configs(config)}
    exec_config = exec_configs[profile_name]
    if profile_session_overrides:
        session_overrides = {
            name: dict(overrides)
            for name, overrides in exec_config.session_overrides.items()
        }
        for session_name, overrides in profile_session_overrides.items():
            merged = dict(session_overrides.get(session_name, {}))
            merged.update(overrides)
            session_overrides[session_name] = merged
        exec_config = replace(exec_config, session_overrides=session_overrides)

    brokers = [TradersPostClient(webhook_url="", config_name=profile_name)]
    broker = MultiBroker(brokers)
    position_manager = ContractCapManager(max_open_contracts=exec_config.max_open_contracts)

    orb_engines, symbol_map, atr_lengths = build_engines(
        config,
        broker,
        config_name=profile_name,
        session_list=list(exec_config.session_overrides.keys()),
        exec_overrides=exec_config.session_overrides,
        position_manager=position_manager,
    )
    lsi_engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name=profile_name,
        lsi_list=list(exec_config.lsi_session_overrides.keys()),
        lsi_overrides=exec_config.lsi_session_overrides,
        position_manager=position_manager,
    )
    if dynamic_sizing_providers:
        for engine in lsi_engines:
            provider = dynamic_sizing_providers.get(engine.name) or dynamic_sizing_providers.get("*")
            if provider is None:
                continue
            engine.dynamic_sizing_provider = provider
            engine.dynamic_sizing_shadow = dynamic_sizing_shadow

    _wire_nq_ny_overlap(orb_engines, lsi_engines)

    recorder = ReplayRecorder(profile_name)
    all_engines = orb_engines + lsi_engines
    for engine in all_engines:
        engine.on_trade_exit = recorder.make_callback(engine)

    for engine in all_engines:
        if engine.name == "NQ_LDN":
            def _make_g5_gate(config_name: str):
                def _g5_gate(ldn_date: str) -> bool:
                    ldn_dt = datetime.strptime(ldn_date, "%Y%m%d")
                    asia_dt = ldn_dt - timedelta(days=1)
                    while asia_dt.weekday() >= 5:
                        asia_dt -= timedelta(days=1)
                    return recorder.asia_tp1_hit_for_date(
                        asia_dt.strftime("%Y%m%d"),
                        config_name=config_name,
                    )

                return _g5_gate

            engine.g5_gate_check = _make_g5_gate(profile_name)

    replay_start = datetime.fromisoformat(start_date).replace(tzinfo=ET) - timedelta(days=1)
    replay_end_date = datetime.fromisoformat(end_date).date()

    atr_by_symbol: dict[str, dict[int, ATRCalculator]] = {}
    daily_history_by_symbol: dict[str, DailyHistoryTracker] = {}
    events: list[tuple[datetime, str, int, Bar]] = []
    atr_update_minutes: dict[str, int] = {}
    for symbol, lengths in atr_lengths.items():
        atr_by_symbol[symbol] = {length: ATRCalculator(length=length) for length in lengths}
        seed_daily = _seed_daily_bars(symbol.split(".")[0], replay_start)
        tracker = DailyHistoryTracker()
        tracker.seed_daily(seed_daily)
        daily_history_by_symbol[symbol] = tracker
        for calc in atr_by_symbol[symbol].values():
            calc.seed_daily(seed_daily)

        ath_seed = _seed_ath_high(symbol.split(".")[0], replay_start)
        if ath_seed is not None:
            for engine in symbol_map.get(symbol, []):
                if hasattr(engine, "seed_ath_high"):
                    engine.seed_ath_high(ath_seed)

        frame_end = datetime.combine(replay_end_date + timedelta(days=1), time.min, tzinfo=ET)
        required_minutes = {
            _engine_bar_minutes(engine)
            for engine in symbol_map.get(symbol, [])
        } or {5}
        atr_update_minutes[symbol] = min(required_minutes)
        for bar_minutes in sorted(required_minutes):
            timeframe = _timeframe_for_minutes(bar_minutes)
            bars = _read_parquet_frame(symbol.split(".")[0], timeframe, start=replay_start, end=frame_end)
            events.extend(_build_bar_events(symbol, bars, bar_minutes=bar_minutes))

    events.sort(key=lambda item: (item[0], item[1], item[2]))
    tick_cache = TickCache()
    current_time = replay_start
    final_tick_time = latest_data_ts or datetime.combine(replay_end_date + timedelta(days=1), time.min, tzinfo=ET)
    set_daily_history_provider(_daily_history_provider_from_trackers(daily_history_by_symbol))
    try:
        idx = 0
        while idx < len(events):
            event_time = events[idx][0]
            active_symbols = [symbol for symbol, engines in symbol_map.items() if any(_active_for_ticks(engine) for engine in engines)]
            if active_symbols and current_time < event_time:
                tick_events: list[tuple[datetime, str, Bar]] = []
                for symbol in active_symbols:
                    ticks = tick_cache.interval(symbol.split(".")[0], current_time, event_time)
                    for ts, row in ticks.iterrows():
                        tick_events.append((
                            ts.to_pydatetime(),
                            symbol,
                            Bar(
                                timestamp=ts.to_pydatetime(),
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=int(row["volume"] or 0),
                            ),
                        ))
                tick_events.sort(key=lambda item: (item[0], item[1]))
                for _ts, symbol, tick in tick_events:
                    daily_atrs = {
                        length: calc.value for length, calc in atr_by_symbol[symbol].items()
                    }
                    for engine in symbol_map[symbol]:
                        await engine.on_tick(tick, daily_atrs.get(getattr(engine, "atr_length", 14), 0.0))

            while idx < len(events) and events[idx][0] == event_time:
                _close_time, symbol, bar_minutes, bar = events[idx]
                if bar_minutes == atr_update_minutes.get(symbol, 5):
                    daily_history_by_symbol[symbol].on_5m_bar(bar)
                    for calc in atr_by_symbol[symbol].values():
                        calc.on_5m_bar(bar)
                daily_atrs = {
                    length: calc.value for length, calc in atr_by_symbol[symbol].items()
                }
                for engine in symbol_map[symbol]:
                    if _engine_bar_minutes(engine) == bar_minutes:
                        await engine.on_bar(bar, daily_atrs.get(getattr(engine, "atr_length", 14), 0.0))
                idx += 1

            current_time = event_time

        active_symbols = [symbol for symbol, engines in symbol_map.items() if any(_active_for_ticks(engine) for engine in engines)]
        if active_symbols and current_time < final_tick_time:
            tick_events: list[tuple[datetime, str, Bar]] = []
            for symbol in active_symbols:
                ticks = tick_cache.interval(symbol.split(".")[0], current_time, final_tick_time + timedelta(seconds=1))
                for ts, row in ticks.iterrows():
                    tick_events.append((
                        ts.to_pydatetime(),
                        symbol,
                        Bar(
                            timestamp=ts.to_pydatetime(),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"] or 0),
                        ),
                    ))
            tick_events.sort(key=lambda item: (item[0], item[1]))
            for _ts, symbol, tick in tick_events:
                daily_atrs = {
                    length: calc.value for length, calc in atr_by_symbol[symbol].items()
                }
                for engine in symbol_map[symbol]:
                    await engine.on_tick(tick, daily_atrs.get(getattr(engine, "atr_length", 14), 0.0))
    finally:
        set_daily_history_provider(None)

    trades = [
        trade for trade in recorder.trades
        if start_date <= trade["date"] <= end_date
    ]
    trades = sorted(
        trades,
        key=lambda trade: (
            trade.get("entry_time") or trade.get("exit_time") or "",
            trade.get("exit_time") or "",
            trade["session"],
        ),
    )
    summary = _compute_summary(trades)
    equity_curve = _build_equity_curve(trades, end_date)
    debug_events: list[dict[str, object]] = []
    for engine in all_engines:
        for event in getattr(engine, "_hunter_debug_events", []) or []:
            row = dict(event)
            row.setdefault("profile", profile_name)
            row.setdefault("session", getattr(engine, "name", ""))
            debug_events.append(row)

    return {
        "name": label or f"EXEC EXACT {profile_name} {start_date} to {end_date}",
        "notes": "Historical replay through live execution engines using local parquet data.",
        "config": _build_config_dict(profile_name, exec_config),
        "summary": summary,
        "trades": trades,
        "debug_events": debug_events,
        "equity_curve": equity_curve,
    }


def save_profile_backtest(result: dict) -> str:
    result_id = _generate_result_id(result)
    _post_run(result, result_id)
    return result_id


def run_profile_backtest_sync(**kwargs) -> dict:
    return asyncio.run(run_profile_backtest(**kwargs))
