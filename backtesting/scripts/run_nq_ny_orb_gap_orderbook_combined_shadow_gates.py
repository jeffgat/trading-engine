#!/usr/bin/env python3
"""Run frozen combined shadow gates for NQ NY ORB gap MBP-1 features.

The screen fits feature quartiles on 2021-2024 only, then applies those
thresholds unchanged to 2025 and 2026. These are research shadow gates:
they do not change the live/dry execution config.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from run_nq_ny_orb_gap_orderbook_bucket_screen import metrics, period_for_date, thresholds_for


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_orb_gap_orderbook_feature_lab_20260610_scored"
    / "trade_orderbook_gap_features.csv"
)
DEFAULT_OUTPUT_DIR = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_orb_gap_orderbook_combined_shadow_gates_20260610"
)


@dataclass(frozen=True)
class RuleMask:
    name: str
    family: str
    rule: str
    mask: pd.Series
    components: tuple[str, ...]


THRESHOLD_FEATURES = (
    "gap_create_5m_mid_range_ticks",
    "gap_create_5m_update_rate_per_sec",
    "gap_create_5m_price_volume",
    "gap_create_5m_price_range_ticks",
    "gap_create_last30s_update_rate_per_sec",
    "gap_create_last10s_update_rate_per_sec",
    "pre_entry_10s_l1_imbalance_mean",
    "pre_entry_10s_bid_dominance_pct",
    "revisit_full_update_rate_per_sec",
    "pre_entry_30s_mid_velocity_ticks_per_sec",
)


def clean_numeric(frame: pd.DataFrame, feature: str) -> pd.Series:
    return pd.to_numeric(frame[feature], errors="coerce").replace([np.inf, -np.inf], np.nan)


def threshold_table(frame: pd.DataFrame, features: tuple[str, ...]) -> pd.DataFrame:
    dev = frame[frame["analysis_period"].eq("dev_2021_2024")]
    rows: list[dict[str, object]] = []
    for feature in features:
        if feature not in frame.columns:
            continue
        thresholds = thresholds_for(dev, feature)
        if thresholds is None or len(thresholds) < 3:
            continue
        rows.append(
            {
                "feature": feature,
                "q25": thresholds[0],
                "q50": thresholds[1],
                "q75": thresholds[2],
                "thresholds": json.dumps(thresholds),
            }
        )
    return pd.DataFrame(rows)


def primitive_masks(frame: pd.DataFrame, thresholds: pd.DataFrame) -> dict[str, RuleMask]:
    by_feature = thresholds.set_index("feature").to_dict(orient="index")

    def value(feature: str) -> pd.Series:
        return clean_numeric(frame, feature)

    def q(feature: str, key: str) -> float:
        return float(by_feature[feature][key])

    def le(feature: str, key: str, name: str, family: str, desc: str) -> RuleMask:
        mask = value(feature).le(q(feature, key)).fillna(False)
        return RuleMask(name, family, f"{feature} <= dev_{key} ({q(feature, key):.6g}); {desc}", mask, (name,))

    def gt(feature: str, key: str, name: str, family: str, desc: str) -> RuleMask:
        mask = value(feature).gt(q(feature, key)).fillna(False)
        return RuleMask(name, family, f"{feature} > dev_{key} ({q(feature, key):.6g}); {desc}", mask, (name,))

    def between(feature: str, low_key: str, high_key: str, name: str, family: str, desc: str) -> RuleMask:
        series = value(feature)
        mask = series.gt(q(feature, low_key)).fillna(False) & series.le(q(feature, high_key)).fillna(False)
        return RuleMask(
            name,
            family,
            f"dev_{low_key} < {feature} <= dev_{high_key} ({q(feature, low_key):.6g}, {q(feature, high_key):.6g}); {desc}",
            mask,
            (name,),
        )

    primitives = [
        le("gap_create_5m_mid_range_ticks", "q25", "gap_mid_range_q1", "gap_creation", "quiet/small MBP1 mid range during gap creation"),
        le("gap_create_5m_update_rate_per_sec", "q25", "gap_update_rate_q1", "gap_creation", "quiet/slower book update rate during gap creation"),
        le("gap_create_5m_price_volume", "q25", "gap_price_volume_q1", "gap_creation", "lower traded volume during gap creation"),
        le("gap_create_5m_price_range_ticks", "q25", "gap_price_range_q1", "gap_creation", "smaller trade-price range during gap creation"),
        le("gap_create_last30s_update_rate_per_sec", "q25", "gap_last30_update_q1", "gap_creation", "quiet final 30s of gap creation"),
        le("gap_create_last10s_update_rate_per_sec", "q25", "gap_last10_update_q1", "gap_creation", "quiet final 10s of gap creation"),
        le("pre_entry_10s_l1_imbalance_mean", "q25", "pre10_imbalance_q1", "revisit_avoidance", "low pre-entry imbalance"),
        le("pre_entry_10s_l1_imbalance_mean", "q75", "pre10_imbalance_not_q4", "revisit_avoidance", "avoid extreme high pre-entry imbalance"),
        le("pre_entry_10s_bid_dominance_pct", "q25", "pre10_bid_dominance_q1", "revisit_avoidance", "low pre-entry bid dominance"),
        le("pre_entry_10s_bid_dominance_pct", "q75", "pre10_bid_dominance_not_q4", "revisit_avoidance", "avoid extreme high pre-entry bid dominance"),
        le("revisit_full_update_rate_per_sec", "q25", "revisit_update_rate_q1", "revisit_avoidance", "quiet/slower full revisit update rate"),
        le("revisit_full_update_rate_per_sec", "q75", "revisit_update_rate_not_q4", "revisit_avoidance", "avoid extreme full-revisit update rate"),
        gt("pre_entry_30s_mid_velocity_ticks_per_sec", "q25", "pre30_mid_velocity_not_q1", "revisit_avoidance", "avoid weakest pre-entry mid velocity bucket"),
        between("pre_entry_30s_mid_velocity_ticks_per_sec", "q25", "q75", "pre30_mid_velocity_q2_q3", "revisit_avoidance", "middle pre-entry mid velocity buckets"),
    ]
    return {primitive.name: primitive for primitive in primitives}


def any_rule(name: str, family: str, rule: str, parts: list[RuleMask]) -> RuleMask:
    mask = pd.concat([part.mask for part in parts], axis=1).any(axis=1)
    components = tuple(component for part in parts for component in part.components)
    return RuleMask(name, family, rule, mask.fillna(False), components)


def at_least_rule(name: str, family: str, rule: str, parts: list[RuleMask], minimum: int) -> RuleMask:
    mask = pd.concat([part.mask for part in parts], axis=1).sum(axis=1).ge(minimum)
    components = tuple(component for part in parts for component in part.components)
    return RuleMask(name, family, rule, mask.fillna(False), components)


def and_rule(left: RuleMask, right: RuleMask) -> RuleMask:
    return RuleMask(
        name=f"{left.name}__AND__{right.name}",
        family="gap_plus_revisit",
        rule=f"({left.rule}) AND ({right.rule})",
        mask=(left.mask & right.mask).fillna(False),
        components=(*left.components, *right.components),
    )


def build_gate_recipes(frame: pd.DataFrame, thresholds: pd.DataFrame) -> list[RuleMask]:
    primitives = primitive_masks(frame, thresholds)
    top_gap = [
        primitives["gap_mid_range_q1"],
        primitives["gap_update_rate_q1"],
        primitives["gap_price_volume_q1"],
    ]
    broad_gap = [
        primitives["gap_mid_range_q1"],
        primitives["gap_update_rate_q1"],
        primitives["gap_price_volume_q1"],
        primitives["gap_price_range_q1"],
    ]
    late_gap = [
        primitives["gap_last30_update_q1"],
        primitives["gap_last10_update_q1"],
    ]

    gap_recipes = [
        primitives["gap_mid_range_q1"],
        primitives["gap_update_rate_q1"],
        primitives["gap_price_volume_q1"],
        primitives["gap_price_range_q1"],
        any_rule("gap_mid_range_OR_update_q1", "gap_creation", "gap mid-range q1 OR gap update-rate q1", top_gap[:2]),
        any_rule("gap_any_top3_q1", "gap_creation", "any of gap mid-range/update-rate/price-volume q1", top_gap),
        at_least_rule("gap_2of3_top_q1", "gap_creation", "at least two of gap mid-range/update-rate/price-volume q1", top_gap, 2),
        at_least_rule("gap_3of3_top_q1", "gap_creation", "all three of gap mid-range/update-rate/price-volume q1", top_gap, 3),
        any_rule("gap_any_broad4_q1", "gap_creation", "any of four quiet gap-creation q1 primitives", broad_gap),
        at_least_rule("gap_2of4_broad_q1", "gap_creation", "at least two of four quiet gap-creation q1 primitives", broad_gap, 2),
        any_rule("gap_late_update_any_q1", "gap_creation", "last 30s update-rate q1 OR last 10s update-rate q1", late_gap),
    ]

    revisit_recipes = [
        primitives["pre10_imbalance_q1"],
        primitives["pre10_bid_dominance_q1"],
        primitives["pre10_imbalance_not_q4"],
        primitives["pre10_bid_dominance_not_q4"],
        primitives["revisit_update_rate_q1"],
        primitives["revisit_update_rate_not_q4"],
        primitives["pre30_mid_velocity_not_q1"],
        primitives["pre30_mid_velocity_q2_q3"],
        at_least_rule(
            "pre10_imbalance_AND_bid_not_q4",
            "revisit_avoidance",
            "avoid q4 for both pre-entry 10s imbalance and bid dominance",
            [primitives["pre10_imbalance_not_q4"], primitives["pre10_bid_dominance_not_q4"]],
            2,
        ),
    ]

    gates: list[RuleMask] = []
    gates.extend(gap_recipes)
    gates.extend(revisit_recipes)
    for gap in gap_recipes:
        for revisit in revisit_recipes:
            gates.append(and_rule(gap, revisit))
    return gates


def period_rows(frame: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    rows = [
        ("dev_2021_2024", frame[frame["analysis_period"].eq("dev_2021_2024")]),
        ("inspect_2025", frame[frame["analysis_period"].eq("inspect_2025")]),
        ("inspect_2026", frame[frame["analysis_period"].eq("inspect_2026")]),
        ("all", frame),
    ]
    return rows


def gate_period_metrics(frame: pd.DataFrame, gates: list[RuleMask]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for gate in gates:
        for period, period_frame in period_rows(frame):
            mask = gate.mask.loc[period_frame.index]
            passed = period_frame[mask]
            failed = period_frame[~mask]
            base_metrics = metrics(period_frame)
            pass_metrics = metrics(passed)
            fail_metrics = metrics(failed)
            for subset, subset_metrics in (("pass", pass_metrics), ("fail", fail_metrics)):
                rows.append(
                    {
                        "gate_name": gate.name,
                        "gate_family": gate.family,
                        "rule": gate.rule,
                        "components": ",".join(gate.components),
                        "period": period,
                        "subset": subset,
                        "keep_pct": round(
                            float(subset_metrics["trades"]) / max(float(base_metrics["trades"]), 1.0) * 100.0,
                            4,
                        ),
                        "delta_avg_r_vs_baseline": round(
                            float(subset_metrics["avg_r"]) - float(base_metrics["avg_r"]),
                            6,
                        ),
                        "delta_total_r_vs_baseline": round(
                            float(subset_metrics["total_r"]) - float(base_metrics["total_r"]),
                            6,
                        ),
                        "delta_mfe_ge_2r_vs_baseline": round(
                            float(subset_metrics["mfe_ge_2r_pct"]) - float(base_metrics["mfe_ge_2r_pct"]),
                            6,
                        ),
                        **subset_metrics,
                    }
                )
    return pd.DataFrame(rows)


def gate_yearly_metrics(frame: pd.DataFrame, gates: list[RuleMask]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for gate in gates:
        for year, year_frame in frame.groupby("year", sort=True):
            mask = gate.mask.loc[year_frame.index]
            passed = year_frame[mask]
            failed = year_frame[~mask]
            for subset, subset_frame in (("pass", passed), ("fail", failed)):
                rows.append(
                    {
                        "gate_name": gate.name,
                        "gate_family": gate.family,
                        "year": int(year),
                        "subset": subset,
                        **metrics(subset_frame),
                    }
                )
    return pd.DataFrame(rows)


def build_ranked_summary(period_metrics: pd.DataFrame, yearly_metrics: pd.DataFrame) -> pd.DataFrame:
    pass_metrics = period_metrics[period_metrics["subset"].eq("pass")].copy()
    rows: list[dict[str, object]] = []
    by_gate = pass_metrics.groupby("gate_name", sort=False)
    yearly_pass = yearly_metrics[yearly_metrics["subset"].eq("pass")].copy()

    def row_for(group: pd.DataFrame, period: str) -> pd.Series:
        match = group[group["period"].eq(period)]
        if match.empty:
            raise ValueError(f"Missing {period} row for gate {group['gate_name'].iloc[0]}")
        return match.iloc[0]

    for gate_name, group in by_gate:
        dev = row_for(group, "dev_2021_2024")
        p2025 = row_for(group, "inspect_2025")
        p2026 = row_for(group, "inspect_2026")
        all_period = row_for(group, "all")
        years = yearly_pass[yearly_pass["gate_name"].eq(gate_name)]
        active_years = years[years["trades"].gt(0)]
        positive_years = int(active_years["total_r"].gt(0).sum())
        negative_years = int(active_years["total_r"].lt(0).sum())
        min_year_total_r = float(active_years["total_r"].min()) if not active_years.empty else 0.0
        robust_score = (
            float(dev["delta_avg_r_vs_baseline"]) * 8.0
            + max(float(dev["profit_factor"]) - 1.0, 0.0)
            + float(dev["delta_mfe_ge_2r_vs_baseline"]) / 12.0
            + float(p2025["avg_r"])
            + float(p2026["avg_r"])
            + min(float(dev["keep_pct"]), 50.0) / 25.0
            + min(positive_years, 6) * 0.2
            - max(negative_years - 1, 0) * 0.5
        )
        status = classify_gate(dev, p2025, p2026, active_years)
        rows.append(
            {
                "gate_name": gate_name,
                "gate_family": dev["gate_family"],
                "rule": dev["rule"],
                "components": dev["components"],
                "status": status,
                "robust_score": round(robust_score, 6),
                "active_years": int(len(active_years)),
                "positive_years": positive_years,
                "negative_years": negative_years,
                "min_year_total_r": round(min_year_total_r, 6),
                "dev_trades": int(dev["trades"]),
                "dev_keep_pct": float(dev["keep_pct"]),
                "dev_total_r": float(dev["total_r"]),
                "dev_avg_r": float(dev["avg_r"]),
                "dev_delta_avg_r_vs_baseline": float(dev["delta_avg_r_vs_baseline"]),
                "dev_win_rate_pct": float(dev["win_rate_pct"]),
                "dev_pf": float(dev["profit_factor"]),
                "dev_max_dd_r": float(dev["max_dd_r"]),
                "dev_mfe_ge_2r_pct": float(dev["mfe_ge_2r_pct"]),
                "inspect_2025_trades": int(p2025["trades"]),
                "inspect_2025_total_r": float(p2025["total_r"]),
                "inspect_2025_avg_r": float(p2025["avg_r"]),
                "inspect_2025_pf": float(p2025["profit_factor"]),
                "inspect_2025_max_dd_r": float(p2025["max_dd_r"]),
                "inspect_2026_trades": int(p2026["trades"]),
                "inspect_2026_total_r": float(p2026["total_r"]),
                "inspect_2026_avg_r": float(p2026["avg_r"]),
                "inspect_2026_pf": float(p2026["profit_factor"]),
                "inspect_2026_max_dd_r": float(p2026["max_dd_r"]),
                "all_trades": int(all_period["trades"]),
                "all_total_r": float(all_period["total_r"]),
                "all_avg_r": float(all_period["avg_r"]),
                "all_pf": float(all_period["profit_factor"]),
                "all_max_dd_r": float(all_period["max_dd_r"]),
            }
        )
    ranked = pd.DataFrame(rows)
    status_rank = {
        "shadow_candidate": 0,
        "watch_no_2026_coverage": 1,
        "watch_low_2026_count": 2,
        "watch_low_2025_count": 3,
        "reject_inspection_loss": 4,
        "reject_dev_not_improved": 5,
        "reject_low_dev_count": 6,
    }
    ranked["_status_rank"] = ranked["status"].map(status_rank).fillna(99)
    ranked = ranked.sort_values(["_status_rank", "robust_score"], ascending=[True, False]).drop(columns=["_status_rank"])
    return ranked


def classify_gate(dev: pd.Series, p2025: pd.Series, p2026: pd.Series, active_years: pd.DataFrame) -> str:
    if int(dev["trades"]) < 20:
        return "reject_low_dev_count"
    if float(dev["delta_avg_r_vs_baseline"]) <= 0.0:
        return "reject_dev_not_improved"
    if int(p2025["trades"]) < 5:
        return "watch_low_2025_count"
    if float(p2025["avg_r"]) <= 0.0 or (int(p2026["trades"]) > 0 and float(p2026["avg_r"]) < 0.0):
        return "reject_inspection_loss"
    if int(p2026["trades"]) == 0:
        return "watch_no_2026_coverage"
    if int(p2026["trades"]) < 3:
        return "watch_low_2026_count"
    if not active_years.empty and int(active_years["total_r"].lt(0).sum()) > 3:
        return "reject_inspection_loss"
    return "shadow_candidate"


def trade_gate_flags(frame: pd.DataFrame, gates: list[RuleMask]) -> pd.DataFrame:
    base_cols = [
        "trade_uid",
        "date",
        "analysis_period",
        "entry_time",
        "exit_time",
        "exit_type",
        "r_multiple",
        "mfe_r",
        "mae_r",
        "risk_points",
    ]
    out = frame[[col for col in base_cols if col in frame.columns]].copy()
    flag_columns = {
        gate.name: gate.mask.astype(bool).reindex(frame.index, fill_value=False).to_numpy()
        for gate in gates
    }
    flags = pd.DataFrame(flag_columns, index=frame.index)
    return pd.concat([out, flags], axis=1)


def write_report(
    output_dir: Path,
    frame: pd.DataFrame,
    thresholds: pd.DataFrame,
    period_metrics: pd.DataFrame,
    ranked: pd.DataFrame,
) -> None:
    baseline = pd.DataFrame(
        [
            {"period": period, **metrics(period_frame)}
            for period, period_frame in period_rows(frame)
        ]
    )

    def table(df: pd.DataFrame, columns: list[str], limit: int = 12) -> str:
        if df.empty:
            return "No rows.\n"
        return df.loc[:, columns].head(limit).to_markdown(index=False)

    candidates = ranked[ranked["status"].eq("shadow_candidate")]
    watches = ranked[ranked["status"].str.startswith("watch_")]
    top_gap_only = ranked[ranked["gate_family"].eq("gap_creation")]
    top_combined = ranked[ranked["gate_family"].eq("gap_plus_revisit")]

    report = [
        "# NQ NY ORB Gap MBP1 Combined Shadow-Gate Screen",
        "",
        "- Source: `nq_ny_orb_gap_orderbook_feature_lab_20260610_scored`",
        "- Thresholds: quartiles fit on `2021-2024` only.",
        "- 2025 and 2026 are inspection slices, not re-fit.",
        "- All gates are shadow research overlays; none are live execution gates.",
        "- Post-entry features are intentionally excluded.",
        "",
        "## Baseline",
        "",
        baseline.to_markdown(index=False),
        "",
        "## Frozen Thresholds",
        "",
        thresholds.to_markdown(index=False),
        "",
        "## Candidate Shadow Gates",
        "",
        table(
            candidates,
            [
                "gate_name",
                "gate_family",
                "dev_trades",
                "dev_avg_r",
                "dev_pf",
                "dev_max_dd_r",
                "inspect_2025_trades",
                "inspect_2025_avg_r",
                "inspect_2026_trades",
                "inspect_2026_avg_r",
                "active_years",
                "negative_years",
                "robust_score",
            ],
            15,
        ),
        "",
        "## Watchlist Gates",
        "",
        table(
            watches,
            [
                "gate_name",
                "status",
                "dev_trades",
                "dev_avg_r",
                "dev_pf",
                "inspect_2025_trades",
                "inspect_2025_avg_r",
                "inspect_2026_trades",
                "inspect_2026_avg_r",
                "robust_score",
            ],
            12,
        ),
        "",
        "## Best Gap-Only Gates",
        "",
        table(
            top_gap_only,
            [
                "gate_name",
                "status",
                "dev_trades",
                "dev_avg_r",
                "dev_pf",
                "inspect_2025_trades",
                "inspect_2025_avg_r",
                "inspect_2026_trades",
                "inspect_2026_avg_r",
                "all_trades",
                "all_avg_r",
            ],
            12,
        ),
        "",
        "## Best Gap + Revisit Gates",
        "",
        table(
            top_combined,
            [
                "gate_name",
                "status",
                "dev_trades",
                "dev_avg_r",
                "dev_pf",
                "inspect_2025_trades",
                "inspect_2025_avg_r",
                "inspect_2026_trades",
                "inspect_2026_avg_r",
                "all_trades",
                "all_avg_r",
            ],
            12,
        ),
        "",
        "## Interpretation Guardrails",
        "",
        "- Treat `shadow_candidate` as a forward-tagging candidate, not a live filter.",
        "- Gates with zero or tiny 2026 coverage are hypotheses only.",
        "- Favor simple gates that preserve enough trade count and survive 2025/2026 without threshold changes.",
        "- Revisit rules should be interpreted as avoidance filters unless forward data proves they confirm buying activity.",
        "",
        "## Files",
        "",
        "- `ranked_shadow_gates.csv`",
        "- `shadow_gate_period_metrics.csv`",
        "- `shadow_gate_yearly_metrics.csv`",
        "- `shadow_gate_trade_flags.csv`",
        "- `shadow_gate_thresholds.csv`",
    ]
    (output_dir / "report.md").write_text("\n".join(report) + "\n")
    baseline.to_csv(output_dir / "baseline_period_metrics.csv", index=False)


def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input_csv)
    if not input_path.exists():
        raise SystemExit(f"Input CSV not found: {input_path}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(input_path)
    dates = pd.to_datetime(frame["date"])
    derived = pd.DataFrame(
        {
            "date": dates,
            "year": dates.dt.year.astype(int),
            "analysis_period": dates.map(period_for_date),
        },
        index=frame.index,
    )
    frame = pd.concat([frame.drop(columns=["date"]), derived], axis=1).copy()
    frame = frame[frame["setup_found"].astype(bool) & frame["orderbook_file_found"].astype(bool)].copy()

    thresholds = threshold_table(frame, THRESHOLD_FEATURES)
    missing = sorted(set(THRESHOLD_FEATURES) - set(thresholds["feature"]))
    if missing:
        raise SystemExit(f"Missing threshold features: {missing}")

    gates = build_gate_recipes(frame, thresholds)
    period_metric_rows = gate_period_metrics(frame, gates)
    yearly_metric_rows = gate_yearly_metrics(frame, gates)
    ranked = build_ranked_summary(period_metric_rows, yearly_metric_rows)
    flags = trade_gate_flags(frame, gates)

    thresholds.to_csv(output_dir / "shadow_gate_thresholds.csv", index=False)
    period_metric_rows.to_csv(output_dir / "shadow_gate_period_metrics.csv", index=False)
    yearly_metric_rows.to_csv(output_dir / "shadow_gate_yearly_metrics.csv", index=False)
    ranked.to_csv(output_dir / "ranked_shadow_gates.csv", index=False)
    flags.to_csv(output_dir / "shadow_gate_trade_flags.csv", index=False)
    write_report(output_dir, frame, thresholds, period_metric_rows, ranked)

    summary = {
        "input_csv": str(input_path),
        "output_dir": str(output_dir),
        "rows": int(len(frame)),
        "threshold_features": int(len(thresholds)),
        "shadow_gates": int(len(gates)),
        "shadow_candidates": int(ranked["status"].eq("shadow_candidate").sum()),
        "watchlist_gates": int(ranked["status"].str.startswith("watch_").sum()),
        "report": str(output_dir / "report.md"),
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-csv", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
