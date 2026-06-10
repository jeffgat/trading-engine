"""Structured manifests for agentic strategy discovery workflows.

The manifest is intentionally plain JSON so a human, script, dashboard, or
agent can inspect and update the same run record without custom tooling.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DISCOVERY_PHASE_ORDER = [
    "intake",
    "learnings_review",
    "holdout_freeze",
    "structural_screen",
    "discovery_search",
    "walk_forward",
    "stability_check",
    "overfit_audit",
    "deployability_audit",
    "promotion_packet",
    "phase_one_handoff",
    "learnings_update",
]


TERMINAL_PHASE_STATUSES = {"completed", "skipped", "failed"}
VALID_DEPLOYABILITY = {"live_native", "post_filter_only", "research_only"}
VALID_CANDIDATE_VERDICTS = {"PENDING", "PROMOTE", "CHALLENGER", "REJECT"}
PROMOTION_VERDICTS = {"PROMOTE", "CHALLENGER"}


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class DataWindow:
    """Date boundaries for discovery and downstream holdout use."""

    start: str
    pre_holdout_end: str
    holdout_start: str
    holdout_end: str | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.start > self.pre_holdout_end:
            errors.append("data.start must be <= data.pre_holdout_end")
        if self.pre_holdout_end >= self.holdout_start:
            errors.append("data.pre_holdout_end must be before data.holdout_start")
        if self.holdout_end is not None and self.holdout_start > self.holdout_end:
            errors.append("data.holdout_start must be <= data.holdout_end")
        return errors


@dataclass
class WorkflowGateConfig:
    """Hard gates enforced by the workflow runner."""

    allow_contaminated_holdout: bool = False
    require_overfit_audit: bool = True
    require_deployability_labels: bool = True
    min_psr: float = 0.85
    min_dsr: float = 0.50
    max_promoted_candidates: int = 3


@dataclass
class PhaseSpec:
    """A single workflow phase owned by a bounded agent role."""

    id: str
    title: str
    agent_role: str
    skills: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    command: list[str] | None = None
    expected_artifacts: list[str] = field(default_factory=list)
    uses_holdout: bool = False
    status: str = "pending"
    artifact_path: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    decision: str | None = None
    rationale: str | None = None
    required: bool = True


@dataclass
class CandidateSpec:
    """Candidate row carried through discovery and promotion."""

    id: str
    label: str
    verdict: str = "PENDING"
    params: dict[str, Any] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    source_phase: str | None = None
    deployability: str | None = None
    live_support_notes: str | None = None
    exact_replay_required: bool = True
    psr: float | None = None
    dsr: float | None = None
    n_trials_raw: int | None = None
    n_trials_effective: int | None = None
    notes: str | None = None

    def is_promoted(self) -> bool:
        return self.verdict in PROMOTION_VERDICTS


@dataclass
class DiscoveryRunManifest:
    """Top-level workflow state for one discovery run."""

    run_id: str
    thesis: str
    asset: str
    strategy_family: str
    data: DataWindow
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    output_dir: str | None = None
    objective_stack: list[str] = field(default_factory=lambda: ["calmar", "oos_plausibility"])
    constraints: dict[str, Any] = field(default_factory=dict)
    search_budget: dict[str, Any] = field(default_factory=dict)
    base_config: dict[str, Any] = field(default_factory=dict)
    gates: WorkflowGateConfig = field(default_factory=WorkflowGateConfig)
    phases: list[PhaseSpec] = field(default_factory=list)
    candidates: list[CandidateSpec] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    verdict: str | None = None

    def phase(self, phase_id: str) -> PhaseSpec:
        for phase in self.phases:
            if phase.id == phase_id:
                return phase
        raise KeyError(f"Unknown discovery phase: {phase_id}")

    def completed_phase_ids(self) -> set[str]:
        return {phase.id for phase in self.phases if phase.status == "completed"}

    def promoted_candidates(self) -> list[CandidateSpec]:
        return [candidate for candidate in self.candidates if candidate.is_promoted()]

    def validate(self) -> list[str]:
        errors = self.data.validate()
        seen: set[str] = set()
        last_index = -1
        for phase in self.phases:
            if phase.id in seen:
                errors.append(f"duplicate phase id: {phase.id}")
            seen.add(phase.id)
            if phase.id not in DISCOVERY_PHASE_ORDER:
                errors.append(f"unknown phase id: {phase.id}")
                continue
            index = DISCOVERY_PHASE_ORDER.index(phase.id)
            if index < last_index:
                errors.append("phases must be listed in discovery order")
            last_index = max(last_index, index)
        for candidate in self.candidates:
            if candidate.verdict not in VALID_CANDIDATE_VERDICTS:
                errors.append(f"candidate {candidate.id} has invalid verdict {candidate.verdict!r}")
            if candidate.deployability is not None and candidate.deployability not in VALID_DEPLOYABILITY:
                errors.append(f"candidate {candidate.id} has invalid deployability {candidate.deployability!r}")
        max_trials = self.search_budget.get("max_trials")
        if max_trials is not None and int(max_trials) < 1:
            errors.append("search_budget.max_trials must be >= 1")
        top_n = self.search_budget.get("top_n")
        if top_n is not None and int(top_n) < 1:
            errors.append("search_budget.top_n must be >= 1")
        return errors


def create_default_manifest(
    *,
    run_id: str,
    thesis: str,
    asset: str,
    strategy_family: str,
    data: DataWindow,
    output_dir: str | None = None,
) -> DiscoveryRunManifest:
    """Create a default discovery manifest with all MVP phases."""
    phases = [
        PhaseSpec(
            id="intake",
            title="Intake Thesis",
            agent_role="Discovery Conductor",
            skills=["agent-first", "discovery-pipeline"],
            tools=["manifest"],
            status="completed",
            decision="accepted",
            rationale="Initial discovery manifest created.",
        ),
        PhaseSpec(
            id="learnings_review",
            title="Read Asset Learnings",
            agent_role="Thesis Scout",
            skills=["discovery-pipeline"],
            tools=["learnings_briefs"],
        ),
        PhaseSpec(
            id="holdout_freeze",
            title="Freeze Final Holdout",
            agent_role="Holdout Guardian",
            skills=["discovery-pipeline"],
            tools=["holdout_log"],
        ),
        PhaseSpec(
            id="structural_screen",
            title="Structural Family Screen",
            agent_role="Sweep Runner",
            skills=["backtesting-frameworks", "discovery-pipeline"],
            tools=["native_structural_screen", "run_backtest", "compute_metrics"],
        ),
        PhaseSpec(
            id="discovery_search",
            title="Pre-Holdout Discovery Search",
            agent_role="Search Designer",
            skills=["strategy-optimizer", "discovery-pipeline"],
            tools=["native_discovery_search", "run_sweep", "candidate_shortlist"],
        ),
        PhaseSpec(
            id="walk_forward",
            title="Rolling Walk-Forward Ranking",
            agent_role="Walk-Forward Auditor",
            skills=["discovery-pipeline"],
            tools=["native_walk_forward", "run_walkforward"],
        ),
        PhaseSpec(
            id="stability_check",
            title="Local Stability and Plateau Check",
            agent_role="Stability Auditor",
            skills=["discovery-pipeline"],
            tools=["native_stability_check", "analyze_parameter_stability", "local_sweep"],
        ),
        PhaseSpec(
            id="overfit_audit",
            title="PSR/DSR Overfit Audit",
            agent_role="Overfit Auditor",
            skills=["discovery-pipeline"],
            tools=["native_overfit_audit", "compute_psr", "compute_dsr"],
        ),
        PhaseSpec(
            id="deployability_audit",
            title="Deployability Audit",
            agent_role="Deployability Auditor",
            skills=["discovery-pipeline"],
            tools=["candidate_deployability_labels"],
        ),
        PhaseSpec(
            id="promotion_packet",
            title="Promotion Packet",
            agent_role="Promotion Writer",
            skills=["discovery-pipeline"],
            tools=["promotion_memo"],
        ),
        PhaseSpec(
            id="phase_one_handoff",
            title="Phase-One Handoff",
            agent_role="Phase-One Handoff",
            skills=["phase-one-robust-pipeline"],
            tools=["native_phase_one_handoff", "phase_one_pipeline"],
            required=False,
        ),
        PhaseSpec(
            id="learnings_update",
            title="Update Learnings",
            agent_role="Promotion Writer",
            skills=["discovery-pipeline"],
            tools=["native_learnings_update", "learnings_registry"],
            required=False,
        ),
    ]
    return DiscoveryRunManifest(
        run_id=run_id,
        thesis=thesis,
        asset=asset,
        strategy_family=strategy_family,
        data=data,
        output_dir=output_dir,
        phases=phases,
    )


def _from_mapping(dataclass_type, payload: dict[str, Any]):
    fields = dataclass_type.__dataclass_fields__
    kwargs = {}
    for name in fields:
        if name in payload:
            kwargs[name] = payload[name]
    return dataclass_type(**kwargs)


def manifest_from_dict(payload: dict[str, Any]) -> DiscoveryRunManifest:
    """Deserialize a manifest dict into dataclasses."""
    data = _from_mapping(DataWindow, payload["data"])
    gates = _from_mapping(WorkflowGateConfig, payload.get("gates", {}))
    phases = [_from_mapping(PhaseSpec, item) for item in payload.get("phases", [])]
    candidates = [
        _from_mapping(CandidateSpec, item) for item in payload.get("candidates", [])
    ]
    manifest = DiscoveryRunManifest(
        run_id=payload["run_id"],
        thesis=payload["thesis"],
        asset=payload["asset"],
        strategy_family=payload["strategy_family"],
        data=data,
        created_at=payload.get("created_at", utc_now()),
        updated_at=payload.get("updated_at", utc_now()),
        output_dir=payload.get("output_dir"),
        objective_stack=list(payload.get("objective_stack", ["calmar", "oos_plausibility"])),
        constraints=dict(payload.get("constraints", {})),
        search_budget=dict(payload.get("search_budget", {})),
        base_config=dict(payload.get("base_config", {})),
        gates=gates,
        phases=phases,
        candidates=candidates,
        artifacts=list(payload.get("artifacts", [])),
        verdict=payload.get("verdict"),
    )
    return manifest


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses and paths to JSON-compatible structures."""
    if is_dataclass(value):
        return to_jsonable(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [to_jsonable(item) for item in value]
    return value


def load_manifest(path: str | Path) -> DiscoveryRunManifest:
    """Load a discovery manifest from JSON."""
    manifest_path = Path(path)
    payload = json.loads(manifest_path.read_text())
    return manifest_from_dict(payload)


def save_manifest(manifest: DiscoveryRunManifest, path: str | Path) -> None:
    """Save a discovery manifest as pretty JSON."""
    manifest.updated_at = utc_now()
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(to_jsonable(manifest), indent=2, sort_keys=False) + "\n")
