#!/usr/bin/env python3
"""Exact replay for ALPHA_V1 ES_NY runner-trail candidates."""

from __future__ import annotations

import argparse
import copy
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader import historical_backtest as hb  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "alpha_v1_es_ny_runner_trail_exact_20260511"
BASE_PROFILE = "ALPHA_V1-A"
SESSION_KEY = "ES_NY"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"

RESULT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_ES_NY_RUNNER_TRAIL_EXACT_20260511.md"

WINDOWS = (
    ("full", FULL_START),
    ("last_2y", "2024-03-24"),
    ("last_1y", "2025-03-24"),
    ("holdout_2025p", "2025-01-01"),
)


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    overrides: dict[str, Any]
    rationale: str

    @property
    def profile_name(self) -> str:
        return f"EXACT_ES_NY_RUNNER_{self.key}".upper()[:120]


CANDIDATES = (
    Candidate(
        key="baseline",
        label="Current split: TP1 at 1R, runner to 5R or BE",
        overrides={
            "runner_trail_mode": "",
            "runner_trail_trigger_r": 0.0,
            "runner_trail_stop_r": 0.0,
            "runner_trail_step_r": 1.0,
            "runner_trail_gap_r": 1.0,
            "runner_trail_atr_pct": 0.0,
        },
        rationale="Incumbent live ALPHA_V1 ES_NY management.",
    ),
    Candidate(
        key="risk_gap_0p75r",
        label="Risk trail: keep runner stop 0.75R behind MFE",
        overrides={
            "runner_trail_mode": "risk",
            "runner_trail_trigger_r": 0.0,
            "runner_trail_stop_r": 0.0,
            "runner_trail_step_r": 1.0,
            "runner_trail_gap_r": 0.75,
            "runner_trail_atr_pct": 0.0,
        },
        rationale="Best recent candidate from the simulator sweep.",
    ),
    Candidate(
        key="atr_gap_5pct",
        label="ATR trail: keep runner stop 5% ATR behind MFE",
        overrides={
            "runner_trail_mode": "atr",
            "runner_trail_trigger_r": 0.0,
            "runner_trail_stop_r": 0.0,
            "runner_trail_step_r": 1.0,
            "runner_trail_gap_r": 1.0,
            "runner_trail_atr_pct": 5.0,
        },
        rationale="Best smoother drawdown candidate from the simulator sweep.",
    ),
)


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        out = float(value)
        return out if math.isfinite(out) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    if isinstance(data, np.integer):
        return int(data)
    if isinstance(data, np.floating):
        out = float(data)
        return out if math.isfinite(out) else None
    return data


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "inf" if value > 0 else "-"
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _alpha_profile() -> ExecutionConfig:
    profiles = {profile.name: profile for profile in load_exec_configs()}
    if BASE_PROFILE not in profiles:
        raise KeyError(f"Missing execution profile {BASE_PROFILE!r}")
    return profiles[BASE_PROFILE]


def _profile_for(candidate: Candidate, alpha: ExecutionConfig) -> ExecutionConfig:
    overrides = copy.deepcopy(alpha.session_overrides[SESSION_KEY])
    overrides.update(candidate.overrides)
    return ExecutionConfig(
        name=candidate.profile_name,
        enabled=True,
        max_open_contracts=alpha.max_open_contracts,
        webhooks=[],
        session_overrides={SESSION_KEY: overrides},
        lsi_session_overrides={},
    )


def _run_exact(config: dict[str, Any], candidate: Candidate, profile: ExecutionConfig, refresh: bool) -> dict[str, Any]:
    cache_path = RESULT_DIR / f"exact_{candidate.key}.json"
    if cache_path.exists() and not refresh:
        print(f"[cache] {candidate.key}", flush=True)
        return json.loads(cache_path.read_text())

    print(f"[run] {candidate.key}: {candidate.label}", flush=True)
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    started = time.perf_counter()
    try:
        result = hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"ALPHA_V1 ES_NY Runner Trail Exact {candidate.key} {FULL_START} to {END_DATE}",
        )
    finally:
        hb.load_exec_configs = original_loader

    payload = {
        "candidate": {
            "key": candidate.key,
            "label": candidate.label,
            "rationale": candidate.rationale,
            "overrides": candidate.overrides,
        },
        "profile_name": profile.name,
        "profile_session_overrides": _safe_json(profile.session_overrides),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
        "result": result,
    }
    cache_path.write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True, default=_json_default) + "\n")
    return payload


def _slice(trades: list[dict[str, Any]], start: str, end: str = END_DATE) -> list[dict[str, Any]]:
    return [trade for trade in trades if start <= str(trade.get("date", "")) <= end]


def _positive_runner_stop_count(trades: list[dict[str, Any]]) -> int:
    return sum(
        1
        for trade in trades
        if trade.get("exit_type") == "tp1_be" and float(trade.get("r_multiple", 0.0)) > 0.5001
    )


def _metrics(candidate: Candidate, payload: dict[str, Any], window: str, start: str) -> dict[str, Any]:
    trades = _slice(payload["result"]["trades"], start)
    summary = hb._compute_summary(trades)
    return {
        "candidate": candidate.key,
        "label": candidate.label,
        "window": window,
        "start": start,
        "end": END_DATE,
        "trades": int(summary["total_trades"]),
        "total_r": _round(summary["total_r"]),
        "net_r": _round(summary.get("total_net_r")),
        "profit_factor": _round(summary["profit_factor"], 3),
        "max_dd_r": _round(summary["max_drawdown_r"]),
        "calmar": _round(summary["calmar_ratio"], 3),
        "win_rate_pct": _round(summary["win_rate"] * 100.0),
        "tp1_be": int(summary["exit_breakdown"].get("tp1_be", 0)),
        "tp1_tp2": int(summary["exit_breakdown"].get("tp1_tp2", 0)),
        "tp2_direct": int(summary["exit_breakdown"].get("tp2_direct", 0)),
        "positive_runner_stops": _positive_runner_stop_count(trades),
    }


def _build_summary(payloads: dict[str, dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    candidates_by_key = {candidate.key: candidate for candidate in CANDIDATES}
    for key, payload in payloads.items():
        candidate = candidates_by_key[key]
        for window, start in WINDOWS:
            rows.append(_metrics(candidate, payload, window, start))
    return pd.DataFrame(rows)


def _report(summary: pd.DataFrame, payloads: dict[str, dict[str, Any]]) -> str:
    full = summary[summary["window"] == "full"].set_index("candidate")
    recent = summary[summary["window"] == "holdout_2025p"].set_index("candidate")
    last2 = summary[summary["window"] == "last_2y"].set_index("candidate")

    baseline = full.loc["baseline"]
    risk = full.loc["risk_gap_0p75r"]
    atr = full.loc["atr_gap_5pct"]
    risk_recent = recent.loc["risk_gap_0p75r"]
    atr_recent = recent.loc["atr_gap_5pct"]

    if risk_recent["total_r"] > recent.loc["baseline"]["total_r"] and risk["total_r"] >= 0:
        verdict = (
            "Risk-gap 0.75R remains the lead candidate for a live paper/shadow branch: "
            "it directly targets the recent 3-4R giveback problem while keeping full-period expectancy positive."
        )
    elif atr["max_dd_r"] > baseline["max_dd_r"] and atr["calmar"] >= baseline["calmar"]:
        verdict = (
            "ATR 5% is the lead risk-control candidate: it smooths drawdown without a clear recent edge sacrifice."
        )
    else:
        verdict = (
            "Baseline remains the production incumbent; the runner trails need more evidence before replacing it."
        )

    table_cols = [
        "candidate",
        "window",
        "trades",
        "total_r",
        "profit_factor",
        "max_dd_r",
        "calmar",
        "win_rate_pct",
        "positive_runner_stops",
        "tp1_be",
        "tp1_tp2",
    ]
    table = summary[table_cols].to_markdown(index=False)

    lines = [
        "# ALPHA_V1 ES_NY Runner-Trail Exact Replay (2026-05-11)",
        "",
        f"- Replay: exact/live execution engine, `{FULL_START}` through `{END_DATE}`.",
        "- Scope: ES_NY only, ALPHA_V1-A base profile, 1s execution replay where active.",
        "- Candidates promoted from the simulator sweep: `risk_gap_0p75r` and `atr_gap_5pct`.",
        "",
        "## Verdict",
        "",
        verdict,
        "",
        "## Metrics",
        "",
        table,
        "",
        "## Candidate Notes",
        "",
        (
            f"- Baseline full: {_fmt(baseline['total_r'])}R, PF {_fmt(baseline['profit_factor'])}, "
            f"DD {_fmt(baseline['max_dd_r'])}R."
        ),
        (
            f"- Risk 0.75R full: {_fmt(risk['total_r'])}R, PF {_fmt(risk['profit_factor'])}, "
            f"DD {_fmt(risk['max_dd_r'])}R; 2025+ {_fmt(risk_recent['total_r'])}R."
        ),
        (
            f"- ATR 5% full: {_fmt(atr['total_r'])}R, PF {_fmt(atr['profit_factor'])}, "
            f"DD {_fmt(atr['max_dd_r'])}R; 2025+ {_fmt(atr_recent['total_r'])}R."
        ),
        (
            f"- Last-2Y risk vs ATR: {_fmt(last2.loc['risk_gap_0p75r']['total_r'])}R "
            f"vs {_fmt(last2.loc['atr_gap_5pct']['total_r'])}R."
        ),
        "",
        "## Artifacts",
        "",
        f"- Summary CSV: `backtesting/data/results/{RUN_SLUG}/summary.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]

    for key, payload in payloads.items():
        lines.append(
            f"- `{key}` exact cache: `backtesting/data/results/{RUN_SLUG}/exact_{key}.json` "
            f"({payload['elapsed_seconds']}s)"
        )

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="Ignore existing exact replay caches.")
    args = parser.parse_args()

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    config = load_config(DEFAULT_CONFIG)
    alpha = _alpha_profile()

    payloads: dict[str, dict[str, Any]] = {}
    for candidate in CANDIDATES:
        profile = _profile_for(candidate, alpha)
        payloads[candidate.key] = _run_exact(config, candidate, profile, refresh=args.refresh)

    summary = _build_summary(payloads)
    summary_path = RESULT_DIR / "summary.csv"
    json_path = RESULT_DIR / "summary.json"
    summary.to_csv(summary_path, index=False)
    json_path.write_text(
        json.dumps(
            {
                "run_slug": RUN_SLUG,
                "base_profile": BASE_PROFILE,
                "session": SESSION_KEY,
                "full_start": FULL_START,
                "end_date": END_DATE,
                "rows": summary.to_dict(orient="records"),
            },
            indent=2,
            sort_keys=True,
            default=_json_default,
        )
        + "\n"
    )
    REPORT_PATH.write_text(_report(summary, payloads))

    print(f"[done] summary: {summary_path}", flush=True)
    print(f"[done] report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
