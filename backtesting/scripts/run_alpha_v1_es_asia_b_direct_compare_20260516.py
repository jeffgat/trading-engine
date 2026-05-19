#!/usr/bin/env python3
"""Exact live-engine comparison for active ALPHA ES Asia vs ES Asia-B.

Creates temporary in-memory execution profiles only. No execution config files
are edited.
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
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "alpha_v1_es_asia_b_direct_compare_20260516"
BASE_PROFILE = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"

RESULT_DIR = ROOT / "backtesting" / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "ALPHA_V1_ES_ASIA_B_DIRECT_COMPARE_20260516.md"

ACTIVE_EXACT_TRADES = ROOT / "backtesting" / "data" / "results" / "alpha_v1_live_replay_compare_20260503" / "exact_trades.csv"
R11_EXACT_TRADES = ROOT / "backtesting" / "data" / "results" / "alpha_v1_single_vs_split_exact_compare_20260506" / "split_exact_trades.csv"

WINDOWS = {
    "full": ("2016-04-17", "2026-03-24"),
    "2024_plus": ("2024-01-01", "2026-03-24"),
    "2025_plus": ("2025-01-01", "2026-03-24"),
    "last_2y": ("2024-03-24", "2026-03-24"),
    "last_1y": ("2025-03-24", "2026-03-24"),
}

YEARS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026_YTD": ("2026-01-01", "2026-03-24"),
}

LEG_MAP = {
    "NQ_NY_LSI": "nq_ny_htf_lsi",
    "NQ_Asia": "nq_asia_orb",
    "ES_Asia": "es_asia_orb",
    "ES_NY": "es_ny_orb",
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
class Candidate:
    key: str
    label: str
    notes: str
    session_overrides: dict[str, Any]


@dataclass(frozen=True)
class RiskProfile:
    key: str
    label: str
    risks: dict[str, float]


RISK_PROFILES = (
    RiskProfile(
        key="fast_safe",
        label="Fast-safe annual default",
        risks={
            "nq_ny_htf_lsi": 300.0,
            "nq_asia_orb": 300.0,
            "es_asia_orb": 150.0,
            "nq_ny_orb_r11": 150.0,
            "es_ny_orb": 100.0,
        },
    ),
    RiskProfile(
        key="balanced_ny",
        label="Balanced NY sleeve",
        risks={
            "nq_ny_htf_lsi": 300.0,
            "nq_asia_orb": 300.0,
            "es_asia_orb": 200.0,
            "nq_ny_orb_r11": 250.0,
            "es_ny_orb": 200.0,
        },
    ),
    RiskProfile(
        key="aggressive_sprint",
        label="Aggressive sprint",
        risks={
            "nq_ny_htf_lsi": 500.0,
            "nq_asia_orb": 400.0,
            "es_asia_orb": 150.0,
            "nq_ny_orb_r11": 250.0,
            "es_ny_orb": 300.0,
        },
    ),
)


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    return data


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _slice(trades: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [trade for trade in trades if start <= str(trade.get("date", "")) <= end]


def _summary_row(candidate: Candidate, trades: list[dict[str, Any]], window: str, start: str, end: str) -> dict[str, Any]:
    selected = _slice(trades, start, end)
    summary = hb._compute_summary(selected)
    exit_counts: dict[str, int] = {}
    for trade in selected:
        key = str(trade.get("exit_type", ""))
        exit_counts[key] = exit_counts.get(key, 0) + 1
    total = int(summary.get("total_trades", 0) or 0)

    def pct(count: int) -> float | None:
        return _round(count / total * 100.0, 2) if total else None

    full_targets = exit_counts.get("tp1_tp2", 0)
    tp1_be = exit_counts.get("tp1_be", 0)
    stops = exit_counts.get("sl", 0)
    eod_exits = exit_counts.get("eod", 0) + exit_counts.get("tp1_eod", 0)
    single_tp1 = exit_counts.get("tp1_single", 0)
    return {
        "candidate": candidate.key,
        "label": candidate.label,
        "window": window,
        "start": start,
        "end": end,
        "trades": int(summary.get("total_trades", 0) or 0),
        "net_r": _round(summary.get("total_r"), 2),
        "net_r_fee_adjusted": _round(summary.get("total_net_r"), 2),
        "win_rate_pct": _round(float(summary.get("win_rate", 0.0) or 0.0) * 100.0, 2),
        "profit_factor": _round(summary.get("profit_factor"), 3),
        "sharpe": _round(summary.get("sharpe_ratio"), 3),
        "calmar": _round(summary.get("calmar_ratio"), 3),
        "max_dd_r": _round(summary.get("max_drawdown_r"), 2),
        "full_target_rate_pct": pct(full_targets),
        "tp1_be_rate_pct": pct(tp1_be),
        "sl_rate_pct": pct(stops),
        "eod_rate_pct": pct(eod_exits),
        "single_tp1_rate_pct": pct(single_tp1),
        "exit_counts": json.dumps(exit_counts, sort_keys=True),
    }


def _profile_for(candidate: Candidate) -> ExecutionConfig:
    return ExecutionConfig(
        name=f"EXACT_{candidate.key}",
        enabled=True,
        max_open_contracts=20,
        webhooks=[],
        session_overrides={"ES_Asia": copy.deepcopy(candidate.session_overrides)},
        lsi_session_overrides={},
    )


def _run_candidate(config: dict[str, Any], candidate: Candidate) -> dict[str, Any]:
    profile = _profile_for(candidate)
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


def _load_current_portfolio_stream(candidate_trades: pd.DataFrame | None = None) -> pd.DataFrame:
    active = pd.read_csv(ACTIVE_EXACT_TRADES)
    active = active.copy()
    active["leg"] = active["session"].map(LEG_MAP)
    active = active[active["leg"].notna()].copy()
    if candidate_trades is not None:
        active = active[active["leg"] != "es_asia_orb"].copy()
        active = pd.concat([active, candidate_trades], ignore_index=True)

    r11 = pd.read_csv(R11_EXACT_TRADES)
    r11 = r11[r11["comparison_leg"] == "nq_ny_orb_r11"].copy()
    r11["leg"] = "nq_ny_orb_r11"

    keep = ["leg", "date", "entry_time", "exit_time", "r_multiple"]
    stream = pd.concat([active[keep], r11[keep]], ignore_index=True)
    stream["date"] = stream["date"].astype(str)
    stream["exit_ts"] = pd.to_datetime(stream["exit_time"], utc=True, errors="coerce")
    stream["entry_ts"] = pd.to_datetime(stream["entry_time"], utc=True, errors="coerce")
    stream = stream[stream["exit_ts"].notna()].copy()
    stream["r_multiple"] = stream["r_multiple"].astype(float)
    return stream.sort_values(["exit_ts", "leg", "entry_ts"]).reset_index(drop=True)


def _candidate_stream(trades: list[dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for trade in trades:
        rows.append(
            {
                "leg": "es_asia_orb",
                "date": str(trade["date"]),
                "entry_time": trade.get("entry_time"),
                "exit_time": trade.get("exit_time"),
                "r_multiple": float(trade.get("r_multiple", 0.0)),
            }
        )
    return pd.DataFrame(rows)


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize().tz_localize("UTC")
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def _simulate_accounts(trades: pd.DataFrame, *, start: str, end: str, profile: RiskProfile) -> pd.DataFrame:
    subset = trades[(trades["date"] >= start) & (trades["date"] <= end)].copy()
    subset["risk_usd"] = subset["leg"].map(profile.risks).astype(float)
    subset["pnl_usd"] = subset["r_multiple"] * subset["risk_usd"]
    subset = subset.sort_values(["exit_ts", "leg", "entry_ts"]).reset_index(drop=True)

    trade_tuples = [
        (row.exit_ts, pd.Timestamp(row.exit_ts).date().isoformat(), float(row.pnl_usd))
        for row in subset[["exit_ts", "pnl_usd"]].itertuples(index=False)
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

        for exit_ts, trade_day, pnl_usd in trade_tuples:
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
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_MODEL["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        net_after_fee = (
            float(FUNDED_MODEL["first_payout_withdrawal_usd"]) - float(FUNDED_MODEL["challenge_fee_usd"])
            if outcome == "payout"
            else -float(FUNDED_MODEL["challenge_fee_usd"])
        )
        rows.append(
            {
                "account_id": account_id,
                "account_start": start_ts.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date).date() - start_ts.date()).days) + 1,
                "trades_to_outcome": trades_taken,
                "net_after_fee_usd": round(net_after_fee, 2),
            }
        )
    return pd.DataFrame(rows)


def _max_consecutive(outcomes: pd.DataFrame, name: str) -> int:
    max_run = 0
    run = 0
    for _, row in outcomes.sort_values("account_start").iterrows():
        if row["outcome"] == name:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def _score_outcomes(outcomes: pd.DataFrame) -> dict[str, Any]:
    total = len(outcomes)
    payouts = outcomes[outcomes["outcome"] == "payout"]
    breaches = outcomes[outcomes["outcome"] == "breach"]
    opens = outcomes[outcomes["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    return {
        "accounts": int(total),
        "payouts": int(len(payouts)),
        "breaches": int(len(breaches)),
        "open": int(len(opens)),
        "resolved_payout_rate_pct": _round(len(payouts) / resolved * 100.0, 2) if resolved else None,
        "resolved_breach_rate_pct": _round(len(breaches) / resolved * 100.0, 2) if resolved else None,
        "start_payout_rate_pct": _round(len(payouts) / total * 100.0, 2) if total else None,
        "start_breach_rate_pct": _round(len(breaches) / total * 100.0, 2) if total else None,
        "open_rate_pct": _round(len(opens) / total * 100.0, 2) if total else None,
        "avg_days_to_payout": _round(float(payouts["days_to_outcome"].mean()), 1) if not payouts.empty else None,
        "median_days_to_payout": _round(float(payouts["days_to_outcome"].median()), 1) if not payouts.empty else None,
        "max_consecutive_breaches": _max_consecutive(outcomes, "breach"),
        "ev_per_start_usd": _round(float(outcomes["net_after_fee_usd"].mean()), 2) if total else None,
    }


def _portfolio_rows(label: str, stream: pd.DataFrame) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    outcomes_all = []
    for profile in RISK_PROFILES:
        for year, (start, end) in YEARS.items():
            outcomes = _simulate_accounts(stream, start=start, end=end, profile=profile)
            outcomes["portfolio_variant"] = label
            outcomes["risk_profile"] = profile.key
            outcomes["year"] = year
            outcomes_all.append(outcomes)
            row = {
                "portfolio_variant": label,
                "risk_profile": profile.key,
                "risk_label": profile.label,
                "year": year,
                **_score_outcomes(outcomes),
            }
            rows.append(row)
    return rows, pd.concat(outcomes_all, ignore_index=True)


def _build_candidates(alpha: ExecutionConfig) -> list[Candidate]:
    active = copy.deepcopy(alpha.session_overrides["ES_Asia"])
    active.setdefault("instrument", "ES")
    active.setdefault("risk_usd", 150)
    active.setdefault("max_single_risk_usd", 225)

    asia_b_base = {
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
        "risk_usd": 150,
        "max_single_risk_usd": 225,
    }
    original = {**asia_b_base, "rr": 3.0, "tp1_ratio": 0.6}
    constrained = {**asia_b_base, "rr": 2.0, "tp1_ratio": 0.75}

    return [
        Candidate(
            key="active_es_asia_rr1p5_tp0p7",
            label="Active ALPHA ES Asia ORB",
            notes="Current ALPHA_V1-A ES_Asia execution profile.",
            session_overrides=active,
        ),
        Candidate(
            key="es_asia_b_original_rr3_tp0p6",
            label="ES Asia-B original",
            notes="Original Asia-B thesis: ATR 12%, RR 3.0, TP1 0.6, entry to 23:15, flat 04:00-07:00.",
            session_overrides=original,
        ),
        Candidate(
            key="es_asia_b_constrained_rr2_tp0p75",
            label="ES Asia-B constrained target",
            notes="Live-native constrained target row from the ALPHA candidate sweep family.",
            session_overrides=constrained,
        ),
    ]


def _md_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> list[str]:
    lines = [
        "| " + " | ".join(label for label, _ in columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for _, key in columns:
            value = row.get(key)
            if isinstance(value, float):
                value = f"{value:.2f}"
            elif value is None:
                value = "-"
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return lines


def _write_report(window_rows: list[dict[str, Any]], portfolio_rows: list[dict[str, Any]]) -> None:
    full_rows = [row for row in window_rows if row["window"] == "full"]
    recent_rows = [row for row in window_rows if row["window"] in {"2025_plus", "last_1y"}]
    portfolio_2025 = [row for row in portfolio_rows if row["year"] == "2025"]
    lines = [
        "# ALPHA_V1 ES Asia-B Direct Compare",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Engine path: `execution/src/trader/historical_backtest.py` with temporary ES_Asia-only profiles.",
        f"- Window: `{FULL_START}` to `{END_DATE}`.",
        "- No execution config files were edited.",
        "",
        "## Exact Standalone Full Window",
        "",
        *_md_table(
            full_rows,
            [
                ("Candidate", "label"),
                ("Trades", "trades"),
                ("Net R", "net_r"),
                ("PF", "profit_factor"),
                ("WR %", "win_rate_pct"),
                ("DD R", "max_dd_r"),
                ("Sharpe", "sharpe"),
                ("Calmar", "calmar"),
                ("Full TP %", "full_target_rate_pct"),
                ("TP1-BE %", "tp1_be_rate_pct"),
                ("SL %", "sl_rate_pct"),
                ("EOD %", "eod_rate_pct"),
            ],
        ),
        "",
        "## Exact Recent Windows",
        "",
        *_md_table(
            recent_rows,
            [
                ("Candidate", "label"),
                ("Window", "window"),
                ("Trades", "trades"),
                ("Net R", "net_r"),
                ("PF", "profit_factor"),
                ("DD R", "max_dd_r"),
                ("Sharpe", "sharpe"),
            ],
        ),
        "",
        "## Five-Leg Portfolio Replacement Read, 2025",
        "",
        *_md_table(
            portfolio_2025,
            [
                ("Variant", "portfolio_variant"),
                ("Risk", "risk_profile"),
                ("Payout %", "resolved_payout_rate_pct"),
                ("Breach %", "resolved_breach_rate_pct"),
                ("Open %", "open_rate_pct"),
                ("Avg PayD", "avg_days_to_payout"),
                ("Max CBr", "max_consecutive_breaches"),
                ("EV/start", "ev_per_start_usd"),
            ],
        ),
        "",
        "## Artifacts",
        "",
        f"- `backtesting/data/results/{RUN_SLUG}/window_metrics.csv`",
        f"- `backtesting/data/results/{RUN_SLUG}/portfolio_summary.csv`",
        f"- `backtesting/data/results/{RUN_SLUG}/exact_trades.csv`",
        f"- `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    alpha = {profile.name: profile for profile in load_exec_configs(config)}[BASE_PROFILE]
    candidates = _build_candidates(alpha)

    all_trades: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    candidate_streams: dict[str, pd.DataFrame] = {}
    payload_candidates: list[dict[str, Any]] = []

    for candidate in candidates:
        print(f"Running {candidate.label}...", flush=True)
        result = _run_candidate(config, candidate)
        trades = result.get("trades", [])
        for trade in trades:
            trade["candidate"] = candidate.key
            trade["candidate_label"] = candidate.label
        all_trades.extend(trades)
        candidate_streams[candidate.key] = _candidate_stream(trades)
        for window, (start, end) in WINDOWS.items():
            window_rows.append(_summary_row(candidate, trades, window, start, end))
        payload_candidates.append(
            {
                "key": candidate.key,
                "label": candidate.label,
                "notes": candidate.notes,
                "session_overrides": _safe_json(candidate.session_overrides),
                "summary": _safe_json(result.get("summary", {})),
            }
        )

    current_stream = _load_current_portfolio_stream()
    portfolio_rows, portfolio_outcomes = _portfolio_rows("current_active_es_asia", current_stream)
    for key in ("es_asia_b_original_rr3_tp0p6", "es_asia_b_constrained_rr2_tp0p75"):
        stream = _load_current_portfolio_stream(candidate_streams[key])
        rows, outcomes = _portfolio_rows(key, stream)
        portfolio_rows.extend(rows)
        portfolio_outcomes = pd.concat([portfolio_outcomes, outcomes], ignore_index=True)

    pd.DataFrame(all_trades).to_csv(RESULT_DIR / "exact_trades.csv", index=False)
    pd.DataFrame(window_rows).to_csv(RESULT_DIR / "window_metrics.csv", index=False)
    pd.DataFrame(portfolio_rows).to_csv(RESULT_DIR / "portfolio_summary.csv", index=False)
    portfolio_outcomes.to_csv(RESULT_DIR / "portfolio_account_outcomes.csv", index=False)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "base_profile": BASE_PROFILE,
        "date_range": {"start": FULL_START, "end": END_DATE},
        "candidates": payload_candidates,
        "window_rows": window_rows,
        "portfolio_rows": portfolio_rows,
        "paths": {
            "result_dir": str(RESULT_DIR),
            "report": str(REPORT_PATH),
        },
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True) + "\n")
    _write_report(window_rows, portfolio_rows)
    print(json.dumps({"result_dir": str(RESULT_DIR), "report": str(REPORT_PATH)}, indent=2))


if __name__ == "__main__":
    main()
