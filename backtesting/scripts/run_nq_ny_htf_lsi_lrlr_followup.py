#!/usr/bin/env python3
"""Follow-up study for LRLR-lite and TP1-aware LRLR on the NQ NY 2m HTF-LSI anchor."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    VALIDATION_START,
    build_config,
    load_timeframe_data,
    save_json,
    slice_trades,
)


OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lrlr_followup"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_LRLR_FOLLOWUP.md"

BASE_PARAMS = {
    "timeframe": "2m",
    "direction_filter": "long",
    "entry_mode": "fvg_limit",
    "htf_trade_max_per_session": 1,
    "rr": 3.0,
    "tp1_ratio": 0.6,
    "min_gap_atr_pct": 3.0,
    "atr_length": 14,
    "htf_level_tf_minutes": 60,
    "htf_n_left": 3,
    "lsi_fvg_window_left": 50,
    "lsi_fvg_window_right": 5,
    "max_fvg_to_inversion_bars": 0,
}

LRLR_BASE = {
    "lsi_lrlr_enabled": True,
    "lsi_lrlr_gate": "",
    "lsi_lrlr_swing_n_left": 2,
    "lsi_lrlr_swing_n_right": 2,
    "lsi_lrlr_min_pivots": 2,
    "lsi_lrlr_lookback_minutes": 120,
    "lsi_lrlr_max_cluster_span_minutes": 120,
    "lsi_lrlr_max_price_span_atr": 0.18,
    "lsi_lrlr_monotonic_tolerance_atr": 0.03,
    "lsi_lrlr_line_tolerance_atr": 0.04,
}

LITE_GAPS = (30, 40)
TP1_BUFFERS = (0.0, 0.1, 0.2, 0.3)


def snapshot(metrics: dict) -> dict:
    keep = (
        "total_signals",
        "total_trades",
        "no_fills",
        "win_rate",
        "profit_factor",
        "avg_r",
        "total_r",
        "calmar_ratio",
        "max_drawdown_r",
        "sharpe_ratio",
    )
    snap = {}
    for key in keep:
        value = metrics.get(key, 0.0)
        if isinstance(value, (int, float)):
            snap[key] = round(float(value), 4)
        else:
            snap[key] = value
    return snap


def summarize_periods(trades) -> dict[str, dict]:
    return {
        "pre_holdout": snapshot(compute_metrics(slice_trades(trades, DISCOVERY_START, HOLDOUT_START))),
        "discovery": snapshot(compute_metrics(slice_trades(trades, DISCOVERY_START, VALIDATION_START))),
        "validation": snapshot(compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START))),
    }


def segment_payload(trades, predicate) -> dict:
    selected = [trade for trade in trades if predicate(trade)]
    rejected = [trade for trade in trades if not predicate(trade)]
    totals = summarize_periods(trades)
    selected_metrics = summarize_periods(selected)
    rejected_metrics = summarize_periods(rejected)
    coverage = {}
    for bucket in ("pre_holdout", "discovery", "validation"):
        total_signals = max(float(totals[bucket]["total_signals"]), 1.0)
        total_trades = max(float(totals[bucket]["total_trades"]), 1.0)
        coverage[bucket] = {
            "signal_share": round(float(selected_metrics[bucket]["total_signals"]) / total_signals, 4),
            "filled_share": round(float(selected_metrics[bucket]["total_trades"]) / total_trades, 4),
        }
    return {
        "all": totals,
        "selected": selected_metrics,
        "rejected": rejected_metrics,
        "coverage": coverage,
    }


def build_branch_config(label: str):
    return build_config(name=f"NQ NY HTF_LSI LRLR followup {label}", **BASE_PARAMS)


def with_lrlr(
    config,
    *,
    name_suffix: str,
    gate: str = "",
    tp1_path_enabled: bool = False,
    tp1_buffer_atr: float = 0.0,
    **overrides,
):
    return dataclasses.replace(
        config,
        name=f"{config.name} {name_suffix}",
        lsi_lrlr_enabled=True,
        lsi_lrlr_gate=gate,
        lsi_lrlr_tp1_path_enabled=tp1_path_enabled,
        lsi_lrlr_tp1_buffer_atr=tp1_buffer_atr,
        **{
            **{k: v for k, v in LRLR_BASE.items() if k not in {"lsi_lrlr_enabled", "lsi_lrlr_gate"}},
            **overrides,
        },
    )


def validation_tuple(row: dict) -> tuple[float, float, float]:
    validation = row["require_gate"]["validation"]
    discovery = row["require_gate"]["discovery"]
    return (
        float(validation["calmar_ratio"]),
        float(validation["profit_factor"]),
        float(discovery["profit_factor"]),
    )


def write_report(summary: dict) -> None:
    baseline = summary["baseline"]
    lite_rows = summary["lite_variants"]
    tp1_rows = summary["tp1_variants"]
    best_lite = max(lite_rows, key=validation_tuple)
    best_tp1 = max(tp1_rows, key=validation_tuple)

    lines = [
        "# NQ NY HTF-LSI LRLR Follow-up",
        "",
        "- Scope: pre-holdout only (`2016-01-01` to `2025-03-31`). Holdout remains closed.",
        "- Anchor: `2m` NQ NY HTF-LSI long branch (`fvg_limit`, `cap1`, `rr=3.0`, `tp1=0.6`).",
        "- Pass 1: LRLR-lite = `2` unswept pivots with `30m` or `40m` max pivot spacing.",
        "- Pass 2: TP1-aware LRLR = LRLR-lite plus the nearest LRLR level must sit inside TP1, optionally with an ATR buffer.",
        "",
        (
            f"- Baseline validation: PF `{baseline['validation']['profit_factor']:.3f}` / "
            f"Avg R `{baseline['validation']['avg_r']:.3f}` / "
            f"Calmar `{baseline['validation']['calmar_ratio']:.3f}` / "
            f"trades `{int(baseline['validation']['total_trades'])}`"
        ),
        (
            f"- Best LRLR-lite gate: gap `{best_lite['max_pivot_gap_minutes']}m` -> "
            f"PF `{best_lite['require_gate']['validation']['profit_factor']:.3f}` / "
            f"Avg R `{best_lite['require_gate']['validation']['avg_r']:.3f}` / "
            f"Calmar `{best_lite['require_gate']['validation']['calmar_ratio']:.3f}` / "
            f"trades `{int(best_lite['require_gate']['validation']['total_trades'])}`"
        ),
        (
            f"- Best TP1-aware gate: gap `{best_tp1['max_pivot_gap_minutes']}m`, buffer `{best_tp1['tp1_buffer_atr']:.1f} ATR` -> "
            f"PF `{best_tp1['require_gate']['validation']['profit_factor']:.3f}` / "
            f"Avg R `{best_tp1['require_gate']['validation']['avg_r']:.3f}` / "
            f"Calmar `{best_tp1['require_gate']['validation']['calmar_ratio']:.3f}` / "
            f"trades `{int(best_tp1['require_gate']['validation']['total_trades'])}`"
        ),
        "",
        "## LRLR-lite",
        "",
        "| Max Gap (m) | Segmented Val PF | Segmented Val Avg R | Segmented Share | Require Val PF | Require Val Avg R | Require Val Calmar | Require Trades | Exclude Val PF | Exclude Val Avg R |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in sorted(lite_rows, key=validation_tuple, reverse=True):
        seg = row["annotated"]["selected"]["validation"]
        cov = row["annotated"]["coverage"]["validation"]
        req = row["require_gate"]["validation"]
        exc = row["exclude_gate"]["validation"]
        lines.append(
            f"| {row['max_pivot_gap_minutes']} | {seg['profit_factor']:.3f} | {seg['avg_r']:.3f} | "
            f"{cov['filled_share']:.1%} | {req['profit_factor']:.3f} | {req['avg_r']:.3f} | "
            f"{req['calmar_ratio']:.3f} | {int(req['total_trades'])} | {exc['profit_factor']:.3f} | {exc['avg_r']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## TP1-aware LRLR",
            "",
            "| Max Gap (m) | Buffer (ATR) | TP1-Qualified Val PF | TP1-Qualified Val Avg R | TP1 Share | Require Val PF | Require Val Avg R | Require Val Calmar | Require Trades | Exclude Val PF | Exclude Val Avg R |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )

    for row in sorted(tp1_rows, key=validation_tuple, reverse=True):
        seg = row["annotated"]["selected"]["validation"]
        cov = row["annotated"]["coverage"]["validation"]
        req = row["require_gate"]["validation"]
        exc = row["exclude_gate"]["validation"]
        lines.append(
            f"| {row['max_pivot_gap_minutes']} | {row['tp1_buffer_atr']:.1f} | {seg['profit_factor']:.3f} | "
            f"{seg['avg_r']:.3f} | {cov['filled_share']:.1%} | {req['profit_factor']:.3f} | "
            f"{req['avg_r']:.3f} | {req['calmar_ratio']:.3f} | {int(req['total_trades'])} | "
            f"{exc['profit_factor']:.3f} | {exc['avg_r']:.3f} |"
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("2m")
    base = build_branch_config("baseline")

    configs = [base]
    lite_defs = []
    tp1_defs = []

    for max_gap in LITE_GAPS:
        annotated = with_lrlr(
            base,
            name_suffix=f"lite_gap{max_gap}_annotated",
            gate="",
            lsi_lrlr_max_pivot_gap_minutes=max_gap,
        )
        require = with_lrlr(
            base,
            name_suffix=f"lite_gap{max_gap}_require",
            gate="require",
            lsi_lrlr_max_pivot_gap_minutes=max_gap,
        )
        exclude = with_lrlr(
            base,
            name_suffix=f"lite_gap{max_gap}_exclude",
            gate="exclude",
            lsi_lrlr_max_pivot_gap_minutes=max_gap,
        )
        configs.extend([annotated, require, exclude])
        lite_defs.append(
            {
                "max_pivot_gap_minutes": max_gap,
                "annotated_name": annotated.name,
                "require_name": require.name,
                "exclude_name": exclude.name,
            }
        )

        for buffer in TP1_BUFFERS:
            annotated_tp1 = with_lrlr(
                base,
                name_suffix=f"lite_gap{max_gap}_tp1_{buffer:.1f}_annotated",
                gate="",
                tp1_path_enabled=True,
                tp1_buffer_atr=buffer,
                lsi_lrlr_max_pivot_gap_minutes=max_gap,
            )
            require_tp1 = with_lrlr(
                base,
                name_suffix=f"lite_gap{max_gap}_tp1_{buffer:.1f}_require",
                gate="require",
                tp1_path_enabled=True,
                tp1_buffer_atr=buffer,
                lsi_lrlr_max_pivot_gap_minutes=max_gap,
            )
            exclude_tp1 = with_lrlr(
                base,
                name_suffix=f"lite_gap{max_gap}_tp1_{buffer:.1f}_exclude",
                gate="exclude",
                tp1_path_enabled=True,
                tp1_buffer_atr=buffer,
                lsi_lrlr_max_pivot_gap_minutes=max_gap,
            )
            configs.extend([annotated_tp1, require_tp1, exclude_tp1])
            tp1_defs.append(
                {
                    "max_pivot_gap_minutes": max_gap,
                    "tp1_buffer_atr": buffer,
                    "annotated_name": annotated_tp1.name,
                    "require_name": require_tp1.name,
                    "exclude_name": exclude_tp1.name,
                }
            )

    print(f"Running LRLR follow-up packet with {len(configs)} configs...", flush=True)
    results = run_sweep(
        df_base,
        configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    by_name = {cfg.name: trades for cfg, trades in results}

    summary = {
        "baseline": summarize_periods(by_name[base.name]),
        "lite_variants": [],
        "tp1_variants": [],
    }

    for row in lite_defs:
        annotated_trades = by_name[row["annotated_name"]]
        summary["lite_variants"].append(
            {
                "max_pivot_gap_minutes": row["max_pivot_gap_minutes"],
                "annotated": segment_payload(annotated_trades, lambda trade: bool(trade.lsi_lrlr_present)),
                "require_gate": summarize_periods(by_name[row["require_name"]]),
                "exclude_gate": summarize_periods(by_name[row["exclude_name"]]),
            }
        )

    for row in tp1_defs:
        annotated_trades = by_name[row["annotated_name"]]
        summary["tp1_variants"].append(
            {
                "max_pivot_gap_minutes": row["max_pivot_gap_minutes"],
                "tp1_buffer_atr": row["tp1_buffer_atr"],
                "annotated": segment_payload(
                    annotated_trades,
                    lambda trade: bool(trade.lsi_lrlr_present and trade.lsi_lrlr_tp1_path_present),
                ),
                "require_gate": summarize_periods(by_name[row["require_name"]]),
                "exclude_gate": summarize_periods(by_name[row["exclude_name"]]),
            }
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", summary)
    write_report(summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
