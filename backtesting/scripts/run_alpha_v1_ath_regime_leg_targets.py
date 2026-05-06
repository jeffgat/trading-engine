#!/usr/bin/env python3
"""Second-pass leg-specific ATH regime research for active ALPHA_V1 legs.

This consumes the point-in-time annotated trade export produced by
run_alpha_v1_ath_regime_first_pass.py.  It deliberately remains a post-filter
research pass: every candidate must be implemented as a live pre-trade gate and
exact-replayed before any deployment decision.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from run_alpha_v1_ath_regime_first_pass import (
    FULL_START,
    WINDOWS,
    _frame_metrics,
    _markdown_table,
    _series_drawdown,
    _series_sharpe,
    _simulate_first_payouts,
    _summarize_payouts,
)


ROOT = Path(__file__).resolve().parent.parent
SOURCE_ANNOTATED = ROOT / "data" / "results" / "alpha_v1_ath_regime_first_pass_20260505" / "annotated_trades.csv"
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_ath_regime_leg_targets_20260505"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ATH_REGIME_LEG_TARGETS_20260505.md"


MaskFn = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class ProfileSpec:
    key: str
    label: str
    thesis: str
    mask_fn: MaskFn
    target_leg: str | None = None
    deployability: str = "post_filter_only"
    live_support_notes: str = (
        "Requires a futures ATH pre-trade gate in the live/exact engine before the order is armed."
    )
    exact_replay_required: str = "yes"


LEG_LABELS = {
    "es_asia_orb": "ES Asia ORB",
    "es_ny_orb": "ES NY ORB",
    "nq_asia_orb": "NQ Asia ORB",
    "nq_ny_htf_lsi": "NQ NY HTF-LSI",
    "portfolio": "Portfolio",
}


def _fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: float | None) -> str:
    if value is None or not math.isfinite(float(value)):
        return "-"
    return f"{100.0 * float(value):.1f}%"


def _load_signal_trades() -> pd.DataFrame:
    trades = pd.read_csv(SOURCE_ANNOTATED)
    signal = trades[trades["context"] == "signal"].copy()
    for col in ("fill_ts", "exit_ts", "fill_time", "exit_time"):
        signal[col] = pd.to_datetime(signal[col])
    signal["exit_day"] = pd.to_datetime(signal["exit_date"])
    return signal.sort_values(["fill_ts", "leg", "leg_trade_ordinal"]).reset_index(drop=True)


def _all(frame: pd.DataFrame) -> pd.Series:
    return pd.Series(True, index=frame.index)


def _keep_leg_buckets(leg: str, buckets: set[str]) -> MaskFn:
    def mask(frame: pd.DataFrame) -> pd.Series:
        return (frame["leg"] != leg) | frame["ath_pct_bucket"].isin(buckets)

    return mask


def _skip_leg_buckets(leg: str, buckets: set[str]) -> MaskFn:
    def mask(frame: pd.DataFrame) -> pd.Series:
        return (frame["leg"] != leg) | ~frame["ath_pct_bucket"].isin(buckets)

    return mask


def _and_masks(*mask_fns: MaskFn) -> MaskFn:
    def mask(frame: pd.DataFrame) -> pd.Series:
        out = pd.Series(True, index=frame.index)
        for mask_fn in mask_fns:
            out &= mask_fn(frame)
        return out

    return mask


def _profiles() -> list[ProfileSpec]:
    return [
        ProfileSpec(
            key="baseline",
            label="No ATH gate",
            thesis="Current active ALPHA_V1 baseline.",
            mask_fn=_all,
            deployability="live_native",
            live_support_notes="Existing active ALPHA_V1 baseline; no ATH gate.",
            exact_replay_required="no",
        ),
        ProfileSpec(
            key="es_asia_near_0_0p5_only",
            label="ES Asia only 0-0.5% below ATH",
            thesis="Test whether ES Asia should become a closest-to-ATH specialist.",
            mask_fn=_keep_leg_buckets("es_asia_orb", {"0-0.5%"}),
            target_leg="es_asia_orb",
        ),
        ProfileSpec(
            key="es_asia_skip_mid_0p5_5",
            label="ES Asia skip 0.5-5% below ATH",
            thesis="Keep ES Asia flow near ATH and far below ATH, skip the low-quality middle bands.",
            mask_fn=_skip_leg_buckets("es_asia_orb", {"0.5-1%", "1-2%", "2-5%"}),
            target_leg="es_asia_orb",
        ),
        ProfileSpec(
            key="nq_lsi_2_5_only",
            label="NQ HTF-LSI only 2-5% below ATH",
            thesis="Test the cleanest HTF-LSI sweet spot from the first pass.",
            mask_fn=_keep_leg_buckets("nq_ny_htf_lsi", {"2-5%"}),
            target_leg="nq_ny_htf_lsi",
        ),
        ProfileSpec(
            key="nq_lsi_1_5_only",
            label="NQ HTF-LSI only 1-5% below ATH",
            thesis="Test whether broadening HTF-LSI to the adjacent strong bucket preserves quality and flow.",
            mask_fn=_keep_leg_buckets("nq_ny_htf_lsi", {"1-2%", "2-5%"}),
            target_leg="nq_ny_htf_lsi",
        ),
        ProfileSpec(
            key="nq_lsi_skip_weak_0p5_1_5_10",
            label="NQ HTF-LSI skip 0.5-1% and 5-10%",
            thesis="Test a surgical HTF-LSI weak-bucket removal without starving the leg.",
            mask_fn=_skip_leg_buckets("nq_ny_htf_lsi", {"0.5-1%", "5-10%"}),
            target_leg="nq_ny_htf_lsi",
        ),
        ProfileSpec(
            key="nq_asia_top3_only",
            label="NQ Asia only 0-0.5%, 1-2%, >10%",
            thesis="Test NQ Asia's strongest bands while avoiding its soft middle.",
            mask_fn=_keep_leg_buckets("nq_asia_orb", {"0-0.5%", "1-2%", ">10%"}),
            target_leg="nq_asia_orb",
        ),
        ProfileSpec(
            key="nq_asia_skip_soft_0p5_1_2_5",
            label="NQ Asia skip 0.5-1% and 2-5%",
            thesis="Test a less restrictive NQ Asia weak-bucket removal.",
            mask_fn=_skip_leg_buckets("nq_asia_orb", {"0.5-1%", "2-5%"}),
            target_leg="nq_asia_orb",
        ),
        ProfileSpec(
            key="es_ny_skip_0p5_1",
            label="ES NY skip 0.5-1% below ATH",
            thesis="Check the other ALPHA_V1 leg's clearly negative ATH dead zone.",
            mask_fn=_skip_leg_buckets("es_ny_orb", {"0.5-1%"}),
            target_leg="es_ny_orb",
        ),
        ProfileSpec(
            key="combo_negative_only_skip",
            label="Combo skip only negative buckets",
            thesis="Remove only the buckets that are negative full-history in their own leg.",
            mask_fn=_and_masks(
                _skip_leg_buckets("es_ny_orb", {"0.5-1%"}),
                _skip_leg_buckets("nq_ny_htf_lsi", {"0.5-1%"}),
            ),
        ),
        ProfileSpec(
            key="combo_surgical_weak_skip",
            label="Combo surgical weak-bucket skip",
            thesis="Combine the most plausible weak-bucket removals while preserving broad portfolio structure.",
            mask_fn=_and_masks(
                _skip_leg_buckets("es_asia_orb", {"0.5-1%"}),
                _skip_leg_buckets("es_ny_orb", {"0.5-1%"}),
                _skip_leg_buckets("nq_asia_orb", {"0.5-1%", "2-5%"}),
                _skip_leg_buckets("nq_ny_htf_lsi", {"0.5-1%", "5-10%"}),
            ),
        ),
    ]


def _window_frame(frame: pd.DataFrame, window: str) -> pd.DataFrame:
    start = WINDOWS[window]
    return frame if start is None else frame[frame["fill_ts"] >= pd.Timestamp(start)]


def _daily_metrics(frame: pd.DataFrame) -> dict[str, float]:
    if frame.empty:
        return {"daily_sharpe": 0.0, "daily_max_dd_r": 0.0, "active_days": 0.0}
    grouped = frame.groupby("exit_day")["r_multiple"].sum().sort_index()
    full_idx = pd.date_range(grouped.index.min(), grouped.index.max(), freq="D")
    daily = grouped.reindex(full_idx, fill_value=0.0)
    return {
        "daily_sharpe": _series_sharpe(daily),
        "daily_max_dd_r": _series_drawdown(daily),
        "active_days": float((daily != 0).sum()),
    }


def _evaluate_profiles(signal: pd.DataFrame, profiles: list[ProfileSpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for window in WINDOWS:
        base_window = _window_frame(signal, window)
        base_metrics = _frame_metrics(base_window)
        base_daily = _daily_metrics(base_window)
        for profile in profiles:
            selected = _window_frame(signal[profile.mask_fn(signal)], window)
            metrics = _frame_metrics(selected)
            daily = _daily_metrics(selected)
            rows.append(
                {
                    "window": window,
                    "profile": profile.key,
                    "label": profile.label,
                    "target_leg": profile.target_leg or "portfolio",
                    "removed_trades": base_metrics["trades"] - metrics["trades"],
                    "removed_r": base_metrics["net_r"] - metrics["net_r"],
                    "net_r_delta": metrics["net_r"] - base_metrics["net_r"],
                    "avg_r_delta": metrics["avg_r"] - base_metrics["avg_r"],
                    "pf_delta": metrics["profit_factor"] - base_metrics["profit_factor"],
                    "max_dd_r_delta": metrics["max_dd_r"] - base_metrics["max_dd_r"],
                    "daily_sharpe_delta": daily["daily_sharpe"] - base_daily["daily_sharpe"],
                    "daily_max_dd_r_delta": daily["daily_max_dd_r"] - base_daily["daily_max_dd_r"],
                    "deployability": profile.deployability,
                    "live_support_notes": profile.live_support_notes,
                    "exact_replay_required": profile.exact_replay_required,
                    **metrics,
                    **daily,
                }
            )
    return pd.DataFrame(rows)


def _leg_impact(signal: pd.DataFrame, profiles: list[ProfileSpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile in profiles:
        selected_all = signal[profile.mask_fn(signal)]
        for window in WINDOWS:
            base_window = _window_frame(signal, window)
            selected_window = _window_frame(selected_all, window)
            for leg in sorted(base_window["leg"].unique()):
                base_leg = base_window[base_window["leg"] == leg]
                selected_leg = selected_window[selected_window["leg"] == leg]
                base_m = _frame_metrics(base_leg)
                selected_m = _frame_metrics(selected_leg)
                rows.append(
                    {
                        "window": window,
                        "profile": profile.key,
                        "leg": leg,
                        "baseline_trades": base_m["trades"],
                        "selected_trades": selected_m["trades"],
                        "removed_trades": base_m["trades"] - selected_m["trades"],
                        "baseline_net_r": base_m["net_r"],
                        "selected_net_r": selected_m["net_r"],
                        "net_r_delta": selected_m["net_r"] - base_m["net_r"],
                        "baseline_avg_r": base_m["avg_r"],
                        "selected_avg_r": selected_m["avg_r"],
                        "avg_r_delta": selected_m["avg_r"] - base_m["avg_r"],
                        "selected_pf": selected_m["profit_factor"],
                        "selected_max_dd_r": selected_m["max_dd_r"],
                    }
                )
    return pd.DataFrame(rows)


def _bucket_thesis(signal: pd.DataFrame, profiles: list[ProfileSpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for profile in profiles:
        if profile.target_leg is None:
            continue
        leg_signal = signal[signal["leg"] == profile.target_leg]
        target_mask = profile.mask_fn(leg_signal)
        for window in WINDOWS:
            leg_window = _window_frame(leg_signal, window)
            target = _window_frame(leg_signal[target_mask], window)
            outside = _window_frame(leg_signal[~target_mask], window)
            base_m = _frame_metrics(leg_window)
            target_m = _frame_metrics(target)
            outside_m = _frame_metrics(outside)
            rows.append(
                {
                    "window": window,
                    "profile": profile.key,
                    "label": profile.label,
                    "leg": profile.target_leg,
                    "baseline_trades": base_m["trades"],
                    "baseline_net_r": base_m["net_r"],
                    "baseline_avg_r": base_m["avg_r"],
                    "target_trades": target_m["trades"],
                    "target_net_r": target_m["net_r"],
                    "target_avg_r": target_m["avg_r"],
                    "target_win_rate": target_m["win_rate"],
                    "target_profit_factor": target_m["profit_factor"],
                    "target_max_dd_r": target_m["max_dd_r"],
                    "outside_trades": outside_m["trades"],
                    "outside_net_r": outside_m["net_r"],
                    "outside_avg_r": outside_m["avg_r"],
                    "outside_profit_factor": outside_m["profit_factor"],
                    "target_avg_delta": target_m["avg_r"] - base_m["avg_r"],
                    "outside_avg_delta": outside_m["avg_r"] - base_m["avg_r"],
                }
            )
    return pd.DataFrame(rows)


def _yearly_profiles(signal: pd.DataFrame, profiles: list[ProfileSpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    signal = signal.copy()
    signal["year"] = signal["exit_day"].dt.year
    base_by_year = {year: _frame_metrics(frame) for year, frame in signal.groupby("year", sort=True)}
    for profile in profiles:
        selected = signal[profile.mask_fn(signal)].copy()
        for year, base_m in base_by_year.items():
            year_selected = selected[selected["year"] == year]
            metrics = _frame_metrics(year_selected)
            rows.append(
                {
                    "year": int(year),
                    "profile": profile.key,
                    "trades": metrics["trades"],
                    "net_r": metrics["net_r"],
                    "avg_r": metrics["avg_r"],
                    "max_dd_r": metrics["max_dd_r"],
                    "baseline_net_r": base_m["net_r"],
                    "net_r_delta": metrics["net_r"] - base_m["net_r"],
                    "max_dd_r_delta": metrics["max_dd_r"] - base_m["max_dd_r"],
                }
            )
    return pd.DataFrame(rows)


def _payout_summary(signal: pd.DataFrame, profiles: list[ProfileSpec]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    max_end = pd.to_datetime(signal["exit_date"]).max().date().isoformat()

    def append_summary(scope: str, leg: str, frame: pd.DataFrame, profile_key: str, window: str) -> None:
        window_start = FULL_START if WINDOWS[window] is None else str(WINDOWS[window])
        outcomes = _simulate_first_payouts(frame, start=window_start, end=max_end, profile=profile_key)
        summary = _summarize_payouts(outcomes, profile=profile_key, window=window)
        rows.append({"scope": scope, "leg": leg, **summary})

    for profile in profiles:
        selected = signal[profile.mask_fn(signal)]
        for window in WINDOWS:
            append_summary("portfolio", "portfolio", selected, profile.key, window)
            if profile.target_leg is not None:
                base_leg = signal[signal["leg"] == profile.target_leg]
                selected_leg = selected[selected["leg"] == profile.target_leg]
                append_summary("target_leg_baseline", profile.target_leg, base_leg, "baseline", window)
                append_summary("target_leg_profile", profile.target_leg, selected_leg, profile.key, window)
    return pd.DataFrame(rows)


def _profile_report_rows(metrics: pd.DataFrame, *, window: str) -> list[dict[str, object]]:
    subset = metrics[metrics["window"] == window].copy()
    subset = subset.sort_values(["net_r_delta", "avg_r_delta"], ascending=[False, False])
    rows: list[dict[str, object]] = []
    for _, row in subset.iterrows():
        rows.append(
            {
                "Profile": row["profile"],
                "Removed": int(row["removed_trades"]),
                "Net R": round(float(row["net_r"]), 1),
                "Delta R": round(float(row["net_r_delta"]), 1),
                "Avg R": round(float(row["avg_r"]), 3),
                "PF": round(float(row["profit_factor"]), 2) if math.isfinite(float(row["profit_factor"])) else "inf",
                "Trade DD": round(float(row["max_dd_r"]), 1),
                "Daily Sh": round(float(row["daily_sharpe"]), 2),
                "Daily DD": round(float(row["daily_max_dd_r"]), 1),
            }
        )
    return rows


def _thesis_report_rows(thesis: pd.DataFrame, *, window: str) -> list[dict[str, object]]:
    subset = thesis[thesis["window"] == window].copy()
    subset = subset.sort_values(["target_avg_delta", "target_trades"], ascending=[False, False])
    rows: list[dict[str, object]] = []
    for _, row in subset.iterrows():
        rows.append(
            {
                "Profile": row["profile"],
                "Leg": LEG_LABELS.get(str(row["leg"]), str(row["leg"])),
                "Base T": int(row["baseline_trades"]),
                "Base R": round(float(row["baseline_net_r"]), 1),
                "Base Avg": round(float(row["baseline_avg_r"]), 3),
                "Target T": int(row["target_trades"]),
                "Target R": round(float(row["target_net_r"]), 1),
                "Target Avg": round(float(row["target_avg_r"]), 3),
                "Target PF": round(float(row["target_profit_factor"]), 2)
                if math.isfinite(float(row["target_profit_factor"]))
                else "inf",
                "Outside R": round(float(row["outside_net_r"]), 1),
                "Outside Avg": round(float(row["outside_avg_r"]), 3),
            }
        )
    return rows


def _payout_report_rows(payout: pd.DataFrame, *, window: str, scope: str) -> list[dict[str, object]]:
    subset = payout[(payout["window"] == window) & (payout["scope"] == scope)].copy()
    if scope == "target_leg_baseline":
        subset = subset.drop_duplicates(subset=["leg", "profile", "window", "scope"])
    rows: list[dict[str, object]] = []
    for _, row in subset.iterrows():
        rows.append(
            {
                "Profile": row["profile"],
                "Leg": LEG_LABELS.get(str(row["leg"]), str(row["leg"])),
                "Accounts": int(row["accounts"]),
                "Pay%": round(float(row["payout_rate_pct"]), 1),
                "Breach%": round(float(row["breach_rate_pct"]), 1),
                "Payouts": int(row["payouts"]),
                "Breaches": int(row["breaches"]),
                "Open": int(row["open"]),
                "EV/acct": round(float(row["ev_per_account_usd"]), 0),
                "Med PayD": None
                if pd.isna(row["median_days_to_payout"])
                else round(float(row["median_days_to_payout"]), 1),
                "MCBch": int(row["max_consecutive_breaches"]),
            }
        )
    return rows


def _yearly_report_rows(yearly: pd.DataFrame, profiles: list[str]) -> list[dict[str, object]]:
    subset = yearly[yearly["profile"].isin(profiles)].copy()
    rows: list[dict[str, object]] = []
    for _, row in subset.sort_values(["profile", "year"]).iterrows():
        rows.append(
            {
                "Profile": row["profile"],
                "Year": int(row["year"]),
                "Net R": round(float(row["net_r"]), 1),
                "Delta R": round(float(row["net_r_delta"]), 1),
                "DD Delta": round(float(row["max_dd_r_delta"]), 1),
            }
        )
    return rows


def _decision_rows(metrics: pd.DataFrame, payout: pd.DataFrame, profiles: list[ProfileSpec]) -> list[dict[str, object]]:
    full = metrics[metrics["window"] == "full"].set_index("profile")
    recent = metrics[metrics["window"] == "2025+"].set_index("profile")
    payout_full = payout[(payout["scope"] == "portfolio") & (payout["window"] == "full")].set_index("profile")
    payout_recent = payout[(payout["scope"] == "portfolio") & (payout["window"] == "2025+")].set_index("profile")
    rows: list[dict[str, object]] = []
    for profile in profiles:
        if profile.key == "baseline":
            continue
        f = full.loc[profile.key]
        r = recent.loc[profile.key]
        pf = payout_full.loc[profile.key]
        pr = payout_recent.loc[profile.key]
        if float(f["net_r_delta"]) >= 0 and float(pf["payout_rate_pct"]) >= float(payout_full.loc["baseline", "payout_rate_pct"]):
            read = "CONDITIONAL research"
        elif float(r["net_r_delta"]) > 0 and float(pr["breach_rate_pct"]) <= float(payout_recent.loc["baseline", "breach_rate_pct"]):
            read = "Recent-only watchlist"
        else:
            read = "NO-GO as broad overlay"
        rows.append(
            {
                "Profile": profile.key,
                "Target": LEG_LABELS.get(profile.target_leg or "portfolio", profile.target_leg or "Portfolio"),
                "Full Delta R": round(float(f["net_r_delta"]), 1),
                "2025+ Delta R": round(float(r["net_r_delta"]), 1),
                "Full Pay%": round(float(pf["payout_rate_pct"]), 1),
                "2025+ Pay%": round(float(pr["payout_rate_pct"]), 1),
                "Decision": read,
                "deployability": profile.deployability,
                "exact_replay_required": profile.exact_replay_required,
            }
        )
    return rows


def _write_report(
    metrics: pd.DataFrame,
    thesis: pd.DataFrame,
    payout: pd.DataFrame,
    yearly: pd.DataFrame,
    profiles: list[ProfileSpec],
) -> None:
    profile_notes = [
        {
            "Profile": profile.key,
            "Target": LEG_LABELS.get(profile.target_leg or "portfolio", profile.target_leg or "Portfolio"),
            "Thesis": profile.thesis,
            "Deploy": profile.deployability,
        }
        for profile in profiles
    ]
    decision_rows = _decision_rows(metrics, payout, profiles)
    interesting_yearly = [
        "nq_lsi_skip_weak_0p5_1_5_10",
        "es_ny_skip_0p5_1",
        "combo_negative_only_skip",
        "combo_surgical_weak_skip",
    ]

    report = f"""# ALPHA_V1 ATH Regime Leg Targets

Date: 2026-05-05

## Scope

- Source: `{SOURCE_ANNOTATED.relative_to(ROOT)}`
- Trade set: active ALPHA_V1 baseline, signal-time ATH features only, futures data only.
- Purpose: test the leg-specific ATH targets suggested by the first pass.
- Status: post-filter research. Any promising row needs a live pre-trade ATH gate and exact replay before promotion.

## Profile Definitions

{_markdown_table(profile_notes, ["Profile", "Target", "Thesis", "Deploy"])}

## Target-Leg Thesis Fit, Full History

This isolates the target leg only. Target = trades that pass that profile's ATH rule; outside = the same leg's removed trades.

{_markdown_table(_thesis_report_rows(thesis, window="full"), ["Profile", "Leg", "Base T", "Base R", "Base Avg", "Target T", "Target R", "Target Avg", "Target PF", "Outside R", "Outside Avg"])}

## Target-Leg Thesis Fit, 2024+

{_markdown_table(_thesis_report_rows(thesis, window="2024+"), ["Profile", "Leg", "Base T", "Base R", "Base Avg", "Target T", "Target R", "Target Avg", "Target PF", "Outside R", "Outside Avg"])}

## Portfolio Overlay Comparison, Full History

{_markdown_table(_profile_report_rows(metrics, window="full"), ["Profile", "Removed", "Net R", "Delta R", "Avg R", "PF", "Trade DD", "Daily Sh", "Daily DD"])}

## Portfolio Overlay Comparison, 2025+

{_markdown_table(_profile_report_rows(metrics, window="2025+"), ["Profile", "Removed", "Net R", "Delta R", "Avg R", "PF", "Trade DD", "Daily Sh", "Daily DD"])}

## Portfolio Funded First-Payout Comparison

Full-history combined-account style comparison, matching the first-pass payout model.

{_markdown_table(_payout_report_rows(payout, window="full", scope="portfolio"), ["Profile", "Leg", "Accounts", "Pay%", "Breach%", "Payouts", "Breaches", "Open", "EV/acct", "Med PayD", "MCBch"])}

## Target-Leg Standalone Funded Comparison, Full History

Because ALPHA_V1 is operated as separate accounts, this compares target-leg baseline accounts against target-leg gated accounts.

{_markdown_table(_payout_report_rows(payout, window="full", scope="target_leg_baseline") + _payout_report_rows(payout, window="full", scope="target_leg_profile"), ["Profile", "Leg", "Accounts", "Pay%", "Breach%", "Payouts", "Breaches", "Open", "EV/acct", "Med PayD", "MCBch"])}

## Decision Table

{_markdown_table(decision_rows, ["Profile", "Target", "Full Delta R", "2025+ Delta R", "Full Pay%", "2025+ Pay%", "Decision", "deployability", "exact_replay_required"])}

## Yearly Stability Snapshot

{_markdown_table(_yearly_report_rows(yearly, interesting_yearly), ["Profile", "Year", "Net R", "Delta R", "DD Delta"])}

## First Read

1. The cleanest next exact-replay candidate is `es_ny_skip_0p5_1`: it removes only `95` ES NY trades, lifts full-history R by `+5.2R`, lifts `2025+` by `+5.6R`, and improves ES NY standalone full-history payouts from `64.2%` to `68.5%`. The recent standalone read is much stronger (`2025+` ES NY baseline `43.8%` payout / `37.5%` breach vs gated `81.2%` payout / `0.0%` breach), but this is still post-filter evidence.
2. `combo_negative_only_skip` is the best portfolio-R overlay (`+6.1R` full history, `+5.6R` in `2025+`), but its full-history combined-account payout rate falls from `73.8%` to `71.9%`. Treat it as a recent-flow watchlist, not a broad promotion.
3. HTF-LSI's `1-5%` and `2-5%` whitelists have excellent trade quality and no standalone first-payout breaches, but they slow payout cadence and reduce portfolio R by `-30.5R` to `-50.5R`. The surgical HTF-LSI skip is safer, but the lift is only `+0.3R` full history and `-2.2R` in `2025+`.
4. ES Asia near-ATH is real as a quality pocket, but not as a replacement gate: `0-0.5%` below ATH produces `0.188R` avg versus `0.103R` baseline, yet removing the rest cuts `-84.8R` from the portfolio and stretches standalone median payout time to `655` days.
5. NQ Asia's top-bucket whitelists improve full-history standalone quality, but fail the recent test (`2025+` loses `-23R` to `-26R`). Do not prioritize NQ Asia ATH gating yet.
6. Treat every non-baseline row as `post_filter_only`; the research gate is causal in principle, but the live/exact engine does not yet compute futures ATH state before arming the order.

## Artifacts

- Profile metrics: `data/results/alpha_v1_ath_regime_leg_targets_20260505/profile_metrics.csv`
- Leg impact: `data/results/alpha_v1_ath_regime_leg_targets_20260505/leg_impact.csv`
- Target thesis table: `data/results/alpha_v1_ath_regime_leg_targets_20260505/target_thesis.csv`
- Yearly profiles: `data/results/alpha_v1_ath_regime_leg_targets_20260505/yearly_profiles.csv`
- Funded payout summary: `data/results/alpha_v1_ath_regime_leg_targets_20260505/funded_first_payout_summary.csv`
- Machine summary: `data/results/alpha_v1_ath_regime_leg_targets_20260505/summary.json`
"""
    REPORT_PATH.write_text(report)


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    profiles = _profiles()
    signal = _load_signal_trades()
    metrics = _evaluate_profiles(signal, profiles)
    leg_impact = _leg_impact(signal, profiles)
    thesis = _bucket_thesis(signal, profiles)
    yearly = _yearly_profiles(signal, profiles)
    payout = _payout_summary(signal, profiles)

    metrics.to_csv(RESULT_DIR / "profile_metrics.csv", index=False)
    leg_impact.to_csv(RESULT_DIR / "leg_impact.csv", index=False)
    thesis.to_csv(RESULT_DIR / "target_thesis.csv", index=False)
    yearly.to_csv(RESULT_DIR / "yearly_profiles.csv", index=False)
    payout.to_csv(RESULT_DIR / "funded_first_payout_summary.csv", index=False)

    payload = {
        "source_annotated": str(SOURCE_ANNOTATED.relative_to(ROOT)),
        "report": str(REPORT_PATH.relative_to(ROOT)),
        "result_dir": str(RESULT_DIR.relative_to(ROOT)),
        "trade_rows": int(len(signal)),
        "profiles": [
            {
                "key": profile.key,
                "label": profile.label,
                "target_leg": profile.target_leg,
                "deployability": profile.deployability,
                "exact_replay_required": profile.exact_replay_required,
            }
            for profile in profiles
        ],
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2))
    _write_report(metrics, thesis, payout, yearly, profiles)

    best_full = metrics[(metrics["window"] == "full") & (metrics["profile"] != "baseline")].sort_values(
        ["net_r_delta", "avg_r_delta"], ascending=[False, False]
    ).iloc[0]
    print("ALPHA_V1 ATH leg-target pass complete")
    print(
        f"Best full-history overlay: {best_full['profile']} | "
        f"Delta R {best_full['net_r_delta']:.1f} | Avg R {best_full['avg_r']:.3f}"
    )
    print(f"Report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
