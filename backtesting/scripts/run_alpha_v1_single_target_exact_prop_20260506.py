#!/usr/bin/env python3
"""Exact replay + phase-one sizing for ALPHA_V1 single-target candidates.

Creates temporary in-memory execution profiles only. It does not edit
execution/config/exec_configs.json.
"""

from __future__ import annotations

import copy
import json
import math
import sys
import time
from collections import defaultdict
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
from trader.main import DEFAULT_CONFIG, SESSION_CONFIGS, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "alpha_v1_single_target_exact_prop_20260506"
BASE_PROFILE = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"

RESULT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_SINGLE_TARGET_EXACT_PROP_20260506.md"

FUNDED_MODEL = {
    "account_size_usd": 50_000.0,
    "starting_balance_usd": 50_000.0,
    "trailing_drawdown_usd": 2_000.0,
    "max_trailing_breach_usd": 50_000.0,
    "first_payout_floor_usd": 52_500.0,
    "first_payout_withdrawal_usd": 500.0,
    "challenge_fee_usd": 100.0,
    "cohort_spacing_days": 14,
}

RISK_VALUES = (
    50,
    75,
    100,
    125,
    150,
    175,
    200,
    225,
    250,
    275,
    300,
    325,
    350,
    375,
    400,
    450,
    500,
    600,
    700,
)

RESEARCH_REFERENCE = {
    "es_ny_orb_single_1r": {"trades": 846, "net_r": 186.4, "profit_factor": 1.57, "max_dd_r": 8.0},
    "nq_ny_orb_r11_single_1p4r": {"trades": 552, "net_r": 149.2, "profit_factor": 1.58, "max_dd_r": 6.4},
    "es_asia_orb_single_1p25r": {"trades": 1422, "net_r": 173.7, "profit_factor": 1.32, "max_dd_r": 13.6},
}


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    session_key: str
    target_r: float
    source: str
    live_support_notes: str
    full_overrides: dict[str, Any] | None = None

    @property
    def profile_name(self) -> str:
        return f"EXACT_{self.key}".upper()[:120]


CANDIDATES = (
    Candidate(
        key="es_ny_orb_single_1r",
        label="ES NY ORB single 1.0R",
        session_key="ES_NY",
        target_r=1.0,
        source=f"{BASE_PROFILE} ES_NY clone",
        live_support_notes="Native ORB execution fields: ALPHA_V1-A ES_NY cloned with exit_mode=single_target, rr=1.0, tp1_ratio=1.0.",
    ),
    Candidate(
        key="nq_ny_orb_r11_single_1p4r",
        label="NQ NY ORB R11 single 1.4R",
        session_key="NQ_NY",
        target_r=1.4,
        source="research NQ_NY R11 branch override",
        live_support_notes="Native ORB execution fields using the R11 NY window with exit_mode=single_target, rr=1.4, tp1_ratio=1.0.",
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
            "excluded_dow": [4],
            "fomc_exclusion": False,
            "min_stop_pts": 0.0,
            "min_tp1_pts": 0.0,
            "risk_usd": 400,
            "max_single_risk_usd": 400,
        },
    ),
    Candidate(
        key="es_asia_orb_single_1p25r",
        label="ES Asia ORB single 1.25R",
        session_key="ES_Asia",
        target_r=1.25,
        source=f"{BASE_PROFILE} ES_Asia clone",
        live_support_notes="Native ORB execution fields: ALPHA_V1-A ES_Asia cloned with exit_mode=single_target, rr=1.25, tp1_ratio=1.0.",
    ),
)


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
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
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        out = float(data)
        return out if math.isfinite(out) else None
    return data


def _ts(value: Any) -> pd.Timestamp:
    if value is None or value == "":
        return pd.NaT
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts


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


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator) * 100.0, 2) if denominator else 0.0


def _candidate_overrides(candidate: Candidate, alpha: ExecutionConfig) -> dict[str, Any]:
    if candidate.full_overrides is not None:
        overrides = copy.deepcopy(candidate.full_overrides)
    elif candidate.session_key in alpha.session_overrides:
        overrides = copy.deepcopy(alpha.session_overrides[candidate.session_key])
    else:
        overrides = copy.deepcopy(SESSION_CONFIGS[candidate.session_key])
    overrides.update(
        {
            "rr": candidate.target_r,
            "tp1_ratio": 1.0,
            "exit_mode": "single_target",
        }
    )
    return overrides


def _profile_for(candidate: Candidate, alpha: ExecutionConfig) -> ExecutionConfig:
    return ExecutionConfig(
        name=candidate.profile_name,
        enabled=True,
        max_open_contracts=20,
        webhooks=[],
        session_overrides={candidate.session_key: _candidate_overrides(candidate, alpha)},
        lsi_session_overrides={},
    )


def _run_exact(config: dict[str, Any], candidate: Candidate, profile: ExecutionConfig) -> dict[str, Any]:
    cache_path = RESULT_DIR / f"exact_{candidate.key}.json"
    if cache_path.exists():
        print(f"[exact cache] {candidate.label}", flush=True)
        return json.loads(cache_path.read_text())

    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        label = f"ALPHA V1 Exact SingleTarget {candidate.label} {FULL_START} to {END_DATE}"
        result = hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=label,
        )
    finally:
        hb.load_exec_configs = original_loader

    result_id = hb.save_profile_backtest(result)
    payload = {
        "candidate": candidate.__dict__,
        "profile_name": profile.name,
        "profile_session_overrides": _safe_json(profile.session_overrides),
        "result_id": result_id,
        "result": result,
    }
    cache_path.write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True, default=_json_default) + "\n")
    return payload


def _slice_trades(trades: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [trade for trade in trades if start <= str(trade.get("date", "")) <= end]


def _metrics(candidate: Candidate, trades: list[dict[str, Any]], window: str, start: str) -> dict[str, Any]:
    selected = _slice_trades(trades, start, END_DATE)
    summary = hb._compute_summary(selected)
    exits = dict(summary.get("exit_breakdown") or {})
    total = int(summary.get("total_trades") or 0)
    target_count = int(exits.get("tp2_direct", 0) + exits.get("tp1_tp2", 0))
    sl_count = int(exits.get("sl", 0))
    eod_count = int(exits.get("eod", 0) + exits.get("tp1_eod", 0))
    return {
        "candidate": candidate.key,
        "label": candidate.label,
        "session": candidate.session_key,
        "window": window,
        "start": start,
        "end": END_DATE,
        "target_r": candidate.target_r,
        "trades": total,
        "net_r": _round(summary.get("total_r"), 3),
        "profit_factor": _round(summary.get("profit_factor"), 4),
        "win_rate_pct": _round(float(summary.get("win_rate") or 0.0) * 100.0, 2),
        "max_dd_r": _round(abs(float(summary.get("max_drawdown_r") or 0.0)), 3),
        "sharpe": _round(summary.get("sharpe_ratio"), 4),
        "calmar": _round(summary.get("calmar_ratio"), 4),
        "target_count": target_count,
        "target_rate_pct": _pct(target_count, total),
        "sl_count": sl_count,
        "sl_rate_pct": _pct(sl_count, total),
        "eod_count": eod_count,
        "eod_rate_pct": _pct(eod_count, total),
        "exit_breakdown": exits,
        "deployability": "live_native",
        "live_support_notes": candidate.live_support_notes,
        "exact_replay_required": "complete",
    }


def _trade_rows(candidate: Candidate, trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        exit_ts = _ts(trade.get("exit_time") or trade.get("entry_time") or trade.get("date"))
        entry_ts = _ts(trade.get("entry_time") or trade.get("exit_time") or trade.get("date"))
        if pd.isna(exit_ts):
            continue
        rows.append(
            {
                "candidate": candidate.key,
                "label": candidate.label,
                "session": candidate.session_key,
                "date": str(trade.get("date") or exit_ts.date().isoformat()),
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "direction": str(trade.get("direction", "")),
                "r_multiple": float(trade.get("r_multiple", 0.0) or 0.0),
                "exit_type": str(trade.get("exit_type", "")),
            }
        )
    return sorted(rows, key=lambda row: (row["exit_ts"], row["candidate"], row["entry_ts"]))


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize()
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def _simulate_funded(base_rows: list[dict[str, Any]], risk_usd: float) -> list[dict[str, Any]]:
    rows = []
    for row in base_rows:
        if not (FULL_START <= str(row["date"]) <= END_DATE):
            continue
        out = dict(row)
        out["risk_usd"] = float(risk_usd)
        out["pnl_usd"] = float(row["r_multiple"]) * float(risk_usd)
        rows.append(out)
    rows.sort(key=lambda row: (row["exit_ts"], row["candidate"], row["entry_ts"]))

    outcomes = []
    for account_id, start_ts in enumerate(_cohort_starts(FULL_START, END_DATE), start=1):
        balance = float(FUNDED_MODEL["starting_balance_usd"])
        floor = balance - float(FUNDED_MODEL["trailing_drawdown_usd"])
        high_eod = balance
        current_day: str | None = None
        outcome = "open"
        outcome_date = pd.Timestamp(END_DATE).date().isoformat()
        trades_taken = 0
        ending_index = -1

        for idx, row in enumerate(rows):
            if row["exit_ts"] < start_ts:
                continue
            trade_day = pd.Timestamp(row["exit_ts"]).date().isoformat()
            if current_day is not None and trade_day != current_day:
                high_eod = max(high_eod, balance)
                floor = max(
                    floor,
                    min(
                        high_eod - float(FUNDED_MODEL["trailing_drawdown_usd"]),
                        float(FUNDED_MODEL["max_trailing_breach_usd"]),
                    ),
                )
            current_day = trade_day
            balance += float(row["pnl_usd"])
            trades_taken += 1
            ending_index = idx
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_MODEL["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        if outcome == "open":
            future = [row for row in rows if row["exit_ts"] >= start_ts]
            if future:
                outcome_date = pd.Timestamp(future[-1]["exit_ts"]).date().isoformat()

        net_after_fee = (
            float(FUNDED_MODEL["first_payout_withdrawal_usd"]) - float(FUNDED_MODEL["challenge_fee_usd"])
            if outcome == "payout"
            else -float(FUNDED_MODEL["challenge_fee_usd"])
        )
        outcomes.append(
            {
                "account_id": account_id,
                "account_start": start_ts.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date) - start_ts).days) + 1,
                "trades_to_outcome": trades_taken,
                "ending_balance_usd": _round(balance, 2),
                "breach_floor_usd": _round(floor, 2),
                "net_after_fee_usd": _round(net_after_fee, 2),
                "ending_trade_index": ending_index,
            }
        )
    return outcomes


def _max_consecutive(outcomes: list[dict[str, Any]], outcome_name: str) -> int:
    max_run = 0
    run = 0
    for row in sorted(outcomes, key=lambda item: item["account_start"]):
        if row["outcome"] == outcome_name:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def _score_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(outcomes)
    payouts = [row for row in outcomes if row["outcome"] == "payout"]
    breaches = [row for row in outcomes if row["outcome"] == "breach"]
    opens = [row for row in outcomes if row["outcome"] == "open"]
    month_breaches: dict[str, int] = defaultdict(int)
    for row in breaches:
        month_breaches[str(row["account_start"])[:7]] += 1
    days = [int(row["days_to_outcome"]) for row in payouts]
    trades = [int(row["trades_to_outcome"]) for row in payouts]
    ev_values = [float(row["net_after_fee_usd"] or 0.0) for row in outcomes]
    ratio_raw = math.inf if payouts and not breaches else (len(payouts) / len(breaches) if breaches else 0.0)
    return {
        "accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "payout_rate_pct": _pct(len(payouts), total),
        "breach_rate_pct": _pct(len(breaches), total),
        "open_rate_pct": _pct(len(opens), total),
        "payout_breach_ratio": ratio_raw,
        "payout_breach_ratio_smooth": _round((len(payouts) + 0.5) / (len(breaches) + 0.5), 3),
        "ev_per_account_usd": _round(float(np.mean(ev_values)), 2) if ev_values else 0.0,
        "avg_days_to_payout": _round(float(np.mean(days)), 1) if days else None,
        "median_days_to_payout": _round(float(np.median(days)), 1) if days else None,
        "fastest_days_to_payout": min(days) if days else None,
        "avg_trades_to_payout": _round(float(np.mean(trades)), 1) if trades else None,
        "median_trades_to_payout": _round(float(np.median(trades)), 1) if trades else None,
        "avg_open_balance_usd": _round(float(np.mean([row["ending_balance_usd"] for row in opens])), 2) if opens else None,
        "max_consecutive_breaches": _max_consecutive(outcomes, "breach"),
        "max_consecutive_payouts": _max_consecutive(outcomes, "payout"),
        "worst_month_breaches": max(month_breaches.values()) if month_breaches else 0,
    }


def _risk_score(row: dict[str, Any]) -> float:
    payout = float(row["payout_rate_pct"] or 0.0)
    breach = float(row["breach_rate_pct"] or 0.0)
    ev = float(row["ev_per_account_usd"] or 0.0)
    days = float(row["avg_days_to_payout"] or 999.0)
    ratio = float(row["payout_breach_ratio_smooth"] or 0.0)
    max_run = float(row["max_consecutive_breaches"] or 0.0)
    worst_month = float(row["worst_month_breaches"] or 0.0)
    risk = float(row["risk_usd"] or 0.0)
    return round(ev + payout * 2.0 + ratio * 45.0 - breach * 3.5 - days * 1.25 - max_run * 35.0 - worst_month * 15.0 - risk * 0.03, 4)


def _run_risk_sweep(candidate: Candidate, rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, list[dict[str, Any]]]]:
    risk_rows: list[dict[str, Any]] = []
    selected_outcomes: dict[str, list[dict[str, Any]]] = {}
    for risk in RISK_VALUES:
        outcomes = _simulate_funded(rows, risk)
        score = _score_outcomes(outcomes)
        row = {
            "candidate": candidate.key,
            "label": candidate.label,
            "risk_usd": int(risk),
            **score,
        }
        row["balanced_score"] = _risk_score(row)
        risk_rows.append(row)

    df = pd.DataFrame(risk_rows)
    positive = df[(df["ev_per_account_usd"] > 0.0) & (df["payouts"] > 0)].copy()
    guarded = positive[(positive["payout_rate_pct"] >= 35.0) & (positive["breach_rate_pct"] <= 45.0)].copy()
    low_breach = positive[(positive["breach_rate_pct"] <= 25.0)].copy()
    sprint = positive[
        (positive["payout_rate_pct"] >= 75.0)
        & (positive["breach_rate_pct"] <= 10.0)
    ].copy()
    low_breach_ev = positive[(positive["breach_rate_pct"] <= 10.0)].copy()

    best_balanced = df.sort_values(["balanced_score", "ev_per_account_usd"], ascending=[False, False]).iloc[0].to_dict()
    best_ev = df.sort_values(["ev_per_account_usd", "payout_rate_pct"], ascending=[False, False]).iloc[0].to_dict()
    best_guarded = (
        guarded.sort_values(
            ["balanced_score", "ev_per_account_usd", "avg_days_to_payout"],
            ascending=[False, False, True],
        ).iloc[0].to_dict()
        if not guarded.empty
        else best_balanced
    )
    best_low_breach = (
        low_breach.sort_values(
            ["payout_breach_ratio_smooth", "ev_per_account_usd", "avg_days_to_payout"],
            ascending=[False, False, True],
        ).iloc[0].to_dict()
        if not low_breach.empty
        else best_guarded
    )
    best_sprint = (
        sprint.sort_values(
            ["avg_days_to_payout", "ev_per_account_usd", "payout_rate_pct"],
            ascending=[True, False, False],
        ).iloc[0].to_dict()
        if not sprint.empty
        else best_guarded
    )
    best_low_breach_ev = (
        low_breach_ev.sort_values(
            ["ev_per_account_usd", "avg_days_to_payout", "payout_rate_pct"],
            ascending=[False, True, False],
        ).iloc[0].to_dict()
        if not low_breach_ev.empty
        else best_low_breach
    )
    picks = {
        "best_balanced": best_balanced,
        "best_ev": best_ev,
        "best_guarded": best_guarded,
        "best_low_breach": best_low_breach,
        "best_sprint": best_sprint,
        "best_low_breach_ev": best_low_breach_ev,
    }
    for name, row in picks.items():
        selected_outcomes[name] = _simulate_funded(rows, float(row["risk_usd"]))
    return risk_rows, picks, selected_outcomes


def _md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _compact_pick(candidate: Candidate, bucket: str, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate": candidate.key,
        "label": candidate.label,
        "bucket": bucket,
        "risk_usd": row.get("risk_usd"),
        "accounts": row.get("accounts"),
        "payouts": row.get("payouts"),
        "breaches": row.get("breaches"),
        "open": row.get("open"),
        "payout_rate_pct": row.get("payout_rate_pct"),
        "breach_rate_pct": row.get("breach_rate_pct"),
        "ev_per_account_usd": row.get("ev_per_account_usd"),
        "avg_days_to_payout": row.get("avg_days_to_payout"),
        "median_days_to_payout": row.get("median_days_to_payout"),
        "max_consecutive_breaches": row.get("max_consecutive_breaches"),
        "balanced_score": row.get("balanced_score"),
    }


def _write_report(payload: dict[str, Any]) -> None:
    metric_rows = payload["window_metrics"]
    full_metrics = [row for row in metric_rows if row["window"] == "full"]
    pick_rows = payload["pick_rows"]
    chosen = [row for row in pick_rows if row["bucket"] == "best_sprint"]
    conservative = [row for row in pick_rows if row["bucket"] == "best_low_breach_ev"]
    exact_vs_research = []
    for row in full_metrics:
        ref = RESEARCH_REFERENCE.get(str(row["candidate"]), {})
        exact_vs_research.append(
            {
                "label": row["label"],
                "research_net_r": ref.get("net_r"),
                "exact_net_r": row["net_r"],
                "delta_r": _round(float(row["net_r"] or 0.0) - float(ref.get("net_r") or 0.0), 2),
                "research_pf": ref.get("profit_factor"),
                "exact_pf": row["profit_factor"],
                "research_dd_r": ref.get("max_dd_r"),
                "exact_dd_r": row["max_dd_r"],
            }
        )
    lines = [
        "# ALPHA_V1 Single-Target Exact Replay + Phase-One Sizing",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Exact/live-engine window: `{FULL_START}` to `{END_DATE}`",
        "- Engine path: `execution/src/trader/historical_backtest.py` using temporary in-memory execution profiles.",
        f"- Base profile cloned where applicable: `{BASE_PROFILE}`. No live execution config file was edited.",
        "- Account model: 50k account, 2k EOD trailing drawdown, trail cap at 50k, first payout at 52.5k, $500 first payout, $100 account/reset cost, starts every 14 calendar days.",
        "- Deployability: all three candidates are `live_native`; exact replay status is `complete`.",
        "",
        "## Exact Replay Stats",
        "",
        _md_table(
            full_metrics,
            [
                "label",
                "trades",
                "net_r",
                "profit_factor",
                "win_rate_pct",
                "max_dd_r",
                "target_rate_pct",
                "sl_rate_pct",
                "eod_rate_pct",
                "result_id",
            ],
        ),
        "",
        "## Research Vs Exact Replay",
        "",
        _md_table(
            exact_vs_research,
            [
                "label",
                "research_net_r",
                "exact_net_r",
                "delta_r",
                "research_pf",
                "exact_pf",
                "research_dd_r",
                "exact_dd_r",
            ],
        ),
        "",
        "## Preferred Phase-One Sizing",
        "",
        "_Preferred means the fastest row that still clears at least 75% payout and at most 10% breach. If no row clears that guard, it falls back to the guarded positive-EV row._",
        "",
        _md_table(
            chosen,
            [
                "label",
                "risk_usd",
                "payouts",
                "breaches",
                "open",
                "payout_rate_pct",
                "breach_rate_pct",
                "ev_per_account_usd",
                "avg_days_to_payout",
                "max_consecutive_breaches",
            ],
        ),
        "",
        "## Conservative Low-Breach Sizing",
        "",
        "_This is the highest-EV row with no more than 10% breaches. It is safer but can be materially slower._",
        "",
        _md_table(
            conservative,
            [
                "label",
                "risk_usd",
                "payouts",
                "breaches",
                "open",
                "payout_rate_pct",
                "breach_rate_pct",
                "ev_per_account_usd",
                "avg_days_to_payout",
                "max_consecutive_breaches",
            ],
        ),
        "",
        "## Risk Buckets",
        "",
        _md_table(
            pick_rows,
            [
                "label",
                "bucket",
                "risk_usd",
                "payouts",
                "breaches",
                "payout_rate_pct",
                "breach_rate_pct",
                "ev_per_account_usd",
                "avg_days_to_payout",
                "max_consecutive_breaches",
            ],
        ),
        "",
        "## Read",
        "",
        "- `best_sprint` is the practical phase-one default: it prioritizes time to payout inside a 75% payout / 10% breach guard.",
        "- `best_low_breach_ev` is the conservative standalone default when speed matters less than avoiding resets.",
        "- `best_guarded` is a broad positive-EV fallback: at least 35% payout rate when possible and no more than 45% breaches.",
        "- `best_ev` is included as an aggressive ceiling; it can over-size a choppy leg if the EV comes with poor breach clustering.",
        "- The exact replay materially haircut ES NY versus the research sweep, so exact replay should supersede the earlier optimistic ES NY single-target read.",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    exec_profiles = {profile.name: profile for profile in load_exec_configs(config)}
    alpha = exec_profiles[BASE_PROFILE]

    exact_payloads = []
    window_metrics: list[dict[str, Any]] = []
    trade_rows: list[dict[str, Any]] = []
    risk_rows: list[dict[str, Any]] = []
    pick_rows: list[dict[str, Any]] = []
    outcome_exports: dict[str, Any] = {}

    for idx, candidate in enumerate(CANDIDATES, start=1):
        profile = _profile_for(candidate, alpha)
        print(f"[exact {idx}/{len(CANDIDATES)}] {candidate.label} profile={profile.name}", flush=True)
        exact = _run_exact(config, candidate, profile)
        result = exact["result"]
        trades = result.get("trades", [])
        print(
            "  -> trades={trades} net={net:+.2f}R pf={pf:.3f} dd={dd:.2f}R id={rid}".format(
                trades=len(trades),
                net=float(result["summary"].get("total_r") or 0.0),
                pf=float(result["summary"].get("profit_factor") or 0.0),
                dd=abs(float(result["summary"].get("max_drawdown_r") or 0.0)),
                rid=exact.get("result_id", "cached"),
            ),
            flush=True,
        )

        exact_payloads.append({key: value for key, value in exact.items() if key != "result"})
        for window, start in (("full", FULL_START), ("last_2y", LAST_2Y_START), ("last_1y", LAST_1Y_START)):
            row = _metrics(candidate, trades, window, start)
            row["result_id"] = exact.get("result_id")
            window_metrics.append(row)

        rows = _trade_rows(candidate, trades)
        trade_rows.extend(rows)
        print(f"[risk {idx}/{len(CANDIDATES)}] {candidate.label} rows={len(rows)}", flush=True)
        candidate_risk_rows, picks, outcomes = _run_risk_sweep(candidate, rows)
        risk_rows.extend(candidate_risk_rows)
        for bucket, row in picks.items():
            pick_rows.append(_compact_pick(candidate, bucket, row))
        outcome_exports[candidate.key] = outcomes
        pd.DataFrame(candidate_risk_rows).to_csv(RESULT_DIR / f"risk_sweep_{candidate.key}.csv", index=False)
        (RESULT_DIR / f"outcomes_{candidate.key}.json").write_text(
            json.dumps(outcomes, indent=2, sort_keys=True, default=_json_default) + "\n",
            encoding="utf-8",
        )

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "window": {"start": FULL_START, "end": END_DATE},
        "funded_model": FUNDED_MODEL,
        "risk_values": list(RISK_VALUES),
        "exact_payloads": exact_payloads,
        "window_metrics": window_metrics,
        "pick_rows": pick_rows,
        "paths": {
            "result_dir": str(RESULT_DIR),
            "summary_json": str(RESULT_DIR / "summary.json"),
            "exact_trades_csv": str(RESULT_DIR / "exact_trades.csv"),
            "window_metrics_csv": str(RESULT_DIR / "window_metrics.csv"),
            "risk_sweep_csv": str(RESULT_DIR / "risk_sweep_all.csv"),
            "risk_picks_csv": str(RESULT_DIR / "risk_picks.csv"),
            "report": str(REPORT_PATH),
        },
        "elapsed_sec": round(time.time() - started, 1),
    }

    pd.DataFrame(trade_rows).to_csv(RESULT_DIR / "exact_trades.csv", index=False)
    pd.DataFrame(window_metrics).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    pd.DataFrame(risk_rows).to_csv(RESULT_DIR / "risk_sweep_all.csv", index=False)
    pd.DataFrame(pick_rows).to_csv(RESULT_DIR / "risk_picks.csv", index=False)
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True, default=_json_default) + "\n")
    _write_report(payload)

    print("SUMMARY_JSON", RESULT_DIR / "summary.json", flush=True)
    print("REPORT", REPORT_PATH, flush=True)
    print("PREFERRED")
    for row in [row for row in pick_rows if row["bucket"] == "best_sprint"]:
        print(json.dumps(row, sort_keys=True, default=_json_default), flush=True)
    print(f"Elapsed {payload['elapsed_sec']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
