#!/usr/bin/env python3
"""Exact replay for the cross-asset ORB non-reject advancement queue."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

import trader.historical_backtest as hb  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config  # noqa: E402

RUN_ID = "cross_asset_orb_nonreject_advancement_20260612"
BACKTESTING_DIR = ROOT / "backtesting"
RESULT_DIR = BACKTESTING_DIR / "data" / "results" / RUN_ID
REPORT_PATH = BACKTESTING_DIR / "learnings" / "reports" / "CROSS_ASSET_ORB_NONREJECT_EXACT_REPLAY_20260612.md"
PROFILES_PATH = RESULT_DIR / "candidate_exec_profiles.json"
QUEUE_PATH = RESULT_DIR / "promotion_queue.csv"

COMBINED_PROFILE_NAME = "ORB_NONREJECT_ADVANCEMENT_20260612"
DISCOVERY_START = "2021-01-01"
DISCOVERY_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"


def _load_generated_profiles() -> dict[str, Any]:
    if not PROFILES_PATH.exists():
        raise FileNotFoundError(PROFILES_PATH)
    return json.loads(PROFILES_PATH.read_text())


def _exec_config_from_raw(name: str, raw: dict[str, Any]) -> ExecutionConfig:
    return ExecutionConfig(
        name=name,
        enabled=bool(raw.get("enabled", False)),
        max_open_contracts=float(raw.get("max_open_contracts", 999)),
        webhooks=[],
        session_overrides=dict(raw.get("sessions", {})),
        lsi_session_overrides=dict(raw.get("lsi_sessions", {})),
    )


def _patch_generated_profile_loader(profile_name: str, raw: dict[str, Any]) -> None:
    exec_config = _exec_config_from_raw(profile_name, raw)

    def _load_exec_configs(_config: dict | None = None):
        return [exec_config]

    hb.load_exec_configs = _load_exec_configs


def _candidate_symbols(queue: pd.DataFrame) -> list[str]:
    return sorted(str(value) for value in queue["asset"].dropna().unique())


def _run_window(
    *,
    config: dict[str, Any],
    profile_name: str,
    start: str,
    end: str,
    latest_data_ts,
) -> dict[str, Any]:
    return hb.run_profile_backtest_sync(
        config=config,
        profile_name=profile_name,
        start_date=start,
        end_date=end,
        latest_data_ts=latest_data_ts,
        label=f"EXEC EXACT {profile_name} {start} to {end}",
    )


def _summary_for_session(result: dict[str, Any], session_name: str) -> dict[str, Any]:
    trades = [trade for trade in result["trades"] if trade.get("session") == session_name]
    summary = hb._compute_summary(trades)
    return {
        "trades": int(summary["total_trades"]),
        "r": round(float(summary["total_r"]), 4),
        "net_r": round(float(summary["total_net_r"]), 4),
        "pf": round(float(summary["profit_factor"]), 4),
        "dd_r": round(float(summary["max_drawdown_r"]), 4),
        "calmar": round(float(summary["calmar_ratio"]), 4),
        "sharpe": round(float(summary["sharpe_ratio"]), 4),
        "win_rate": round(float(summary["win_rate"]), 4),
        "r_by_year": summary.get("r_by_year", {}),
        "exit_breakdown": summary.get("exit_breakdown", {}),
    }


def _candidate_rows(queue: pd.DataFrame, discovery: dict[str, Any], holdout: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, row in queue.sort_values("overall_rank").iterrows():
        session_name = str(row["session_name"])
        disc = _summary_for_session(discovery, session_name)
        hold = _summary_for_session(holdout, session_name)
        rows.append(
            {
                "overall_rank": int(row["overall_rank"]),
                "candidate_id": session_name,
                "source_rule_id": row["source_rule_id"],
                "verdict": row["verdict"],
                "lane": row["lane"],
                "asset": row["asset"],
                "session": row["session"],
                "exec_ticker": row["exec_ticker"],
                "research_disc_trades": int(row["discovery_trades"]),
                "research_disc_r": float(row["discovery_r"]),
                "exact_disc_trades": disc["trades"],
                "exact_disc_r": disc["r"],
                "exact_disc_net_r": disc["net_r"],
                "exact_disc_pf": disc["pf"],
                "exact_disc_dd_r": disc["dd_r"],
                "exact_disc_calmar": disc["calmar"],
                "research_holdout_trades": int(row["holdout_trades"]),
                "research_holdout_r": float(row["holdout_r"]),
                "exact_holdout_trades": hold["trades"],
                "exact_holdout_r": hold["r"],
                "exact_holdout_net_r": hold["net_r"],
                "exact_holdout_pf": hold["pf"],
                "exact_holdout_dd_r": hold["dd_r"],
                "exact_holdout_calmar": hold["calmar"],
                "disc_trade_delta": int(disc["trades"]) - int(row["discovery_trades"]),
                "disc_r_delta": round(float(disc["r"]) - float(row["discovery_r"]), 4),
                "holdout_trade_delta": int(hold["trades"]) - int(row["holdout_trades"]),
                "holdout_r_delta": round(float(hold["r"]) - float(row["holdout_r"]), 4),
                "exact_disc_r_by_year": disc["r_by_year"],
                "exact_holdout_r_by_year": hold["r_by_year"],
                "exact_disc_exit_breakdown": disc["exit_breakdown"],
                "exact_holdout_exit_breakdown": hold["exit_breakdown"],
            }
        )
    return rows


def _status(row: dict[str, Any]) -> str:
    disc_ok = row["exact_disc_trades"] >= 20 and row["exact_disc_r"] > 0 and row["exact_disc_pf"] > 1.0
    holdout_ok = row["exact_holdout_trades"] >= 5 and row["exact_holdout_r"] > 0 and row["exact_holdout_pf"] > 1.0
    if row["verdict"] == "PROMOTE_TO_EXACT_REPLAY" and disc_ok and holdout_ok:
        return "EXACT_REPLAY_PASS"
    if disc_ok:
        return "EXACT_REPLAY_WATCH"
    return "EXACT_REPLAY_FAIL"


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for _, key in columns:
            value = row.get(key)
            if value is None:
                values.append("")
            elif isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _render_report(payload: dict[str, Any]) -> str:
    rows = payload["candidate_summaries"]
    pass_rows = [row for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_PASS"]
    watch_rows = [row for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_WATCH"]
    fail_rows = [row for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_FAIL"]
    cols = [
        ("Rank", "overall_rank"),
        ("Cand", "candidate_id"),
        ("Rule", "source_rule_id"),
        ("Status", "exact_replay_status"),
        ("Research R", "research_disc_r"),
        ("Exact R", "exact_disc_r"),
        ("Exact PF", "exact_disc_pf"),
        ("Exact DD", "exact_disc_dd_r"),
        ("HO R", "exact_holdout_r"),
        ("HO PF", "exact_holdout_pf"),
        ("Delta R", "disc_r_delta"),
    ]
    return "\n".join(
        [
            "# Cross-Asset ORB Non-Reject Exact Replay",
            "",
            "## Summary",
            "",
            (
                f"Ran `{payload['profile_name']}` through the execution-engine exact replay for "
                f"discovery `{payload['discovery_window']['start']}`-`{payload['discovery_window']['end']}` "
                f"and holdout `{payload['holdout_window']['start']}`-`{payload['holdout_window']['end']}`."
            ),
            "",
            f"- Exact replay pass: `{len(pass_rows)}`",
            f"- Exact replay watch: `{len(watch_rows)}`",
            f"- Exact replay fail: `{len(fail_rows)}`",
            "",
            "## Pass",
            "",
            _markdown_table(pass_rows, cols),
            "",
            "## Watch",
            "",
            _markdown_table(watch_rows, cols),
            "",
            "## Fail",
            "",
            _markdown_table(fail_rows, cols),
            "",
            "## Artifacts",
            "",
            f"- `{RESULT_DIR / 'exact_replay_summary.csv'}`",
            f"- `{RESULT_DIR / 'exact_replay_payload.json'}`",
            f"- `{RESULT_DIR / 'exact_replay_trades.csv'}`",
            f"- `{RESULT_DIR / 'exact_replay_report.md'}`",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default=COMBINED_PROFILE_NAME)
    parser.add_argument("--discovery-start", default=DISCOVERY_START)
    parser.add_argument("--discovery-end", default=DISCOVERY_END)
    parser.add_argument("--holdout-start", default=HOLDOUT_START)
    args = parser.parse_args()

    profiles = _load_generated_profiles()
    if args.profile not in profiles:
        raise KeyError(f"{args.profile} not found in {PROFILES_PATH}")
    queue = pd.read_csv(QUEUE_PATH)
    _patch_generated_profile_loader(args.profile, profiles[args.profile])

    config = load_config(DEFAULT_CONFIG)
    symbols = _candidate_symbols(queue)
    common_end = hb.latest_common_end(symbols)
    holdout_end = common_end.date().isoformat()

    print(f"symbols={symbols}", flush=True)
    print(f"common_end={common_end.isoformat()}", flush=True)
    print(f"discovery={args.discovery_start}->{args.discovery_end}", flush=True)
    print(f"holdout={args.holdout_start}->{holdout_end}", flush=True)

    discovery = _run_window(
        config=config,
        profile_name=args.profile,
        start=args.discovery_start,
        end=args.discovery_end,
        latest_data_ts=common_end,
    )
    holdout = _run_window(
        config=config,
        profile_name=args.profile,
        start=args.holdout_start,
        end=holdout_end,
        latest_data_ts=common_end,
    )
    rows = _candidate_rows(queue, discovery, holdout)
    for row in rows:
        row["exact_replay_status"] = _status(row)

    trade_rows = []
    for window_name, result in (("discovery", discovery), ("holdout", holdout)):
        for trade in result["trades"]:
            trade_rows.append({"window": window_name, **trade})

    payload = {
        "run_id": RUN_ID,
        "profile_name": args.profile,
        "symbols": symbols,
        "common_end": common_end.isoformat(),
        "discovery_window": {"start": args.discovery_start, "end": args.discovery_end},
        "holdout_window": {"start": args.holdout_start, "end": holdout_end},
        "candidate_summaries": rows,
        "aggregate": {
            "discovery": discovery["summary"],
            "holdout": holdout["summary"],
        },
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(RESULT_DIR / "exact_replay_summary.csv", index=False)
    pd.DataFrame(trade_rows).to_csv(RESULT_DIR / "exact_replay_trades.csv", index=False)
    (RESULT_DIR / "exact_replay_payload.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    report = _render_report(payload)
    (RESULT_DIR / "exact_replay_report.md").write_text(report + "\n")
    REPORT_PATH.write_text(report + "\n")

    print(
        json.dumps(
            {
                "success": True,
                "profile": args.profile,
                "summary": str(RESULT_DIR / "exact_replay_summary.csv"),
                "report": str(REPORT_PATH),
                "pass": sum(1 for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_PASS"),
                "watch": sum(1 for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_WATCH"),
                "fail": sum(1 for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_FAIL"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
