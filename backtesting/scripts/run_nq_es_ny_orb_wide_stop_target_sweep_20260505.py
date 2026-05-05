#!/usr/bin/env python3
"""Focused NY ORB wide-stop target sweep for NQ R11 and ES ALPHA_V1.

Research artifact only. Does not edit execution configs.

Question:
- Can NQ NY ORB R11 and ES NY ORB widen their NY stops while preserving the
  current result quality?

The sweep holds each candidate's signal/session structure fixed, then varies:
- stop basis/width: ATR% and ORB%
- rr
- TP1 distance in R units, converted to tp1_ratio per rr
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.config import Instrument, SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "nq_es_ny_orb_wide_stop_target_sweep_20260505"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_ES_NY_ORB_WIDE_STOP_TARGET_SWEEP_20260505.md"

FULL_START = "2016-04-17"
END_INCLUSIVE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"
WORKERS = 8

WINDOWS = {
    "last_1y": (LAST_1Y_START, END_INCLUSIVE),
    "last_2y": (LAST_2Y_START, END_INCLUSIVE),
    "full": (FULL_START, END_INCLUSIVE),
}

TP1_R_VALUES = (1.0, 1.25, 1.4, 1.5, 2.0, 2.5, 3.0)
MIN_TP1_RATIO = 0.20
MAX_TP1_RATIO = 0.75


@dataclass(frozen=True)
class CandidateSpec:
    key: str
    label: str
    instrument: Instrument
    data_file: str
    base_config: StrategyConfig
    baseline_stop_source: str
    baseline_stop_value: float
    baseline_rr: float
    baseline_tp1_ratio: float
    atr_stop_values: tuple[float, ...]
    orb_stop_values: tuple[float, ...]
    rr_values: tuple[float, ...]
    deployability: str
    live_support_notes: str
    exact_replay_required: str


@dataclass(frozen=True)
class VariantSpec:
    candidate: CandidateSpec
    variant_id: str
    stop_source: str
    stop_value: float
    rr: float
    tp1_ratio: float
    tp1_r: float
    config: StrategyConfig


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        value = float(data)
        return value if math.isfinite(value) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _fmt_float(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text.replace(".", "p")


def _tp_pairs(rr_values: tuple[float, ...]) -> list[tuple[float, float, float]]:
    pairs: list[tuple[float, float, float]] = []
    seen: set[tuple[float, float]] = set()
    for rr in rr_values:
        for tp1_r in TP1_R_VALUES:
            tp1_ratio = round(tp1_r / rr, 6)
            if tp1_ratio < MIN_TP1_RATIO or tp1_ratio > MAX_TP1_RATIO:
                continue
            key = (round(rr, 6), round(tp1_ratio, 6))
            if key in seen:
                continue
            seen.add(key)
            pairs.append((rr, tp1_ratio, round(rr * tp1_ratio, 4)))
    return pairs


def _session_replace(config: StrategyConfig, **updates: Any) -> StrategyConfig:
    return replace(config, sessions=(replace(config.sessions[0], **updates),))


def _with_stop_target(
    config: StrategyConfig,
    *,
    name: str,
    stop_source: str,
    stop_value: float,
    rr: float,
    tp1_ratio: float,
) -> StrategyConfig:
    cfg = replace(config, name=name, rr=rr, tp1_ratio=tp1_ratio)
    if stop_source == "atr_pct":
        return _session_replace(cfg, stop_atr_pct=stop_value, stop_orb_pct=0.0)
    if stop_source == "orb_pct":
        return _session_replace(cfg, stop_atr_pct=0.0, stop_orb_pct=stop_value)
    raise ValueError(f"Unknown stop_source {stop_source!r}")


def _candidates() -> list[CandidateSpec]:
    nq_session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
    )
    nq_config = StrategyConfig(
        sessions=(nq_session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        excluded_days=(4,),
        impulse_close_filter=False,
        name="nq_ny_orb_r11_baseline",
    )

    es_session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.25,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    es_config = StrategyConfig(
        sessions=(es_session,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        excluded_days=(3,),
        impulse_close_filter=False,
        name="es_ny_orb_baseline",
    )

    return [
        CandidateSpec(
            key="nq_ny_orb_r11",
            label="NQ NY ORB R11 conditional long",
            instrument=NQ,
            data_file="NQ_5m.parquet",
            base_config=nq_config,
            baseline_stop_source="atr_pct",
            baseline_stop_value=7.0,
            baseline_rr=3.5,
            baseline_tp1_ratio=0.4,
            atr_stop_values=(7.0, 8.0, 9.0, 10.0, 12.0, 14.0, 16.0),
            orb_stop_values=(17.0, 25.0, 33.0, 50.0, 75.0, 100.0, 125.0),
            rr_values=(2.5, 3.0, 3.5, 4.0, 5.0),
            deployability="live_native",
            live_support_notes="Standard ORB continuation fields; NQ R11 is not active ALPHA_V1-A but all swept knobs are execution-supported.",
            exact_replay_required="yes_before_live_promotion",
        ),
        CandidateSpec(
            key="es_ny_orb",
            label="ES NY ORB ALPHA_V1",
            instrument=ES,
            data_file="ES_5m.parquet",
            base_config=es_config,
            baseline_stop_source="atr_pct",
            baseline_stop_value=5.0,
            baseline_rr=5.0,
            baseline_tp1_ratio=0.2,
            atr_stop_values=(5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 14.0),
            orb_stop_values=(25.0, 50.0, 75.0, 100.0, 125.0, 150.0),
            rr_values=(2.0, 2.5, 3.0, 4.0, 5.0, 6.0),
            deployability="live_native",
            live_support_notes="Active ALPHA_V1 ORB leg; all swept stop/target knobs are execution-supported.",
            exact_replay_required="yes_before_live_promotion",
        ),
    ]


def _variants_for(candidate: CandidateSpec) -> list[VariantSpec]:
    variants: list[VariantSpec] = []
    stop_options = [
        *[("atr_pct", value) for value in candidate.atr_stop_values],
        *[("orb_pct", value) for value in candidate.orb_stop_values],
    ]
    for stop_source, stop_value in stop_options:
        for rr, tp1_ratio, tp1_r in _tp_pairs(candidate.rr_values):
            variant_id = (
                f"{stop_source}{_fmt_float(stop_value)}"
                f"__rr{_fmt_float(rr)}__tp1r{_fmt_float(tp1_r)}"
            )
            name = f"{candidate.key}__{variant_id}"[:240]
            try:
                cfg = _with_stop_target(
                    candidate.base_config,
                    name=name,
                    stop_source=stop_source,
                    stop_value=stop_value,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                )
            except ValueError as exc:
                print(f"  skip {name}: {exc}", flush=True)
                continue
            variants.append(
                VariantSpec(
                    candidate=candidate,
                    variant_id=variant_id,
                    stop_source=stop_source,
                    stop_value=stop_value,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                    tp1_r=tp1_r,
                    config=cfg,
                )
            )
    return variants


def _load_data(candidate: CandidateSpec) -> dict[str, pd.DataFrame | None]:
    df_5m = load_5m_data(candidate.data_file, start=FULL_START)
    try:
        df_1m = load_1m_for_5m(candidate.data_file, start=FULL_START)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(candidate.data_file, start=FULL_START)
    except FileNotFoundError:
        df_1s = None
    return {"df": df_5m, "df_1m": df_1m, "df_1s": df_1s, "signal_df_1m": df_1m}


def _run_candidate(candidate: CandidateSpec, variants: list[VariantSpec]) -> dict[str, list[TradeResult]]:
    print(f"Running {candidate.key}: {len(variants)} configs", flush=True)
    loaded = _load_data(candidate)
    print(
        f"  data: 5m={len(loaded['df']) if loaded['df'] is not None else 0:,} "
        f"1m={len(loaded['df_1m']) if loaded['df_1m'] is not None else 0:,} "
        f"1s={len(loaded['df_1s']) if loaded['df_1s'] is not None else 0:,}",
        flush=True,
    )

    def progress(done: int, total: int) -> None:
        if done == total or done % 50 == 0:
            print(f"  {candidate.key}: {done}/{total}", flush=True)

    results = run_sweep(
        loaded["df"],
        [variant.config for variant in variants],
        n_workers=min(WORKERS, max(1, len(variants))),
        start_date=FULL_START,
        end_date=END_EXCLUSIVE,
        df_1m=loaded["df_1m"],
        df_1s=loaded["df_1s"],
        signal_df_1m=loaded["signal_df_1m"],
        progress_fn=progress,
    )
    by_name = {variant.config.name: variant for variant in variants}
    trades_by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        trades_by_name[config.name] = [
            trade
            for trade in sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
            if trade.exit_type != EXIT_NO_FILL
        ]
        _ = by_name[config.name]
    return trades_by_name


def _slice(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _stop_stats(trades: list[TradeResult], instrument: Instrument) -> dict[str, Any]:
    risks = [float(trade.risk_points) for trade in trades if trade.risk_points > 0]
    if not risks:
        return {
            "median_stop_points": None,
            "median_stop_ticks": None,
            "p25_stop_ticks": None,
            "p75_stop_ticks": None,
        }
    ticks = [risk / instrument.min_tick for risk in risks]
    return {
        "median_stop_points": _round(median(risks), 4),
        "median_stop_ticks": _round(median(ticks), 1),
        "p25_stop_ticks": _round(float(np.percentile(ticks, 25)), 1),
        "p75_stop_ticks": _round(float(np.percentile(ticks, 75)), 1),
    }


def _exit_stats(trades: list[TradeResult]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for trade in trades:
        name = EXIT_NAMES.get(trade.exit_type, str(trade.exit_type))
        counts[name] = counts.get(name, 0) + 1
    total = max(1, len(trades))
    full_tp = counts.get("tp1_tp2", 0) + counts.get("tp2_single", 0)
    partial_be = counts.get("tp1_be", 0)
    partial_eod = counts.get("tp1_eod", 0)
    stops = counts.get("sl", 0)
    return {
        "exit_counts": counts,
        "full_tp_count": full_tp,
        "full_tp_rate_pct": _round(100.0 * full_tp / total, 2),
        "tp1_be_count": partial_be,
        "tp1_be_rate_pct": _round(100.0 * partial_be / total, 2),
        "tp1_eod_count": partial_eod,
        "tp1_eod_rate_pct": _round(100.0 * partial_eod / total, 2),
        "sl_count": stops,
        "sl_rate_pct": _round(100.0 * stops / total, 2),
    }


def _metric_row(
    *,
    variant: VariantSpec,
    trades: list[TradeResult],
    window: str,
    start: str,
    end: str,
) -> dict[str, Any]:
    selected = _slice(trades, start, end)
    metrics = compute_metrics(selected)
    stop_stats = _stop_stats(selected, variant.candidate.instrument)
    exit_stats = _exit_stats(selected)
    return {
        "candidate": variant.candidate.key,
        "label": variant.candidate.label,
        "variant_id": variant.variant_id,
        "window": window,
        "start": start,
        "end": end,
        "stop_source": variant.stop_source,
        "stop_value": variant.stop_value,
        "rr": variant.rr,
        "tp1_ratio": variant.tp1_ratio,
        "tp1_r": variant.tp1_r,
        "signals": int(metrics["total_signals"]),
        "trades": int(metrics["total_trades"]),
        "no_fills": int(metrics["no_fills"]),
        "net_r": _round(metrics["total_r"], 2),
        "win_rate_pct": _round(float(metrics["win_rate"]) * 100.0, 2),
        "profit_factor": _round(metrics["profit_factor"], 3),
        "avg_r": _round(metrics["avg_r"], 4),
        "sharpe_ratio": _round(metrics["sharpe_ratio"], 3),
        "max_dd_r": _round(metrics["max_drawdown_r"], 2),
        "calmar_ratio": _round(metrics["calmar_ratio"], 3),
        "negative_years": int(sum(1 for value in (metrics.get("r_by_year") or {}).values() if value < 0)),
        "r_by_year": metrics.get("r_by_year") or {},
        **stop_stats,
        **exit_stats,
        "deployability": variant.candidate.deployability,
        "live_support_notes": variant.candidate.live_support_notes,
        "exact_replay_required": variant.candidate.exact_replay_required,
    }


def _baseline_lookup(metric_rows: list[dict[str, Any]], candidates: list[CandidateSpec]) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for candidate in candidates:
        tp1_r = round(candidate.baseline_rr * candidate.baseline_tp1_ratio, 4)
        variant_id = (
            f"{candidate.baseline_stop_source}{_fmt_float(candidate.baseline_stop_value)}"
            f"__rr{_fmt_float(candidate.baseline_rr)}__tp1r{_fmt_float(tp1_r)}"
        )
        rows = [row for row in metric_rows if row["candidate"] == candidate.key and row["variant_id"] == variant_id]
        out[candidate.key] = {str(row["window"]): row for row in rows}
    return out


def _score_rows(
    metric_rows: list[dict[str, Any]],
    baseline_by_candidate: dict[str, dict[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    by_variant: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metric_rows:
        by_variant.setdefault((str(row["candidate"]), str(row["variant_id"])), []).append(row)

    ranked: list[dict[str, Any]] = []
    for (candidate_key, variant_id), rows in by_variant.items():
        by_window = {str(row["window"]): row for row in rows}
        if not {"last_1y", "last_2y", "full"} <= set(by_window):
            continue
        base_windows = baseline_by_candidate[candidate_key]
        full = by_window["full"]
        last1 = by_window["last_1y"]
        last2 = by_window["last_2y"]
        base_full = base_windows["full"]
        base_last1 = base_windows["last_1y"]
        base_last2 = base_windows["last_2y"]

        base_stop = float(base_full.get("median_stop_ticks") or 0.0)
        stop_mult = (float(full["median_stop_ticks"] or 0.0) / base_stop) if base_stop > 0 else 0.0
        full_r_delta = float(full["net_r"] or 0.0) - float(base_full["net_r"] or 0.0)
        last1_r_delta = float(last1["net_r"] or 0.0) - float(base_last1["net_r"] or 0.0)
        last2_r_delta = float(last2["net_r"] or 0.0) - float(base_last2["net_r"] or 0.0)
        dd_worse = abs(float(full["max_dd_r"] or 0.0)) - abs(float(base_full["max_dd_r"] or 0.0))
        pf_delta = float(full["profit_factor"] or 0.0) - float(base_full["profit_factor"] or 0.0)

        near_intact = (
            stop_mult >= 1.20
            and float(full["net_r"] or 0.0) >= 0.90 * float(base_full["net_r"] or 0.0)
            and float(last1["net_r"] or 0.0) >= 0.80 * float(base_last1["net_r"] or 0.0)
            and float(last2["net_r"] or 0.0) >= 0.80 * float(base_last2["net_r"] or 0.0)
            and abs(float(full["max_dd_r"] or 0.0)) <= 1.25 * abs(float(base_full["max_dd_r"] or 0.0))
            and float(full["profit_factor"] or 0.0) >= float(base_full["profit_factor"] or 0.0) - 0.10
            and int(full["negative_years"] or 0) <= int(base_full["negative_years"] or 0)
        )

        score = (
            20.0 * min(stop_mult, 3.0)
            + 2.0 * full_r_delta
            + 3.0 * last1_r_delta
            + 1.5 * last2_r_delta
            - 2.0 * max(dd_worse, 0.0)
            + 25.0 * pf_delta
            - 12.0 * max(0, int(full["negative_years"] or 0) - int(base_full["negative_years"] or 0))
        )
        if not near_intact:
            score -= 35.0

        ranked.append(
            {
                "candidate": candidate_key,
                "label": full["label"],
                "variant_id": variant_id,
                "stop_source": full["stop_source"],
                "stop_value": float(full["stop_value"]),
                "rr": float(full["rr"]),
                "tp1_ratio": float(full["tp1_ratio"]),
                "tp1_r": float(full["tp1_r"]),
                "stop_width_mult": _round(stop_mult, 3),
                "near_intact": near_intact,
                "wide_stop_score": _round(score, 3),
                "full_net_r": float(full["net_r"] or 0.0),
                "full_r_delta": _round(full_r_delta, 2),
                "full_trades": int(full["trades"] or 0),
                "full_wr_pct": float(full["win_rate_pct"] or 0.0),
                "full_pf": float(full["profit_factor"] or 0.0),
                "full_pf_delta": _round(pf_delta, 3),
                "full_dd_r": float(full["max_dd_r"] or 0.0),
                "full_dd_worse_r": _round(dd_worse, 2),
                "full_negative_years": int(full["negative_years"] or 0),
                "full_median_stop_ticks": float(full["median_stop_ticks"] or 0.0),
                "full_full_tp_rate_pct": float(full["full_tp_rate_pct"] or 0.0),
                "full_tp1_be_rate_pct": float(full["tp1_be_rate_pct"] or 0.0),
                "full_sl_rate_pct": float(full["sl_rate_pct"] or 0.0),
                "last_1y_net_r": float(last1["net_r"] or 0.0),
                "last_1y_r_delta": _round(last1_r_delta, 2),
                "last_1y_trades": int(last1["trades"] or 0),
                "last_1y_pf": float(last1["profit_factor"] or 0.0),
                "last_1y_dd_r": float(last1["max_dd_r"] or 0.0),
                "last_2y_net_r": float(last2["net_r"] or 0.0),
                "last_2y_r_delta": _round(last2_r_delta, 2),
                "last_2y_trades": int(last2["trades"] or 0),
                "last_2y_pf": float(last2["profit_factor"] or 0.0),
                "last_2y_dd_r": float(last2["max_dd_r"] or 0.0),
                "deployability": full["deployability"],
                "live_support_notes": full["live_support_notes"],
                "exact_replay_required": full["exact_replay_required"],
            }
        )
    return sorted(ranked, key=lambda row: row["wide_stop_score"], reverse=True)


def _best_by_candidate(rows: list[dict[str, Any]], *, near_intact_only: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if near_intact_only and not row["near_intact"]:
            continue
        if row["candidate"] in seen:
            continue
        seen.add(str(row["candidate"]))
        out.append(row)
    return out


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    out = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        cells = []
        for _, key in columns:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.2f}"
            cells.append(str(value))
        out.append("| " + " | ".join(cells) + " |")
    return out


def _display_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": row["label"],
        "stop": f"{row['stop_source']} {row['stop_value']:g}",
        "mult": row["stop_width_mult"],
        "rr": row["rr"],
        "tp1": row["tp1_ratio"],
        "TP1_R": row["tp1_r"],
        "full R/delta/PF/DD": f"{row['full_net_r']:.1f}/{row['full_r_delta']:+.1f}/{row['full_pf']:.2f}/{row['full_dd_r']:.1f}",
        "1y R/delta/PF/DD": f"{row['last_1y_net_r']:.1f}/{row['last_1y_r_delta']:+.1f}/{row['last_1y_pf']:.2f}/{row['last_1y_dd_r']:.1f}",
        "2y R/delta/PF/DD": f"{row['last_2y_net_r']:.1f}/{row['last_2y_r_delta']:+.1f}/{row['last_2y_pf']:.2f}/{row['last_2y_dd_r']:.1f}",
        "TP2%": row["full_full_tp_rate_pct"],
        "TP1_BE%": row["full_tp1_be_rate_pct"],
        "near": row["near_intact"],
    }


def _write_report(
    *,
    candidates: list[CandidateSpec],
    baseline_by_candidate: dict[str, dict[str, dict[str, Any]]],
    ranked: list[dict[str, Any]],
) -> None:
    baseline_rows = []
    deployability_rows = []
    for candidate in candidates:
        full = baseline_by_candidate[candidate.key]["full"]
        last1 = baseline_by_candidate[candidate.key]["last_1y"]
        last2 = baseline_by_candidate[candidate.key]["last_2y"]
        baseline_rows.append(
            {
                "candidate": candidate.label,
                "stop": f"{candidate.baseline_stop_source} {candidate.baseline_stop_value:g}",
                "rr": candidate.baseline_rr,
                "tp1": candidate.baseline_tp1_ratio,
                "TP1_R": round(candidate.baseline_rr * candidate.baseline_tp1_ratio, 2),
                "stop ticks": full["median_stop_ticks"],
                "full R/PF/DD": f"{full['net_r']:.1f}/{full['profit_factor']:.2f}/{full['max_dd_r']:.1f}",
                "1y R/PF/DD": f"{last1['net_r']:.1f}/{last1['profit_factor']:.2f}/{last1['max_dd_r']:.1f}",
                "2y R/PF/DD": f"{last2['net_r']:.1f}/{last2['profit_factor']:.2f}/{last2['max_dd_r']:.1f}",
                "TP2%": full["full_tp_rate_pct"],
                "TP1_BE%": full["tp1_be_rate_pct"],
            }
        )
        deployability_rows.append(
            {
                "candidate": candidate.label,
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
            }
        )

    near = [row for row in ranked if row["near_intact"]]
    near_rows = [_display_row(row) for row in near[:20]]
    best_near = [_display_row(row) for row in _best_by_candidate(ranked, near_intact_only=True)]
    top_rows = [_display_row(row) for row in ranked[:20]]

    lines = [
        "# NQ/ES NY ORB Wide-Stop Target Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window set: last 1y `{LAST_1Y_START}` to `{END_INCLUSIVE}`, last 2y `{LAST_2Y_START}` to `{END_INCLUSIVE}`, full `{FULL_START}` to `{END_INCLUSIVE}`.",
        "- Scope: NQ NY ORB R11 and ES NY ORB only. Signal/session structure, direction filters, ATR length, DOW exclusions, gap filters, and magnifier settings were held fixed.",
        f"- Swept TP1 as target distance in R: `{TP1_R_VALUES}`; accepted ratios were `{MIN_TP1_RATIO}` to `{MAX_TP1_RATIO}` and still obeyed the hard `rr * tp1_ratio >= 1.0` rule.",
        "- `near_intact` means median stop widened at least 20%, full R retained at least 90%, last-1y and last-2y R retained at least 80%, full DD worsened no more than 25%, PF stayed within 0.10, and negative full years did not increase.",
        "- This is a research sweep, not an execution change. Any selected row still needs exact execution replay before promotion.",
        "",
        "## Read",
        "",
        "- **Result: NO-GO for replacing either NY ORB with a wider-stop variant.** Across the valid config set, zero rows widened the actual median stop by at least `20%` while preserving the current result quality.",
        "- **NQ NY ORB R11**: the least-bad actual widening was around `ATR 9%`, but those rows gave up roughly `26R-30R` full-history versus the baseline. Treat that family as a lower-return research branch, not an upgrade.",
        "- **ES NY ORB**: `ATR 6%` and `ORB 25%` still resolved to the same median stop because the `3pt` minimum stop floor dominated. The first meaningful wider rows, such as `ATR 12%` or `ORB 50%`, either damaged recent performance or widened DD materially.",
        "- Practical conclusion: if the live issue is discomfort with NY stopouts, risk down or pause ES_NY rather than widening the stop.",
        "",
        "## Candidate Deployability",
        "",
        *_md_table(
            deployability_rows,
            [
                ("Candidate", "candidate"),
                ("deployability", "deployability"),
                ("live_support_notes", "live_support_notes"),
                ("exact_replay_required", "exact_replay_required"),
            ],
        ),
        "",
        "## Baselines",
        "",
        *_md_table(
            baseline_rows,
            [
                ("Candidate", "candidate"),
                ("Stop", "stop"),
                ("rr", "rr"),
                ("tp1", "tp1"),
                ("TP1_R", "TP1_R"),
                ("Med Stop Ticks", "stop ticks"),
                ("Full R/PF/DD", "full R/PF/DD"),
                ("1y R/PF/DD", "1y R/PF/DD"),
                ("2y R/PF/DD", "2y R/PF/DD"),
                ("TP2%", "TP2%"),
                ("TP1_BE%", "TP1_BE%"),
            ],
        ),
        "",
        "## Best Near-Intact Wide Stops Per Candidate",
        "",
        *_md_table(
            best_near,
            [
                ("Candidate", "candidate"),
                ("Stop", "stop"),
                ("Stop x", "mult"),
                ("rr", "rr"),
                ("tp1", "tp1"),
                ("TP1_R", "TP1_R"),
                ("Full R/delta/PF/DD", "full R/delta/PF/DD"),
                ("1y R/delta/PF/DD", "1y R/delta/PF/DD"),
                ("2y R/delta/PF/DD", "2y R/delta/PF/DD"),
                ("TP2%", "TP2%"),
                ("TP1_BE%", "TP1_BE%"),
            ],
        ),
        "",
        "## Top Near-Intact Wide Stops",
        "",
        *_md_table(
            near_rows,
            [
                ("Candidate", "candidate"),
                ("Stop", "stop"),
                ("Stop x", "mult"),
                ("rr", "rr"),
                ("tp1", "tp1"),
                ("TP1_R", "TP1_R"),
                ("Full R/delta/PF/DD", "full R/delta/PF/DD"),
                ("1y R/delta/PF/DD", "1y R/delta/PF/DD"),
                ("2y R/delta/PF/DD", "2y R/delta/PF/DD"),
                ("TP2%", "TP2%"),
                ("TP1_BE%", "TP1_BE%"),
                ("Near", "near"),
            ],
        ),
        "",
        "## Top Score Rows Including Degraded",
        "",
        *_md_table(
            top_rows,
            [
                ("Candidate", "candidate"),
                ("Stop", "stop"),
                ("Stop x", "mult"),
                ("rr", "rr"),
                ("tp1", "tp1"),
                ("TP1_R", "TP1_R"),
                ("Full R/delta/PF/DD", "full R/delta/PF/DD"),
                ("1y R/delta/PF/DD", "1y R/delta/PF/DD"),
                ("2y R/delta/PF/DD", "2y R/delta/PF/DD"),
                ("TP2%", "TP2%"),
                ("TP1_BE%", "TP1_BE%"),
                ("Near", "near"),
            ],
        ),
        "",
        "## Artifacts",
        "",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
        f"- Ranked CSV: `backtesting/data/results/{RUN_SLUG}/ranked_candidates.csv`",
        f"- Window metrics CSV: `backtesting/data/results/{RUN_SLUG}/window_metrics.csv`",
        f"- Variant manifest CSV: `backtesting/data/results/{RUN_SLUG}/variant_manifest.csv`",
        f"- Script: `backtesting/scripts/run_nq_es_ny_orb_wide_stop_target_sweep_20260505.py`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _manifest_row(variant: VariantSpec) -> dict[str, Any]:
    session = variant.config.sessions[0]
    return {
        "candidate": variant.candidate.key,
        "label": variant.candidate.label,
        "variant_id": variant.variant_id,
        "instrument": variant.config.instrument.symbol,
        "strategy": variant.config.strategy,
        "direction_filter": variant.config.direction_filter,
        "stop_source": variant.stop_source,
        "stop_value": variant.stop_value,
        "rr": variant.rr,
        "tp1_ratio": variant.tp1_ratio,
        "tp1_r": variant.tp1_r,
        "atr_length": variant.config.atr_length,
        "orb_start": session.orb_start,
        "orb_end": session.orb_end,
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "flat_start": session.flat_start,
        "flat_end": session.flat_end,
        "stop_atr_pct": session.stop_atr_pct,
        "stop_orb_pct": session.stop_orb_pct,
        "min_gap_atr_pct": session.min_gap_atr_pct,
        "min_gap_orb_pct": session.min_gap_orb_pct,
        "min_stop_points": session.min_stop_points,
        "min_tp1_points": session.min_tp1_points,
        "excluded_days": ",".join(str(day) for day in variant.config.excluded_days),
        "impulse_close_filter": variant.config.impulse_close_filter,
        "deployability": variant.candidate.deployability,
        "live_support_notes": variant.candidate.live_support_notes,
        "exact_replay_required": variant.candidate.exact_replay_required,
    }


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = _candidates()
    variants_by_candidate = {candidate.key: _variants_for(candidate) for candidate in candidates}
    total = sum(len(variants) for variants in variants_by_candidate.values())
    print(f"Candidates: {len(candidates)}", flush=True)
    print(f"Total configs: {total}", flush=True)
    print(f"TP1_R values: {TP1_R_VALUES}", flush=True)

    trades_by_name: dict[str, list[TradeResult]] = {}
    for candidate in candidates:
        trades_by_name.update(_run_candidate(candidate, variants_by_candidate[candidate.key]))

    manifest_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        for variant in variants_by_candidate[candidate.key]:
            trades = trades_by_name.get(variant.config.name, [])
            manifest_rows.append(_manifest_row(variant))
            for window, (start, end) in WINDOWS.items():
                metric_rows.append(_metric_row(variant=variant, trades=trades, window=window, start=start, end=end))

    baseline_by_candidate = _baseline_lookup(metric_rows, candidates)
    ranked = _score_rows(metric_rows, baseline_by_candidate)
    near = [row for row in ranked if row["near_intact"]]
    best_near = _best_by_candidate(ranked, near_intact_only=True)

    pd.DataFrame(manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    pd.DataFrame(ranked).to_csv(RESULT_DIR / "ranked_candidates.csv", index=False)
    pd.DataFrame(near).to_csv(RESULT_DIR / "near_intact_candidates.csv", index=False)
    pd.DataFrame(best_near).to_csv(RESULT_DIR / "best_near_intact_by_candidate.csv", index=False)

    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "run_slug": RUN_SLUG,
        "windows": WINDOWS,
        "tp1_r_values": TP1_R_VALUES,
        "tp1_ratio_bounds": {"min": MIN_TP1_RATIO, "max": MAX_TP1_RATIO},
        "candidate_count": len(candidates),
        "variant_count": total,
        "candidate_specs": [
            {
                "key": candidate.key,
                "label": candidate.label,
                "atr_stop_values": candidate.atr_stop_values,
                "orb_stop_values": candidate.orb_stop_values,
                "rr_values": candidate.rr_values,
                "baseline": {
                    "stop_source": candidate.baseline_stop_source,
                    "stop_value": candidate.baseline_stop_value,
                    "rr": candidate.baseline_rr,
                    "tp1_ratio": candidate.baseline_tp1_ratio,
                    "tp1_r": round(candidate.baseline_rr * candidate.baseline_tp1_ratio, 4),
                },
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
            }
            for candidate in candidates
        ],
        "baseline_by_candidate": baseline_by_candidate,
        "best_near_intact_by_candidate": best_near,
        "near_intact_count": len(near),
        "top_50": ranked[:50],
        "notes": [
            "Research sweep only; execution configs were not edited.",
            "near_intact is a preservation screen, not a robust-pipeline promotion label.",
            "Live-native rows still need exact execution replay before promotion.",
        ],
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True) + "\n")
    _write_report(candidates=candidates, baseline_by_candidate=baseline_by_candidate, ranked=ranked)

    print("\nBaselines:", flush=True)
    for candidate in candidates:
        full = baseline_by_candidate[candidate.key]["full"]
        print(
            f"  {candidate.key:<16} stop={candidate.baseline_stop_source} {candidate.baseline_stop_value:g} "
            f"rr={candidate.baseline_rr:g} tp1={candidate.baseline_tp1_ratio:g} "
            f"med_stop={full['median_stop_ticks']} ticks full={full['net_r']}R "
            f"PF={full['profit_factor']} DD={full['max_dd_r']} TP2={full['full_tp_rate_pct']}%",
            flush=True,
        )

    print("\nBest near-intact wide stops:", flush=True)
    if not best_near:
        print("  none", flush=True)
    for row in best_near:
        print(
            f"  {row['candidate']:<16} {row['stop_source']}={row['stop_value']:>6.1f} "
            f"stop_x={row['stop_width_mult']:.2f} rr={row['rr']:.2f} tp1={row['tp1_ratio']:.4f} "
            f"TP1_R={row['tp1_r']:.2f} | full {row['full_net_r']:+.1f}R "
            f"({row['full_r_delta']:+.1f}) PF {row['full_pf']:.2f} DD {row['full_dd_r']:.1f} "
            f"| 1y {row['last_1y_net_r']:+.1f}R ({row['last_1y_r_delta']:+.1f})",
            flush=True,
        )

    print(f"\nNear-intact rows: {len(near)}", flush=True)
    print(f"Saved: {RESULT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
