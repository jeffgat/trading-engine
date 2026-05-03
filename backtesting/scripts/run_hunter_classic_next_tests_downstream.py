#!/usr/bin/env python3
"""Downstream validation for the Hunter next-test frozen branches.

This script does not search parameters. It scores the three branches selected
after the Hunter next-tests grid:

- neutral reference: balanced stress-gated baseline
- 10y-safe branch: pre-holdout leader with Tuesday + disabled rejection filter
- recent-strength branch: no-Tuesday, EMA14 tol5, disabled rejection filter
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_hunter_classic_three_candidate_downstream import (
    ACCOUNT_COST_USD,
    ACCOUNT_SIZE,
    ALPHA_DAILY_PATH,
    BASE_RISK_USD,
    FIRST_PAYOUT_USD,
    MC_PATHS,
    MC_SEED,
    PAYOUT_TARGET_BALANCE,
    TRAILING_DD_USD,
    daily_r,
    filter_window,
    max_drawdown,
    metrics_for,
    monte_carlo_for,
    phase_one_scorecard,
    portfolio_metrics,
    rolling_stress_for,
)


BACKTESTING_DIR = Path(__file__).resolve().parent.parent
TRADE_DIR = BACKTESTING_DIR / "data/results/hunter_classic_next_tests_20260502/selected_trades"
OUT_DIR = BACKTESTING_DIR / "data/results/hunter_classic_next_tests_downstream_20260502"
REPORT_PATH = BACKTESTING_DIR / "learnings/reports/NQ_HUNTER_CLASSIC_NEXT_TESTS_DOWNSTREAM_20260502.md"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    label: str
    role: str
    params: str


CANDIDATES = (
    Candidate(
        "ema14_tol2_distnone__noTue__1055__rej20__stress",
        "Neutral Reference",
        "balanced stress-gated baseline",
        "EMA14, 2pt tolerance, no distance cap, no Tuesday, 10:55 cutoff, rejection <=20",
    ),
    Candidate(
        "ema14_tol0_distnone__withTue__1055__rej100__stress",
        "10y-Safe Branch",
        "workflow-clean pre-holdout leader",
        "EMA14, 0pt tolerance, no distance cap, Tuesday included, 10:55 cutoff, rejection disabled",
    ),
    Candidate(
        "ema14_tol5_distnone__noTue__1055__rej100__stress",
        "Recent-Strength Branch",
        "best current-regime branch with better long-history twin than rej40",
        "EMA14, 5pt tolerance, no distance cap, no Tuesday, 10:55 cutoff, rejection disabled",
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


def alpha_context(trades: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    alpha = pd.read_csv(ALPHA_DAILY_PATH, index_col=0, parse_dates=True)
    legs = [c for c in alpha.columns if c != "alpha_v1_total"]
    hunter = daily_r(trades)
    start = max(alpha.index.min(), hunter.index.min())
    end = min(alpha.index.max(), hunter.index.max())
    alpha = alpha.loc[(alpha.index >= start) & (alpha.index <= end)].copy()
    hunter = hunter.reindex(alpha.index, fill_value=0.0)
    baseline = alpha[legs].sum(axis=1)
    return alpha, hunter, baseline


def portfolio_rows(candidate: Candidate, trades: pd.DataFrame) -> list[dict[str, object]]:
    alpha, hunter, baseline = alpha_context(trades)
    legs = [c for c in alpha.columns if c != "alpha_v1_total"]
    scenarios = [
        ("ALPHA_V1 baseline", 1.00, 0.00),
        ("+ Hunter 0.25x", 1.00, 0.25),
        ("+ Hunter 0.50x", 1.00, 0.50),
        ("+ Hunter 1.00x", 1.00, 1.00),
        ("ES_NY 0.75x + Hunter 0.25x", 0.75, 0.25),
        ("ES_NY 0.50x + Hunter 0.50x", 0.50, 0.50),
    ]
    rows: list[dict[str, object]] = []
    for scenario, es_ny_scale, hunter_scale in scenarios:
        adjusted = alpha[legs].copy()
        adjusted["es_ny_orb_long"] = adjusted["es_ny_orb_long"] * es_ny_scale
        series = adjusted.sum(axis=1) + hunter * hunter_scale
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "label": candidate.label,
                "scenario": scenario,
                "start": alpha.index.min().date().isoformat(),
                "end": alpha.index.max().date().isoformat(),
                "es_ny_scale": es_ny_scale,
                "hunter_scale": hunter_scale,
                "corr_to_alpha": float(hunter.corr(baseline)) if hunter.std() > 0 and baseline.std() > 0 else 0.0,
                **portfolio_metrics(series),
            }
        )
    return rows


def overlap_rows(candidate: Candidate, trades: pd.DataFrame) -> list[dict[str, object]]:
    alpha, hunter, baseline = alpha_context(trades)
    legs = [c for c in alpha.columns if c != "alpha_v1_total"]
    rows: list[dict[str, object]] = []
    for leg in legs + ["alpha_v1_total"]:
        series = baseline if leg == "alpha_v1_total" else alpha[leg]
        hunter_active = hunter != 0
        leg_active = series != 0
        both_active = hunter_active & leg_active
        both_losing = both_active & (hunter < 0) & (series < 0)
        both_winning = both_active & (hunter > 0) & (series > 0)
        offset_days = both_active & ((hunter > 0) != (series > 0))
        rows.append(
            {
                "candidate_id": candidate.candidate_id,
                "label": candidate.label,
                "leg": leg,
                "corr": float(hunter.corr(series)) if hunter.std() > 0 and series.std() > 0 else 0.0,
                "hunter_active_days": int(hunter_active.sum()),
                "leg_active_days": int(leg_active.sum()),
                "both_active_days": int(both_active.sum()),
                "both_losing_days": int(both_losing.sum()),
                "both_winning_days": int(both_winning.sum()),
                "offset_days": int(offset_days.sum()),
                "avg_combined_r_on_overlap": float((hunter[both_active] + series[both_active]).mean()) if both_active.any() else 0.0,
                "worst_combined_r_on_overlap": float((hunter[both_active] + series[both_active]).min()) if both_active.any() else 0.0,
            }
        )
    return rows


def annual_monthly_rows(candidate: Candidate, trades: pd.DataFrame, windows: dict[str, tuple[pd.Timestamp | None, pd.Timestamp | None]]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    annual_rows: list[dict[str, object]] = []
    monthly_rows: list[dict[str, object]] = []
    for window_name, (start, end) in windows.items():
        subset = filter_window(trades, start, end)
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
    return annual_rows, monthly_rows


def candidate_delta(portfolio: pd.DataFrame, candidate_id: str, scenario: str, field: str) -> float:
    base = portfolio[(portfolio["candidate_id"] == candidate_id) & (portfolio["scenario"] == "ALPHA_V1 baseline")].iloc[0]
    row = portfolio[(portfolio["candidate_id"] == candidate_id) & (portfolio["scenario"] == scenario)].iloc[0]
    return float(row[field] - base[field])


def build_report(
    window_metrics: pd.DataFrame,
    stress_metrics: pd.DataFrame,
    annual: pd.DataFrame,
    monthly: pd.DataFrame,
    mc: pd.DataFrame,
    phase: pd.DataFrame,
    portfolio: pd.DataFrame,
    overlap: pd.DataFrame,
) -> str:
    full = window_metrics[window_metrics["window"] == "full_10y"].copy()
    holdout = window_metrics[window_metrics["window"] == "holdout_2025_plus"].copy()
    last_1 = window_metrics[window_metrics["window"] == "last_1y"].copy()
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

    annual_rows_md = []
    full_annual = annual[annual["window"] == "full_10y"]
    years = sorted(full_annual["year"].unique())
    for year in years:
        row = [str(int(year))]
        for candidate in CANDIDATES:
            sub = full_annual[(full_annual["candidate_id"] == candidate.candidate_id) & (full_annual["year"] == year)]
            row.append(fmt_signed_r(float(sub.iloc[0]["net_r"])) if len(sub) else "+0.0R")
        annual_rows_md.append(row)

    monthly_pain_rows = []
    full_monthly = monthly[monthly["window"] == "full_10y"]
    for candidate in CANDIDATES:
        sub = full_monthly[full_monthly["candidate_id"] == candidate.candidate_id].sort_values("net_r").head(5)
        worst_months = ", ".join(f"{r.month}: {fmt_signed_r(float(r.net_r))}" for r in sub.itertuples(index=False))
        monthly_pain_rows.append([candidate.label, worst_months])

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

    portfolio_rows_md = []
    for _, row in portfolio_focus.iterrows():
        delta_net = candidate_delta(portfolio, row["candidate_id"], row["scenario"], "net_r")
        delta_dd = candidate_delta(portfolio, row["candidate_id"], row["scenario"], "closed_dd_r")
        portfolio_rows_md.append(
            [
                row["label"],
                row["scenario"],
                fmt_signed_r(row["net_r"]),
                fmt_signed_r(row["closed_dd_r"]),
                fmt_signed_r(delta_net),
                fmt_signed_r(delta_dd),
                fmt_signed_r(row["worst_month_r"]),
                fmt_num(row["corr_to_alpha"], 2),
            ]
        )

    overlap_focus = overlap[overlap["leg"].isin(["es_ny_orb_long", "nq_asia_orb_long", "es_asia_orb_long", "nq_ny_lsi_long", "alpha_v1_total"])]
    overlap_rows_md = []
    for _, row in overlap_focus.iterrows():
        overlap_rows_md.append(
            [
                row["label"],
                row["leg"],
                fmt_num(row["corr"], 2),
                str(int(row["both_active_days"])),
                str(int(row["both_losing_days"])),
                str(int(row["offset_days"])),
                fmt_signed_r(row["worst_combined_r_on_overlap"]),
            ]
        )

    return "\n\n".join(
        [
            "# NQ Hunter Classic Next-Tests Downstream Validation (2026-05-02)",
            "## Scope\n\n"
            "This packet validates the three frozen branches selected after `NQ_HUNTER_CLASSIC_NEXT_TESTS_20260502`. "
            "No new parameters are searched. All three keep the stress gate: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`.",
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
            "## Annual Net R\n\n"
            + md_table(
                ["Year"] + [candidate.label for candidate in CANDIDATES],
                annual_rows_md,
            ),
            "## Worst Monthly Pain\n\n"
            + md_table(
                ["Label", "Five Worst Months"],
                monthly_pain_rows,
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
                ["Label", "Scenario", "Net", "DD", "Delta Net", "Delta DD", "Worst Month", "Corr"],
                portfolio_rows_md,
            ),
            "## ALPHA_V1 Leg Overlap\n\n"
            + md_table(
                ["Label", "Leg", "Corr", "Overlap Days", "Both Losing", "Offset Days", "Worst Combined"],
                overlap_rows_md,
            ),
            "## Read\n\n"
            "- The **10y-safe branch** is the best if the priority is long-history durability. It roughly adds `+71R` over the neutral reference full-history, improves DD, and has the best 0.25x full-history payout scorecard, but it gives up recent/current-regime heat.\n"
            "- The **recent-strength branch** is the best if the priority is the current Hunter behavior: strongest 2025+ and last-1y, best recent payout speed, and still improves full-history net versus neutral. Its DD and negative-year profile are weaker, so it should stay a challenger rather than replace the neutral branch outright.\n"
            "- The **neutral reference** remains the best control leg. It has the cleanest interpretation and avoids the Tuesday long-history/current-regime fork.\n"
            "- In ALPHA_V1 portfolio context, adding Hunter at `0.25x` beats risk-down ES NY + Hunter on total R for all three branches. Risking down ES NY improves worst month/DD slightly but gives up too much net.\n"
            "- Correlation remains low to ALPHA_V1 legs. Overlap risk is not zero, but it is not concentrated enough to block a small pilot.",
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
    annual_rows: list[dict[str, object]] = []
    monthly_rows: list[dict[str, object]] = []
    mc_rows = []
    phase_rows = []
    account_detail_frames = []
    portfolio_out = []
    overlap_out = []
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

        a_rows, m_rows = annual_monthly_rows(candidate, trades, windows)
        annual_rows.extend(a_rows)
        monthly_rows.extend(m_rows)

        for scale in (1.0, 0.5, 0.25):
            mc_rows.append(
                {
                    "candidate_id": candidate.candidate_id,
                    "label": candidate.label,
                    **monte_carlo_for(trades, scale, rng),
                }
            )

        portfolio_out.extend(portfolio_rows(candidate, trades))
        overlap_out.extend(overlap_rows(candidate, trades))

    window_metrics = pd.DataFrame(window_rows)
    stress_metrics = pd.DataFrame(stress_rows)
    annual = pd.DataFrame(annual_rows)
    monthly = pd.DataFrame(monthly_rows)
    mc = pd.DataFrame(mc_rows)
    phase = pd.DataFrame(phase_rows)
    portfolio = pd.DataFrame(portfolio_out)
    overlap = pd.DataFrame(overlap_out)
    account_details = pd.concat(account_detail_frames, ignore_index=True) if account_detail_frames else pd.DataFrame()

    window_metrics.to_csv(OUT_DIR / "candidate_window_metrics.csv", index=False)
    stress_metrics.to_csv(OUT_DIR / "rolling_stress_metrics.csv", index=False)
    annual.to_csv(OUT_DIR / "annual_returns.csv", index=False)
    monthly.to_csv(OUT_DIR / "monthly_returns.csv", index=False)
    mc.to_csv(OUT_DIR / "monte_carlo_bootstrap.csv", index=False)
    phase.to_csv(OUT_DIR / "phase_one_scorecard.csv", index=False)
    portfolio.to_csv(OUT_DIR / "portfolio_scenarios.csv", index=False)
    overlap.to_csv(OUT_DIR / "alpha_v1_leg_overlap.csv", index=False)
    account_details.to_csv(OUT_DIR / "phase_one_account_details_025x.csv", index=False)

    summary = {
        "generated_at": "2026-05-02",
        "common_end": common_end.date().isoformat(),
        "last_1y_start": last_1y_start.date().isoformat(),
        "last_2y_start": last_2y_start.date().isoformat(),
        "account_model": {
            "account_size": ACCOUNT_SIZE,
            "trailing_dd_usd": TRAILING_DD_USD,
            "payout_target_balance": PAYOUT_TARGET_BALANCE,
            "first_payout_usd": FIRST_PAYOUT_USD,
            "account_cost_usd": ACCOUNT_COST_USD,
            "base_risk_usd": BASE_RISK_USD,
        },
        "monte_carlo": {"paths": MC_PATHS, "seed": MC_SEED},
        "candidates": [candidate.__dict__ for candidate in CANDIDATES],
        "outputs": sorted(path.name for path in OUT_DIR.iterdir()),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=True) + "\n")

    report = build_report(window_metrics, stress_metrics, annual, monthly, mc, phase, portfolio, overlap)
    REPORT_PATH.write_text(report)
    (OUT_DIR / "summary.md").write_text(report)

    print(f"Wrote results to {OUT_DIR}")
    print(f"Wrote report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
