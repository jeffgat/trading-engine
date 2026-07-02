#!/usr/bin/env python3
"""3m BOS confirmation pass for the NQ NY VWAP static 1:1.5R leg.

This keeps the current sweep/reclaim setup, then waits for a structure-shift
close before entering. It tests BOS as confirmation, not as replacement.
"""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_DIR = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT / "src"))

RUN_SLUG = "nq_ny_vwap_3m_sweep_bos_confirm_20260630"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_3M_SWEEP_BOS_CONFIRM_20260630.md"
BASELINE_TRADES_PATH = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_vwap_static_rr_timeframe_sweep_20260630"
    / "top_timeframe_static_rr_trades.csv"
)

DATA_START = "2021-06-05"
DATA_END_EXCLUSIVE = "2026-06-06"
TIMEFRAME_MIN = 3
ENTRY_START = "09:45"
ENTRY_END = "15:00"
RR = 1.5
NQ_TICK = 0.25
MIN_STOP_TICKS = 4

EXTENSION_ATR_PCT = 0.025
CONSOLIDATION_ATR_PCT = 0.20
CONSOLIDATION_MINUTES = 30
SWEEP_SETUP_TIMEOUT_MINUTES = 60
SESSION_RANGE_ATR_MAX = 2.0
STOP_BASIS = "atr14_prev"
STOP_PCT = 0.075
MIN_RR_TO_MEAN_STATIC_STOP = 0.20
COOLDOWN_MINUTES = 10
MAX_TRADES_PER_DAY = 3

DIRECTION_SCOPES = ("long_only", "both")
CONFIRMATION_WINDOW_MINUTES = (0, 15, 30, 45, 60)
BREAKOUT_BUFFER_RANGE_PCTS = (0.0, 0.10, 0.25, 0.50)


def _load_context_module() -> Any:
    path = SCRIPT_DIR / "run_nq_ny_level_reversion_context_filter_recent5_20260629.py"
    spec = importlib.util.spec_from_file_location("nq_level_context_20260629_confirm", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load context-filter module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ctx = _load_context_module()


@dataclass(frozen=True)
class ConfirmConfig:
    direction_scope: str
    confirmation_window_minutes: int
    breakout_buffer_range_pct: float

    @property
    def consolidation_bars(self) -> int:
        return int(round(CONSOLIDATION_MINUTES / TIMEFRAME_MIN))

    @property
    def sweep_setup_timeout_bars(self) -> int:
        return int(round(SWEEP_SETUP_TIMEOUT_MINUTES / TIMEFRAME_MIN))

    @property
    def confirmation_window_bars(self) -> int:
        return int(round(self.confirmation_window_minutes / TIMEFRAME_MIN))

    @property
    def cooldown_bars(self) -> int:
        return int(math.ceil(COOLDOWN_MINUTES / TIMEFRAME_MIN))

    @property
    def trigger_label(self) -> str:
        pct = f"{self.breakout_buffer_range_pct * 100:g}".replace(".", "p")
        return f"sweep_reclaim_then_bos_{self.confirmation_window_minutes}m_plus_{pct}pct_range"

    @property
    def variant_id(self) -> str:
        pct = f"{self.breakout_buffer_range_pct:g}".replace(".", "p")
        return (
            f"vwap_3m_{self.direction_scope}_sweep_bos_confirm_"
            f"cons{CONSOLIDATION_MINUTES}m_x{CONSOLIDATION_ATR_PCT:g}_"
            f"confirm{self.confirmation_window_minutes}m_plus_{pct}range_"
            f"stop_{STOP_BASIS}_pct{STOP_PCT:g}_rr{RR:g}"
        )


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _load_1m_source() -> pd.DataFrame:
    df = pd.read_parquet(DATA_DIR / "NQ_1m.parquet")
    return df[(df.index >= DATA_START) & (df.index < DATA_END_EXCLUSIVE)].copy()


def _resample_ohlcv(df_1m: pd.DataFrame, timeframe_min: int) -> pd.DataFrame:
    if timeframe_min == 1:
        return df_1m.copy()
    rule = f"{timeframe_min}min"
    out = df_1m.resample(rule, label="left", closed="left", origin="start_day").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"])


def _ceil_even_stop_ticks(raw_points: float) -> int:
    ticks = max(MIN_STOP_TICKS, int(math.ceil(raw_points / NQ_TICK)))
    if ticks % 2:
        ticks += 1
    return ticks


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    equity = np.cumsum(np.array(values, dtype=float))
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = sum(value for value in values if value < 0)
    if losses < 0:
        return float(wins / abs(losses))
    return float("inf") if wins > 0 else 0.0


def _yearly_rows(trades: list[dict[str, Any]]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["year", "period", "trades", "win_rate", "total_r", "avg_r", "profit_factor", "max_drawdown_r"])
    frame = pd.DataFrame(trades)
    frame["year"] = frame["date"].astype(str).str.slice(0, 4)
    rows = []
    for year, group in frame.groupby("year", sort=True):
        values = [float(value) for value in group["r_multiple"]]
        rows.append(
            {
                "year": str(year),
                "period": f"{group['date'].min()} to {group['date'].max()}",
                "trades": int(len(group)),
                "win_rate": round(float(np.mean([value > 0 for value in values])), 4),
                "total_r": round(float(sum(values)), 4),
                "avg_r": round(float(np.mean(values)), 4),
                "profit_factor": round(_profit_factor(values), 4),
                "max_drawdown_r": round(_max_drawdown(values), 4),
            }
        )
    return pd.DataFrame(rows)


def _score_values(trades: list[dict[str, Any]], trading_days: int, label: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    values = [float(row["r_multiple"]) for row in trades]
    exits = Counter(row.get("exit_type", "") for row in trades)
    by_day = pd.Series([row["date"] for row in trades]).value_counts() if trades else pd.Series(dtype=int)
    days_with_trade = int((by_day > 0).sum())
    days_1_to_3 = int(((by_day >= 1) & (by_day <= 3)).sum())
    years = trading_days / 252.0 if trading_days else 0.0
    total_r = float(sum(values))
    max_dd = _max_drawdown(values)
    avg_annual_r = total_r / years if years else 0.0
    yearly = _yearly_rows(trades)
    full_years = yearly[yearly["year"].isin(["2022", "2023", "2024", "2025"])] if not yearly.empty else yearly
    row = {
        "label": label,
        "total_trades": len(trades),
        "trading_days": trading_days,
        "avg_trades_per_day": round(len(trades) / trading_days, 4) if trading_days else 0.0,
        "days_with_trade": days_with_trade,
        "pct_days_with_trade": round(days_with_trade / trading_days, 4) if trading_days else 0.0,
        "pct_days_1_to_3_trades": round(days_1_to_3 / trading_days, 4) if trading_days else 0.0,
        "zero_trade_days": trading_days - days_with_trade,
        "total_r": round(total_r, 4),
        "avg_r": round(total_r / len(trades), 4) if trades else 0.0,
        "avg_annual_r": round(avg_annual_r, 4),
        "calmar": round(avg_annual_r / abs(max_dd), 4) if max_dd < 0 else 0.0,
        "profit_factor": round(_profit_factor(values), 4),
        "win_rate": round(float(np.mean([value > 0 for value in values])), 4) if values else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "negative_years": int((yearly["total_r"] < 0).sum()) if not yearly.empty else 0,
        "negative_full_years": int((full_years["total_r"] < 0).sum()) if not full_years.empty else 0,
        "target_exits": int(exits.get("target", 0)),
        "stop_exits": int(exits.get("stop", 0)),
        "eod_exits": int(exits.get("eod", 0)),
    }
    if extra:
        row.update(extra)
    return row


def _extension_direction(day: Any, idx: int, config: ConfirmConfig) -> int | None:
    extension = EXTENSION_ATR_PCT * day.atr
    mean = float(day.vwap[idx])
    if not math.isfinite(mean):
        return None
    if day.closes[idx] < mean and mean - day.lows[idx] >= extension:
        return 1
    if config.direction_scope == "both" and day.closes[idx] > mean and day.highs[idx] - mean >= extension:
        return -1
    return None


def _consolidation_accepts(day: Any, config: ConfirmConfig, sweep_idx: int, direction: int) -> tuple[float, float, float] | None:
    extension = EXTENSION_ATR_PCT * day.atr
    mean = float(day.vwap[sweep_idx])
    if not math.isfinite(mean):
        return None
    cons_slice = slice(sweep_idx - config.consolidation_bars, sweep_idx)
    cons_high = float(np.max(day.highs[cons_slice]))
    cons_low = float(np.min(day.lows[cons_slice]))
    cons_range = cons_high - cons_low
    if cons_range <= 0 or cons_range > CONSOLIDATION_ATR_PCT * day.atr:
        return None
    if direction == 1:
        if not np.all(day.highs[cons_slice] < day.vwap[cons_slice]):
            return None
        if mean - cons_low < extension:
            return None
    else:
        if not np.all(day.lows[cons_slice] > day.vwap[cons_slice]):
            return None
        if cons_high - mean < extension:
            return None
    return cons_high, cons_low, cons_range


def _sweep_reclaim_accepts(day: Any, sweep_idx: int, direction: int, cons_high: float, cons_low: float) -> bool:
    mean = float(day.vwap[sweep_idx])
    close = float(day.closes[sweep_idx])
    if direction == 1:
        return day.lows[sweep_idx] < cons_low and close > cons_low and close < mean
    return day.highs[sweep_idx] > cons_high and close < cons_high and close > mean


def _confirmation_idx(
    day: Any,
    config: ConfirmConfig,
    sweep_idx: int,
    direction: int,
    cons_high: float,
    cons_low: float,
    cons_range: float,
) -> int | None:
    max_confirm_idx = min(len(day.timestamps) - 2, sweep_idx + config.confirmation_window_bars)
    buffer_points = config.breakout_buffer_range_pct * cons_range
    for confirm_idx in range(sweep_idx, max_confirm_idx + 1):
        if day.times[confirm_idx] < ENTRY_START or day.times[confirm_idx] > ENTRY_END:
            continue
        mean = float(day.vwap[confirm_idx])
        close = float(day.closes[confirm_idx])
        if not math.isfinite(mean):
            continue
        if float(day.session_range_atr[confirm_idx]) > SESSION_RANGE_ATR_MAX:
            continue
        if direction == 1:
            if close > cons_high + buffer_points and close < mean:
                return confirm_idx
        elif close < cons_low - buffer_points and close > mean:
            return confirm_idx
    return None


def _candidate_trade(
    day: Any,
    config: ConfirmConfig,
    *,
    direction: int,
    extension_idx: int,
    sweep_idx: int,
    confirm_idx: int,
    cons_high: float,
    cons_low: float,
    cons_range: float,
) -> dict[str, Any] | None:
    entry_idx = confirm_idx + 1
    entry = float(day.opens[entry_idx])
    confirm_mean = float(day.vwap[confirm_idx])
    raw_stop_points = day.atr * STOP_PCT
    stop_ticks = _ceil_even_stop_ticks(raw_stop_points)
    risk = stop_ticks * NQ_TICK
    reward = risk * RR
    if direction == 1:
        stop = entry - risk
        target = entry + reward
        rr_to_mean_static_stop = (confirm_mean - entry) / risk if risk > 0 else 0.0
        break_level = cons_high + config.breakout_buffer_range_pct * cons_range
        break_distance_points = float(day.closes[confirm_idx]) - cons_high
    else:
        stop = entry + risk
        target = entry - reward
        rr_to_mean_static_stop = (entry - confirm_mean) / risk if risk > 0 else 0.0
        break_level = cons_low - config.breakout_buffer_range_pct * cons_range
        break_distance_points = cons_low - float(day.closes[confirm_idx])
    if rr_to_mean_static_stop < MIN_RR_TO_MEAN_STATIC_STOP:
        return None

    exit_idx, exit_price, exit_type, r_multiple = ctx._simulate_exit(
        day,
        direction=direction,
        entry_idx=entry_idx,
        entry=entry,
        stop=stop,
        target=target,
        risk=risk,
    )
    close = float(day.closes[confirm_idx])
    directional_vwap_distance_atr = ((float(day.vwap[confirm_idx]) - close) * direction) / day.atr
    return {
        "date": day.date,
        "timeframe": "3m",
        "timeframe_min": TIMEFRAME_MIN,
        "direction": "long" if direction == 1 else "short",
        "direction_int": direction,
        "entry_logic": "sweep_reclaim_plus_bos_confirmation",
        "direction_scope": config.direction_scope,
        "trigger_label": config.trigger_label,
        "variant_id": config.variant_id,
        "extension_ts": day.timestamps[extension_idx].isoformat(),
        "sweep_ts": day.timestamps[sweep_idx].isoformat(),
        "signal_ts": day.timestamps[confirm_idx].isoformat(),
        "signal_time": day.times[confirm_idx],
        "entry_ts": day.timestamps[entry_idx].isoformat(),
        "exit_ts": day.timestamps[exit_idx].isoformat(),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "mean_price": round(confirm_mean, 2),
        "exit_price": round(float(exit_price), 2),
        "exit_type": exit_type,
        "risk_points": round(risk, 2),
        "reward_points": round(reward, 2),
        "rr": RR,
        "r_multiple": round(float(r_multiple), 4),
        "stop_basis": STOP_BASIS,
        "stop_pct": STOP_PCT,
        "stop_model": f"{STOP_BASIS}_pct7p5_rr{RR:g}",
        "stop_base_points": round(day.atr, 2),
        "raw_stop_points": round(raw_stop_points, 4),
        "stop_ticks": stop_ticks,
        "rr_to_mean_static_stop": round(rr_to_mean_static_stop, 4),
        "fixed_target_reaches_mean": bool(rr_to_mean_static_stop >= RR),
        "atr14_prev": round(day.atr, 2),
        "session_range_atr": round(float(day.session_range_atr[confirm_idx]), 5),
        "setup_wait_bars": confirm_idx - extension_idx,
        "setup_wait_minutes": (confirm_idx - extension_idx) * TIMEFRAME_MIN,
        "sweep_to_confirm_bars": confirm_idx - sweep_idx,
        "sweep_to_confirm_minutes": (confirm_idx - sweep_idx) * TIMEFRAME_MIN,
        "consolidation_minutes": CONSOLIDATION_MINUTES,
        "consolidation_bars": config.consolidation_bars,
        "sweep_setup_timeout_bars": config.sweep_setup_timeout_bars,
        "confirmation_window_minutes": config.confirmation_window_minutes,
        "confirmation_window_bars": config.confirmation_window_bars,
        "cooldown_bars": config.cooldown_bars,
        "consolidation_high": round(cons_high, 2),
        "consolidation_low": round(cons_low, 2),
        "consolidation_range": round(cons_range, 2),
        "consolidation_range_atr": round(cons_range / day.atr, 5),
        "breakout_buffer_range_pct": config.breakout_buffer_range_pct,
        "break_level": round(break_level, 2),
        "break_distance_points": round(break_distance_points, 2),
        "break_distance_range_pct": round(break_distance_points / cons_range, 4),
        "signal_close": round(close, 2),
        "signal_high": round(float(day.highs[confirm_idx]), 2),
        "signal_low": round(float(day.lows[confirm_idx]), 2),
        "signal_vwap": round(float(day.vwap[confirm_idx]), 2),
        "vwap_slope_atr": round(float(day.vwap_slope_atr[confirm_idx]), 5),
        "directional_vwap_distance_atr": round(float(directional_vwap_distance_atr), 5),
        "directional_efficiency": round(float(day.directional_efficiency[confirm_idx]), 5),
        "structure_30m": day.structure_30m[confirm_idx],
        "context_session_range_atr_max": SESSION_RANGE_ATR_MAX,
        "deployability": "research_only",
        "live_support_notes": (
            "BOS confirmation exists only in this research script; live execution and exact replay parity are not implemented."
        ),
        "exact_replay_required": "yes",
        "exit_idx": exit_idx,
        "extension_idx": extension_idx,
        "sweep_idx": sweep_idx,
        "signal_idx": confirm_idx,
        "entry_idx": entry_idx,
    }


def _generate_candidates_for_day(day: Any, config: ConfirmConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    max_signal_idx = len(day.timestamps) - 2
    for extension_idx in range(0, max_signal_idx):
        if day.times[extension_idx] < ENTRY_START or day.times[extension_idx] > ENTRY_END:
            continue
        direction = _extension_direction(day, extension_idx, config)
        if direction is None:
            continue
        start_sweep_idx = extension_idx + 1 + config.consolidation_bars
        end_sweep_idx = min(max_signal_idx, extension_idx + config.sweep_setup_timeout_bars)
        if start_sweep_idx > end_sweep_idx:
            continue

        for sweep_idx in range(start_sweep_idx, end_sweep_idx + 1):
            if day.times[sweep_idx] < ENTRY_START or day.times[sweep_idx] > ENTRY_END:
                continue
            cons = _consolidation_accepts(day, config, sweep_idx, direction)
            if cons is None:
                continue
            cons_high, cons_low, cons_range = cons
            if not _sweep_reclaim_accepts(day, sweep_idx, direction, cons_high, cons_low):
                continue
            confirm_idx = _confirmation_idx(day, config, sweep_idx, direction, cons_high, cons_low, cons_range)
            if confirm_idx is None:
                continue
            candidate = _candidate_trade(
                day,
                config,
                direction=direction,
                extension_idx=extension_idx,
                sweep_idx=sweep_idx,
                confirm_idx=confirm_idx,
                cons_high=cons_high,
                cons_low=cons_low,
                cons_range=cons_range,
            )
            if candidate is not None:
                candidates.append(candidate)
                break
    return candidates


def _simulate_model(days: list[Any], candidates_by_day: list[list[dict[str, Any]]], config: ConfirmConfig) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for day, day_candidates in zip(days, candidates_by_day, strict=True):
        current_min_idx = 0
        day_trade_count = 0
        for candidate in day_candidates:
            if day_trade_count >= MAX_TRADES_PER_DAY:
                break
            if (
                int(candidate["extension_idx"]) < current_min_idx
                or int(candidate["sweep_idx"]) < current_min_idx
                or int(candidate["signal_idx"]) < current_min_idx
                or int(candidate["entry_idx"]) < current_min_idx
            ):
                continue
            trades.append(candidate)
            day_trade_count += 1
            current_min_idx = int(candidate["exit_idx"]) + config.cooldown_bars
    return trades


def _score_config(trades: list[dict[str, Any]], trading_days: int, config: ConfirmConfig, total_candidates: int) -> dict[str, Any]:
    extra = {
        "timeframe": "3m",
        "timeframe_min": TIMEFRAME_MIN,
        "entry_logic": "sweep_reclaim_plus_bos_confirmation",
        "direction_scope": config.direction_scope,
        "trigger_label": config.trigger_label,
        "variant_id": config.variant_id,
        "consolidation_minutes": CONSOLIDATION_MINUTES,
        "consolidation_bars": config.consolidation_bars,
        "sweep_setup_timeout_minutes": SWEEP_SETUP_TIMEOUT_MINUTES,
        "sweep_setup_timeout_bars": config.sweep_setup_timeout_bars,
        "confirmation_window_minutes": config.confirmation_window_minutes,
        "confirmation_window_bars": config.confirmation_window_bars,
        "cooldown_bars": config.cooldown_bars,
        "breakout_buffer_range_pct": config.breakout_buffer_range_pct,
        "extension_atr_pct": EXTENSION_ATR_PCT,
        "consolidation_atr_pct": CONSOLIDATION_ATR_PCT,
        "session_range_atr_max": SESSION_RANGE_ATR_MAX,
        "min_rr_to_mean_static_stop": MIN_RR_TO_MEAN_STATIC_STOP,
        "stop_basis": STOP_BASIS,
        "stop_pct": STOP_PCT,
        "stop_model": f"{STOP_BASIS}_pct7p5_rr{RR:g}",
        "rr": RR,
        "total_candidates": total_candidates,
        "avg_stop_points": round(float(np.mean([row["risk_points"] for row in trades])), 2) if trades else 0.0,
        "median_stop_points": round(float(np.median([row["risk_points"] for row in trades])), 2) if trades else 0.0,
        "fixed_target_reaches_mean_pct": round(float(np.mean([row["fixed_target_reaches_mean"] for row in trades])), 4) if trades else 0.0,
        "deployability": "research_only",
        "exact_replay_required": "yes",
    }
    return _score_values(trades, trading_days, config.variant_id, extra)


def _load_baseline_controls(trading_days: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not BASELINE_TRADES_PATH.exists():
        empty = pd.DataFrame()
        return empty, empty
    frame = pd.read_csv(BASELINE_TRADES_PATH)
    frame = frame[frame["timeframe"].astype(str) == "3m"].copy()
    control_rows = []
    yearly_parts = []
    groups = {
        "baseline_sweep_reclaim_3m_all_directions": frame,
        "baseline_sweep_reclaim_3m_long_only": frame[frame["direction"].astype(str) == "long"],
        "baseline_sweep_reclaim_3m_short_only": frame[frame["direction"].astype(str) == "short"],
    }
    for label, group in groups.items():
        trades = group.to_dict(orient="records")
        control_rows.append(
            _score_values(
                trades,
                trading_days,
                label,
                {
                    "entry_logic": "sweep_reclaim",
                    "timeframe": "3m",
                    "stop_model": f"{STOP_BASIS}_pct7p5_rr{RR:g}",
                    "rr": RR,
                },
            )
        )
        yearly = _yearly_rows(trades)
        if not yearly.empty:
            yearly.insert(0, "label", label)
            yearly_parts.append(yearly)
    yearly_frame = pd.concat(yearly_parts, ignore_index=True) if yearly_parts else pd.DataFrame()
    return pd.DataFrame(control_rows), yearly_frame


def _format_table(frame: pd.DataFrame, columns: list[str], n: int | None = None) -> str:
    if frame.empty:
        return "_None._"
    view = frame[columns].copy()
    if n is not None:
        view = view.head(n)
    return view.to_markdown(index=False)


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading NQ 1m source data {DATA_START} to <{DATA_END_EXCLUSIVE}...")
    df_1m = _load_1m_source()
    df_3m = _resample_ohlcv(df_1m, TIMEFRAME_MIN)
    days = ctx._prepare_days(ctx._prepare_rth(df_3m))
    trading_days = len(days)
    print(f"Prepared 3m RTH days={trading_days}; bars={len(df_3m)}", flush=True)

    rows: list[dict[str, Any]] = []
    trades_by_variant: dict[str, list[dict[str, Any]]] = {}
    for direction_scope in DIRECTION_SCOPES:
        for confirmation_window_minutes in CONFIRMATION_WINDOW_MINUTES:
            for breakout_buffer_range_pct in BREAKOUT_BUFFER_RANGE_PCTS:
                config = ConfirmConfig(
                    direction_scope=direction_scope,
                    confirmation_window_minutes=confirmation_window_minutes,
                    breakout_buffer_range_pct=breakout_buffer_range_pct,
                )
                candidates_by_day = [_generate_candidates_for_day(day, config) for day in days]
                total_candidates = sum(len(day_candidates) for day_candidates in candidates_by_day)
                trades = _simulate_model(days, candidates_by_day, config)
                row = _score_config(trades, trading_days, config, total_candidates)
                rows.append(row)
                trades_by_variant[config.variant_id] = trades
                print(
                    f"{config.variant_id}: {row['total_trades']} trades "
                    f"{row['total_r']:+.2f}R PF {row['profit_factor']:.3f} "
                    f"DD {row['max_drawdown_r']:.2f}R",
                    flush=True,
                )

    ranked = pd.DataFrame(rows).sort_values(
        ["calmar", "negative_full_years", "profit_factor", "total_r", "max_drawdown_r"],
        ascending=[False, True, False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    best_by_scope = (
        ranked.sort_values(["direction_scope", "calmar", "profit_factor"], ascending=[True, False, False])
        .groupby("direction_scope", group_keys=False)
        .head(1)
        .sort_values("direction_scope")
        .reset_index(drop=True)
    )
    daily_cadence = ranked[
        (ranked["avg_trades_per_day"] >= 1.0)
        & (ranked["avg_trades_per_day"] <= 3.0)
    ].copy()
    near_daily_cadence = ranked[
        (ranked["avg_trades_per_day"] >= 0.75)
        & (ranked["avg_trades_per_day"] <= 3.0)
    ].copy()
    best = ranked.iloc[0].to_dict()
    best_variant_id = str(best["variant_id"])
    best_trades = trades_by_variant[best_variant_id]
    best_yearly = _yearly_rows(best_trades)
    control_frame, control_yearly = _load_baseline_controls(trading_days)

    ranked_path = RESULT_DIR / "sweep_bos_confirm_results.csv"
    best_by_scope_path = RESULT_DIR / "best_by_direction_scope.csv"
    daily_cadence_path = RESULT_DIR / "daily_cadence_rows.csv"
    near_daily_cadence_path = RESULT_DIR / "near_daily_cadence_rows.csv"
    best_trades_path = RESULT_DIR / "top_sweep_bos_confirm_trades.csv"
    best_yearly_path = RESULT_DIR / "top_sweep_bos_confirm_yearly.csv"
    control_path = RESULT_DIR / "baseline_sweep_reclaim_controls.csv"
    control_yearly_path = RESULT_DIR / "baseline_sweep_reclaim_yearly.csv"
    summary_path = RESULT_DIR / "summary.json"

    ranked.to_csv(ranked_path, index=False)
    best_by_scope.to_csv(best_by_scope_path, index=False)
    daily_cadence.to_csv(daily_cadence_path, index=False)
    near_daily_cadence.to_csv(near_daily_cadence_path, index=False)
    pd.DataFrame(best_trades).drop(columns=["exit_idx", "extension_idx", "sweep_idx", "signal_idx", "entry_idx"], errors="ignore").to_csv(
        best_trades_path,
        index=False,
    )
    best_yearly.to_csv(best_yearly_path, index=False)
    control_frame.to_csv(control_path, index=False)
    control_yearly.to_csv(control_yearly_path, index=False)

    result_cols = [
        "rank",
        "direction_scope",
        "confirmation_window_minutes",
        "breakout_buffer_range_pct",
        "total_trades",
        "avg_trades_per_day",
        "pct_days_with_trade",
        "total_r",
        "avg_r",
        "avg_annual_r",
        "calmar",
        "profit_factor",
        "win_rate",
        "max_drawdown_r",
        "negative_full_years",
        "fixed_target_reaches_mean_pct",
    ]
    control_cols = [
        "label",
        "total_trades",
        "avg_trades_per_day",
        "pct_days_with_trade",
        "total_r",
        "avg_r",
        "avg_annual_r",
        "calmar",
        "profit_factor",
        "win_rate",
        "max_drawdown_r",
        "negative_full_years",
    ]
    yearly_cols = ["year", "period", "trades", "win_rate", "total_r", "avg_r", "profit_factor", "max_drawdown_r"]

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "3m_sweep_reclaim_plus_bos_confirmation",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "timeframe_min": TIMEFRAME_MIN,
        "rr": RR,
        "stop_basis": STOP_BASIS,
        "stop_pct": STOP_PCT,
        "direction_scopes": list(DIRECTION_SCOPES),
        "consolidation_minutes": CONSOLIDATION_MINUTES,
        "sweep_setup_timeout_minutes": SWEEP_SETUP_TIMEOUT_MINUTES,
        "confirmation_window_minutes": list(CONFIRMATION_WINDOW_MINUTES),
        "breakout_buffer_range_pcts": list(BREAKOUT_BUFFER_RANGE_PCTS),
        "trading_days": trading_days,
        "grid_rows": int(len(ranked)),
        "best_row": _safe(best),
        "best_by_direction_scope": _safe(best_by_scope.to_dict(orient="records")),
        "daily_cadence_rows": _safe(daily_cadence.to_dict(orient="records")),
        "near_daily_cadence_rows": _safe(near_daily_cadence.to_dict(orient="records")),
        "baseline_controls": _safe(control_frame.to_dict(orient="records")),
        "artifacts": {
            "results": str(ranked_path.relative_to(ROOT)),
            "best_by_direction_scope": str(best_by_scope_path.relative_to(ROOT)),
            "daily_cadence_rows": str(daily_cadence_path.relative_to(ROOT)),
            "near_daily_cadence_rows": str(near_daily_cadence_path.relative_to(ROOT)),
            "top_trades": str(best_trades_path.relative_to(ROOT)),
            "top_yearly": str(best_yearly_path.relative_to(ROOT)),
            "baseline_controls": str(control_path.relative_to(ROOT)),
            "report": str(REPORT_PATH.relative_to(ROOT)),
        },
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_lines = [
        "# NQ NY VWAP 3m Sweep + BOS Confirmation",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{DATA_START}` to `<{DATA_END_EXCLUSIVE}` from raw NQ 1m bars resampled to native 3m.",
        f"- Exit: fixed static `{RR}:1` reward-to-risk with stop priority on same-bar stop/target touches.",
        f"- Stop: `{STOP_BASIS}` `{STOP_PCT:.1%}` rounded to even NQ ticks, matching the current best 3m leg.",
        "- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full NY RTH window.",
        "- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.",
        "",
        "## Confirmation Entry Criteria",
        "",
        "1. Use the current 3m sweep/reclaim VWAP setup: extension from VWAP, 30-minute consolidation, sweep of the consolidation edge, reclaim close still on the VWAP side, and fixed 1.5R target.",
        "2. Do not enter immediately on the sweep/reclaim bar.",
        "3. Wait up to `N` minutes for a BOS close beyond `consolidation edge + buffer * consolidation range` while still on the VWAP side.",
        "4. Enter on the next 3m bar open after the BOS confirmation. Maximum 3 sequential non-overlapping trades/day, about 10 minutes cooldown after exit.",
        "",
        "The confirmation-window grid was `0`, `15`, `30`, `45`, and `60` minutes. The buffer grid was `0%`, `10%`, `25%`, and `50%` of the consolidation range.",
        "",
        "## Baseline Controls",
        "",
        _format_table(control_frame, control_cols, n=None),
        "",
        "## Best By Direction Scope",
        "",
        _format_table(best_by_scope, result_cols, n=None),
        "",
        "## Daily-Cadence Confirmation Rows",
        "",
        _format_table(daily_cadence, result_cols, n=None),
        "",
        "## Near-Daily Confirmation Rows",
        "",
        _format_table(near_daily_cadence, result_cols, n=None),
        "",
        "## Top Confirmation Rows",
        "",
        _format_table(ranked, result_cols, n=20),
        "",
        "## Best Confirmation Year Split",
        "",
        _format_table(best_yearly, yearly_cols, n=None),
        "",
        "## Summary Read",
        "",
        f"- Best confirmation row: `{best['direction_scope']}` with `{int(best['confirmation_window_minutes'])}m` confirmation window and `{best['breakout_buffer_range_pct']:.0%}` range buffer; `{int(best['total_trades'])}` trades, `{best['avg_trades_per_day']}` trades/day, `{best['total_r']:+.2f}R`, PF `{best['profit_factor']:.3f}`, max DD `{best['max_drawdown_r']:.2f}R`.",
        "- This tests BOS as an extra confirmation after the sweep/reclaim, not as a replacement.",
        "- Treat this as a challenger screen only. Promotion would require exact replay and train/validation before prop-firm lifecycle scoring.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(report_lines))
    print(f"\nWrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"Wrote artifacts under {RESULT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
