from __future__ import annotations

from pathlib import Path

from orb_backtest.research_memory import (
    ResearchMemoryConfig,
    build_research_memory_index,
    ensure_research_memory_index,
    index_needs_rebuild,
    load_research_memory_index,
    search_research_memory,
)


def test_research_memory_retrieves_source_linked_prior_conclusion(tmp_path: Path):
    repo = _make_repo(tmp_path)
    config = ResearchMemoryConfig(repo_root=repo)

    index = build_research_memory_index(config)
    hits = search_research_memory(
        "Did NQ Asia ORB survive strict stress with doubled commission?",
        config,
        index=index,
        top_k=3,
    )

    assert hits
    assert hits[0].chunk.source_path == "backtesting/learnings/reports/ORB_STRICT_STRESS.md"
    assert hits[0].chunk.start_line == 1
    assert "doubled commission" in hits[0].chunk.text
    assert "strict stress" in hits[0].chunk.text


def test_research_memory_rebuilds_when_sources_change(tmp_path: Path):
    repo = _make_repo(tmp_path)
    config = ResearchMemoryConfig(repo_root=repo)

    build_research_memory_index(config)
    index = load_research_memory_index(config)
    assert not index_needs_rebuild(config, index)

    new_report = repo / "backtesting" / "learnings" / "reports" / "NEW_BRANCH.md"
    new_report.write_text("# New Branch\n\nA fresh deployability note.\n")

    assert index_needs_rebuild(config, index)
    refreshed = ensure_research_memory_index(config)
    hits = search_research_memory("fresh deployability", config, index=refreshed)

    assert hits[0].chunk.source_path == "backtesting/learnings/reports/NEW_BRANCH.md"


def test_research_memory_prefers_asset_specific_source_path(tmp_path: Path):
    repo = _make_repo(tmp_path)
    asset_dir = repo / "backtesting" / "learnings" / "asset"
    asset_dir.mkdir(parents=True)
    shared_body = (
        "Plain ORB strict stress used doubled commission and adverse ticks. "
        "Holdout stayed closed."
    )
    (asset_dir / "NQ.md").write_text(f"# Plain ORB Stress\n\n{shared_body}\n")
    (asset_dir / "RTY.md").write_text(f"# Plain ORB Stress\n\n{shared_body}\n")
    config = ResearchMemoryConfig(
        repo_root=repo,
        include_globs=("backtesting/learnings/asset/*.md",),
    )

    index = build_research_memory_index(config)
    hits = search_research_memory("NQ ORB strict stress doubled commission", config, index=index)

    assert hits[0].chunk.source_path == "backtesting/learnings/asset/NQ.md"


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "trading_engine"
    reports = repo / "backtesting" / "learnings" / "reports"
    registry = repo / "backtesting" / "learnings" / "registry"
    reports.mkdir(parents=True)
    registry.mkdir(parents=True)

    (repo / "AGENTS.md").write_text("# Agent Instructions\n\nUse deterministic validation.\n")
    (repo / "backtesting" / "AGENTS.md").write_text(
        "# Backtesting Instructions\n\nHoldout stays closed until strict gates pass.\n"
    )
    (repo / "backtesting" / "README.md").write_text("# Backtesting\n\nResearch engine.\n")
    (registry / "catalog.json").write_text("{}\n")
    (reports / "ORB_STRICT_STRESS.md").write_text(
        "# ORB Strict Stress\n\n"
        "NQ Asia ORB exact replay looked promising, but strict stress failed under "
        "doubled commission and adverse ticks. Do not promote without a new thesis.\n"
    )
    return repo
