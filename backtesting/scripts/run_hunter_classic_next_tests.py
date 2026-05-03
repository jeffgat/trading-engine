#!/usr/bin/env python3
"""Workflow-clean Hunter Classic follow-up tests.

This grid continues from the stress-gated balanced Hunter candidate and focuses
on the three strongest ablation follow-ups:

- signal cutoff: 10:55 vs 13:00
- rejection wick filter: 20 vs relaxed 40 vs disabled 100
- Tuesday exclusion: keep excluded vs include Tuesday

Stress gate stays on for the main ranking. A few no-gate rows are included only
as context; they are excluded from promotion leaderboards.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_hunter_classic_ablation import (  # noqa: E402
    BASELINE_ID,
    DATA_1S,
    FULL_END,
    FULL_START,
    HOLDOUT_START,
    LAST_1Y_START,
    LOAD_END,
    REGIME_CALENDAR,
    RISK_USD,
    AblationConfig,
    build_broad_candidates,
    filter_candidates,
    filter_stress_gate,
    fmt_pct,
    fmt_r,
    load_1s,
    load_regime_lookup,
    max_drawdown,
    metric_packet,
    profit_factor,
    resample_5m,
    score,
    select_trades,
    trade_date,
    trade_r,
    write_csv,
)


RESULT_DIR = Path("data/results/hunter_classic_next_tests_20260502")
REPORT_PATH = Path("learnings/reports/NQ_HUNTER_CLASSIC_NEXT_TESTS_20260502.md")

BASE_PROFILE = "ema14_tol2_distnone"
BASE_WEEKDAY = "noTue"
BASE_SIGNAL = "1055"
BASE_REJECTION = "rej20"

STRESS_GATE_LABEL = "stress"
NO_GATE_LABEL = "nogate"


def next_test_configs() -> list[AblationConfig]:
    """Build the main stress-gated grid plus a few no-gate context rows."""

    base = AblationConfig(
        variant_id=BASELINE_ID,
        label="Baseline balanced",
        category="baseline",
        description="Stress-gated EMA14/tol2 no-cap, no Tuesday, 10:55 signal cutoff, rejection <=20.",
        allowed_weekdays=frozenset({0, 2, 3, 4}),
        signal_end="10:55",
        ema_enabled=True,
        ema_length=14,
        ema_tolerance_points=2.0,
        ema_max_distance=None,
        rejection_max_pct=20.0,
        stress_gate=True,
    )

    ema_profiles: list[tuple[str, int, float, float | None]] = [
        ("ema14_tol2_distnone", 14, 2.0, None),
        ("ema14_tol0_distnone", 14, 0.0, None),
        ("ema14_tol5_distnone", 14, 5.0, None),
        ("ema14_tol2_dist150", 14, 2.0, 150.0),
        ("ema10_tol0_dist150", 10, 0.0, 150.0),
    ]
    signal_ends = [("1055", "10:55"), ("1300", "13:00")]
    rejection_profiles = [("rej20", 20.0), ("rej40", 40.0), ("rej100", 100.0)]
    weekdays = [
        ("noTue", frozenset({0, 2, 3, 4})),
        ("withTue", frozenset({0, 1, 2, 3, 4})),
    ]

    configs: list[AblationConfig] = []
    for ema_name, ema_len, ema_tol, ema_cap in ema_profiles:
        for signal_name, signal_end in signal_ends:
            for rejection_name, rejection_max in rejection_profiles:
                for weekday_name, allowed_weekdays in weekdays:
                    variant_id = "__".join(
                        [
                            ema_name,
                            weekday_name,
                            signal_name,
                            rejection_name,
                            STRESS_GATE_LABEL,
                        ]
                    )
                    configs.append(
                        replace(
                            base,
                            variant_id=variant_id,
                            label=variant_id,
                            category="main_grid",
                            description=(
                                f"{ema_name}; {weekday_name}; signal_end={signal_end}; "
                                f"rejection_max={rejection_max:g}; stress gate on"
                            ),
                            allowed_weekdays=allowed_weekdays,
                            signal_end=signal_end,
                            ema_length=ema_len,
                            ema_tolerance_points=ema_tol,
                            ema_max_distance=ema_cap,
                            rejection_max_pct=rejection_max,
                            stress_gate=True,
                        )
                    )

    # A small no-gate context panel. These are not used for promotion rankings.
    context_specs = [
        ("ema14_tol2_distnone", 14, 2.0, None, "noTue", frozenset({0, 2, 3, 4}), "1055", "10:55", "rej20", 20.0),
        ("ema14_tol2_distnone", 14, 2.0, None, "noTue", frozenset({0, 2, 3, 4}), "1300", "13:00", "rej20", 20.0),
        ("ema14_tol2_distnone", 14, 2.0, None, "noTue", frozenset({0, 2, 3, 4}), "1300", "13:00", "rej100", 100.0),
        ("ema14_tol2_distnone", 14, 2.0, None, "withTue", frozenset({0, 1, 2, 3, 4}), "1300", "13:00", "rej100", 100.0),
    ]
    for ema_name, ema_len, ema_tol, ema_cap, weekday_name, allowed_weekdays, signal_name, signal_end, rejection_name, rejection_max in context_specs:
        variant_id = "__".join([ema_name, weekday_name, signal_name, rejection_name, NO_GATE_LABEL])
        configs.append(
            replace(
                base,
                variant_id=variant_id,
                label=variant_id,
                category="context_no_gate",
                description=(
                    f"No-gate context: {ema_name}; {weekday_name}; signal_end={signal_end}; "
                    f"rejection_max={rejection_max:g}"
                ),
                allowed_weekdays=allowed_weekdays,
                signal_end=signal_end,
                ema_length=ema_len,
                ema_tolerance_points=ema_tol,
                ema_max_distance=ema_cap,
                rejection_max_pct=rejection_max,
                stress_gate=False,
            )
        )

    return configs


WINDOWS: dict[str, tuple[pd.Timestamp, pd.Timestamp]] = {
    "pre_holdout": (FULL_START, HOLDOUT_START - pd.Timedelta(days=1)),
    "full_10y": (FULL_START, FULL_END),
    "since_2024": (pd.Timestamp("2024-01-01"), FULL_END),
    "since_2025": (HOLDOUT_START, FULL_END),
    "last_1y": (LAST_1Y_START, FULL_END),
}


def parse_variant_id(variant_id: str) -> dict[str, Any]:
    parts = variant_id.split("__")
    if variant_id == BASELINE_ID:
        return {
            "ema_profile": BASE_PROFILE,
            "weekday_profile": BASE_WEEKDAY,
            "signal_profile": BASE_SIGNAL,
            "rejection_profile": BASE_REJECTION,
            "gate_profile": STRESS_GATE_LABEL,
        }
    if len(parts) != 5:
        return {
            "ema_profile": "",
            "weekday_profile": "",
            "signal_profile": "",
            "rejection_profile": "",
            "gate_profile": "",
        }
    return {
        "ema_profile": parts[0],
        "weekday_profile": parts[1],
        "signal_profile": parts[2],
        "rejection_profile": parts[3],
        "gate_profile": parts[4],
    }


def annual_metric_packet(trades: list[Any], year: int) -> dict[str, Any]:
    selected = [trade for trade in trades if trade_date(trade).year == year]
    values = np.asarray([trade_r(trade) for trade in selected], dtype=float)
    return {
        "trades": int(len(values)),
        "net_r": float(values.sum()) if len(values) else 0.0,
        "wr_pct": float((values > 0).mean() * 100.0) if len(values) else 0.0,
        "pf": profit_factor(values),
        "closed_dd_r": max_drawdown(values),
    }


def add_rank_columns(metrics_df: pd.DataFrame) -> pd.DataFrame:
    pivot = metrics_df.pivot(index="variant_id", columns="window", values="score")
    out = metrics_df.copy()
    out["pre_holdout_score"] = out["variant_id"].map(pivot["pre_holdout"])
    out["full_10y_score"] = out["variant_id"].map(pivot["full_10y"])
    out["since_2025_score"] = out["variant_id"].map(pivot["since_2025"])
    out["last_1y_score"] = out["variant_id"].map(pivot["last_1y"])
    return out


def paired_effects(metrics_df: pd.DataFrame) -> pd.DataFrame:
    wide = metrics_df.set_index(["variant_id", "window"])
    config_rows = metrics_df.drop_duplicates("variant_id")[
        [
            "variant_id",
            "ema_profile",
            "weekday_profile",
            "signal_profile",
            "rejection_profile",
            "gate_profile",
        ]
    ]
    stress_rows = config_rows[config_rows["gate_profile"] == STRESS_GATE_LABEL]
    rows: list[dict[str, Any]] = []

    def delta_row(effect: str, from_id: str, to_id: str) -> None:
        if from_id not in wide.index.get_level_values("variant_id") or to_id not in wide.index.get_level_values("variant_id"):
            return
        record: dict[str, Any] = {"effect": effect, "from_variant": from_id, "to_variant": to_id}
        for window in WINDOWS:
            before = wide.loc[(from_id, window)]
            after = wide.loc[(to_id, window)]
            record[f"{window}_delta_net_r"] = float(after.net_r - before.net_r)
            record[f"{window}_delta_dd_r"] = float(after.closed_dd_r - before.closed_dd_r)
            record[f"{window}_delta_trades"] = int(after.trades - before.trades)
            record[f"{window}_delta_pf"] = float(after.pf - before.pf)
        rows.append(record)

    for row in stress_rows.itertuples(index=False):
        base_parts = [
            row.ema_profile,
            row.weekday_profile,
            row.signal_profile,
            row.rejection_profile,
            STRESS_GATE_LABEL,
        ]
        if row.signal_profile == "1055":
            target = "__".join([row.ema_profile, row.weekday_profile, "1300", row.rejection_profile, STRESS_GATE_LABEL])
            delta_row("signal_1055_to_1300", "__".join(base_parts), target)
        if row.rejection_profile == "rej20":
            for target_rej in ("rej40", "rej100"):
                target = "__".join([row.ema_profile, row.weekday_profile, row.signal_profile, target_rej, STRESS_GATE_LABEL])
                delta_row(f"rejection_20_to_{target_rej[3:]}", "__".join(base_parts), target)
        if row.weekday_profile == "noTue":
            target = "__".join([row.ema_profile, "withTue", row.signal_profile, row.rejection_profile, STRESS_GATE_LABEL])
            delta_row("weekday_noTue_to_withTue", "__".join(base_parts), target)

    return pd.DataFrame(rows)


def summarize_effects(effect_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for effect, group in effect_df.groupby("effect"):
        record: dict[str, Any] = {"effect": effect, "pairs": int(len(group))}
        for window in WINDOWS:
            record[f"{window}_median_delta_net_r"] = float(group[f"{window}_delta_net_r"].median())
            record[f"{window}_median_delta_dd_r"] = float(group[f"{window}_delta_dd_r"].median())
            record[f"{window}_median_delta_trades"] = float(group[f"{window}_delta_trades"].median())
            record[f"{window}_positive_net_pairs"] = int((group[f"{window}_delta_net_r"] > 0).sum())
        rows.append(record)
    return pd.DataFrame(rows).sort_values("effect")


def get_window_row(metrics_df: pd.DataFrame, variant_id: str, window: str) -> pd.Series:
    return metrics_df[(metrics_df["variant_id"] == variant_id) & (metrics_df["window"] == window)].iloc[0]


def compact_metrics(metrics_df: pd.DataFrame, variant_id: str) -> str:
    pre = get_window_row(metrics_df, variant_id, "pre_holdout")
    full = get_window_row(metrics_df, variant_id, "full_10y")
    recent = get_window_row(metrics_df, variant_id, "since_2025")
    last = get_window_row(metrics_df, variant_id, "last_1y")
    return (
        f"pre {fmt_r(float(pre.net_r))}/{fmt_r(float(pre.closed_dd_r))} DD; "
        f"full {fmt_r(float(full.net_r))}/{fmt_r(float(full.closed_dd_r))} DD; "
        f"2025+ {fmt_r(float(recent.net_r))}; last1 {fmt_r(float(last.net_r))}"
    )


def top_ids(metrics_df: pd.DataFrame, window: str, *, n: int = 5, stress_only: bool = True) -> list[str]:
    sub = metrics_df[metrics_df["window"] == window].copy()
    if stress_only:
        sub = sub[sub["gate_profile"] == STRESS_GATE_LABEL]
    sub = sub.sort_values(["score", "net_r"], ascending=False)
    return list(sub.head(n)["variant_id"])


def build_report(metrics_df: pd.DataFrame, effect_summary: pd.DataFrame, annual_df: pd.DataFrame, selected_ids: list[str]) -> str:
    baseline_id = "ema14_tol2_distnone__noTue__1055__rej20__stress"
    baseline = get_window_row(metrics_df, baseline_id, "full_10y")
    pre_leaders = top_ids(metrics_df, "pre_holdout", n=5)
    full_leaders = top_ids(metrics_df, "full_10y", n=5)
    hot_leaders = top_ids(metrics_df, "last_1y", n=5)
    since_2025_leaders = top_ids(metrics_df, "since_2025", n=5)

    best_pre = pre_leaders[0]
    best_full = full_leaders[0]
    best_hot = hot_leaders[0]
    best_2025 = since_2025_leaders[0]

    lines = [
        "# NQ Hunter Classic ORB Next Tests (2026-05-02)",
        "",
        "## Scope",
        "",
        "Follow-up around the stress-gated balanced Hunter candidate `ema14_tol2_distnone_relegacy_samewin0`.",
        "",
        "- Stress gate remains ON for all promotion rankings: skip `bull_high_vol`, `bear_high_vol`, `bear_medium_vol`.",
        "- Swept signal cutoff `10:55` vs `13:00`, rejection wick max `20/40/100`, and Tuesday excluded vs included.",
        "- EMA controls included because they are cheap: `ema14 tol0/tol2/tol5`, `ema14 tol2 dist150`, and previous `ema10 tol0 dist150` challenger.",
        "- Holdout view remains `2025-01-01+`; pre-holdout ranking is the workflow-clean read.",
        "",
        "## Baseline",
        "",
        f"Stress-gated balanced baseline: `{baseline_id}`.",
        "",
        f"- Full 10y: {int(baseline.trades):,} trades, {fmt_r(float(baseline.net_r))}, "
        f"{fmt_pct(float(baseline.wr_pct))} WR, PF {float(baseline.pf):.2f}, DD {fmt_r(float(baseline.closed_dd_r))}",
        f"- {compact_metrics(metrics_df, baseline_id)}",
        "",
        "## Paired Effect Summary",
        "",
        "| Effect | Pairs | Pre-HO Net | Full Net | 2024+ Net | 2025+ Net | Last 1y Net | Full DD |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    effect_labels = {
        "signal_1055_to_1300": "Signal 10:55 -> 13:00",
        "rejection_20_to_40": "Rejection 20 -> 40",
        "rejection_20_to_100": "Rejection 20 -> disabled",
        "weekday_noTue_to_withTue": "Add Tuesday",
    }
    for row in effect_summary.itertuples(index=False):
        lines.append(
            f"| {effect_labels.get(row.effect, row.effect)} | {row.pairs} | "
            f"{fmt_r(row.pre_holdout_median_delta_net_r)} | "
            f"{fmt_r(row.full_10y_median_delta_net_r)} | "
            f"{fmt_r(row.since_2024_median_delta_net_r)} | "
            f"{fmt_r(row.since_2025_median_delta_net_r)} | "
            f"{fmt_r(row.last_1y_median_delta_net_r)} | "
            f"{fmt_r(row.full_10y_median_delta_dd_r)} |"
        )

    def add_leaderboard(title: str, ids: list[str], ranking_window: str) -> None:
        lines.extend(
            [
                "",
                f"## {title}",
                "",
                "| Rank | Candidate | Trades | Net | WR | PF | DD | Neg Years | 2025+ | Last 1y |",
                "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for rank, variant_id in enumerate(ids, start=1):
            row = get_window_row(metrics_df, variant_id, ranking_window)
            recent = get_window_row(metrics_df, variant_id, "since_2025")
            last = get_window_row(metrics_df, variant_id, "last_1y")
            lines.append(
                f"| {rank} | `{variant_id}` | {int(row.trades):,} | {fmt_r(float(row.net_r))} | "
                f"{fmt_pct(float(row.wr_pct))} | {float(row.pf):.2f} | {fmt_r(float(row.closed_dd_r))} | "
                f"{int(row.negative_years)} | {fmt_r(float(recent.net_r))} | {fmt_r(float(last.net_r))} |"
            )

    add_leaderboard("Workflow-Clean Pre-Holdout Leaders", pre_leaders, "pre_holdout")
    add_leaderboard("Full 10-Year Leaders", full_leaders, "full_10y")
    add_leaderboard("Recent Hot-Window Leaders", hot_leaders, "last_1y")

    lines.extend(
        [
            "",
            "## Key Candidate Comparison",
            "",
            "| Role | Candidate | Pre-HO | Full 10y | 2024+ | 2025+ | Last 1y | Full Neg Years |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    role_rows = [
        ("Baseline", baseline_id),
        ("Best workflow-clean", best_pre),
        ("Best full 10y", best_full),
        ("Best 2025+", best_2025),
        ("Best last 1y", best_hot),
    ]
    seen: set[str] = set()
    for role, variant_id in role_rows:
        if variant_id in seen:
            continue
        seen.add(variant_id)
        pre = get_window_row(metrics_df, variant_id, "pre_holdout")
        full = get_window_row(metrics_df, variant_id, "full_10y")
        since_2024 = get_window_row(metrics_df, variant_id, "since_2024")
        since_2025 = get_window_row(metrics_df, variant_id, "since_2025")
        last = get_window_row(metrics_df, variant_id, "last_1y")
        lines.append(
            f"| {role} | `{variant_id}` | "
            f"{fmt_r(float(pre.net_r))} / {fmt_r(float(pre.closed_dd_r))} DD | "
            f"{fmt_r(float(full.net_r))} / {fmt_r(float(full.closed_dd_r))} DD | "
            f"{fmt_r(float(since_2024.net_r))} | {fmt_r(float(since_2025.net_r))} | "
            f"{fmt_r(float(last.net_r))} | {int(full.negative_years)} |"
        )

    lines.extend(
        [
            "",
            "## Annual Net R For Shortlist",
            "",
            "| Year | " + " | ".join(f"`{variant_id}`" for variant_id in selected_ids) + " |",
            "|---:|" + "|".join(["---:"] * len(selected_ids)) + "|",
        ]
    )
    for year in range(FULL_START.year, FULL_END.year + 1):
        values = []
        for variant_id in selected_ids:
            row = annual_df[(annual_df["variant_id"] == variant_id) & (annual_df["year"] == year)]
            values.append(fmt_r(float(row.iloc[0].net_r)) if not row.empty else "+0.0R")
        lines.append(f"| {year} | " + " | ".join(values) + " |")

    lines.extend(
        [
            "",
            "## No-Gate Context",
            "",
            "| Variant | Full 10y | 2025+ | Last 1y |",
            "|---|---:|---:|---:|",
        ]
    )
    for variant_id in metrics_df.loc[metrics_df["gate_profile"] == NO_GATE_LABEL, "variant_id"].drop_duplicates():
        full = get_window_row(metrics_df, variant_id, "full_10y")
        since_2025 = get_window_row(metrics_df, variant_id, "since_2025")
        last = get_window_row(metrics_df, variant_id, "last_1y")
        lines.append(
            f"| `{variant_id}` | {fmt_r(float(full.net_r))} / {fmt_r(float(full.closed_dd_r))} DD | "
            f"{fmt_r(float(since_2025.net_r))} | {fmt_r(float(last.net_r))} |"
        )

    lines.extend(
        [
            "",
            "## Read",
            "",
            "- **Signal extension to 13:00 is not broadly validated.** The original baseline-only ablation looked good, and the direct baseline row still improves, but the paired grid median gives up 2024+, 2025+, and last-1y R while slightly worsening full-history DD. Treat 13:00 as a narrow baseline-like side branch, not the new default.",
            "- **Relaxing/removing the rejection wick filter is the cleanest robust improvement.** `rej40` and `rej100` both add median R across every window; the cost is worse full-history DD. The top workflow/full candidates use `rej100`, and the best recent candidate ties between `rej40` and `rej100` with `rej100` having the better long-history profile.",
            "- **Tuesday is a 10y-vs-recent fork.** It helps every full/pre-history paired comparison and drives the best 10y candidates, but it hurts every 2025+ and last-1y paired comparison. Do not re-add Tuesday to the live/pilot expression unless the objective is explicitly 10y diversification over current-regime strength.",
            "- **Best 10y-safe candidate:** `ema14_tol0_distnone__withTue__1055__rej100__stress` is the workflow-clean pre-holdout leader; `ema14_tol5_distnone__withTue__1055__rej100__stress` is the full-10y hindsight leader. Both disable rejection and re-add Tuesday, and both give up last-1y R versus the baseline.",
            "- **Best hot candidate:** `ema14_tol5_distnone__noTue__1055__rej100__stress`/`rej40` wins the recent window. Prefer `rej100` if carrying it forward because it has identical recent performance with better pre/full/DD than `rej40`.",
            "- **Supersede read:** no single row cleanly supersedes the balanced stress-gated baseline across all objectives. Carry forward two branches: a 10y-safe Tuesday/rej100 branch and a recent-strength no-Tuesday/tol5/rej100 branch. Keep the current balanced baseline as the neutral reference until downstream validation decides.",
            "",
            "## Artifacts",
            "",
            f"- Results packet: `{RESULT_DIR}`",
            "- `next_test_metrics.csv`",
            "- `paired_effects.csv`",
            "- `paired_effect_summary.csv`",
            "- `annual_metrics.csv`",
            "- `selected_trades/*.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "selected_trades").mkdir(parents=True, exist_ok=True)

    regime_lookup = load_regime_lookup(REGIME_CALENDAR)
    df_1s = load_1s(DATA_1S, FULL_START, LOAD_END)
    bars_5m = resample_5m(df_1s)
    candidates = build_broad_candidates(bars_5m)
    print(f"Built broad candidate pool: {len(candidates):,}", flush=True)

    exit_cache: dict[tuple[tuple[str, str], bool], Any | None] = {}
    metric_rows: list[dict[str, Any]] = []
    annual_rows: list[dict[str, Any]] = []
    trade_count_rows: list[dict[str, Any]] = []
    trades_by_variant: dict[str, list[Any]] = {}

    configs = next_test_configs()
    for config in configs:
        selected_candidates = filter_candidates(candidates, config)
        raw_trades = select_trades(selected_candidates, exit_cache, config, df_1s)
        trades = filter_stress_gate(raw_trades, regime_lookup, config)
        trades_by_variant[config.variant_id] = trades
        parsed = parse_variant_id(config.variant_id)
        print(
            f"{config.variant_id}: candidates={len(selected_candidates):,} raw={len(raw_trades):,} trades={len(trades):,}",
            flush=True,
        )

        trade_count_rows.append(
            {
                "variant_id": config.variant_id,
                "label": config.label,
                "category": config.category,
                "candidate_count": len(selected_candidates),
                "raw_trade_count": len(raw_trades),
                "final_trade_count": len(trades),
                **parsed,
            }
        )

        for window_name, (start, end) in WINDOWS.items():
            metrics = metric_packet(trades, start, end)
            metric_rows.append(
                {
                    **asdict(config),
                    **parsed,
                    "window": window_name,
                    **metrics,
                    "score": score(metrics),
                }
            )

        for year in range(FULL_START.year, FULL_END.year + 1):
            annual_rows.append(
                {
                    "variant_id": config.variant_id,
                    "year": year,
                    **parsed,
                    **annual_metric_packet(trades, year),
                }
            )

    metrics_df = add_rank_columns(pd.DataFrame(metric_rows))
    annual_df = pd.DataFrame(annual_rows)
    trade_counts_df = pd.DataFrame(trade_count_rows)
    effects_df = paired_effects(metrics_df)
    effect_summary = summarize_effects(effects_df)

    metrics_df.to_csv(RESULT_DIR / "next_test_metrics.csv", index=False)
    annual_df.to_csv(RESULT_DIR / "annual_metrics.csv", index=False)
    trade_counts_df.to_csv(RESULT_DIR / "trade_counts.csv", index=False)
    effects_df.to_csv(RESULT_DIR / "paired_effects.csv", index=False)
    effect_summary.to_csv(RESULT_DIR / "paired_effect_summary.csv", index=False)

    selected_ids = []
    preferred_recent_id = "ema14_tol5_distnone__noTue__1055__rej100__stress"
    for ids in (
        ["ema14_tol2_distnone__noTue__1055__rej20__stress"],
        top_ids(metrics_df, "pre_holdout", n=1),
        top_ids(metrics_df, "full_10y", n=1),
        [preferred_recent_id],
        top_ids(metrics_df, "since_2025", n=1),
        top_ids(metrics_df, "last_1y", n=1),
    ):
        for variant_id in ids:
            if variant_id not in selected_ids:
                selected_ids.append(variant_id)

    for variant_id in selected_ids:
        write_csv(
            RESULT_DIR / "selected_trades" / f"{variant_id}.csv",
            [
                {
                    **asdict(trade),
                    "variant_id": variant_id,
                    "r": trade_r(trade),
                }
                for trade in trades_by_variant[variant_id]
            ],
        )

    report = build_report(metrics_df, effect_summary, annual_df, selected_ids)
    REPORT_PATH.write_text(report)
    (RESULT_DIR / "summary.md").write_text(report)
    (RESULT_DIR / "summary.json").write_text(
        json.dumps(
            {
                "baseline": "ema14_tol2_distnone__noTue__1055__rej20__stress",
                "selected_ids": selected_ids,
                "result_dir": str(RESULT_DIR),
                "report": str(REPORT_PATH),
                "config_count": len(configs),
                "main_grid_count": int(sum(c.category == "main_grid" for c in configs)),
                "context_no_gate_count": int(sum(c.category == "context_no_gate" for c in configs)),
            },
            indent=2,
            default=str,
            allow_nan=True,
        )
        + "\n"
    )

    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
