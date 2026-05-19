#!/usr/bin/env python3
"""Freeze NQ LSI order-book impulse gates on validation, then replay holdout.

This consumes the per-trade feature CSVs produced by
run_nq_ny_lsi_orderbook_impulse.py. Thresholds are selected from validation
features only, then replayed unchanged on holdout features.

If validation coverage is partial, the report keeps that limitation explicit.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_nq_ny_lsi_cisd_candidate_validation as val


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VALIDATION_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_impulse_validation_partial_20260514"
    / "trade_orderbook_impulse.csv"
)
DEFAULT_HOLDOUT_CSV = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_impulse_20260513"
    / "trade_orderbook_impulse.csv"
)
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_lsi_orderbook_impulse_frozen_replay_20260514"
DEFAULT_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_ORDERBOOK_IMPULSE_FROZEN_REPLAY_20260514.md"

SCORE_COLUMNS = (
    "impulse_score",
    "pressure_score",
    "price_impulse_score",
    "aggression_imbalance",
    "aligned_aggression_rate_ratio",
    "mid_velocity_ratio",
    "mid_velocity_ticks_per_second",
    "mid_move_ticks",
    "volume_rate_ratio",
    "aligned_depth_imbalance_3_mean",
)


def clean_feature_frame(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    if "has_orderbook_data" in frame.columns:
        if frame["has_orderbook_data"].dtype != bool:
            frame["has_orderbook_data"] = frame["has_orderbook_data"].astype(str).str.lower().eq("true")
    else:
        frame["has_orderbook_data"] = False
    for column in SCORE_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)
    frame["r_multiple"] = pd.to_numeric(frame["r_multiple"], errors="coerce")
    return frame


def metrics(prefix: str, subset: pd.DataFrame) -> dict[str, Any]:
    out = {f"{prefix}_{key}": value for key, value in val.r_metrics(subset["r_multiple"].dropna().to_numpy()).items()}
    out[f"{prefix}_coverage_rows"] = int(len(subset))
    return out


def threshold_grid(values: pd.Series, column: str) -> list[tuple[str, float, str]]:
    values = values.replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return []
    thresholds = [
        (f"{column}_q50", float(values.quantile(0.50)), "validation_quantile"),
        (f"{column}_q60", float(values.quantile(0.60)), "validation_quantile"),
        (f"{column}_q70", float(values.quantile(0.70)), "validation_quantile"),
        (f"{column}_q80", float(values.quantile(0.80)), "validation_quantile"),
    ]
    if column in {"impulse_score", "pressure_score", "price_impulse_score"}:
        thresholds.extend(
            [
                (f"{column}_ge_0p5", 0.5, "absolute"),
                (f"{column}_ge_1", 1.0, "absolute"),
                (f"{column}_ge_2", 2.0, "absolute"),
                (f"{column}_ge_3", 3.0, "absolute"),
            ]
        )
    elif column == "aggression_imbalance":
        thresholds.extend(
            [
                (f"{column}_ge_0p10", 0.10, "absolute"),
                (f"{column}_ge_0p25", 0.25, "absolute"),
                (f"{column}_ge_0p50", 0.50, "absolute"),
            ]
        )
    elif column == "volume_rate_ratio":
        thresholds.extend(
            [
                (f"{column}_ge_1", 1.0, "absolute"),
                (f"{column}_ge_1p5", 1.5, "absolute"),
                (f"{column}_ge_2", 2.0, "absolute"),
            ]
        )
    elif column == "aligned_depth_imbalance_3_mean":
        thresholds.extend(
            [
                (f"{column}_ge_0", 0.0, "absolute"),
                (f"{column}_ge_0p10", 0.10, "absolute"),
            ]
        )
    return thresholds


def select_candidate_gates(
    validation: pd.DataFrame,
    holdout: pd.DataFrame,
    *,
    min_validation_trades: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    all_rows: list[dict[str, Any]] = []
    selected_rows: list[dict[str, Any]] = []
    candidates = sorted(set(validation["candidate"].dropna()) | set(holdout["candidate"].dropna()))

    for candidate in candidates:
        validation_all = validation[validation["candidate"] == candidate].copy()
        holdout_all = holdout[holdout["candidate"] == candidate].copy()
        validation_scored = validation_all[validation_all["has_orderbook_data"]].copy()
        holdout_scored = holdout_all[holdout_all["has_orderbook_data"]].copy()
        validation_base = val.r_metrics(validation_scored["r_multiple"].dropna().to_numpy())

        candidate_rows: list[dict[str, Any]] = []
        for column in SCORE_COLUMNS:
            if column not in validation_scored.columns or column not in holdout_scored.columns:
                continue
            for gate, threshold, source in threshold_grid(validation_scored[column], column):
                validation_gate = validation_scored[validation_scored[column] >= threshold]
                if len(validation_gate) < min_validation_trades:
                    continue
                holdout_gate = holdout_scored[holdout_scored[column] >= threshold]
                validation_metrics = val.r_metrics(validation_gate["r_multiple"].dropna().to_numpy())
                holdout_metrics = val.r_metrics(holdout_gate["r_multiple"].dropna().to_numpy())
                row: dict[str, Any] = {
                    "candidate": candidate,
                    "gate": gate,
                    "score_column": column,
                    "threshold": threshold,
                    "threshold_source": source,
                    "validation_scored_rows": int(len(validation_scored)),
                    "validation_total_rows": int(len(validation_all)),
                    "validation_feature_coverage": float(len(validation_scored) / len(validation_all)) if len(validation_all) else 0.0,
                    "holdout_scored_rows": int(len(holdout_scored)),
                    "holdout_total_rows": int(len(holdout_all)),
                    "holdout_feature_coverage": float(len(holdout_scored) / len(holdout_all)) if len(holdout_all) else 0.0,
                    "validation_delta_avg_r": float(validation_metrics["avg_r"] - validation_base["avg_r"]),
                    "validation_delta_calmar": float(validation_metrics["calmar"] - validation_base["calmar"]),
                    "validation_trade_retention": float(len(validation_gate) / len(validation_scored)) if len(validation_scored) else 0.0,
                    "holdout_trade_retention": float(len(holdout_gate) / len(holdout_scored)) if len(holdout_scored) else 0.0,
                }
                row.update({f"validation_{key}": value for key, value in validation_metrics.items()})
                row.update({f"holdout_{key}": value for key, value in holdout_metrics.items()})
                candidate_rows.append(row)

        all_rows.extend(candidate_rows)
        if candidate_rows:
            ranked = sorted(
                candidate_rows,
                key=lambda row: (
                    row["validation_calmar"],
                    row["validation_profit_factor"],
                    row["validation_total_r"],
                    row["validation_trades"],
                    row["holdout_trades"],
                ),
                reverse=True,
            )
            selected_rows.append({**ranked[0], "selection_status": "selected"})
        else:
            row = {
                "candidate": candidate,
                "gate": "",
                "score_column": "",
                "threshold": math.nan,
                "threshold_source": "",
                "selection_status": "no_validation_gate_met_min_trades",
                "validation_scored_rows": int(len(validation_scored)),
                "validation_total_rows": int(len(validation_all)),
                "validation_feature_coverage": float(len(validation_scored) / len(validation_all)) if len(validation_all) else 0.0,
                "holdout_scored_rows": int(len(holdout_scored)),
                "holdout_total_rows": int(len(holdout_all)),
                "holdout_feature_coverage": float(len(holdout_scored) / len(holdout_all)) if len(holdout_all) else 0.0,
            }
            row.update({f"validation_baseline_scored_{key}": value for key, value in val.r_metrics(validation_scored["r_multiple"].dropna().to_numpy()).items()})
            row.update({f"holdout_baseline_scored_{key}": value for key, value in val.r_metrics(holdout_scored["r_multiple"].dropna().to_numpy()).items()})
            selected_rows.append(row)

    return pd.DataFrame(all_rows), pd.DataFrame(selected_rows)


def baseline_rows(validation: pd.DataFrame, holdout: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for period, frame in (("validation", validation), ("holdout", holdout)):
        for candidate, group in frame.groupby("candidate"):
            scored = group[group["has_orderbook_data"]]
            row = {
                "period": period,
                "candidate": candidate,
                "total_rows": int(len(group)),
                "scored_rows": int(len(scored)),
                "feature_coverage": float(len(scored) / len(group)) if len(group) else 0.0,
            }
            row.update({f"all_{key}": value for key, value in val.r_metrics(group["r_multiple"].dropna().to_numpy()).items()})
            row.update({f"scored_{key}": value for key, value in val.r_metrics(scored["r_multiple"].dropna().to_numpy()).items()})
            rows.append(row)
    return pd.DataFrame(rows)


def write_report(
    *,
    path: Path,
    selected: pd.DataFrame,
    baselines: pd.DataFrame,
    validation_csv: Path,
    holdout_csv: Path,
    min_validation_trades: int,
) -> None:
    validation_total = int(baselines[baselines["period"] == "validation"]["total_rows"].sum())
    validation_scored = int(baselines[baselines["period"] == "validation"]["scored_rows"].sum())
    holdout_total = int(baselines[baselines["period"] == "holdout"]["total_rows"].sum())
    holdout_scored = int(baselines[baselines["period"] == "holdout"]["scored_rows"].sum())
    validation_coverage = validation_scored / validation_total if validation_total else 0.0
    if validation_coverage >= 0.95:
        data_status = "- Data status: validation coverage is effectively complete; unmatched rows are tiny/no-data windows."
    else:
        data_status = (
            "- Important limitation: validation coverage is incomplete. Treat this as a pipeline check, "
            "not a final feature verdict."
        )
    lines = [
        "# NQ LSI Order-Book Impulse Frozen Threshold Replay",
        "",
        "- Method: select candidate-specific order-book gates on validation rows only, then replay the frozen threshold on holdout rows.",
        f"- Validation CSV: `{validation_csv}`.",
        f"- Holdout CSV: `{holdout_csv}`.",
        f"- Minimum validation trades per selected gate: `{min_validation_trades}`.",
        f"- Validation feature coverage: `{validation_scored}/{validation_total}` rows.",
        f"- Holdout feature coverage: `{holdout_scored}/{holdout_total}` rows.",
        data_status,
        "",
        "## Selected Validation Gates Replayed On Holdout",
        "",
        "| Candidate | Status | Gate | Val Trades | Val PF | Val Avg R | Val R | Holdout Trades | Holdout PF | Holdout Avg R | Holdout R |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in selected.sort_values("candidate").iterrows():
        status = row.get("selection_status", "selected")
        if status != "selected":
            lines.append(
                f"| `{row['candidate']}` | {status} | n/a | 0 | 0.000 | 0.000 | 0.00 | 0 | 0.000 | 0.000 | 0.00 |"
            )
            continue
        lines.append(
            f"| `{row['candidate']}` | selected | `{row['gate']}` @ {float(row['threshold']):.4f} | "
            f"{int(row['validation_trades'])} | {float(row['validation_profit_factor']):.3f} | "
            f"{float(row['validation_avg_r']):.3f} | {float(row['validation_total_r']):.2f} | "
            f"{int(row['holdout_trades'])} | {float(row['holdout_profit_factor']):.3f} | "
            f"{float(row['holdout_avg_r']):.3f} | {float(row['holdout_total_r']):.2f} |"
        )

    lines.extend(
        [
            "",
            "## Baseline Coverage",
            "",
            "| Period | Candidate | Rows | Scored | Coverage | All PF | All Avg R | Scored PF | Scored Avg R |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in baselines.sort_values(["period", "candidate"]).iterrows():
        lines.append(
            f"| {row['period']} | `{row['candidate']}` | {int(row['total_rows'])} | {int(row['scored_rows'])} | "
            f"{float(row['feature_coverage']):.1%} | {float(row['all_profit_factor']):.3f} | "
            f"{float(row['all_avg_r']):.3f} | {float(row['scored_profit_factor']):.3f} | "
            f"{float(row['scored_avg_r']):.3f} |"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-csv", type=Path, default=DEFAULT_VALIDATION_CSV)
    parser.add_argument("--holdout-csv", type=Path, default=DEFAULT_HOLDOUT_CSV)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--min-validation-trades", type=int, default=8)
    args = parser.parse_args()

    validation = clean_feature_frame(args.validation_csv)
    holdout = clean_feature_frame(args.holdout_csv)
    all_gates, selected = select_candidate_gates(
        validation,
        holdout,
        min_validation_trades=args.min_validation_trades,
    )
    baselines = baseline_rows(validation, holdout)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_gates_path = args.output_dir / "validation_gate_candidates.csv"
    selected_path = args.output_dir / "selected_frozen_replay.csv"
    baseline_path = args.output_dir / "baseline_coverage.csv"
    summary_path = args.output_dir / "summary.json"
    all_gates.to_csv(all_gates_path, index=False)
    selected.to_csv(selected_path, index=False)
    baselines.to_csv(baseline_path, index=False)
    summary = {
        "validation_csv": str(args.validation_csv),
        "holdout_csv": str(args.holdout_csv),
        "min_validation_trades": args.min_validation_trades,
        "validation_rows": int(len(validation)),
        "validation_scored_rows": int(validation["has_orderbook_data"].sum()),
        "holdout_rows": int(len(holdout)),
        "holdout_scored_rows": int(holdout["has_orderbook_data"].sum()),
        "data_status": (
            "effectively_complete"
            if float(validation["has_orderbook_data"].mean()) >= 0.95
            else "partial_validation_coverage"
        ),
        "outputs": {
            "validation_gate_candidates": str(all_gates_path),
            "selected_frozen_replay": str(selected_path),
            "baseline_coverage": str(baseline_path),
            "report": str(args.report_path),
        },
    }
    summary_path.write_text(json.dumps(summary, indent=2, default=str))
    write_report(
        path=args.report_path,
        selected=selected,
        baselines=baselines,
        validation_csv=args.validation_csv,
        holdout_csv=args.holdout_csv,
        min_validation_trades=args.min_validation_trades,
    )
    print(f"Wrote {all_gates_path}", flush=True)
    print(f"Wrote {selected_path}", flush=True)
    print(f"Wrote {baseline_path}", flush=True)
    print(f"Wrote {args.report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
