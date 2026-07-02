#!/usr/bin/env python3
"""Recent 5-year NQ NY level mean-reversion context-filter pass.

Tests intraday regime/context filters on the state-machine level-reversion
anchors from the prior pass. Research artifact only; not wired to live execution.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402


RUN_SLUG = "nq_ny_level_reversion_context_filter_recent5_20260629"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LEVEL_REVERSION_CONTEXT_FILTER_RECENT5_20260629.md"
PRIOR_RANKED_PATH = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_level_reversion_state_machine_recent5_20260629"
    / "ranked_candidates.csv"
)

DATA_START = "2021-06-05"
DATA_END_EXCLUSIVE = "2026-06-06"
ENTRY_START = "09:45"
ENTRY_END = "15:00"
FLAT_TIME = "15:55"
VWAP_SLOPE_REJECT_ATR = 0.02
VWAP_DISTANCE_REJECT_ATR = 0.10

TIME_BUCKETS = {
    "full": (ENTRY_START, ENTRY_END),
    "10:00-12:00": ("10:00", "12:00"),
    "10:00-14:00": ("10:00", "14:00"),
    "11:00-15:00": ("11:00", "15:00"),
}


@dataclass(frozen=True)
class PreparedDay:
    date: str
    timestamps: list[pd.Timestamp]
    times: list[str]
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    vwap: np.ndarray
    day_mid: np.ndarray
    session_high_so_far: np.ndarray
    session_low_so_far: np.ndarray
    session_range_atr: np.ndarray
    directional_efficiency: np.ndarray
    vwap_slope_atr: np.ndarray
    structure_30m: list[str]
    ib_high_30: float
    ib_low_30: float
    ib_mid_30: float
    atr: float


@dataclass(frozen=True)
class StateMachineConfig:
    label: str
    mean_mode: str
    extension_atr_pct: float
    consolidation_bars: int
    consolidation_atr_pct: float
    setup_timeout_bars: int
    stop_buffer_atr_pct: float
    min_rr_to_mean: float
    cooldown_bars: int = 2
    max_trades_per_day: int = 3


@dataclass(frozen=True)
class ContextConfig:
    structure_gate: str
    vwap_acceptance: str
    efficiency_max: float | None
    ib_location: str
    session_range_atr_max: float | None
    time_bucket: str


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


def _time_str(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%H:%M")


def _minutes(value: str) -> int:
    hour, minute = value.split(":")
    return int(hour) * 60 + int(minute)


def _variant_id(config: StateMachineConfig) -> str:
    return (
        f"{config.mean_mode}_ext{config.extension_atr_pct:g}_"
        f"cons{config.consolidation_bars}x{config.consolidation_atr_pct:g}_"
        f"timeout{config.setup_timeout_bars}_buf{config.stop_buffer_atr_pct:g}_"
        f"minrr{config.min_rr_to_mean:g}"
    )


def _prepare_rth(df: pd.DataFrame) -> pd.DataFrame:
    rth = df.between_time("09:30", "16:00").copy()
    rth["date"] = rth.index.date.astype(str)
    typical = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    rth["_tpv"] = typical * rth["volume"].astype(float)
    grouped = rth.groupby("date", sort=True)
    rth["session_vwap"] = grouped["_tpv"].cumsum() / grouped["volume"].cumsum().replace(0, np.nan)

    daily = grouped.agg({"high": "max", "low": "min"})
    daily["range"] = daily["high"] - daily["low"]
    daily["atr14_prev"] = daily["range"].rolling(14, min_periods=5).mean().shift(1)
    fallback = float(daily["range"].median())
    rth["atr14_prev"] = rth["date"].map(daily["atr14_prev"]).fillna(fallback)
    return rth.drop(columns=["_tpv"])


def _completed_30m_structure(times: list[str], highs: np.ndarray, lows: np.ndarray) -> list[str]:
    session_start = _minutes("09:30")
    group_nums = [max(0, (_minutes(value) - session_start) // 30) for value in times]
    group_high: dict[int, float] = {}
    group_low: dict[int, float] = {}
    for idx, group_num in enumerate(group_nums):
        group_high[group_num] = max(group_high.get(group_num, -math.inf), float(highs[idx]))
        group_low[group_num] = min(group_low.get(group_num, math.inf), float(lows[idx]))

    structures: list[str] = []
    for group_num in group_nums:
        completed = sorted(value for value in group_high if value < group_num)
        if len(completed) < 2:
            structures.append("unknown")
            continue
        prior = completed[-2]
        latest = completed[-1]
        if group_high[latest] > group_high[prior] and group_low[latest] > group_low[prior]:
            structures.append("bullish")
        elif group_high[latest] < group_high[prior] and group_low[latest] < group_low[prior]:
            structures.append("bearish")
        else:
            structures.append("mixed")
    return structures


def _prepare_days(rth: pd.DataFrame) -> list[PreparedDay]:
    days: list[PreparedDay] = []
    for date, day in rth.groupby("date", sort=True):
        timestamps = list(day.index)
        times = [_time_str(ts) for ts in timestamps]
        opens = day["open"].to_numpy(dtype=float)
        highs = day["high"].to_numpy(dtype=float)
        lows = day["low"].to_numpy(dtype=float)
        closes = day["close"].to_numpy(dtype=float)
        vwap = day["session_vwap"].to_numpy(dtype=float)
        day_mid = (np.maximum.accumulate(highs) + np.minimum.accumulate(lows)) / 2.0
        session_high_so_far = np.maximum.accumulate(highs)
        session_low_so_far = np.minimum.accumulate(lows)
        session_range = np.maximum(session_high_so_far - session_low_so_far, 0.25)
        atr = float(day["atr14_prev"].iloc[0])
        session_range_atr = session_range / atr
        directional_efficiency = np.abs(closes - float(opens[0])) / session_range

        vwap_slope_atr = np.zeros(len(vwap), dtype=float)
        if len(vwap) > 6:
            vwap_slope_atr[6:] = (vwap[6:] - vwap[:-6]) / atr

        ib_mask = [idx for idx, value in enumerate(times) if "09:30" <= value < "10:00"]
        ib_high = float("nan")
        ib_low = float("nan")
        ib_mid = float("nan")
        if ib_mask:
            ib_high = float(np.max(highs[ib_mask]))
            ib_low = float(np.min(lows[ib_mask]))
            ib_mid = (ib_high + ib_low) / 2.0

        if math.isfinite(atr) and atr > 0 and len(day) >= 20:
            days.append(
                PreparedDay(
                    date=str(date),
                    timestamps=timestamps,
                    times=times,
                    opens=opens,
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    vwap=vwap,
                    day_mid=day_mid,
                    session_high_so_far=session_high_so_far,
                    session_low_so_far=session_low_so_far,
                    session_range_atr=session_range_atr,
                    directional_efficiency=directional_efficiency,
                    vwap_slope_atr=vwap_slope_atr,
                    structure_30m=_completed_30m_structure(times, highs, lows),
                    ib_high_30=ib_high,
                    ib_low_30=ib_low,
                    ib_mid_30=ib_mid,
                    atr=atr,
                )
            )
    return days


def _mean_level(day: PreparedDay, mode: str, idx: int) -> float | None:
    if mode == "vwap":
        value = float(day.vwap[idx])
        return value if math.isfinite(value) else None
    if mode == "ib_mid30":
        if day.times[idx] < "10:00" or not math.isfinite(day.ib_mid_30):
            return None
        return float(day.ib_mid_30)
    if mode == "day_mid":
        return float(day.day_mid[idx])
    raise ValueError(f"Unknown mean_mode: {mode}")


def _simulate_exit(
    day: PreparedDay,
    *,
    direction: int,
    entry_idx: int,
    entry: float,
    stop: float,
    target: float,
    risk: float,
) -> tuple[int, float, str, float]:
    exit_idx = len(day.timestamps) - 1
    exit_price = float(day.closes[-1])
    exit_type = "eod"
    for scan_idx in range(entry_idx, len(day.timestamps)):
        if day.times[scan_idx] > FLAT_TIME:
            exit_idx = scan_idx - 1 if scan_idx > entry_idx else scan_idx
            exit_price = float(day.closes[exit_idx])
            exit_type = "eod"
            break
        if direction == 1:
            stop_hit = day.lows[scan_idx] <= stop
            target_hit = day.highs[scan_idx] >= target
            if stop_hit:
                exit_idx = scan_idx
                exit_price = stop
                exit_type = "stop"
                break
            if target_hit:
                exit_idx = scan_idx
                exit_price = target
                exit_type = "target"
                break
        else:
            stop_hit = day.highs[scan_idx] >= stop
            target_hit = day.lows[scan_idx] <= target
            if stop_hit:
                exit_idx = scan_idx
                exit_price = stop
                exit_type = "stop"
                break
            if target_hit:
                exit_idx = scan_idx
                exit_price = target
                exit_type = "target"
                break

    pnl_points = (exit_price - entry) * direction
    r_multiple = pnl_points / risk if risk > 0 else 0.0
    return exit_idx, exit_price, exit_type, r_multiple


def _try_setup_from_extension(
    day: PreparedDay,
    config: StateMachineConfig,
    extension_idx: int,
    direction: int,
) -> dict[str, Any] | None:
    extension = config.extension_atr_pct * day.atr
    stop_buffer = config.stop_buffer_atr_pct * day.atr
    start_signal_idx = extension_idx + 1 + config.consolidation_bars
    end_signal_idx = min(
        len(day.timestamps) - 2,
        extension_idx + config.setup_timeout_bars,
    )
    if start_signal_idx > end_signal_idx:
        return None

    for signal_idx in range(start_signal_idx, end_signal_idx + 1):
        if day.times[signal_idx] < ENTRY_START or day.times[signal_idx] > ENTRY_END:
            continue
        mean = _mean_level(day, config.mean_mode, signal_idx)
        if mean is None:
            continue

        cons_slice = slice(signal_idx - config.consolidation_bars, signal_idx)
        cons_high = float(np.max(day.highs[cons_slice]))
        cons_low = float(np.min(day.lows[cons_slice]))
        cons_range = cons_high - cons_low
        if cons_range > config.consolidation_atr_pct * day.atr:
            continue

        if direction == 1:
            if cons_high >= mean or mean - cons_low < extension:
                continue
            swept = day.lows[signal_idx] < cons_low
            reclaimed = day.closes[signal_idx] > cons_low and day.closes[signal_idx] < mean
            if not (swept and reclaimed):
                continue
            entry_idx = signal_idx + 1
            entry = float(day.opens[entry_idx])
            stop = float(day.lows[signal_idx] - stop_buffer)
            target = float(mean)
            risk = entry - stop
            reward = target - entry
        else:
            if cons_low <= mean or cons_high - mean < extension:
                continue
            swept = day.highs[signal_idx] > cons_high
            reclaimed = day.closes[signal_idx] < cons_high and day.closes[signal_idx] > mean
            if not (swept and reclaimed):
                continue
            entry_idx = signal_idx + 1
            entry = float(day.opens[entry_idx])
            stop = float(day.highs[signal_idx] + stop_buffer)
            target = float(mean)
            risk = stop - entry
            reward = entry - target

        if risk <= 0 or reward <= 0 or reward / risk < config.min_rr_to_mean:
            continue

        exit_idx, exit_price, exit_type, r_multiple = _simulate_exit(
            day,
            direction=direction,
            entry_idx=entry_idx,
            entry=entry,
            stop=stop,
            target=target,
            risk=risk,
        )
        vwap_value = float(day.vwap[signal_idx])
        close = float(day.closes[signal_idx])
        directional_vwap_distance_atr = ((vwap_value - close) * direction) / day.atr
        return {
            "date": day.date,
            "direction": "long" if direction == 1 else "short",
            "direction_int": direction,
            "mean_mode": config.mean_mode,
            "base_label": config.label,
            "base_variant_id": _variant_id(config),
            "extension_idx": extension_idx,
            "signal_idx": signal_idx,
            "entry_idx": entry_idx,
            "exit_idx": exit_idx,
            "extension_ts": day.timestamps[extension_idx].isoformat(),
            "signal_ts": day.timestamps[signal_idx].isoformat(),
            "signal_time": day.times[signal_idx],
            "entry_ts": day.timestamps[entry_idx].isoformat(),
            "exit_ts": day.timestamps[exit_idx].isoformat(),
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "exit_price": round(exit_price, 2),
            "exit_type": exit_type,
            "risk_points": round(risk, 2),
            "reward_points": round(reward, 2),
            "rr_to_mean": round(reward / risk, 4),
            "r_multiple": round(r_multiple, 4),
            "atr14_prev": round(day.atr, 2),
            "setup_wait_bars": signal_idx - extension_idx,
            "signal_close": round(close, 2),
            "signal_vwap": round(vwap_value, 2),
            "vwap_slope_atr": round(float(day.vwap_slope_atr[signal_idx]), 5),
            "directional_vwap_distance_atr": round(float(directional_vwap_distance_atr), 5),
            "session_range_atr": round(float(day.session_range_atr[signal_idx]), 5),
            "directional_efficiency": round(float(day.directional_efficiency[signal_idx]), 5),
            "structure_30m": day.structure_30m[signal_idx],
            "ib_high_30": round(day.ib_high_30, 2),
            "ib_low_30": round(day.ib_low_30, 2),
            "signal_high": round(float(day.highs[signal_idx]), 2),
            "signal_low": round(float(day.lows[signal_idx]), 2),
        }

    return None


def _generate_candidates_for_day(day: PreparedDay, config: StateMachineConfig) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    extension = config.extension_atr_pct * day.atr
    for idx in range(0, len(day.timestamps) - 2):
        bar_time = day.times[idx]
        if bar_time < ENTRY_START or bar_time > ENTRY_END:
            continue
        mean = _mean_level(day, config.mean_mode, idx)
        if mean is None:
            continue

        direction = 0
        if day.closes[idx] < mean and mean - day.lows[idx] >= extension:
            direction = 1
        elif day.closes[idx] > mean and day.highs[idx] - mean >= extension:
            direction = -1
        else:
            continue

        candidate = _try_setup_from_extension(day, config, idx, direction)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def _is_clean_30m_acceptance(candidate: dict[str, Any]) -> bool:
    direction = int(candidate["direction_int"])
    structure = str(candidate["structure_30m"])
    close = float(candidate["signal_close"])
    vwap = float(candidate["signal_vwap"])
    if direction == 1:
        return structure == "bearish" and close < vwap
    return structure == "bullish" and close > vwap


def _vwap_slope_rejects(candidate: dict[str, Any]) -> bool:
    direction = int(candidate["direction_int"])
    close = float(candidate["signal_close"])
    vwap = float(candidate["signal_vwap"])
    slope = float(candidate["vwap_slope_atr"])
    if direction == 1:
        return close < vwap and slope <= -VWAP_SLOPE_REJECT_ATR
    return close > vwap and slope >= VWAP_SLOPE_REJECT_ATR


def _vwap_distance_rejects(candidate: dict[str, Any]) -> bool:
    return float(candidate["directional_vwap_distance_atr"]) >= VWAP_DISTANCE_REJECT_ATR


def _ib_accepts(candidate: dict[str, Any], mode: str) -> bool:
    if mode == "none":
        return True
    if not math.isfinite(float(candidate["ib_high_30"])) or not math.isfinite(float(candidate["ib_low_30"])):
        return False
    direction = int(candidate["direction_int"])
    high = float(candidate["signal_high"])
    low = float(candidate["signal_low"])
    close = float(candidate["signal_close"])
    ib_high = float(candidate["ib_high_30"])
    ib_low = float(candidate["ib_low_30"])
    if direction == 1:
        if mode == "must_be_outside_ib":
            return low < ib_low
        if mode == "must_reclaim_inside_ib":
            return low < ib_low and close > ib_low
    else:
        if mode == "must_be_outside_ib":
            return high > ib_high
        if mode == "must_reclaim_inside_ib":
            return high > ib_high and close < ib_high
    raise ValueError(f"Unknown ib_location mode: {mode}")


def _context_accepts(candidate: dict[str, Any], context: ContextConfig) -> bool:
    bucket_start, bucket_end = TIME_BUCKETS[context.time_bucket]
    signal_time = str(candidate["signal_time"])
    if signal_time < bucket_start or signal_time > bucket_end:
        return False

    if context.structure_gate == "reject_30m_trend_acceptance" and _is_clean_30m_acceptance(candidate):
        return False
    if context.structure_gate == "require_30m_mixed" and candidate["structure_30m"] != "mixed":
        return False
    if context.structure_gate not in ("none", "reject_30m_trend_acceptance", "require_30m_mixed"):
        raise ValueError(f"Unknown structure_gate: {context.structure_gate}")

    if context.vwap_acceptance == "reject_vwap_side_slope" and _vwap_slope_rejects(candidate):
        return False
    if context.vwap_acceptance == "reject_vwap_side_distance" and _vwap_distance_rejects(candidate):
        return False
    if context.vwap_acceptance not in ("none", "reject_vwap_side_slope", "reject_vwap_side_distance"):
        raise ValueError(f"Unknown vwap_acceptance: {context.vwap_acceptance}")

    if context.efficiency_max is not None:
        if float(candidate["directional_efficiency"]) > context.efficiency_max:
            return False

    if not _ib_accepts(candidate, context.ib_location):
        return False

    if context.session_range_atr_max is not None:
        if float(candidate["session_range_atr"]) > context.session_range_atr_max:
            return False

    return True


def _simulate_context(
    candidates_by_day: list[list[dict[str, Any]]],
    base_config: StateMachineConfig,
    context: ContextConfig,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    context_fields = asdict(context)
    for day_candidates in candidates_by_day:
        current_min_idx = 0
        day_trade_count = 0
        for candidate in day_candidates:
            if day_trade_count >= base_config.max_trades_per_day:
                break
            if (
                int(candidate["extension_idx"]) < current_min_idx
                or int(candidate["signal_idx"]) < current_min_idx
                or int(candidate["entry_idx"]) < current_min_idx
            ):
                continue
            if not _context_accepts(candidate, context):
                continue
            trade = {
                key: value
                for key, value in candidate.items()
                if key
                not in {
                    "direction_int",
                    "extension_idx",
                    "signal_idx",
                    "entry_idx",
                    "exit_idx",
                }
            }
            trade.update(context_fields)
            trades.append(trade)
            day_trade_count += 1
            current_min_idx = int(candidate["exit_idx"]) + base_config.cooldown_bars
    return trades


def _max_drawdown(values: list[float]) -> float:
    equity = np.cumsum(np.array(values, dtype=float))
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _score_trades(
    trades: list[dict[str, Any]],
    trading_days: int,
    base_config: StateMachineConfig,
    context: ContextConfig,
    total_candidates: int,
) -> dict[str, Any]:
    rs = [float(row["r_multiple"]) for row in trades]
    wins = [value for value in rs if value > 0]
    losses = [value for value in rs if value < 0]
    by_day = pd.Series([row["date"] for row in trades]).value_counts() if trades else pd.Series(dtype=int)
    days_with_trade = int((by_day > 0).sum())
    days_1_to_3 = int(((by_day >= 1) & (by_day <= 3)).sum())
    avg_trades_per_day = len(trades) / trading_days if trading_days else 0.0
    pct_days_with_trade = days_with_trade / trading_days if trading_days else 0.0
    pct_days_1_to_3 = days_1_to_3 / trading_days if trading_days else 0.0
    total_r = float(sum(rs))
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else (999.0 if wins else 0.0)
    max_dd = _max_drawdown(rs)
    frequency_penalty = abs(avg_trades_per_day - 1.5) * 18.0 + max(0.0, 0.70 - pct_days_with_trade) * 70.0
    rank_score = total_r + 30.0 * min(profit_factor, 2.0) + 80.0 * pct_days_1_to_3 + 0.30 * max_dd - frequency_penalty
    exits = pd.Series([row["exit_type"] for row in trades]).value_counts().to_dict() if trades else {}
    waits = [int(row["setup_wait_bars"]) for row in trades]
    baseline_context = (
        context.structure_gate == "none"
        and context.vwap_acceptance == "none"
        and context.efficiency_max is None
        and context.ib_location == "none"
        and context.session_range_atr_max is None
        and context.time_bucket == "full"
    )
    return {
        "base_label": base_config.label,
        "base_variant_id": _variant_id(base_config),
        "mean_mode": base_config.mean_mode,
        **asdict(context),
        "is_baseline_context": baseline_context,
        "rank_score": round(rank_score, 4),
        "total_candidates": total_candidates,
        "total_trades": len(trades),
        "trading_days": trading_days,
        "avg_trades_per_day": round(avg_trades_per_day, 4),
        "days_with_trade": days_with_trade,
        "pct_days_with_trade": round(pct_days_with_trade, 4),
        "pct_days_1_to_3_trades": round(pct_days_1_to_3, 4),
        "zero_trade_days": trading_days - days_with_trade,
        "total_r": round(total_r, 4),
        "avg_r": round(total_r / len(trades), 4) if trades else 0.0,
        "profit_factor": round(float(profit_factor), 4),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "target_exits": int(exits.get("target", 0)),
        "stop_exits": int(exits.get("stop", 0)),
        "eod_exits": int(exits.get("eod", 0)),
        "avg_setup_wait_bars": round(float(np.mean(waits)), 2) if waits else None,
        "deployability": "research_only",
        "live_support_notes": (
            "Context-filtered level-reversion prototype exists only in this research script; "
            "live execution and exact replay parity are not implemented."
        ),
        "exact_replay_required": "yes",
    }


def _make_context_grid() -> list[ContextConfig]:
    contexts: list[ContextConfig] = []
    for structure_gate in ("none", "reject_30m_trend_acceptance", "require_30m_mixed"):
        for vwap_acceptance in ("none", "reject_vwap_side_slope", "reject_vwap_side_distance"):
            for efficiency_max in (None, 0.35, 0.45, 0.55, 0.65):
                for ib_location in ("none", "must_be_outside_ib", "must_reclaim_inside_ib"):
                    for session_range_atr_max in (None, 1.25, 1.50, 1.75, 2.00):
                        for time_bucket in ("full", "10:00-12:00", "10:00-14:00", "11:00-15:00"):
                            contexts.append(
                                ContextConfig(
                                    structure_gate=structure_gate,
                                    vwap_acceptance=vwap_acceptance,
                                    efficiency_max=efficiency_max,
                                    ib_location=ib_location,
                                    session_range_atr_max=session_range_atr_max,
                                    time_bucket=time_bucket,
                                )
                            )
    return contexts


def _load_anchor_configs() -> tuple[list[StateMachineConfig], pd.DataFrame]:
    prior = pd.read_csv(PRIOR_RANKED_PATH)
    anchors: list[pd.Series] = []
    for mean_mode in ("day_mid", "vwap", "ib_mid30"):
        subset = prior[prior["mean_mode"] == mean_mode].sort_values("rank")
        if subset.empty:
            continue
        row = subset.iloc[0].copy()
        row["anchor_label"] = f"{mean_mode}_edge_anchor"
        anchors.append(row)

    frequency_subset = prior[
        (prior["avg_trades_per_day"] >= 1.0)
        & (prior["avg_trades_per_day"] <= 3.0)
        & (prior["pct_days_with_trade"] >= 0.70)
    ].sort_values("rank")
    if not frequency_subset.empty:
        row = frequency_subset.iloc[0].copy()
        row["anchor_label"] = "best_cadence_anchor"
        anchors.append(row)

    configs: list[StateMachineConfig] = []
    seen: set[str] = set()
    for row in anchors:
        variant = str(row["variant_id"])
        label = str(row["anchor_label"])
        if variant in seen:
            continue
        seen.add(variant)
        configs.append(
            StateMachineConfig(
                label=label,
                mean_mode=str(row["mean_mode"]),
                extension_atr_pct=float(row["extension_atr_pct"]),
                consolidation_bars=int(row["consolidation_bars"]),
                consolidation_atr_pct=float(row["consolidation_atr_pct"]),
                setup_timeout_bars=int(row["setup_timeout_bars"]),
                stop_buffer_atr_pct=float(row["stop_buffer_atr_pct"]),
                min_rr_to_mean=float(row["min_rr_to_mean"]),
                cooldown_bars=int(row.get("cooldown_bars", 2)),
                max_trades_per_day=int(row.get("max_trades_per_day", 3)),
            )
        )
    return configs, prior


def _add_baseline_deltas(results: pd.DataFrame) -> pd.DataFrame:
    rows = results.copy()
    baseline = rows[rows["is_baseline_context"]].set_index("base_label")
    for column in ("total_r", "profit_factor", "max_drawdown_r", "total_trades", "pct_days_with_trade"):
        rows[f"baseline_{column}"] = rows["base_label"].map(baseline[column])
    rows["total_r_delta"] = (rows["total_r"] - rows["baseline_total_r"]).round(4)
    rows["profit_factor_delta"] = (rows["profit_factor"] - rows["baseline_profit_factor"]).round(4)
    rows["drawdown_improvement_r"] = (rows["max_drawdown_r"] - rows["baseline_max_drawdown_r"]).round(4)
    rows["trade_delta"] = (rows["total_trades"] - rows["baseline_total_trades"]).astype(int)
    rows["coverage_delta"] = (rows["pct_days_with_trade"] - rows["baseline_pct_days_with_trade"]).round(4)
    return rows


def _best_by(rows: pd.DataFrame, column: str, report_cols: list[str]) -> str:
    best = (
        rows.sort_values(["rank_score", "total_r", "profit_factor"], ascending=[False, False, False])
        .groupby(column, dropna=False)
        .head(1)
        .sort_values(column)
    )
    return best[report_cols].to_markdown(index=False)


def _yearly_table(trades: pd.DataFrame) -> str:
    if trades.empty:
        return "_None._"
    yearly = trades.assign(year=trades["date"].str.slice(0, 4)).groupby("year").agg(
        trades=("r_multiple", "size"),
        total_r=("r_multiple", "sum"),
        avg_r=("r_multiple", "mean"),
        win_rate=("r_multiple", lambda values: float((values > 0).mean())),
    )
    yearly["total_r"] = yearly["total_r"].round(2)
    yearly["avg_r"] = yearly["avg_r"].round(4)
    yearly["win_rate"] = yearly["win_rate"].round(4)
    return yearly.reset_index().to_markdown(index=False)


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading NQ 5m data {DATA_START} to {DATA_END_EXCLUSIVE}...")
    df = load_5m_data(NQ.data_file, start=DATA_START, end=DATA_END_EXCLUSIVE)
    days = _prepare_days(_prepare_rth(df))
    trading_days = len(days)
    print(f"Prepared {trading_days} RTH days; first={days[0].date} last={days[-1].date}")

    base_configs, prior = _load_anchor_configs()
    contexts = _make_context_grid()
    print(f"Anchors: {len(base_configs)}")
    for config in base_configs:
        print(f"  {config.label}: {_variant_id(config)}")
    print(f"Context grid: {len(contexts)} per anchor; total rows={len(contexts) * len(base_configs)}")

    rows: list[dict[str, Any]] = []
    trades_by_key: dict[tuple[str, int], list[dict[str, Any]]] = {}
    baseline_audit: list[dict[str, Any]] = []
    for base_idx, base_config in enumerate(base_configs, start=1):
        print(f"Generating candidates for {base_config.label} ({base_idx}/{len(base_configs)})...")
        candidates_by_day = [_generate_candidates_for_day(day, base_config) for day in days]
        total_candidates = sum(len(day_candidates) for day_candidates in candidates_by_day)
        print(f"  candidate events={total_candidates}")
        for context_idx, context in enumerate(contexts, start=1):
            trades = _simulate_context(candidates_by_day, base_config, context)
            row = _score_trades(trades, trading_days, base_config, context, total_candidates)
            rows.append(row)
            if row["is_baseline_context"]:
                trades_by_key[(base_config.label, context_idx)] = trades
                previous = prior[prior["variant_id"] == _variant_id(base_config)].sort_values("rank").head(1)
                if not previous.empty:
                    prior_row = previous.iloc[0]
                    baseline_audit.append(
                        {
                            "base_label": base_config.label,
                            "variant_id": _variant_id(base_config),
                            "prior_total_trades": int(prior_row["total_trades"]),
                            "replay_total_trades": int(row["total_trades"]),
                            "prior_total_r": round(float(prior_row["total_r"]), 4),
                            "replay_total_r": round(float(row["total_r"]), 4),
                            "prior_profit_factor": round(float(prior_row["profit_factor"]), 4),
                            "replay_profit_factor": round(float(row["profit_factor"]), 4),
                        }
                    )
            if context_idx % 500 == 0:
                print(f"  {base_config.label}: completed {context_idx}/{len(contexts)} contexts", flush=True)

    results = _add_baseline_deltas(pd.DataFrame(rows))
    ranked = results.sort_values(
        [
            "rank_score",
            "pct_days_with_trade",
            "avg_trades_per_day",
            "total_r",
            "profit_factor",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))

    frequency_fit = ranked[
        (ranked["avg_trades_per_day"] >= 1.0)
        & (ranked["avg_trades_per_day"] <= 3.0)
        & (ranked["pct_days_with_trade"] >= 0.70)
    ].copy()
    edge_improved = ranked[
        (ranked["profit_factor"] >= 1.15)
        & (ranked["total_r_delta"] > 0)
        & (ranked["total_trades"] >= 300)
    ].copy()
    high_coverage_positive = ranked[
        (ranked["pct_days_with_trade"] >= 0.80)
        & (ranked["total_r"] > 0)
    ].copy()
    freq_pf105 = frequency_fit[frequency_fit["profit_factor"] >= 1.05].copy()

    ranked_path = RESULT_DIR / "ranked_context_candidates.csv"
    summary_path = RESULT_DIR / "summary.json"
    audit_path = RESULT_DIR / "baseline_audit.csv"
    ranked.to_csv(ranked_path, index=False)
    pd.DataFrame(baseline_audit).to_csv(audit_path, index=False)

    best_row = ranked.iloc[0].to_dict() if not ranked.empty else {}
    best_freq_row = frequency_fit.iloc[0].to_dict() if not frequency_fit.empty else {}
    best_key_context = None
    if best_row:
        best_context = ContextConfig(
            structure_gate=str(best_row["structure_gate"]),
            vwap_acceptance=str(best_row["vwap_acceptance"]),
            efficiency_max=(
                None
                if pd.isna(best_row["efficiency_max"])
                else float(best_row["efficiency_max"])
            ),
            ib_location=str(best_row["ib_location"]),
            session_range_atr_max=(
                None
                if pd.isna(best_row["session_range_atr_max"])
                else float(best_row["session_range_atr_max"])
            ),
            time_bucket=str(best_row["time_bucket"]),
        )
        base_config = next(config for config in base_configs if config.label == best_row["base_label"])
        candidates_by_day = [_generate_candidates_for_day(day, base_config) for day in days]
        best_trades = _simulate_context(candidates_by_day, base_config, best_context)
        best_trades_path = RESULT_DIR / "best_context_trades.csv"
        pd.DataFrame(best_trades).to_csv(best_trades_path, index=False)
        best_key_context = str(best_trades_path.relative_to(ROOT))
    else:
        best_trades = []
        best_trades_path = RESULT_DIR / "best_context_trades.csv"
        pd.DataFrame(best_trades).to_csv(best_trades_path, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "context_filter_screen",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "available_last_day": days[-1].date if days else None,
        "trading_days": trading_days,
        "anchors": [_variant_id(config) for config in base_configs],
        "base_anchor_count": len(base_configs),
        "context_configs_per_anchor": len(contexts),
        "raw_context_rows": int(len(ranked)),
        "frequency_fit_configs": int(len(frequency_fit)),
        "frequency_fit_pf105_configs": int(len(freq_pf105)),
        "edge_improved_configs": int(len(edge_improved)),
        "high_coverage_positive_configs": int(len(high_coverage_positive)),
        "top_rows": ranked.head(20).to_dict(orient="records"),
        "top_frequency_fit_rows": frequency_fit.head(20).to_dict(orient="records"),
        "baseline_audit": baseline_audit,
        "best_context_trades": best_key_context,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_cols = [
        "rank",
        "base_label",
        "structure_gate",
        "vwap_acceptance",
        "efficiency_max",
        "ib_location",
        "session_range_atr_max",
        "time_bucket",
        "total_trades",
        "avg_trades_per_day",
        "pct_days_with_trade",
        "total_r",
        "avg_r",
        "profit_factor",
        "win_rate",
        "max_drawdown_r",
        "total_r_delta",
        "profit_factor_delta",
        "drawdown_improvement_r",
    ]
    short_cols = [
        "base_label",
        "structure_gate",
        "vwap_acceptance",
        "efficiency_max",
        "ib_location",
        "session_range_atr_max",
        "time_bucket",
        "total_trades",
        "avg_trades_per_day",
        "pct_days_with_trade",
        "total_r",
        "profit_factor",
        "max_drawdown_r",
        "total_r_delta",
    ]
    baseline_table = (
        ranked[ranked["is_baseline_context"]]
        .sort_values("base_label")[short_cols]
        .to_markdown(index=False)
    )
    top_freq = frequency_fit.head(20)[report_cols].to_markdown(index=False) if not frequency_fit.empty else "_None._"
    top_freq_pf105 = freq_pf105.head(20)[report_cols].to_markdown(index=False) if not freq_pf105.empty else "_None._"
    top_edge_improved = edge_improved.head(20)[report_cols].to_markdown(index=False) if not edge_improved.empty else "_None._"
    top_high_cov = (
        high_coverage_positive.head(20)[report_cols].to_markdown(index=False)
        if not high_coverage_positive.empty
        else "_None._"
    )
    best_by_base = (
        ranked.sort_values(["rank_score", "total_r"], ascending=[False, False])
        .groupby("base_label")
        .head(1)
        .sort_values("base_label")[report_cols]
        .to_markdown(index=False)
    )
    audit_table = pd.DataFrame(baseline_audit).to_markdown(index=False)

    report_lines = [
        "# NQ NY Level Mean-Reversion Context-Filter Recent 5-Year Pass",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{DATA_START}` to `<{DATA_END_EXCLUSIVE}` using available NQ 5m bars",
        f"- Trading days: `{trading_days}`",
        f"- Base anchors tested: `{len(base_configs)}`",
        f"- Context configs per anchor: `{len(contexts)}`",
        f"- Raw context rows: `{len(ranked)}`",
        "- Intrabar path assumption: conservative 5m bar path; stop wins if stop and target touch the same bar",
        "- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.",
        "",
        "## Context Grid",
        "",
        "- `structure_gate`: `none`, `reject_30m_trend_acceptance`, `require_30m_mixed`",
        "- `vwap_acceptance`: `none`, `reject_vwap_side_slope`, `reject_vwap_side_distance`",
        "- `efficiency_max`: `none`, `0.35`, `0.45`, `0.55`, `0.65`",
        "- `ib_location`: `none`, `must_be_outside_ib`, `must_reclaim_inside_ib`",
        "- `session_range_atr_max`: `none`, `1.25`, `1.50`, `1.75`, `2.00`",
        "- `time_bucket`: `full`, `10:00-12:00`, `10:00-14:00`, `11:00-15:00`",
        f"- VWAP slope rejection threshold: `{VWAP_SLOPE_REJECT_ATR}` ATR over the prior 6 bars",
        f"- VWAP distance rejection threshold: `{VWAP_DISTANCE_REJECT_ATR}` ATR on the continuation side of VWAP",
        "",
        "## Baseline Anchor Replay Audit",
        "",
        audit_table,
        "",
        "## Ungated Baselines",
        "",
        baseline_table,
        "",
        "## Top Rows By Frequency-Aware Score",
        "",
        ranked.head(25)[report_cols].to_markdown(index=False),
        "",
        "## Best Row Per Base Anchor",
        "",
        best_by_base,
        "",
        "## Top Frequency-Fit Rows",
        "",
        top_freq,
        "",
        "## Frequency-Fit Rows With PF >= 1.05",
        "",
        top_freq_pf105,
        "",
        "## Edge-Improved Rows",
        "",
        top_edge_improved,
        "",
        "## Positive Rows With >=80% Day Coverage",
        "",
        top_high_cov,
        "",
        "## Best By Filter Dimension",
        "",
        "### Structure Gate",
        "",
        _best_by(ranked, "structure_gate", short_cols),
        "",
        "### VWAP Acceptance",
        "",
        _best_by(ranked, "vwap_acceptance", short_cols),
        "",
        "### Efficiency Max",
        "",
        _best_by(ranked, "efficiency_max", short_cols),
        "",
        "### IB Location",
        "",
        _best_by(ranked, "ib_location", short_cols),
        "",
        "### Session Range ATR Max",
        "",
        _best_by(ranked, "session_range_atr_max", short_cols),
        "",
        "### Time Bucket",
        "",
        _best_by(ranked, "time_bucket", short_cols),
        "",
        "## Best Context Row Year Split",
        "",
        _yearly_table(pd.DataFrame(best_trades)),
        "",
        "## Summary Read",
        "",
        f"- Frequency-fit configs (`1-3` trades/day and >=70% day coverage): `{len(frequency_fit)}`",
        f"- Frequency-fit configs with PF `>=1.05`: `{len(freq_pf105)}`",
        f"- Edge-improved configs (PF `>=1.15`, positive R delta, >=300 trades): `{len(edge_improved)}`",
        f"- Positive configs with `>=80%` day coverage: `{len(high_coverage_positive)}`",
        "- Treat this as a context-screening pass only. Any survivor still needs 1m/1s path validation, train/validation split, and prop-firm risk scoring.",
        "",
        "## Artifacts",
        "",
        f"- Ranked context candidates: `backtesting/data/results/{RUN_SLUG}/ranked_context_candidates.csv`",
        f"- Best context trades: `backtesting/data/results/{RUN_SLUG}/best_context_trades.csv`",
        f"- Baseline audit: `backtesting/data/results/{RUN_SLUG}/baseline_audit.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {ranked_path}")
    print(f"Wrote {best_trades_path}")
    print(f"Wrote {audit_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")
    print(f"Elapsed {summary['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
