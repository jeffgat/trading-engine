from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from orb_backtest.discovery import (
    CandidateSpec,
    DataWindow,
    DiscoveryWorkflow,
    create_default_manifest,
    save_manifest,
)
from orb_backtest.discovery import tools as native_tools
from orb_backtest.discovery.manifest import load_manifest
from orb_backtest.config import default_config, with_overrides
from orb_backtest.engine.simulator import EXIT_TP2_SINGLE, TradeResult
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import WalkForwardFold, WalkForwardResult


REPO_ROOT = Path(__file__).resolve().parents[1]


def _make_manifest(tmp_path: Path):
    manifest = create_default_manifest(
        run_id="test_run",
        thesis="Test a tiny workflow.",
        asset="NQ",
        strategy_family="unit_test",
        data=DataWindow(
            start="2020-01-01",
            pre_holdout_end="2024-12-31",
            holdout_start="2025-01-01",
        ),
        output_dir=str(tmp_path / "run"),
    )
    path = tmp_path / "manifest.json"
    save_manifest(manifest, path)
    return path


def test_manifest_date_gate():
    manifest = create_default_manifest(
        run_id="bad_dates",
        thesis="bad",
        asset="NQ",
        strategy_family="bad",
        data=DataWindow(
            start="2020-01-01",
            pre_holdout_end="2025-01-01",
            holdout_start="2025-01-01",
        ),
    )
    assert "data.pre_holdout_end must be before data.holdout_start" in manifest.validate()


def test_holdout_phase_writes_artifact(tmp_path):
    path = _make_manifest(tmp_path)
    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)

    workflow.run_phase("learnings_review")
    artifact = workflow.run_phase("holdout_freeze")

    assert artifact.status == "completed"
    assert artifact.payload["holdout_start"] == "2025-01-01"
    saved = load_manifest(path)
    assert saved.phase("holdout_freeze").status == "completed"
    assert saved.phase("holdout_freeze").artifact_path is not None


def test_promotion_requires_prior_gates(tmp_path):
    path = _make_manifest(tmp_path)
    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)

    artifact = workflow.run_phase("promotion_packet")

    assert artifact.status == "failed"
    assert artifact.payload["error"]["code"] == "DISCOVERY_PHASE_ORDER_BLOCKED"


def test_promotion_packet_with_candidate(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    for phase_id in [
        "learnings_review",
        "holdout_freeze",
        "structural_screen",
        "discovery_search",
        "walk_forward",
        "stability_check",
        "overfit_audit",
        "deployability_audit",
    ]:
        phase = manifest.phase(phase_id)
        phase.status = "completed"
    manifest.candidates.append(
        CandidateSpec(
            id="cand_a",
            label="Candidate A",
            verdict="PROMOTE",
            deployability="live_native",
            live_support_notes="Supported by current execution config.",
            psr=0.95,
            dsr=0.75,
            n_trials_raw=100,
            n_trials_effective=12,
        )
    )
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("promotion_packet")

    assert artifact.status == "completed"
    memo = Path(artifact.payload["memo_path"]).read_text()
    assert "Candidate A" in memo
    assert "PROMOTE" in memo


def test_command_phase_captures_logs(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    manifest.phase("learnings_review").status = "completed"
    manifest.phase("holdout_freeze").status = "completed"
    phase = manifest.phase("structural_screen")
    phase.command = [
        sys.executable,
        "-c",
        "print('structural ok')",
    ]
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("structural_screen")

    assert artifact.status == "completed"
    assert Path(artifact.stdout_path).read_text().strip() == "structural ok"


def test_native_phase_dispatch_updates_manifest(tmp_path, monkeypatch):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    manifest.phase("learnings_review").status = "completed"
    manifest.phase("holdout_freeze").status = "completed"
    save_manifest(manifest, path)

    def fake_native_phase(phase_id, manifest, *, repo_root, output_dir):
        assert phase_id == "structural_screen"
        manifest.candidates.append(
            CandidateSpec(
                id="native_cand",
                label="Native Candidate",
                source_phase="structural_screen",
                metrics={"total_trades": 10, "total_r": 3.0},
            )
        )
        return native_tools.NativePhaseOutcome(
            decision="passed",
            rationale="fake native phase",
            payload={"candidate_id": "native_cand"},
        )

    monkeypatch.setattr(native_tools, "run_native_phase", fake_native_phase)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("structural_screen")

    assert artifact.status == "completed"
    saved = load_manifest(path)
    assert saved.phase("structural_screen").status == "completed"
    assert saved.candidates[0].id == "native_cand"


def test_native_discovery_search_completes_without_search_space(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    for phase_id in ["learnings_review", "holdout_freeze", "structural_screen"]:
        manifest.phase(phase_id).status = "completed"
    manifest.candidates.append(
        CandidateSpec(
            id="baseline",
            label="Baseline",
            source_phase="structural_screen",
            metrics={"total_trades": 10, "total_r": 3.0},
        )
    )
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("discovery_search")

    assert artifact.status == "completed"
    assert artifact.decision == "base_only"
    assert Path(artifact.payload["detail_path"]).exists()


def test_native_mfe_diagnostic_uses_post_fill_price_path():
    idx = pd.date_range("2024-01-02 09:45", periods=4, freq="1min")
    df = pd.DataFrame(
        {
            "open": [100.0, 101.0, 103.0, 102.0],
            "high": [101.0, 104.0, 105.0, 103.0],
            "low": [99.5, 100.5, 102.0, 101.0],
            "close": [100.5, 103.0, 102.5, 102.0],
            "volume": [1, 1, 1, 1],
        },
        index=idx,
    )
    config = with_overrides(default_config(), rr=2.0, tp1_ratio=1.0, exit_mode="single_target")
    trade = TradeResult(
        date="2024-01-02",
        session="NY",
        direction=1,
        signal_bar=0,
        fill_bar=0,
        entry_price=100.0,
        stop_price=97.5,
        tp1_price=105.0,
        tp2_price=105.0,
        exit_type=EXIT_TP2_SINGLE,
        exit_bar=3,
        pnl_points=5.0,
        pnl_usd=1000.0,
        r_multiple=2.0,
        qty=1,
        half_qty=0,
        gap_size=1.0,
        risk_points=2.5,
        fill_time="2024-01-02 09:45:00",
        exit_time="2024-01-02 09:48:00",
    )

    diagnostic = native_tools._mfe_diagnostics([trade], df, config)

    assert diagnostic["summary"]["trade_count"] == 1
    assert diagnostic["summary"]["p50_mfe_r"] == 2.0
    assert diagnostic["summary"]["mfe_ge_target_pct"] == 100.0
    assert diagnostic["trades"][0]["mfe_r"] == 2.0


def test_walk_forward_stability_handles_categorical_params():
    config = default_config()
    folds = [
        WalkForwardFold(
            fold_index=index,
            is_start="2020-01-01",
            is_end="2020-12-31",
            oos_start="2021-01-01",
            oos_end="2021-03-31",
            best_params={"rr": rr, "direction_filter": direction},
            best_config=config,
            is_metrics={},
            is_objective_value=1.0,
            oos_metrics={},
            oos_objective_value=1.0,
            oos_trades=[],
        )
        for index, (rr, direction) in enumerate(
            [(1.0, "long"), (1.25, "long"), (1.0, "both")],
            start=1,
        )
    ]
    wf_result = WalkForwardResult(
        folds=folds,
        combined_oos_trades=[],
        combined_oos_metrics={},
        walk_forward_efficiency=1.0,
        is_months=12,
        oos_months=3,
        step_months=3,
        anchored=False,
        objective="calmar",
    )

    stability = analyze_parameter_stability(
        wf_result,
        {"rr": [1.0, 1.25, 1.5, 2.0], "direction_filter": ["long", "short", "both"]},
    )

    direction = next(param for param in stability.params if param.name == "direction_filter")
    assert direction.mode == "long"
    assert direction.stability_score == 0.6667


def test_stability_check_matches_anchor_candidate_by_params(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    manifest.search_budget["param_ranges"] = {
        "rr": [1.5, 2.0],
        "direction_filter": ["long", "short", "both"],
    }
    manifest.candidates.append(
        CandidateSpec(
            id="struct_anchor",
            label="Structural Anchor",
            params={"rr": 2.0, "direction_filter": "both"},
            metrics={"objective_value": 3.0},
        )
    )
    output_dir = tmp_path / "run"
    native_tools._write_detail(
        output_dir,
        "discovery_search",
        {
            "all_results": [
                {
                    "candidate_id": "cand_same_params",
                    "params": {"rr": 2.0, "direction_filter": "both"},
                    "objective_value": 3.0,
                },
                {
                    "candidate_id": "cand_rr_neighbor",
                    "params": {"rr": 1.5, "direction_filter": "both"},
                    "objective_value": 1.0,
                },
                {
                    "candidate_id": "cand_direction_neighbor",
                    "params": {"rr": 2.0, "direction_filter": "short"},
                    "objective_value": 1.0,
                },
            ]
        },
    )
    native_tools._write_detail(output_dir, "walk_forward", {})

    native_tools.run_stability_check(manifest, output_dir=output_dir)

    candidate = manifest.candidates[0]
    assert candidate.metrics["plateau_score"] == 0.0
    assert candidate.metrics["stability_passed"] is False
    assert candidate.verdict == "REJECT"


def test_overfit_audit_promotes_statistically_viable_candidate(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    for phase_id in [
        "learnings_review",
        "holdout_freeze",
        "structural_screen",
        "discovery_search",
        "walk_forward",
        "stability_check",
    ]:
        manifest.phase(phase_id).status = "completed"
    manifest.search_budget["min_trades"] = 5
    manifest.candidates.append(
        CandidateSpec(
            id="strong",
            label="Strong Candidate",
            verdict="PENDING",
            metrics={
                "total_trades": 20,
                "total_r": 11.0,
                "objective_value": 4.0,
                "selection_rank": 1,
                "stability_passed": True,
                "r_multiples": [1.0] * 15 + [-0.2] * 5,
                "trade_dates": [f"2024-01-{day:02d}" for day in range(1, 21)],
            },
        )
    )
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("overfit_audit")

    assert artifact.status == "completed"
    saved = load_manifest(path)
    candidate = saved.candidates[0]
    assert candidate.verdict == "PROMOTE"
    assert candidate.psr is not None and candidate.psr >= saved.gates.min_psr
    assert candidate.dsr is not None and candidate.dsr >= saved.gates.min_dsr


def test_overfit_audit_rejects_duplicate_candidate_configs(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    for phase_id in [
        "learnings_review",
        "holdout_freeze",
        "structural_screen",
        "discovery_search",
        "walk_forward",
        "stability_check",
    ]:
        manifest.phase(phase_id).status = "completed"
    metrics = {
        "total_trades": 20,
        "total_r": 11.0,
        "objective_value": 4.0,
        "stability_passed": True,
        "r_multiples": [1.0] * 15 + [-0.2] * 5,
        "trade_dates": [f"2024-01-{day:02d}" for day in range(1, 21)],
    }
    manifest.candidates.extend(
        [
            CandidateSpec(
                id="first",
                label="First Candidate",
                verdict="PENDING",
                params={"rr": 2.0, "ny_stop_atr_pct": 7.5},
                metrics={**metrics, "selection_rank": 1},
            ),
            CandidateSpec(
                id="dupe",
                label="Duplicate Candidate",
                verdict="PENDING",
                params={"rr": 2.0, "ny_stop_atr_pct": 7.5},
                metrics={**metrics, "selection_rank": 2},
            ),
        ]
    )
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("overfit_audit")

    assert artifact.status == "completed"
    saved = load_manifest(path)
    verdicts = {candidate.id: candidate.verdict for candidate in saved.candidates}
    assert verdicts["first"] == "PROMOTE"
    assert verdicts["dupe"] == "REJECT"
    assert "duplicate" in (saved.candidates[1].notes or "")


def test_deployability_audit_infers_live_native_label(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    for phase_id in [
        "learnings_review",
        "holdout_freeze",
        "structural_screen",
        "discovery_search",
        "walk_forward",
        "stability_check",
        "overfit_audit",
    ]:
        manifest.phase(phase_id).status = "completed"
    manifest.candidates.append(
        CandidateSpec(
            id="cand_auto_label",
            label="Auto Label Candidate",
            verdict="PROMOTE",
            params={"rr": 2.0, "ny_stop_atr_pct": 7.5},
            psr=0.95,
            dsr=0.75,
        )
    )
    manifest.candidates.append(
        CandidateSpec(
            id="cand_rejected_label",
            label="Rejected Candidate",
            verdict="REJECT",
            params={"rr": 2.0},
        )
    )
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("deployability_audit")

    assert artifact.status == "completed"
    saved = load_manifest(path)
    candidate = saved.candidates[0]
    assert candidate.deployability == "live_native"
    assert candidate.live_support_notes
    rejected = saved.candidates[1]
    assert rejected.deployability == "live_native"
    assert rejected.live_support_notes


def test_low_dsr_blocks_promotion(tmp_path):
    path = _make_manifest(tmp_path)
    manifest = load_manifest(path)
    for phase_id in [
        "learnings_review",
        "holdout_freeze",
        "structural_screen",
        "discovery_search",
        "walk_forward",
        "stability_check",
        "overfit_audit",
        "deployability_audit",
    ]:
        manifest.phase(phase_id).status = "completed"
    manifest.candidates.append(
        CandidateSpec(
            id="cand_weak",
            label="Weak Candidate",
            verdict="PROMOTE",
            deployability="live_native",
            live_support_notes="Supported.",
            psr=0.99,
            dsr=0.10,
        )
    )
    save_manifest(manifest, path)

    workflow = DiscoveryWorkflow(path, repo_root=REPO_ROOT)
    artifact = workflow.run_phase("promotion_packet")

    assert artifact.status == "failed"
    assert artifact.payload["error"]["code"] == "CANDIDATE_OVERFIT_GATE_FAILED"
