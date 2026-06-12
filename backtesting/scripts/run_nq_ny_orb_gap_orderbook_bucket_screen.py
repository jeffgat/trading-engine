#!/usr/bin/env python3
"""Bucket-screen NQ NY ORB gap MBP-1 features.

This consumes the scored ORB gap order-book feature lab output. Thresholds are
fit on the 2021-2024 development window, then applied unchanged to 2025 and
2026 for inspection. Post-entry features are reported as diagnostics only.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_orb_gap_orderbook_feature_lab_20260610_scored"
    / "trade_orderbook_gap_features.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_orb_gap_orderbook_bucket_screen_20260610"


@dataclass(frozen=True)
class FeatureSpec:
    feature: str
    family: str
    stage: str
    causal_use: str
    direction_hint: str = "unknown"


GAP_FEATURES = (
    "gap_create_5m_mid_velocity_ticks_per_sec",
    "gap_create_5m_mid_range_ticks",
    "gap_create_5m_spread_mean_ticks",
    "gap_create_5m_spread_widen_ticks",
    "gap_create_5m_l1_imbalance_mean",
    "gap_create_5m_bid_dominance_pct",
    "gap_create_5m_update_rate_per_sec",
    "gap_create_5m_price_velocity_ticks_per_sec",
    "gap_create_5m_price_range_ticks",
    "gap_create_5m_price_volume",
    "gap_create_last30s_mid_velocity_ticks_per_sec",
    "gap_create_last30s_spread_mean_ticks",
    "gap_create_last30s_spread_widen_ticks",
    "gap_create_last30s_l1_imbalance_mean",
    "gap_create_last30s_bid_dominance_pct",
    "gap_create_last30s_update_rate_per_sec",
    "gap_create_last30s_price_velocity_ticks_per_sec",
    "gap_create_last30s_price_range_ticks",
    "gap_create_last30s_price_volume",
    "gap_create_last10s_mid_velocity_ticks_per_sec",
    "gap_create_last10s_spread_mean_ticks",
    "gap_create_last10s_spread_widen_ticks",
    "gap_create_last10s_l1_imbalance_mean",
    "gap_create_last10s_bid_dominance_pct",
    "gap_create_last10s_update_rate_per_sec",
    "gap_create_last10s_price_velocity_ticks_per_sec",
    "gap_create_last10s_price_range_ticks",
    "gap_create_last10s_price_volume",
)

REVISIT_FEATURES = (
    "revisit_full_mid_velocity_ticks_per_sec",
    "revisit_full_mid_range_ticks",
    "revisit_full_spread_mean_ticks",
    "revisit_full_spread_widen_ticks",
    "revisit_full_l1_imbalance_mean",
    "revisit_full_bid_dominance_pct",
    "revisit_full_update_rate_per_sec",
    "revisit_full_price_velocity_ticks_per_sec",
    "revisit_full_price_range_ticks",
    "revisit_full_price_volume",
    "pre_entry_30s_mid_velocity_ticks_per_sec",
    "pre_entry_30s_mid_range_ticks",
    "pre_entry_30s_spread_mean_ticks",
    "pre_entry_30s_spread_widen_ticks",
    "pre_entry_30s_l1_imbalance_mean",
    "pre_entry_30s_bid_dominance_pct",
    "pre_entry_30s_update_rate_per_sec",
    "pre_entry_30s_price_velocity_ticks_per_sec",
    "pre_entry_30s_price_range_ticks",
    "pre_entry_30s_price_volume",
    "pre_entry_10s_mid_velocity_ticks_per_sec",
    "pre_entry_10s_mid_range_ticks",
    "pre_entry_10s_spread_mean_ticks",
    "pre_entry_10s_spread_widen_ticks",
    "pre_entry_10s_l1_imbalance_mean",
    "pre_entry_10s_bid_dominance_pct",
    "pre_entry_10s_update_rate_per_sec",
    "pre_entry_10s_price_velocity_ticks_per_sec",
    "pre_entry_10s_price_range_ticks",
    "pre_entry_10s_price_volume",
)

POST_FEATURES = (
    "post_entry_30s_mid_velocity_ticks_per_sec",
    "post_entry_30s_mid_range_ticks",
    "post_entry_30s_spread_mean_ticks",
    "post_entry_30s_spread_widen_ticks",
    "post_entry_30s_l1_imbalance_mean",
    "post_entry_30s_bid_dominance_pct",
    "post_entry_30s_update_rate_per_sec",
    "post_entry_30s_price_velocity_ticks_per_sec",
    "post_entry_30s_price_range_ticks",
    "post_entry_30s_price_volume",
    "post_entry_60s_mid_velocity_ticks_per_sec",
    "post_entry_60s_mid_range_ticks",
    "post_entry_60s_spread_mean_ticks",
    "post_entry_60s_spread_widen_ticks",
    "post_entry_60s_l1_imbalance_mean",
    "post_entry_60s_bid_dominance_pct",
    "post_entry_60s_update_rate_per_sec",
    "post_entry_60s_price_velocity_ticks_per_sec",
    "post_entry_60s_price_range_ticks",
    "post_entry_60s_price_volume",
)

HIGHER_BETTER_HINTS = (
    "velocity",
    "bid_dominance",
    "l1_imbalance",
    "price_volume",
    "update_rate",
)
LOWER_BETTER_HINTS = (
    "spread_mean",
    "spread_widen",
)


def finite_series(frame: pd.DataFrame, feature: str) -> pd.Series:
    return pd.to_numeric(frame[feature], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()


def max_drawdown_r(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for raw in values:
        if not math.isfinite(float(raw)):
            continue
        equity += float(raw)
        peak = max(peak, equity)
        max_dd = min(max_dd, equity - peak)
    return float(max_dd)


def metrics(frame: pd.DataFrame) -> dict[str, float | int]:
    if frame.empty:
        return {
            "trades": 0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_r": 0.0,
            "avg_mfe_r": 0.0,
            "median_mfe_r": 0.0,
            "mfe_ge_2r_pct": 0.0,
            "avg_mae_r": 0.0,
        }
    r = pd.to_numeric(frame["r_multiple"], errors="coerce").fillna(0.0)
    wins = r[r > 0]
    losses = r[r < 0]
    mfe = pd.to_numeric(frame["mfe_r"], errors="coerce")
    mae = pd.to_numeric(frame["mae_r"], errors="coerce")
    loss_sum = float(-losses.sum())
    return {
        "trades": int(len(frame)),
        "total_r": round(float(r.sum()), 6),
        "avg_r": round(float(r.mean()), 6),
        "win_rate_pct": round(float((r > 0).mean() * 100.0), 4),
        "profit_factor": round(float(wins.sum()) / loss_sum, 6) if loss_sum > 0 else 0.0,
        "max_dd_r": round(max_drawdown_r(r), 6),
        "avg_mfe_r": round(float(mfe.mean()), 6),
        "median_mfe_r": round(float(mfe.median()), 6),
        "mfe_ge_2r_pct": round(float((mfe >= 2.0).mean() * 100.0), 4),
        "avg_mae_r": round(float(mae.mean()), 6),
    }


def period_for_date(value: object) -> str:
    ts = pd.Timestamp(value)
    if ts.year <= 2024:
        return "dev_2021_2024"
    if ts.year == 2025:
        return "inspect_2025"
    return "inspect_2026"


def feature_specs(columns: set[str]) -> list[FeatureSpec]:
    specs: list[FeatureSpec] = []
    for feature in GAP_FEATURES:
        if feature in columns:
            specs.append(
                FeatureSpec(feature, "gap_creation", _stage_from_feature(feature), "entry_causal", hint(feature))
            )
    for feature in REVISIT_FEATURES:
        if feature in columns:
            specs.append(
                FeatureSpec(feature, "gap_revisit", _stage_from_feature(feature), "entry_causal", hint(feature))
            )
    for feature in POST_FEATURES:
        if feature in columns:
            specs.append(
                FeatureSpec(feature, "post_entry", _stage_from_feature(feature), "diagnostic_only", hint(feature))
            )
    return specs


def _stage_from_feature(feature: str) -> str:
    for prefix in (
        "gap_create_5m",
        "gap_create_last30s",
        "gap_create_last10s",
        "revisit_full",
        "pre_entry_30s",
        "pre_entry_10s",
        "post_entry_30s",
        "post_entry_60s",
    ):
        if feature.startswith(prefix):
            return prefix
    return "unknown"


def hint(feature: str) -> str:
    if any(token in feature for token in LOWER_BETTER_HINTS):
        return "lower_may_be_better"
    if any(token in feature for token in HIGHER_BETTER_HINTS):
        return "higher_may_be_better"
    return "unknown"


def thresholds_for(dev: pd.DataFrame, feature: str) -> list[float] | None:
    values = finite_series(dev, feature)
    if len(values) < 20 or values.nunique() < 4:
        return None
    raw = values.quantile([0.25, 0.5, 0.75]).astype(float).tolist()
    thresholds = sorted(set(round(value, 12) for value in raw))
    return thresholds if len(thresholds) >= 2 else None


def assign_bucket(values: pd.Series, thresholds: list[float]) -> pd.Series:
    bins = [-np.inf, *thresholds, np.inf]
    labels = [f"q{i}" for i in range(1, len(bins))]
    clean = pd.to_numeric(values, errors="coerce").replace([np.inf, -np.inf], np.nan)
    return pd.cut(clean, bins=bins, labels=labels, include_lowest=True).astype("string")


def bucket_screen(frame: pd.DataFrame, specs: list[FeatureSpec]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dev = frame[frame["analysis_period"].eq("dev_2021_2024")].copy()
    threshold_rows: list[dict[str, object]] = []
    bucket_rows: list[dict[str, object]] = []
    contrast_rows: list[dict[str, object]] = []

    for spec in specs:
        thresholds = thresholds_for(dev, spec.feature)
        if thresholds is None:
            continue
        threshold_rows.append({**asdict(spec), "thresholds": json.dumps(thresholds)})
        bucket_col = assign_bucket(frame[spec.feature], thresholds)

        for period in ("dev_2021_2024", "inspect_2025", "inspect_2026", "all"):
            period_frame = frame if period == "all" else frame[frame["analysis_period"].eq(period)]
            period_buckets = bucket_col.loc[period_frame.index]
            for bucket in sorted(period_buckets.dropna().unique()):
                group = period_frame[period_buckets.eq(bucket)]
                row = {
                    **asdict(spec),
                    "period": period,
                    "bucket": bucket,
                    "bucket_min": float(finite_series(group, spec.feature).min()) if not group.empty else np.nan,
                    "bucket_max": float(finite_series(group, spec.feature).max()) if not group.empty else np.nan,
                    **metrics(group),
                }
                bucket_rows.append(row)

        contrast_rows.extend(contrast_for_feature(frame, bucket_col, spec))

    return (
        pd.DataFrame(threshold_rows),
        pd.DataFrame(bucket_rows),
        pd.DataFrame(contrast_rows),
    )


def contrast_for_feature(frame: pd.DataFrame, bucket_col: pd.Series, spec: FeatureSpec) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    periods = ("dev_2021_2024", "inspect_2025", "inspect_2026")
    for period in periods:
        period_frame = frame[frame["analysis_period"].eq(period)]
        period_buckets = bucket_col.loc[period_frame.index]
        low = period_frame[period_buckets.eq("q1")]
        high_label = f"q{len(bucket_col.dropna().unique())}"
        high = period_frame[period_buckets.eq(high_label)]
        if low.empty or high.empty:
            continue
        low_metrics = metrics(low)
        high_metrics = metrics(high)
        rows.append(
            {
                **asdict(spec),
                "period": period,
                "low_bucket": "q1",
                "high_bucket": high_label,
                "low_trades": low_metrics["trades"],
                "high_trades": high_metrics["trades"],
                "low_total_r": low_metrics["total_r"],
                "high_total_r": high_metrics["total_r"],
                "delta_high_minus_low_total_r": round(
                    float(high_metrics["total_r"]) - float(low_metrics["total_r"]),
                    6,
                ),
                "low_avg_r": low_metrics["avg_r"],
                "high_avg_r": high_metrics["avg_r"],
                "delta_high_minus_low_avg_r": round(
                    float(high_metrics["avg_r"]) - float(low_metrics["avg_r"]),
                    6,
                ),
                "low_mfe_ge_2r_pct": low_metrics["mfe_ge_2r_pct"],
                "high_mfe_ge_2r_pct": high_metrics["mfe_ge_2r_pct"],
                "delta_high_minus_low_mfe_ge_2r_pct": round(
                    float(high_metrics["mfe_ge_2r_pct"]) - float(low_metrics["mfe_ge_2r_pct"]),
                    6,
                ),
                "low_max_dd_r": low_metrics["max_dd_r"],
                "high_max_dd_r": high_metrics["max_dd_r"],
            }
        )
    return rows


def filter_candidates(frame: pd.DataFrame, thresholds: pd.DataFrame, specs: list[FeatureSpec]) -> pd.DataFrame:
    spec_by_feature = {spec.feature: spec for spec in specs}
    rows: list[dict[str, object]] = []
    dev = frame[frame["analysis_period"].eq("dev_2021_2024")].copy()

    for row in thresholds.itertuples(index=False):
        spec = spec_by_feature[row.feature]
        values = assign_bucket(frame[spec.feature], json.loads(row.thresholds))
        labels = sorted(values.dropna().unique())
        if not labels:
            continue
        for side, selected in (("low", labels[:1]), ("high", labels[-1:]), ("mid_high", labels[-2:])):
            mask = values.isin(selected)
            dev_group = dev[mask.loc[dev.index]]
            if len(dev_group) < 15:
                continue
            dev_metrics = metrics(dev_group)
            base_dev = metrics(dev)
            inspect_2025 = frame[frame["analysis_period"].eq("inspect_2025")]
            inspect_2026 = frame[frame["analysis_period"].eq("inspect_2026")]
            group_2025 = inspect_2025[mask.loc[inspect_2025.index]]
            group_2026 = inspect_2026[mask.loc[inspect_2026.index]]
            rows.append(
                {
                    **asdict(spec),
                    "selection_side": side,
                    "selected_buckets": ",".join(selected),
                    "dev_trades": dev_metrics["trades"],
                    "dev_trade_keep_pct": round(float(dev_metrics["trades"]) / max(float(base_dev["trades"]), 1.0) * 100.0, 4),
                    "dev_total_r": dev_metrics["total_r"],
                    "dev_avg_r": dev_metrics["avg_r"],
                    "dev_win_rate_pct": dev_metrics["win_rate_pct"],
                    "dev_pf": dev_metrics["profit_factor"],
                    "dev_max_dd_r": dev_metrics["max_dd_r"],
                    "dev_mfe_ge_2r_pct": dev_metrics["mfe_ge_2r_pct"],
                    "dev_delta_avg_r_vs_base": round(float(dev_metrics["avg_r"]) - float(base_dev["avg_r"]), 6),
                    "dev_delta_mfe_ge_2r_vs_base": round(float(dev_metrics["mfe_ge_2r_pct"]) - float(base_dev["mfe_ge_2r_pct"]), 6),
                    "inspect_2025_trades": metrics(group_2025)["trades"],
                    "inspect_2025_total_r": metrics(group_2025)["total_r"],
                    "inspect_2025_avg_r": metrics(group_2025)["avg_r"],
                    "inspect_2025_mfe_ge_2r_pct": metrics(group_2025)["mfe_ge_2r_pct"],
                    "inspect_2026_trades": metrics(group_2026)["trades"],
                    "inspect_2026_total_r": metrics(group_2026)["total_r"],
                    "inspect_2026_avg_r": metrics(group_2026)["avg_r"],
                    "inspect_2026_mfe_ge_2r_pct": metrics(group_2026)["mfe_ge_2r_pct"],
                }
            )

    candidates = pd.DataFrame(rows)
    if candidates.empty:
        return candidates
    candidates["score"] = (
        candidates["dev_delta_avg_r_vs_base"].astype(float) * 10.0
        + candidates["dev_delta_mfe_ge_2r_vs_base"].astype(float) / 10.0
        + candidates["inspect_2025_avg_r"].astype(float)
        + candidates["inspect_2026_avg_r"].astype(float)
    )
    return candidates.sort_values(["causal_use", "score"], ascending=[True, False])


def write_report(
    *,
    output_dir: Path,
    frame: pd.DataFrame,
    bucket_summary: pd.DataFrame,
    contrasts: pd.DataFrame,
    candidates: pd.DataFrame,
) -> None:
    base_rows = []
    for period in ("dev_2021_2024", "inspect_2025", "inspect_2026", "all"):
        subset = frame if period == "all" else frame[frame["analysis_period"].eq(period)]
        base_rows.append({"period": period, **metrics(subset)})
    base = pd.DataFrame(base_rows)

    def table(df: pd.DataFrame, columns: list[str], limit: int = 10) -> str:
        if df.empty:
            return "No rows.\n"
        return df.loc[:, columns].head(limit).to_markdown(index=False)

    top_gap = candidates[candidates["family"].eq("gap_creation")].sort_values("score", ascending=False)
    top_revisit = candidates[candidates["family"].eq("gap_revisit")].sort_values("score", ascending=False)
    top_post = contrasts[contrasts["family"].eq("post_entry")].sort_values(
        "delta_high_minus_low_avg_r",
        ascending=False,
    )

    report = [
        "# NQ NY ORB Gap MBP1 Bucket Screen",
        "",
        "- Source: `nq_ny_orb_gap_orderbook_feature_lab_20260610_scored`",
        "- Thresholds: quartiles fit on `2021-2024` only.",
        "- 2025 and 2026 are inspection slices, not re-fit.",
        "- Post-entry rows are diagnostic only and are not entry filters.",
        "",
        "## Baseline",
        "",
        base.to_markdown(index=False),
        "",
        "## 1. Feature Bucket Screen",
        "",
        "See `feature_bucket_summary.csv` for every feature/bucket/period. The ranked candidate table below keeps only simple low/high/mid-high bucket selections with at least 15 development trades.",
        "",
        table(
            candidates,
            [
                "family",
                "feature",
                "selection_side",
                "selected_buckets",
                "dev_trades",
                "dev_avg_r",
                "dev_delta_avg_r_vs_base",
                "dev_mfe_ge_2r_pct",
                "inspect_2025_avg_r",
                "inspect_2026_avg_r",
                "score",
            ],
            12,
        ),
        "",
        "## 2. Gap-Creation Impulse",
        "",
        table(
            top_gap,
            [
                "feature",
                "selection_side",
                "selected_buckets",
                "dev_trades",
                "dev_avg_r",
                "dev_mfe_ge_2r_pct",
                "inspect_2025_trades",
                "inspect_2025_avg_r",
                "inspect_2026_trades",
                "inspect_2026_avg_r",
            ],
            10,
        ),
        "",
        "## 3. Revisit / Pre-Entry Avoidance",
        "",
        table(
            top_revisit,
            [
                "feature",
                "selection_side",
                "selected_buckets",
                "dev_trades",
                "dev_avg_r",
                "dev_mfe_ge_2r_pct",
                "inspect_2025_trades",
                "inspect_2025_avg_r",
                "inspect_2026_trades",
                "inspect_2026_avg_r",
            ],
            10,
        ),
        "",
        "## 4. Post-Entry Diagnostics",
        "",
        table(
            top_post,
            [
                "feature",
                "period",
                "low_trades",
                "high_trades",
                "low_avg_r",
                "high_avg_r",
                "delta_high_minus_low_avg_r",
                "low_mfe_ge_2r_pct",
                "high_mfe_ge_2r_pct",
            ],
            10,
        ),
        "",
        "## Interpretation Guardrails",
        "",
        "- Any entry candidate must come from `entry_causal` rows only.",
        "- Post-entry correlations can become management/scratch research, not entry gates.",
        "- Candidates with tiny inspection trade counts are hypothesis generators only.",
    ]
    (output_dir / "report.md").write_text("\n".join(report) + "\n")
    base.to_csv(output_dir / "baseline_period_metrics.csv", index=False)


def run(args: argparse.Namespace) -> int:
    input_path = Path(args.input_csv)
    if not input_path.exists():
        raise SystemExit(f"Input CSV not found: {input_path}")
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    frame = pd.read_csv(input_path)
    frame["date"] = pd.to_datetime(frame["date"])
    frame["analysis_period"] = frame["date"].map(period_for_date)
    frame = frame[frame["setup_found"].astype(bool) & frame["orderbook_file_found"].astype(bool)].copy()

    specs = feature_specs(set(frame.columns))
    thresholds, bucket_summary, contrasts = bucket_screen(frame, specs)
    candidates = filter_candidates(frame, thresholds, specs)

    thresholds.to_csv(output_dir / "feature_thresholds.csv", index=False)
    bucket_summary.to_csv(output_dir / "feature_bucket_summary.csv", index=False)
    contrasts.to_csv(output_dir / "feature_bucket_contrasts.csv", index=False)
    candidates.to_csv(output_dir / "candidate_bucket_filters.csv", index=False)
    write_report(
        output_dir=output_dir,
        frame=frame,
        bucket_summary=bucket_summary,
        contrasts=contrasts,
        candidates=candidates,
    )

    summary = {
        "input_csv": str(input_path),
        "output_dir": str(output_dir),
        "rows": int(len(frame)),
        "features_tested": int(len(thresholds)),
        "bucket_rows": int(len(bucket_summary)),
        "candidate_rows": int(len(candidates)),
        "entry_causal_candidates": int(candidates["causal_use"].eq("entry_causal").sum()) if not candidates.empty else 0,
        "diagnostic_candidates": int(candidates["causal_use"].eq("diagnostic_only").sum()) if not candidates.empty else 0,
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
