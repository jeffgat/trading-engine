#!/usr/bin/env python3
"""Exact replay for ORB Futures Surface v1 promoted plain-breakout rows."""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

import trader.historical_backtest as hb  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, SESSION_CONFIGS, load_config  # noqa: E402

SOURCE_RUN_ID = "orb_futures_surface_v1_broad_full_20260618"
RUN_ID = "orb_futures_surface_v1_exact_replay_20260618"
BACKTESTING_DIR = ROOT / "backtesting"
SOURCE_DIR = BACKTESTING_DIR / "data" / "results" / SOURCE_RUN_ID
RESULT_DIR = BACKTESTING_DIR / "data" / "results" / RUN_ID
REPORT_PATH = BACKTESTING_DIR / "learnings" / "reports" / "ORB_FUTURES_SURFACE_V1_EXACT_REPLAY_20260618.md"

PROFILE_NAME = "ORB_FUTURES_SURFACE_V1_EXACT_REPLAY"
DISCOVERY_START = "2021-01-01"
DISCOVERY_END = "2024-12-31"
BASE_RISK_USD = 5000.0

SESSION_DEFAULTS = {
    "NY": {
        "base_session": "NQ_NY",
        "orb_start": "09:30",
        "entry_end": "13:00",
        "flat_start": "15:50",
        "flat_end": "16:00",
    },
    "Asia": {
        "base_session": "NQ_Asia",
        "orb_start": "20:00",
        "entry_end": "23:15",
        "flat_start": "06:45",
        "flat_end": "07:00",
    },
    "LDN": {
        "base_session": "NQ_LDN",
        "orb_start": "03:00",
        "entry_end": "08:25",
        "flat_start": "08:20",
        "flat_end": "08:25",
    },
}

DOW_NAME_TO_INT = {
    "None": None,
    "Monday": 0,
    "Tuesday": 1,
    "Wednesday": 2,
    "Thursday": 3,
    "Friday": 4,
}


def _add_minutes(time_text: str, minutes: int) -> str:
    base = datetime.strptime(time_text, "%H:%M")
    return (base + timedelta(minutes=int(minutes))).strftime("%H:%M")


def _load_source() -> tuple[pd.DataFrame, dict[str, Any]]:
    top_path = SOURCE_DIR / "top_candidates.csv"
    summary_path = SOURCE_DIR / "summary.json"
    if not top_path.exists():
        raise FileNotFoundError(top_path)
    if not summary_path.exists():
        raise FileNotFoundError(summary_path)
    return pd.read_csv(top_path), json.loads(summary_path.read_text())


def _thresholds(summary: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, float]]:
    out: dict[tuple[str, str, int], dict[str, float]] = {}
    for sleeve in summary["sleeve_reports"]:
        asset = str(sleeve["asset"])
        session = str(sleeve["session"])
        for orb_minutes, values in sleeve["thresholds_by_orb_minutes"].items():
            out[(asset, session, int(orb_minutes))] = {
                key: float(value)
                for key, value in values.items()
            }
    return out


def _threshold_value(values: dict[str, float], gate: str, kind: str) -> float:
    if kind == "atr":
        if gate == "low_or_mid_atr":
            return values["atr_p66"]
        if gate == "low_atr_only":
            return values["atr_p33"]
    if kind == "orb":
        if gate == "small_or_mid_orb":
            return values["orb_p66"]
        if gate == "small_orb_only":
            return values["orb_p33"]
    return 0.0


def _base_session_name(asset: str, session: str) -> str:
    preferred = f"{asset}_{session}"
    if preferred in SESSION_CONFIGS:
        return preferred
    return SESSION_DEFAULTS[session]["base_session"]


def _candidate_session_name(row: pd.Series) -> str:
    return "ORBFX_%s_%s_R%d" % (
        str(row["asset"]).upper(),
        str(row["session"]).upper(),
        int(row["rank"]),
    )


def _candidate_override(row: pd.Series, thresholds: dict[tuple[str, str, int], dict[str, float]]) -> dict[str, Any]:
    asset = str(row["asset"])
    session = str(row["session"])
    direction = str(row["direction"])
    orb_minutes = int(row["orb_minutes"])
    defaults = SESSION_DEFAULTS[session]
    orb_start = defaults["orb_start"]
    orb_end = _add_minutes(orb_start, orb_minutes)
    values = thresholds[(asset, session, orb_minutes)]
    return {
        "base_session": _base_session_name(asset, session),
        "strategy_type": "orb_breakout",
        "orb_breakout_trigger": "touch",
        "orb_breakout_buffer_ticks": 0,
        "orb_breakout_buffer_atr_pct": 0.0,
        "base_bar_minutes": 5,
        "instrument": asset,
        "orb_start": orb_start,
        "orb_end": orb_end,
        "entry_start": orb_end,
        "entry_end": defaults["entry_end"],
        "flat_start": defaults["flat_start"],
        "flat_end": defaults["flat_end"],
        "stop_basis": "atr",
        "stop_atr_pct": float(row["stop_atr_pct"]),
        "min_gap_atr_pct": 0.0,
        "max_gap_atr_pct": 0.0,
        "gap_filter_basis": "atr",
        "rr": float(row["rr"]),
        "tp1_ratio": 1.0,
        "exit_mode": "single_target",
        "atr_length": 14,
        "risk_usd": BASE_RISK_USD,
        "max_single_risk_usd": BASE_RISK_USD,
        "long_only": direction == "long",
        "short_only": direction == "short",
        "excluded_dow": DOW_NAME_TO_INT.get(str(row["excluded_dow"])),
        "max_prior_rolling_atr_pct": _threshold_value(values, str(row["atr_gate"]), "atr"),
        "max_orb_range_pct": _threshold_value(values, str(row["orb_gate"]), "orb"),
        "orb_trade_max_per_session": 1,
        "fomc_exclusion": False,
        "icf_enabled": False,
    }


def _promoted_one_sided(top: pd.DataFrame) -> pd.DataFrame:
    rows = top[
        (top["verdict"] == "PROMOTE_TO_EXACT_REPLAY_QUEUE")
        & (top["direction"].isin(["long", "short"]))
    ].copy()
    return rows.sort_values(["asset", "session", "rank"]).reset_index(drop=True)


def _skipped_promoted_rows(top: pd.DataFrame) -> pd.DataFrame:
    rows = top[
        (top["verdict"] == "PROMOTE_TO_EXACT_REPLAY_QUEUE")
        & (~top["direction"].isin(["long", "short"]))
    ].copy()
    return rows.sort_values(["asset", "session", "rank"]).reset_index(drop=True)


def _build_profile(rows: pd.DataFrame, thresholds: dict[tuple[str, str, int], dict[str, float]]) -> tuple[ExecutionConfig, dict[str, str]]:
    overrides: dict[str, dict[str, Any]] = {}
    source_by_session: dict[str, str] = {}
    for _, row in rows.iterrows():
        session_name = _candidate_session_name(row)
        overrides[session_name] = _candidate_override(row, thresholds)
        source_by_session[session_name] = str(row["rule_id"])
    return (
        ExecutionConfig(
            name=PROFILE_NAME,
            enabled=False,
            max_open_contracts=99999.0,
            webhooks=[],
            session_overrides=overrides,
            lsi_session_overrides={},
        ),
        source_by_session,
    )


def _patch_profile_loader(profile: ExecutionConfig) -> None:
    def _load_exec_configs(_config: dict | None = None):
        return [profile]

    hb.load_exec_configs = _load_exec_configs


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
        "r_by_year": summary.get("r_by_year", {}),
        "exit_breakdown": summary.get("exit_breakdown", {}),
    }


def _status(row: dict[str, Any]) -> str:
    research_trades = max(int(row["research_preholdout_trades"]), 1)
    trade_delta_pct = abs(row["exact_trades"] - research_trades) / research_trades
    r_retention = row["exact_net_r"] / row["research_preholdout_r"] if row["research_preholdout_r"] > 0 else 0.0
    exact_positive = row["exact_trades"] >= 20 and row["exact_net_r"] > 0 and row["exact_pf"] > 1.0
    if exact_positive and trade_delta_pct <= 0.35 and r_retention >= 0.50:
        return "EXACT_REPLAY_PASS"
    if exact_positive:
        return "EXACT_REPLAY_WATCH"
    return "EXACT_REPLAY_FAIL"


def _candidate_rows(source_rows: pd.DataFrame, result: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for _, source in source_rows.iterrows():
        session_name = _candidate_session_name(source)
        exact = _summary_for_session(result, session_name)
        research_r = float(source["preholdout_r"])
        exact_net_r = exact["net_r"]
        row = {
            "candidate_session": session_name,
            "source_rule_id": str(source["rule_id"]),
            "asset": str(source["asset"]),
            "session": str(source["session"]),
            "direction": str(source["direction"]),
            "rank": int(source["rank"]),
            "research_validation_r": float(source["validation_r"]),
            "research_preholdout_trades": int(source["preholdout_trades"]),
            "research_preholdout_r": research_r,
            "research_stress_r": float(source["stress_total_r"]),
            "exact_trades": exact["trades"],
            "exact_r": exact["r"],
            "exact_net_r": exact_net_r,
            "exact_pf": exact["pf"],
            "exact_dd_r": exact["dd_r"],
            "exact_calmar": exact["calmar"],
            "trade_delta": exact["trades"] - int(source["preholdout_trades"]),
            "net_r_delta": round(exact_net_r - research_r, 4),
            "net_r_retention": round(exact_net_r / research_r, 4) if research_r > 0 else 0.0,
            "exact_r_by_year": exact["r_by_year"],
            "exact_exit_breakdown": exact["exit_breakdown"],
            "cluster_score": float(source["cluster_score"]),
            "dsr": float(source["dsr"]),
        }
        row["exact_replay_status"] = _status(row)
        rows.append(row)
    return rows


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
                values.append(f"{value:.2f}" if math.isfinite(value) else str(value))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _render_report(payload: dict[str, Any]) -> str:
    rows = payload["candidate_summaries"]
    skipped_rows = payload.get("skipped_promoted_candidates", [])
    pass_rows = [row for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_PASS"]
    watch_rows = [row for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_WATCH"]
    fail_rows = [row for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_FAIL"]
    cols = [
        ("Cand", "candidate_session"),
        ("Rule", "source_rule_id"),
        ("Status", "exact_replay_status"),
        ("Research R", "research_preholdout_r"),
        ("Exact Net R", "exact_net_r"),
        ("Ret", "net_r_retention"),
        ("Exact PF", "exact_pf"),
        ("Exact DD", "exact_dd_r"),
        ("Trades", "exact_trades"),
        ("Delta", "trade_delta"),
    ]
    return "\n".join(
        [
            "# ORB Futures Surface v1 Exact Replay",
            "",
            "## Summary",
            "",
            (
                f"Ran `{payload['profile_name']}` through execution-engine exact replay for "
                f"`{payload['window']['start']}`-`{payload['window']['end']}`. Holdout remained closed."
            ),
            "",
            f"- Candidates replayed: `{len(rows)}`",
            f"- Exact replay pass: `{len(pass_rows)}`",
            f"- Exact replay watch: `{len(watch_rows)}`",
            f"- Exact replay fail: `{len(fail_rows)}`",
            f"- Promoted rows skipped: `{len(skipped_rows)}` unsupported `both`-direction rows",
            "- Source candidates: promoted one-sided rows from ORB Futures Surface v1 broad run.",
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
            f"- `{RESULT_DIR / 'exact_replay_trades.csv'}`",
            f"- `{RESULT_DIR / 'exact_replay_payload.json'}`",
            f"- `{RESULT_DIR / 'exact_replay_report.md'}`",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=DISCOVERY_START)
    parser.add_argument("--end", default=DISCOVERY_END)
    args = parser.parse_args()

    top, source_summary = _load_source()
    promoted = _promoted_one_sided(top)
    skipped_promoted = _skipped_promoted_rows(top)
    thresholds = _thresholds(source_summary)
    profile, _source_by_session = _build_profile(promoted, thresholds)
    _patch_profile_loader(profile)

    config = load_config(DEFAULT_CONFIG)
    symbols = sorted(promoted["asset"].unique().tolist())
    common_end = hb.latest_common_end(symbols)
    print(f"candidates={len(promoted)} symbols={symbols}", flush=True)
    print(f"window={args.start}->{args.end} common_end={common_end.isoformat()}", flush=True)

    result = hb.run_profile_backtest_sync(
        config=config,
        profile_name=PROFILE_NAME,
        start_date=args.start,
        end_date=args.end,
        latest_data_ts=common_end,
        label=f"EXEC EXACT {PROFILE_NAME} {args.start} to {args.end}",
    )
    rows = _candidate_rows(promoted, result)
    trade_rows = []
    for trade in result["trades"]:
        trade_rows.append({"window": "preholdout", **trade})

    payload = {
        "run_id": RUN_ID,
        "source_run_id": SOURCE_RUN_ID,
        "profile_name": PROFILE_NAME,
        "window": {"start": args.start, "end": args.end},
        "common_end": common_end.isoformat(),
        "profile": asdict(profile),
        "skipped_promoted_candidates": skipped_promoted[
            [
                "rule_id",
                "asset",
                "session",
                "direction",
                "rank",
                "validation_r",
                "preholdout_r",
            ]
        ].to_dict("records"),
        "candidate_summaries": rows,
        "aggregate": result["summary"],
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
                "run_id": RUN_ID,
                "candidates": len(rows),
                "pass": sum(1 for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_PASS"),
                "watch": sum(1 for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_WATCH"),
                "fail": sum(1 for row in rows if row["exact_replay_status"] == "EXACT_REPLAY_FAIL"),
                "summary": str(RESULT_DIR / "exact_replay_summary.csv"),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
