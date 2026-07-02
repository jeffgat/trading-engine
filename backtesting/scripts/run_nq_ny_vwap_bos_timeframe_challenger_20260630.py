#!/usr/bin/env python3
"""Native 1m/2m/3m/5m BOS challenger for the NQ NY VWAP static 1:1.5R leg.

This isolates one hypothesis: replace the sweep/reclaim signal with a close
above consolidation structure while keeping the static stop/exit plumbing and
time-normalizing setup durations across native bar sizes.
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

RUN_SLUG = "nq_ny_vwap_bos_timeframe_challenger_20260630"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_BOS_TIMEFRAME_CHALLENGER_20260630.md"
BASELINE_TRADES_PATH = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_vwap_static_rr_timeframe_sweep_20260630"
    / "top_timeframe_static_rr_trades.csv"
)

DATA_START = "2021-06-05"
DATA_END_EXCLUSIVE = "2026-06-06"
TIMEFRAMES = (1, 2, 3, 5)
ENTRY_START = "09:45"
ENTRY_END = "15:00"
RR = 1.5
NQ_TICK = 0.25
MIN_STOP_TICKS = 4

EXTENSION_ATR_PCT = 0.025
CONSOLIDATION_ATR_PCT = 0.20
SESSION_RANGE_ATR_MAX = 2.0
STOP_BASIS = "atr14_prev"
STOP_PCT = 0.075
MIN_RR_TO_MEAN_STATIC_STOP = 0.20
SIGNAL_WINDOW_MINUTES = 30
COOLDOWN_MINUTES = 10
MAX_TRADES_PER_DAY = 3

CONSOLIDATION_MINUTES = (15, 21, 30, 45, 60)
BREAKOUT_BUFFER_RANGE_PCTS = (0.0, 0.10, 0.25, 0.50)


def _load_context_module() -> Any:
    path = SCRIPT_DIR / "run_nq_ny_level_reversion_context_filter_recent5_20260629.py"
    spec = importlib.util.spec_from_file_location("nq_level_context_20260629_bos", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load context-filter module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ctx = _load_context_module()


@dataclass(frozen=True)
class BosConfig:
    timeframe_min: int
    consolidation_minutes: int
    breakout_buffer_range_pct: float
    signal_window_minutes: int = SIGNAL_WINDOW_MINUTES

    @property
    def timeframe(self) -> str:
        return f"{self.timeframe_min}m"

    @property
    def consolidation_bars(self) -> int:
        return _round_bars(self.consolidation_minutes, self.timeframe_min)

    @property
    def signal_window_bars(self) -> int:
        return _round_bars(self.signal_window_minutes, self.timeframe_min)

    @property
    def setup_timeout_bars(self) -> int:
        return self.consolidation_bars + self.signal_window_bars

    @property
    def cooldown_bars(self) -> int:
        return max(1, int(math.ceil(COOLDOWN_MINUTES / self.timeframe_min)))

    @property
    def trigger_label(self) -> str:
        pct = f"{self.breakout_buffer_range_pct * 100:g}".replace(".", "p")
        return f"close_above_cons_high_plus_{pct}pct_range"

    @property
    def variant_id(self) -> str:
        pct = f"{self.breakout_buffer_range_pct:g}".replace(".", "p")
        return (
            f"vwap_{self.timeframe}_long_bos_ext{EXTENSION_ATR_PCT:g}_"
            f"cons{self.consolidation_minutes}m_x{CONSOLIDATION_ATR_PCT:g}_"
            f"trigger_cons_high_plus_{pct}range_"
            f"stop_{STOP_BASIS}_pct{STOP_PCT:g}_rr{RR:g}"
        )


def _round_bars(minutes: int, timeframe_min: int) -> int:
    return max(1, int(math.floor(minutes / timeframe_min + 0.5)))


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


def _generate_bos_candidates_for_day(day: Any, config: BosConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    extension = EXTENSION_ATR_PCT * day.atr
    max_signal_idx = len(day.timestamps) - 2
    for extension_idx in range(0, max_signal_idx):
        bar_time = day.times[extension_idx]
        if bar_time < ENTRY_START or bar_time > ENTRY_END:
            continue
        extension_mean = float(day.vwap[extension_idx])
        if not math.isfinite(extension_mean):
            continue
        if not (day.closes[extension_idx] < extension_mean and extension_mean - day.lows[extension_idx] >= extension):
            continue

        start_signal_idx = extension_idx + 1 + config.consolidation_bars
        end_signal_idx = min(max_signal_idx, extension_idx + config.setup_timeout_bars)
        if start_signal_idx > end_signal_idx:
            continue

        for signal_idx in range(start_signal_idx, end_signal_idx + 1):
            if day.times[signal_idx] < ENTRY_START or day.times[signal_idx] > ENTRY_END:
                continue
            signal_mean = float(day.vwap[signal_idx])
            if not math.isfinite(signal_mean):
                continue

            cons_slice = slice(signal_idx - config.consolidation_bars, signal_idx)
            cons_high = float(np.max(day.highs[cons_slice]))
            cons_low = float(np.min(day.lows[cons_slice]))
            cons_range = cons_high - cons_low
            if cons_range <= 0:
                continue
            if cons_range > CONSOLIDATION_ATR_PCT * day.atr:
                continue
            if not np.all(day.highs[cons_slice] < day.vwap[cons_slice]):
                continue
            if signal_mean - cons_low < extension:
                continue
            if float(day.session_range_atr[signal_idx]) > SESSION_RANGE_ATR_MAX:
                continue

            break_level = cons_high + config.breakout_buffer_range_pct * cons_range
            signal_close = float(day.closes[signal_idx])
            if signal_close <= break_level or signal_close >= signal_mean:
                continue

            entry_idx = signal_idx + 1
            entry = float(day.opens[entry_idx])
            raw_stop_points = day.atr * STOP_PCT
            stop_ticks = _ceil_even_stop_ticks(raw_stop_points)
            risk = stop_ticks * NQ_TICK
            stop = entry - risk
            target = entry + risk * RR
            rr_to_mean_static_stop = (signal_mean - entry) / risk if risk > 0 else 0.0
            if rr_to_mean_static_stop < MIN_RR_TO_MEAN_STATIC_STOP:
                continue

            exit_idx, exit_price, exit_type, r_multiple = ctx._simulate_exit(
                day,
                direction=1,
                entry_idx=entry_idx,
                entry=entry,
                stop=stop,
                target=target,
                risk=risk,
            )
            directional_vwap_distance_atr = (float(day.vwap[signal_idx]) - signal_close) / day.atr
            return_candidate = {
                "date": day.date,
                "timeframe": config.timeframe,
                "timeframe_min": config.timeframe_min,
                "direction": "long",
                "direction_int": 1,
                "entry_logic": "bos_close",
                "trigger_label": config.trigger_label,
                "variant_id": config.variant_id,
                "extension_ts": day.timestamps[extension_idx].isoformat(),
                "signal_ts": day.timestamps[signal_idx].isoformat(),
                "signal_time": day.times[signal_idx],
                "entry_ts": day.timestamps[entry_idx].isoformat(),
                "exit_ts": day.timestamps[exit_idx].isoformat(),
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "mean_price": round(signal_mean, 2),
                "exit_price": round(float(exit_price), 2),
                "exit_type": exit_type,
                "risk_points": round(risk, 2),
                "reward_points": round(risk * RR, 2),
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
                "session_range_atr": round(float(day.session_range_atr[signal_idx]), 5),
                "setup_wait_bars": signal_idx - extension_idx,
                "setup_wait_minutes": (signal_idx - extension_idx) * config.timeframe_min,
                "consolidation_minutes": config.consolidation_minutes,
                "consolidation_bars": config.consolidation_bars,
                "setup_timeout_bars": config.setup_timeout_bars,
                "signal_window_minutes": config.signal_window_minutes,
                "cooldown_bars": config.cooldown_bars,
                "consolidation_high": round(cons_high, 2),
                "consolidation_low": round(cons_low, 2),
                "consolidation_range": round(cons_range, 2),
                "consolidation_range_atr": round(cons_range / day.atr, 5),
                "breakout_buffer_range_pct": config.breakout_buffer_range_pct,
                "break_level": round(break_level, 2),
                "break_distance_points": round(signal_close - cons_high, 2),
                "break_distance_range_pct": round((signal_close - cons_high) / cons_range, 4),
                "signal_close": round(signal_close, 2),
                "signal_high": round(float(day.highs[signal_idx]), 2),
                "signal_low": round(float(day.lows[signal_idx]), 2),
                "signal_vwap": round(float(day.vwap[signal_idx]), 2),
                "vwap_slope_atr": round(float(day.vwap_slope_atr[signal_idx]), 5),
                "directional_vwap_distance_atr": round(float(directional_vwap_distance_atr), 5),
                "directional_efficiency": round(float(day.directional_efficiency[signal_idx]), 5),
                "structure_30m": day.structure_30m[signal_idx],
                "ib_high_30": round(day.ib_high_30, 2),
                "ib_low_30": round(day.ib_low_30, 2),
                "context_session_range_atr_max": SESSION_RANGE_ATR_MAX,
                "deployability": "research_only",
                "live_support_notes": (
                    "BOS challenger exists only in this research script; live execution and exact replay parity are not implemented."
                ),
                "exact_replay_required": "yes",
                "exit_idx": exit_idx,
                "extension_idx": extension_idx,
                "signal_idx": signal_idx,
                "entry_idx": entry_idx,
            }
            candidates.append(return_candidate)
            break
    return candidates


def _simulate_model(days: list[Any], candidates_by_day: list[list[dict[str, Any]]], config: BosConfig) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for day, day_candidates in zip(days, candidates_by_day, strict=True):
        current_min_idx = 0
        day_trade_count = 0
        for candidate in day_candidates:
            if day_trade_count >= MAX_TRADES_PER_DAY:
                break
            if (
                int(candidate["extension_idx"]) < current_min_idx
                or int(candidate["signal_idx"]) < current_min_idx
                or int(candidate["entry_idx"]) < current_min_idx
            ):
                continue
            trades.append(candidate)
            day_trade_count += 1
            current_min_idx = int(candidate["exit_idx"]) + config.cooldown_bars
    return trades


def _score_config(trades: list[dict[str, Any]], trading_days: int, config: BosConfig, total_candidates: int) -> dict[str, Any]:
    extra = {
        "timeframe": config.timeframe,
        "timeframe_min": config.timeframe_min,
        "entry_logic": "bos_close",
        "trigger_label": config.trigger_label,
        "variant_id": config.variant_id,
        "consolidation_minutes": config.consolidation_minutes,
        "consolidation_bars": config.consolidation_bars,
        "setup_timeout_bars": config.setup_timeout_bars,
        "signal_window_minutes": config.signal_window_minutes,
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


def _load_baseline_controls(trading_days_by_timeframe: dict[int, int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not BASELINE_TRADES_PATH.exists():
        empty = pd.DataFrame()
        return empty, empty
    frame = pd.read_csv(BASELINE_TRADES_PATH)
    control_rows = []
    yearly_parts = []
    for timeframe_min in TIMEFRAMES:
        timeframe = f"{timeframe_min}m"
        tf_frame = frame[frame["timeframe"].astype(str) == timeframe].copy()
        if tf_frame.empty:
            continue
        trading_days = trading_days_by_timeframe.get(timeframe_min, int(tf_frame["date"].nunique()))
        stop_model = str(tf_frame["stop_model"].iloc[0]) if "stop_model" in tf_frame else f"{STOP_BASIS}_pct7p5_rr{RR:g}"
        stop_basis = str(tf_frame["stop_basis"].iloc[0]) if "stop_basis" in tf_frame else STOP_BASIS
        stop_pct = float(tf_frame["stop_pct"].iloc[0]) if "stop_pct" in tf_frame else STOP_PCT
        for suffix, group in {
            "all_directions": tf_frame,
            "long_only": tf_frame[tf_frame["direction"].astype(str) == "long"],
            "short_only": tf_frame[tf_frame["direction"].astype(str) == "short"],
        }.items():
            label = f"baseline_sweep_reclaim_{timeframe}_{suffix}"
            trades = group.to_dict(orient="records")
            control_rows.append(
                _score_values(
                    trades,
                    trading_days,
                    label,
                    {
                        "entry_logic": "sweep_reclaim",
                        "timeframe": timeframe,
                        "timeframe_min": timeframe_min,
                        "stop_model": stop_model,
                        "stop_basis": stop_basis,
                        "stop_pct": stop_pct,
                        "rr": RR,
                        "baseline_source": str(BASELINE_TRADES_PATH.relative_to(ROOT)),
                        "deployability": "research_only",
                        "live_support_notes": (
                            "Baseline trade controls are imported from the static-RR research sweep; "
                            "live execution and exact replay parity are not implemented."
                        ),
                        "exact_replay_required": "yes",
                    },
                )
            )
            yearly = _yearly_rows(trades)
            if not yearly.empty:
                yearly.insert(0, "label", label)
                yearly.insert(1, "timeframe", timeframe)
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

    rows: list[dict[str, Any]] = []
    trades_by_variant: dict[str, list[dict[str, Any]]] = {}
    timeframe_meta: list[dict[str, Any]] = []
    trading_days_by_timeframe: dict[int, int] = {}

    for timeframe_min in TIMEFRAMES:
        df_tf = _resample_ohlcv(df_1m, timeframe_min)
        days = ctx._prepare_days(ctx._prepare_rth(df_tf))
        trading_days = len(days)
        trading_days_by_timeframe[timeframe_min] = trading_days
        timeframe_meta.append(
            {
                "timeframe": f"{timeframe_min}m",
                "timeframe_min": timeframe_min,
                "bars": int(len(df_tf)),
                "trading_days": trading_days,
                "signal_window_bars": _round_bars(SIGNAL_WINDOW_MINUTES, timeframe_min),
                "cooldown_bars": max(1, int(math.ceil(COOLDOWN_MINUTES / timeframe_min))),
            }
        )
        print(
            f"\nPrepared {timeframe_min}m RTH days={trading_days}; bars={len(df_tf)}; "
            f"signal_window={_round_bars(SIGNAL_WINDOW_MINUTES, timeframe_min)} bars",
            flush=True,
        )
        for consolidation_minutes in CONSOLIDATION_MINUTES:
            for breakout_buffer_range_pct in BREAKOUT_BUFFER_RANGE_PCTS:
                config = BosConfig(
                    timeframe_min=timeframe_min,
                    consolidation_minutes=consolidation_minutes,
                    breakout_buffer_range_pct=breakout_buffer_range_pct,
                )
                candidates_by_day = [_generate_bos_candidates_for_day(day, config) for day in days]
                total_candidates = sum(len(day_candidates) for day_candidates in candidates_by_day)
                trades = _simulate_model(days, candidates_by_day, config)
                row = _score_config(trades, trading_days, config, total_candidates)
                rows.append(row)
                trades_by_variant[config.variant_id] = trades
                print(
                    f"  {config.variant_id}: {row['total_trades']} trades "
                    f"{row['total_r']:+.2f}R PF {row['profit_factor']:.3f} "
                    f"DD {row['max_drawdown_r']:.2f}R",
                    flush=True,
                )

    ranked = pd.DataFrame(rows).sort_values(
        ["calmar", "negative_full_years", "profit_factor", "total_r", "max_drawdown_r"],
        ascending=[False, True, False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    best_by_timeframe = (
        ranked.sort_values(
            ["timeframe_min", "calmar", "negative_full_years", "profit_factor", "total_r", "max_drawdown_r"],
            ascending=[True, False, True, False, False, False],
        )
        .groupby("timeframe", group_keys=False)
        .head(1)
        .sort_values("timeframe_min")
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
    control_frame, control_yearly = _load_baseline_controls(trading_days_by_timeframe)

    ranked_path = RESULT_DIR / "ranked_rows.csv"
    best_by_tf_path = RESULT_DIR / "best_by_timeframe.csv"
    daily_cadence_path = RESULT_DIR / "daily_cadence_rows.csv"
    near_daily_cadence_path = RESULT_DIR / "near_daily_cadence_rows.csv"
    best_trades_path = RESULT_DIR / "top_bos_timeframe_challenger_trades.csv"
    best_yearly_path = RESULT_DIR / "top_bos_timeframe_challenger_yearly.csv"
    control_path = RESULT_DIR / "baseline_controls.csv"
    control_yearly_path = RESULT_DIR / "baseline_controls_yearly.csv"
    summary_path = RESULT_DIR / "summary.json"

    ranked.to_csv(ranked_path, index=False)
    best_by_timeframe.to_csv(best_by_tf_path, index=False)
    daily_cadence.to_csv(daily_cadence_path, index=False)
    near_daily_cadence.to_csv(near_daily_cadence_path, index=False)
    pd.DataFrame(best_trades).drop(columns=["exit_idx", "extension_idx", "signal_idx", "entry_idx"], errors="ignore").to_csv(
        best_trades_path,
        index=False,
    )
    best_yearly.to_csv(best_yearly_path, index=False)
    control_frame.to_csv(control_path, index=False)
    control_yearly.to_csv(control_yearly_path, index=False)

    result_cols = [
        "rank",
        "timeframe",
        "consolidation_minutes",
        "consolidation_bars",
        "signal_window_minutes",
        "setup_timeout_bars",
        "cooldown_bars",
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
        "deployability",
    ]
    control_cols = [
        "label",
        "timeframe",
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
        "deployability",
    ]
    yearly_cols = ["year", "period", "trades", "win_rate", "total_r", "avg_r", "profit_factor", "max_drawdown_r"]
    control_timeframes = sorted(control_frame["timeframe"].unique().tolist()) if not control_frame.empty else []

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "bos_timeframe_challenger",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "timeframes": list(TIMEFRAMES),
        "direction": "long_only",
        "rr": RR,
        "stop_basis": STOP_BASIS,
        "stop_pct": STOP_PCT,
        "consolidation_minutes": list(CONSOLIDATION_MINUTES),
        "breakout_buffer_range_pcts": list(BREAKOUT_BUFFER_RANGE_PCTS),
        "signal_window_minutes": SIGNAL_WINDOW_MINUTES,
        "cooldown_minutes_approx": COOLDOWN_MINUTES,
        "time_normalized": True,
        "timeframe_meta": _safe(timeframe_meta),
        "trading_days_by_timeframe": _safe(trading_days_by_timeframe),
        "grid_rows": int(len(ranked)),
        "best_row": _safe(best),
        "best_by_timeframe": _safe(best_by_timeframe.to_dict(orient="records")),
        "daily_cadence_rows": _safe(daily_cadence.to_dict(orient="records")),
        "near_daily_cadence_rows": _safe(near_daily_cadence.to_dict(orient="records")),
        "baseline_controls": _safe(control_frame.to_dict(orient="records")),
        "baseline_control_timeframes_available": control_timeframes,
        "artifacts": {
            "ranked_rows": str(ranked_path.relative_to(ROOT)),
            "best_by_timeframe": str(best_by_tf_path.relative_to(ROOT)),
            "daily_cadence_rows": str(daily_cadence_path.relative_to(ROOT)),
            "near_daily_cadence_rows": str(near_daily_cadence_path.relative_to(ROOT)),
            "top_trades": str(best_trades_path.relative_to(ROOT)),
            "top_yearly": str(best_yearly_path.relative_to(ROOT)),
            "baseline_controls": str(control_path.relative_to(ROOT)),
            "baseline_controls_yearly": str(control_yearly_path.relative_to(ROOT)),
            "report": str(REPORT_PATH.relative_to(ROOT)),
        },
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    best_daily = daily_cadence.iloc[0].to_dict() if not daily_cadence.empty else None
    best_near_daily = near_daily_cadence.iloc[0].to_dict() if not near_daily_cadence.empty else None
    control_note = (
        f"Baseline trade-level controls available for: `{', '.join(control_timeframes)}`."
        if control_timeframes
        else "No baseline trade-level controls were available from the requested static-RR top-trades CSV."
    )

    report_lines = [
        "# NQ NY VWAP BOS Timeframe Challenger",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{DATA_START}` to `<{DATA_END_EXCLUSIVE}` from raw NQ 1m bars; 2m/3m/5m were resampled from 1m for alignment.",
        f"- Timeframes: `{', '.join(f'{tf}m' for tf in TIMEFRAMES)}`",
        "- Direction: long-only.",
        f"- Exit: fixed static `{RR}:1` reward-to-risk with stop priority on same-bar stop/target touches.",
        f"- Stop: `{STOP_BASIS}` `{STOP_PCT:.1%}` rounded up to even NQ ticks.",
        "- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full NY RTH window.",
        f"- Time normalization: consolidation bars = round(minutes/timeframe), signal window ~= `{SIGNAL_WINDOW_MINUTES}` minutes, cooldown = ceil(`{COOLDOWN_MINUTES}`/timeframe).",
        "- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.",
        "",
        "## Challenger Entry Criteria",
        "",
        "Long setup:",
        "",
        "1. Use NY RTH session VWAP as the mean.",
        "2. Price must be below VWAP and extend at least `0.025 * prior 14-day RTH ATR` away from VWAP.",
        "3. Wait for an `N`-minute consolidation below VWAP; tested `15`, `21`, `30`, `45`, and `60` minutes.",
        "4. The consolidation range must be `<= 0.20 * ATR` and every consolidation bar high must stay below its same-bar VWAP.",
        "5. Signal bar must close above `consolidation high + buffer * consolidation range`, while still closing below VWAP.",
        "6. Enter long on the next native bar open. Maximum 3 sequential non-overlapping trades/day, about 10 minutes cooldown after exit.",
        "",
        "The buffer grid was `0%`, `10%`, `25%`, and `50%` of the consolidation range above the consolidation high.",
        "",
        "## Baseline Controls",
        "",
        control_note,
        "",
        _format_table(control_frame, control_cols, n=None),
        "",
        "## Best By Timeframe",
        "",
        _format_table(best_by_timeframe, result_cols, n=None),
        "",
        "## Daily-Cadence Challenger Rows",
        "",
        "These are the practical rows that preserve the target of at least about one trade/day.",
        "",
        _format_table(daily_cadence, result_cols, n=20),
        "",
        "## Near-Daily Challenger Rows",
        "",
        "These are included to show rows just below one trade/day when quality improves but cadence thins.",
        "",
        _format_table(near_daily_cadence, result_cols, n=20),
        "",
        "## Top Challenger Rows",
        "",
        _format_table(ranked, result_cols, n=25),
        "",
        "## Best Challenger Year Split",
        "",
        _format_table(best_yearly, yearly_cols, n=None),
        "",
        "## Summary Read",
        "",
        f"- Best overall BOS row: `{best['timeframe']}` `{int(best['consolidation_minutes'])}m` consolidation with `{best['breakout_buffer_range_pct']:.0%}` range buffer; `{int(best['total_trades'])}` trades, `{best['avg_trades_per_day']}` trades/day, `{best['total_r']:+.2f}R`, PF `{best['profit_factor']:.3f}`, Calmar `{best['calmar']:.3f}`, max DD `{best['max_drawdown_r']:.2f}R`.",
        (
            f"- Best daily-cadence BOS row: `{best_daily['timeframe']}` `{int(best_daily['consolidation_minutes'])}m` consolidation with `{best_daily['breakout_buffer_range_pct']:.0%}` range buffer; `{int(best_daily['total_trades'])}` trades, `{best_daily['avg_trades_per_day']}` trades/day, `{best_daily['total_r']:+.2f}R`, PF `{best_daily['profit_factor']:.3f}`, Calmar `{best_daily['calmar']:.3f}`, max DD `{best_daily['max_drawdown_r']:.2f}R`."
            if best_daily is not None
            else "- No BOS rows reached the daily-cadence view of at least one trade/day."
        ),
        (
            f"- Best near-daily BOS row: `{best_near_daily['timeframe']}` `{int(best_near_daily['consolidation_minutes'])}m` consolidation with `{best_near_daily['breakout_buffer_range_pct']:.0%}` range buffer; `{int(best_near_daily['total_trades'])}` trades, `{best_near_daily['avg_trades_per_day']}` trades/day, `{best_near_daily['total_r']:+.2f}R`, PF `{best_near_daily['profit_factor']:.3f}`, Calmar `{best_near_daily['calmar']:.3f}`, max DD `{best_near_daily['max_drawdown_r']:.2f}R`."
            if best_near_daily is not None
            else "- No BOS rows reached the near-daily view of at least 0.75 trades/day."
        ),
        "- Treat this as a challenger screen only. Promotion would require implementation as live-native logic, exact replay, and train/validation before prop-firm lifecycle scoring.",
        "",
        "## Artifacts",
        "",
        f"- Ranked rows: `backtesting/data/results/{RUN_SLUG}/ranked_rows.csv`",
        f"- Best by timeframe: `backtesting/data/results/{RUN_SLUG}/best_by_timeframe.csv`",
        f"- Daily cadence rows: `backtesting/data/results/{RUN_SLUG}/daily_cadence_rows.csv`",
        f"- Near-daily rows: `backtesting/data/results/{RUN_SLUG}/near_daily_cadence_rows.csv`",
        f"- Baseline controls: `backtesting/data/results/{RUN_SLUG}/baseline_controls.csv`",
        f"- Top trades: `backtesting/data/results/{RUN_SLUG}/top_bos_timeframe_challenger_trades.csv`",
        f"- Top yearly: `backtesting/data/results/{RUN_SLUG}/top_bos_timeframe_challenger_yearly.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"\nWrote {REPORT_PATH.relative_to(ROOT)}")
    print(f"Wrote artifacts under {RESULT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
