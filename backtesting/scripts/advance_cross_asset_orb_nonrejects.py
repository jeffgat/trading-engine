#!/usr/bin/env python3
"""Advance non-rejected cross-asset ORB candidates into replay-review artifacts.

Inputs come from ``run_cross_asset_orb_base_matrix.py``. This script does not
enable live trading. It creates disabled execution-profile JSON blocks and a
promotion queue for every candidate whose verdict is not ``REJECT``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = ROOT.parent
EXEC_SRC = REPO_ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.broker import MultiBroker, TradersPostClient  # noqa: E402
from trader.main import (  # noqa: E402
    DEFAULT_CONFIG,
    ExecutionConfig,
    SIGNAL_TO_EXEC,
    build_engines,
    load_config,
)

SOURCE_RUN = "cross_asset_orb_base_matrix_20260612"
RUN_ID = "cross_asset_orb_nonreject_advancement_20260612"
SOURCE_DIR = ROOT / "data" / "results" / SOURCE_RUN
RESULT_DIR = ROOT / "data" / "results" / RUN_ID
REPORT_PATH = ROOT / "learnings" / "reports" / "CROSS_ASSET_ORB_NONREJECT_ADVANCEMENT_20260612.md"

PROFILE_PREFIX = "ORB_ADV_20260612"
COMBINED_PROFILE_NAME = "ORB_NONREJECT_ADVANCEMENT_20260612"
REPLAY_RISK_USD = 5000.0
REPLAY_MAX_SINGLE_RISK_USD = 7500.0

DOW_TO_INT = {
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}

BASE_SESSION_BY_RESEARCH_SESSION = {
    "NY": "NQ_NY",
    "Asia": "NQ_Asia",
    "LDN": "NQ_LDN",
}


def _read_inputs() -> tuple[pd.DataFrame, dict[str, Any]]:
    top3_path = SOURCE_DIR / "top3_candidates.csv"
    summary_path = SOURCE_DIR / "summary.json"
    if not top3_path.exists():
        raise FileNotFoundError(top3_path)
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    return pd.read_csv(top3_path), json.loads(summary_path.read_text())


def _sleeve_lookup(summary: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(sleeve["asset"]), str(sleeve["session"])): sleeve
        for sleeve in summary["sleeve_reports"]
    }


def _split_window(window: str) -> tuple[str, str]:
    start, end = window.split("-", 1)
    return start, end


def _gate_value(thresholds: dict[str, float], gate: str, kind: str) -> float:
    if kind == "atr":
        if gate == "low_or_mid_atr":
            return float(thresholds["atr_p66"])
        if gate == "low_atr_only":
            return float(thresholds["atr_p33"])
    if kind == "orb":
        if gate == "small_or_mid_orb":
            return float(thresholds["orb_p66"])
        if gate == "small_orb_only":
            return float(thresholds["orb_p33"])
    return 0.0


def _clean_dow(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    text = str(value)
    if text in {"None", "nan", ""}:
        return None
    return DOW_TO_INT[text]


def _direction_flags(direction: str) -> tuple[bool, bool]:
    if direction == "long":
        return True, False
    if direction == "short":
        return False, True
    if direction == "both":
        return False, False
    raise ValueError(f"Unknown direction: {direction}")


def _profile_name(row: pd.Series) -> str:
    rank = int(row["overall_rank"])
    return f"{PROFILE_PREFIX}_{rank:02d}_{row['asset']}_{row['session'].upper()}"


def _session_name(row: pd.Series) -> str:
    rank = int(row["overall_rank"])
    return f"ORB{rank:02d}_{row['asset']}_{row['session'].upper()}"


def _session_override(row: pd.Series, sleeve: dict[str, Any]) -> dict[str, Any]:
    anchor = sleeve["anchor_config"]
    thresholds = sleeve["thresholds"]
    orb_start, orb_end = _split_window(anchor["orb_window"])
    entry_start, entry_end = _split_window(anchor["entry_window"])
    flat_start, flat_end = _split_window(anchor["flat_window"])
    long_only, short_only = _direction_flags(str(row["direction"]))
    asset = str(row["asset"])

    return {
        "base_session": BASE_SESSION_BY_RESEARCH_SESSION[str(row["session"])],
        "instrument": asset,
        "exec_ticker": SIGNAL_TO_EXEC.get(asset, asset),
        "orb_start": orb_start,
        "orb_end": orb_end,
        "entry_start": entry_start,
        "entry_end": entry_end,
        "flat_start": flat_start,
        "flat_end": flat_end,
        "stop_basis": "atr",
        "gap_filter_basis": "atr",
        "stop_atr_pct": float(anchor["stop_atr_pct"]),
        "min_gap_atr_pct": float(anchor["min_gap_atr_pct"]),
        "max_gap_atr_pct": 0.0,
        "atr_length": int(anchor["atr_length"]),
        "rr": float(row["rr"]),
        "tp1_ratio": 1.0,
        "exit_mode": "single_target",
        "risk_usd": REPLAY_RISK_USD,
        "max_single_risk_usd": REPLAY_MAX_SINGLE_RISK_USD,
        "long_only": long_only,
        "short_only": short_only,
        "excluded_dow": _clean_dow(row["excluded_dow"]),
        "continuation_fvg_selection": "first",
        "orb_trade_max_per_session": 1,
        "icf_enabled": False,
        "fomc_exclusion": False,
        "max_prior_rolling_atr_pct": _gate_value(thresholds, str(row["atr_gate"]), "atr"),
        "max_orb_range_pct": _gate_value(thresholds, str(row["orb_gate"]), "orb"),
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
    }


def _candidate_record(row: pd.Series, session_name: str, profile_name: str, override: dict[str, Any]) -> dict[str, Any]:
    lane = "primary_exact_replay_queue" if row["verdict"] == "PROMOTE_TO_EXACT_REPLAY" else "challenger_exact_replay_queue"
    return {
        "candidate_id": session_name,
        "profile_name": profile_name,
        "session_name": session_name,
        "lane": lane,
        "source_rule_id": row["rule_id"],
        "asset": row["asset"],
        "session": row["session"],
        "verdict": row["verdict"],
        "deployability": row["deployability"],
        "overall_rank": int(row["overall_rank"]),
        "sleeve_rank": int(row["rank"]),
        "rr": float(row["rr"]),
        "direction": row["direction"],
        "excluded_dow": None if pd.isna(row["excluded_dow"]) else row["excluded_dow"],
        "atr_gate": row["atr_gate"],
        "orb_gate": row["orb_gate"],
        "max_prior_rolling_atr_pct": override["max_prior_rolling_atr_pct"],
        "max_orb_range_pct": override["max_orb_range_pct"],
        "exec_ticker": override["exec_ticker"],
        "discovery_trades": int(row["trades"]),
        "discovery_r": float(row["r"]),
        "discovery_pf": float(row["pf"]),
        "discovery_dd_r": float(row["dd_r"]),
        "discovery_calmar": float(row["calmar"]),
        "discovery_dsr": float(row["dsr"]),
        "discovery_payout_rate": float(row["disc_payout_rate"]),
        "discovery_breach_rate": float(row["disc_breach_rate"]),
        "discovery_ev_per_start_usd": float(row["disc_ev_per_start"]),
        "holdout_trades": int(row["holdout_trades"]),
        "holdout_r": float(row["holdout_r"]),
        "holdout_pf": float(row["holdout_pf"]),
        "holdout_ev_per_start_usd": float(row["holdout_ev_per_start"]),
        "exact_replay_required": True,
        "dry_run_enabled": False,
        "next_step": "Run execution-engine exact replay; keep profile disabled until replay parity and paper-risk review pass.",
    }


def _execution_profiles(records: list[dict[str, Any]], overrides_by_session: dict[str, dict[str, Any]]) -> dict[str, Any]:
    profiles: dict[str, Any] = {}
    for record in records:
        session_name = record["session_name"]
        profiles[record["profile_name"]] = {
            "enabled": False,
            "max_open_contracts": 999,
            "webhooks": [],
            "sessions": {session_name: overrides_by_session[session_name]},
            "lsi_sessions": {},
        }

    profiles[COMBINED_PROFILE_NAME] = {
        "enabled": False,
        "max_open_contracts": 999,
        "webhooks": [],
        "sessions": {
            record["session_name"]: overrides_by_session[record["session_name"]]
            for record in sorted(records, key=lambda item: item["overall_rank"])
        },
        "lsi_sessions": {},
    }
    return profiles


def _validate_profiles(profiles: dict[str, Any]) -> list[dict[str, Any]]:
    config = load_config(DEFAULT_CONFIG)
    broker = MultiBroker([TradersPostClient(webhook_url="", config_name="validation")])
    validation: list[dict[str, Any]] = []
    for profile_name, raw in profiles.items():
        exec_config = ExecutionConfig(
            name=profile_name,
            enabled=False,
            max_open_contracts=float(raw["max_open_contracts"]),
            session_overrides=raw["sessions"],
            lsi_session_overrides=raw["lsi_sessions"],
        )
        engines, symbol_map, atr_lengths = build_engines(
            config,
            broker,
            config_name=profile_name,
            session_list=list(exec_config.session_overrides.keys()),
            exec_overrides=exec_config.session_overrides,
        )
        validation.append(
            {
                "profile_name": profile_name,
                "expected_sessions": len(exec_config.session_overrides),
                "built_engines": len(engines),
                "symbols": sorted(symbol_map.keys()),
                "atr_lengths": {symbol: sorted(lengths) for symbol, lengths in atr_lengths.items()},
                "valid": len(engines) == len(exec_config.session_overrides),
            }
        )
    return validation


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


def _render_report(records: list[dict[str, Any]], validation: list[dict[str, Any]]) -> str:
    primary = [row for row in records if row["lane"] == "primary_exact_replay_queue"]
    challengers = [row for row in records if row["lane"] == "challenger_exact_replay_queue"]
    invalid = [row for row in validation if not row["valid"]]
    cols = [
        ("Rank", "overall_rank"),
        ("Cand", "candidate_id"),
        ("Rule", "source_rule_id"),
        ("Verdict", "verdict"),
        ("Exec", "exec_ticker"),
        ("R", "discovery_r"),
        ("PF", "discovery_pf"),
        ("DD", "discovery_dd_r"),
        ("DSR", "discovery_dsr"),
        ("EV", "discovery_ev_per_start_usd"),
        ("HO R", "holdout_r"),
        ("HO PF", "holdout_pf"),
    ]
    lines = [
        "# Cross-Asset ORB Non-Reject Advancement",
        "",
        "## Decision",
        "",
        (
            f"Advanced `{len(records)}` non-rejected candidates from `{SOURCE_RUN}`: "
            f"`{len(primary)}` primary exact-replay promotions and `{len(challengers)}` challengers. "
            "All generated execution profiles are disabled and have no webhooks."
        ),
        "",
        (
            "This packet moves candidates into exact execution replay / paper-review preparation. "
            "It does not enable live trading and it does not override the previous rejection decisions."
        ),
        "",
        "## Primary Exact-Replay Queue",
        "",
        _markdown_table(primary, cols),
        "",
        "## Challenger Exact-Replay Queue",
        "",
        _markdown_table(challengers, cols),
        "",
        "## Validation",
        "",
        (
            f"- Profile validation: `{len(validation) - len(invalid)}/{len(validation)}` generated profiles built "
            "through the execution-engine builder."
        ),
        "- RTY research candidates now route to `M2K` in the generated profile metadata.",
        "- Replay profiles use `risk_usd=5000` for R-denominated exact replay parity; dry-run sizing should be cut separately before enabling.",
        "- Required next step: run execution-engine exact replay on these disabled profiles, then compare exact replay versus research rows before any dry-run config promotion.",
        "",
        "## Artifacts",
        "",
        f"- `{RESULT_DIR / 'promotion_queue.csv'}`",
        f"- `{RESULT_DIR / 'candidate_exec_profiles.json'}`",
        f"- `{RESULT_DIR / 'promotion_packet.json'}`",
        f"- `{RESULT_DIR / 'report.md'}`",
        "",
    ]
    if invalid:
        lines.extend(
            [
                "## Validation Issues",
                "",
                _markdown_table(invalid, [("Profile", "profile_name"), ("Expected", "expected_sessions"), ("Built", "built_engines"), ("Valid", "valid")]),
                "",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    top3, summary = _read_inputs()
    sleeve_by_key = _sleeve_lookup(summary)
    nonreject = top3[top3["verdict"] != "REJECT"].copy()
    nonreject = nonreject.sort_values("overall_rank")

    records: list[dict[str, Any]] = []
    overrides_by_session: dict[str, dict[str, Any]] = {}
    for _, row in nonreject.iterrows():
        sleeve = sleeve_by_key[(str(row["asset"]), str(row["session"]))]
        session_name = _session_name(row)
        profile_name = _profile_name(row)
        override = _session_override(row, sleeve)
        overrides_by_session[session_name] = override
        records.append(_candidate_record(row, session_name, profile_name, override))

    profiles = _execution_profiles(records, overrides_by_session)
    validation = _validate_profiles(profiles)
    packet = {
        "run_id": RUN_ID,
        "source_run": SOURCE_RUN,
        "combined_profile_name": COMBINED_PROFILE_NAME,
        "candidate_count": len(records),
        "primary_exact_replay_count": sum(1 for row in records if row["lane"] == "primary_exact_replay_queue"),
        "challenger_exact_replay_count": sum(1 for row in records if row["lane"] == "challenger_exact_replay_queue"),
        "replay_profile_defaults": {
            "enabled": False,
            "webhooks": [],
            "risk_usd": REPLAY_RISK_USD,
            "max_single_risk_usd": REPLAY_MAX_SINGLE_RISK_USD,
        },
        "candidates": records,
        "validation": validation,
        "execution_profiles": profiles,
    }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(records).to_csv(RESULT_DIR / "promotion_queue.csv", index=False)
    (RESULT_DIR / "candidate_exec_profiles.json").write_text(json.dumps(profiles, indent=2) + "\n")
    (RESULT_DIR / "promotion_packet.json").write_text(json.dumps(packet, indent=2, default=str) + "\n")
    report = _render_report(records, validation)
    (RESULT_DIR / "report.md").write_text(report + "\n")
    REPORT_PATH.write_text(report + "\n")

    print(
        json.dumps(
            {
                "success": all(row["valid"] for row in validation),
                "candidate_count": len(records),
                "primary_exact_replay_count": packet["primary_exact_replay_count"],
                "challenger_exact_replay_count": packet["challenger_exact_replay_count"],
                "combined_profile": COMBINED_PROFILE_NAME,
                "report": str(REPORT_PATH),
                "profiles": str(RESULT_DIR / "candidate_exec_profiles.json"),
            },
            indent=2,
        )
    )
    return 0 if all(row["valid"] for row in validation) else 1


if __name__ == "__main__":
    raise SystemExit(main())
