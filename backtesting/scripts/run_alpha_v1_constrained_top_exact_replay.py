#!/usr/bin/env python3
"""Exact replay for the top constrained active ALPHA_V1 target profile.

This is a temporary in-memory replay. It does not edit execution configs.
"""

from __future__ import annotations

import copy
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader import historical_backtest as hb  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "alpha_v1_constrained_top_exact_replay_20260504"
PROFILE_NAME = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"
RESULT_DIR = ROOT / "backtesting" / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "ALPHA_V1_CONSTRAINED_TOP_EXACT_REPLAY_20260504.md"

TOP_TARGETS = {
    "sessions": {
        "NQ_Asia": {"rr": 3.0, "tp1_ratio": 0.5},
        "ES_Asia": {"rr": 1.5, "tp1_ratio": 1.25 / 1.5},
        "ES_NY": {"rr": 2.5, "tp1_ratio": 0.5},
    },
    "lsi_sessions": {
        "NQ_NY_LSI": {"rr": 3.0, "tp1_ratio": 0.5},
    },
}


def _clone_top_profile(base: ExecutionConfig) -> ExecutionConfig:
    profile = copy.deepcopy(base)
    profile.name = "ALPHA_V1_CONSTRAINED_TOP_RESEARCH_SHORTLIST"
    profile.webhooks = []
    for session, values in TOP_TARGETS["sessions"].items():
        if session in profile.session_overrides:
            profile.session_overrides[session] = {**profile.session_overrides[session], **values}
    for session, values in TOP_TARGETS["lsi_sessions"].items():
        if session in profile.lsi_session_overrides:
            profile.lsi_session_overrides[session] = {**profile.lsi_session_overrides[session], **values}
    return profile


def _metrics(summary: dict[str, Any]) -> dict[str, Any]:
    trades = int(summary.get("total_trades", 0) or 0)
    return {
        "trades": trades,
        "net_r": round(float(summary.get("total_r", 0.0) or 0.0), 2),
        "wr_pct": round(float(summary.get("win_rate", 0.0) or 0.0) * 100.0, 2),
        "pf": round(float(summary.get("profit_factor", 0.0) or 0.0), 3),
        "max_dd_r": round(float(summary.get("max_drawdown_r", 0.0) or 0.0), 2),
        "sharpe": round(float(summary.get("sharpe_ratio", 0.0) or 0.0), 3),
        "calmar": round(float(summary.get("calmar_ratio", 0.0) or 0.0), 3),
    }


def _slice(trades: list[dict[str, Any]], start: str, end: str, session: str | None = None) -> list[dict[str, Any]]:
    return [
        trade for trade in trades
        if start <= str(trade.get("date", "")) <= end
        and (session is None or trade.get("session") == session)
    ]


def _window_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    windows = {
        "last_1y": (LAST_1Y_START, END_DATE),
        "last_2y": (LAST_2Y_START, END_DATE),
        "full": (FULL_START, END_DATE),
    }
    sessions = sorted({str(trade.get("session")) for trade in trades})
    rows: list[dict[str, Any]] = []
    for window, (start, end) in windows.items():
        rows.append({"scope": "combined", "window": window, **_metrics(hb._compute_summary(_slice(trades, start, end)))})
        for session in sessions:
            rows.append({"scope": session, "window": window, **_metrics(hb._compute_summary(_slice(trades, start, end, session)))})
    return rows


def _write_report(payload: dict[str, Any]) -> None:
    rows = payload["window_rows"]
    lines = [
        "# ALPHA_V1 Constrained Top Exact Replay",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Base profile: `{PROFILE_NAME}` cloned in memory; `execution/config/exec_configs.json` was not edited.",
        f"- Window: `{FULL_START}` to `{END_DATE}`.",
        "- Purpose: exact replay the top constrained active-ALPHA target profile from the broad research sweep.",
        "",
        "## Target Overrides",
        "",
        "```json",
        json.dumps(TOP_TARGETS, indent=2, sort_keys=True),
        "```",
        "",
        "## Exact Metrics",
        "",
        "| Scope | Window | Trades | Net R | WR | PF | DD | Sharpe | Calmar |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['scope']} | {row['window']} | {row['trades']} | {row['net_r']:.2f} | "
            f"{row['wr_pct']:.2f}% | {row['pf']:.3f} | {row['max_dd_r']:.2f} | "
            f"{row['sharpe']:.3f} | {row['calmar']:.3f} |"
        )
    lines.extend(
        [
            "",
            "## Read",
            "",
            "- This exact pass validates execution-engine behavior for the active-leg constrained target shortlist only.",
            "- It does not exact-replay the conditional research branches; those still need separate implementation/parity work before promotion.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    profiles = {profile.name: profile for profile in load_exec_configs(config)}
    profile = _clone_top_profile(profiles[PROFILE_NAME])

    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        result = hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"EXEC EXACT {profile.name} constrained top {FULL_START} to {END_DATE}",
        )
    finally:
        hb.load_exec_configs = original_loader

    trades = result.get("trades", [])
    window_rows = _window_rows(trades)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "base_profile": PROFILE_NAME,
        "replay_profile": profile.name,
        "targets": TOP_TARGETS,
        "summary": result.get("summary", {}),
        "window_rows": window_rows,
        "paths": {
            "json": str(RESULT_DIR / "summary.json"),
            "trades_csv": str(RESULT_DIR / "exact_trades.csv"),
            "window_metrics_csv": str(RESULT_DIR / "window_metrics.csv"),
            "report": str(REPORT_PATH),
        },
    }
    pd.DataFrame(trades).to_csv(RESULT_DIR / "exact_trades.csv", index=False)
    pd.DataFrame(window_rows).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2, default=str, sort_keys=True) + "\n")
    _write_report(payload)
    print(json.dumps({"result_dir": str(RESULT_DIR), "report": str(REPORT_PATH), "summary": payload["summary"]}, indent=2, default=str))


if __name__ == "__main__":
    main()
