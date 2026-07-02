#!/usr/bin/env python3
"""Validate the current best NQ NY VWAP mean-reversion research candidate.

Runs the five follow-up checks requested after the context-filter pass:
validation, sensitivity, lower-timeframe path replay, exit/stop refinement,
and prop-firm lifecycle simulation.
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
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / ".agents" / "skills" / "prop-firm-risk-analysis" / "scripts"))

import run_nq_ny_level_reversion_context_filter_recent5_20260629 as ctx  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402
from prop_firm_risk import (  # noqa: E402
    PropFirmRiskProfile,
    make_account_starts,
    max_consecutive_outcomes,
    profile_to_dict,
    score_prop_firm_outcomes,
    simulate_prop_firm_risk,
)


RUN_SLUG = "nq_ny_vwap_mean_reversion_validation_20260630"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_MEAN_REVERSION_VALIDATION_20260630.md"

RECENT_START = "2021-06-05"
RECENT_END_EXCLUSIVE = "2026-06-06"
COLD_START = "2016-01-01"
COLD_END_EXCLUSIVE = "2021-06-05"

ENTRY_START = "09:45"
ENTRY_END = "15:00"
FLAT_TIME = "15:55"

BEST_SLOPE_THRESHOLD = 0.02
BEST_CONTEXT = {
    "slope_threshold": BEST_SLOPE_THRESHOLD,
    "efficiency_max": 0.65,
    "session_range_atr_max": 2.0,
    "time_bucket": "10:00-14:00",
}

TIME_BUCKETS = {
    "full": (ENTRY_START, ENTRY_END),
    "10:00-12:00": ("10:00", "12:00"),
    "10:00-13:00": ("10:00", "13:00"),
    "10:00-14:00": ("10:00", "14:00"),
    "10:00-15:00": ("10:00", "15:00"),
    "11:00-15:00": ("11:00", "15:00"),
}


@dataclass(frozen=True)
class ExitModel:
    name: str
    stop_model: str
    target_model: str


BASE_CONFIG = ctx.StateMachineConfig(
    label="best_vwap_mr",
    mean_mode="vwap",
    extension_atr_pct=0.025,
    consolidation_bars=6,
    consolidation_atr_pct=0.20,
    setup_timeout_bars=12,
    stop_buffer_atr_pct=0.02,
    min_rr_to_mean=0.20,
    cooldown_bars=2,
    max_trades_per_day=3,
)

ORIGINAL_EXIT_MODEL = ExitModel(
    name="signal_1x_to_vwap",
    stop_model="signal_1x",
    target_model="vwap",
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
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _max_drawdown(values: list[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    if len(arr) == 0:
        return 0.0
    equity = np.cumsum(arr)
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _profit_factor(values: list[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    wins = arr[arr > 0]
    losses = arr[arr < 0]
    if len(losses) == 0:
        return 999.0 if len(wins) else 0.0
    return float(wins.sum() / abs(losses.sum()))


def _score_trades(
    trades: list[dict[str, Any]] | pd.DataFrame,
    *,
    label: str,
    trading_days: int | None = None,
) -> dict[str, Any]:
    df = pd.DataFrame(trades)
    if df.empty:
        return {
            "label": label,
            "trades": 0,
            "trading_days": trading_days or 0,
            "avg_trades_per_day": 0.0,
            "days_with_trade": 0,
            "pct_days_with_trade": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "profit_factor": 0.0,
            "win_rate": 0.0,
            "max_drawdown_r": 0.0,
        }
    rs = df["r_multiple"].astype(float).to_numpy()
    day_counts = df["date"].astype(str).value_counts()
    total_days = int(trading_days or day_counts.size)
    days_with_trade = int(day_counts.size)
    return {
        "label": label,
        "trades": int(len(df)),
        "trading_days": total_days,
        "avg_trades_per_day": round(float(len(df) / total_days), 4) if total_days else 0.0,
        "days_with_trade": days_with_trade,
        "pct_days_with_trade": round(float(days_with_trade / total_days), 4) if total_days else 0.0,
        "total_r": round(float(rs.sum()), 4),
        "avg_r": round(float(rs.mean()), 4),
        "profit_factor": round(_profit_factor(rs), 4),
        "win_rate": round(float((rs > 0).mean()), 4),
        "max_drawdown_r": round(_max_drawdown(rs), 4),
    }


def _date_mask(df: pd.DataFrame, start: str, end_exclusive: str) -> pd.Series:
    dates = pd.to_datetime(df["date"].astype(str))
    return (dates >= pd.Timestamp(start)) & (dates < pd.Timestamp(end_exclusive))


def _month_add(ts: pd.Timestamp, months: int) -> pd.Timestamp:
    return ts + pd.DateOffset(months=months)


def _time_accepts(signal_time: str, bucket: str) -> bool:
    start, end = TIME_BUCKETS[bucket]
    return start <= signal_time <= end


def _slope_rejects(candidate: dict[str, Any], threshold: float) -> bool:
    direction = int(candidate["direction_int"])
    close = float(candidate["signal_close"])
    vwap = float(candidate["signal_vwap"])
    slope = float(candidate["vwap_slope_atr"])
    if direction == 1:
        return close < vwap and slope <= -threshold
    return close > vwap and slope >= threshold


def _filter_accepts(
    candidate: dict[str, Any],
    *,
    slope_threshold: float,
    efficiency_max: float | None,
    session_range_atr_max: float | None,
    time_bucket: str,
) -> bool:
    if not _time_accepts(str(candidate["signal_time"]), time_bucket):
        return False
    if _slope_rejects(candidate, slope_threshold):
        return False
    if efficiency_max is not None and float(candidate["directional_efficiency"]) > efficiency_max:
        return False
    if session_range_atr_max is not None and float(candidate["session_range_atr"]) > session_range_atr_max:
        return False
    return True


def _build_orders(
    day: ctx.PreparedDay,
    candidate: dict[str, Any],
    model: ExitModel,
) -> tuple[float, float, float, float] | None:
    direction = int(candidate["direction_int"])
    signal_idx = int(candidate["signal_idx"])
    entry_idx = int(candidate["entry_idx"])
    entry = float(day.opens[entry_idx])
    buffer = BASE_CONFIG.stop_buffer_atr_pct * day.atr
    cons_slice = slice(signal_idx - BASE_CONFIG.consolidation_bars, signal_idx)
    cons_high = float(np.max(day.highs[cons_slice]))
    cons_low = float(np.min(day.lows[cons_slice]))

    if direction == 1:
        signal_stop_base = float(day.lows[signal_idx])
        cons_stop_base = cons_low
        vwap_target = float(day.vwap[signal_idx])
        day_mid_target = float(day.day_mid[signal_idx])
    else:
        signal_stop_base = float(day.highs[signal_idx])
        cons_stop_base = cons_high
        vwap_target = float(day.vwap[signal_idx])
        day_mid_target = float(day.day_mid[signal_idx])

    if model.stop_model == "signal_0x":
        stop = signal_stop_base
    elif model.stop_model == "signal_0.5x":
        stop = signal_stop_base - direction * buffer * 0.5
    elif model.stop_model == "signal_1x":
        stop = signal_stop_base - direction * buffer
    elif model.stop_model == "signal_1.5x":
        stop = signal_stop_base - direction * buffer * 1.5
    elif model.stop_model == "cons_edge_1x":
        stop = cons_stop_base - direction * buffer
    else:
        raise ValueError(f"Unknown stop model: {model.stop_model}")

    risk = (entry - stop) * direction
    if risk <= 0:
        return None

    reward_to_vwap = (vwap_target - entry) * direction
    if model.target_model == "vwap":
        target = vwap_target
    elif model.target_model == "partial_75_to_vwap":
        target = entry + direction * reward_to_vwap * 0.75
    elif model.target_model == "day_mid":
        target = day_mid_target
    elif model.target_model == "fixed_1r":
        target = entry + direction * risk
    elif model.target_model == "fixed_1.5r":
        target = entry + direction * risk * 1.5
    else:
        raise ValueError(f"Unknown target model: {model.target_model}")

    reward = (target - entry) * direction
    if reward <= 0 or reward / risk < BASE_CONFIG.min_rr_to_mean:
        return None
    return entry, stop, target, risk


def _simulate_exit_5m(
    day: ctx.PreparedDay,
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
    r_multiple = ((exit_price - entry) * direction) / risk if risk > 0 else 0.0
    return exit_idx, exit_price, exit_type, r_multiple


def _simulate_candidate_set(
    days: list[ctx.PreparedDay],
    candidates_by_day: list[list[dict[str, Any]]],
    *,
    slope_threshold: float,
    efficiency_max: float | None,
    session_range_atr_max: float | None,
    time_bucket: str,
    exit_model: ExitModel = ORIGINAL_EXIT_MODEL,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for day, day_candidates in zip(days, candidates_by_day, strict=True):
        current_min_idx = 0
        day_trade_count = 0
        for candidate in day_candidates:
            if day_trade_count >= BASE_CONFIG.max_trades_per_day:
                break
            if (
                int(candidate["extension_idx"]) < current_min_idx
                or int(candidate["signal_idx"]) < current_min_idx
                or int(candidate["entry_idx"]) < current_min_idx
            ):
                continue
            if not _filter_accepts(
                candidate,
                slope_threshold=slope_threshold,
                efficiency_max=efficiency_max,
                session_range_atr_max=session_range_atr_max,
                time_bucket=time_bucket,
            ):
                continue
            order = _build_orders(day, candidate, exit_model)
            if order is None:
                continue
            entry, stop, target, risk = order
            direction = int(candidate["direction_int"])
            exit_idx, exit_price, exit_type, r_multiple = _simulate_exit_5m(
                day,
                direction=direction,
                entry_idx=int(candidate["entry_idx"]),
                entry=entry,
                stop=stop,
                target=target,
                risk=risk,
            )
            reward = abs(target - entry)
            trade = {
                "date": day.date,
                "direction": "long" if direction == 1 else "short",
                "direction_int": direction,
                "signal_ts": candidate["signal_ts"],
                "signal_time": candidate["signal_time"],
                "entry_ts": day.timestamps[int(candidate["entry_idx"])].isoformat(),
                "exit_ts": day.timestamps[exit_idx].isoformat(),
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "exit_price": round(exit_price, 2),
                "exit_type": exit_type,
                "risk_points": round(risk, 4),
                "reward_points": round(reward, 4),
                "rr_to_target": round(reward / risk, 4),
                "r_multiple": round(r_multiple, 4),
                "atr14_prev": candidate["atr14_prev"],
                "setup_wait_bars": candidate["setup_wait_bars"],
                "vwap_slope_atr": candidate["vwap_slope_atr"],
                "directional_efficiency": candidate["directional_efficiency"],
                "session_range_atr": candidate["session_range_atr"],
                "exit_model": exit_model.name,
                "slope_threshold": slope_threshold,
                "efficiency_max": efficiency_max,
                "session_range_atr_max": session_range_atr_max,
                "time_bucket": time_bucket,
                "deployability": "research_only",
                "live_support_notes": "VWAP mean-reversion context-filter prototype is not implemented in live execution.",
                "exact_replay_required": "yes",
            }
            trades.append(trade)
            day_trade_count += 1
            current_min_idx = exit_idx + BASE_CONFIG.cooldown_bars
    return trades


def _prepare_days(start: str, end_exclusive: str) -> list[ctx.PreparedDay]:
    df = load_5m_data(NQ.data_file, start=start, end=end_exclusive)
    return ctx._prepare_days(ctx._prepare_rth(df))


def _make_candidates(days: list[ctx.PreparedDay]) -> list[list[dict[str, Any]]]:
    return [ctx._generate_candidates_for_day(day, BASE_CONFIG) for day in days]


def _period_scores(days: list[ctx.PreparedDay], trades: list[dict[str, Any]]) -> pd.DataFrame:
    trade_df = pd.DataFrame(trades)
    rows: list[dict[str, Any]] = []
    periods = [
        ("recent_full", "2021-06-07", "2026-06-06"),
        ("retrospective_dev_2021_2023", "2021-06-07", "2024-01-01"),
        ("retrospective_validation_2024_2026", "2024-01-01", "2026-06-06"),
    ]
    if not trade_df.empty:
        for year in sorted(trade_df["date"].str.slice(0, 4).unique()):
            periods.append((f"year_{year}", f"{year}-01-01", f"{int(year)+1}-01-01"))

    day_df = pd.DataFrame({"date": [day.date for day in days]})
    for label, start, end in periods:
        day_count = int(((pd.to_datetime(day_df["date"]) >= pd.Timestamp(start)) & (pd.to_datetime(day_df["date"]) < pd.Timestamp(end))).sum())
        subset = trade_df[_date_mask(trade_df, start, end)] if not trade_df.empty else trade_df
        rows.append(_score_trades(subset, label=label, trading_days=day_count))

    rolling_start = pd.Timestamp("2021-07-01")
    rolling_end = pd.Timestamp("2026-07-01")
    cursor = rolling_start
    while _month_add(cursor, 6) <= rolling_end:
        end = _month_add(cursor, 6)
        label = f"rolling_6m_{cursor.date()}_{(end - pd.Timedelta(days=1)).date()}"
        day_count = int(((pd.to_datetime(day_df["date"]) >= cursor) & (pd.to_datetime(day_df["date"]) < end)).sum())
        subset = trade_df[_date_mask(trade_df, cursor.isoformat(), end.isoformat())] if not trade_df.empty else trade_df
        rows.append(_score_trades(subset, label=label, trading_days=day_count))
        cursor = _month_add(cursor, 6)
    return pd.DataFrame(rows)


def _sensitivity_grid(days: list[ctx.PreparedDay], candidates_by_day: list[list[dict[str, Any]]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for slope_threshold in (0.01, 0.015, 0.02, 0.025, 0.03):
        for efficiency_max in (0.55, 0.60, 0.65, 0.70, None):
            for session_range_atr_max in (1.50, 1.75, 2.00, 2.25, None):
                for time_bucket in ("10:00-12:00", "10:00-13:00", "10:00-14:00", "10:00-15:00", "11:00-15:00", "full"):
                    trades = _simulate_candidate_set(
                        days,
                        candidates_by_day,
                        slope_threshold=slope_threshold,
                        efficiency_max=efficiency_max,
                        session_range_atr_max=session_range_atr_max,
                        time_bucket=time_bucket,
                    )
                    row = _score_trades(trades, label="sensitivity", trading_days=len(days))
                    row.update(
                        {
                            "slope_threshold": slope_threshold,
                            "efficiency_max": efficiency_max,
                            "session_range_atr_max": session_range_atr_max,
                            "time_bucket": time_bucket,
                            "deployability": "research_only",
                            "live_support_notes": "Sensitivity row for simulator-only VWAP mean-reversion context filter.",
                            "exact_replay_required": "yes",
                        }
                    )
                    rows.append(row)
    ranked = pd.DataFrame(rows).sort_values(
        ["total_r", "profit_factor", "max_drawdown_r"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    return ranked


def _exit_model_grid() -> list[ExitModel]:
    models: list[ExitModel] = []
    for stop_model in ("signal_0x", "signal_0.5x", "signal_1x", "signal_1.5x", "cons_edge_1x"):
        for target_model in ("partial_75_to_vwap", "vwap", "day_mid", "fixed_1r", "fixed_1.5r"):
            models.append(ExitModel(f"{stop_model}_to_{target_model}", stop_model, target_model))
    return models


def _exit_refinement(days: list[ctx.PreparedDay], candidates_by_day: list[list[dict[str, Any]]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for model in _exit_model_grid():
        trades = _simulate_candidate_set(
            days,
            candidates_by_day,
            slope_threshold=BEST_CONTEXT["slope_threshold"],
            efficiency_max=BEST_CONTEXT["efficiency_max"],
            session_range_atr_max=BEST_CONTEXT["session_range_atr_max"],
            time_bucket=BEST_CONTEXT["time_bucket"],
            exit_model=model,
        )
        row = _score_trades(trades, label=model.name, trading_days=len(days))
        row.update(
            {
                "exit_model": model.name,
                "stop_model": model.stop_model,
                "target_model": model.target_model,
                "deployability": "research_only",
                "live_support_notes": "Exit/stop refinement for simulator-only VWAP mean-reversion context filter.",
                "exact_replay_required": "yes",
            }
        )
        rows.append(row)
    ranked = pd.DataFrame(rows).sort_values(
        ["total_r", "profit_factor", "max_drawdown_r"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    return ranked


def _read_lower_tf(path: Path, start: str, end_exclusive: str) -> pd.DataFrame | None:
    if not path.exists():
        return None
    return pd.read_parquet(
        path,
        columns=["open", "high", "low", "close", "volume"],
        filters=[
            ("datetime", ">=", pd.Timestamp(start)),
            ("datetime", "<", pd.Timestamp(end_exclusive)),
        ],
    ).sort_index()


def _replay_trade_lower(row: dict[str, Any], lower: pd.DataFrame, label: str) -> dict[str, Any]:
    entry_ts = pd.Timestamp(row["entry_ts"])
    date = str(row["date"])
    flat_ts = pd.Timestamp(f"{date} {FLAT_TIME}:00")
    window = lower.loc[entry_ts:flat_ts]
    direction = int(row["direction_int"])
    entry = float(row["entry"])
    stop = float(row["stop"])
    target = float(row["target"])
    risk = float(row["risk_points"])
    if window.empty:
        return {
            **row,
            "path_label": label,
            "path_missing": True,
            "path_exit_ts": row["exit_ts"],
            "path_exit_price": row["exit_price"],
            "path_exit_type": row["exit_type"],
            "path_r_multiple": row["r_multiple"],
        }

    exit_ts = window.index[-1]
    exit_price = float(window["close"].iloc[-1])
    exit_type = "eod"
    for ts, bar in window.iterrows():
        if direction == 1:
            stop_hit = float(bar.low) <= stop
            target_hit = float(bar.high) >= target
        else:
            stop_hit = float(bar.high) >= stop
            target_hit = float(bar.low) <= target
        if stop_hit:
            exit_ts = ts
            exit_price = stop
            exit_type = "stop"
            break
        if target_hit:
            exit_ts = ts
            exit_price = target
            exit_type = "target"
            break
    r_multiple = ((exit_price - entry) * direction) / risk if risk > 0 else 0.0
    return {
        **row,
        "path_label": label,
        "path_missing": False,
        "path_exit_ts": pd.Timestamp(exit_ts).isoformat(),
        "path_exit_price": round(exit_price, 2),
        "path_exit_type": exit_type,
        "path_r_multiple": round(float(r_multiple), 4),
        "path_r_delta": round(float(r_multiple - float(row["r_multiple"])), 4),
        "path_exit_type_changed": exit_type != row["exit_type"],
    }


def _path_replay(trades: list[dict[str, Any]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    summary_rows: list[dict[str, Any]] = []
    paths = {
        "1m": ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_1m.parquet",
        "1s": ROOT / "data" / "raw" / "NQ_1s.parquet",
    }
    for label, path in paths.items():
        lower = _read_lower_tf(path, RECENT_START, RECENT_END_EXCLUSIVE)
        if lower is None:
            summary_rows.append({"path_label": label, "available": False})
            continue
        replayed = [_replay_trade_lower(row, lower, label) for row in trades]
        replay_df = pd.DataFrame(replayed)
        replay_df["r_multiple"] = replay_df["path_r_multiple"].astype(float)
        score = _score_trades(replay_df, label=label, trading_days=1293)
        score.update(
            {
                "path_label": label,
                "available": True,
                "missing_trades": int(replay_df["path_missing"].sum()),
                "exit_type_changes": int(replay_df.get("path_exit_type_changed", pd.Series(dtype=bool)).fillna(False).sum()),
                "total_r_delta_vs_5m": round(float(replay_df["path_r_delta"].fillna(0).sum()), 4),
            }
        )
        summary_rows.append(score)
        frames.append(replay_df)
    all_replays = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    return all_replays, pd.DataFrame(summary_rows)


def _exit_model_from_name(name: str) -> ExitModel:
    for model in _exit_model_grid():
        if model.name == name:
            return model
    raise ValueError(f"Unknown exit model: {name}")


def _monte_carlo(trades: pd.DataFrame, *, iterations: int = 2000, seed: int = 7) -> dict[str, Any]:
    if trades.empty:
        return {}
    rng = np.random.default_rng(seed)
    rs = trades["r_multiple"].astype(float).to_numpy()
    totals = np.zeros(iterations)
    dds = np.zeros(iterations)
    for idx in range(iterations):
        sample = rng.choice(rs, size=len(rs), replace=True)
        totals[idx] = sample.sum()
        dds[idx] = _max_drawdown(sample)
    return {
        "iterations": iterations,
        "sample_trades": int(len(rs)),
        "total_r_p05": round(float(np.quantile(totals, 0.05)), 2),
        "total_r_median": round(float(np.quantile(totals, 0.50)), 2),
        "total_r_p95": round(float(np.quantile(totals, 0.95)), 2),
        "max_dd_r_p05": round(float(np.quantile(dds, 0.05)), 2),
        "max_dd_r_median": round(float(np.quantile(dds, 0.50)), 2),
        "max_dd_r_p95": round(float(np.quantile(dds, 0.95)), 2),
        "prob_total_r_positive": round(float((totals > 0).mean()), 4),
        "prob_dd_worse_than_20r": round(float((dds <= -20.0).mean()), 4),
    }


def _prop_risk(path_trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    profile = PropFirmRiskProfile(
        trailing_drawdown_usd=2000.0,
        pass_target_usd=3000.0,
        first_payout_usd=1500.0,
        floor_cap_delta_usd=0.0,
        challenge_fee_usd=0.0,
        account_start_spacing_days=14,
    )
    starts = make_account_starts("2021-06-07", RECENT_END_EXCLUSIVE, profile.account_start_spacing_days)
    rows: list[dict[str, Any]] = []
    best_outcomes = pd.DataFrame()
    best_ev = -1e18
    base = path_trades.copy()
    for risk_usd in (50, 75, 100, 125, 150, 175, 200, 250, 300, 400):
        prop_trades = base.assign(
            pnl_usd=base["r_multiple"].astype(float) * float(risk_usd),
            exit_ts=base["path_exit_ts"],
        ).to_dict(orient="records")
        outcomes = simulate_prop_firm_risk(
            variant_id=f"best_vwap_mr_risk{risk_usd}",
            trades=prop_trades,
            account_starts=starts,
            profile=profile,
            end_exclusive=RECENT_END_EXCLUSIVE,
        )
        score = score_prop_firm_outcomes(outcomes)
        row = {
            "risk_usd_per_r": risk_usd,
            **score,
            "max_consecutive_pre_payout_busts": max_consecutive_outcomes(outcomes, "bust_pre_payout"),
            "max_consecutive_post_payout_busts": max_consecutive_outcomes(outcomes, "bust_post_payout"),
            "deployability": "research_only",
            "live_support_notes": "Prop lifecycle uses research-only VWAP mean-reversion trade stream.",
            "exact_replay_required": "yes",
        }
        rows.append(row)
        if float(score["ev_per_start_usd"]) > best_ev:
            best_ev = float(score["ev_per_start_usd"])
            best_outcomes = outcomes.assign(risk_usd_per_r=risk_usd)
    ranked = pd.DataFrame(rows).sort_values(
        ["ev_per_start_usd", "first_payout_rate", "pre_payout_bust_rate"],
        ascending=[False, False, True],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    ranked.attrs["profile"] = profile_to_dict(profile)
    return ranked, best_outcomes


def _to_markdown(df: pd.DataFrame, cols: list[str], n: int = 20) -> str:
    if df.empty:
        return "_None._"
    return df.head(n)[cols].to_markdown(index=False)


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("Preparing recent 5m days and candidates...")
    recent_days = _prepare_days(RECENT_START, RECENT_END_EXCLUSIVE)
    recent_candidates = _make_candidates(recent_days)
    best_5m_trades = _simulate_candidate_set(recent_days, recent_candidates, **BEST_CONTEXT)
    print(f"Recent best candidate trades: {len(best_5m_trades)}")

    print("Running validation splits...")
    validation = _period_scores(recent_days, best_5m_trades)

    print("Running cold older-window stress...")
    cold_days = _prepare_days(COLD_START, COLD_END_EXCLUSIVE)
    cold_candidates = _make_candidates(cold_days)
    cold_trades = _simulate_candidate_set(cold_days, cold_candidates, **BEST_CONTEXT)
    cold_score = pd.DataFrame([_score_trades(cold_trades, label="cold_2016_to_2021_06", trading_days=len(cold_days))])

    print("Running sensitivity grid...")
    sensitivity = _sensitivity_grid(recent_days, recent_candidates)

    print("Running exit/stop refinement...")
    exit_refinement = _exit_refinement(recent_days, recent_candidates)
    best_exit_model = _exit_model_from_name(str(exit_refinement.iloc[0]["exit_model"]))
    best_exit_5m_trades = _simulate_candidate_set(
        recent_days,
        recent_candidates,
        slope_threshold=BEST_CONTEXT["slope_threshold"],
        efficiency_max=BEST_CONTEXT["efficiency_max"],
        session_range_atr_max=BEST_CONTEXT["session_range_atr_max"],
        time_bucket=BEST_CONTEXT["time_bucket"],
        exit_model=best_exit_model,
    )

    print("Running 1m/1s path replay...")
    path_replays, path_summary = _path_replay(best_5m_trades)
    exit_path_replays, exit_path_summary = _path_replay(best_exit_5m_trades)
    path_1s = path_replays[path_replays["path_label"] == "1s"].copy() if not path_replays.empty else pd.DataFrame()
    path_1s_prop = path_1s.copy()
    if not path_1s_prop.empty:
        path_1s_prop["r_multiple"] = path_1s_prop["path_r_multiple"].astype(float)
    exit_path_1s = exit_path_replays[exit_path_replays["path_label"] == "1s"].copy() if not exit_path_replays.empty else pd.DataFrame()
    exit_path_1s_prop = exit_path_1s.copy()
    if not exit_path_1s_prop.empty:
        exit_path_1s_prop["r_multiple"] = exit_path_1s_prop["path_r_multiple"].astype(float)

    print("Running Monte Carlo bootstrap...")
    mc_summary = _monte_carlo(path_1s_prop if not path_1s_prop.empty else pd.DataFrame(best_5m_trades))
    exit_mc_summary = _monte_carlo(exit_path_1s_prop if not exit_path_1s_prop.empty else pd.DataFrame(best_exit_5m_trades))

    print("Running prop-firm lifecycle grid...")
    prop_grid, best_prop_outcomes = _prop_risk(path_1s_prop if not path_1s_prop.empty else pd.DataFrame(best_5m_trades))
    exit_prop_grid, exit_best_prop_outcomes = _prop_risk(
        exit_path_1s_prop if not exit_path_1s_prop.empty else pd.DataFrame(best_exit_5m_trades)
    )

    paths = {
        "best_5m_trades": RESULT_DIR / "best_candidate_5m_trades.csv",
        "best_exit_5m_trades": RESULT_DIR / "best_exit_refined_5m_trades.csv",
        "validation": RESULT_DIR / "validation_windows.csv",
        "cold_score": RESULT_DIR / "cold_window_score.csv",
        "cold_trades": RESULT_DIR / "cold_window_trades.csv",
        "sensitivity": RESULT_DIR / "sensitivity_grid.csv",
        "exit_refinement": RESULT_DIR / "exit_stop_refinement.csv",
        "path_replays": RESULT_DIR / "path_replay_trades.csv",
        "path_summary": RESULT_DIR / "path_replay_summary.csv",
        "exit_path_replays": RESULT_DIR / "exit_refined_path_replay_trades.csv",
        "exit_path_summary": RESULT_DIR / "exit_refined_path_replay_summary.csv",
        "prop_grid": RESULT_DIR / "prop_risk_grid.csv",
        "best_prop_outcomes": RESULT_DIR / "best_prop_account_paths.csv",
        "exit_prop_grid": RESULT_DIR / "exit_refined_prop_risk_grid.csv",
        "exit_best_prop_outcomes": RESULT_DIR / "exit_refined_best_prop_account_paths.csv",
        "summary": RESULT_DIR / "summary.json",
    }
    pd.DataFrame(best_5m_trades).to_csv(paths["best_5m_trades"], index=False)
    pd.DataFrame(best_exit_5m_trades).to_csv(paths["best_exit_5m_trades"], index=False)
    validation.to_csv(paths["validation"], index=False)
    cold_score.to_csv(paths["cold_score"], index=False)
    pd.DataFrame(cold_trades).to_csv(paths["cold_trades"], index=False)
    sensitivity.to_csv(paths["sensitivity"], index=False)
    exit_refinement.to_csv(paths["exit_refinement"], index=False)
    path_replays.to_csv(paths["path_replays"], index=False)
    path_summary.to_csv(paths["path_summary"], index=False)
    exit_path_replays.to_csv(paths["exit_path_replays"], index=False)
    exit_path_summary.to_csv(paths["exit_path_summary"], index=False)
    prop_grid.to_csv(paths["prop_grid"], index=False)
    best_prop_outcomes.to_csv(paths["best_prop_outcomes"], index=False)
    exit_prop_grid.to_csv(paths["exit_prop_grid"], index=False)
    exit_best_prop_outcomes.to_csv(paths["exit_best_prop_outcomes"], index=False)

    best_5m_score = _score_trades(best_5m_trades, label="best_5m", trading_days=len(recent_days))
    best_1s_score = (
        path_summary[path_summary["path_label"] == "1s"].iloc[0].to_dict()
        if not path_summary.empty and "1s" in set(path_summary["path_label"].astype(str))
        else {}
    )
    best_exit_5m_score = _score_trades(best_exit_5m_trades, label=best_exit_model.name, trading_days=len(recent_days))
    best_exit_1s_score = (
        exit_path_summary[exit_path_summary["path_label"] == "1s"].iloc[0].to_dict()
        if not exit_path_summary.empty and "1s" in set(exit_path_summary["path_label"].astype(str))
        else {}
    )
    best_sensitivity = sensitivity.iloc[0].to_dict() if not sensitivity.empty else {}
    best_exit = exit_refinement.iloc[0].to_dict() if not exit_refinement.empty else {}
    best_prop = prop_grid.iloc[0].to_dict() if not prop_grid.empty else {}
    best_exit_prop = exit_prop_grid.iloc[0].to_dict() if not exit_prop_grid.empty else {}
    summary = {
        "run_slug": RUN_SLUG,
        "phase": "best_vwap_mean_reversion_validation",
        "candidate": {
            "base_variant_id": "vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2",
            "context": BEST_CONTEXT,
            "deployability": "research_only",
            "live_support_notes": "Strategy exists only as research script; live execution and exact replay parity are not implemented.",
            "exact_replay_required": "yes",
        },
        "recent_5m_score": best_5m_score,
        "cold_window_score": cold_score.iloc[0].to_dict(),
        "path_1s_score": best_1s_score,
        "best_sensitivity": best_sensitivity,
        "best_exit_refinement": best_exit,
        "best_exit_refined_5m_score": best_exit_5m_score,
        "best_exit_refined_1s_score": best_exit_1s_score,
        "monte_carlo": mc_summary,
        "exit_refined_monte_carlo": exit_mc_summary,
        "best_prop": best_prop,
        "best_exit_refined_prop": best_exit_prop,
        "prop_profile": prop_grid.attrs.get("profile", {}),
        "elapsed_seconds": round(time.time() - started, 2),
    }
    paths["summary"].write_text(json.dumps(_safe(summary), indent=2) + "\n")

    validation_cols = ["label", "trades", "trading_days", "avg_trades_per_day", "total_r", "avg_r", "profit_factor", "win_rate", "max_drawdown_r"]
    sensitivity_cols = ["rank", "slope_threshold", "efficiency_max", "session_range_atr_max", "time_bucket", "trades", "avg_trades_per_day", "total_r", "avg_r", "profit_factor", "max_drawdown_r"]
    path_cols = ["path_label", "available", "trades", "total_r", "avg_r", "profit_factor", "win_rate", "max_drawdown_r", "exit_type_changes", "total_r_delta_vs_5m"]
    exit_cols = ["rank", "exit_model", "trades", "avg_trades_per_day", "total_r", "avg_r", "profit_factor", "win_rate", "max_drawdown_r"]
    prop_cols = ["rank", "risk_usd_per_r", "total_starts", "first_payout_rate", "pre_payout_bust_rate", "post_payout_bust_rate", "open_rate", "ev_per_start_usd", "marked_ev_per_start_usd", "avg_days_to_first_payout", "worst_min_cushion_usd"]

    report_lines = [
        "# NQ NY VWAP Mean-Reversion Validation Packet",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Candidate: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` + `reject_vwap_side_slope` + `efficiency_max=0.65` + `session_range_atr_max=2.0` + `10:00-14:00`",
        f"- Recent validation window: `{RECENT_START}` to `<{RECENT_END_EXCLUSIVE}`",
        f"- Cold older stress window: `{COLD_START}` to `<{COLD_END_EXCLUSIVE}`",
        "- Deployability: `research_only`; exact replay and live execution support are still required before any deployment discussion.",
        "",
        "## Step 0: Current Candidate Replay",
        "",
        pd.DataFrame([best_5m_score]).to_markdown(index=False),
        "",
        "## Step 1: Validation",
        "",
        "### Recent split and annual/rolling windows",
        "",
        _to_markdown(validation, validation_cols, n=30),
        "",
        "### Cold older-window stress",
        "",
        cold_score[validation_cols].to_markdown(index=False),
        "",
        "## Step 2: Sensitivity",
        "",
        _to_markdown(sensitivity, sensitivity_cols, n=20),
        "",
        "## Step 3: 1m/1s Path Replay",
        "",
        "### Original VWAP-target candidate",
        "",
        path_summary[path_cols].to_markdown(index=False) if not path_summary.empty else "_No lower-timeframe data available._",
        "",
        "### Exit-refined candidate",
        "",
        exit_path_summary[path_cols].to_markdown(index=False) if not exit_path_summary.empty else "_No lower-timeframe data available._",
        "",
        "## Step 4: Exit/Stop Refinement",
        "",
        _to_markdown(exit_refinement, exit_cols, n=20),
        "",
        "## Step 5: Prop-Firm Lifecycle",
        "",
        "- Account model: `$2,000` EOD trailing drawdown capped at starting balance, `$3,000` pass target, `$1,500` first payout, `$0` fee, account starts every `14` days.",
        "- Prop scores use the `1s` path replay trade stream when available.",
        "",
        _to_markdown(prop_grid, prop_cols, n=20),
        "",
        "### Exit-refined prop lifecycle",
        "",
        _to_markdown(exit_prop_grid, prop_cols, n=20),
        "",
        "## Monte Carlo Bootstrap",
        "",
        "### Original VWAP-target candidate",
        "",
        pd.DataFrame([mc_summary]).to_markdown(index=False) if mc_summary else "_None._",
        "",
        "### Exit-refined candidate",
        "",
        pd.DataFrame([exit_mc_summary]).to_markdown(index=False) if exit_mc_summary else "_None._",
        "",
        "## Summary Read",
        "",
        "- This packet validates the current best VWAP mean-reversion row as a selective research sleeve, not as a daily-trade strategy.",
        "- The key promotion questions are whether the edge survives the older cold window, whether 1s path replay materially degrades the 5m result, and whether any prop sizing has positive realized first-payout EV without excessive bust clustering.",
        "- Any positive result remains `research_only` until the strategy is implemented as a live-native pre-trade gate and exact replay parity exists.",
        "",
        "## Artifacts",
        "",
    ]
    for name, path in paths.items():
        if name != "summary":
            report_lines.append(f"- {name}: `{path.relative_to(ROOT)}`")
    report_lines.append(f"- summary: `{paths['summary'].relative_to(ROOT)}`")
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {RESULT_DIR}")
    print(f"Elapsed {summary['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
