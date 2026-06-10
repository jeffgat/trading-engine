#!/usr/bin/env python3
"""Run manifest-driven strategy discovery workflows.

This runner orchestrates deterministic research tools from a JSON manifest. It
does not choose strategy parameters by itself; it enforces the workflow gates
and writes a reproducible artifact trail for each phase.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.discovery import (  # noqa: E402
    DataWindow,
    DiscoveryWorkflow,
    create_default_manifest,
    save_manifest,
)
from orb_backtest.errors import BacktestError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic discovery workflow runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="Create a starter discovery manifest")
    init.add_argument("--output", required=True, help="Manifest JSON path")
    init.add_argument("--run-id", required=True)
    init.add_argument("--thesis", required=True)
    init.add_argument("--asset", required=True)
    init.add_argument("--strategy-family", required=True)
    init.add_argument("--start", required=True, help="Discovery data start date")
    init.add_argument("--pre-holdout-end", required=True)
    init.add_argument("--holdout-start", required=True)
    init.add_argument("--holdout-end", default=None)
    init.add_argument("--output-dir", default=None, help="Run output directory")
    init.add_argument("--data-file", default=None, help="5m data file/path for native phases")
    init.add_argument("--sessions", default=None, help="Comma-separated sessions, e.g. NY or NY,Asia")
    init.add_argument("--strategy", default=None, help="StrategyConfig strategy name")
    init.add_argument("--direction", default=None, choices=["both", "long", "short"])
    init.add_argument("--base-overrides-json", default="{}", help="JSON object merged into base_config")
    init.add_argument("--param-ranges-json", default="{}", help="JSON object for search_budget.param_ranges")
    init.add_argument("--rank-by", default=None, help="Optimization objective, e.g. calmar")
    init.add_argument("--max-trials", type=int, default=None)
    init.add_argument("--top-n", type=int, default=None)
    init.add_argument("--min-trades", type=int, default=None)
    init.add_argument("--disable-walk-forward", action="store_true")

    validate = sub.add_parser("validate", help="Validate a manifest")
    validate.add_argument("manifest")

    status = sub.add_parser("status", help="Print workflow status")
    status.add_argument("manifest")

    run = sub.add_parser("run", help="Run one phase or all pending phases")
    run.add_argument("manifest")
    run.add_argument("--phase", default=None, help="Run one phase id")
    run.add_argument("--all", action="store_true", help="Run all pending phases")
    run.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    try:
        if args.cmd == "init":
            return _cmd_init(args)
        if args.cmd == "validate":
            return _cmd_validate(args)
        if args.cmd == "status":
            return _cmd_status(args)
        if args.cmd == "run":
            return _cmd_run(args)
    except BacktestError as exc:
        print(json.dumps({"success": False, "error": exc.to_dict()}, indent=2), file=sys.stderr)
        return exc.status_code if 0 < exc.status_code < 128 else 1
    return 1


def _cmd_init(args) -> int:
    data = DataWindow(
        start=args.start,
        pre_holdout_end=args.pre_holdout_end,
        holdout_start=args.holdout_start,
        holdout_end=args.holdout_end,
    )
    manifest = create_default_manifest(
        run_id=args.run_id,
        thesis=args.thesis,
        asset=args.asset,
        strategy_family=args.strategy_family,
        data=data,
        output_dir=args.output_dir,
    )
    try:
        base_overrides = json.loads(args.base_overrides_json)
        param_ranges = json.loads(args.param_ranges_json)
    except json.JSONDecodeError as exc:
        print(json.dumps({"success": False, "error": f"Invalid JSON: {exc}"}, indent=2), file=sys.stderr)
        return 2
    if not isinstance(base_overrides, dict) or not isinstance(param_ranges, dict):
        print(json.dumps({"success": False, "error": "base/search JSON values must be objects"}, indent=2), file=sys.stderr)
        return 2

    base_config = dict(base_overrides)
    if args.data_file:
        base_config["data_file"] = args.data_file
    if args.sessions:
        base_config["sessions"] = [item.strip() for item in args.sessions.split(",") if item.strip()]
    if args.strategy:
        base_config["strategy"] = args.strategy
    if args.direction:
        base_config["direction"] = args.direction
    manifest.base_config = base_config

    search_budget = dict(manifest.search_budget)
    if param_ranges:
        search_budget["param_ranges"] = param_ranges
    if args.rank_by:
        search_budget["rank_by"] = args.rank_by
    if args.max_trials is not None:
        search_budget["max_trials"] = args.max_trials
    if args.top_n is not None:
        search_budget["top_n"] = args.top_n
    if args.min_trades is not None:
        search_budget["min_trades"] = args.min_trades
    if args.disable_walk_forward:
        search_budget["walk_forward"] = {"enabled": False}
    manifest.search_budget = search_budget

    errors = manifest.validate()
    if errors:
        print(json.dumps({"success": False, "errors": errors}, indent=2), file=sys.stderr)
        return 2
    save_manifest(manifest, args.output)
    print(json.dumps({"success": True, "manifest": str(Path(args.output).resolve())}, indent=2))
    return 0


def _cmd_validate(args) -> int:
    workflow = DiscoveryWorkflow(args.manifest, repo_root=ROOT)
    workflow.validate()
    print(json.dumps({"success": True, "manifest": str(Path(args.manifest).resolve())}, indent=2))
    return 0


def _cmd_status(args) -> int:
    workflow = DiscoveryWorkflow(args.manifest, repo_root=ROOT)
    print(json.dumps(workflow.status(), indent=2))
    return 0


def _cmd_run(args) -> int:
    workflow = DiscoveryWorkflow(args.manifest, repo_root=ROOT)
    if args.phase and args.all:
        print("Use either --phase or --all, not both.", file=sys.stderr)
        return 2
    if not args.phase and not args.all:
        print("Specify --phase <id> or --all.", file=sys.stderr)
        return 2
    if args.phase:
        artifact = workflow.run_phase(args.phase, dry_run=args.dry_run)
        print(json.dumps({"success": artifact.status == "completed", "artifact": artifact.__dict__}, indent=2))
        return 0 if artifact.status == "completed" else 1
    artifacts = workflow.run_all(dry_run=args.dry_run)
    print(json.dumps({"success": all(a.status == "completed" for a in artifacts), "artifacts": [a.__dict__ for a in artifacts]}, indent=2))
    return 0 if all(a.status == "completed" for a in artifacts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
