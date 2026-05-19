#!/usr/bin/env python3
"""No-fetch stress test for the NQ NY LSI 3m trapped-reversal survivor."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_ny_lsi_3m_trapped_reversal_stress_20260515"
DEFAULT_INPUT_PATH = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_sweep_reclaim_velocity_20260515"
    / "trade_risk_tier_replay.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = (
    ROOT
    / "learnings"
    / "reports"
    / "NQ_NY_LSI_3M_TRAPPED_REVERSAL_STRESS_20260515.md"
)

CANDIDATE = "add_3m_hourly_atr12p5_b3_a7p5"
FEATURE = "trapped_reversal_confirm_score"
TICK_SIZE = 0.25
SLIPPAGE_TICKS_PER_SIDE = (0.0, 0.5, 1.0, 2.0)
PROFILES = ("tier_0p5_1_1p5", "tier_0p75_1_1p25", "tier_0_1_1p5")
PAYOUT_R = 5.0
BREACH_R = -4.0
DAILY_LOSS_R = -2.0
CYCLE_DAYS = 14
MIN_TRADING_DAYS = 5
BOOTSTRAP_RUNS = 5000

WINDOWS = {
    "full": ("2016-01-01", "2026-05-02"),
    "pre_holdout": ("2016-01-01", "2025-04-01"),
    "validation": ("2023-01-01", "2025-04-01"),
    "holdout": ("2025-04-01", "2026-05-02"),
    "post_2023": ("2023-01-01", "2026-05-02"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-path", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def _profile_label(profile: str) -> str:
    return profile.replace("tier_", "").replace("p", ".").replace("_", "/")


def r_metrics(values: pd.Series | np.ndarray | list[float]) -> dict[str, float | int]:
    r = np.asarray(pd.Series(values).dropna(), dtype=float)
    if len(r) == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "max_dd_r": 0.0,
            "profit_factor": 0.0,
            "calmar": 0.0,
            "max_consec_losses": 0,
        }

    wins = r > 0.0
    losses = r < 0.0
    gross_win = float(r[wins].sum()) if wins.any() else 0.0
    gross_loss = float(r[losses].sum()) if losses.any() else 0.0
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak

    current_losses = 0
    max_losses = 0
    for value in r:
        if value < 0.0:
            current_losses += 1
            max_losses = max(max_losses, current_losses)
        else:
            current_losses = 0

    total = float(equity[-1])
    max_dd = float(dd.min()) if len(dd) else 0.0
    return {
        "trades": int(len(r)),
        "win_rate": float(wins.mean()),
        "total_r": total,
        "avg_r": float(r.mean()),
        "max_dd_r": max_dd,
        "profit_factor": abs(gross_win / gross_loss) if gross_loss else 0.0,
        "calmar": total / abs(max_dd) if max_dd else 0.0,
        "max_consec_losses": int(max_losses),
    }


def load_input(path: Path) -> pd.DataFrame:
    data = pd.read_csv(path)
    data = data[
        (data["candidate"] == CANDIDATE)
        & (data["feature"] == FEATURE)
        & (data["weight_profile"].isin(PROFILES))
    ].copy()
    if data.empty:
        raise RuntimeError(f"No rows found for {CANDIDATE} / {FEATURE} in {path}")

    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date.astype(str)
    data["signal_ts"] = pd.to_datetime(data["signal_start"], errors="coerce")
    data["month"] = data["signal_ts"].dt.to_period("M").astype(str)
    for column in ("r_multiple", "risk_points", "risk_weight", "weighted_r", "feature_value"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["active_trade"] = data["active_trade"].astype(str).str.lower().isin({"true", "1", "yes"})
    data = data.dropna(subset=["date", "signal_ts", "r_multiple", "risk_points", "risk_weight"])
    return data.sort_values(["signal_ts", "weight_profile"]).reset_index(drop=True)


def slippage_adjusted_r(frame: pd.DataFrame, ticks_per_side: float) -> pd.Series:
    round_trip_points = 2.0 * ticks_per_side * TICK_SIZE
    risk_points = frame["risk_points"].replace(0.0, np.nan)
    return frame["r_multiple"] - (round_trip_points / risk_points).fillna(0.0)


def build_stressed_trades(data: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile, profile_df in data.groupby("weight_profile", sort=False):
        for ticks in SLIPPAGE_TICKS_PER_SIDE:
            base_r = slippage_adjusted_r(profile_df, ticks)
            for mode in ("baseline", "tiered"):
                for idx, row in profile_df.iterrows():
                    active = bool(row["active_trade"]) if mode == "tiered" else True
                    risk_weight = float(row["risk_weight"]) if mode == "tiered" else 1.0
                    stressed_r = float(base_r.loc[idx]) * risk_weight if active else 0.0
                    rows.append(
                        {
                            "profile": profile,
                            "profile_label": _profile_label(profile),
                            "mode": mode,
                            "slippage_ticks_per_side": float(ticks),
                            "active_trade": active,
                            "risk_weight": risk_weight,
                            "stressed_r": stressed_r,
                            "base_r_after_slippage": float(base_r.loc[idx]),
                            "r_multiple": float(row["r_multiple"]),
                            "risk_points": float(row["risk_points"]),
                            "date": row["date"],
                            "signal_ts": row["signal_ts"],
                            "month": row["month"],
                            "feature_tier": row["feature_tier"],
                            "feature_value": float(row["feature_value"]),
                            "direction": int(row["direction"]),
                            "confirmation": row["confirmation"],
                            "trade_uid": row["trade_uid"],
                        }
                    )
    return pd.DataFrame(rows)


def _window_mask(frame: pd.DataFrame, start: str, end: str) -> pd.Series:
    return (frame["date"] >= start) & (frame["date"] < end)


def build_metric_tables(stressed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    tier_rows: list[dict[str, Any]] = []
    monthly_rows: list[dict[str, Any]] = []

    keys = ["profile", "profile_label", "mode", "slippage_ticks_per_side"]
    for key_values, group in stressed.groupby(keys, sort=False):
        profile, profile_label, mode, ticks = key_values
        active_group = group[group["active_trade"]].copy()
        for window, (start, end) in WINDOWS.items():
            subset = active_group[_window_mask(active_group, start, end)]
            row = {
                "profile": profile,
                "profile_label": profile_label,
                "mode": mode,
                "slippage_ticks_per_side": ticks,
                "window": window,
                "start": start,
                "end": end,
                "avg_risk_weight": float(subset["risk_weight"].mean()) if len(subset) else 0.0,
                "active_rate": float(len(subset) / max(len(group[_window_mask(group, start, end)]), 1)),
            }
            row.update(r_metrics(subset["stressed_r"]))
            rows.append(row)

            for tier, tier_df in subset.groupby("feature_tier", sort=False):
                tier_row = {
                    "profile": profile,
                    "profile_label": profile_label,
                    "mode": mode,
                    "slippage_ticks_per_side": ticks,
                    "window": window,
                    "feature_tier": tier,
                    "avg_risk_weight": float(tier_df["risk_weight"].mean()) if len(tier_df) else 0.0,
                }
                tier_row.update(r_metrics(tier_df["stressed_r"]))
                tier_rows.append(tier_row)

            for month, month_df in subset.groupby("month", sort=True):
                monthly_rows.append(
                    {
                        "profile": profile,
                        "profile_label": profile_label,
                        "mode": mode,
                        "slippage_ticks_per_side": ticks,
                        "window": window,
                        "month": month,
                        **r_metrics(month_df["stressed_r"]),
                    }
                )

    metrics = pd.DataFrame(rows)
    tiers = pd.DataFrame(tier_rows)
    monthly = pd.DataFrame(monthly_rows)

    if not metrics.empty:
        compare_keys = ["profile", "profile_label", "slippage_ticks_per_side", "window"]
        baseline = metrics[metrics["mode"] == "baseline"][
            compare_keys + ["total_r", "avg_r", "max_dd_r", "profit_factor", "calmar", "trades"]
        ].copy()
        tiered = metrics["mode"] == "tiered"
        merged = metrics[tiered].merge(
            baseline,
            on=compare_keys,
            how="left",
            suffixes=("", "_baseline"),
        )
        for _, row in merged.iterrows():
            mask = (
                (metrics["profile"] == row["profile"])
                & (metrics["slippage_ticks_per_side"] == row["slippage_ticks_per_side"])
                & (metrics["window"] == row["window"])
                & (metrics["mode"] == "tiered")
            )
            for metric in ("total_r", "avg_r", "max_dd_r", "profit_factor", "calmar"):
                metrics.loc[mask, f"delta_{metric}"] = row[metric] - row[f"{metric}_baseline"]
            metrics.loc[mask, "baseline_trades"] = row["trades_baseline"]

    return metrics, tiers, monthly


def simulate_accounts(
    trades: pd.DataFrame,
    *,
    start: str,
    end: str,
    daily_loss: bool,
    min_trading_days: bool,
) -> tuple[dict[str, Any], pd.DataFrame]:
    eligible = trades[
        (trades["date"] >= start)
        & (trades["date"] < end)
        & (trades["active_trade"])
    ].sort_values(["signal_ts", "trade_uid"]).copy()
    if eligible.empty:
        return {
            "accounts": 0,
            "payouts": 0,
            "breaches": 0,
            "open": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "ev_r": 0.0,
            "avg_days_payout": 0.0,
            "avg_days_breach": 0.0,
            "avg_trades_payout": 0.0,
            "avg_trades_breach": 0.0,
            "max_consec_breaches": 0,
        }, pd.DataFrame()

    trade_rows = [
        {
            "date": pd.Timestamp(row.date).date(),
            "signal_ts": row.signal_ts,
            "r": float(row.stressed_r),
        }
        for row in eligible.itertuples(index=False)
    ]

    d_start = pd.Timestamp(start).date()
    d_end = pd.Timestamp(end).date()
    account_starts = []
    current = d_start
    while current <= d_end:
        account_starts.append(current)
        current += pd.Timedelta(days=CYCLE_DAYS).to_pytimedelta()

    outcomes = []
    for account_start in account_starts:
        cum_r = 0.0
        day_r = 0.0
        current_day = None
        blocked_day = None
        outcome = "open"
        outcome_date = account_start
        trades_taken = 0
        traded_days: set[Any] = set()

        for trade in trade_rows:
            if trade["date"] < account_start:
                continue
            if blocked_day == trade["date"]:
                continue
            if current_day != trade["date"]:
                current_day = trade["date"]
                day_r = 0.0

            cum_r += trade["r"]
            day_r += trade["r"]
            trades_taken += 1
            outcome_date = trade["date"]
            traded_days.add(trade["date"])

            if cum_r <= BREACH_R:
                outcome = "breach"
                break
            if daily_loss and day_r <= DAILY_LOSS_R:
                blocked_day = trade["date"]
            if cum_r >= PAYOUT_R and (
                not min_trading_days or len(traded_days) >= MIN_TRADING_DAYS
            ):
                outcome = "payout"
                break

        outcomes.append(
            {
                "account_start": account_start.isoformat(),
                "outcome": outcome,
                "final_r": float(cum_r),
                "trades_taken": int(trades_taken),
                "trading_days": int(len(traded_days)),
                "calendar_days": int((outcome_date - account_start).days + 1),
            }
        )

    out = pd.DataFrame(outcomes)
    payouts = out[out["outcome"] == "payout"]
    breaches = out[out["outcome"] == "breach"]
    opens = out[out["outcome"] == "open"]
    capped = np.where(
        out["outcome"].eq("payout"),
        PAYOUT_R,
        np.where(out["outcome"].eq("breach"), BREACH_R, out["final_r"]),
    )

    consec = 0
    max_consec = 0
    for outcome in out["outcome"]:
        if outcome == "breach":
            consec += 1
            max_consec = max(max_consec, consec)
        elif outcome == "payout":
            consec = 0

    return {
        "accounts": int(len(out)),
        "payouts": int(len(payouts)),
        "breaches": int(len(breaches)),
        "open": int(len(opens)),
        "payout_rate": float(len(payouts) / len(out)) if len(out) else 0.0,
        "breach_rate": float(len(breaches) / len(out)) if len(out) else 0.0,
        "ev_r": float(np.mean(capped)) if len(capped) else 0.0,
        "avg_days_payout": float(payouts["calendar_days"].mean()) if len(payouts) else 0.0,
        "avg_days_breach": float(breaches["calendar_days"].mean()) if len(breaches) else 0.0,
        "avg_trades_payout": float(payouts["trades_taken"].mean()) if len(payouts) else 0.0,
        "avg_trades_breach": float(breaches["trades_taken"].mean()) if len(breaches) else 0.0,
        "max_consec_breaches": int(max_consec),
    }, out


def build_account_tables(stressed: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, Any]] = []
    outcome_frames: list[pd.DataFrame] = []

    account_modes = (
        ("basic", False, False),
        ("daily_stop", True, False),
        ("daily_stop_min5days", True, True),
    )
    keys = ["profile", "profile_label", "mode", "slippage_ticks_per_side"]
    for key_values, group in stressed.groupby(keys, sort=False):
        profile, profile_label, sizing_mode, ticks = key_values
        for window in ("post_2023", "holdout"):
            start, end = WINDOWS[window]
            for account_mode, daily_loss, min_days in account_modes:
                result, outcomes = simulate_accounts(
                    group,
                    start=start,
                    end=end,
                    daily_loss=daily_loss,
                    min_trading_days=min_days,
                )
                row = {
                    "profile": profile,
                    "profile_label": profile_label,
                    "mode": sizing_mode,
                    "slippage_ticks_per_side": ticks,
                    "window": window,
                    "account_mode": account_mode,
                    "daily_loss_r": DAILY_LOSS_R if daily_loss else 0.0,
                    "min_trading_days": MIN_TRADING_DAYS if min_days else 0,
                }
                row.update(result)
                summary_rows.append(row)
                if not outcomes.empty:
                    outcomes = outcomes.assign(
                        profile=profile,
                        profile_label=profile_label,
                        mode=sizing_mode,
                        slippage_ticks_per_side=ticks,
                        window=window,
                        account_mode=account_mode,
                    )
                    outcome_frames.append(outcomes)

    summary = pd.DataFrame(summary_rows)
    outcomes = pd.concat(outcome_frames, ignore_index=True) if outcome_frames else pd.DataFrame()
    if not summary.empty:
        compare_keys = ["profile", "profile_label", "slippage_ticks_per_side", "window", "account_mode"]
        baseline = summary[summary["mode"] == "baseline"][
            compare_keys + ["payout_rate", "breach_rate", "ev_r"]
        ].copy()
        merged = summary[summary["mode"] == "tiered"].merge(
            baseline,
            on=compare_keys,
            how="left",
            suffixes=("", "_baseline"),
        )
        for _, row in merged.iterrows():
            mask = (
                (summary["profile"] == row["profile"])
                & (summary["slippage_ticks_per_side"] == row["slippage_ticks_per_side"])
                & (summary["window"] == row["window"])
                & (summary["account_mode"] == row["account_mode"])
                & (summary["mode"] == "tiered")
            )
            summary.loc[mask, "delta_payout_rate"] = row["payout_rate"] - row["payout_rate_baseline"]
            summary.loc[mask, "delta_breach_rate"] = row["breach_rate"] - row["breach_rate_baseline"]
            summary.loc[mask, "delta_ev_r"] = row["ev_r"] - row["ev_r_baseline"]
    return summary, outcomes


def max_drawdown(values: np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    equity = np.cumsum(values)
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def bootstrap_summary(stressed: pd.DataFrame) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    rows: list[dict[str, Any]] = []
    keys = ["profile", "profile_label", "mode", "slippage_ticks_per_side"]
    for key_values, group in stressed.groupby(keys, sort=False):
        profile, profile_label, mode, ticks = key_values
        active_group = group[group["active_trade"]]
        for window in ("post_2023", "holdout"):
            start, end = WINDOWS[window]
            values = active_group[_window_mask(active_group, start, end)]["stressed_r"].to_numpy(float)
            if len(values) == 0:
                continue
            totals = np.empty(BOOTSTRAP_RUNS)
            dds = np.empty(BOOTSTRAP_RUNS)
            for i in range(BOOTSTRAP_RUNS):
                sample = rng.choice(values, size=len(values), replace=True)
                totals[i] = float(sample.sum())
                dds[i] = max_drawdown(sample)
            rows.append(
                {
                    "profile": profile,
                    "profile_label": profile_label,
                    "mode": mode,
                    "slippage_ticks_per_side": ticks,
                    "window": window,
                    "trades": int(len(values)),
                    "runs": BOOTSTRAP_RUNS,
                    "total_r_p05": float(np.quantile(totals, 0.05)),
                    "total_r_p50": float(np.quantile(totals, 0.50)),
                    "total_r_p95": float(np.quantile(totals, 0.95)),
                    "max_dd_r_p05": float(np.quantile(dds, 0.05)),
                    "max_dd_r_p50": float(np.quantile(dds, 0.50)),
                    "prob_total_r_positive": float(np.mean(totals > 0.0)),
                    "prob_max_dd_worse_than_4r": float(np.mean(dds <= -4.0)),
                }
            )
    return pd.DataFrame(rows)


def write_report(
    report_path: Path,
    *,
    metrics: pd.DataFrame,
    account_summary: pd.DataFrame,
    tiers: pd.DataFrame,
    bootstrap: pd.DataFrame,
    output_dir: Path,
) -> None:
    account_focus = account_summary[
        (account_summary["mode"] == "tiered")
        & (account_summary["account_mode"] == "daily_stop_min5days")
        & (account_summary["slippage_ticks_per_side"] == 1.0)
    ].sort_values(["window", "delta_ev_r", "ev_r"], ascending=[True, False, False])

    r_focus = metrics[
        (metrics["mode"] == "tiered")
        & (metrics["slippage_ticks_per_side"].isin((0.0, 1.0)))
        & (metrics["window"].isin(("validation", "holdout", "post_2023")))
    ].sort_values(["window", "slippage_ticks_per_side", "delta_total_r"], ascending=[True, True, False])

    tier_focus = tiers[
        (tiers["mode"] == "tiered")
        & (tiers["profile"] == "tier_0p75_1_1p25")
        & (tiers["slippage_ticks_per_side"] == 1.0)
        & (tiers["window"].isin(("validation", "holdout")))
    ].sort_values(["window", "feature_tier"])

    boot_focus = bootstrap[
        (bootstrap["mode"] == "tiered")
        & (bootstrap["slippage_ticks_per_side"] == 1.0)
        & (bootstrap["window"].isin(("post_2023", "holdout")))
    ].sort_values(["window", "prob_total_r_positive"], ascending=[True, False])

    lines = [
        "# NQ NY LSI 3m Trapped-Reversal Stress",
        "",
        "- Objective: push the no-extra-fetch `3m` trapped-reversal survivor through stricter execution-cost, account-rule, tier, monthly, and bootstrap tests.",
        f"- Candidate: `{CANDIDATE}`",
        f"- Feature: `{FEATURE}`",
        "- Scope: research-engine trade replay using already-created local CSVs. No DataBento fetch. This is not full live-engine parity because the live LSI engine does not yet model this candidate's `inversion_or_cisd` confirmation plus `atr_pct` stop exactly.",
        "",
        "## Account Stress, 1 Tick/Side Slippage",
        "",
        f"Account rules here: stagger every `{CYCLE_DAYS}` calendar days, payout `+{PAYOUT_R:.0f}R`, breach `{BREACH_R:.0f}R`, daily stop `{DAILY_LOSS_R:.0f}R`, minimum `{MIN_TRADING_DAYS}` trading days before payout.",
        "",
        "| Window | Profile | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in account_focus.iterrows():
        lines.append(
            f"| {row['window']} | `{row['profile_label']}` | "
            f"{row['payout_rate']:.1%} | {row['breach_rate']:.1%} | {row['ev_r']:.2f}R | "
            f"{row.get('delta_ev_r', 0.0):+.2f}R | {row.get('delta_payout_rate', 0.0):+.1%} | "
            f"{row.get('delta_breach_rate', 0.0):+.1%} |"
        )

    lines.extend(
        [
            "",
            "## R-Multiple Stress",
            "",
            "| Window | Slip | Profile | Trades | Total R | Avg R | PF | Max DD | Delta Total R |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in r_focus.iterrows():
        lines.append(
            f"| {row['window']} | {row['slippage_ticks_per_side']:.1f} | `{row['profile_label']}` | "
            f"{int(row['trades'])} | {row['total_r']:.2f} | {row['avg_r']:.3f} | "
            f"{row['profit_factor']:.2f} | {row['max_dd_r']:.2f}R | "
            f"{row.get('delta_total_r', 0.0):+.2f}R |"
        )

    lines.extend(
        [
            "",
            "## Conservative Tier Quality",
            "",
            "| Window | Tier | Trades | Avg Weight | Total R | Avg R | PF |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in tier_focus.iterrows():
        lines.append(
            f"| {row['window']} | `{row['feature_tier']}` | {int(row['trades'])} | "
            f"{row['avg_risk_weight']:.2f} | {row['total_r']:.2f} | {row['avg_r']:.3f} | "
            f"{row['profit_factor']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Bootstrap Fragility, 1 Tick/Side Slippage",
            "",
            "| Window | Profile | Trades | P05 Total R | P50 Total R | P95 Total R | Prob Positive | Prob DD <= -4R |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in boot_focus.iterrows():
        lines.append(
            f"| {row['window']} | `{row['profile_label']}` | {int(row['trades'])} | "
            f"{row['total_r_p05']:.2f} | {row['total_r_p50']:.2f} | {row['total_r_p95']:.2f} | "
            f"{row['prob_total_r_positive']:.1%} | {row['prob_max_dd_worse_than_4r']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- The live execution engine needs a separate parity task before this can be called production-exact.",
            "- For current no-fetch research, prefer the conservative `0.75/1/1.25` profile unless the account stress clearly rewards a more aggressive profile after slippage.",
            "- The `0/1/1.5` skip-weak profile is useful as a fragility test; it should not be promoted unless it survives holdout account behavior after slippage.",
            "",
            "## Output Files",
            "",
            f"- `{output_dir / 'stress_trades.csv'}`",
            f"- `{output_dir / 'stress_metrics.csv'}`",
            f"- `{output_dir / 'tier_metrics.csv'}`",
            f"- `{output_dir / 'monthly_metrics.csv'}`",
            f"- `{output_dir / 'account_summary.csv'}`",
            f"- `{output_dir / 'account_outcomes.csv'}`",
            f"- `{output_dir / 'bootstrap_summary.csv'}`",
            f"- `{output_dir / 'summary.json'}`",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    data = load_input(args.input_path)
    stressed = build_stressed_trades(data)
    metrics, tiers, monthly = build_metric_tables(stressed)
    account_summary, account_outcomes = build_account_tables(stressed)
    bootstrap = bootstrap_summary(stressed)

    stressed_path = args.output_dir / "stress_trades.csv"
    metrics_path = args.output_dir / "stress_metrics.csv"
    tiers_path = args.output_dir / "tier_metrics.csv"
    monthly_path = args.output_dir / "monthly_metrics.csv"
    account_summary_path = args.output_dir / "account_summary.csv"
    account_outcomes_path = args.output_dir / "account_outcomes.csv"
    bootstrap_path = args.output_dir / "bootstrap_summary.csv"

    stressed.to_csv(stressed_path, index=False)
    metrics.to_csv(metrics_path, index=False)
    tiers.to_csv(tiers_path, index=False)
    monthly.to_csv(monthly_path, index=False)
    account_summary.to_csv(account_summary_path, index=False)
    account_outcomes.to_csv(account_outcomes_path, index=False)
    bootstrap.to_csv(bootstrap_path, index=False)

    write_report(
        args.report_path,
        metrics=metrics,
        account_summary=account_summary,
        tiers=tiers,
        bootstrap=bootstrap,
        output_dir=args.output_dir,
    )
    save_json(
        args.output_dir / "summary.json",
        {
            "run_slug": RUN_SLUG,
            "candidate": CANDIDATE,
            "feature": FEATURE,
            "input_path": str(args.input_path),
            "slippage_ticks_per_side": SLIPPAGE_TICKS_PER_SIDE,
            "account_rules": {
                "payout_r": PAYOUT_R,
                "breach_r": BREACH_R,
                "daily_loss_r": DAILY_LOSS_R,
                "cycle_days": CYCLE_DAYS,
                "min_trading_days": MIN_TRADING_DAYS,
            },
            "bootstrap_runs": BOOTSTRAP_RUNS,
            "outputs": {
                "stress_trades": str(stressed_path),
                "stress_metrics": str(metrics_path),
                "tier_metrics": str(tiers_path),
                "monthly_metrics": str(monthly_path),
                "account_summary": str(account_summary_path),
                "account_outcomes": str(account_outcomes_path),
                "bootstrap_summary": str(bootstrap_path),
                "report": str(args.report_path),
            },
        },
    )
    print(f"Wrote {metrics_path}", flush=True)
    print(f"Wrote {account_summary_path}", flush=True)
    print(f"Wrote {args.report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
