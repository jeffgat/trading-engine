#!/usr/bin/env python3
"""Evaluate swapped ALPHA_V1 payout policies across time-based and R-based staggers.

This script keeps the same swapped-portfolio setup used in the prior
`ALPHA_V1` replacement studies:

- Replace only the legacy `NQ_NY_LSI` leg with `HTF_LSI_5M_LAG24`
- Keep `NQ_Asia`, `ES_Asia`, and `ES_NY` as the other three portfolio legs
- Use the exact execution replay path to build the combined trade stream

Workflow:
1. Run exact single-leg replays for a small risk grid per leg
2. Build an offline shortlist using blended daily PnL
3. Exact-verify the shortlisted full-portfolio combos
4. Compare stagger policies on the exact combined daily streams

Important assumption for R-triggered staggers:
- Account starts are triggered from the master combined portfolio daily PnL
  stream, not from each account's own path.
- `1R` is defined as `$500`, so `+5R / -4R` maps to the same
  `+$2500 / -$2000` payout model used in the prior work.
- When a day closes having crossed multiple R-trigger bands, multiple new
  accounts are allowed to start on the next trading day.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "execution" / "src"))

from trader import main as trader_main  # noqa: E402
from trader.historical_backtest import run_profile_backtest_sync  # noqa: E402


START = "2024-01-01"
END = "2025-12-31"
PROFILE = "ALPHA_V1"
PAYOUT_USD = 2500.0
BREACH_USD = -2000.0
ACCOUNT_R_USD = 500.0

TIME_STAGGERS = (7, 10, 14, 21)
R_TRIGGER_BANDS = (2.0, 3.0, 4.0, 5.0)

HTF_RISKS = (250, 300, 350, 400)
NQ_ASIA_RISKS = (250, 300, 350, 400)
ES_ASIA_RISKS = (150, 200, 250, 300)
ES_NY_RISKS = (250, 300, 350, 400)


@dataclass(frozen=True)
class Policy:
    name: str
    kind: str
    value: float


POLICIES = [
    *(Policy(name=f"time_{days}d", kind="calendar", value=float(days)) for days in TIME_STAGGERS),
    *(Policy(name=f"r_trigger_{threshold:g}R", kind="r_trigger", value=float(threshold)) for threshold in R_TRIGGER_BANDS),
]


RAW_CONFIGS = json.loads((ROOT / "execution" / "config" / "exec_configs.json").read_text())
LEG_DEFS = {
    "HTF_LSI": {
        "kind": "lsi",
        "session_name": "NQ_NY_LSI",
        "template": RAW_CONFIGS["HTF_LSI_5M_LAG24"]["lsi_sessions"]["NQ_NY_LSI"],
        "risks": HTF_RISKS,
    },
    "NQ_Asia": {
        "kind": "session",
        "session_name": "NQ_Asia",
        "template": RAW_CONFIGS["ALPHA_V1"]["sessions"]["NQ_Asia"],
        "risks": NQ_ASIA_RISKS,
    },
    "ES_Asia": {
        "kind": "session",
        "session_name": "ES_Asia",
        "template": RAW_CONFIGS["ALPHA_V1"]["sessions"]["ES_Asia"],
        "risks": ES_ASIA_RISKS,
    },
    "ES_NY": {
        "kind": "session",
        "session_name": "ES_NY",
        "template": RAW_CONFIGS["ALPHA_V1"]["sessions"]["ES_NY"],
        "risks": ES_NY_RISKS,
    },
}
LEG_KEYS = ("HTF_LSI", "NQ_Asia", "ES_Asia", "ES_NY")
BASELINE_COMBO = {"HTF_LSI": 300, "NQ_Asia": 300, "ES_Asia": 200, "ES_NY": 300}


def next_trading_index(dates: list[str], start_str: str) -> int | None:
    for idx, date_str in enumerate(dates):
        if date_str >= start_str:
            return idx
    return None


def summarize_accounts(results: list[dict[str, Any]]) -> dict[str, Any]:
    payouts = [row for row in results if row["status"] == "PAYOUT"]
    breaches = [row for row in results if row["status"] == "BREACH"]
    resolved = payouts + breaches
    payout_days = sorted(row["cal_days"] for row in payouts)
    return {
        "starts": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": sum(1 for row in results if row["status"] == "OPEN"),
        "payout_rate": (len(payouts) / len(resolved) * 100.0) if resolved else 0.0,
        "breach_rate": (len(breaches) / len(resolved) * 100.0) if resolved else 0.0,
        "avg_payout_days": (sum(payout_days) / len(payout_days)) if payout_days else None,
        "fastest_payout_days": min(payout_days) if payout_days else None,
        "slowest_payout_days": max(payout_days) if payout_days else None,
    }


def simulate_accounts_from_start_dates(
    dated_daily_usd: list[tuple[str, float]],
    start_dates: list[str],
    payout_usd: float,
    breach_usd: float,
) -> list[dict[str, Any]]:
    if not dated_daily_usd or not start_dates:
        return []

    dates = [date_str for date_str, _ in dated_daily_usd]
    daily_pnl = [pnl for _, pnl in dated_daily_usd]
    results: list[dict[str, Any]] = []
    for start_str in start_dates:
        first_idx = next_trading_index(dates, start_str)
        if first_idx is None:
            continue

        start_dt = datetime.strptime(start_str, "%Y-%m-%d")
        equity = 0.0
        status = "OPEN"
        stop_idx = first_idx
        for stop_idx in range(first_idx, len(dates)):
            equity += daily_pnl[stop_idx]
            if equity >= payout_usd:
                status = "PAYOUT"
                break
            if equity <= breach_usd:
                status = "BREACH"
                break

        end_dt = datetime.strptime(dates[min(stop_idx, len(dates) - 1)], "%Y-%m-%d")
        results.append(
            {
                "start": start_str,
                "cal_days": (end_dt - start_dt).days + 1,
                "status": status,
            }
        )
    return results


def build_calendar_start_dates(dated_daily_usd: list[tuple[str, float]], stagger_days: int) -> list[str]:
    if not dated_daily_usd:
        return []
    first_date = datetime.strptime(dated_daily_usd[0][0], "%Y-%m-%d")
    last_date = datetime.strptime(dated_daily_usd[-1][0], "%Y-%m-%d")
    starts: list[str] = []
    current = first_date
    while current <= last_date:
        starts.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=stagger_days)
    return starts


def build_r_trigger_start_dates(
    dated_daily_usd: list[tuple[str, float]],
    trigger_r: float,
    account_r_usd: float,
) -> list[str]:
    if not dated_daily_usd:
        return []

    threshold_usd = trigger_r * account_r_usd
    dates = [date_str for date_str, _ in dated_daily_usd]
    daily_pnl = [pnl for _, pnl in dated_daily_usd]
    starts = [dates[0]]

    cumulative = 0.0
    anchor = 0.0
    for idx, pnl in enumerate(daily_pnl):
        cumulative += pnl
        delta = cumulative - anchor
        if abs(delta) < threshold_usd:
            continue
        if idx + 1 >= len(dates):
            break

        step_count = int(abs(delta) // threshold_usd)
        next_start = dates[idx + 1]
        for _ in range(step_count):
            starts.append(next_start)
        anchor += (threshold_usd * step_count) if delta > 0 else (-threshold_usd * step_count)
    return starts


def evaluate_policy(
    dated_daily_usd: list[tuple[str, float]],
    policy: Policy,
) -> dict[str, Any]:
    if policy.kind == "calendar":
        starts = build_calendar_start_dates(dated_daily_usd, int(policy.value))
    elif policy.kind == "r_trigger":
        starts = build_r_trigger_start_dates(dated_daily_usd, policy.value, ACCOUNT_R_USD)
    else:
        raise ValueError(f"Unknown policy kind: {policy.kind}")

    stats = summarize_accounts(
        simulate_accounts_from_start_dates(dated_daily_usd, starts, PAYOUT_USD, BREACH_USD)
    )
    stats["policy"] = policy.name
    if policy.kind == "calendar":
        stats["stagger_days"] = int(policy.value)
    else:
        stats["trigger_r"] = float(policy.value)
        stats["trigger_usd"] = float(policy.value * ACCOUNT_R_USD)
    return stats


def build_single_leg_profile(leg_key: str, risk: int) -> dict[str, Any]:
    leg = LEG_DEFS[leg_key]
    override = dict(leg["template"])
    override["risk_usd"] = risk
    if leg_key == "HTF_LSI":
        override["max_single_risk_usd"] = 500
    profile = {
        "enabled": True,
        "max_open_contracts": 20,
        "webhooks": [],
        "sessions": {},
        "lsi_sessions": {},
    }
    if leg["kind"] == "session":
        profile["sessions"][leg["session_name"]] = override
    else:
        profile["lsi_sessions"][leg["session_name"]] = override
    return {"TEMP": profile}


def run_exact_profile(profile_config: dict[str, Any], profile_name: str, label: str) -> dict[str, Any]:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    try:
        json.dump(profile_config, tmp)
        tmp.close()
        old_path = trader_main.EXEC_CONFIGS_PATH
        trader_main.EXEC_CONFIGS_PATH = Path(tmp.name)
        try:
            return run_profile_backtest_sync(
                config={},
                profile_name=profile_name,
                start_date=START,
                end_date=END,
                label=label,
            )
        finally:
            trader_main.EXEC_CONFIGS_PATH = old_path
    finally:
        try:
            os.unlink(tmp.name)
        except FileNotFoundError:
            pass


def backtest_to_daily_usd(backtest: dict[str, Any]) -> list[tuple[str, float]]:
    daily = defaultdict(float)
    for trade in backtest["trades"]:
        daily[trade["date"]] += float(trade["pnl_usd"])
    return sorted(daily.items())


def build_combo_profile(combo: dict[str, int]) -> dict[str, Any]:
    cfg = copy.deepcopy(RAW_CONFIGS)
    cfg[PROFILE]["max_open_contracts"] = 20
    cfg[PROFILE]["sessions"]["NQ_Asia"]["risk_usd"] = combo["NQ_Asia"]
    cfg[PROFILE]["sessions"]["ES_Asia"]["risk_usd"] = combo["ES_Asia"]
    cfg[PROFILE]["sessions"]["ES_NY"]["risk_usd"] = combo["ES_NY"]
    htf = dict(LEG_DEFS["HTF_LSI"]["template"])
    htf["risk_usd"] = combo["HTF_LSI"]
    htf["max_single_risk_usd"] = 500
    cfg[PROFILE]["lsi_sessions"]["NQ_NY_LSI"] = htf
    return cfg


def candidate_sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    avg_days = row["avg_payout_days"] if row["avg_payout_days"] is not None else 10**9
    return (avg_days, -row["payout_rate"], row["breach_rate"])


def main() -> None:
    single_leg_data: dict[str, dict[int, dict[str, Any]]] = {}
    print("Running exact single-leg grid...")
    for leg_key in LEG_KEYS:
        single_leg_data[leg_key] = {}
        for risk in LEG_DEFS[leg_key]["risks"]:
            backtest = run_exact_profile(
                build_single_leg_profile(leg_key, risk),
                profile_name="TEMP",
                label=f"{leg_key} risk {risk}",
            )
            daily_usd = backtest_to_daily_usd(backtest)
            single_leg_data[leg_key][risk] = {
                "trade_count": len(backtest["trades"]),
                "daily_usd": dict(daily_usd),
            }
            print(f"  single {leg_key} risk={risk} trades={len(backtest['trades'])} days={len(daily_usd)}", flush=True)

    offline_rows: list[dict[str, Any]] = []
    print("Building offline combo shortlist across stagger policies...")
    for risks in product(*(LEG_DEFS[key]["risks"] for key in LEG_KEYS)):
        combo = dict(zip(LEG_KEYS, risks))
        daily = defaultdict(float)
        trade_count = 0
        for leg_key, risk in combo.items():
            row = single_leg_data[leg_key][risk]
            trade_count += row["trade_count"]
            for date_str, pnl in row["daily_usd"].items():
                daily[date_str] += pnl
        dated_daily_usd = sorted(daily.items())
        for policy in POLICIES:
            stats = evaluate_policy(dated_daily_usd, policy)
            stats["combo"] = combo
            stats["trade_count"] = trade_count
            offline_rows.append(stats)

    shortlist: dict[str, dict[str, Any]] = {}
    payout_thresholds = (85.0, 80.0, 75.0)
    for policy in POLICIES:
        policy_rows = [row for row in offline_rows if row["policy"] == policy.name]
        shortlist[f"{policy.name}__baseline"] = next(
            row for row in policy_rows if row["combo"] == BASELINE_COMBO
        )
        shortlist[f"{policy.name}__absolute_fastest"] = min(policy_rows, key=candidate_sort_key)
        for threshold in payout_thresholds:
            eligible = [row for row in policy_rows if row["payout_rate"] >= threshold]
            if eligible:
                shortlist[f"{policy.name}__best_ge_{int(threshold)}"] = min(eligible, key=candidate_sort_key)

    exact_combo_streams: dict[tuple[tuple[str, int], ...], dict[str, Any]] = {}
    print("Exact-verifying shortlisted combos...")
    for label, row in shortlist.items():
        combo = row["combo"]
        combo_key = tuple((leg_key, combo[leg_key]) for leg_key in LEG_KEYS)
        if combo_key in exact_combo_streams:
            continue
        backtest = run_exact_profile(
            build_combo_profile(combo),
            profile_name=PROFILE,
            label=f"ALPHA_V1 stagger frontier {label}",
        )
        exact_combo_streams[combo_key] = {
            "combo": combo,
            "trade_count": len(backtest["trades"]),
            "dated_daily_usd": backtest_to_daily_usd(backtest),
        }
        print(f"  verified combo={combo} trades={len(backtest['trades'])}", flush=True)

    exact_policy_rows: list[dict[str, Any]] = []
    for combo_stream in exact_combo_streams.values():
        for policy in POLICIES:
            stats = evaluate_policy(combo_stream["dated_daily_usd"], policy)
            stats["combo"] = combo_stream["combo"]
            stats["trade_count"] = combo_stream["trade_count"]
            exact_policy_rows.append(stats)

    policy_winners: dict[str, dict[str, Any]] = {}
    for policy in POLICIES:
        policy_rows = [row for row in exact_policy_rows if row["policy"] == policy.name]
        threshold_80 = [row for row in policy_rows if row["payout_rate"] >= 80.0]
        threshold_75 = [row for row in policy_rows if row["payout_rate"] >= 75.0]
        policy_winners[policy.name] = {
            "baseline": next(row for row in policy_rows if row["combo"] == BASELINE_COMBO),
            "best_ge_80": min(threshold_80, key=candidate_sort_key) if threshold_80 else None,
            "best_ge_75": min(threshold_75, key=candidate_sort_key) if threshold_75 else None,
            "absolute_fastest": min(policy_rows, key=candidate_sort_key),
        }

    out_path = ROOT / "backtesting" / "data" / "results" / "alpha_v1_htf_stagger_policy_frontier_2024_2025.json"
    out_path.write_text(
        json.dumps(
            {
                "start": START,
                "end": END,
                "payout_usd": PAYOUT_USD,
                "breach_usd": BREACH_USD,
                "account_r_usd_for_r_trigger": ACCOUNT_R_USD,
                "time_staggers": TIME_STAGGERS,
                "r_trigger_bands": R_TRIGGER_BANDS,
                "offline_shortlist_size": len(shortlist),
                "verified_combo_count": len(exact_combo_streams),
                "policy_winners": policy_winners,
                "verified_rows": exact_policy_rows,
            },
            indent=2,
        )
    )
    print(f"saved {out_path}")


if __name__ == "__main__":
    main()
