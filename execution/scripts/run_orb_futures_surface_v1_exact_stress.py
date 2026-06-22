#!/usr/bin/env python3
"""Exact-replay cost/slippage stress for ORB Futures Surface v1 survivors."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.main import INSTRUMENTS, SIGNAL_TO_EXEC  # noqa: E402

SOURCE_RUN_ID = "orb_futures_surface_v1_exact_replay_20260618"
RUN_ID = "orb_futures_surface_v1_exact_stress_20260618"
BACKTESTING_DIR = ROOT / "backtesting"
SOURCE_DIR = BACKTESTING_DIR / "data" / "results" / SOURCE_RUN_ID
RESULT_DIR = BACKTESTING_DIR / "data" / "results" / RUN_ID
REPORT_PATH = BACKTESTING_DIR / "learnings" / "reports" / "ORB_FUTURES_SURFACE_V1_EXACT_STRESS_20260618.md"

FULL_STRESS_COMMISSION_MULTIPLIER = 2.0
FULL_STRESS_SLIPPAGE_TICKS_PER_SIDE = 2
SCENARIOS: tuple[tuple[str, float, int], ...] = (
    ("baseline_recomputed", 1.0, 0),
    ("double_commission_only", 2.0, 0),
    ("two_ticks_slippage_only", 1.0, 2),
    ("full_stress_2x_commission_2ticks", 2.0, 2),
    ("boundary_2x_commission_4ticks", 2.0, 4),
)


def _load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    summary_path = SOURCE_DIR / "exact_replay_summary.csv"
    trades_path = SOURCE_DIR / "exact_replay_trades.csv"
    payload_path = SOURCE_DIR / "exact_replay_payload.json"
    for path in (summary_path, trades_path, payload_path):
        if not path.exists():
            raise FileNotFoundError(path)
    return (
        pd.read_csv(summary_path),
        pd.read_csv(trades_path),
        json.loads(payload_path.read_text()),
    )


def _asset_from_session(session_name: str) -> str:
    parts = str(session_name).split("_")
    if len(parts) >= 2 and parts[0] == "ORBFX":
        return parts[1]
    return parts[0]


def _trade_sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("entry_time") or ""),
        str(row.get("exit_time") or ""),
        str(row.get("candidate_session") or row.get("session") or ""),
    )


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return max_dd


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0.0)
    losses = -sum(value for value in values if value < 0.0)
    if losses <= 0.0:
        return math.inf if wins > 0.0 else 0.0
    return wins / losses


def _max_consecutive_losses(values: list[float]) -> int:
    current = 0
    worst = 0
    for value in values:
        if value < 0.0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def _stress_trade(
    trade: dict[str, Any],
    *,
    scenario: str,
    commission_multiplier: float,
    slippage_ticks_per_side: int,
) -> dict[str, Any] | None:
    session_name = str(trade["session"])
    asset = _asset_from_session(session_name)
    exec_symbol = SIGNAL_TO_EXEC.get(asset, asset)
    spec = INSTRUMENTS[exec_symbol]
    risk_points = float(trade.get("risk_points") or 0.0)
    qty = float(trade.get("qty") or 0.0)
    if risk_points <= 0.0 or qty <= 0.0:
        return None

    point_value = float(spec["point_value"])
    min_tick = float(spec["min_tick"])
    gross_pnl_usd = float(trade.get("gross_pnl_usd") or 0.0)
    gross_risk_usd = risk_points * qty * point_value
    base_commission_usd = float(trade.get("commission_usd") or 0.0)
    stressed_commission_usd = base_commission_usd * commission_multiplier
    slippage_points = slippage_ticks_per_side * min_tick * 2.0
    slippage_usd = slippage_points * qty * point_value
    stressed_pnl_usd = gross_pnl_usd - stressed_commission_usd - slippage_usd
    stressed_net_r = stressed_pnl_usd / gross_risk_usd if gross_risk_usd > 0.0 else 0.0
    base_net_r = float(trade.get("net_r_multiple") or 0.0)

    return {
        "scenario": scenario,
        "candidate_session": session_name,
        "asset": asset,
        "exec_symbol": exec_symbol,
        "date": str(trade["date"]),
        "direction": trade.get("direction"),
        "exit_type": trade.get("exit_type"),
        "entry_time": trade.get("entry_time"),
        "exit_time": trade.get("exit_time"),
        "qty": qty,
        "risk_points": risk_points,
        "point_value": point_value,
        "min_tick": min_tick,
        "base_net_r": base_net_r,
        "gross_pnl_usd": gross_pnl_usd,
        "base_commission_usd": base_commission_usd,
        "commission_multiplier": commission_multiplier,
        "stressed_commission_usd": stressed_commission_usd,
        "slippage_ticks_per_side": slippage_ticks_per_side,
        "slippage_points_round_trip": slippage_points,
        "slippage_usd": slippage_usd,
        "slippage_r": slippage_points / risk_points,
        "stressed_pnl_usd": stressed_pnl_usd,
        "stressed_net_r": stressed_net_r,
    }


def _summarize(
    rows: list[dict[str, Any]],
    *,
    scenario: str,
    commission_multiplier: float,
    slippage_ticks_per_side: int,
    exact_by_session: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_session: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_session.setdefault(str(row["candidate_session"]), []).append(row)

    for session_name, session_rows in sorted(by_session.items()):
        session_rows = sorted(session_rows, key=_trade_sort_key)
        values = [float(row["stressed_net_r"]) for row in session_rows]
        pnl_values = [float(row["stressed_pnl_usd"]) for row in session_rows]
        by_year: dict[str, float] = {}
        by_month: dict[str, float] = {}
        for row, value in zip(session_rows, values, strict=True):
            date = str(row["date"])
            by_year[date[:4]] = by_year.get(date[:4], 0.0) + value
            by_month[date[:7]] = by_month.get(date[:7], 0.0) + value

        total_r = float(sum(values))
        max_dd = _max_drawdown(values)
        exact = exact_by_session[session_name]
        min_year_r = min(by_year.values()) if by_year else 0.0
        pf = _profit_factor(pnl_values)
        full_stress = (
            math.isclose(commission_multiplier, FULL_STRESS_COMMISSION_MULTIPLIER)
            and slippage_ticks_per_side == FULL_STRESS_SLIPPAGE_TICKS_PER_SIDE
        )
        status = ""
        if full_stress:
            if total_r > 0.0 and pf > 1.0 and min_year_r > 0.0:
                status = "EXACT_STRESS_PASS"
            elif total_r > 0.0 and pf > 1.0:
                status = "EXACT_STRESS_WATCH"
            else:
                status = "EXACT_STRESS_FAIL"

        out.append(
            {
                "scenario": scenario,
                "candidate_session": session_name,
                "source_rule_id": exact["source_rule_id"],
                "asset": exact["asset"],
                "session": exact["session"],
                "direction": exact["direction"],
                "commission_multiplier": commission_multiplier,
                "slippage_ticks_per_side": slippage_ticks_per_side,
                "trade_count": len(session_rows),
                "stressed_total_net_r": round(total_r, 4),
                "stressed_avg_net_r": round(float(np.mean(values)) if values else 0.0, 6),
                "stressed_pf": round(float(pf), 4),
                "stressed_max_drawdown_r": round(max_dd, 4),
                "stressed_calmar_proxy": round(total_r / abs(max_dd), 4) if max_dd < 0.0 else math.inf,
                "stressed_win_rate": round(float(np.mean([value > 0.0 for value in values])) if values else 0.0, 4),
                "stressed_max_consecutive_losses": _max_consecutive_losses(values),
                "stressed_min_year_r": round(min_year_r, 4),
                "stressed_min_month_r": round(min(by_month.values()), 4) if by_month else 0.0,
                "stress_retention_vs_exact": round(total_r / float(exact["exact_net_r"]), 4)
                if float(exact["exact_net_r"]) > 0.0
                else 0.0,
                "stress_retention_vs_research": round(total_r / float(exact["research_preholdout_r"]), 4)
                if float(exact["research_preholdout_r"]) > 0.0
                else 0.0,
                "exact_net_r": float(exact["exact_net_r"]),
                "research_preholdout_r": float(exact["research_preholdout_r"]),
                "research_stress_r": float(exact["research_stress_r"]),
                "stressed_r_by_year": json.dumps({key: round(value, 4) for key, value in sorted(by_year.items())}),
                "stressed_r_by_month": json.dumps({key: round(value, 4) for key, value in sorted(by_month.items())}),
                "exact_stress_status": status,
                "deployability": "live_native",
                "live_support_notes": (
                    "Research gates are supported before arming in the execution engine; broker stop-order "
                    "routing semantics still need paper/dry verification before live orders."
                ),
                "exact_replay_required": "complete",
            }
        )
    return out


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
            if isinstance(value, float):
                values.append(f"{value:.2f}" if math.isfinite(value) else str(value))
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _render_report(payload: dict[str, Any]) -> str:
    full_rows = [
        row for row in payload["summary_rows"]
        if row["scenario"] == "full_stress_2x_commission_2ticks"
    ]
    pass_rows = [row for row in full_rows if row["exact_stress_status"] == "EXACT_STRESS_PASS"]
    watch_rows = [row for row in full_rows if row["exact_stress_status"] == "EXACT_STRESS_WATCH"]
    fail_rows = [row for row in full_rows if row["exact_stress_status"] == "EXACT_STRESS_FAIL"]
    cols = [
        ("Cand", "candidate_session"),
        ("Status", "exact_stress_status"),
        ("Deploy", "deployability"),
        ("Replay", "exact_replay_required"),
        ("Stress R", "stressed_total_net_r"),
        ("Ret Exact", "stress_retention_vs_exact"),
        ("PF", "stressed_pf"),
        ("DD R", "stressed_max_drawdown_r"),
        ("Min Year", "stressed_min_year_r"),
        ("Trades", "trade_count"),
    ]
    ladder_cols = [
        ("Cand", "candidate_session"),
        ("Scenario", "scenario"),
        ("Deploy", "deployability"),
        ("Net R", "stressed_total_net_r"),
        ("PF", "stressed_pf"),
        ("DD R", "stressed_max_drawdown_r"),
        ("Min Year", "stressed_min_year_r"),
    ]
    return "\n".join(
        [
            "# ORB Futures Surface v1 Exact Stress",
            "",
            "## Summary",
            "",
            (
                "Stress-tested the four exact-replay pass rows from "
                "`ORB_FUTURES_SURFACE_V1_EXACT_REPLAY` over `2021-01-01`-`2024-12-31`. "
                "Holdout remained closed."
            ),
            "",
            "- Full stress: `2x` baseline commission plus `2` adverse ticks per side on every filled round trip.",
            "- This is post-exact-replay cost/slippage accounting; it preserves the exact replay signal/fill path.",
            f"- Full-stress pass: `{len(pass_rows)}`",
            f"- Full-stress watch: `{len(watch_rows)}`",
            f"- Full-stress fail: `{len(fail_rows)}`",
            "",
            "## Full Stress Pass",
            "",
            _markdown_table(pass_rows, cols),
            "",
            "## Full Stress Watch",
            "",
            _markdown_table(watch_rows, cols),
            "",
            "## Full Stress Fail",
            "",
            _markdown_table(fail_rows, cols),
            "",
            "## Stress Ladder",
            "",
            _markdown_table(payload["summary_rows"], ladder_cols),
            "",
            "## Artifacts",
            "",
            f"- `{RESULT_DIR / 'exact_stress_summary.csv'}`",
            f"- `{RESULT_DIR / 'exact_stress_trades.csv'}`",
            f"- `{RESULT_DIR / 'exact_stress_payload.json'}`",
            f"- `{RESULT_DIR / 'exact_stress_report.md'}`",
            "",
        ]
    )


def main() -> int:
    exact_summary, exact_trades, exact_payload = _load_inputs()
    pass_summary = exact_summary[exact_summary["exact_replay_status"] == "EXACT_REPLAY_PASS"].copy()
    pass_sessions = set(pass_summary["candidate_session"].tolist())
    pass_trades = exact_trades[exact_trades["session"].isin(pass_sessions)].copy()
    exact_by_session = {
        str(row["candidate_session"]): row.to_dict()
        for _, row in pass_summary.iterrows()
    }

    all_trade_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    for scenario, commission_multiplier, slippage_ticks_per_side in SCENARIOS:
        scenario_rows: list[dict[str, Any]] = []
        for trade in pass_trades.to_dict("records"):
            row = _stress_trade(
                trade,
                scenario=scenario,
                commission_multiplier=commission_multiplier,
                slippage_ticks_per_side=slippage_ticks_per_side,
            )
            if row is None:
                continue
            scenario_rows.append(row)
            all_trade_rows.append(row)
        summary_rows.extend(
            _summarize(
                scenario_rows,
                scenario=scenario,
                commission_multiplier=commission_multiplier,
                slippage_ticks_per_side=slippage_ticks_per_side,
                exact_by_session=exact_by_session,
            )
        )

    payload = {
        "run_id": RUN_ID,
        "source_run_id": SOURCE_RUN_ID,
        "source_window": exact_payload.get("window", {}),
        "stress_model": {
            "full_stress_commission_multiplier": FULL_STRESS_COMMISSION_MULTIPLIER,
            "full_stress_slippage_ticks_per_side": FULL_STRESS_SLIPPAGE_TICKS_PER_SIDE,
            "scenarios": [
                {
                    "scenario": scenario,
                    "commission_multiplier": commission_multiplier,
                    "slippage_ticks_per_side": slippage_ticks_per_side,
                }
                for scenario, commission_multiplier, slippage_ticks_per_side in SCENARIOS
            ],
            "notes": (
                "Stress starts from exact replay trade records. Gross PnL is preserved, commission is multiplied, "
                "and adverse round-trip slippage is subtracted as ticks_per_side * min_tick * 2."
            ),
        },
        "input_exact_summary": str(SOURCE_DIR / "exact_replay_summary.csv"),
        "input_exact_trades": str(SOURCE_DIR / "exact_replay_trades.csv"),
        "summary_rows": summary_rows,
    }

    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(summary_rows).to_csv(RESULT_DIR / "exact_stress_summary.csv", index=False)
    pd.DataFrame(all_trade_rows).to_csv(RESULT_DIR / "exact_stress_trades.csv", index=False)
    (RESULT_DIR / "exact_stress_payload.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    report = _render_report(payload)
    (RESULT_DIR / "exact_stress_report.md").write_text(report + "\n")
    REPORT_PATH.write_text(report + "\n")

    full_rows = [
        row for row in summary_rows
        if row["scenario"] == "full_stress_2x_commission_2ticks"
    ]
    print(
        json.dumps(
            {
                "success": True,
                "run_id": RUN_ID,
                "candidates": len(full_rows),
                "pass": sum(1 for row in full_rows if row["exact_stress_status"] == "EXACT_STRESS_PASS"),
                "watch": sum(1 for row in full_rows if row["exact_stress_status"] == "EXACT_STRESS_WATCH"),
                "fail": sum(1 for row in full_rows if row["exact_stress_status"] == "EXACT_STRESS_FAIL"),
                "summary": str(RESULT_DIR / "exact_stress_summary.csv"),
                "report": str(REPORT_PATH),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
