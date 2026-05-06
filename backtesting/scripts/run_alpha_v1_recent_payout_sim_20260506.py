#!/usr/bin/env python3
"""Recent annual phase-one payout simulation for ALPHA_V1 with NQ NY ORB R11.

Uses cached live/exact trade streams only:
- Four active ALPHA_V1-A legs from alpha_v1_live_replay_compare_20260503.
- NQ NY ORB R11 split ladder from alpha_v1_single_vs_split_exact_compare_20260506.

The script does not edit execution configs.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_recent_payout_sim_20260506"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_RECENT_PAYOUT_SIM_20260506.md"

ACTIVE_EXACT_TRADES = ROOT / "data" / "results" / "alpha_v1_live_replay_compare_20260503" / "exact_trades.csv"
R11_EXACT_TRADES = ROOT / "data" / "results" / "alpha_v1_single_vs_split_exact_compare_20260506" / "split_exact_trades.csv"

SESSION_TO_LEG = {
    "NQ_NY_LSI": "nq_ny_htf_lsi",
    "NQ_Asia": "nq_asia_orb",
    "ES_Asia": "es_asia_orb",
    "ES_NY": "es_ny_orb",
}

LEG_LABELS = {
    "nq_ny_htf_lsi": "NQ NY HTF-LSI",
    "nq_asia_orb": "NQ Asia ORB",
    "es_asia_orb": "ES Asia ORB",
    "nq_ny_orb_r11": "NQ NY ORB R11",
    "es_ny_orb": "ES NY ORB",
}

YEARS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026_YTD": ("2026-01-01", "2026-03-24"),
}

FUNDED_MODEL = {
    "starting_balance_usd": 50_000.0,
    "trailing_drawdown_usd": 2_000.0,
    "max_trailing_breach_usd": 50_000.0,
    "first_payout_floor_usd": 52_500.0,
    "first_payout_withdrawal_usd": 500.0,
    "challenge_fee_usd": 150.0,
    "cohort_spacing_days": 14,
}


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    risks: dict[str, float]
    notes: str


STATIC_PROFILES = [
    Profile(
        key="probation_lowest_breach",
        label="Probation / lowest breach",
        risks={
            "nq_ny_htf_lsi": 300.0,
            "nq_asia_orb": 250.0,
            "es_asia_orb": 200.0,
            "nq_ny_orb_r11": 150.0,
            "es_ny_orb": 150.0,
        },
        notes="Cleanest initial paper/live probation menu.",
    ),
    Profile(
        key="balanced_default",
        label="Balanced default",
        risks={
            "nq_ny_htf_lsi": 300.0,
            "nq_asia_orb": 300.0,
            "es_asia_orb": 200.0,
            "nq_ny_orb_r11": 250.0,
            "es_ny_orb": 200.0,
        },
        notes="ALPHA_V1.md 2026-05-06 preferred first pass.",
    ),
    Profile(
        key="nq_led_sprint",
        label="NQ-led sprint",
        risks={
            "nq_ny_htf_lsi": 400.0,
            "nq_asia_orb": 300.0,
            "es_asia_orb": 200.0,
            "nq_ny_orb_r11": 350.0,
            "es_ny_orb": 150.0,
        },
        notes="Faster branch with lower ES_NY and more NQ exposure.",
    ),
]

RISK_GRID = {
    "nq_ny_htf_lsi": (300.0, 400.0, 500.0),
    "nq_asia_orb": (250.0, 300.0, 350.0, 400.0),
    "es_asia_orb": (150.0, 200.0, 250.0, 300.0),
    "nq_ny_orb_r11": (150.0, 200.0, 250.0, 300.0, 350.0, 400.0),
    "es_ny_orb": (100.0, 150.0, 200.0, 250.0, 300.0),
}


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _fmt(value: Any) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "-"
    if isinstance(value, (int, np.integer)):
        return str(int(value))
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _load_trade_stream() -> pd.DataFrame:
    active = pd.read_csv(ACTIVE_EXACT_TRADES)
    active = active.copy()
    active["leg"] = active["session"].map(SESSION_TO_LEG)
    active = active[active["leg"].notna()].copy()
    active["source"] = "alpha_v1_live_exact_4leg"

    r11 = pd.read_csv(R11_EXACT_TRADES)
    r11 = r11[r11["comparison_leg"] == "nq_ny_orb_r11"].copy()
    r11["leg"] = "nq_ny_orb_r11"
    r11["source"] = "nq_r11_exact_split"

    keep_cols = ["leg", "date", "entry_time", "exit_time", "r_multiple", "source"]
    stream = pd.concat([active[keep_cols], r11[keep_cols]], ignore_index=True)
    stream["date"] = stream["date"].astype(str)
    stream["exit_ts"] = pd.to_datetime(stream["exit_time"], utc=True, errors="coerce")
    stream["entry_ts"] = pd.to_datetime(stream["entry_time"], utc=True, errors="coerce")
    stream = stream[stream["exit_ts"].notna()].copy()
    stream["r_multiple"] = stream["r_multiple"].astype(float)
    return stream.sort_values(["exit_ts", "leg", "entry_ts"]).reset_index(drop=True)


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize().tz_localize("UTC")
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def _simulate_accounts(trades: pd.DataFrame, *, start: str, end: str, profile: Profile) -> pd.DataFrame:
    mask = (trades["date"] >= start) & (trades["date"] <= end)
    subset = trades.loc[mask].copy()
    subset["risk_usd"] = subset["leg"].map(profile.risks).astype(float)
    subset["pnl_usd"] = subset["r_multiple"] * subset["risk_usd"]
    subset = subset.sort_values(["exit_ts", "leg", "entry_ts"]).reset_index(drop=True)
    trade_tuples = [
        (
            row.exit_ts,
            pd.Timestamp(row.exit_ts).date().isoformat(),
            str(row.leg),
            float(row.pnl_usd),
        )
        for row in subset[["exit_ts", "leg", "pnl_usd"]].itertuples(index=False)
    ]

    rows: list[dict[str, Any]] = []
    for account_id, start_ts in enumerate(_cohort_starts(start, end), start=1):
        balance = float(FUNDED_MODEL["starting_balance_usd"])
        floor = balance - float(FUNDED_MODEL["trailing_drawdown_usd"])
        high_eod = balance
        current_day: str | None = None
        outcome = "open"
        outcome_date = pd.Timestamp(end).date().isoformat()
        trades_taken = 0
        leg_counts: dict[str, int] = defaultdict(int)

        for exit_ts, trade_day, leg, pnl_usd in trade_tuples:
            if exit_ts < start_ts:
                continue
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
            balance += pnl_usd
            trades_taken += 1
            leg_counts[leg] += 1
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_MODEL["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        if outcome == "payout":
            net_after_fee = float(FUNDED_MODEL["first_payout_withdrawal_usd"]) - float(FUNDED_MODEL["challenge_fee_usd"])
        else:
            net_after_fee = -float(FUNDED_MODEL["challenge_fee_usd"])

        rows.append(
            {
                "profile": profile.key,
                "profile_label": profile.label,
                "account_id": account_id,
                "account_start": start_ts.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date).date() - start_ts.date()).days) + 1,
                "trades_to_outcome": trades_taken,
                "ending_balance_usd": _round(balance, 2),
                "breach_floor_usd": _round(floor, 2),
                "net_after_fee_usd": _round(net_after_fee, 2),
                **{f"{leg}_trades": int(leg_counts[leg]) for leg in LEG_LABELS},
            }
        )
    return pd.DataFrame(rows)


def _max_consecutive(outcomes: pd.DataFrame, outcome_name: str) -> int:
    max_run = 0
    run = 0
    for _, row in outcomes.sort_values("account_start").iterrows():
        if row["outcome"] == outcome_name:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def _score_outcomes(outcomes: pd.DataFrame, *, profile: Profile, year: str) -> dict[str, Any]:
    if outcomes.empty:
        return {
            "profile": profile.key,
            "profile_label": profile.label,
            "year": year,
            "accounts": 0,
            "payouts": 0,
            "breaches": 0,
            "open": 0,
            "resolved_payout_rate_pct": None,
            "resolved_breach_rate_pct": None,
            "start_payout_rate_pct": None,
            "start_breach_rate_pct": None,
            "open_rate_pct": None,
            "avg_days_to_payout": None,
            "median_days_to_payout": None,
            "max_consecutive_breaches": 0,
            "ev_per_start_usd": None,
        }

    total = len(outcomes)
    payouts = outcomes[outcomes["outcome"] == "payout"]
    breaches = outcomes[outcomes["outcome"] == "breach"]
    opens = outcomes[outcomes["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    return {
        "profile": profile.key,
        "profile_label": profile.label,
        "year": year,
        "accounts": int(total),
        "payouts": int(len(payouts)),
        "breaches": int(len(breaches)),
        "open": int(len(opens)),
        "resolved_payout_rate_pct": _round(len(payouts) / resolved * 100.0, 2) if resolved else None,
        "resolved_breach_rate_pct": _round(len(breaches) / resolved * 100.0, 2) if resolved else None,
        "start_payout_rate_pct": _round(len(payouts) / total * 100.0, 2),
        "start_breach_rate_pct": _round(len(breaches) / total * 100.0, 2),
        "open_rate_pct": _round(len(opens) / total * 100.0, 2),
        "avg_days_to_payout": _round(float(payouts["days_to_outcome"].mean()), 1) if not payouts.empty else None,
        "median_days_to_payout": _round(float(payouts["days_to_outcome"].median()), 1) if not payouts.empty else None,
        "avg_trades_to_payout": _round(float(payouts["trades_to_outcome"].mean()), 1) if not payouts.empty else None,
        "max_consecutive_breaches": _max_consecutive(outcomes, "breach"),
        "ev_per_start_usd": _round(float(outcomes["net_after_fee_usd"].mean()), 2),
    }


def _summarize_profile(trades: pd.DataFrame, profile: Profile) -> tuple[pd.DataFrame, pd.DataFrame]:
    outcomes = []
    summary = []
    for year, (start, end) in YEARS.items():
        year_outcomes = _simulate_accounts(trades, start=start, end=end, profile=profile)
        year_outcomes["year"] = year
        outcomes.append(year_outcomes)
        summary.append(_score_outcomes(year_outcomes, profile=profile, year=year))
    return pd.concat(outcomes, ignore_index=True), pd.DataFrame(summary)


def _combo_profiles() -> list[Profile]:
    profiles: list[Profile] = []
    for htf in RISK_GRID["nq_ny_htf_lsi"]:
        for nq_asia in RISK_GRID["nq_asia_orb"]:
            for es_asia in RISK_GRID["es_asia_orb"]:
                for nq_r11 in RISK_GRID["nq_ny_orb_r11"]:
                    for es_ny in RISK_GRID["es_ny_orb"]:
                        risks = {
                            "nq_ny_htf_lsi": htf,
                            "nq_asia_orb": nq_asia,
                            "es_asia_orb": es_asia,
                            "nq_ny_orb_r11": nq_r11,
                            "es_ny_orb": es_ny,
                        }
                        key = f"htf{int(htf)}_nqa{int(nq_asia)}_esa{int(es_asia)}_r11{int(nq_r11)}_esny{int(es_ny)}"
                        label = f"HTF {int(htf)} / NQ Asia {int(nq_asia)} / ES Asia {int(es_asia)} / R11 {int(nq_r11)} / ES NY {int(es_ny)}"
                        profiles.append(Profile(key=key, label=label, risks=risks, notes="grid"))
    return profiles


def _sweep_risk_grid(trades: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile in _combo_profiles():
        yearly = []
        for year, (start, end) in YEARS.items():
            outcomes = _simulate_accounts(trades, start=start, end=end, profile=profile)
            yearly.append(_score_outcomes(outcomes, profile=profile, year=year))
        by_year = {row["year"]: row for row in yearly}
        full_years = [by_year["2024"], by_year["2025"]]
        recent_years = [by_year["2024"], by_year["2025"], by_year["2026_YTD"]]
        avg_days_full = float(np.mean([r["avg_days_to_payout"] or 999.0 for r in full_years]))
        max_days_full = max(float(r["avg_days_to_payout"] or 999.0) for r in full_years)
        avg_resolved_breach_full = float(np.mean([r["resolved_breach_rate_pct"] or 0.0 for r in full_years]))
        max_resolved_breach_full = max(float(r["resolved_breach_rate_pct"] or 0.0) for r in full_years)
        avg_resolved_pay_full = float(np.mean([r["resolved_payout_rate_pct"] or 0.0 for r in full_years]))
        avg_open_full = float(np.mean([r["open_rate_pct"] or 0.0 for r in full_years]))
        avg_ev_full = float(np.mean([r["ev_per_start_usd"] or -999.0 for r in full_years]))
        max_consec_breach = max(int(r["max_consecutive_breaches"] or 0) for r in recent_years)
        fast_enough = max_days_full <= 90.0
        score = (
            avg_resolved_pay_full * 3.0
            - avg_resolved_breach_full * 4.5
            - avg_days_full * 0.8
            - max_consec_breach * 12.0
            + avg_ev_full * 0.08
            - avg_open_full * 0.5
        )
        if fast_enough:
            score += 50.0
        rows.append(
            {
                "profile": profile.key,
                "profile_label": profile.label,
                **{f"{leg}_risk": int(risk) for leg, risk in profile.risks.items()},
                "total_risk": int(sum(profile.risks.values())),
                "avg_days_2024_2025": _round(avg_days_full, 1),
                "max_days_2024_2025": _round(max_days_full, 1),
                "avg_resolved_payout_2024_2025": _round(avg_resolved_pay_full, 2),
                "avg_resolved_breach_2024_2025": _round(avg_resolved_breach_full, 2),
                "max_resolved_breach_2024_2025": _round(max_resolved_breach_full, 2),
                "avg_open_2024_2025": _round(avg_open_full, 2),
                "avg_ev_2024_2025": _round(avg_ev_full, 2),
                "max_consecutive_breaches_2024_2026": max_consec_breach,
                "fast_enough_90d": bool(fast_enough),
                "rank_score": _round(score, 4),
                **{
                    f"{row['year']}_{field}": row[field]
                    for row in yearly
                    for field in (
                        "resolved_payout_rate_pct",
                        "resolved_breach_rate_pct",
                        "start_payout_rate_pct",
                        "start_breach_rate_pct",
                        "open_rate_pct",
                        "avg_days_to_payout",
                        "payouts",
                        "breaches",
                        "open",
                    )
                },
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["fast_enough_90d", "rank_score", "avg_resolved_breach_2024_2025", "avg_days_2024_2025"],
        ascending=[False, False, True, True],
    )


def _trade_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for leg, label in LEG_LABELS.items():
        sub = trades[trades["leg"] == leg]
        rows.append(
            {
                "leg": leg,
                "label": label,
                "source": ",".join(sorted(sub["source"].dropna().unique())),
                "trades": int(len(sub)),
                "start": sub["date"].min() if not sub.empty else None,
                "end": sub["date"].max() if not sub.empty else None,
                "net_r": _round(float(sub["r_multiple"].sum()), 2) if not sub.empty else None,
                "trades_2024": int((sub["date"].str[:4] == "2024").sum()) if not sub.empty else 0,
                "r_2024": _round(float(sub.loc[sub["date"].str[:4] == "2024", "r_multiple"].sum()), 2) if not sub.empty else None,
                "trades_2025": int((sub["date"].str[:4] == "2025").sum()) if not sub.empty else 0,
                "r_2025": _round(float(sub.loc[sub["date"].str[:4] == "2025", "r_multiple"].sum()), 2) if not sub.empty else None,
                "trades_2026_ytd": int((sub["date"].str[:4] == "2026").sum()) if not sub.empty else 0,
                "r_2026_ytd": _round(float(sub.loc[sub["date"].str[:4] == "2026", "r_multiple"].sum()), 2) if not sub.empty else None,
            }
        )
    return pd.DataFrame(rows)


def _profile_summary_rows(summary: pd.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for _, row in summary.iterrows():
        rows.append(
            {
                "Profile": row["profile_label"],
                "Year": row["year"],
                "Accts": int(row["accounts"]),
                "Pay": int(row["payouts"]),
                "Breach": int(row["breaches"]),
                "Open": int(row["open"]),
                "Res Pay%": _round(row["resolved_payout_rate_pct"], 1),
                "Res Br%": _round(row["resolved_breach_rate_pct"], 1),
                "Open%": _round(row["open_rate_pct"], 1),
                "Avg PayD": _round(row["avg_days_to_payout"], 1),
                "Med PayD": _round(row["median_days_to_payout"], 1),
                "EV/start": _round(row["ev_per_start_usd"], 0),
                "MCBch": int(row["max_consecutive_breaches"]),
            }
        )
    return rows


def _grid_rows(sweep: pd.DataFrame, n: int = 12) -> list[dict[str, Any]]:
    rows = []
    for _, row in sweep.head(n).iterrows():
        rows.append(
            {
                "HTF": int(row["nq_ny_htf_lsi_risk"]),
                "NQ Asia": int(row["nq_asia_orb_risk"]),
                "ES Asia": int(row["es_asia_orb_risk"]),
                "R11": int(row["nq_ny_orb_r11_risk"]),
                "ES NY": int(row["es_ny_orb_risk"]),
                "Avg PayD": _round(row["avg_days_2024_2025"], 1),
                "Max PayD": _round(row["max_days_2024_2025"], 1),
                "Avg Res Pay%": _round(row["avg_resolved_payout_2024_2025"], 1),
                "Avg Res Br%": _round(row["avg_resolved_breach_2024_2025"], 1),
                "MCBch": int(row["max_consecutive_breaches_2024_2026"]),
                "EV/start": _round(row["avg_ev_2024_2025"], 0),
            }
        )
    return rows


def _write_report(
    *,
    trade_summary: pd.DataFrame,
    static_summary: pd.DataFrame,
    sweep: pd.DataFrame,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    trade_rows = [
        {
            "Leg": row["label"],
            "Trades": int(row["trades"]),
            "Net R": _round(row["net_r"], 1),
            "2024 R": _round(row["r_2024"], 1),
            "2025 R": _round(row["r_2025"], 1),
            "2026 R": _round(row["r_2026_ytd"], 1),
            "Source": row["source"],
        }
        for _, row in trade_summary.iterrows()
    ]
    fast = sweep[sweep["fast_enough_90d"] == True]
    report = f"""# ALPHA_V1 Recent Payout Simulation

- Run slug: `alpha_v1_recent_payout_sim_20260506`
- Windows: `2024`, `2025`, and partial `2026_YTD` through `2026-03-24`.
- Account model: `$50k` account, `$2k` EOD trailing DD capped at `$50k`, payout trigger `$52.5k`, first payout `$500`, account cost `$150`, starts every `14` calendar days.
- Payout and breach percentages below are **resolved-account rates** (`payouts / payouts+breaches`) so open year-end accounts do not distort partial 2026. Open rate is shown separately.

## Trade Stream

{_markdown_table(trade_rows, ["Leg", "Trades", "Net R", "2024 R", "2025 R", "2026 R", "Source"])}

## Proposed ALPHA Menus

{_markdown_table(_profile_summary_rows(static_summary), ["Profile", "Year", "Accts", "Pay", "Breach", "Open", "Res Pay%", "Res Br%", "Open%", "Avg PayD", "Med PayD", "EV/start", "MCBch"])}

## Top Fast-Enough Grid Rows

Rows are ranked on 2024-2025 because 2026 is partial. `Avg PayD` and `Max PayD` must stay under `90d` to be considered fast enough.

{_markdown_table(_grid_rows(fast, 12), ["HTF", "NQ Asia", "ES Asia", "R11", "ES NY", "Avg PayD", "Max PayD", "Avg Res Pay%", "Avg Res Br%", "MCBch", "EV/start"])}

## Read

- Payout speed is **not** the blocker. All three proposed menus are under the desired `2-3 month` average on resolved 2024-2025 payouts.
- The blocker is breach clustering when NY ORB risk is raised. The `Balanced default` is fast (`47d` in 2024, `28d` in 2025), but partial `2026_YTD` resolved at only `2` payouts / `3` breaches / `1` open.
- The safest fast row is `HTF $300 / NQ Asia $300 / ES Asia $150 / R11 $150 / ES NY $100`: average 2024-2025 payout time `52d`, resolved payout `95.7%`, resolved breach `4.3%`, max consecutive breaches `2`, and `2026_YTD` had `2` payouts / `0` breaches / `4` open.
- A more aggressive but still reasonable sprint row is `HTF $300 / NQ Asia $300 / ES Asia $150 / R11 $250 / ES NY $200`: average 2024-2025 payout time `41d`, resolved payout `89.9%`, resolved breach `10.1%`, max consecutive breaches `3`, but partial `2026_YTD` already shows NY-sleeve stress.
- 2026 is too short to finalize sizing; many accounts are still open. Use it as a live-flow sanity check, not a full-year verdict.

## Artifacts

- `trade_stream.csv`
- `trade_summary.csv`
- `static_profile_year_summary.csv`
- `static_profile_account_outcomes.csv`
- `risk_sweep_ranked.csv`
- `summary.json`
"""
    REPORT_PATH.write_text(report)


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    trades = _load_trade_stream()
    trade_summary = _trade_summary(trades)

    static_outcomes = []
    static_summaries = []
    for profile in STATIC_PROFILES:
        outcomes, summary = _summarize_profile(trades, profile)
        static_outcomes.append(outcomes)
        static_summaries.append(summary)
    static_outcomes_df = pd.concat(static_outcomes, ignore_index=True)
    static_summary_df = pd.concat(static_summaries, ignore_index=True)

    sweep = _sweep_risk_grid(trades)

    trades.to_csv(RESULT_DIR / "trade_stream.csv", index=False)
    trade_summary.to_csv(RESULT_DIR / "trade_summary.csv", index=False)
    static_outcomes_df.to_csv(RESULT_DIR / "static_profile_account_outcomes.csv", index=False)
    static_summary_df.to_csv(RESULT_DIR / "static_profile_year_summary.csv", index=False)
    sweep.to_csv(RESULT_DIR / "risk_sweep_ranked.csv", index=False)

    summary = {
        "run_slug": RESULT_DIR.name,
        "funded_model": FUNDED_MODEL,
        "windows": YEARS,
        "inputs": {
            "active_exact_trades": str(ACTIVE_EXACT_TRADES),
            "nq_r11_exact_trades": str(R11_EXACT_TRADES),
        },
        "static_profiles": [
            {"key": p.key, "label": p.label, "risks": p.risks, "notes": p.notes}
            for p in STATIC_PROFILES
        ],
        "top_fast_enough": sweep[sweep["fast_enough_90d"] == True].head(20).to_dict(orient="records"),
        "paths": {
            "result_dir": str(RESULT_DIR),
            "report": str(REPORT_PATH),
            "risk_sweep_ranked": str(RESULT_DIR / "risk_sweep_ranked.csv"),
            "static_profile_year_summary": str(RESULT_DIR / "static_profile_year_summary.csv"),
        },
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(summary, indent=2))
    _write_report(trade_summary=trade_summary, static_summary=static_summary_df, sweep=sweep)
    print(f"Wrote {REPORT_PATH}")
    print(f"Wrote {RESULT_DIR}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
