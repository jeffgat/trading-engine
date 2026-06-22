"""Native deterministic tools for agentic discovery workflows."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

import numpy as np

from ..config import (
    ASIA_SESSION,
    LDN_SESSION,
    NY_SESSION,
    SessionConfig,
    StrategyConfig,
    default_config,
    ib_config,
    with_overrides,
)
from ..data.instruments import get_instrument
from ..data.loader import load_1m_for_5m, load_30s_for_5m, load_1s_for_5m, load_5m_data
from ..engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult, run_backtest
from ..errors import BacktestError
from ..optimize.grid import generate_param_grid
from ..optimize.objectives import VALID_OBJECTIVES, get_objective_value
from ..optimize.parallel import run_sweep
from ..optimize.stability import analyze_parameter_stability
from ..optimize.walkforward import run_walkforward
from ..results.export import results_to_dict
from ..results.metrics import compute_metrics
from ..validate.deflated_sharpe import compute_dsr, compute_psr, estimate_effective_trials
from .manifest import CandidateSpec, DiscoveryRunManifest, to_jsonable


NATIVE_PHASES = frozenset(
    {
        "structural_screen",
        "discovery_search",
        "walk_forward",
        "stability_check",
        "overfit_audit",
        "phase_one_handoff",
        "learnings_update",
    }
)

_SESSION_MAP = {
    "NY": NY_SESSION,
    "NEW_YORK": NY_SESSION,
    "NEWYORK": NY_SESSION,
    "ASIA": ASIA_SESSION,
    "LDN": LDN_SESSION,
    "LONDON": LDN_SESSION,
}
_STRATEGY_FIELDS = {field.name for field in fields(StrategyConfig)}
_SESSION_FIELDS = {field.name for field in fields(SessionConfig)}
_KNOWN_STRATEGIES = {
    "continuation",
    "reversal",
    "orb_breakout",
    "inversion",
    "cisd",
    "lsi",
    "htf_lsi",
    "reference_lsi",
    "ib",
}
_IGNORED_BASE_KEYS = {
    "data_file",
    "data_1m_file",
    "data_30s_file",
    "data_1s_file",
    "load_1m",
    "load_30s",
    "load_1s",
    "sessions",
    "search_space",
    "overrides",
    "template",
    "deployability",
    "live_support_notes",
    "post_filters",
    "research_only",
    "phase_one_command",
}
_TUPLE_FIELDS = {
    "half_days",
    "excluded_dates",
    "excluded_days",
    "data_sweep_event_types",
    "htf_lsi_reference_levels",
    "ref_lsi_reference_levels",
}


@dataclass(frozen=True)
class NativePhaseOutcome:
    """Result returned by one native discovery phase."""

    decision: str
    rationale: str
    payload: dict[str, Any]


class DiscoveryToolError(BacktestError):
    """Structured error raised by native discovery tools."""


def tool_error(code: str, reason: str, fix: str) -> DiscoveryToolError:
    return DiscoveryToolError(code=code, reason=reason, fix=fix)


def run_native_phase(
    phase_id: str,
    manifest: DiscoveryRunManifest,
    *,
    repo_root: str | Path,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Dispatch a native phase by id."""
    if phase_id == "structural_screen":
        return run_structural_screen(manifest, repo_root=repo_root, output_dir=output_dir)
    if phase_id == "discovery_search":
        return run_discovery_search(manifest, repo_root=repo_root, output_dir=output_dir)
    if phase_id == "walk_forward":
        return run_walk_forward(manifest, repo_root=repo_root, output_dir=output_dir)
    if phase_id == "stability_check":
        return run_stability_check(manifest, output_dir=output_dir)
    if phase_id == "overfit_audit":
        return run_overfit_audit(manifest, output_dir=output_dir)
    if phase_id == "phase_one_handoff":
        return run_phase_one_handoff(manifest, output_dir=output_dir)
    if phase_id == "learnings_update":
        return run_learnings_update(manifest, output_dir=output_dir)
    raise tool_error(
        "UNKNOWN_NATIVE_DISCOVERY_PHASE",
        f"No native discovery tool exists for phase {phase_id!r}.",
        "Use a phase id listed in NATIVE_PHASES or configure phase.command.",
    )


def run_structural_screen(
    manifest: DiscoveryRunManifest,
    *,
    repo_root: str | Path,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Run the base strategy on the pre-holdout window and seed a candidate."""
    base = build_strategy_config(manifest)
    data_file, df, df_1m, df_30s, df_1s = load_discovery_data(
        manifest,
        repo_root=repo_root,
        start=manifest.data.start,
        end=manifest.data.pre_holdout_end,
    )
    trades = run_backtest(
        df,
        base,
        start_date=manifest.data.start,
        end_date=manifest.data.pre_holdout_end,
        df_1m=df_1m,
        signal_df_1m=df_1m,
        df_30s=df_30s,
        df_1s=df_1s,
    )
    mfe_df = df_1m if df_1m is not None else df
    result = _result_payload(trades, base, mfe_df=mfe_df)
    objective = _objective_name(manifest)
    objective_value = get_objective_value(result["summary"], objective, base.risk_usd)
    candidate = _candidate_from_run(
        manifest,
        prefix="struct",
        label="Structural baseline",
        config=base,
        params=_extract_params(base, _param_ranges(manifest).keys()),
        metrics=result["summary"],
        trades=trades,
        source_phase="structural_screen",
        objective=objective,
        objective_value=objective_value,
        selection_rank=1,
    )
    _upsert_candidate(manifest, candidate)
    detail = {
        "data_file": data_file,
        "data_rows": len(df),
        "start": manifest.data.start,
        "end": manifest.data.pre_holdout_end,
        "objective": objective,
        "objective_value": objective_value,
        "result": result,
        "candidate_id": candidate.id,
    }
    detail_path = _write_detail(output_dir, "structural_screen", detail)
    total_trades = result["summary"].get("total_trades", 0)
    total_r = result["summary"].get("total_r", 0.0)
    decision = "passed" if total_trades > 0 and total_r > 0 else "needs_revision"
    return NativePhaseOutcome(
        decision=decision,
        rationale="Base strategy was evaluated on pre-holdout data without saving to the experiment DB.",
        payload={
            "detail_path": str(detail_path),
            "candidate_id": candidate.id,
            "summary": result["summary"],
        },
    )


def run_discovery_search(
    manifest: DiscoveryRunManifest,
    *,
    repo_root: str | Path,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Run a bounded pre-holdout parameter search and update the shortlist."""
    param_ranges = _param_ranges(manifest)
    if not param_ranges:
        detail = {
            "param_ranges": {},
            "total_trials_planned": 1,
            "total_trials_run": 1,
            "all_results": [],
            "shortlist": [candidate.id for candidate in manifest.candidates],
        }
        detail_path = _write_detail(output_dir, "discovery_search", detail)
        return NativePhaseOutcome(
            decision="base_only",
            rationale="No search_budget.param_ranges configured; structural baseline remains the candidate pool.",
            payload={"detail_path": str(detail_path), "total_trials_run": 1},
        )

    base = build_strategy_config(manifest)
    configs = generate_param_grid(base, param_ranges)
    max_trials = int(manifest.search_budget.get("max_trials", len(configs)))
    truncated = len(configs) > max_trials
    configs = configs[:max_trials]
    data_file, df, df_1m, df_30s, df_1s = load_discovery_data(
        manifest,
        repo_root=repo_root,
        start=manifest.data.start,
        end=manifest.data.pre_holdout_end,
    )
    n_workers = int(manifest.search_budget.get("n_workers", 1))
    results = run_sweep(
        df,
        configs,
        n_workers=n_workers,
        start_date=manifest.data.start,
        end_date=manifest.data.pre_holdout_end,
        df_1m=df_1m,
        signal_df_1m=df_1m,
        df_30s=df_30s,
        df_1s=df_1s,
    )
    objective = _objective_name(manifest)
    rows = []
    mfe_df = df_1m if df_1m is not None else df
    for config, trades in results:
        metrics = compute_metrics(trades)
        mfe = _mfe_diagnostics(trades, mfe_df, config)
        metrics["mfe"] = mfe["summary"]
        params = _extract_params(config, param_ranges.keys())
        rows.append(
            {
                "candidate_id": _candidate_id("cand", params or _config_summary(config)),
                "params": params,
                "config": _config_summary(config),
                "metrics": _public_metrics(metrics),
                "objective_value": _finite_float(get_objective_value(metrics, objective, config.risk_usd)),
                "r_multiples": _r_multiples(trades),
                "trade_dates": _trade_dates(trades),
                "mfe_trades": mfe["trades"],
            }
        )
    rows.sort(key=lambda row: row["objective_value"], reverse=True)

    min_trades = int(manifest.search_budget.get("min_trades", 1))
    top_n = int(manifest.search_budget.get("top_n", manifest.gates.max_promoted_candidates))
    eligible_rows = [row for row in rows if row["metrics"].get("total_trades", 0) >= min_trades]
    shortlist = eligible_rows[:top_n] if eligible_rows else rows[:top_n]
    for rank, row in enumerate(shortlist, start=1):
        row["selection_rank"] = rank
        candidate = CandidateSpec(
            id=row["candidate_id"],
            label=f"Discovery candidate {rank}",
            verdict="PENDING",
            params=dict(row["params"]),
            config=dict(row["config"]),
            metrics={
                **dict(row["metrics"]),
                "objective": objective,
                "objective_value": row["objective_value"],
                "selection_rank": rank,
                "r_multiples": list(row["r_multiples"]),
                "trade_dates": list(row["trade_dates"]),
            },
            source_phase="discovery_search",
            exact_replay_required=True,
        )
        _upsert_candidate(manifest, candidate)

    detail = {
        "data_file": data_file,
        "data_rows": len(df),
        "param_ranges": param_ranges,
        "objective": objective,
        "total_trials_planned": len(generate_param_grid(base, param_ranges)),
        "total_trials_run": len(configs),
        "truncated_by_max_trials": truncated,
        "min_trades": min_trades,
        "top_n": top_n,
        "all_results": rows,
        "shortlist": [row["candidate_id"] for row in shortlist],
    }
    detail_path = _write_detail(output_dir, "discovery_search", detail)
    return NativePhaseOutcome(
        decision="shortlisted" if shortlist else "no_candidates",
        rationale="Pre-holdout search completed with explicit raw trial tracking.",
        payload={
            "detail_path": str(detail_path),
            "total_trials_run": len(configs),
            "shortlist": [row["candidate_id"] for row in shortlist],
            "best_objective_value": rows[0]["objective_value"] if rows else None,
        },
    )


def run_walk_forward(
    manifest: DiscoveryRunManifest,
    *,
    repo_root: str | Path,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Run rolling walk-forward optimization when a search space is configured."""
    settings = dict(manifest.search_budget.get("walk_forward", {}) or {})
    if settings.get("enabled") is False:
        detail_path = _write_detail(output_dir, "walk_forward", {"enabled": False})
        return NativePhaseOutcome(
            decision="disabled",
            rationale="search_budget.walk_forward.enabled is false.",
            payload={"detail_path": str(detail_path)},
        )
    param_ranges = _param_ranges(manifest)
    if not param_ranges:
        detail_path = _write_detail(output_dir, "walk_forward", {"param_ranges": {}})
        return NativePhaseOutcome(
            decision="skipped_no_search_space",
            rationale="Walk-forward requires search_budget.param_ranges.",
            payload={"detail_path": str(detail_path)},
        )

    base = build_strategy_config(manifest)
    data_file, df, df_1m, df_30s, df_1s = load_discovery_data(
        manifest,
        repo_root=repo_root,
        start=manifest.data.start,
        end=manifest.data.pre_holdout_end,
    )
    objective = _objective_name(manifest)
    try:
        wf_result = run_walkforward(
            df,
            base,
            param_ranges,
            is_months=int(settings.get("is_months", 12)),
            oos_months=int(settings.get("oos_months", 3)),
            step_months=int(settings.get("step_months", settings.get("oos_months", 3))),
            anchored=bool(settings.get("anchored", False)),
            objective=objective,
            n_workers=int(settings.get("n_workers", manifest.search_budget.get("n_workers", 1))),
            start_date=manifest.data.start,
            df_1m=df_1m,
            signal_df_1m=df_1m,
            df_30s=df_30s,
            df_1s=df_1s,
        )
    except ValueError as exc:
        detail_path = _write_detail(
            output_dir,
            "walk_forward",
            {
                "data_file": data_file,
                "param_ranges": param_ranges,
                "error": str(exc),
            },
        )
        return NativePhaseOutcome(
            decision="skipped_no_valid_folds",
            rationale=str(exc),
            payload={"detail_path": str(detail_path)},
        )

    stability = analyze_parameter_stability(wf_result, param_ranges)
    consensus_params = {param.name: param.mode for param in stability.params}
    consensus_config = with_overrides(base, **consensus_params) if consensus_params else base
    metrics = dict(wf_result.combined_oos_metrics)
    mfe_df = df_1m if df_1m is not None else df
    mfe = _mfe_diagnostics(wf_result.combined_oos_trades, mfe_df, consensus_config)
    metrics["mfe"] = mfe["summary"]
    candidate = _candidate_from_run(
        manifest,
        prefix="wf",
        label="Walk-forward consensus",
        config=consensus_config,
        params=consensus_params,
        metrics=metrics,
        trades=wf_result.combined_oos_trades,
        source_phase="walk_forward",
        objective=objective,
        objective_value=get_objective_value(metrics, objective, consensus_config.risk_usd),
        selection_rank=1,
    )
    candidate.metrics["walk_forward_efficiency"] = _finite_float(wf_result.walk_forward_efficiency)
    candidate.metrics["stability_score"] = _finite_float(stability.overall_score)
    candidate.metrics["stability_interpretation"] = stability.interpretation
    _upsert_candidate(manifest, candidate)

    detail = {
        "data_file": data_file,
        "param_ranges": param_ranges,
        "objective": objective,
        "settings": settings,
        "folds": [
            {
                "fold_index": fold.fold_index,
                "is_start": fold.is_start,
                "is_end": fold.is_end,
                "oos_start": fold.oos_start,
                "oos_end": fold.oos_end,
                "best_params": fold.best_params,
                "is_metrics": _public_metrics(fold.is_metrics),
                "is_objective_value": _finite_float(fold.is_objective_value),
                "oos_metrics": _public_metrics(fold.oos_metrics),
                "oos_objective_value": _finite_float(fold.oos_objective_value),
            }
            for fold in wf_result.folds
        ],
        "combined_oos_metrics": _public_metrics(metrics),
        "mfe_trades": mfe["trades"],
        "walk_forward_efficiency": _finite_float(wf_result.walk_forward_efficiency),
        "stability": _stability_payload(stability),
        "consensus_candidate_id": candidate.id,
    }
    detail_path = _write_detail(output_dir, "walk_forward", detail)
    return NativePhaseOutcome(
        decision="ranked",
        rationale="Rolling walk-forward completed on pre-holdout data.",
        payload={
            "detail_path": str(detail_path),
            "fold_count": len(wf_result.folds),
            "combined_oos_metrics": _public_metrics(metrics),
            "consensus_candidate_id": candidate.id,
        },
    )


def run_stability_check(
    manifest: DiscoveryRunManifest,
    *,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Score local plateau behavior and walk-forward parameter stability."""
    search_detail = _read_detail(output_dir, "discovery_search")
    wf_detail = _read_detail(output_dir, "walk_forward")
    param_ranges = _param_ranges(manifest)
    min_plateau_score = float(manifest.search_budget.get("min_plateau_score", 0.4))
    objective_floor_ratio = float(manifest.search_budget.get("objective_floor_ratio", 0.8))
    rows = []

    if search_detail and search_detail.get("all_results"):
        plateau_scores = _local_plateau_scores(
            search_detail["all_results"],
            param_ranges,
            objective_floor_ratio=objective_floor_ratio,
        )
        plateau_scores_by_params = {
            _params_key(row.get("params", {}), param_ranges.keys()): plateau_scores[str(row["candidate_id"])]
            for row in search_detail["all_results"]
            if row.get("candidate_id") and str(row["candidate_id"]) in plateau_scores
        }
        for candidate in manifest.candidates:
            score = plateau_scores.get(candidate.id)
            if score is None and candidate.params:
                score = plateau_scores_by_params.get(_params_key(candidate.params, param_ranges.keys()))
            if score is None:
                continue
            candidate.metrics["plateau_score"] = score
            candidate.metrics["stability_passed"] = score >= min_plateau_score
            if score < min_plateau_score:
                candidate.verdict = "REJECT"
                candidate.notes = "Rejected by local plateau check."
            rows.append(
                {
                    "candidate_id": candidate.id,
                    "plateau_score": score,
                    "stability_passed": candidate.metrics["stability_passed"],
                }
            )

    if wf_detail and wf_detail.get("stability"):
        stability = wf_detail["stability"]
        consensus_id = wf_detail.get("consensus_candidate_id")
        for candidate in manifest.candidates:
            if candidate.id != consensus_id:
                continue
            score = float(stability.get("overall_score", 0.0))
            candidate.metrics["stability_score"] = score
            candidate.metrics["stability_interpretation"] = stability.get("interpretation")
            candidate.metrics["stability_passed"] = score >= min_plateau_score
            if score < min_plateau_score:
                candidate.verdict = "REJECT"
                candidate.notes = "Rejected by walk-forward parameter stability check."
            rows.append(
                {
                    "candidate_id": candidate.id,
                    "walk_forward_stability_score": score,
                    "interpretation": stability.get("interpretation"),
                    "stability_passed": candidate.metrics["stability_passed"],
                }
            )

    if not rows and manifest.candidates:
        for candidate in manifest.candidates:
            candidate.metrics.setdefault("plateau_score", 1.0)
            candidate.metrics.setdefault("stability_passed", True)
            rows.append(
                {
                    "candidate_id": candidate.id,
                    "plateau_score": candidate.metrics["plateau_score"],
                    "stability_passed": True,
                }
            )

    detail = {
        "min_plateau_score": min_plateau_score,
        "objective_floor_ratio": objective_floor_ratio,
        "candidates": rows,
    }
    detail_path = _write_detail(output_dir, "stability_check", detail)
    return NativePhaseOutcome(
        decision="passed" if any(row.get("stability_passed") for row in rows) else "no_stable_candidates",
        rationale="Candidates were checked for local plateau behavior and available walk-forward stability.",
        payload={"detail_path": str(detail_path), "candidates": rows},
    )


def run_overfit_audit(
    manifest: DiscoveryRunManifest,
    *,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Compute PSR/DSR, estimate effective trials, and finalize promotion verdicts."""
    search_detail = _read_detail(output_dir, "discovery_search")
    all_trade_date_sets = _trade_date_sets_from_detail(search_detail)
    n_trials_raw = int(
        (search_detail or {}).get(
            "total_trials_run",
            manifest.search_budget.get("total_trials_run", max(len(manifest.candidates), 1)),
        )
    )
    n_trials_effective = (
        estimate_effective_trials(all_trade_date_sets)
        if all_trade_date_sets
        else max(len(manifest.candidates), 1)
    )
    min_trades = int(manifest.search_budget.get("min_trades", 1))
    audited = []
    eligible: list[CandidateSpec] = []

    for candidate in sorted(manifest.candidates, key=_candidate_sort_key):
        r_multiples = np.asarray(candidate.metrics.get("r_multiples", []), dtype=float)
        total_trades = int(candidate.metrics.get("total_trades", len(r_multiples)))
        if len(r_multiples) < min_trades or total_trades < min_trades:
            candidate.verdict = "REJECT"
            candidate.notes = f"Rejected by overfit audit: fewer than {min_trades} filled trades."
            audited.append(_audit_row(candidate, None, None, n_trials_raw, n_trials_effective))
            continue

        psr = compute_psr(r_multiples)
        dsr = compute_dsr(r_multiples, n_trials_raw, n_trials_effective)
        candidate.psr = psr.psr
        candidate.dsr = dsr.dsr
        candidate.n_trials_raw = n_trials_raw
        candidate.n_trials_effective = n_trials_effective
        stability_passed = bool(candidate.metrics.get("stability_passed", True))
        psr_passed = candidate.psr >= manifest.gates.min_psr
        dsr_passed = candidate.dsr >= manifest.gates.min_dsr
        passed = stability_passed and psr_passed and dsr_passed
        if passed and candidate.verdict != "REJECT":
            eligible.append(candidate)
        else:
            candidate.verdict = "REJECT"
            if not stability_passed:
                candidate.notes = "Rejected by local/walk-forward stability gate."
            else:
                candidate.notes = (
                    f"Rejected by PSR/DSR gate: PSR={candidate.psr:.4f}, "
                    f"DSR={candidate.dsr:.4f}."
                )
        audited.append(_audit_row(candidate, dataclasses.asdict(psr), dataclasses.asdict(dsr), n_trials_raw, n_trials_effective))

    unique_eligible = []
    seen_candidate_keys: set[str] = set()
    for candidate in eligible:
        key = _candidate_uniqueness_key(candidate)
        if key in seen_candidate_keys:
            candidate.verdict = "REJECT"
            candidate.notes = "Rejected as a duplicate of an already promoted frozen config."
            continue
        seen_candidate_keys.add(key)
        unique_eligible.append(candidate)

    for index, candidate in enumerate(unique_eligible):
        if index >= manifest.gates.max_promoted_candidates:
            candidate.verdict = "REJECT"
            candidate.notes = "Rejected by max promoted candidate gate."
        elif index == 0:
            candidate.verdict = "PROMOTE"
            candidate.notes = "Best surviving discovery candidate."
        else:
            candidate.verdict = "CHALLENGER"
            candidate.notes = "Surviving challenger candidate."

    candidates_by_id = {candidate.id: candidate for candidate in manifest.candidates}
    for row in audited:
        candidate = candidates_by_id.get(row["candidate_id"])
        if candidate is None:
            continue
        row["verdict"] = candidate.verdict
        row["notes"] = candidate.notes

    detail = {
        "n_trials_raw": n_trials_raw,
        "n_trials_effective": n_trials_effective,
        "min_psr": manifest.gates.min_psr,
        "min_dsr": manifest.gates.min_dsr,
        "candidates": audited,
        "pbo_cscv": {
            "implemented": False,
            "note": "The current codebase implements PSR/DSR and effective trial estimation, but not CSCV/PBO.",
        },
    }
    detail_path = _write_detail(output_dir, "overfit_audit", detail)
    return NativePhaseOutcome(
        decision="promotable_candidates" if manifest.promoted_candidates() else "no_promotable_candidates",
        rationale="PSR/DSR were computed for candidate promotion with raw/effective trial counts.",
        payload={
            "detail_path": str(detail_path),
            "n_trials_raw": n_trials_raw,
            "n_trials_effective": n_trials_effective,
            "promoted_candidates": [candidate.id for candidate in manifest.promoted_candidates()],
        },
    )


def run_phase_one_handoff(
    manifest: DiscoveryRunManifest,
    *,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Write a frozen handoff packet for the phase-one robust pipeline."""
    promoted = manifest.promoted_candidates()
    if not promoted:
        raise tool_error(
            "NO_PHASE_ONE_HANDOFF_CANDIDATES",
            "Phase-one handoff requires at least one promoted or challenger candidate.",
            "Run promotion_packet after candidates pass overfit and deployability gates.",
        )
    packet = {
        "source_run_id": manifest.run_id,
        "next_workflow": "phase-one-robust-pipeline",
        "asset": manifest.asset,
        "strategy_family": manifest.strategy_family,
        "holdout": dataclasses.asdict(manifest.data),
        "candidates": [
            {
                "id": candidate.id,
                "label": candidate.label,
                "verdict": candidate.verdict,
                "params": candidate.params,
                "config": candidate.config,
                "metrics": _public_metrics(candidate.metrics),
                "psr": candidate.psr,
                "dsr": candidate.dsr,
                "n_trials_raw": candidate.n_trials_raw,
                "n_trials_effective": candidate.n_trials_effective,
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
            }
            for candidate in promoted
        ],
        "guardrails": [
            "Do not reopen discovery parameters in phase one.",
            "Run exact replay before execution-config consideration.",
            "Treat this as candidate promotion, not final live approval.",
        ],
    }
    packet_path = _artifact_dir(output_dir) / "phase_one_handoff_packet.json"
    _write_json(packet_path, packet)
    return NativePhaseOutcome(
        decision="handoff_packet_ready",
        rationale="Frozen candidates were serialized for phase-one robust validation.",
        payload={"packet_path": str(packet_path), "candidate_ids": [candidate.id for candidate in promoted]},
    )


def run_learnings_update(
    manifest: DiscoveryRunManifest,
    *,
    output_dir: str | Path,
) -> NativePhaseOutcome:
    """Create a learnings-update draft without mutating canonical research memory."""
    promoted = manifest.promoted_candidates()
    lines = [
        f"# Learnings Update Draft: {manifest.run_id}",
        "",
        f"- Asset: `{manifest.asset}`",
        f"- Strategy family: `{manifest.strategy_family}`",
        f"- Discovery window: `{manifest.data.start}` to `{manifest.data.pre_holdout_end}`",
        f"- Holdout preserved from: `{manifest.data.holdout_start}`",
        "",
        "## Candidate Outcomes",
        "",
    ]
    for candidate in manifest.candidates:
        lines.extend(
            [
                f"### {candidate.label}",
                "",
                f"- Verdict: `{candidate.verdict}`",
                f"- Params: `{json.dumps(candidate.params, sort_keys=True)}`",
                f"- Total R: `{candidate.metrics.get('total_r', '')}`",
                f"- Max DD R: `{candidate.metrics.get('max_drawdown_r', '')}`",
                f"- Calmar: `{candidate.metrics.get('calmar_ratio', '')}`",
                f"- MFE p50/p75/p90 R: `{_mfe_metric(candidate, 'p50_mfe_r')}` / `{_mfe_metric(candidate, 'p75_mfe_r')}` / `{_mfe_metric(candidate, 'p90_mfe_r')}`",
                f"- PSR/DSR: `{candidate.psr}` / `{candidate.dsr}`",
                f"- Deployability: `{candidate.deployability or ''}`",
                "",
            ]
        )
    if not promoted:
        lines.append("No candidates survived promotion gates; record the failed hypothesis if this was a meaningful conclusion.")
    lines.extend(
        [
            "",
            "## Registry Step",
            "",
            "After a human reviews and applies this draft to the canonical learnings file, run:",
            "",
            "```bash",
            "uv run python scripts/build_learnings_registry.py",
            "```",
            "",
        ]
    )
    draft_path = Path(output_dir) / "learnings_update_draft.md"
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text("\n".join(lines))
    return NativePhaseOutcome(
        decision="draft_ready",
        rationale="A learnings-update draft was written for review; canonical memory was not mutated automatically.",
        payload={"draft_path": str(draft_path), "promoted_candidates": [candidate.id for candidate in promoted]},
    )


def build_strategy_config(manifest: DiscoveryRunManifest) -> StrategyConfig:
    """Build a StrategyConfig from manifest.base_config."""
    base = dict(manifest.base_config or {})
    instrument_symbol = str(base.get("instrument") or manifest.asset).upper()
    try:
        instrument = get_instrument(instrument_symbol)
    except KeyError as exc:
        raise tool_error(
            "DISCOVERY_UNKNOWN_INSTRUMENT",
            str(exc),
            "Set manifest.asset or base_config.instrument to a registered futures symbol.",
        ) from exc

    strategy = _strategy_name(manifest)
    config = ib_config(instrument) if strategy == "ib" else default_config(instrument)
    if strategy != "ib":
        sessions = _resolve_sessions(base.get("sessions") or manifest.constraints.get("sessions") or ["NY"])
        config = with_overrides(config, sessions=tuple(sessions))

    overrides: dict[str, Any] = {"strategy": strategy}
    if "direction" in base:
        overrides["direction_filter"] = base["direction"]
    for key, value in base.items():
        if key in _IGNORED_BASE_KEYS or key == "direction":
            continue
        if key in _STRATEGY_FIELDS or _is_session_override(key):
            overrides[key] = _coerce_config_value(key, value)
    for key, value in dict(base.get("overrides", {}) or {}).items():
        overrides[key] = _coerce_config_value(key, value)
    overrides.setdefault("name", f"{manifest.run_id} {strategy}")
    return with_overrides(config, **overrides)


def load_discovery_data(
    manifest: DiscoveryRunManifest,
    *,
    repo_root: str | Path,
    start: str,
    end: str,
):
    """Load 5m data and optional lower-timeframe data for a discovery phase."""
    data_file = resolve_data_file(manifest, repo_root=repo_root)
    try:
        df = load_5m_data(data_file, start=start, end=end)
    except FileNotFoundError as exc:
        raise tool_error(
            "DISCOVERY_DATA_NOT_FOUND",
            str(exc),
            "Set base_config.data_file to an existing 5m CSV/parquet path or sync the instrument data.",
        ) from exc

    base = dict(manifest.base_config or {})
    df_1m = None
    df_30s = None
    df_1s = None
    if base.get("load_1m", True):
        try:
            df_1m = (
                load_5m_data(str(base["data_1m_file"]), start=start, end=end)
                if base.get("data_1m_file")
                else load_1m_for_5m(data_file, start=start, end=end)
            )
        except FileNotFoundError:
            df_1m = None
    if base.get("load_30s", False):
        df_30s = (
            load_5m_data(str(base["data_30s_file"]), start=start, end=end)
            if base.get("data_30s_file")
            else load_30s_for_5m(data_file, start=start, end=end)
        )
    if base.get("load_1s", False):
        df_1s = (
            load_5m_data(str(base["data_1s_file"]), start=start, end=end)
            if base.get("data_1s_file")
            else load_1s_for_5m(data_file, start=start, end=end)
        )
    return data_file, df, df_1m, df_30s, df_1s


def resolve_data_file(manifest: DiscoveryRunManifest, *, repo_root: str | Path) -> str:
    """Resolve manifest data_file to an absolute path when possible."""
    base = dict(manifest.base_config or {})
    data_file = base.get("data_file") or manifest.constraints.get("data_file")
    if not data_file:
        try:
            data_file = get_instrument(str(base.get("instrument") or manifest.asset)).data_file
        except KeyError as exc:
            raise tool_error(
                "DISCOVERY_UNKNOWN_INSTRUMENT",
                str(exc),
                "Set base_config.data_file explicitly or use a registered instrument.",
            ) from exc
    path = Path(str(data_file))
    if path.is_absolute():
        return str(path)
    root = Path(repo_root)
    for candidate in (root / path, root / "data" / "raw" / path, root / "data" / "cache" / path):
        if candidate.exists():
            return str(candidate)
    return str(path)


def _strategy_name(manifest: DiscoveryRunManifest) -> str:
    base = dict(manifest.base_config or {})
    raw = str(base.get("strategy") or manifest.strategy_family or "continuation").lower()
    return raw if raw in _KNOWN_STRATEGIES else "continuation"


def _resolve_sessions(raw: Any) -> list[SessionConfig]:
    values = [raw] if isinstance(raw, str) else list(raw or [])
    sessions: list[SessionConfig] = []
    for value in values:
        key = str(value).strip().upper().replace(" ", "_")
        if key not in _SESSION_MAP:
            raise tool_error(
                "DISCOVERY_UNKNOWN_SESSION",
                f"Unknown session {value!r}.",
                "Use one of NY, Asia, or LDN in base_config.sessions.",
            )
        sessions.append(_SESSION_MAP[key])
    return sessions or [NY_SESSION]


def _coerce_config_value(key: str, value: Any) -> Any:
    if key in _TUPLE_FIELDS and isinstance(value, list):
        return tuple(value)
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return value


def _is_session_override(key: str) -> bool:
    for prefix in ("ny_", "asia_", "ldn_"):
        if key.startswith(prefix) and key[len(prefix):] in _SESSION_FIELDS:
            return True
    return False


def _param_ranges(manifest: DiscoveryRunManifest) -> dict[str, list[Any]]:
    raw = (
        manifest.search_budget.get("param_ranges")
        or manifest.search_budget.get("search_space")
        or (manifest.base_config or {}).get("search_space")
        or {}
    )
    return {str(key): list(value if isinstance(value, Iterable) and not isinstance(value, str) else [value]) for key, value in dict(raw).items()}


def _objective_name(manifest: DiscoveryRunManifest) -> str:
    objective = str(manifest.search_budget.get("rank_by") or (manifest.objective_stack[0] if manifest.objective_stack else "calmar"))
    return objective if objective in VALID_OBJECTIVES else "calmar"


def _result_payload(
    trades: list[TradeResult],
    config: StrategyConfig,
    *,
    mfe_df: Any | None = None,
) -> dict[str, Any]:
    result = results_to_dict(trades, config, include_trades=False, include_equity_curve=True)
    mfe = _mfe_diagnostics(trades, mfe_df, config)
    result["summary"]["mfe"] = mfe["summary"]
    result["summary"] = _public_metrics(result["summary"])
    result["r_multiples"] = _r_multiples(trades)
    result["trade_dates"] = _trade_dates(trades)
    result["mfe_trades"] = mfe["trades"]
    return result


def _candidate_from_run(
    manifest: DiscoveryRunManifest,
    *,
    prefix: str,
    label: str,
    config: StrategyConfig,
    params: dict[str, Any],
    metrics: dict[str, Any],
    trades: list[TradeResult],
    source_phase: str,
    objective: str,
    objective_value: float,
    selection_rank: int,
) -> CandidateSpec:
    candidate_id = _candidate_id(prefix, params or _config_summary(config))
    return CandidateSpec(
        id=candidate_id,
        label=label,
        verdict="PENDING",
        params=dict(params),
        config=_config_summary(config),
        metrics={
            **_public_metrics(metrics),
            "objective": objective,
            "objective_value": _finite_float(objective_value),
            "selection_rank": selection_rank,
            "r_multiples": _r_multiples(trades),
            "trade_dates": _trade_dates(trades),
        },
        source_phase=source_phase,
        exact_replay_required=True,
    )


def _config_summary(config: StrategyConfig) -> dict[str, Any]:
    payload = results_to_dict([], config, include_trades=False)["config"]
    return dict(payload)


def _extract_params(config: StrategyConfig, param_names: Iterable[str]) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for name in param_names:
        for prefix in ("ny_", "asia_", "ldn_"):
            if name.startswith(prefix):
                attr = name[len(prefix):]
                session_name = prefix[:-1].upper()
                for session in config.sessions:
                    if session.name.upper() == session_name:
                        params[name] = getattr(session, attr)
                break
        else:
            params[name] = getattr(config, name)
    return params


def _public_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {str(key): _json_ready(value) for key, value in dict(metrics).items() if key not in {"r_multiples", "trade_dates"}}


def _r_multiples(trades: list[TradeResult]) -> list[float]:
    values = []
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            continue
        net_r = getattr(trade, "net_r_multiple", 0.0)
        values.append(round(float(net_r or trade.r_multiple), 6))
    return values


def _trade_dates(trades: list[TradeResult]) -> list[str]:
    return [trade.date for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _mfe_diagnostics(
    trades: list[TradeResult],
    df: Any | None,
    config: StrategyConfig,
) -> dict[str, Any]:
    """Compute post-fill maximum favorable excursion in R units."""
    if df is None or getattr(df, "empty", True):
        return {"summary": _empty_mfe_summary(config), "trades": []}

    rows = []
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL or trade.fill_bar < 0 or trade.risk_points <= 0:
            continue
        path = _trade_price_path(df, trade)
        if path is None or getattr(path, "empty", True):
            continue
        if trade.direction == 1:
            favorable_points = float(path["high"].max()) - float(trade.entry_price)
        else:
            favorable_points = float(trade.entry_price) - float(path["low"].min())
        mfe_r = max(0.0, favorable_points / float(trade.risk_points))
        net_r = getattr(trade, "net_r_multiple", 0.0)
        realized_r = float(net_r or trade.r_multiple)
        rows.append(
            {
                "date": trade.date,
                "session": trade.session,
                "direction": "long" if trade.direction == 1 else "short",
                "exit_type": EXIT_NAMES.get(trade.exit_type, "unknown"),
                "realized_r": round(realized_r, 6),
                "mfe_r": round(mfe_r, 6),
                "entry_time": trade.fill_time,
                "exit_time": trade.exit_time,
            }
        )

    if not rows:
        return {"summary": _empty_mfe_summary(config), "trades": []}

    values = np.asarray([row["mfe_r"] for row in rows], dtype=float)
    target_r = _target_r(config)
    summary = {
        "source": "post_fill_to_exit",
        "timeframe": _infer_mfe_timeframe(df),
        "trade_count": len(rows),
        "avg_mfe_r": round(float(np.mean(values)), 4),
        "p25_mfe_r": round(float(np.quantile(values, 0.25)), 4),
        "p50_mfe_r": round(float(np.quantile(values, 0.50)), 4),
        "p75_mfe_r": round(float(np.quantile(values, 0.75)), 4),
        "p90_mfe_r": round(float(np.quantile(values, 0.90)), 4),
        "mfe_ge_1r_pct": round(_pct(float(np.mean(values >= 1.0))), 2),
        "mfe_ge_2r_pct": round(_pct(float(np.mean(values >= 2.0))), 2),
        "mfe_ge_target_pct": round(_pct(float(np.mean(values >= target_r))), 2),
        "target_r": target_r,
    }
    return {"summary": summary, "trades": rows}


def _empty_mfe_summary(config: StrategyConfig) -> dict[str, Any]:
    return {
        "source": "post_fill_to_exit",
        "timeframe": None,
        "trade_count": 0,
        "avg_mfe_r": 0.0,
        "p25_mfe_r": 0.0,
        "p50_mfe_r": 0.0,
        "p75_mfe_r": 0.0,
        "p90_mfe_r": 0.0,
        "mfe_ge_1r_pct": 0.0,
        "mfe_ge_2r_pct": 0.0,
        "mfe_ge_target_pct": 0.0,
        "target_r": _target_r(config),
    }


def _trade_price_path(df: Any, trade: TradeResult):
    if trade.fill_time:
        end = trade.exit_time or trade.fill_time
        try:
            path = df.loc[trade.fill_time:end]
            if not path.empty:
                return path
        except Exception:
            pass
    start = max(int(trade.fill_bar), 0)
    end = max(int(trade.exit_bar), start)
    try:
        return df.iloc[start : end + 1]
    except Exception:
        return None


def _infer_mfe_timeframe(df: Any) -> str | None:
    try:
        if len(df.index) < 2:
            return None
        delta = df.index[1] - df.index[0]
        seconds = int(delta.total_seconds())
    except Exception:
        return None
    if seconds % 60 == 0:
        return f"{seconds // 60}m"
    return f"{seconds}s"


def _target_r(config: StrategyConfig) -> float:
    if config.exit_mode == "single_target":
        return float(config.rr)
    return float(max(config.rr, config.tp1_ratio * config.rr))


def _pct(value: float) -> float:
    return value * 100.0


def _mfe_metric(candidate: CandidateSpec, key: str) -> Any:
    mfe = candidate.metrics.get("mfe")
    if isinstance(mfe, dict):
        return mfe.get(key, "")
    return ""


def _candidate_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(_json_ready(payload), sort_keys=True, default=str).encode()
    return f"{prefix}_{hashlib.sha256(encoded).hexdigest()[:10]}"


def _upsert_candidate(manifest: DiscoveryRunManifest, candidate: CandidateSpec) -> None:
    for index, existing in enumerate(manifest.candidates):
        if existing.id == candidate.id:
            manifest.candidates[index] = candidate
            return
    manifest.candidates.append(candidate)


def _candidate_sort_key(candidate: CandidateSpec) -> tuple[int, float]:
    rank = int(candidate.metrics.get("selection_rank", 999999))
    objective = float(candidate.metrics.get("objective_value", 0.0) or 0.0)
    return rank, -objective


def _candidate_uniqueness_key(candidate: CandidateSpec) -> str:
    payload = candidate.params or candidate.config
    return json.dumps(_json_ready(payload), sort_keys=True, default=str)


def _audit_row(
    candidate: CandidateSpec,
    psr: dict[str, Any] | None,
    dsr: dict[str, Any] | None,
    n_trials_raw: int,
    n_trials_effective: int,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate.id,
        "verdict": candidate.verdict,
        "psr": psr,
        "dsr": dsr,
        "n_trials_raw": n_trials_raw,
        "n_trials_effective": n_trials_effective,
        "notes": candidate.notes,
    }


def _trade_date_sets_from_detail(detail: dict[str, Any] | None) -> list[set[str]]:
    if not detail:
        return []
    return [set(row.get("trade_dates", [])) for row in detail.get("all_results", [])]


def _local_plateau_scores(
    rows: list[dict[str, Any]],
    param_ranges: dict[str, list[Any]],
    *,
    objective_floor_ratio: float,
) -> dict[str, float]:
    if not rows:
        return {}
    ranges = {key: list(values) for key, values in param_ranges.items()}
    by_key = {_params_key(row.get("params", {}), ranges.keys()): row for row in rows}
    scores: dict[str, float] = {}
    for row in rows:
        params = row.get("params", {})
        candidate_id = row.get("candidate_id")
        if not candidate_id:
            continue
        neighbor_scores = []
        for param, values in ranges.items():
            if param not in params:
                continue
            try:
                index = values.index(params[param])
            except ValueError:
                continue
            for neighbor_index in (index - 1, index + 1):
                if neighbor_index < 0 or neighbor_index >= len(values):
                    continue
                neighbor_params = dict(params)
                neighbor_params[param] = values[neighbor_index]
                neighbor = by_key.get(_params_key(neighbor_params, ranges.keys()))
                if neighbor is not None:
                    neighbor_scores.append(float(neighbor.get("objective_value", 0.0) or 0.0))
        if not neighbor_scores:
            scores[str(candidate_id)] = 1.0
            continue
        own = float(row.get("objective_value", 0.0) or 0.0)
        threshold = own * objective_floor_ratio if own > 0 else own
        scores[str(candidate_id)] = round(sum(score >= threshold for score in neighbor_scores) / len(neighbor_scores), 4)
    return scores


def _params_key(params: dict[str, Any], keys: Iterable[str]) -> tuple[Any, ...]:
    return tuple(params.get(key) for key in keys)


def _stability_payload(stability) -> dict[str, Any]:
    return {
        "overall_score": stability.overall_score,
        "n_folds": stability.n_folds,
        "interpretation": stability.interpretation,
        "params": [dataclasses.asdict(param) for param in stability.params],
    }


def _artifact_dir(output_dir: str | Path) -> Path:
    path = Path(output_dir) / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _detail_path(output_dir: str | Path, phase_id: str) -> Path:
    return _artifact_dir(output_dir) / f"{phase_id}_details.json"


def _write_detail(output_dir: str | Path, phase_id: str, payload: dict[str, Any]) -> Path:
    path = _detail_path(output_dir, phase_id)
    _write_json(path, payload)
    return path


def _read_detail(output_dir: str | Path, phase_id: str) -> dict[str, Any] | None:
    path = _detail_path(output_dir, phase_id)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), indent=2, sort_keys=False) + "\n")


def _json_ready(value: Any) -> Any:
    value = to_jsonable(value)
    if isinstance(value, np.generic):
        return _json_ready(value.item())
    if isinstance(value, np.ndarray):
        return [_json_ready(item) for item in value.tolist()]
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    return value


def _finite_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0
