#!/usr/bin/env python3
"""Exact live-engine replay for selected ALPHA_V1 stop/target candidates.

This script creates temporary in-memory execution profiles only. It does not
edit execution/config/exec_configs.json.
"""

from __future__ import annotations

import copy
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader import historical_backtest as hb  # noqa: E402
from trader.main import (  # noqa: E402
    DEFAULT_CONFIG,
    SESSION_CONFIGS,
    ExecutionConfig,
    load_config,
    load_exec_configs,
)


RUN_SLUG = "alpha_v1_stop_target_live_engine_replay_20260504"
BASE_PROFILE = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"

RESULT_DIR = ROOT / "backtesting" / "data" / "results" / RUN_SLUG
REPORT_PATH = (
    ROOT
    / "backtesting"
    / "learnings"
    / "reports"
    / "ALPHA_V1_STOP_TARGET_LIVE_ENGINE_REPLAY_20260504.md"
)


@dataclass(frozen=True)
class LiveCandidate:
    key: str
    label: str
    rank: int
    session_key: str
    rr: float
    tp1_ratio: float
    stop_label: str
    stop_updates: dict[str, Any]
    deployability: str
    live_support_notes: str
    exact_replay_required: str
    base: str
    full_overrides: dict[str, Any] | None = None

    @property
    def tp1_r(self) -> float:
        return self.rr * self.tp1_ratio


SUPPORTED_CANDIDATES = [
    LiveCandidate(
        key="nq_asia_orb_orb125_rr2p5_tp0p60",
        label="NQ Asia ORB",
        rank=1,
        session_key="NQ_Asia",
        rr=2.5,
        tp1_ratio=0.60,
        stop_label="ORB 125%",
        stop_updates={"stop_basis": "orb", "stop_orb_pct": 125.0, "stop_atr_pct": 0.0},
        deployability="live_native",
        live_support_notes="Active ALPHA_V1 ORB leg; replayed by cloning ALPHA_V1-A NQ_Asia and overriding stop/target fields.",
        exact_replay_required="complete",
        base="ALPHA_V1-A NQ_Asia",
    ),
    LiveCandidate(
        key="es_asia_orb_orb50_rr2_tp0p75",
        label="ES Asia ORB",
        rank=2,
        session_key="ES_Asia",
        rr=2.0,
        tp1_ratio=0.75,
        stop_label="ORB 50%",
        stop_updates={"stop_basis": "orb", "stop_orb_pct": 50.0, "stop_atr_pct": 0.0},
        deployability="live_native",
        live_support_notes="Active ALPHA_V1 ORB leg; replayed by cloning ALPHA_V1-A ES_Asia and overriding stop/target fields.",
        exact_replay_required="complete",
        base="ALPHA_V1-A ES_Asia",
    ),
    LiveCandidate(
        key="es_asia_b_ungated_atr12_rr2_tp0p75",
        label="ES Asia-B ungated",
        rank=3,
        session_key="ES_Asia",
        rr=2.0,
        tp1_ratio=0.75,
        stop_label="ATR 12%",
        stop_updates={"stop_basis": "atr", "stop_atr_pct": 12.0, "stop_orb_pct": 0.0},
        deployability="live_native",
        live_support_notes="Standard live ORB continuation fields, no regime gate; replayed as a temporary ES_Asia branch profile.",
        exact_replay_required="complete",
        base="SESSION_CONFIGS ES_Asia branch override",
        full_overrides={
            "orb_start": "20:00",
            "orb_end": "20:15",
            "entry_start": "20:15",
            "entry_end": "23:15",
            "flat_start": "04:00",
            "flat_end": "07:00",
            "stop_basis": "atr",
            "stop_atr_pct": 12.0,
            "stop_orb_pct": 0.0,
            "gap_filter_basis": "atr",
            "min_gap_atr_pct": 1.0,
            "min_gap_orb_pct": 0.0,
            "max_gap_atr_pct": 0,
            "instrument": "ES",
            "atr_length": 14,
            "long_only": True,
            "short_only": False,
            "icf_enabled": False,
            "excluded_dow": None,
            "fomc_exclusion": False,
            "min_stop_pts": 3.0,
            "min_tp1_pts": 3.0,
            "risk_usd": 100,
            "max_single_risk_usd": 300,
        },
    ),
    LiveCandidate(
        key="nq_ny_orb_r11_atr7_rr3_tp0p50",
        label="NQ NY ORB R11",
        rank=4,
        session_key="NQ_NY",
        rr=3.0,
        tp1_ratio=0.50,
        stop_label="ATR 7%",
        stop_updates={"stop_basis": "atr", "stop_atr_pct": 7.0, "stop_orb_pct": 0.0},
        deployability="live_native",
        live_support_notes="Standard live ORB continuation fields; replayed using the NQ_NY R11 session definition with target override.",
        exact_replay_required="complete",
        base="research NQ_NY R11 branch override",
        full_overrides={
            "orb_start": "09:30",
            "orb_end": "09:50",
            "entry_start": "09:50",
            "entry_end": "12:00",
            "flat_start": "15:30",
            "flat_end": "16:00",
            "stop_basis": "atr",
            "stop_atr_pct": 7.0,
            "stop_orb_pct": 0.0,
            "gap_filter_basis": "atr",
            "min_gap_atr_pct": 2.5,
            "max_gap_atr_pct": 0,
            "instrument": "NQ",
            "atr_length": 12,
            "long_only": True,
            "short_only": False,
            "icf_enabled": False,
            "excluded_dow": 4,
            "fomc_exclusion": False,
            "min_stop_pts": 0.0,
            "min_tp1_pts": 0.0,
            "risk_usd": 200,
            "max_single_risk_usd": 300,
        },
    ),
    LiveCandidate(
        key="es_ny_orb_orb50_rr3_tp0p50",
        label="ES NY ORB",
        rank=6,
        session_key="ES_NY",
        rr=3.0,
        tp1_ratio=0.50,
        stop_label="ORB 50%",
        stop_updates={"stop_basis": "orb", "stop_orb_pct": 50.0, "stop_atr_pct": 0.0},
        deployability="live_native",
        live_support_notes="Active ALPHA_V1 ORB leg; replayed by cloning ALPHA_V1-A ES_NY and overriding stop/target fields.",
        exact_replay_required="complete",
        base="ALPHA_V1-A ES_NY",
    ),
]

BLOCKED_CANDIDATES = [
    {
        "rank": 5,
        "key": "nq_ny_cisd_additive_no_thu_atr10_rr2p5_tp0p40",
        "label": "NQ CISD additive noThu",
        "stop": "ATR 10%",
        "rr": 2.5,
        "tp1_ratio": 0.40,
        "tp1_r": 1.0,
        "deployability": "research_only",
        "live_support_notes": (
            "Blocked for exact live replay: the current execution engine does not expose the "
            "research CISD/additive confirmation fields required by this branch. It should not "
            "be approximated with legacy LSI or plain ORB replay."
        ),
        "exact_replay_required": "yes_after_live_engine_parity",
    }
]


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _round(value: Any, digits: int = 2) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(out):
        return 0.0
    return round(out, digits)


def _metrics(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "trades": int(summary.get("total_trades", 0) or 0),
        "net_r": _round(summary.get("total_r", 0.0), 2),
        "wr_pct": _round(float(summary.get("win_rate", 0.0) or 0.0) * 100.0, 2),
        "pf": _round(summary.get("profit_factor", 0.0), 3),
        "max_dd_r": _round(summary.get("max_drawdown_r", 0.0), 2),
        "sharpe": _round(summary.get("sharpe_ratio", 0.0), 3),
        "calmar": _round(summary.get("calmar_ratio", 0.0), 3),
    }


def _slice(trades: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [trade for trade in trades if start <= str(trade.get("date", "")) <= end]


def _candidate_overrides(candidate: LiveCandidate, alpha: ExecutionConfig) -> dict[str, Any]:
    if candidate.full_overrides is not None:
        overrides = copy.deepcopy(candidate.full_overrides)
    elif candidate.session_key in alpha.session_overrides:
        overrides = copy.deepcopy(alpha.session_overrides[candidate.session_key])
    else:
        overrides = copy.deepcopy(SESSION_CONFIGS[candidate.session_key])
    overrides.update(candidate.stop_updates)
    overrides.update({"rr": candidate.rr, "tp1_ratio": candidate.tp1_ratio})
    return overrides


def _profile_for(candidate: LiveCandidate, alpha: ExecutionConfig) -> ExecutionConfig:
    return ExecutionConfig(
        name=f"EXACT_{candidate.key}",
        enabled=True,
        max_open_contracts=20,
        webhooks=[],
        session_overrides={candidate.session_key: _candidate_overrides(candidate, alpha)},
        lsi_session_overrides={},
    )


def _run_candidate(config: dict[str, Any], profile: ExecutionConfig) -> dict[str, Any]:
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        return hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"EXEC EXACT {profile.name} {FULL_START} to {END_DATE}",
        )
    finally:
        hb.load_exec_configs = original_loader


def _window_rows(candidate: LiveCandidate, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for window, start in (
        ("last_1y", LAST_1Y_START),
        ("last_2y", LAST_2Y_START),
        ("full", FULL_START),
    ):
        rows.append(
            {
                "rank": candidate.rank,
                "candidate": candidate.key,
                "label": candidate.label,
                "window": window,
                "start": start,
                "end": END_DATE,
                "stop": candidate.stop_label,
                "rr": candidate.rr,
                "tp1_ratio": candidate.tp1_ratio,
                "tp1_r": candidate.tp1_r,
                "deployability": candidate.deployability,
                "live_support_notes": candidate.live_support_notes,
                "exact_replay_required": candidate.exact_replay_required,
                **_metrics(hb._compute_summary(_slice(trades, start, END_DATE))),
            }
        )
    return rows


def _score(row_by_window: dict[str, dict[str, Any]]) -> float:
    last1 = row_by_window["last_1y"]
    last2 = row_by_window["last_2y"]
    full = row_by_window["full"]
    return (
        float(last1["net_r"]) * 0.55
        + float(last2["net_r"]) * 0.30
        + float(full["net_r"]) * 0.15
        + float(full["pf"]) * 2.0
        + float(full["max_dd_r"]) * 0.10
    )


def _rank_rows(window_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, dict[str, Any]]] = {}
    for row in window_rows:
        grouped.setdefault(str(row["candidate"]), {})[str(row["window"])] = row

    ranked = []
    for candidate, by_window in grouped.items():
        if {"last_1y", "last_2y", "full"} - set(by_window):
            continue
        last1 = by_window["last_1y"]
        last2 = by_window["last_2y"]
        full = by_window["full"]
        ranked.append(
            {
                "candidate": candidate,
                "label": full["label"],
                "input_rank": int(full["rank"]),
                "stop": full["stop"],
                "rr": full["rr"],
                "tp1_ratio": full["tp1_ratio"],
                "tp1_r": full["tp1_r"],
                "last_1y_trades": last1["trades"],
                "last_1y_net_r": last1["net_r"],
                "last_1y_wr_pct": last1["wr_pct"],
                "last_1y_pf": last1["pf"],
                "last_1y_dd_r": last1["max_dd_r"],
                "last_2y_trades": last2["trades"],
                "last_2y_net_r": last2["net_r"],
                "last_2y_wr_pct": last2["wr_pct"],
                "full_trades": full["trades"],
                "full_net_r": full["net_r"],
                "full_wr_pct": full["wr_pct"],
                "full_pf": full["pf"],
                "full_dd_r": full["max_dd_r"],
                "deployability": full["deployability"],
                "live_support_notes": full["live_support_notes"],
                "exact_replay_required": full["exact_replay_required"],
                "score": round(_score(by_window), 4),
            }
        )
    ranked.sort(key=lambda row: (row["score"], row["last_1y_net_r"], row["full_net_r"]), reverse=True)
    for idx, row in enumerate(ranked, start=1):
        row["live_exact_rank"] = idx
    return ranked


def _write_report(payload: dict[str, Any]) -> None:
    ranked = payload["ranked_rows"]
    blocked = payload["blocked_candidates"]
    lines = [
        "# ALPHA_V1 Stop/Target Candidate Live-Engine Replay",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Result directory: `{RESULT_DIR}`",
        f"- Window: `{FULL_START}` to `{END_DATE}`",
        f"- Engine path: `execution/src/trader/historical_backtest.py` using live `ORBEngine` profiles created in memory.",
        f"- Base profile for active ALPHA legs: `{BASE_PROFILE}`. No live execution config file was edited.",
        "- Ranking lens: last 1y first, then last 2y, then full available history.",
        "",
        "## Ranked Exact Replay Results",
        "",
        "| Rank | Candidate | Stop | rr | tp1 | TP1_R | Last 1y Trades | Last 1y R | Last 1y WR | Last 2y R | Full Trades | Full R | Full WR | Full PF | Full DD | Deployability |",
        "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for row in ranked:
        lines.append(
            f"| {row['live_exact_rank']} | {row['label']} | {row['stop']} | "
            f"{row['rr']:.2f} | {row['tp1_ratio']:.2f} | {row['tp1_r']:.2f} | "
            f"{row['last_1y_trades']} | {row['last_1y_net_r']:.2f} | {row['last_1y_wr_pct']:.2f}% | "
            f"{row['last_2y_net_r']:.2f} | {row['full_trades']} | {row['full_net_r']:.2f} | "
            f"{row['full_wr_pct']:.2f}% | {row['full_pf']:.3f} | {row['full_dd_r']:.2f} | "
            f"{row['deployability']} |"
        )
    lines.extend(
        [
            "",
            "## Blocked / Not Replayed",
            "",
            "| Candidate | Requested Structure | Reason | Exact Replay Required |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in blocked:
        lines.append(
            f"| {row['label']} | {row['stop']}, rr={row['rr']}, tp1={row['tp1_ratio']}, TP1_R={row['tp1_r']} | "
            f"{row['live_support_notes']} | {row['exact_replay_required']} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Rows are single-candidate exact replays. They are not a combined portfolio because `ES Asia ORB` and `ES Asia-B ungated` both occupy the `ES_Asia` execution session key and are alternative definitions.",
            "- The live engine path can replay standard ORB continuation stop/target variants directly. The CISD additive branch needs execution-engine parity before it can be exact-replayed or deployed.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    exec_profiles = {profile.name: profile for profile in load_exec_configs(config)}
    alpha = exec_profiles[BASE_PROFILE]

    all_trades: list[dict[str, Any]] = []
    all_window_rows: list[dict[str, Any]] = []
    candidate_payloads: list[dict[str, Any]] = []

    for candidate in SUPPORTED_CANDIDATES:
        print(f"Running {candidate.rank}. {candidate.label}: {candidate.stop_label}, rr={candidate.rr}, tp1={candidate.tp1_ratio}", flush=True)
        profile = _profile_for(candidate, alpha)
        result = _run_candidate(config, profile)
        trades = result.get("trades", [])
        for trade in trades:
            trade["candidate"] = candidate.key
            trade["candidate_label"] = candidate.label
        rows = _window_rows(candidate, trades)
        all_trades.extend(trades)
        all_window_rows.extend(rows)
        candidate_payloads.append(
            {
                "candidate": candidate.__dict__,
                "profile_name": profile.name,
                "profile_session_overrides": _safe_json(profile.session_overrides),
                "summary": _safe_json(result.get("summary", {})),
                "window_rows": rows,
            }
        )

    ranked_rows = _rank_rows(all_window_rows)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "base_profile": BASE_PROFILE,
        "date_range": {"start": FULL_START, "end": END_DATE},
        "engine_path": "execution/src/trader/historical_backtest.py",
        "supported_candidates": candidate_payloads,
        "blocked_candidates": BLOCKED_CANDIDATES,
        "window_rows": all_window_rows,
        "ranked_rows": ranked_rows,
        "paths": {
            "result_dir": str(RESULT_DIR),
            "summary_json": str(RESULT_DIR / "summary.json"),
            "exact_trades_csv": str(RESULT_DIR / "exact_trades.csv"),
            "window_metrics_csv": str(RESULT_DIR / "window_metrics.csv"),
            "ranked_csv": str(RESULT_DIR / "ranked_summary.csv"),
            "report": str(REPORT_PATH),
        },
    }

    pd.DataFrame(all_trades).to_csv(RESULT_DIR / "exact_trades.csv", index=False)
    pd.DataFrame(all_window_rows).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    pd.DataFrame(ranked_rows).to_csv(RESULT_DIR / "ranked_summary.csv", index=False)
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True) + "\n")
    _write_report(payload)
    print(json.dumps({"result_dir": str(RESULT_DIR), "report": str(REPORT_PATH), "ranked_rows": ranked_rows}, indent=2))


if __name__ == "__main__":
    main()
