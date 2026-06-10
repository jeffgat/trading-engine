#!/usr/bin/env python3
"""Cost/slippage stress for the live-native NQ NY ORB rolling-gate candidate.

Inputs are exact replay artifacts only. The stress starts from each trade's
post-commission net R and subtracts additional adverse round-trip slippage.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = "nq_ny_orb_rolling_gate_cost_stress_20260609"
ARTIFACT_DIR = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / RUN_ID
    / "artifacts"
)
PRE_HOLDOUT_ARTIFACT = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2021_20260609"
    / "artifacts"
    / "exact_replay_results.json"
)
HOLDOUT_ARTIFACT = (
    ROOT
    / "backtesting"
    / "data"
    / "results"
    / "discovery_runs"
    / "nq_ny_orb_exec_native_rolling_gate_2025_holdout_20260609"
    / "artifacts"
    / "holdout_results.json"
)

NQ_TICK_SIZE_POINTS = 0.25
STRESS_TICKS_PER_SIDE = (0, 1, 2, 4, 8)


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text())


def _load_trades() -> list[dict[str, Any]]:
    pre = _load_payload(PRE_HOLDOUT_ARTIFACT)
    holdout = _load_payload(HOLDOUT_ARTIFACT)
    rows: list[dict[str, Any]] = []
    for period, payload in (
        ("pre_holdout_2021_2024", pre),
        ("holdout_2025", holdout),
    ):
        for trade in payload["result"]["trades"]:
            row = dict(trade)
            row["period"] = period
            row["date"] = str(row["date"])
            rows.append(row)
    return rows


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return round(max_dd, 3)


def _profit_factor(values: list[float]) -> float:
    wins = sum(value for value in values if value > 0)
    losses = -sum(value for value in values if value < 0)
    if losses <= 0:
        return math.inf if wins > 0 else 0.0
    return wins / losses


def _max_consecutive_losses(values: list[float]) -> int:
    current = 0
    worst = 0
    for value in values:
        if value < 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def _summarize(rows: list[dict[str, Any]], ticks_per_side: int) -> dict[str, Any]:
    stressed = [float(row["stressed_net_r"]) for row in rows]
    dates = [str(row["date"]) for row in rows]
    by_year: dict[str, float] = {}
    by_month: dict[str, float] = {}
    for date, value in zip(dates, stressed, strict=True):
        by_year[date[:4]] = by_year.get(date[:4], 0.0) + value
        by_month[date[:7]] = by_month.get(date[:7], 0.0) + value

    total_r = float(sum(stressed))
    max_dd = _max_drawdown(stressed)
    return {
        "ticks_per_side": ticks_per_side,
        "extra_round_trip_points": round(ticks_per_side * NQ_TICK_SIZE_POINTS * 2.0, 3),
        "trade_count": len(rows),
        "total_net_r": round(total_r, 3),
        "avg_net_r": round(float(np.mean(stressed)) if stressed else 0.0, 4),
        "profit_factor": round(float(_profit_factor(stressed)), 4),
        "max_drawdown_r": max_dd,
        "calmar_proxy": round(total_r / abs(max_dd), 4) if max_dd < 0 else math.inf,
        "win_rate": round(float(np.mean([value > 0 for value in stressed])) if stressed else 0.0, 4),
        "max_consecutive_losses": _max_consecutive_losses(stressed),
        "min_month_r": round(min(by_month.values()), 3) if by_month else 0.0,
        "r_by_year": {key: round(value, 3) for key, value in sorted(by_year.items())},
        "r_by_month": {key: round(value, 3) for key, value in sorted(by_month.items())},
    }


def _stress_rows(trades: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trade_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []

    periods = ("pre_holdout_2021_2024", "holdout_2025", "combined_2021_2025")
    for ticks_per_side in STRESS_TICKS_PER_SIDE:
        extra_round_trip_points = ticks_per_side * NQ_TICK_SIZE_POINTS * 2.0
        stressed_for_period: dict[str, list[dict[str, Any]]] = {period: [] for period in periods}

        for trade in trades:
            risk_points = float(trade.get("risk_points") or 0.0)
            if risk_points <= 0:
                continue
            extra_slippage_r = extra_round_trip_points / risk_points
            stressed_net_r = float(trade.get("net_r_multiple", trade.get("r_multiple", 0.0))) - extra_slippage_r
            row = {
                "period": trade["period"],
                "ticks_per_side": ticks_per_side,
                "date": trade["date"],
                "exit_type": trade.get("exit_type"),
                "risk_points": round(risk_points, 4),
                "base_net_r": round(float(trade.get("net_r_multiple", 0.0)), 6),
                "extra_slippage_r": round(extra_slippage_r, 6),
                "stressed_net_r": round(stressed_net_r, 6),
            }
            trade_rows.append(row)
            stressed_for_period[trade["period"]].append(row)
            stressed_for_period["combined_2021_2025"].append(row)

        for period in periods:
            period_rows = sorted(stressed_for_period[period], key=lambda row: row["date"])
            summary = _summarize(period_rows, ticks_per_side)
            summary["period"] = period
            summary_rows.append(summary)

    return trade_rows, summary_rows


def _scenario(summary_rows: list[dict[str, Any]], period: str, ticks_per_side: int) -> dict[str, Any]:
    for row in summary_rows:
        if row["period"] == period and row["ticks_per_side"] == ticks_per_side:
            return row
    raise KeyError((period, ticks_per_side))


def _verdict(summary_rows: list[dict[str, Any]]) -> dict[str, Any]:
    holdout_2 = _scenario(summary_rows, "holdout_2025", 2)
    pre_2 = _scenario(summary_rows, "pre_holdout_2021_2024", 2)
    combined_4 = _scenario(summary_rows, "combined_2021_2025", 4)
    holdout_4 = _scenario(summary_rows, "holdout_2025", 4)
    combined_8 = _scenario(summary_rows, "combined_2021_2025", 8)

    stress_pass = (
        holdout_2["total_net_r"] > 0
        and holdout_2["profit_factor"] >= 1.2
        and pre_2["total_net_r"] > 0
        and combined_4["total_net_r"] > 0
    )
    return {
        "label": "dry_run_candidate_cost_stress_pass" if stress_pass else "cost_stress_fail",
        "deployability": "live_native",
        "exact_replay_required": "complete",
        "profile_status": "disabled",
        "reason": (
            "Pre-holdout and 2025 holdout remain positive under 2 ticks/side adverse slippage; "
            "the combined 2021-2025 set remains positive under 4 ticks/side."
            if stress_pass
            else "Cost stress did not preserve positive edge under the minimum stress thresholds."
        ),
        "important_caveat": (
            "This is a post-exact replay cost stress, not a replacement for paper/dry-run fill monitoring. "
            "The 8 ticks/side stress is an extreme scenario and is used to locate the edge boundary."
        ),
        "operating_plan_next_step": (
            "Keep profile disabled for live orders; if promoted, run dry-only/paper monitoring first, "
            "track live-vs-exact fill slippage in ticks per side, and do not scale risk until observed "
            "slippage is comfortably inside the 2 ticks/side stress envelope."
        ),
        "key_scenarios": {
            "pre_holdout_2_ticks": pre_2,
            "holdout_2_ticks": holdout_2,
            "holdout_4_ticks": holdout_4,
            "combined_4_ticks": combined_4,
            "combined_8_ticks": combined_8,
        },
    }


def _write_markdown(payload: dict[str, Any], path: Path) -> None:
    summary_rows = payload["summary_rows"]
    verdict = payload["verdict"]
    lines = [
        "# NQ NY ORB Rolling-Gate Cost Stress",
        "",
        "- Inputs: exact replay artifacts only.",
        "- Baseline R: `net_r_multiple`, already commission-adjusted.",
        "- Stress model: subtract additional adverse round-trip slippage from every trade.",
        f"- Tick size: `{NQ_TICK_SIZE_POINTS}` points.",
        "- Candidate deployability: `live_native`; execution profile remains disabled.",
        "",
        "## Verdict",
        "",
        f"- `{verdict['label']}`",
        f"- {verdict['reason']}",
        f"- Caveat: {verdict['important_caveat']}",
        f"- Next operating step: {verdict['operating_plan_next_step']}",
        "",
        "## Stress Summary",
        "",
        "| Period | Ticks/side | RT points | Trades | Net R | PF | DD R | Calmar | Win rate | Max loss streak | Min month R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['period']} | {row['ticks_per_side']} | {row['extra_round_trip_points']:.2f} | "
            f"{row['trade_count']} | {row['total_net_r']:.3f} | {row['profit_factor']:.3f} | "
            f"{row['max_drawdown_r']:.3f} | {row['calmar_proxy']:.3f} | "
            f"{row['win_rate']:.2%} | {row['max_consecutive_losses']} | {row['min_month_r']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Key Reads",
            "",
        ]
    )
    for name, row in verdict["key_scenarios"].items():
        lines.append(
            f"- `{name}`: Net R `{row['total_net_r']}`, PF `{row['profit_factor']}`, "
            f"DD `{row['max_drawdown_r']}`, min month `{row['min_month_r']}`."
        )

    lines.extend(
        [
            "",
            "## Files",
            "",
            f"- Summary CSV: `{payload['summary_csv']}`",
            f"- Trade-level stress CSV: `{payload['trade_csv']}`",
            "",
        ]
    )
    path.write_text("\n".join(lines))


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    trades = _load_trades()
    trade_rows, summary_rows = _stress_rows(trades)
    verdict = _verdict(summary_rows)

    summary_csv = ARTIFACT_DIR / "cost_stress_summary.csv"
    trade_csv = ARTIFACT_DIR / "cost_stress_trades.csv"
    pd.DataFrame(summary_rows).to_csv(summary_csv, index=False)
    pd.DataFrame(trade_rows).to_csv(trade_csv, index=False)

    payload = {
        "run_id": RUN_ID,
        "inputs": {
            "pre_holdout": str(PRE_HOLDOUT_ARTIFACT),
            "holdout_2025": str(HOLDOUT_ARTIFACT),
        },
        "stress_ticks_per_side": list(STRESS_TICKS_PER_SIDE),
        "tick_size_points": NQ_TICK_SIZE_POINTS,
        "summary_rows": summary_rows,
        "verdict": verdict,
        "summary_csv": str(summary_csv),
        "trade_csv": str(trade_csv),
    }

    json_path = ARTIFACT_DIR / "cost_stress_results.json"
    md_path = ARTIFACT_DIR / "cost_stress_results.md"
    json_path.write_text(json.dumps(payload, indent=2))
    _write_markdown(payload, md_path)

    print(
        json.dumps(
            {
                "success": True,
                "json": str(json_path),
                "markdown": str(md_path),
                "summary_csv": str(summary_csv),
                "trade_csv": str(trade_csv),
                "verdict": verdict["label"],
                "key_scenarios": verdict["key_scenarios"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
