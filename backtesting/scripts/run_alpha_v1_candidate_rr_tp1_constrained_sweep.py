#!/usr/bin/env python3
"""Constrained RR/TP1 sweep for ALPHA_V1 and nearby candidate legs.

This script creates research artifacts only. It does not edit execution configs.

Constraint:
- rr <= 3.0
- 1.0 <= rr * tp1_ratio <= 1.5
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
REPO_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

import run_alpha_v1_hot_regime_ablation as alpha_hot  # noqa: E402
import run_cross_asset_htf_lsi_broad_discovery as cross_htf  # noqa: E402
import run_nq_ny_lsi_cisd_target_sweep as cisd_target  # noqa: E402
import run_nq_ny_lsi_cisd_sequence as cisd_seq  # noqa: E402
from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "alpha_v1_candidate_rr_tp1_constrained_sweep_20260504"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_CANDIDATE_RR_TP1_CONSTRAINED_SWEEP_20260504.md"

FULL_START = "2016-04-17"
END_INCLUSIVE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"

RR_VALUES = (1.5, 2.0, 2.5, 3.0)
TP1_R_VALUES = (1.0, 1.25, 1.5)
WORKERS = 8

WINDOWS = {
    "last_1y": (LAST_1Y_START, END_INCLUSIVE),
    "last_2y": (LAST_2Y_START, END_INCLUSIVE),
    "full": (FULL_START, END_INCLUSIVE),
}


@dataclass(frozen=True)
class CandidateSpec:
    key: str
    label: str
    source_group: str
    data_key: str
    base_config: StrategyConfig
    deployability: str
    live_support_notes: str
    exact_replay_required: str
    inclusion_notes: str


@dataclass(frozen=True)
class VariantSpec:
    candidate: CandidateSpec
    variant_id: str
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


def _target_pairs() -> list[tuple[float, float, float]]:
    pairs: list[tuple[float, float, float]] = []
    for rr in RR_VALUES:
        for tp1_r in TP1_R_VALUES:
            tp1_ratio = round(tp1_r / rr, 6)
            if rr <= 3.0 and 1.0 <= rr * tp1_ratio <= 1.500001:
                pairs.append((rr, tp1_ratio, round(rr * tp1_ratio, 4)))
    return pairs


def _with_target(config: StrategyConfig, *, name: str, rr: float, tp1_ratio: float) -> StrategyConfig:
    return replace(config, name=name, rr=rr, tp1_ratio=tp1_ratio)


def _metric_row(
    *,
    variant: VariantSpec,
    trades: list[TradeResult],
    window: str,
    start: str,
    end_inclusive: str,
) -> dict[str, Any]:
    selected = [trade for trade in trades if start <= trade.date <= end_inclusive]
    metrics = compute_metrics(selected)
    return {
        "candidate": variant.candidate.key,
        "label": variant.candidate.label,
        "source_group": variant.candidate.source_group,
        "variant_id": variant.variant_id,
        "window": window,
        "start": start,
        "end": end_inclusive,
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
        "deployability": variant.candidate.deployability,
        "live_support_notes": variant.candidate.live_support_notes,
        "exact_replay_required": variant.candidate.exact_replay_required,
    }


def _score_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_variant: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metric_rows:
        by_variant.setdefault((str(row["candidate"]), str(row["variant_id"])), []).append(row)

    ranked: list[dict[str, Any]] = []
    for (candidate, variant_id), rows in by_variant.items():
        by_window = {str(row["window"]): row for row in rows}
        if not {"last_1y", "last_2y", "full"} <= set(by_window):
            continue
        last1 = by_window["last_1y"]
        last2 = by_window["last_2y"]
        full = by_window["full"]
        score = (
            3.0 * float(last1["net_r"] or 0.0)
            + 2.0 * float(last2["net_r"] or 0.0)
            + 0.75 * float(full["net_r"] or 0.0)
            - 0.75 * abs(float(last1["max_dd_r"] or 0.0))
            - 0.35 * abs(float(last2["max_dd_r"] or 0.0))
            - 0.10 * abs(float(full["max_dd_r"] or 0.0))
            - 8.0 * int(full["negative_years"] or 0)
        )
        if int(last1["trades"] or 0) < 12:
            score -= 20.0
        ranked.append(
            {
                "candidate": candidate,
                "label": full["label"],
                "source_group": full["source_group"],
                "variant_id": variant_id,
                "rr": float(full["rr"]),
                "tp1_ratio": float(full["tp1_ratio"]),
                "tp1_r": float(full["tp1_r"]),
                "promotion_score": round(score, 3),
                "last_1y_net_r": float(last1["net_r"] or 0.0),
                "last_1y_trades": int(last1["trades"] or 0),
                "last_1y_wr_pct": float(last1["win_rate_pct"] or 0.0),
                "last_1y_pf": float(last1["profit_factor"] or 0.0),
                "last_1y_dd_r": float(last1["max_dd_r"] or 0.0),
                "last_2y_net_r": float(last2["net_r"] or 0.0),
                "last_2y_trades": int(last2["trades"] or 0),
                "last_2y_wr_pct": float(last2["win_rate_pct"] or 0.0),
                "last_2y_pf": float(last2["profit_factor"] or 0.0),
                "last_2y_dd_r": float(last2["max_dd_r"] or 0.0),
                "full_net_r": float(full["net_r"] or 0.0),
                "full_trades": int(full["trades"] or 0),
                "full_wr_pct": float(full["win_rate_pct"] or 0.0),
                "full_pf": float(full["profit_factor"] or 0.0),
                "full_dd_r": float(full["max_dd_r"] or 0.0),
                "full_negative_years": int(full["negative_years"] or 0),
                "deployability": full["deployability"],
                "live_support_notes": full["live_support_notes"],
                "exact_replay_required": full["exact_replay_required"],
            }
        )
    return sorted(ranked, key=lambda row: row["promotion_score"], reverse=True)


def _manifest_row(variant: VariantSpec) -> dict[str, Any]:
    cfg = variant.config
    session = cfg.sessions[0]
    return {
        "candidate": variant.candidate.key,
        "label": variant.candidate.label,
        "source_group": variant.candidate.source_group,
        "variant_id": variant.variant_id,
        "data_key": variant.candidate.data_key,
        "strategy": cfg.strategy,
        "instrument": cfg.instrument.symbol,
        "session": session.name,
        "direction_filter": cfg.direction_filter,
        "rr": variant.rr,
        "tp1_ratio": variant.tp1_ratio,
        "tp1_r": variant.tp1_r,
        "atr_length": cfg.atr_length,
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
        "excluded_days": ",".join(str(day) for day in cfg.excluded_days),
        "impulse_close_filter": cfg.impulse_close_filter,
        "continuation_fvg_selection": cfg.continuation_fvg_selection,
        "orb_trade_max_per_session": cfg.orb_trade_max_per_session,
        "orb_reentry_policy": cfg.orb_reentry_policy,
        "lsi_entry_mode": cfg.lsi_entry_mode,
        "lsi_fvg_window_left": cfg.lsi_fvg_window_left,
        "lsi_fvg_window_right": cfg.lsi_fvg_window_right,
        "max_fvg_to_inversion_bars": cfg.max_fvg_to_inversion_bars,
        "htf_level_tf_minutes": cfg.htf_level_tf_minutes,
        "htf_n_left": cfg.htf_n_left,
        "htf_trade_max_per_session": cfg.htf_trade_max_per_session,
        "deployability": variant.candidate.deployability,
        "live_support_notes": variant.candidate.live_support_notes,
        "exact_replay_required": variant.candidate.exact_replay_required,
        "inclusion_notes": variant.candidate.inclusion_notes,
    }


def _active_alpha_candidates() -> list[CandidateSpec]:
    out: list[CandidateSpec] = []
    for leg in alpha_hot._active_alpha_v1_legs():
        data_key = "NQ_5m" if leg.config.instrument.symbol == "NQ" else "ES_5m"
        out.append(
            CandidateSpec(
                key=leg.key,
                label=leg.label,
                source_group="active_alpha_v1",
                data_key=data_key,
                base_config=leg.config,
                deployability="live_native",
                live_support_notes="Active ALPHA_V1 leg; knobs are supported by research and execution config paths.",
                exact_replay_required="yes",
                inclusion_notes="Current ALPHA_V1 leg from ALPHA_V1.md.",
            )
        )
    return out


def _extra_orb_candidates() -> list[CandidateSpec]:
    nq_ny_r11 = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:50",
                entry_start="09:50",
                entry_end="12:00",
                flat_start="15:30",
                flat_end="16:00",
                stop_atr_pct=7.0,
                min_gap_atr_pct=2.5,
            ),
        ),
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
        name="candidate_nq_ny_orb_r11",
    )
    nq_ny_short_v2 = StrategyConfig(
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:55",
                entry_start="09:55",
                entry_end="11:00",
                flat_start="11:00",
                flat_end="16:00",
                stop_orb_pct=17.0,
                min_gap_orb_pct=5.0,
                min_stop_points=10.0,
                min_tp1_points=10.0,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=14,
        excluded_days=(0,),
        name="candidate_nq_ny_short_v2",
    )
    es_asia_b = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="23:15",
                flat_start="04:00",
                flat_end="07:00",
                stop_atr_pct=12.0,
                min_gap_atr_pct=1.0,
                min_stop_points=3.0,
                min_tp1_points=3.0,
            ),
        ),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=14,
        name="candidate_es_asia_b_ungated",
    )
    return [
        CandidateSpec(
            key="nq_ny_orb_r11",
            label="NQ NY ORB R11 conditional long",
            source_group="conditional_candidate",
            data_key="NQ_5m",
            base_config=nq_ny_r11,
            deployability="live_native",
            live_support_notes="Standard ORB continuation fields; not currently in execution/config but supported by engine knobs.",
            exact_replay_required="yes",
            inclusion_notes="NQ detailed history marks R11 conditional with 4/5 pipeline phases passed.",
        ),
        CandidateSpec(
            key="nq_ny_short_v2",
            label="NQ NY ORB short v2 conditional",
            source_group="conditional_candidate",
            data_key="NQ_5m",
            base_config=nq_ny_short_v2,
            deployability="live_native",
            live_support_notes="Standard ORB continuation fields, short-only, ORB stop and dual floors.",
            exact_replay_required="yes",
            inclusion_notes="Included as a low-frequency diversifier; known annual-R bottleneck.",
        ),
        CandidateSpec(
            key="es_asia_b_ungated",
            label="ES Asia-B ORB ungated",
            source_group="conditional_candidate",
            data_key="ES_5m",
            base_config=es_asia_b,
            deployability="live_native",
            live_support_notes="Standard ORB continuation fields; no regime gate required for the preferred branch.",
            exact_replay_required="yes",
            inclusion_notes="ES detailed history marks Asia-B STRONG and paper-trading consideration.",
        ),
    ]


def _es_htf_candidate() -> CandidateSpec:
    cfg = cross_htf.build_config(
        symbol="ES",
        timeframe="3m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start="08:30",
        entry_end="14:00",
        rr=2.5,
        tp1_ratio=0.5,
        min_gap_atr_pct=3.0,
        atr_length=14,
        htf_level_tf_minutes=90,
        htf_n_left=3,
        htf_trade_max_per_session=2,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=3,
        max_fvg_to_inversion_bars=0,
        min_stop_points=3.0,
        min_tp1_points=3.0,
        name="candidate_es_ny_htf_lsi_balanced_lag0_gap3",
    )
    return CandidateSpec(
        key="es_ny_htf_lsi_balanced_lag0_gap3",
        label="ES NY HTF-LSI balanced lag0 gap3",
        source_group="conditional_research",
        data_key="ES_3m",
        base_config=cfg,
        deployability="research_only",
        live_support_notes="Research HTF-LSI branch; execution support/parity not established and opened holdout was weak.",
        exact_replay_required="yes",
        inclusion_notes="Included because it is the best ES HTF-LSI restart branch, but it is not promotion-clean.",
    )


def _cisd_candidates() -> list[CandidateSpec]:
    candidates: list[CandidateSpec] = []
    for base in cisd_target.base_variants():
        if base.key not in {
            "add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530",
            "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200",
        }:
            continue
        key = "nq_ny_cisd_additive_no_thu" if "add_1m" in base.key else "nq_ny_pure_cisd_long_noon"
        candidates.append(
            CandidateSpec(
                key=key,
                label=base.label,
                source_group="conditional_research",
                data_key="NQ_1m",
                base_config=base.config,
                deployability="live_native",
                live_support_notes=(
                    "Simulator-native LSI/CISD fields; requires execution implementation/parity "
                    "before deployment."
                ),
                exact_replay_required="yes",
                inclusion_notes="NQ CISD restricted finalist from 2026-05-03; target-only retest under stricter RR cap.",
            )
        )
    return candidates


def _all_candidates() -> list[CandidateSpec]:
    return [
        *_active_alpha_candidates(),
        *_extra_orb_candidates(),
        _es_htf_candidate(),
        *_cisd_candidates(),
    ]


def _variants_for(candidate: CandidateSpec) -> list[VariantSpec]:
    variants: list[VariantSpec] = []
    for rr, tp1_ratio, tp1_r in _target_pairs():
        variant_id = f"rr{_fmt_float(rr)}__tp1r{_fmt_float(tp1_r)}"
        name = f"{candidate.key}__{variant_id}"
        try:
            cfg = _with_target(candidate.base_config, name=name, rr=rr, tp1_ratio=tp1_ratio)
        except ValueError as exc:
            print(f"  skip {name}: {exc}", flush=True)
            continue
        variants.append(
            VariantSpec(
                candidate=candidate,
                variant_id=variant_id,
                rr=rr,
                tp1_ratio=tp1_ratio,
                tp1_r=tp1_r,
                config=cfg,
            )
        )
    return variants


def _load_data_by_key() -> dict[str, dict[str, Any]]:
    print("Loading market data...", flush=True)
    nq = alpha_hot._load_data(NQ)
    es = alpha_hot._load_data(ES)
    es_3m, es_1m, es_1s, es_signal = cross_htf.load_timeframe_data("ES", "3m")
    cisd_data = cisd_seq.load_timeframes()
    return {
        "NQ_5m": {"df": nq.df_5m, "df_1m": nq.df_1m, "df_1s": nq.df_1s, "signal_df_1m": nq.signal_df_1m},
        "ES_5m": {"df": es.df_5m, "df_1m": es.df_1m, "df_1s": es.df_1s, "signal_df_1m": es.signal_df_1m},
        "ES_3m": {"df": es_3m, "df_1m": es_1m, "df_1s": es_1s, "signal_df_1m": es_signal},
        "NQ_1m": {"df": cisd_data["1m"], "df_1m": None, "df_1s": None, "signal_df_1m": cisd_data["1m"]},
    }


def _run_group(data_key: str, variants: list[VariantSpec], loaded: dict[str, Any]) -> dict[str, list[TradeResult]]:
    if not variants:
        return {}
    print(f"Running {data_key}: {len(variants)} configs", flush=True)

    def progress(done: int, total: int) -> None:
        if done == total or done % 20 == 0:
            print(f"  {data_key}: {done}/{total}", flush=True)

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
    by_name: dict[str, VariantSpec] = {variant.config.name: variant for variant in variants}
    trades_by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        variant = by_name[config.name]
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        trades_by_name[variant.config.name] = [
            trade for trade in sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))
            if trade.exit_type != EXIT_NO_FILL
        ]
    return trades_by_name


def _best_by_candidate(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in ranked:
        if row["candidate"] in seen:
            continue
        seen.add(str(row["candidate"]))
        out.append(row)
    return out


def _md_table(rows: list[dict[str, Any]], cols: list[tuple[str, str]]) -> list[str]:
    lines = [
        "| " + " | ".join(label for label, _ in cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for row in rows:
        vals = []
        for _, key in cols:
            value = row.get(key, "")
            if isinstance(value, float):
                value = f"{value:.2f}"
            vals.append(str(value))
        lines.append("| " + " | ".join(vals) + " |")
    return lines


def _write_report(
    *,
    candidates: list[CandidateSpec],
    ranked: list[dict[str, Any]],
    manifest_rows: list[dict[str, Any]],
) -> None:
    best = _best_by_candidate(ranked)
    by_key = {candidate.key: candidate for candidate in candidates}

    report_rows = []
    for idx, row in enumerate(best, start=1):
        report_rows.append(
            {
                "rank": idx,
                "candidate": row["label"],
                "group": row["source_group"],
                "rr": row["rr"],
                "tp1_ratio": row["tp1_ratio"],
                "TP1_R": row["tp1_r"],
                "1y R/tr/PF/DD": f"{row['last_1y_net_r']:.1f}/{row['last_1y_trades']}/{row['last_1y_pf']:.2f}/{row['last_1y_dd_r']:.1f}",
                "2y R/tr/PF/DD": f"{row['last_2y_net_r']:.1f}/{row['last_2y_trades']}/{row['last_2y_pf']:.2f}/{row['last_2y_dd_r']:.1f}",
                "full R/tr/PF/DD": f"{row['full_net_r']:.1f}/{row['full_trades']}/{row['full_pf']:.2f}/{row['full_dd_r']:.1f}",
                "WR 1y/full": f"{row['last_1y_wr_pct']:.1f}%/{row['full_wr_pct']:.1f}%",
                "deployability": row["deployability"],
                "exact": row["exact_replay_required"],
            }
        )

    active = [row for row in best if row["source_group"] == "active_alpha_v1"]
    conditionals = [row for row in best if row["source_group"] != "active_alpha_v1"]

    lines = [
        "# ALPHA_V1 Candidate RR/TP1 Constrained Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window set: last 1y `{LAST_1Y_START}` to `{END_INCLUSIVE}`, last 2y `{LAST_2Y_START}` to `{END_INCLUSIVE}`, full `{FULL_START}` to `{END_INCLUSIVE}`.",
        f"- Constraint: `rr <= 3.0` and `1.0 <= rr * tp1_ratio <= 1.5`.",
        f"- Target menu: `{[(rr, tp1, tp1r) for rr, tp1, tp1r in _target_pairs()]}`.",
        "- Method: broad research replay with 1s/1m magnifier data where the research configs require it. Execution configs were not edited.",
        "- Exact replay posture: live-native rows are exact-replay candidates, but this packet is the research shortlist stage. Use the exact execution state machines before promoting any live config.",
        "",
        "## Candidate Set",
        "",
        *_md_table(
            [
                {
                    "candidate": candidate.label,
                    "key": candidate.key,
                    "group": candidate.source_group,
                    "deployability": candidate.deployability,
                    "exact": candidate.exact_replay_required,
                    "notes": candidate.inclusion_notes,
                }
                for candidate in candidates
            ],
            [
                ("Candidate", "candidate"),
                ("Key", "key"),
                ("Group", "group"),
                ("Deployability", "deployability"),
                ("Exact replay required", "exact"),
                ("Inclusion notes", "notes"),
            ],
        ),
        "",
        "## Top Ranked Candidate Per Leg",
        "",
        *_md_table(
            report_rows,
            [
                ("Rank", "rank"),
                ("Candidate", "candidate"),
                ("Group", "group"),
                ("rr", "rr"),
                ("tp1_ratio", "tp1_ratio"),
                ("TP1_R", "TP1_R"),
                ("1y R/tr/PF/DD", "1y R/tr/PF/DD"),
                ("2y R/tr/PF/DD", "2y R/tr/PF/DD"),
                ("full R/tr/PF/DD", "full R/tr/PF/DD"),
                ("WR 1y/full", "WR 1y/full"),
                ("Deployability", "deployability"),
                ("Exact", "exact"),
            ],
        ),
        "",
        "## Active ALPHA_V1 Read",
        "",
    ]

    for row in active:
        current = by_key[str(row["candidate"])].base_config
        lines.append(
            f"- **{row['label']}**: best constrained row is `rr={row['rr']:.2f}`, "
            f"`tp1_ratio={row['tp1_ratio']:.4f}` (`TP1_R={row['tp1_r']:.2f}`), versus current "
            f"`rr={current.rr}`, `tp1_ratio={current.tp1_ratio}`. Last-1y `{row['last_1y_net_r']:.1f}R`, "
            f"last-2y `{row['last_2y_net_r']:.1f}R`, full `{row['full_net_r']:.1f}R`."
        )

    lines.extend(["", "## Conditional Promotion Read", ""])
    for row in conditionals:
        lines.append(
            f"- **{row['label']}**: best constrained row `rr={row['rr']:.2f}`, "
            f"`tp1_ratio={row['tp1_ratio']:.4f}` (`TP1_R={row['tp1_r']:.2f}`), "
            f"last-1y `{row['last_1y_net_r']:.1f}R` on `{row['last_1y_trades']}` trades, "
            f"last-2y `{row['last_2y_net_r']:.1f}R`, full `{row['full_net_r']:.1f}R`; "
            f"deployability `{row['deployability']}`. {row['live_support_notes']}"
        )

    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            "- Promote only after exact replay: the strongest live-native research rows are candidates for exact execution replay, not direct config edits.",
            "- The constrained menu is most useful when it preserves or improves recent R without creating a large full-history DD tax. Rows with strong 1y but weak full-history labels should stay as hot-regime/watchlist ideas.",
            "- Ignore/reject any branch whose best constrained row remains weak in the last 1y or requires research-only support; it does not improve ALPHA_V1 promotion usefulness from this target sweep alone.",
            "",
            "## Artifacts",
            "",
            f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
            f"- Ranked rows CSV: `backtesting/data/results/{RUN_SLUG}/ranked_candidates.csv`",
            f"- Window metrics CSV: `backtesting/data/results/{RUN_SLUG}/window_metrics.csv`",
            f"- Variant manifest CSV: `backtesting/data/results/{RUN_SLUG}/variant_manifest.csv`",
            f"- Script: `backtesting/scripts/run_alpha_v1_candidate_rr_tp1_constrained_sweep.py`",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = _all_candidates()
    variants = [variant for candidate in candidates for variant in _variants_for(candidate)]
    print(f"Candidate legs: {len(candidates)}", flush=True)
    print(f"Target pairs per leg: {len(_target_pairs())}", flush=True)
    print(f"Total configs: {len(variants)}", flush=True)

    loaded_by_key = _load_data_by_key()
    variants_by_data: dict[str, list[VariantSpec]] = {}
    for variant in variants:
        variants_by_data.setdefault(variant.candidate.data_key, []).append(variant)

    trades_by_name: dict[str, list[TradeResult]] = {}
    for data_key, group_variants in variants_by_data.items():
        trades_by_name.update(_run_group(data_key, group_variants, loaded_by_key[data_key]))

    metric_rows: list[dict[str, Any]] = []
    manifest_rows: list[dict[str, Any]] = []
    for variant in variants:
        trades = trades_by_name.get(variant.config.name, [])
        manifest_rows.append(_manifest_row(variant))
        for window, (start, end) in WINDOWS.items():
            metric_rows.append(_metric_row(variant=variant, trades=trades, window=window, start=start, end_inclusive=end))

    ranked = _score_rows(metric_rows)
    best = _best_by_candidate(ranked)

    pd.DataFrame(manifest_rows).to_csv(RESULT_DIR / "variant_manifest.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    pd.DataFrame(ranked).to_csv(RESULT_DIR / "ranked_candidates.csv", index=False)
    pd.DataFrame(best).to_csv(RESULT_DIR / "best_by_candidate.csv", index=False)

    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "run_slug": RUN_SLUG,
        "constraint": {
            "rr_max": 3.0,
            "tp1_r_min": 1.0,
            "tp1_r_max": 1.5,
            "target_pairs": [{"rr": rr, "tp1_ratio": tp1, "tp1_r": tp1r} for rr, tp1, tp1r in _target_pairs()],
        },
        "windows": WINDOWS,
        "candidates": [
            {
                "key": candidate.key,
                "label": candidate.label,
                "source_group": candidate.source_group,
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
                "inclusion_notes": candidate.inclusion_notes,
            }
            for candidate in candidates
        ],
        "best_by_candidate": best,
        "top_25": ranked[:25],
        "notes": [
            "Research sweep only; execution configs were not edited.",
            "Live-native candidates still require exact execution replay before promotion.",
            "ES HTF-LSI balanced branch is included for completeness but remains research_only after weak opened holdout.",
        ],
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True) + "\n")
    _write_report(candidates=candidates, ranked=ranked, manifest_rows=manifest_rows)

    print("\nBest by candidate:", flush=True)
    for row in best:
        print(
            f"  {row['candidate']:<36} rr={row['rr']:.2f} tp1={row['tp1_ratio']:.4f} "
            f"TP1_R={row['tp1_r']:.2f} | 1y {row['last_1y_net_r']:+.1f}R "
            f"2y {row['last_2y_net_r']:+.1f}R full {row['full_net_r']:+.1f}R",
            flush=True,
        )
    print(f"\nSaved: {RESULT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
