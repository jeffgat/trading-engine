#!/usr/bin/env python3
"""Phase-one funded payout/risk sizing for HOT_REGIME_V1 NQ+ES portfolios.

This is a research artifact only. It replays selected portfolio combinations
through the production exact/live engine, then runs a 50k prop-firm first-payout
simulation while sweeping per-leg USD risk.
"""

from __future__ import annotations

import copy
import itertools
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_hot_regime_v1_nq_es_portfolio_search as port  # noqa: E402


RUN_SLUG = "hot_regime_v1_nq_es_phase1_payout_risk_20260505"
RESULT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "HOT_REGIME_V1_NQ_ES_PHASE1_PAYOUT_RISK_20260505.md"

START_DATE = port.START_DATE
END_DATE = port.END_DATE

SELECTED_PORTFOLIOS = (
    "current_nq_es_all6",
    "constrained_no_nq_orb_no_es_lsi",
    "combo_all_cleaner_core5",
    "alt_es_ny_lowdd_rr2_tp075",
    "constrained_nq_es_all6",
    "constrained_nq_es_no_es_lsi",
)

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

RISK_VALUES = (0, 50, 75, 100, 125, 150, 175, 200, 250, 300, 350, 400, 450, 500, 600, 700)
POSITIVE_RISK_VALUES = tuple(v for v in RISK_VALUES if v > 0)


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


def _pct(numerator: int | float, denominator: int | float) -> float:
    if not denominator:
        return 0.0
    return round(float(numerator) / float(denominator) * 100.0, 2)


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


def _ts(value: Any) -> pd.Timestamp:
    if value is None or value == "":
        return pd.NaT
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(None)
    return ts


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize()
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def _risk_key(risk_map: dict[str, float]) -> tuple[tuple[str, int], ...]:
    return tuple(sorted((leg, int(round(float(risk)))) for leg, risk in risk_map.items()))


def _risk_map_json(risk_map: dict[str, float]) -> str:
    return json.dumps({leg: int(round(float(risk))) for leg, risk in sorted(risk_map.items())}, sort_keys=True)


def _trade_rows(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        entry_ts = _ts(trade.get("entry_time") or trade.get("exit_time") or trade.get("date"))
        exit_ts = _ts(trade.get("exit_time") or trade.get("entry_time") or trade.get("date"))
        if pd.isna(exit_ts):
            continue
        date = str(trade.get("date") or exit_ts.date().isoformat())
        rows.append(
            {
                "leg": str(trade.get("session", "")),
                "date": date,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "direction": str(trade.get("direction", "")),
                "r_multiple": float(trade.get("r_multiple", 0.0) or 0.0),
                "exit_type": str(trade.get("exit_type", "")),
            }
        )
    return sorted(rows, key=lambda row: (row["exit_ts"], row["leg"], row["entry_ts"]))


def _pnl_rows(base_rows: list[dict[str, Any]], risk_map: dict[str, float]) -> list[dict[str, Any]]:
    rows = []
    for row in base_rows:
        risk = float(risk_map.get(str(row["leg"]), 0.0) or 0.0)
        if risk <= 0:
            continue
        out = dict(row)
        out["risk_usd"] = risk
        out["pnl_usd"] = float(out["r_multiple"]) * risk
        rows.append(out)
    return sorted(rows, key=lambda row: (row["exit_ts"], row["leg"], row["entry_ts"]))


def _simulate_funded(base_rows: list[dict[str, Any]], risk_map: dict[str, float], *, start: str, end: str) -> list[dict[str, Any]]:
    rows = _pnl_rows(base_rows, risk_map)
    rows = [row for row in rows if start <= str(row["date"]) <= end]
    outcomes = []
    for account_id, start_ts in enumerate(_cohort_starts(start, end), start=1):
        balance = float(FUNDED_MODEL["starting_balance_usd"])
        floor = balance - float(FUNDED_MODEL["trailing_drawdown_usd"])
        high_eod = balance
        current_day: str | None = None
        outcome = "open"
        outcome_date = pd.Timestamp(end).date().isoformat()
        trades_taken = 0
        leg_counts: dict[str, int] = defaultdict(int)
        leg_pnl: dict[str, float] = defaultdict(float)
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
            pnl = float(row["pnl_usd"])
            balance += pnl
            trades_taken += 1
            leg = str(row["leg"])
            leg_counts[leg] += 1
            leg_pnl[leg] += pnl
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
                "leg_counts": dict(sorted(leg_counts.items())),
                "leg_pnl": {leg: _round(value, 2) for leg, value in sorted(leg_pnl.items())},
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


def _funded_row(portfolio: str, base_rows: list[dict[str, Any]], risk_map: dict[str, float], source: str) -> dict[str, Any]:
    outcomes = _simulate_funded(base_rows, risk_map, start=START_DATE, end=END_DATE)
    score = _score_outcomes(outcomes)
    total_active_risk = sum(float(value) for value in risk_map.values() if value > 0)
    active_legs = [leg for leg, value in sorted(risk_map.items()) if value > 0]
    row = {
        "portfolio": portfolio,
        "source": source,
        "risk_map_json": _risk_map_json(risk_map),
        "active_legs": len(active_legs),
        "active_leg_names": ",".join(active_legs),
        "total_active_risk_usd": int(total_active_risk),
        "max_leg_risk_usd": int(max([0, *[float(v) for v in risk_map.values()]])),
        **score,
    }
    for leg, risk in sorted(risk_map.items()):
        row[f"risk_{leg}"] = int(round(float(risk)))
    row["speed_score"] = _speed_score(row)
    row["ratio_score"] = _ratio_score(row)
    row["balanced_score"] = _balanced_score(row)
    return row


def _speed_score(row: dict[str, Any]) -> float:
    payout = float(row["payout_rate_pct"] or 0.0)
    breach = float(row["breach_rate_pct"] or 0.0)
    ev = float(row["ev_per_account_usd"] or 0.0)
    days = float(row["avg_days_to_payout"] or 999.0)
    max_run = float(row["max_consecutive_breaches"] or 0.0)
    active_risk = float(row["total_active_risk_usd"] or 0.0)
    return round(ev + payout * 3.0 - breach * 4.0 - days * 2.0 - max_run * 30.0 - active_risk * 0.02, 4)


def _ratio_score(row: dict[str, Any]) -> float:
    payout = float(row["payout_rate_pct"] or 0.0)
    breach = float(row["breach_rate_pct"] or 0.0)
    ev = float(row["ev_per_account_usd"] or 0.0)
    days = float(row["avg_days_to_payout"] or 999.0)
    ratio = float(row["payout_breach_ratio_smooth"] or 0.0)
    max_run = float(row["max_consecutive_breaches"] or 0.0)
    return round(ratio * 120.0 + payout * 1.2 + ev - breach * 3.0 - days * 0.8 - max_run * 25.0, 4)


def _balanced_score(row: dict[str, Any]) -> float:
    payout = float(row["payout_rate_pct"] or 0.0)
    breach = float(row["breach_rate_pct"] or 0.0)
    ev = float(row["ev_per_account_usd"] or 0.0)
    days = float(row["avg_days_to_payout"] or 999.0)
    ratio = float(row["payout_breach_ratio_smooth"] or 0.0)
    max_run = float(row["max_consecutive_breaches"] or 0.0)
    worst_month = float(row["worst_month_breaches"] or 0.0)
    return round(ev + payout * 2.0 + ratio * 45.0 - breach * 3.5 - days * 1.25 - max_run * 35.0 - worst_month * 15.0, 4)


def _leg_stats(base_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in base_rows:
        grouped[str(row["leg"])].append(float(row["r_multiple"]))
    stats = []
    for leg, values in sorted(grouped.items()):
        wins = [value for value in values if value > 0]
        losses = [value for value in values if value < 0]
        gross_win = sum(wins)
        gross_loss = abs(sum(losses))
        stats.append(
            {
                "leg": leg,
                "trades": len(values),
                "net_r": _round(sum(values), 2),
                "wr_pct": _round(len(wins) / len(values) * 100.0, 2) if values else 0.0,
                "pf": _round(gross_win / gross_loss, 3) if gross_loss else None,
                "avg_r": _round(float(np.mean(values)), 4) if values else 0.0,
                "median_r": _round(float(median(values)), 4) if values else 0.0,
            }
        )
    return stats


def _quality_weights(stats: list[dict[str, Any]]) -> dict[str, float]:
    weights = {}
    positive = [max(0.0, float(row["net_r"] or 0.0)) for row in stats]
    avg_positive = float(np.mean([value for value in positive if value > 0])) if any(value > 0 for value in positive) else 1.0
    for row in stats:
        net = max(0.0, float(row["net_r"] or 0.0))
        pf = float(row["pf"] or 1.0)
        avg_r = max(0.0, float(row["avg_r"] or 0.0))
        weight = 0.35 + 0.45 * min(1.8, net / avg_positive) + 0.25 * min(1.8, max(0.0, pf - 1.0)) + 0.4 * min(1.5, avg_r * 5.0)
        if net <= 0:
            weight = 0.0
        weights[str(row["leg"])] = round(min(2.0, weight), 3)
    return weights


def _scale_weights(weights: dict[str, float], scale: float, legs: list[str]) -> dict[str, float]:
    out = {}
    for leg in legs:
        raw = float(weights.get(leg, 0.0)) * scale
        if raw <= 0:
            out[leg] = 0.0
            continue
        nearest = min(POSITIVE_RISK_VALUES, key=lambda value: abs(value - raw))
        out[leg] = float(nearest)
    return out


def _candidate_maps(legs: list[str], stats: list[dict[str, Any]]) -> list[tuple[dict[str, float], str]]:
    candidates: list[tuple[dict[str, float], str]] = []
    legs = sorted(legs)

    def add(risk_map: dict[str, float], source: str) -> None:
        complete = {leg: float(risk_map.get(leg, 0.0) or 0.0) for leg in legs}
        if sum(complete.values()) > 0:
            candidates.append((complete, source))

    for risk in POSITIVE_RISK_VALUES:
        add({leg: float(risk) for leg in legs}, f"uniform_{risk}")

    for subset_size in range(1, len(legs) + 1):
        for subset in itertools.combinations(legs, subset_size):
            for risk in (75, 100, 125, 150, 200, 250, 300, 350, 400, 500):
                add({leg: float(risk) for leg in subset}, f"subset_uniform_{subset_size}_{risk}")

    nq_legs = [leg for leg in legs if leg.startswith("NQ")]
    es_legs = [leg for leg in legs if leg.startswith("ES")]
    for nq_risk in POSITIVE_RISK_VALUES:
        for es_risk in POSITIVE_RISK_VALUES:
            risk_map = {leg: float(nq_risk) for leg in nq_legs}
            risk_map.update({leg: float(es_risk) for leg in es_legs})
            add(risk_map, "symbol_split")

    orb_legs = [leg for leg in legs if not leg.endswith("_LSI")]
    lsi_legs = [leg for leg in legs if leg.endswith("_LSI")]
    for orb_risk in POSITIVE_RISK_VALUES:
        for lsi_risk in POSITIVE_RISK_VALUES:
            risk_map = {leg: float(orb_risk) for leg in orb_legs}
            risk_map.update({leg: float(lsi_risk) for leg in lsi_legs})
            add(risk_map, "strategy_split")

    weights = _quality_weights(stats)
    for scale in (50, 75, 100, 125, 150, 175, 200, 250, 300, 350, 400, 500):
        add(_scale_weights(weights, float(scale), legs), "quality_weighted")

    # A few explicit maps that match the qualitative reads from the live replay.
    add({"NQ_Asia": 250, "NQ_NY_LSI": 250, "ES_Asia": 200, "ES_NY": 150, "NQ_NY": 75, "ES_NY_LSI": 0}, "hand_quality_a")
    add({"NQ_Asia": 300, "NQ_NY_LSI": 250, "ES_Asia": 250, "ES_NY": 150, "NQ_NY": 0, "ES_NY_LSI": 0}, "hand_quality_b")
    add({"NQ_Asia": 350, "NQ_NY_LSI": 300, "ES_Asia": 200, "ES_NY": 100, "NQ_NY": 0, "ES_NY_LSI": 0}, "hand_fast_core")

    unique: dict[tuple[tuple[str, int], ...], tuple[dict[str, float], str]] = {}
    for risk_map, source in candidates:
        unique.setdefault(_risk_key(risk_map), (risk_map, source))
    return list(unique.values())


def _optimize_objective(
    portfolio: str,
    base_rows: list[dict[str, Any]],
    legs: list[str],
    seeds: list[dict[str, float]],
    objective: str,
    cache: dict[tuple[tuple[str, int], ...], dict[str, Any]],
) -> dict[str, Any]:
    score_col = {
        "speed": "speed_score",
        "ratio": "ratio_score",
        "balanced": "balanced_score",
    }[objective]

    def evaluate(risk_map: dict[str, float], source: str) -> dict[str, Any]:
        complete = {leg: float(risk_map.get(leg, 0.0) or 0.0) for leg in legs}
        key = _risk_key(complete)
        if key not in cache:
            cache[key] = _funded_row(portfolio, base_rows, complete, source)
        return cache[key]

    best: dict[str, Any] | None = None
    for seed in seeds:
        current = {leg: float(seed.get(leg, 0.0) or 0.0) for leg in legs}
        best_local = evaluate(current, f"coordinate_{objective}_seed")
        improved = True
        passes = 0
        while improved and passes < 4:
            passes += 1
            improved = False
            for leg in legs:
                leg_best_map = copy.deepcopy(current)
                leg_best_row = best_local
                for risk in RISK_VALUES:
                    trial = copy.deepcopy(current)
                    trial[leg] = float(risk)
                    if sum(trial.values()) <= 0:
                        continue
                    row = evaluate(trial, f"coordinate_{objective}")
                    if float(row[score_col]) > float(leg_best_row[score_col]):
                        leg_best_row = row
                        leg_best_map = trial
                if _risk_key(leg_best_map) != _risk_key(current):
                    current = leg_best_map
                    best_local = leg_best_row
                    improved = True
        if best is None or float(best_local[score_col]) > float(best[score_col]):
            best = best_local
    assert best is not None
    return best


def _run_risk_search(portfolio: str, base_rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, Any], dict[str, list[dict[str, Any]]]]:
    legs = sorted({str(row["leg"]) for row in base_rows})
    stats = _leg_stats(base_rows)
    candidates = _candidate_maps(legs, stats)
    cache: dict[tuple[tuple[str, int], ...], dict[str, Any]] = {}
    for idx, (risk_map, source) in enumerate(candidates, 1):
        cache[_risk_key(risk_map)] = _funded_row(portfolio, base_rows, risk_map, source)
        if idx % 1000 == 0:
            print(f"  risk maps evaluated for {portfolio}: {idx:,}", flush=True)

    seed_maps = [risk_map for risk_map, _source in candidates]
    top_seed_rows = sorted(cache.values(), key=lambda row: float(row["balanced_score"]), reverse=True)[:60]
    for row in top_seed_rows:
        seed_maps.append(json.loads(row["risk_map_json"]))

    best_speed = _optimize_objective(portfolio, base_rows, legs, seed_maps[:140], "speed", cache)
    best_ratio = _optimize_objective(portfolio, base_rows, legs, seed_maps[:140], "ratio", cache)
    best_balanced = _optimize_objective(portfolio, base_rows, legs, seed_maps[:140], "balanced", cache)

    df = pd.DataFrame(list(cache.values()))
    positive = df[df["payouts"] > 0].copy()
    if positive.empty:
        speed_guard = pd.DataFrame()
        ratio_guard = pd.DataFrame()
    else:
        speed_guard = positive[
            (positive["payout_rate_pct"] >= 45.0)
            & (positive["breach_rate_pct"] <= 45.0)
            & (positive["ev_per_account_usd"] > 0.0)
        ].copy()
        ratio_guard = positive[
            (positive["payout_rate_pct"] >= 35.0)
            & (positive["ev_per_account_usd"] > 0.0)
        ].copy()

    best_fastest_guarded = (
        speed_guard.sort_values(
            ["avg_days_to_payout", "payout_rate_pct", "breach_rate_pct", "ev_per_account_usd"],
            ascending=[True, False, True, False],
        ).iloc[0].to_dict()
        if not speed_guard.empty
        else best_speed
    )
    best_ratio_guarded = (
        ratio_guard.sort_values(
            ["payout_breach_ratio_smooth", "payout_rate_pct", "avg_days_to_payout", "ev_per_account_usd"],
            ascending=[False, False, True, False],
        ).iloc[0].to_dict()
        if not ratio_guard.empty
        else best_ratio
    )

    bests = {
        "best_speed_score": best_speed,
        "best_ratio_score": best_ratio,
        "best_balanced_score": best_balanced,
        "fastest_guarded": best_fastest_guarded,
        "best_ratio_guarded": best_ratio_guarded,
        "leg_stats": stats,
    }
    outcome_exports = {
        "best_speed_score": _simulate_funded(base_rows, json.loads(best_speed["risk_map_json"]), start=START_DATE, end=END_DATE),
        "best_ratio_score": _simulate_funded(base_rows, json.loads(best_ratio["risk_map_json"]), start=START_DATE, end=END_DATE),
        "best_balanced_score": _simulate_funded(base_rows, json.loads(best_balanced["risk_map_json"]), start=START_DATE, end=END_DATE),
        "fastest_guarded": _simulate_funded(base_rows, json.loads(best_fastest_guarded["risk_map_json"]), start=START_DATE, end=END_DATE),
        "best_ratio_guarded": _simulate_funded(base_rows, json.loads(best_ratio_guarded["risk_map_json"]), start=START_DATE, end=END_DATE),
    }
    return df, bests, outcome_exports


def _load_or_run_exact(spec: dict[str, Any], base_profile: Any, config: dict[str, Any], idx: int) -> dict[str, Any]:
    cache_path = RESULT_DIR / f"exact_{spec['name']}.json"
    if cache_path.exists():
        print(f"[exact cache] {spec['name']}", flush=True)
        return json.loads(cache_path.read_text())

    started = time.time()
    profile = port._build_profile(
        name=f"PHASE1_NQES_{idx:02d}_{spec['name']}"[:120],
        base_profile=base_profile,
        legs=spec["legs"],
        targets=spec.get("targets") or {},
    )
    print(f"[exact {idx}] {spec['name']} legs={len(spec['legs'])}", flush=True)
    result = port._run_profile(config, profile, f"HOT NQ+ES phase-one exact {spec['name']}")
    trades = result.get("trades", [])
    payload = {
        "name": spec["name"],
        "profile_name": profile.name,
        "legs": spec["legs"],
        "targets": spec.get("targets") or {},
        "metrics": port._metrics(trades),
        "by_leg": port._by_leg_metrics(trades),
        "trades": trades,
        "elapsed_sec": round(time.time() - started, 1),
    }
    cache_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n")
    m = payload["metrics"]
    print(
        f"  -> exact trades={m['trades']} net={m['net_r']:+.2f}R pf={m['pf']:.3f} dd={m['dd_r']:.2f}R elapsed={payload['elapsed_sec']:.1f}s",
        flush=True,
    )
    return payload


def _top_rows(df: pd.DataFrame, sort_cols: list[str], ascending: list[bool], n: int = 12) -> list[dict[str, Any]]:
    return df.sort_values(sort_cols, ascending=ascending).head(n).to_dict(orient="records")


def _mini(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "portfolio": row.get("portfolio"),
        "risk_map_json": row.get("risk_map_json"),
        "accounts": row.get("accounts"),
        "payouts": row.get("payouts"),
        "breaches": row.get("breaches"),
        "open": row.get("open"),
        "payout_rate_pct": row.get("payout_rate_pct"),
        "breach_rate_pct": row.get("breach_rate_pct"),
        "payout_breach_ratio": row.get("payout_breach_ratio"),
        "payout_breach_ratio_smooth": row.get("payout_breach_ratio_smooth"),
        "ev_per_account_usd": row.get("ev_per_account_usd"),
        "avg_days_to_payout": row.get("avg_days_to_payout"),
        "median_days_to_payout": row.get("median_days_to_payout"),
        "max_consecutive_breaches": row.get("max_consecutive_breaches"),
        "worst_month_breaches": row.get("worst_month_breaches"),
        "speed_score": row.get("speed_score"),
        "ratio_score": row.get("ratio_score"),
        "balanced_score": row.get("balanced_score"),
    }


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _write_report(payload: dict[str, Any]) -> None:
    best_speed = payload["global_bests"]["fastest_guarded"]
    best_ratio = payload["global_bests"]["best_ratio_guarded"]
    best_balanced = payload["global_bests"]["best_balanced_score"]
    lines = [
        "# HOT_REGIME_V1 NQ+ES Phase 1 Payout Risk Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Exact/live-engine window: `{START_DATE}` to `{END_DATE}`",
        "- Scope: NQ and ES combinations from the constrained HOT_REGIME_V1 portfolio search.",
        "- Account model: 50k account, 2k EOD trailing drawdown, first payout at 52.5k, $500 payout, $100 reset/account cost, account starts every 14 days.",
        "- Risk sizing only changes USD risk per leg. Strategy logic, exact replay, and live overlap hooks remain unchanged.",
        "",
        "## Headline",
        "",
        f"- Fastest guarded: `{best_speed['portfolio']}` with `{best_speed['risk_map_json']}`.",
        f"  Result: {best_speed['payouts']}/{best_speed['accounts']} payouts, {best_speed['breaches']} breaches, avg {best_speed['avg_days_to_payout']} days, EV ${best_speed['ev_per_account_usd']} per attempt.",
        f"- Best payout/breach guarded: `{best_ratio['portfolio']}` with `{best_ratio['risk_map_json']}`.",
        f"  Result: {best_ratio['payouts']}/{best_ratio['accounts']} payouts, {best_ratio['breaches']} breaches, ratio {_fmt(best_ratio['payout_breach_ratio'])}, EV ${best_ratio['ev_per_account_usd']} per attempt.",
        f"- Best balanced score: `{best_balanced['portfolio']}` with `{best_balanced['risk_map_json']}`.",
        "",
        "## Global Bests",
        "",
        _markdown_table(
            [
                {"bucket": "fastest_guarded", **_mini(best_speed)},
                {"bucket": "best_ratio_guarded", **_mini(best_ratio)},
                {"bucket": "best_balanced_score", **_mini(best_balanced)},
                {"bucket": "best_speed_score", **_mini(payload["global_bests"]["best_speed_score"])},
                {"bucket": "best_ratio_score", **_mini(payload["global_bests"]["best_ratio_score"])},
            ],
            [
                "bucket",
                "portfolio",
                "payouts",
                "breaches",
                "open",
                "payout_rate_pct",
                "breach_rate_pct",
                "payout_breach_ratio",
                "ev_per_account_usd",
                "avg_days_to_payout",
                "max_consecutive_breaches",
                "risk_map_json",
            ],
        ),
        "",
        "## Per Portfolio Bests",
        "",
        _markdown_table(
            payload["portfolio_best_rows"],
            [
                "portfolio",
                "bucket",
                "payouts",
                "breaches",
                "open",
                "payout_rate_pct",
                "breach_rate_pct",
                "payout_breach_ratio",
                "ev_per_account_usd",
                "avg_days_to_payout",
                "max_consecutive_breaches",
                "risk_map_json",
            ],
        ),
        "",
        "## Notes",
        "",
        "- This is intentionally recent-window Phase 1 sizing, not a 10-year robustness verdict.",
        "- Infinite payout/breach ratio means the tested account starts had payouts and zero breaches in this exact window.",
        "- The best ratio rows can be slower/lower-capacity than the fastest rows; the balanced row is the practical compromise bucket.",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = port.load_config(port.DEFAULT_CONFIG)
    base_profile = {profile.name: profile for profile in port.tm.load_exec_configs(config)}[port.BASE_PROFILE_NAME]
    specs_by_name = {spec["name"]: spec for spec in port._specs()}
    selected_specs = [specs_by_name[name] for name in SELECTED_PORTFOLIOS]

    exact_payloads = []
    all_risk_rows: list[pd.DataFrame] = []
    portfolio_bests: dict[str, Any] = {}
    portfolio_best_rows: list[dict[str, Any]] = []
    outcome_exports: dict[str, Any] = {}

    print(f"Running Phase 1 risk sizing for {len(selected_specs)} portfolios", flush=True)
    for idx, spec in enumerate(selected_specs, 1):
        exact = _load_or_run_exact(spec, base_profile, config, idx)
        exact_payloads.append({key: value for key, value in exact.items() if key != "trades"})
        base_rows = _trade_rows(exact["trades"])
        print(f"[risk {idx}/{len(selected_specs)}] {spec['name']} base trades={len(base_rows)}", flush=True)
        risk_df, bests, outcomes = _run_risk_search(spec["name"], base_rows)
        risk_df.to_csv(RESULT_DIR / f"risk_sweep_{spec['name']}.csv", index=False)
        (RESULT_DIR / f"outcomes_{spec['name']}.json").write_text(
            json.dumps(outcomes, indent=2, sort_keys=True, default=_json_default) + "\n"
        )
        all_risk_rows.append(risk_df)
        portfolio_bests[spec["name"]] = {key: _mini(value) if isinstance(value, dict) and "risk_map_json" in value else value for key, value in bests.items()}
        outcome_exports[spec["name"]] = outcomes
        for bucket in ("fastest_guarded", "best_ratio_guarded", "best_balanced_score"):
            portfolio_best_rows.append({"bucket": bucket, **_mini(bests[bucket])})
        print(
            "  -> fastest {fast_payouts}/{accounts} payouts, {fast_breaches} breaches, {fast_days} avg days; "
            "ratio-best {ratio_payouts}/{accounts} payouts, {ratio_breaches} breaches".format(
                fast_payouts=bests["fastest_guarded"]["payouts"],
                accounts=bests["fastest_guarded"]["accounts"],
                fast_breaches=bests["fastest_guarded"]["breaches"],
                fast_days=bests["fastest_guarded"]["avg_days_to_payout"],
                ratio_payouts=bests["best_ratio_guarded"]["payouts"],
                ratio_breaches=bests["best_ratio_guarded"]["breaches"],
            ),
            flush=True,
        )

    all_df = pd.concat(all_risk_rows, ignore_index=True)
    all_df.to_csv(RESULT_DIR / "risk_sweep_all.csv", index=False)

    global_bests = {
        "fastest_guarded": _top_rows(
            all_df[
                (all_df["payout_rate_pct"] >= 45.0)
                & (all_df["breach_rate_pct"] <= 45.0)
                & (all_df["ev_per_account_usd"] > 0.0)
            ],
            ["avg_days_to_payout", "payout_rate_pct", "breach_rate_pct", "ev_per_account_usd"],
            [True, False, True, False],
            1,
        )[0],
        "best_ratio_guarded": _top_rows(
            all_df[(all_df["payout_rate_pct"] >= 35.0) & (all_df["ev_per_account_usd"] > 0.0)],
            ["payout_breach_ratio_smooth", "payout_rate_pct", "avg_days_to_payout", "ev_per_account_usd"],
            [False, False, True, False],
            1,
        )[0],
        "best_balanced_score": _top_rows(all_df, ["balanced_score", "ev_per_account_usd"], [False, False], 1)[0],
        "best_speed_score": _top_rows(all_df, ["speed_score", "ev_per_account_usd"], [False, False], 1)[0],
        "best_ratio_score": _top_rows(all_df, ["ratio_score", "ev_per_account_usd"], [False, False], 1)[0],
    }

    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "window": {"start": START_DATE, "end": END_DATE},
        "funded_model": FUNDED_MODEL,
        "selected_portfolios": list(SELECTED_PORTFOLIOS),
        "risk_values": list(RISK_VALUES),
        "exact_payloads": exact_payloads,
        "portfolio_bests": portfolio_bests,
        "portfolio_best_rows": portfolio_best_rows,
        "global_bests": {key: _mini(value) for key, value in global_bests.items()},
        "top_speed": _top_rows(all_df, ["speed_score", "ev_per_account_usd"], [False, False], 20),
        "top_ratio": _top_rows(all_df, ["ratio_score", "ev_per_account_usd"], [False, False], 20),
        "top_balanced": _top_rows(all_df, ["balanced_score", "ev_per_account_usd"], [False, False], 20),
        "paths": {
            "summary_json": str(RESULT_DIR / "summary.json"),
            "risk_sweep_all_csv": str(RESULT_DIR / "risk_sweep_all.csv"),
            "report": str(REPORT_PATH),
        },
        "elapsed_sec": round(time.time() - started, 1),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n")
    _write_report(payload)
    print("SUMMARY_JSON", RESULT_DIR / "summary.json", flush=True)
    print("REPORT", REPORT_PATH, flush=True)
    print("GLOBAL_BESTS")
    for key, row in payload["global_bests"].items():
        print(json.dumps({"bucket": key, **row}, sort_keys=True, default=_json_default), flush=True)
    print(f"Elapsed {payload['elapsed_sec']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
