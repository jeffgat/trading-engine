#!/usr/bin/env python3
"""Static 1:1.5R stop-basis sweep for the NQ NY VWAP cadence leg.

This reuses the recent 5-year VWAP level-reversion state-machine setup, keeps
the high-cadence anchor constant, and replaces the dynamic VWAP target with a
fixed 1.5R target. Stops are sized from previous ATR, prior RTH session range,
or current session range known at signal time.
"""

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
sys.path.insert(0, str(ROOT / "src"))

RUN_SLUG = "nq_ny_vwap_static_rr_stop_sweep_20260630"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_STATIC_RR_STOP_SWEEP_20260630.md"

RR = 1.5
MIN_STOP_TICKS = 4
NQ_TICK = 0.25


def _load_context_module() -> Any:
    path = SCRIPT_DIR / "run_nq_ny_level_reversion_context_filter_recent5_20260629.py"
    spec = importlib.util.spec_from_file_location("nq_level_context_20260629", path)
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


BASE_CONFIG = ctx.StateMachineConfig(
    label="best_cadence_anchor_static_rr",
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

BASE_CONTEXT = ctx.ContextConfig(
    structure_gate="none",
    vwap_acceptance="none",
    efficiency_max=None,
    ib_location="none",
    session_range_atr_max=2.0,
    time_bucket="full",
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


def _prior_session_ranges(days: list[Any]) -> dict[str, float]:
    ranges: dict[str, float] = {}
    previous: float | None = None
    for day in days:
        if previous is not None and math.isfinite(previous) and previous > 0:
            ranges[day.date] = previous
        else:
            ranges[day.date] = float(day.atr)
        previous = float(day.session_high_so_far[-1] - day.session_low_so_far[-1])
    return ranges


def _stop_base_points(day: Any, candidate: dict[str, Any], config: StaticStopConfig, prior_ranges: dict[str, float]) -> float:
    signal_idx = int(candidate["signal_idx"])
    if config.stop_basis == "atr14_prev":
        return float(day.atr)
    if config.stop_basis == "prior_session_range":
        return float(prior_ranges.get(day.date, day.atr))
    if config.stop_basis == "session_range_so_far":
        return float(max(day.session_high_so_far[signal_idx] - day.session_low_so_far[signal_idx], NQ_TICK))
    raise ValueError(f"Unknown stop_basis: {config.stop_basis}")


def _simulate_static_exit(
    day: Any,
    candidate: dict[str, Any],
    config: StaticStopConfig,
    prior_ranges: dict[str, float],
) -> dict[str, Any] | None:
    direction = int(candidate["direction_int"])
    entry_idx = int(candidate["entry_idx"])
    entry = float(day.opens[entry_idx])
    stop_base = _stop_base_points(day, candidate, config, prior_ranges)
    raw_stop_points = stop_base * config.stop_pct
    stop_ticks = _ceil_even_stop_ticks(raw_stop_points)
    risk = stop_ticks * NQ_TICK
    reward = risk * config.rr

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
        "rr": config.rr,
        "r_multiple": round(float(r_multiple), 4),
        "stop_basis": config.stop_basis,
        "stop_pct": config.stop_pct,
        "stop_model": config.label,
        "stop_base_points": round(stop_base, 2),
        "raw_stop_points": round(raw_stop_points, 4),
        "stop_ticks": stop_ticks,
        "rr_to_mean_static_stop": round(rr_to_mean_static_stop, 4),
        "fixed_target_reaches_mean": bool(rr_to_mean_static_stop >= config.rr),
        "atr14_prev": candidate["atr14_prev"],
        "session_range_atr": candidate["session_range_atr"],
        "setup_wait_bars": candidate["setup_wait_bars"],
        "vwap_slope_atr": candidate["vwap_slope_atr"],
        "directional_vwap_distance_atr": candidate["directional_vwap_distance_atr"],
        "directional_efficiency": candidate["directional_efficiency"],
        "structure_30m": candidate["structure_30m"],
        "base_variant_id": "vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2",
        "context_session_range_atr_max": BASE_CONTEXT.session_range_atr_max,
        "deployability": "research_only",
        "live_support_notes": (
            "Static-RR VWAP cadence prototype exists only in this research script; "
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
    config: StaticStopConfig,
    prior_ranges: dict[str, float],
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
            if not ctx._context_accepts(candidate, BASE_CONTEXT):
                continue
            trade = _simulate_static_exit(day, candidate, config, prior_ranges)
            if trade is None:
                continue
            trades.append(trade)
            day_trade_count += 1
            current_min_idx = int(trade["exit_idx"]) + BASE_CONFIG.cooldown_bars
    return trades


def _score_trades(trades: list[dict[str, Any]], trading_days: int, config: StaticStopConfig) -> dict[str, Any]:
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
    negative_years = int((yearly["total_r"] < 0).sum()) if not yearly.empty else 0
    full_years = yearly[yearly["year"].isin(["2022", "2023", "2024", "2025"])] if not yearly.empty else yearly
    negative_full_years = int((full_years["total_r"] < 0).sum()) if not full_years.empty else 0
    avg_stop = float(np.mean([row["risk_points"] for row in trades])) if trades else 0.0
    median_stop = float(np.median([row["risk_points"] for row in trades])) if trades else 0.0
    target_before_mean = float(np.mean([row["fixed_target_reaches_mean"] for row in trades])) if trades else 0.0
    avg_annual_r = total_r / years if years else 0.0
    calmar = avg_annual_r / abs(max_dd) if max_dd < 0 else 0.0
    return {
        **asdict(config),
        "stop_model": config.label,
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
        "negative_years": negative_years,
        "negative_full_years": negative_full_years,
        "target_exits": int(exits.get("target", 0)),
        "stop_exits": int(exits.get("stop", 0)),
        "eod_exits": int(exits.get("eod", 0)),
        "avg_stop_points": round(avg_stop, 2),
        "median_stop_points": round(median_stop, 2),
        "fixed_target_reaches_mean_pct": round(target_before_mean, 4),
        "deployability": "research_only",
        "live_support_notes": (
            "Static-RR VWAP cadence prototype exists only in this research script; "
            "live execution and exact replay parity are not implemented."
        ),
        "exact_replay_required": "yes",
    }


def _yearly_rows(trades: list[dict[str, Any]]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["year", "trades", "total_r", "avg_r", "win_rate", "profit_factor", "max_drawdown_r"])
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


def _make_grid() -> list[StaticStopConfig]:
    configs: list[StaticStopConfig] = []
    for pct in (0.03, 0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25):
        configs.append(StaticStopConfig("atr14_prev", pct))
    for pct in (0.05, 0.075, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00):
        configs.append(StaticStopConfig("prior_session_range", pct))
        configs.append(StaticStopConfig("session_range_so_far", pct))
    return configs


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

    print(f"Loading NQ 5m data {ctx.DATA_START} to {ctx.DATA_END_EXCLUSIVE}...")
    df = ctx.load_5m_data(ctx.NQ.data_file, start=ctx.DATA_START, end=ctx.DATA_END_EXCLUSIVE)
    days = ctx._prepare_days(ctx._prepare_rth(df))
    trading_days = len(days)
    prior_ranges = _prior_session_ranges(days)
    print(f"Prepared {trading_days} RTH days; first={days[0].date} last={days[-1].date}")

    print("Generating base high-cadence VWAP candidates...")
    candidates_by_day = [ctx._generate_candidates_for_day(day, BASE_CONFIG) for day in days]
    total_candidates = sum(len(day_candidates) for day_candidates in candidates_by_day)
    print(f"Candidate events={total_candidates}")

    configs = _make_grid()
    print(f"Static stop grid={len(configs)} configs; RR={RR}")
    rows: list[dict[str, Any]] = []
    trades_by_label: dict[str, list[dict[str, Any]]] = {}
    for idx, config in enumerate(configs, start=1):
        trades = _simulate_model(days, candidates_by_day, config, prior_ranges)
        trades_by_label[config.label] = trades
        row = _score_trades(trades, trading_days, config)
        row["total_candidates"] = total_candidates
        rows.append(row)
        print(
            f"  {idx:02d}/{len(configs)} {config.label}: "
            f"{row['total_trades']} trades {row['total_r']:+.2f}R "
            f"PF {row['profit_factor']:.3f} DD {row['max_drawdown_r']:.2f}R",
            flush=True,
        )

    ranked = pd.DataFrame(rows).sort_values(
        ["calmar", "negative_full_years", "profit_factor", "total_r", "max_drawdown_r"],
        ascending=[False, True, False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))

    frequency_fit = ranked[
        (ranked["avg_trades_per_day"] >= 1.0)
        & (ranked["avg_trades_per_day"] <= 3.0)
        & (ranked["pct_days_with_trade"] >= 0.70)
    ].copy()
    positive_pf105 = frequency_fit[frequency_fit["profit_factor"] >= 1.05].copy()

    top = ranked.iloc[0].to_dict()
    top_label = str(top["stop_model"])
    top_trades = trades_by_label[top_label]
    top_yearly = _yearly_rows(top_trades)

    ranked_path = RESULT_DIR / "sweep_results.csv"
    top_trades_path = RESULT_DIR / "top_static_rr_trades.csv"
    yearly_path = RESULT_DIR / "top_static_rr_yearly.csv"
    summary_path = RESULT_DIR / "summary.json"
    ranked.to_csv(ranked_path, index=False)
    pd.DataFrame(top_trades).drop(columns=["exit_idx", "extension_idx", "signal_idx", "entry_idx"], errors="ignore").to_csv(
        top_trades_path,
        index=False,
    )
    top_yearly.to_csv(yearly_path, index=False)

    report_cols = [
        "rank",
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
        "fixed_target_reaches_mean_pct",
        "deployability",
    ]
    basis_cols = [
        "rank",
        "stop_pct",
        "total_trades",
        "avg_trades_per_day",
        "total_r",
        "calmar",
        "profit_factor",
        "max_drawdown_r",
        "avg_stop_points",
    ]
    best_by_basis = ranked.groupby("stop_basis", group_keys=False).head(1).sort_values("stop_basis")

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "static_rr_stop_sweep",
        "data_start": ctx.DATA_START,
        "data_end_exclusive": ctx.DATA_END_EXCLUSIVE,
        "trading_days": trading_days,
        "rr": RR,
        "min_stop_ticks": MIN_STOP_TICKS,
        "base_variant_id": "vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2",
        "base_context": _safe(asdict(BASE_CONTEXT)),
        "candidate_events": total_candidates,
        "grid_rows": len(ranked),
        "frequency_fit_rows": int(len(frequency_fit)),
        "frequency_fit_pf105_rows": int(len(positive_pf105)),
        "best_row": _safe(top),
        "best_by_basis": _safe(best_by_basis.to_dict(orient="records")),
        "artifacts": {
            "sweep_results": str(ranked_path.relative_to(ROOT)),
            "top_trades": str(top_trades_path.relative_to(ROOT)),
            "top_yearly": str(yearly_path.relative_to(ROOT)),
            "report": str(REPORT_PATH.relative_to(ROOT)),
        },
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_lines = [
        "# NQ NY VWAP Static 1:1.5R Stop Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{ctx.DATA_START}` to `<{ctx.DATA_END_EXCLUSIVE}` using NQ 5m RTH bars",
        f"- Trading days: `{trading_days}`",
        f"- Base setup: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` high-cadence VWAP state-machine anchor",
        f"- Context: no structure/VWAP/efficiency/IB filter, `session_range_atr_max=2.0`, full window",
        f"- Exit: static fixed `{RR}:1` reward-to-risk, conservative 5m path with stop priority on same-bar stop/target touches",
        "- Stop basis is known at signal time: previous daily ATR, prior RTH session range, or current session range-so-far.",
        "- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.",
        "",
        "## Top Rows By Calmar",
        "",
        _format_table(ranked, report_cols, n=15),
        "",
        "## Frequency-Fit Rows",
        "",
        _format_table(frequency_fit, report_cols, n=15),
        "",
        "## Frequency-Fit Rows With PF >= 1.05",
        "",
        _format_table(positive_pf105, report_cols, n=15),
        "",
        "## Best By Stop Basis",
        "",
        _format_table(best_by_basis, ["stop_basis", *basis_cols], n=None),
        "",
        "## Best Row Year Split",
        "",
        top_yearly.to_markdown(index=False),
        "",
        "## Summary Read",
        "",
        f"- Best static-RR row: `{top_label}` with `{int(top['total_trades'])}` trades, `{top['avg_trades_per_day']}` trades/day, `{top['total_r']:+.2f}R`, PF `{top['profit_factor']:.3f}`, Calmar `{top['calmar']:.3f}`, max DD `{top['max_drawdown_r']:.2f}R`.",
        f"- Frequency-fit rows (`1-3` trades/day and >=70% day coverage): `{len(frequency_fit)}`.",
        f"- Frequency-fit rows with PF `>=1.05`: `{len(positive_pf105)}`.",
        "- Treat this as a 5m research screen. Any survivor still needs 1m/1s path replay and prop-firm lifecycle scoring before promotion.",
        "",
        "## Artifacts",
        "",
        f"- Sweep results: `backtesting/data/results/{RUN_SLUG}/sweep_results.csv`",
        f"- Top trades: `backtesting/data/results/{RUN_SLUG}/top_static_rr_trades.csv`",
        f"- Top yearly: `backtesting/data/results/{RUN_SLUG}/top_static_rr_yearly.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {ranked_path}")
    print(f"Wrote {top_trades_path}")
    print(f"Wrote {yearly_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
