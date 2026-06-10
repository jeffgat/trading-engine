"""Runner for manifest-driven discovery workflows."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..analysis.holdout_log import check_holdout_period
from ..errors import BacktestError
from .manifest import (
    DISCOVERY_PHASE_ORDER,
    PROMOTION_VERDICTS,
    CandidateSpec,
    DiscoveryRunManifest,
    PhaseSpec,
    load_manifest,
    save_manifest,
    to_jsonable,
    utc_now,
)
from . import tools as native_tools


class DiscoveryWorkflowError(BacktestError):
    """Structured discovery workflow error."""


def workflow_error(code: str, reason: str, fix: str) -> DiscoveryWorkflowError:
    return DiscoveryWorkflowError(code=code, reason=reason, fix=fix)


@dataclass
class PhaseArtifact:
    """Structured artifact written by every phase."""

    run_id: str
    phase_id: str
    phase_title: str
    agent_role: str
    status: str
    started_at: str
    finished_at: str
    inputs_hash: str
    decision: str | None = None
    rationale: str | None = None
    command: list[str] | None = None
    returncode: int | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class DiscoveryWorkflow:
    """Execute and audit a discovery manifest one phase at a time."""

    def __init__(
        self,
        manifest_path: str | Path,
        *,
        repo_root: str | Path | None = None,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.manifest = load_manifest(self.manifest_path)
        self.repo_root = Path(repo_root) if repo_root else self.manifest_path.parent
        self.output_dir = self._resolve_output_dir()
        self.artifact_dir = self.output_dir / "artifacts"
        self.log_dir = self.output_dir / "logs"

    def _resolve_output_dir(self) -> Path:
        if self.manifest.output_dir:
            path = Path(self.manifest.output_dir)
            if not path.is_absolute():
                path = self.repo_root / path
            return path
        return self.repo_root / "data" / "results" / "discovery_runs" / self.manifest.run_id

    def validate(self) -> None:
        errors = self.manifest.validate()
        if errors:
            raise workflow_error(
                "INVALID_DISCOVERY_MANIFEST",
                "; ".join(errors),
                "Fix the manifest fields before running the workflow.",
            )

    def status(self) -> dict[str, Any]:
        """Return a compact status summary."""
        return {
            "run_id": self.manifest.run_id,
            "asset": self.manifest.asset,
            "strategy_family": self.manifest.strategy_family,
            "verdict": self.manifest.verdict,
            "output_dir": str(self.output_dir),
            "phases": [
                {
                    "id": phase.id,
                    "title": phase.title,
                    "status": phase.status,
                    "decision": phase.decision,
                    "artifact_path": phase.artifact_path,
                }
                for phase in self.manifest.phases
            ],
            "promoted_candidates": [candidate.id for candidate in self.manifest.promoted_candidates()],
        }

    def run_all(self, *, dry_run: bool = False) -> list[PhaseArtifact]:
        """Run every required pending phase in order."""
        artifacts = []
        for phase in self.manifest.phases:
            if phase.status == "completed":
                continue
            if not phase.required and phase.command is None and not self._has_builtin_phase(phase.id):
                continue
            artifact = self.run_phase(phase.id, dry_run=dry_run)
            artifacts.append(artifact)
            if artifact.status != "completed":
                break
        return artifacts

    def run_phase(self, phase_id: str, *, dry_run: bool = False) -> PhaseArtifact:
        """Run one phase by id and persist its artifact."""
        self.validate()
        phase = self.manifest.phase(phase_id)

        started = utc_now()
        phase.started_at = started
        phase.status = "running"
        save_manifest(self.manifest, self.manifest_path)

        try:
            self._assert_phase_can_run(phase)
            if dry_run:
                artifact = self._dry_run_artifact(phase, started)
            elif phase.id == "learnings_review":
                artifact = self._run_learnings_review(phase, started)
            elif phase.id == "holdout_freeze":
                artifact = self._run_holdout_freeze(phase, started)
            elif phase.id == "deployability_audit":
                artifact = self._run_deployability_audit(phase, started)
            elif phase.id == "promotion_packet":
                artifact = self._run_promotion_packet(phase, started)
            elif phase.command:
                artifact = self._run_command_phase(phase, started)
            elif phase.id in native_tools.NATIVE_PHASES:
                artifact = self._run_native_phase(phase, started)
            else:
                artifact = self._skipped_artifact(
                    phase,
                    started,
                    rationale="No command or built-in tool is configured for this phase.",
                )
        except Exception as exc:
            artifact = self._failure_artifact(phase, started, exc)

        self._persist_phase_result(phase, artifact)
        return artifact

    def _assert_phase_can_run(self, phase: PhaseSpec) -> None:
        completed = self.manifest.completed_phase_ids()
        phase_index = DISCOVERY_PHASE_ORDER.index(phase.id)
        incomplete_required = [
            prior.id
            for prior in self.manifest.phases
            if prior.required
            and DISCOVERY_PHASE_ORDER.index(prior.id) < phase_index
            and prior.status != "completed"
        ]
        if incomplete_required:
            raise workflow_error(
                "DISCOVERY_PHASE_ORDER_BLOCKED",
                f"Phase {phase.id} cannot run before required phase(s): {', '.join(incomplete_required)}",
                "Run the earlier required phases or mark them completed with a valid artifact.",
            )
        if phase.uses_holdout and phase.id not in {"phase_one_handoff"}:
            raise workflow_error(
                "HOLDOUT_ACCESS_BLOCKED",
                f"Phase {phase.id} declares holdout access before phase-one handoff.",
                "Keep discovery phases on pre-holdout data only.",
            )
        if phase.id == "promotion_packet":
            self._assert_promotion_gates(completed)

    def _assert_promotion_gates(self, completed: set[str]) -> None:
        gates = self.manifest.gates
        promoted = self.manifest.promoted_candidates()
        if not promoted:
            raise workflow_error(
                "NO_PROMOTED_CANDIDATES",
                "Promotion packet requires at least one PROMOTE or CHALLENGER candidate.",
                "Add frozen candidates to manifest.candidates before writing the packet.",
            )
        if len(promoted) > gates.max_promoted_candidates:
            raise workflow_error(
                "TOO_MANY_PROMOTED_CANDIDATES",
                f"More than {gates.max_promoted_candidates} candidates are marked PROMOTE or CHALLENGER.",
                "Promote a tiny frozen shortlist and demote extra rows to CHALLENGER or REJECT.",
            )
        if gates.require_overfit_audit and "overfit_audit" not in completed:
            raise workflow_error(
                "OVERFIT_AUDIT_REQUIRED",
                "PSR/DSR overfit audit must complete before promotion.",
                "Run the overfit_audit phase and record candidate PSR/DSR values.",
            )
        if gates.require_deployability_labels and "deployability_audit" not in completed:
            raise workflow_error(
                "DEPLOYABILITY_AUDIT_REQUIRED",
                "Deployability audit must complete before promotion.",
                "Run deployability_audit after candidate labels are populated.",
            )
        for candidate in promoted:
            self._assert_candidate_promotable(candidate)

    def _assert_candidate_promotable(self, candidate: CandidateSpec) -> None:
        gates = self.manifest.gates
        if gates.require_deployability_labels:
            missing = []
            if not candidate.deployability:
                missing.append("deployability")
            if not candidate.live_support_notes:
                missing.append("live_support_notes")
            if missing:
                raise workflow_error(
                    "CANDIDATE_DEPLOYABILITY_MISSING",
                    f"Candidate {candidate.id} is missing {', '.join(missing)}.",
                    "Label every promoted candidate with deployability and live support notes.",
                )
        if candidate.deployability in {"post_filter_only", "research_only"} and not candidate.live_support_notes:
            raise workflow_error(
                "CANDIDATE_NOT_LIVE_NATIVE",
                f"Candidate {candidate.id} is {candidate.deployability} without an implementation note.",
                "Add an implementation plan to make it live_native or keep it as a research idea.",
            )
        if gates.require_overfit_audit:
            if candidate.psr is None or candidate.dsr is None:
                raise workflow_error(
                    "CANDIDATE_OVERFIT_METRICS_MISSING",
                    f"Candidate {candidate.id} is missing PSR/DSR values.",
                    "Record PSR and DSR on promoted candidates before promotion.",
                )
            if candidate.psr < gates.min_psr or candidate.dsr < gates.min_dsr:
                raise workflow_error(
                    "CANDIDATE_OVERFIT_GATE_FAILED",
                    (
                        f"Candidate {candidate.id} has PSR={candidate.psr} and DSR={candidate.dsr}; "
                        f"required PSR>={gates.min_psr}, DSR>={gates.min_dsr}."
                    ),
                    "Demote the candidate or rerun discovery with a more robust packet.",
                )

    def _has_builtin_phase(self, phase_id: str) -> bool:
        return phase_id in {
            "learnings_review",
            "holdout_freeze",
            "deployability_audit",
            "promotion_packet",
            *native_tools.NATIVE_PHASES,
        }

    def _manifest_hash(self) -> str:
        payload = to_jsonable(self.manifest)
        encoded = json.dumps(payload, sort_keys=True, default=str).encode()
        return hashlib.sha256(encoded).hexdigest()

    def _dry_run_artifact(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="skipped",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision="dry_run",
            rationale="Dry run requested; no tools executed.",
            command=phase.command,
        )

    def _run_learnings_review(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        root = self.repo_root
        asset = self.manifest.asset.upper()
        paths = [
            root / "learnings" / "README.md",
            root / "learnings" / "briefs" / "GLOBAL.md",
            root / "learnings" / "briefs" / "assets" / f"{asset}.md",
            root / "learnings" / "asset" / f"{asset}.md",
        ]
        existing = [str(path) for path in paths if path.exists()]
        missing = [str(path) for path in paths if not path.exists()]
        decision = "completed" if existing else "warning"
        rationale = "Learning sources recorded for thesis review."
        if not existing:
            rationale = "No learning files found for this asset."
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="completed",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision=decision,
            rationale=rationale,
            payload={"existing_paths": existing, "missing_paths": missing},
        )

    def _run_holdout_freeze(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        data = self.manifest.data
        holdout_end = data.holdout_end or "open"
        check_end = data.holdout_end or ""
        check = check_holdout_period(data.holdout_start, check_end)
        if not check.is_clean and not self.manifest.gates.allow_contaminated_holdout:
            raise workflow_error(
                "HOLDOUT_CONTAMINATED",
                check.warning or "Holdout period has previous logged use.",
                "Choose a clean holdout or set gates.allow_contaminated_holdout with an explicit caveat.",
            )
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="completed",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision="clean" if check.is_clean else "contaminated_allowed",
            rationale=f"Discovery is restricted to {data.start} through {data.pre_holdout_end}; holdout starts {data.holdout_start}.",
            payload={
                "holdout_start": data.holdout_start,
                "holdout_end": holdout_end,
                "previous_test_count": check.previous_test_count,
                "previous_configs": check.previous_configs,
                "warning": check.warning,
            },
        )

    def _run_deployability_audit(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        rows = []
        missing = []
        for candidate in self.manifest.candidates:
            self._ensure_deployability_label(candidate)
            row = {
                "id": candidate.id,
                "verdict": candidate.verdict,
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
            }
            rows.append(row)
            if candidate.is_promoted() and (not candidate.deployability or not candidate.live_support_notes):
                missing.append(candidate.id)
        if missing:
            raise workflow_error(
                "DEPLOYABILITY_LABELS_INCOMPLETE",
                f"Promoted candidates missing deployability evidence: {', '.join(missing)}",
                "Fill deployability, live_support_notes, and exact_replay_required before promotion.",
            )
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="completed",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision="passed",
            rationale="Promoted candidates include deployability labels and live support notes.",
            payload={"candidates": rows},
        )

    def _ensure_deployability_label(self, candidate: CandidateSpec) -> None:
        """Populate conservative deployability labels when the workflow can infer them."""
        if candidate.deployability and candidate.live_support_notes:
            return
        candidate.exact_replay_required = True
        config = {**candidate.config, **candidate.params}
        constraints = dict(self.manifest.constraints or {})
        if config.get("research_only") or constraints.get("research_only"):
            candidate.deployability = candidate.deployability or "research_only"
            candidate.live_support_notes = candidate.live_support_notes or (
                "Candidate uses research-only logic; convert it to live-native logic before deployment."
            )
            return
        if config.get("post_filters") or constraints.get("post_filters"):
            candidate.deployability = candidate.deployability or "post_filter_only"
            candidate.live_support_notes = candidate.live_support_notes or (
                "Candidate depends on post-filter constraints; implement them as live pre-trade gates before deployment."
            )
            return
        candidate.deployability = candidate.deployability or "live_native"
        candidate.live_support_notes = candidate.live_support_notes or (
            "Candidate is expressed with StrategyConfig-native parameters; exact execution replay is still required."
        )

    def _run_promotion_packet(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        memo_path = self.output_dir / "promotion_packet.md"
        memo_text = self._render_promotion_packet()
        memo_path.parent.mkdir(parents=True, exist_ok=True)
        memo_path.write_text(memo_text)
        self.manifest.verdict = self._overall_verdict()
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="completed",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision=self.manifest.verdict,
            rationale="Promotion packet written with frozen candidate shortlist.",
            payload={"memo_path": str(memo_path)},
        )

    def _run_native_phase(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        outcome = native_tools.run_native_phase(
            phase.id,
            self.manifest,
            repo_root=self.repo_root,
            output_dir=self.output_dir,
        )
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="completed",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision=outcome.decision,
            rationale=outcome.rationale,
            payload=outcome.payload,
        )

    def _run_command_phase(self, phase: PhaseSpec, started: str) -> PhaseArtifact:
        assert phase.command is not None
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = self.log_dir / f"{phase.id}.stdout.log"
        stderr_path = self.log_dir / f"{phase.id}.stderr.log"
        proc = subprocess.run(
            phase.command,
            cwd=self.repo_root,
            text=True,
            capture_output=True,
            check=False,
        )
        stdout_path.write_text(proc.stdout)
        stderr_path.write_text(proc.stderr)
        status = "completed" if proc.returncode == 0 else "failed"
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status=status,
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision="completed" if proc.returncode == 0 else "failed",
            rationale="Configured deterministic command executed.",
            command=phase.command,
            returncode=proc.returncode,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            payload={"expected_artifacts": phase.expected_artifacts},
        )

    def _skipped_artifact(self, phase: PhaseSpec, started: str, *, rationale: str) -> PhaseArtifact:
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="skipped",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision="manual_required",
            rationale=rationale,
            command=phase.command,
        )

    def _failure_artifact(self, phase: PhaseSpec, started: str, exc: Exception) -> PhaseArtifact:
        if isinstance(exc, BacktestError):
            payload = {"error": exc.to_dict()}
            reason = exc.reason
        else:
            payload = {"error": {"code": exc.__class__.__name__, "reason": str(exc)}}
            reason = str(exc)
        return PhaseArtifact(
            run_id=self.manifest.run_id,
            phase_id=phase.id,
            phase_title=phase.title,
            agent_role=phase.agent_role,
            status="failed",
            started_at=started,
            finished_at=utc_now(),
            inputs_hash=self._manifest_hash(),
            decision="failed",
            rationale=reason,
            command=phase.command,
            payload=payload,
        )

    def _persist_phase_result(self, phase: PhaseSpec, artifact: PhaseArtifact) -> None:
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = self.artifact_dir / f"{phase.id}.json"
        artifact_path.write_text(json.dumps(to_jsonable(artifact), indent=2, sort_keys=False) + "\n")
        phase.status = artifact.status
        phase.finished_at = artifact.finished_at
        phase.decision = artifact.decision
        phase.rationale = artifact.rationale
        phase.artifact_path = str(artifact_path)
        if str(artifact_path) not in self.manifest.artifacts:
            self.manifest.artifacts.append(str(artifact_path))
        save_manifest(self.manifest, self.manifest_path)

    def _overall_verdict(self) -> str:
        promoted = [c for c in self.manifest.candidates if c.verdict == "PROMOTE"]
        challengers = [c for c in self.manifest.candidates if c.verdict == "CHALLENGER"]
        if promoted:
            return "PROMOTE"
        if challengers:
            return "CHALLENGER"
        return "REJECT"

    def _render_promotion_packet(self) -> str:
        lines = [
            f"# Discovery Promotion Packet: {self.manifest.run_id}",
            "",
            f"- Asset: `{self.manifest.asset}`",
            f"- Strategy family: `{self.manifest.strategy_family}`",
            f"- Thesis: {self.manifest.thesis}",
            f"- Discovery window: `{self.manifest.data.start}` to `{self.manifest.data.pre_holdout_end}`",
            f"- Frozen holdout starts: `{self.manifest.data.holdout_start}`",
            f"- Objective stack: `{', '.join(self.manifest.objective_stack)}`",
            "",
            "## Candidates",
            "",
            "| Verdict | Candidate | Deployability | PSR | DSR | Raw Trials | Effective Trials | Notes |",
            "|---|---|---|---:|---:|---:|---:|---|",
        ]
        for candidate in self.manifest.candidates:
            if candidate.verdict not in PROMOTION_VERDICTS and candidate.verdict != "REJECT":
                continue
            lines.append(
                "| "
                f"{candidate.verdict} | "
                f"{candidate.label} | "
                f"{candidate.deployability or ''} | "
                f"{_fmt_float(candidate.psr)} | "
                f"{_fmt_float(candidate.dsr)} | "
                f"{candidate.n_trials_raw if candidate.n_trials_raw is not None else ''} | "
                f"{candidate.n_trials_effective if candidate.n_trials_effective is not None else ''} | "
                f"{candidate.notes or candidate.live_support_notes or ''} |"
            )
        lines.extend([
            "",
            "## Phase Artifacts",
            "",
        ])
        for phase in self.manifest.phases:
            if DISCOVERY_PHASE_ORDER.index(phase.id) > DISCOVERY_PHASE_ORDER.index("promotion_packet"):
                continue
            if phase.artifact_path:
                status = "completed" if phase.id == "promotion_packet" and phase.status == "running" else phase.status
                lines.append(f"- `{phase.id}`: `{status}` - `{phase.artifact_path}`")
        lines.extend([
            "",
            "## Guardrail Notes",
            "",
            "- This is a discovery promotion packet, not a live deployment verdict.",
            "- Phase-one payout validation must use the frozen candidate parameters without reopening discovery.",
            "- Non-live-native candidates require live pre-trade implementation before exact replay or execution consideration.",
            "",
        ])
        return "\n".join(lines)


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.4f}"
