#!/usr/bin/env python3
"""Native 1m/2m/3m/5m static 1:1.5R sweep for NQ NY VWAP cadence setup."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_DIR = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT / "src"))

RUN_SLUG = "nq_ny_vwap_static_rr_timeframe_sweep_20260630"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_STATIC_RR_TIMEFRAME_SWEEP_20260630.md"

DATA_START = "2021-06-05"
DATA_END_EXCLUSIVE = "2026-06-06"
RR = 1.5
NQ_TICK = 0.25
MIN_STOP_TICKS = 4
TIMEFRAMES = (1, 2, 3, 5)


def _load_context_module() -> Any:
    path = SCRIPT_DIR / "run_nq_ny_level_reversion_context_filter_recent5_20260629.py"
    spec = importlib.util.spec_from_file_location("nq_level_context_20260629_tf", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load context-filter module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ctx = _load_context_module()


@dataclass(frozen=True)
class StaticStopConfig:
    stop_basis: str
    stop_pct: float
    rr: float = RR

    @property
    def label(self) -> str:
        pct = f"{self.stop_pct * 100:g}".replace(".", "p")
        return f"{self.stop_basis}_pct{pct}_rr{self.rr:g}"


@dataclass(frozen=True)
class TimeframeConfig:
    timeframe_min: int
    setup: Any
    context: Any

    @property
    def label(self) -> str:
        return f"{self.timeframe_min}m"


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
    df = df[(df.index >= DATA_START) & (df.index < DATA_END_EXCLUSIVE)].copy()
    return df


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


def _timeframe_config(timeframe_min: int) -> TimeframeConfig:
    # Preserve the 5m setup's real durations: 30m consolidation, 60m timeout,
    # and about 10m cooldown after exit.
    consolidation_bars = int(round(30 / timeframe_min))
    setup_timeout_bars = int(round(60 / timeframe_min))
    cooldown_bars = int(math.ceil(10 / timeframe_min))
    setup = ctx.StateMachineConfig(
        label=f"vwap_static_rr_{timeframe_min}m_time_normalized",
        mean_mode="vwap",
        extension_atr_pct=0.025,
        consolidation_bars=consolidation_bars,
        consolidation_atr_pct=0.20,
        setup_timeout_bars=setup_timeout_bars,
        stop_buffer_atr_pct=0.02,
        min_rr_to_mean=0.20,
        cooldown_bars=cooldown_bars,
        max_trades_per_day=3,
    )
    context = ctx.ContextConfig(
        structure_gate="none",
        vwap_acceptance="none",
        efficiency_max=None,
        ib_location="none",
        session_range_atr_max=2.0,
        time_bucket="full",
    )
    return TimeframeConfig(timeframe_min=timeframe_min, setup=setup, context=context)


def _make_stop_grid() -> list[StaticStopConfig]:
    configs: list[StaticStopConfig] = []
    for pct in (0.03, 0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25):
        configs.append(StaticStopConfig("atr14_prev", pct))
    for pct in (0.05, 0.075, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00):
        configs.append(StaticStopConfig("prior_session_range", pct))
        configs.append(StaticStopConfig("session_range_so_far", pct))
    return configs


def _ceil_even_stop_ticks(raw_points: float) -> int:
    ticks = max(MIN_STOP_TICKS, int(math.ceil(raw_points / NQ_TICK)))
    if ticks % 2:
        ticks += 1
    return ticks


def _prior_session_ranges(days: list[Any]) -> dict[str, float]:
    ranges: dict[str, float] = {}
    previous: float | None = None
    for day in days:
        ranges[day.date] = previous if previous is not None and previous > 0 else float(day.atr)
        previous = float(day.session_high_so_far[-1] - day.session_low_so_far[-1])
    return ranges


def _stop_base_points(day: Any, candidate: dict[str, Any], stop_config: StaticStopConfig, prior_ranges: dict[str, float]) -> float:
    signal_idx = int(candidate["signal_idx"])
    if stop_config.stop_basis == "atr14_prev":
        return float(day.atr)
    if stop_config.stop_basis == "prior_session_range":
        return float(prior_ranges.get(day.date, day.atr))
    if stop_config.stop_basis == "session_range_so_far":
        return float(max(day.session_high_so_far[signal_idx] - day.session_low_so_far[signal_idx], NQ_TICK))
    raise ValueError(f"Unknown stop_basis: {stop_config.stop_basis}")


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


def _simulate_static_exit(
    day: Any,
    candidate: dict[str, Any],
    stop_config: StaticStopConfig,
    prior_ranges: dict[str, float],
    tf_config: TimeframeConfig,
) -> dict[str, Any]:
    direction = int(candidate["direction_int"])
    entry_idx = int(candidate["entry_idx"])
    entry = float(day.opens[entry_idx])
    stop_base = _stop_base_points(day, candidate, stop_config, prior_ranges)
    raw_stop_points = stop_base * stop_config.stop_pct
    stop_ticks = _ceil_even_stop_ticks(raw_stop_points)
    risk = stop_ticks * NQ_TICK
    reward = risk * stop_config.rr
    if direction == 1:
        stop = entry - risk
        target = entry + reward
    else:
        stop = entry + risk
        target = entry - reward

    exit_idx, exit_price, exit_type, r_multiple = ctx._simulate_exit(
        day,
        direction=direction,
        entry_idx=entry_idx,
        entry=entry,
        stop=stop,
        target=target,
        risk=risk,
    )

    mean_price = float(candidate["target"])
    rr_to_mean_static_stop = ((mean_price - entry) * direction) / risk if risk > 0 else 0.0
    return {
        "date": day.date,
        "timeframe": tf_config.label,
        "timeframe_min": tf_config.timeframe_min,
        "direction": "long" if direction == 1 else "short",
        "direction_int": direction,
        "signal_ts": candidate["signal_ts"],
        "signal_time": candidate["signal_time"],
        "entry_ts": day.timestamps[entry_idx].isoformat(),
        "exit_ts": day.timestamps[exit_idx].isoformat(),
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "mean_price": round(mean_price, 2),
        "exit_price": round(exit_price, 2),
        "exit_type": exit_type,
        "risk_points": round(risk, 2),
        "reward_points": round(reward, 2),
        "rr": stop_config.rr,
        "r_multiple": round(float(r_multiple), 4),
        "stop_basis": stop_config.stop_basis,
        "stop_pct": stop_config.stop_pct,
        "stop_model": stop_config.label,
        "stop_base_points": round(stop_base, 2),
        "raw_stop_points": round(raw_stop_points, 4),
        "stop_ticks": stop_ticks,
        "rr_to_mean_static_stop": round(rr_to_mean_static_stop, 4),
        "fixed_target_reaches_mean": bool(rr_to_mean_static_stop >= stop_config.rr),
        "atr14_prev": candidate["atr14_prev"],
        "session_range_atr": candidate["session_range_atr"],
        "setup_wait_bars": candidate["setup_wait_bars"],
        "consolidation_bars": tf_config.setup.consolidation_bars,
        "setup_timeout_bars": tf_config.setup.setup_timeout_bars,
        "cooldown_bars": tf_config.setup.cooldown_bars,
        "vwap_slope_atr": candidate["vwap_slope_atr"],
        "directional_vwap_distance_atr": candidate["directional_vwap_distance_atr"],
        "directional_efficiency": candidate["directional_efficiency"],
        "structure_30m": candidate["structure_30m"],
        "base_variant_id": (
            f"vwap_ext0.025_cons{tf_config.setup.consolidation_bars}x0.2_"
            f"timeout{tf_config.setup.setup_timeout_bars}_buf0.02_minrr0.2"
        ),
        "context_session_range_atr_max": tf_config.context.session_range_atr_max,
        "deployability": "research_only",
        "live_support_notes": (
            "Native-timeframe static-RR VWAP cadence prototype exists only in this research script; "
            "live execution and exact replay parity are not implemented."
        ),
        "exact_replay_required": "yes",
        "exit_idx": exit_idx,
        "extension_idx": int(candidate["extension_idx"]),
        "signal_idx": int(candidate["signal_idx"]),
        "entry_idx": entry_idx,
    }


def _simulate_model(
    days: list[Any],
    candidates_by_day: list[list[dict[str, Any]]],
    tf_config: TimeframeConfig,
    stop_config: StaticStopConfig,
    prior_ranges: dict[str, float],
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    for day, day_candidates in zip(days, candidates_by_day, strict=True):
        current_min_idx = 0
        day_trade_count = 0
        for candidate in day_candidates:
            if day_trade_count >= tf_config.setup.max_trades_per_day:
                break
            if (
                int(candidate["extension_idx"]) < current_min_idx
                or int(candidate["signal_idx"]) < current_min_idx
                or int(candidate["entry_idx"]) < current_min_idx
            ):
                continue
            if not ctx._context_accepts(candidate, tf_config.context):
                continue
            trade = _simulate_static_exit(day, candidate, stop_config, prior_ranges, tf_config)
            trades.append(trade)
            day_trade_count += 1
            current_min_idx = int(trade["exit_idx"]) + tf_config.setup.cooldown_bars
    return trades


def _yearly_rows(trades: list[dict[str, Any]]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["year", "period", "trades", "win_rate", "total_r", "avg_r", "profit_factor", "max_drawdown_r"])
    frame = pd.DataFrame(trades)
    frame["year"] = frame["date"].str.slice(0, 4)
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


def _score_trades(
    trades: list[dict[str, Any]],
    trading_days: int,
    tf_config: TimeframeConfig,
    stop_config: StaticStopConfig,
    total_candidates: int,
) -> dict[str, Any]:
    values = [float(row["r_multiple"]) for row in trades]
    exits = Counter(row["exit_type"] for row in trades)
    by_day = pd.Series([row["date"] for row in trades]).value_counts() if trades else pd.Series(dtype=int)
    days_with_trade = int((by_day > 0).sum())
    days_1_to_3 = int(((by_day >= 1) & (by_day <= 3)).sum())
    years = trading_days / 252.0 if trading_days else 0.0
    total_r = float(sum(values))
    max_dd = _max_drawdown(values)
    profit_factor = _profit_factor(values)
    yearly = _yearly_rows(trades)
    full_years = yearly[yearly["year"].isin(["2022", "2023", "2024", "2025"])] if not yearly.empty else yearly
    avg_annual_r = total_r / years if years else 0.0
    calmar = avg_annual_r / abs(max_dd) if max_dd < 0 else 0.0
    return {
        "timeframe": tf_config.label,
        "timeframe_min": tf_config.timeframe_min,
        "consolidation_bars": tf_config.setup.consolidation_bars,
        "setup_timeout_bars": tf_config.setup.setup_timeout_bars,
        "cooldown_bars": tf_config.setup.cooldown_bars,
        **asdict(stop_config),
        "stop_model": stop_config.label,
        "total_candidates": total_candidates,
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
        "calmar": round(calmar, 4),
        "profit_factor": round(float(profit_factor), 4),
        "win_rate": round(float(np.mean([value > 0 for value in values])), 4) if values else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "negative_years": int((yearly["total_r"] < 0).sum()) if not yearly.empty else 0,
        "negative_full_years": int((full_years["total_r"] < 0).sum()) if not full_years.empty else 0,
        "target_exits": int(exits.get("target", 0)),
        "stop_exits": int(exits.get("stop", 0)),
        "eod_exits": int(exits.get("eod", 0)),
        "avg_stop_points": round(float(np.mean([row["risk_points"] for row in trades])), 2) if trades else 0.0,
        "median_stop_points": round(float(np.median([row["risk_points"] for row in trades])), 2) if trades else 0.0,
        "fixed_target_reaches_mean_pct": round(float(np.mean([row["fixed_target_reaches_mean"] for row in trades])), 4) if trades else 0.0,
        "deployability": "research_only",
        "live_support_notes": (
            "Native-timeframe static-RR VWAP cadence prototype exists only in this research script; "
            "live execution and exact replay parity are not implemented."
        ),
        "exact_replay_required": "yes",
    }


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
    stop_grid = _make_stop_grid()
    rows: list[dict[str, Any]] = []
    trades_by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    timeframe_meta: list[dict[str, Any]] = []

    for timeframe_min in TIMEFRAMES:
        tf_config = _timeframe_config(timeframe_min)
        print(
            f"\nPreparing {tf_config.label}: cons={tf_config.setup.consolidation_bars} bars, "
            f"timeout={tf_config.setup.setup_timeout_bars}, cooldown={tf_config.setup.cooldown_bars}",
            flush=True,
        )
        df_tf = _resample_ohlcv(df_1m, timeframe_min)
        days = ctx._prepare_days(ctx._prepare_rth(df_tf))
        trading_days = len(days)
        prior_ranges = _prior_session_ranges(days)
        candidates_by_day = [ctx._generate_candidates_for_day(day, tf_config.setup) for day in days]
        total_candidates = sum(len(day_candidates) for day_candidates in candidates_by_day)
        print(f"  days={trading_days}; candidate events={total_candidates}", flush=True)
        timeframe_meta.append(
            {
                "timeframe": tf_config.label,
                "timeframe_min": timeframe_min,
                "bars": int(len(df_tf)),
                "trading_days": trading_days,
                "candidate_events": total_candidates,
                "consolidation_bars": tf_config.setup.consolidation_bars,
                "setup_timeout_bars": tf_config.setup.setup_timeout_bars,
                "cooldown_bars": tf_config.setup.cooldown_bars,
            }
        )
        for idx, stop_config in enumerate(stop_grid, start=1):
            trades = _simulate_model(days, candidates_by_day, tf_config, stop_config, prior_ranges)
            trades_by_key[(tf_config.label, stop_config.label)] = trades
            row = _score_trades(trades, trading_days, tf_config, stop_config, total_candidates)
            rows.append(row)
            print(
                f"  {idx:02d}/{len(stop_grid)} {stop_config.label}: "
                f"{row['total_trades']} trades {row['total_r']:+.2f}R "
                f"PF {row['profit_factor']:.3f} DD {row['max_drawdown_r']:.2f}R",
                flush=True,
            )

    ranked = pd.DataFrame(rows).sort_values(
        ["calmar", "negative_full_years", "profit_factor", "total_r", "max_drawdown_r"],
        ascending=[False, True, False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    best_by_timeframe = (
        ranked.sort_values(["timeframe_min", "calmar", "profit_factor"], ascending=[True, False, False])
        .groupby("timeframe", group_keys=False)
        .head(1)
        .sort_values("timeframe_min")
        .reset_index(drop=True)
    )
    carry_forward = ranked[
        (ranked["stop_basis"] == "prior_session_range")
        & (ranked["stop_pct"].round(6) == 0.10)
    ].sort_values("timeframe_min")
    frequency_fit = ranked[
        (ranked["avg_trades_per_day"] >= 1.0)
        & (ranked["avg_trades_per_day"] <= 3.0)
        & (ranked["pct_days_with_trade"] >= 0.70)
    ].copy()
    frequency_fit_pf105 = frequency_fit[frequency_fit["profit_factor"] >= 1.05].copy()

    top = ranked.iloc[0].to_dict()
    top_key = (str(top["timeframe"]), str(top["stop_model"]))
    top_trades = trades_by_key[top_key]
    top_yearly = _yearly_rows(top_trades)

    ranked_path = RESULT_DIR / "timeframe_sweep_results.csv"
    best_by_tf_path = RESULT_DIR / "best_by_timeframe.csv"
    carry_forward_path = RESULT_DIR / "prior_session_range_pct10_by_timeframe.csv"
    top_trades_path = RESULT_DIR / "top_timeframe_static_rr_trades.csv"
    top_yearly_path = RESULT_DIR / "top_timeframe_static_rr_yearly.csv"
    summary_path = RESULT_DIR / "summary.json"

    ranked.to_csv(ranked_path, index=False)
    best_by_timeframe.to_csv(best_by_tf_path, index=False)
    carry_forward.to_csv(carry_forward_path, index=False)
    pd.DataFrame(top_trades).drop(columns=["exit_idx", "extension_idx", "signal_idx", "entry_idx"], errors="ignore").to_csv(
        top_trades_path,
        index=False,
    )
    top_yearly.to_csv(top_yearly_path, index=False)

    report_cols = [
        "rank",
        "timeframe",
        "stop_basis",
        "stop_pct",
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
        "avg_stop_points",
        "deployability",
    ]
    tf_cols = [
        "timeframe",
        "consolidation_bars",
        "setup_timeout_bars",
        "cooldown_bars",
        "stop_basis",
        "stop_pct",
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

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "native_timeframe_static_rr_sweep",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "rr": RR,
        "timeframes": list(TIMEFRAMES),
        "time_normalized": True,
        "setup_duration": {
            "consolidation_minutes": 30,
            "setup_timeout_minutes": 60,
            "cooldown_minutes_approx": 10,
        },
        "context": _safe(asdict(_timeframe_config(5).context)),
        "grid_rows": int(len(ranked)),
        "frequency_fit_rows": int(len(frequency_fit)),
        "frequency_fit_pf105_rows": int(len(frequency_fit_pf105)),
        "timeframe_meta": _safe(timeframe_meta),
        "best_row": _safe(top),
        "best_by_timeframe": _safe(best_by_timeframe.to_dict(orient="records")),
        "prior_session_range_pct10_by_timeframe": _safe(carry_forward.to_dict(orient="records")),
        "artifacts": {
            "sweep_results": str(ranked_path.relative_to(ROOT)),
            "best_by_timeframe": str(best_by_tf_path.relative_to(ROOT)),
            "prior_session_range_pct10_by_timeframe": str(carry_forward_path.relative_to(ROOT)),
            "top_trades": str(top_trades_path.relative_to(ROOT)),
            "top_yearly": str(top_yearly_path.relative_to(ROOT)),
            "report": str(REPORT_PATH.relative_to(ROOT)),
        },
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_lines = [
        "# NQ NY VWAP Static 1:1.5R Native Timeframe Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{DATA_START}` to `<{DATA_END_EXCLUSIVE}` from raw NQ 1m bars; 2m/3m/5m were resampled from 1m for alignment.",
        f"- Timeframes: `{', '.join(f'{tf}m' for tf in TIMEFRAMES)}`",
        "- Setup was time-normalized: 30-minute consolidation, 60-minute setup timeout, and about 10-minute post-exit cooldown.",
        "- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full window.",
        f"- Exit: static fixed `{RR}:1` reward-to-risk, conservative OHLC path with stop priority on same-bar stop/target touches.",
        "- Stop basis is known at signal time: previous daily ATR, prior RTH session range, or current session range-so-far.",
        "- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.",
        "",
        "## Entry Criteria",
        "",
        "Long setup:",
        "",
        "1. During NY RTH, use session VWAP as the mean.",
        "2. Price must be below VWAP and extend at least `0.025 * prior 14-day RTH ATR` away from VWAP.",
        "3. After the extension, wait for a 30-minute consolidation below VWAP whose high-low range is no more than `0.20 * ATR`.",
        "4. The consolidation must remain below VWAP, and the consolidation low must still be at least `0.025 * ATR` below VWAP.",
        "5. Signal bar must sweep below the consolidation low, then close back above that consolidation low while still closing below VWAP.",
        "6. Enter long on the next bar open. Maximum 3 trades/day, non-overlapping, with about 10 minutes cooldown after exit.",
        "",
        "Short setup is the mirror image above VWAP: extension above VWAP, tight consolidation above VWAP, sweep above consolidation high, close back below that high while still above VWAP, then short next bar open.",
        "",
        "Static exit used in this sweep: stop from selected volatility basis, target fixed at `1.5R`, flat by `15:55` if neither stop nor target hits.",
        "",
        "## Best By Timeframe",
        "",
        _format_table(best_by_timeframe, tf_cols, n=None),
        "",
        "## Direct Carry-Forward: Prior Session Range 10% Stop",
        "",
        _format_table(carry_forward, tf_cols, n=None),
        "",
        "## Top Rows Overall",
        "",
        _format_table(ranked, report_cols, n=20),
        "",
        "## Frequency-Fit Rows With PF >= 1.05",
        "",
        _format_table(frequency_fit_pf105, report_cols, n=20),
        "",
        "## Best Overall Year Split",
        "",
        top_yearly.to_markdown(index=False),
        "",
        "## Summary Read",
        "",
        f"- Best overall native-timeframe row: `{top['timeframe']}` `{top['stop_model']}` with `{int(top['total_trades'])}` trades, `{top['avg_trades_per_day']}` trades/day, `{top['total_r']:+.2f}R`, PF `{top['profit_factor']:.3f}`, Calmar `{top['calmar']:.3f}`, max DD `{top['max_drawdown_r']:.2f}R`.",
        f"- Frequency-fit rows with PF `>=1.05`: `{len(frequency_fit_pf105)}` out of `{len(ranked)}`.",
        "- Treat this as a native-timeframe research screen. It still needs lower-timeframe exact replay, train/validation, and prop lifecycle scoring before promotion.",
        "",
        "## Artifacts",
        "",
        f"- Sweep results: `backtesting/data/results/{RUN_SLUG}/timeframe_sweep_results.csv`",
        f"- Best by timeframe: `backtesting/data/results/{RUN_SLUG}/best_by_timeframe.csv`",
        f"- Prior-session-range 10% by timeframe: `backtesting/data/results/{RUN_SLUG}/prior_session_range_pct10_by_timeframe.csv`",
        f"- Top trades: `backtesting/data/results/{RUN_SLUG}/top_timeframe_static_rr_trades.csv`",
        f"- Top yearly: `backtesting/data/results/{RUN_SLUG}/top_timeframe_static_rr_yearly.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {ranked_path}")
    print(f"Wrote {best_by_tf_path}")
    print(f"Wrote {carry_forward_path}")
    print(f"Wrote {top_trades_path}")
    print(f"Wrote {top_yearly_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
