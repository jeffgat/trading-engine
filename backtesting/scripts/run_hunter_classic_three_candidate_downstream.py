#!/usr/bin/env python3
"""Downstream validation for three frozen NQ Hunter Classic candidates.

Inputs come from the stress-gated strategy workflow packet. This script does
not search new parameters; it scores the three selected candidates across
history, Monte Carlo trade bootstrap, ALPHA_V1 portfolio fit, and a funded
phase-one style account model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


BACKTESTING_DIR = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = BACKTESTING_DIR / "data/results/hunter_classic_stress_gate_strategy_workflow_20260502"
TRADE_DIR = WORKFLOW_DIR / "selected_trades"
OUT_DIR = BACKTESTING_DIR / "data/results/hunter_classic_three_candidate_downstream_20260502"
REPORT_PATH = BACKTESTING_DIR / "learnings/reports/NQ_HUNTER_CLASSIC_THREE_CANDIDATE_DOWNSTREAM_20260502.md"
ALPHA_DAILY_PATH = BACKTESTING_DIR / "data/results/alpha_v1_downside/baseline_full/daily_r.csv"

BASE_RISK_USD = 350.0
ACCOUNT_SIZE = 50_000.0
INITIAL_FLOOR = 48_000.0
TRAILING_DD_USD = 2_000.0
TRAILING_FLOOR_CAP = 50_000.0
PAYOUT_TARGET_BALANCE = 52_500.0
FIRST_PAYOUT_USD = 500.0
ACCOUNT_COST_USD = 100.0
EPOCH = pd.Timestamp("1970-01-01")

MC_PATHS = 5_000
MC_SEED = 20260502


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    label: str
    role: str
    params: str


CANDIDATES = (
    Candidate(
        "ema14_tol0_distnone_relegacy_samewin0",
        "Workflow Leader",
        "workflow/pre-HO leader",
        "EMA14, 0pt tolerance, no distance cap, legacy one reentry after loss",
    ),
    Candidate(
        "ema14_tol2_distnone_relegacy_samewin0",
        "Balanced Challenger",
        "balanced 10y/workflow challenger",
        "EMA14, 2pt tolerance, no distance cap, legacy one reentry after loss",
    ),
    Candidate(
        "ema10_tol0_dist150_reall_samewin0",
        "Recent Challenger",
        "recent hot-regime challenger",
        "EMA10, 0pt tolerance, 150pt distance cap, all non-overlap reentries",
    ),
)


def read_trades(candidate: Candidate) -> pd.DataFrame:
    path = TRADE_DIR / f"{candidate.candidate_id}.csv"
    df = pd.read_csv(path)
    for col in ("signal_dt", "entry_dt", "exit_dt"):
        df[col] = pd.to_datetime(df[col])
    df["date"] = df["exit_dt"].dt.normalize()
    df["candidate_id"] = candidate.candidate_id
    df["label"] = candidate.label
    return df.sort_values(["exit_dt", "trade_no"]).reset_index(drop=True)


def max_drawdown(values: Iterable[float]) -> float:
    returns = np.asarray(list(values), dtype=float)
    if returns.size == 0:
        return 0.0
    equity = np.concatenate([[0.0], np.cumsum(returns)])
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def profit_factor(values: np.ndarray) -> float:
    wins = values[values > 0].sum()
    losses = values[values < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def filter_window(df: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None) -> pd.DataFrame:
    out = df
    if start is not None:
        out = out[out["date"] >= start]
    if end is not None:
        out = out[out["date"] <= end]
    return out.copy()


def daily_r(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    grouped = df.groupby("date")["r"].sum().sort_index()
    idx = pd.date_range(grouped.index.min(), grouped.index.max(), freq="D")
    return grouped.reindex(idx, fill_value=0.0)


def metrics_for(df: pd.DataFrame) -> dict[str, float | int]:
    r = df["r"].to_numpy(dtype=float)
    years = df.groupby(df["date"].dt.year)["r"].sum() if not df.empty else pd.Series(dtype=float)
    return {
        "trades": int(len(df)),
        "net_r": float(r.sum()) if r.size else 0.0,
        "wr_pct": float((r > 0).mean() * 100.0) if r.size else 0.0,
        "pf": profit_factor(r),
        "closed_dd_r": max_drawdown(r),
        "avg_r": float(r.mean()) if r.size else 0.0,
        "positive_years": int((years > 0).sum()),
        "negative_years": int((years < 0).sum()),
    }


def rolling_stress_for(df: pd.DataFrame) -> dict[str, float | int]:
    d = daily_r(df)
    if d.empty:
        return {
            "worst_month_r": 0.0,
            "best_month_r": 0.0,
            "negative_months": 0,
            "worst_21d_sum_r": 0.0,
            "worst_63d_sum_r": 0.0,
            "worst_126d_sum_r": 0.0,
            "worst_21d_dd_r": 0.0,
            "worst_63d_dd_r": 0.0,
            "worst_126d_dd_r": 0.0,
        }

    monthly = d.resample("ME").sum()

    def rolling_dd(days: int) -> float:
        vals = d.to_numpy(dtype=float)
        worst = 0.0
        for end_i in range(len(vals)):
            start_i = max(0, end_i - days + 1)
            worst = min(worst, max_drawdown(vals[start_i : end_i + 1]))
        return float(worst)

    return {
        "worst_month_r": float(monthly.min()),
        "best_month_r": float(monthly.max()),
        "negative_months": int((monthly < 0).sum()),
        "worst_21d_sum_r": float(d.rolling(21, min_periods=1).sum().min()),
        "worst_63d_sum_r": float(d.rolling(63, min_periods=1).sum().min()),
        "worst_126d_sum_r": float(d.rolling(126, min_periods=1).sum().min()),
        "worst_21d_dd_r": rolling_dd(21),
        "worst_63d_dd_r": rolling_dd(63),
        "worst_126d_dd_r": rolling_dd(126),
    }


def monte_carlo_for(df: pd.DataFrame, scale: float, rng: np.random.Generator) -> dict[str, float | int]:
    base = df["r"].to_numpy(dtype=float) * scale
    if base.size == 0:
        return {}
    nets = np.empty(MC_PATHS)
    dds = np.empty(MC_PATHS)
    for i in range(MC_PATHS):
        sample = rng.choice(base, size=base.size, replace=True)
        nets[i] = sample.sum()
        dds[i] = max_drawdown(sample)
    return {
        "paths": MC_PATHS,
        "scale": scale,
        "median_net_r": float(np.median(nets)),
        "p05_net_r": float(np.quantile(nets, 0.05)),
        "p95_net_r": float(np.quantile(nets, 0.95)),
        "median_dd_r": float(np.median(dds)),
        "p05_dd_r": float(np.quantile(dds, 0.05)),
        "p01_dd_r": float(np.quantile(dds, 0.01)),
        "prob_dd_lte_20r": float((dds <= -20.0).mean()),
        "prob_dd_lte_50r": float((dds <= -50.0).mean()),
    }


def simulate_account(trades: pd.DataFrame, start_date: pd.Timestamp, scale: float) -> dict[str, object]:
    balance = ACCOUNT_SIZE
    floor = INITIAL_FLOOR
    peak_balance = balance
    trough_balance = balance
    trades_taken = 0
    start_date = pd.Timestamp(start_date).normalize()
    future = trades[trades["date"] >= start_date].copy()

    if future.empty:
        return {
            "account_start": start_date.date().isoformat(),
            "outcome": "open",
            "outcome_date": start_date.date().isoformat(),
            "days_to_outcome": 0,
            "trades_taken": 0,
            "final_balance": balance,
            "peak_balance": peak_balance,
            "trough_balance": trough_balance,
        }

    for date, day in future.groupby("date", sort=True):
        for _, trade in day.sort_values("exit_dt").iterrows():
            balance += float(trade["r"]) * BASE_RISK_USD * scale
            trades_taken += 1
            peak_balance = max(peak_balance, balance)
            trough_balance = min(trough_balance, balance)

            if balance <= floor:
                return {
                    "account_start": start_date.date().isoformat(),
                    "outcome": "breach",
                    "outcome_date": date.date().isoformat(),
                    "days_to_outcome": int((date - start_date).days) + 1,
                    "trades_taken": trades_taken,
                    "final_balance": balance,
                    "peak_balance": peak_balance,
                    "trough_balance": trough_balance,
                }
            if balance >= PAYOUT_TARGET_BALANCE:
                return {
                    "account_start": start_date.date().isoformat(),
                    "outcome": "payout",
                    "outcome_date": date.date().isoformat(),
                    "days_to_outcome": int((date - start_date).days) + 1,
                    "trades_taken": trades_taken,
                    "final_balance": balance,
                    "peak_balance": peak_balance,
                    "trough_balance": trough_balance,
                }

        floor = max(floor, min(balance - TRAILING_DD_USD, TRAILING_FLOOR_CAP))

    last_date = future["date"].max()
    return {
        "account_start": start_date.date().isoformat(),
        "outcome": "open",
        "outcome_date": last_date.date().isoformat(),
        "days_to_outcome": int((last_date - start_date).days) + 1,
        "trades_taken": trades_taken,
        "final_balance": balance,
        "peak_balance": peak_balance,
        "trough_balance": trough_balance,
    }


def start_dates_for(trades: pd.DataFrame, mode: str) -> list[pd.Timestamp]:
    if trades.empty:
        return []
    first = trades["date"].min()
    last = trades["date"].max()
    if mode == "unique_trade_day":
        return [pd.Timestamp(d) for d in sorted(trades["date"].unique())]
    if mode == "stagger_14d":
        return [pd.Timestamp(d) for d in pd.date_range(first, last, freq="14D")]
    raise ValueError(f"Unknown start mode: {mode}")


def day_ord(ts: pd.Timestamp) -> int:
    return int((pd.Timestamp(ts).normalize() - EPOCH).days)


def ord_to_iso(value: int) -> str:
    return (EPOCH + pd.Timedelta(days=int(value))).date().isoformat()


def phase_one_scorecard(trades: pd.DataFrame, scale: float, mode: str) -> tuple[dict[str, object], pd.DataFrame]:
    starts = start_dates_for(trades, mode)
    sorted_trades = trades.sort_values(["date", "exit_dt"]).copy()
    trade_days = np.array([day_ord(d) for d in sorted_trades["date"]], dtype=np.int64)
    trade_pnls = sorted_trades["r"].to_numpy(dtype=float) * BASE_RISK_USD * scale

    rows = []
    for start in starts:
        start_day = day_ord(start)
        idx = int(np.searchsorted(trade_days, start_day, side="left"))
        balance = ACCOUNT_SIZE
        floor = INITIAL_FLOOR
        peak_balance = balance
        trough_balance = balance
        trades_taken = 0

        if idx >= len(trade_days):
            rows.append(
                {
                    "account_start": ord_to_iso(start_day),
                    "outcome": "open",
                    "outcome_date": ord_to_iso(start_day),
                    "days_to_outcome": 0,
                    "trades_taken": 0,
                    "final_balance": balance,
                    "peak_balance": peak_balance,
                    "trough_balance": trough_balance,
                }
            )
            continue

        current_day = int(trade_days[idx])
        outcome_row = None
        for j in range(idx, len(trade_days)):
            this_day = int(trade_days[j])
            if this_day != current_day:
                floor = max(floor, min(balance - TRAILING_DD_USD, TRAILING_FLOOR_CAP))
                current_day = this_day

            balance += float(trade_pnls[j])
            trades_taken += 1
            peak_balance = max(peak_balance, balance)
            trough_balance = min(trough_balance, balance)

            if balance <= floor:
                outcome_row = {
                    "account_start": ord_to_iso(start_day),
                    "outcome": "breach",
                    "outcome_date": ord_to_iso(this_day),
                    "days_to_outcome": int(this_day - start_day) + 1,
                    "trades_taken": trades_taken,
                    "final_balance": balance,
                    "peak_balance": peak_balance,
                    "trough_balance": trough_balance,
                }
                break
            if balance >= PAYOUT_TARGET_BALANCE:
                outcome_row = {
                    "account_start": ord_to_iso(start_day),
                    "outcome": "payout",
                    "outcome_date": ord_to_iso(this_day),
                    "days_to_outcome": int(this_day - start_day) + 1,
                    "trades_taken": trades_taken,
                    "final_balance": balance,
                    "peak_balance": peak_balance,
                    "trough_balance": trough_balance,
                }
                break

        if outcome_row is None:
            last_day = int(trade_days[-1])
            outcome_row = {
                "account_start": ord_to_iso(start_day),
                "outcome": "open",
                "outcome_date": ord_to_iso(last_day),
                "days_to_outcome": int(last_day - start_day) + 1,
                "trades_taken": trades_taken,
                "final_balance": balance,
                "peak_balance": peak_balance,
                "trough_balance": trough_balance,
            }
        rows.append(outcome_row)

    detail = pd.DataFrame(rows)
    total = len(detail)
    if total == 0:
        return {
            "accounts": 0,
            "payout_rate_pct": 0.0,
            "breach_rate_pct": 0.0,
            "open_rate_pct": 0.0,
            "resolved_success_pct": 0.0,
            "median_days_to_payout": np.nan,
            "median_trades_to_payout": np.nan,
            "ev_per_attempt_usd": -ACCOUNT_COST_USD,
        }, detail

    counts = detail["outcome"].value_counts()
    payouts = detail[detail["outcome"] == "payout"]
    breaches = detail[detail["outcome"] == "breach"]
    resolved = len(payouts) + len(breaches)
    payout_rate = len(payouts) / total
    breach_rate = len(breaches) / total
    open_rate = float(counts.get("open", 0) / total)
    resolved_success = len(payouts) / resolved if resolved else 0.0
    ev = payout_rate * FIRST_PAYOUT_USD - ACCOUNT_COST_USD
    return {
        "accounts": int(total),
        "payout_rate_pct": float(payout_rate * 100.0),
        "breach_rate_pct": float(breach_rate * 100.0),
        "open_rate_pct": float(open_rate * 100.0),
        "resolved_success_pct": float(resolved_success * 100.0),
        "median_days_to_payout": float(payouts["days_to_outcome"].median()) if len(payouts) else np.nan,
        "median_trades_to_payout": float(payouts["trades_taken"].median()) if len(payouts) else np.nan,
        "ev_per_attempt_usd": float(ev),
    }, detail


def portfolio_metrics(daily: pd.Series) -> dict[str, float]:
    d = daily.fillna(0.0).astype(float)
    monthly = d.resample("ME").sum()
    return {
        "net_r": float(d.sum()),
        "closed_dd_r": max_drawdown(d.to_numpy()),
        "worst_month_r": float(monthly.min()) if len(monthly) else 0.0,
        "best_month_r": float(monthly.max()) if len(monthly) else 0.0,
    }


def alpha_portfolio_rows(candidate: Candidate, trades: pd.DataFrame) -> list[dict[str, object]]:
    alpha = pd.read_csv(ALPHA_DAILY_PATH, index_col=0, parse_dates=True)
    legs = [c for c in alpha.columns if c != "alpha_v1_total"]
    hunter = daily_r(trades)
    start = max(alpha.index.min(), hunter.index.min())
    end = min(alpha.index.max(), hunter.index.max())
    alpha = alpha.loc[(alpha.index >= start) & (alpha.index <= end)].copy()
    hunter = hunter.reindex(alpha.index, fill_value=0.0)

    if "es_ny_orb_long" not in alpha.columns:
        raise ValueError("ALPHA_V1 daily_r.csv is missing es_ny_orb_long")

    baseline = alpha[legs].sum(axis=1)
    rows: list[dict[str, object]] = []
    scenarios = [
        ("ALPHA_V1 baseline", 1.00, 0.00),
        ("+ Hunter 0.25x", 1.00, 0.25),
        ("+ Hunter 0.50x", 1.00, 0.50),
        ("+ Hunter 1.00x", 1.00, 1.00),
        ("ES_NY 0.75x + Hunter 0.25x", 0.75, 0.25),
        ("ES_NY 0.50x + Hunter 0.50x", 0.50, 0.50),
    ]
    for scenario, es_ny_scale, hunter_scale in scenarios:
        adjusted = alpha[legs].copy()
        adjusted["es_ny_orb_long"] = adjusted["es_ny_orb_long"] * es_ny_scale
        series = adjusted.sum(axis=1) + hunter * hunter_scale
        m = portfolio_metrics(series)
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "label": candidate.label,
                "scenario": scenario,
                "start": start.date().isoformat(),
                "end": end.date().isoformat(),
                "es_ny_scale": es_ny_scale,
                "hunter_scale": hunter_scale,
                "corr_to_alpha": float(hunter.corr(baseline)) if hunter.std() > 0 and baseline.std() > 0 else 0.0,
                **m,
            }
        )
    return rows


def fmt_num(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:,.{digits}f}"


def fmt_signed_r(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:+,.{digits}f}R"


def fmt_pct(value: float, digits: int = 1) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:,.{digits}f}%"


def fmt_usd(value: float, digits: int = 0) -> str:
    if pd.isna(value):
        return "n/a"
    return f"${value:,.{digits}f}"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def build_report(
    window_metrics: pd.DataFrame,
    stress_metrics: pd.DataFrame,
    mc: pd.DataFrame,
    phase: pd.DataFrame,
    portfolio: pd.DataFrame,
) -> str:
    full = window_metrics[window_metrics["window"] == "full_10y"].copy()
    last_1 = window_metrics[window_metrics["window"] == "last_1y"].copy()
    holdout = window_metrics[window_metrics["window"] == "holdout_2025_plus"].copy()
    phase_focus = phase[
        (phase["start_mode"] == "stagger_14d")
        & (phase["window"].isin(["full_10y", "holdout_2025_plus", "last_1y"]))
        & (phase["scale"] == 0.25)
    ].copy()
    portfolio_focus = portfolio[
        portfolio["scenario"].isin(["ALPHA_V1 baseline", "+ Hunter 0.25x", "ES_NY 0.75x + Hunter 0.25x"])
    ].copy()

    comparison_rows = []
    for candidate in CANDIDATES:
        c_full = full[full["candidate_id"] == candidate.candidate_id].iloc[0]
        c_hold = holdout[holdout["candidate_id"] == candidate.candidate_id].iloc[0]
        c_last = last_1[last_1["candidate_id"] == candidate.candidate_id].iloc[0]
        comparison_rows.append(
            [
                candidate.label,
                f"`{candidate.candidate_id}`",
                fmt_signed_r(c_full["net_r"]),
                fmt_signed_r(c_full["closed_dd_r"]),
                fmt_signed_r(c_hold["net_r"]),
                fmt_signed_r(c_last["net_r"]),
                fmt_pct(c_last["wr_pct"]),
                fmt_num(c_full["pf"], 2),
            ]
        )

    stress_rows = []
    for candidate in CANDIDATES:
        s = stress_metrics[stress_metrics["candidate_id"] == candidate.candidate_id].iloc[0]
        stress_rows.append(
            [
                candidate.label,
                fmt_signed_r(s["worst_month_r"]),
                fmt_signed_r(s["worst_63d_dd_r"]),
                fmt_signed_r(s["worst_126d_dd_r"]),
                fmt_signed_r(s["worst_126d_sum_r"]),
                str(int(s["negative_months"])),
            ]
        )

    mc_rows = []
    for candidate in CANDIDATES:
        m = mc[(mc["candidate_id"] == candidate.candidate_id) & (mc["scale"] == 0.25)].iloc[0]
        mc_rows.append(
            [
                candidate.label,
                fmt_signed_r(m["median_net_r"]),
                fmt_signed_r(m["p05_net_r"]),
                fmt_signed_r(m["median_dd_r"]),
                fmt_signed_r(m["p05_dd_r"]),
                fmt_pct(m["prob_dd_lte_20r"] * 100.0),
            ]
        )

    phase_rows = []
    for _, row in phase_focus.iterrows():
        phase_rows.append(
            [
                row["label"],
                row["window"],
                str(int(row["accounts"])),
                fmt_pct(row["payout_rate_pct"]),
                fmt_pct(row["breach_rate_pct"]),
                fmt_pct(row["open_rate_pct"]),
                fmt_num(row["median_days_to_payout"], 0),
                fmt_usd(row["ev_per_attempt_usd"], 0),
            ]
        )

    portfolio_rows = []
    for _, row in portfolio_focus.iterrows():
        portfolio_rows.append(
            [
                row["label"],
                row["scenario"],
                fmt_signed_r(row["net_r"]),
                fmt_signed_r(row["closed_dd_r"]),
                fmt_signed_r(row["worst_month_r"]),
                fmt_num(row["corr_to_alpha"], 2),
            ]
        )

    return "\n\n".join(
        [
            "# NQ Hunter Classic Three-Candidate Downstream Validation (2026-05-02)",
            "## Scope\n\n"
            "This packet moves the three frozen stress-gated Hunter candidates from the strategy workflow into downstream validation. "
            "No new parameters were searched here. The stress gate remains: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`.",
            "## Candidates\n\n"
            + md_table(
                ["Label", "Candidate", "Role", "Params"],
                [[c.label, f"`{c.candidate_id}`", c.role, c.params] for c in CANDIDATES],
            ),
            "## Core Performance\n\n"
            + md_table(
                ["Label", "Candidate", "Full Net", "Full DD", "2025+ Net", "Last 1y Net", "Last 1y WR", "Full PF"],
                comparison_rows,
            ),
            "## Rolling Stress\n\n"
            + md_table(
                ["Label", "Worst Month", "Worst 3m DD", "Worst 6m DD", "Worst 6m Sum", "Negative Months"],
                stress_rows,
            ),
            "## Monte Carlo Bootstrap at 0.25x Risk\n\n"
            + md_table(
                ["Label", "Median Net", "p05 Net", "Median DD", "p05 DD", "Prob DD <= -20R"],
                mc_rows,
            ),
            "## Phase-One Scorecard, 14-Day Staggered Starts at 0.25x Risk\n\n"
            + md_table(
                ["Label", "Window", "Accounts", "Payout", "Breach", "Open", "Median Days to Payout", "EV/Attempt"],
                phase_rows,
            ),
            "## ALPHA_V1 Portfolio Fit\n\n"
            + md_table(
                ["Label", "Scenario", "Net", "DD", "Worst Month", "Corr"],
                portfolio_rows,
            ),
            "## Read\n\n"
            "- The balanced challenger is the slight pilot preference: it is nearly tied with the workflow leader pre-holdout, but improves full history, 2025+, last 1y, and the 0.25x phase-one scorecard.\n"
            "- The workflow leader remains the cleanest search-discipline fallback because it won pre-holdout without seeing 2025+.\n"
            "- The recent challenger keeps the best last-year profile, but it is still the most hindsight-sensitive branch because its pre-holdout score is much weaker.\n"
            "- At 0.25x risk, all three are viable as paper/live pilot legs beside ALPHA_V1; larger sizing should wait for more forward data because full-risk Monte Carlo and historical drawdowns remain too large for a single funded account.",
            "## Artifacts\n\n"
            f"- Results packet: `{OUT_DIR.relative_to(BACKTESTING_DIR.parent)}`\n"
            f"- Repro script: `backtesting/scripts/{Path(__file__).name}`",
            "",
        ]
    )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    trades_by_candidate = {candidate.candidate_id: read_trades(candidate) for candidate in CANDIDATES}
    common_end = min(df["date"].max() for df in trades_by_candidate.values())
    last_1y_start = common_end - pd.DateOffset(years=1) + pd.Timedelta(days=1)
    last_2y_start = common_end - pd.DateOffset(years=2) + pd.Timedelta(days=1)

    windows: dict[str, tuple[pd.Timestamp | None, pd.Timestamp | None]] = {
        "full_10y": (None, None),
        "pre_holdout": (None, pd.Timestamp("2024-12-31")),
        "holdout_2025_plus": (pd.Timestamp("2025-01-01"), None),
        "last_2y": (last_2y_start.normalize(), None),
        "last_1y": (last_1y_start.normalize(), None),
    }

    window_rows = []
    stress_rows = []
    annual_rows = []
    monthly_rows = []
    mc_rows = []
    phase_rows = []
    account_detail_frames = []
    portfolio_rows = []
    rng = np.random.default_rng(MC_SEED)

    for candidate in CANDIDATES:
        trades = trades_by_candidate[candidate.candidate_id]

        for window_name, (start, end) in windows.items():
            subset = filter_window(trades, start, end)
            window_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "label": candidate.label,
                    "role": candidate.role,
                    "window": window_name,
                    "start": subset["date"].min().date().isoformat() if len(subset) else "",
                    "end": subset["date"].max().date().isoformat() if len(subset) else "",
                    **metrics_for(subset),
                }
            )

            if window_name == "full_10y":
                stress_rows.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "label": candidate.label,
                        **rolling_stress_for(subset),
                    }
                )

            years = subset.groupby(subset["date"].dt.year)["r"].sum() if len(subset) else pd.Series(dtype=float)
            for year, net_r in years.items():
                annual_rows.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "label": candidate.label,
                        "window": window_name,
                        "year": int(year),
                        "net_r": float(net_r),
                    }
                )

            d = daily_r(subset)
            if len(d):
                for month, net_r in d.resample("ME").sum().items():
                    monthly_rows.append(
                        {
                            "candidate_id": candidate.candidate_id,
                            "label": candidate.label,
                            "window": window_name,
                            "month": month.date().isoformat(),
                            "net_r": float(net_r),
                        }
                    )

            for scale in (1.0, 0.5, 0.25):
                for mode in ("unique_trade_day", "stagger_14d"):
                    summary, detail = phase_one_scorecard(subset, scale, mode)
                    phase_rows.append(
                        {
                            "candidate_id": candidate.candidate_id,
                            "label": candidate.label,
                            "window": window_name,
                            "scale": scale,
                            "start_mode": mode,
                            **summary,
                        }
                    )
                    if window_name in ("full_10y", "holdout_2025_plus", "last_1y") and scale == 0.25:
                        detail = detail.copy()
                        detail["candidate_id"] = candidate.candidate_id
                        detail["label"] = candidate.label
                        detail["window"] = window_name
                        detail["scale"] = scale
                        detail["start_mode"] = mode
                        account_detail_frames.append(detail)

        for scale in (1.0, 0.5, 0.25):
            mc_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "label": candidate.label,
                    **monte_carlo_for(trades, scale, rng),
                }
            )

        portfolio_rows.extend(alpha_portfolio_rows(candidate, trades))

    window_metrics = pd.DataFrame(window_rows)
    stress_metrics = pd.DataFrame(stress_rows)
    annual = pd.DataFrame(annual_rows)
    monthly = pd.DataFrame(monthly_rows)
    mc = pd.DataFrame(mc_rows)
    phase = pd.DataFrame(phase_rows)
    portfolio = pd.DataFrame(portfolio_rows)
    account_details = pd.concat(account_detail_frames, ignore_index=True) if account_detail_frames else pd.DataFrame()

    window_metrics.to_csv(OUT_DIR / "candidate_window_metrics.csv", index=False)
    stress_metrics.to_csv(OUT_DIR / "rolling_stress_metrics.csv", index=False)
    annual.to_csv(OUT_DIR / "annual_returns.csv", index=False)
    monthly.to_csv(OUT_DIR / "monthly_returns.csv", index=False)
    mc.to_csv(OUT_DIR / "monte_carlo_bootstrap.csv", index=False)
    phase.to_csv(OUT_DIR / "phase_one_scorecard.csv", index=False)
    portfolio.to_csv(OUT_DIR / "portfolio_scenarios.csv", index=False)
    account_details.to_csv(OUT_DIR / "phase_one_account_details_025x.csv", index=False)

    summary = {
        "generated_at": "2026-05-02",
        "common_end": common_end.date().isoformat(),
        "last_1y_start": last_1y_start.date().isoformat(),
        "last_2y_start": last_2y_start.date().isoformat(),
        "candidates": [candidate.__dict__ for candidate in CANDIDATES],
        "outputs": sorted(path.name for path in OUT_DIR.iterdir()),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=True) + "\n")

    report = build_report(window_metrics, stress_metrics, mc, phase, portfolio)
    REPORT_PATH.write_text(report)
    (OUT_DIR / "summary.md").write_text(report)

    print(f"Wrote results to {OUT_DIR}")
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
