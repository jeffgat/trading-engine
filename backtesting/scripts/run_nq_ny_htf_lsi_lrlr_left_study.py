#!/usr/bin/env python3
"""Study left-side LRLR context on NQ NY HTF-LSI branches.

The workflow keeps holdout closed and asks two questions:
1. On the annotated ungated branch, do trades with LRLR context outperform trades without it?
2. Does requiring LRLR improve the branch once trade-slot competition is handled honestly inside the engine?
"""

from __future__ import annotations

import dataclasses
import json
import sys
from itertools import product
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
    ensure_required_data,
    load_timeframe_data,
    save_json,
    slice_trades,
)


OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lrlr_left_study"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_LRLR_LEFT_STUDY.md"

LRLR_DEFAULTS = {
    "lsi_lrlr_enabled": True,
    "lsi_lrlr_gate": "",
    "lsi_lrlr_swing_n_left": 2,
    "lsi_lrlr_swing_n_right": 2,
    "lsi_lrlr_min_pivots": 3,
    "lsi_lrlr_lookback_minutes": 120,
    "lsi_lrlr_max_pivot_gap_minutes": 30,
    "lsi_lrlr_max_cluster_span_minutes": 120,
    "lsi_lrlr_max_price_span_atr": 0.18,
    "lsi_lrlr_monotonic_tolerance_atr": 0.03,
    "lsi_lrlr_line_tolerance_atr": 0.04,
}

BRANCHES = {
    "2m_anchor": {
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
    },
    "1m_candidate": {
        "timeframe": "1m",
        "direction_filter": "long",
        "entry_mode": "close",
        "htf_trade_max_per_session": 2,
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "lsi_fvg_window_left": 100,
        "lsi_fvg_window_right": 10,
        "max_fvg_to_inversion_bars": 0,
    },
    "3m_candidate": {
        "timeframe": "3m",
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "htf_trade_max_per_session": 2,
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "lsi_fvg_window_left": 33,
        "lsi_fvg_window_right": 3,
        "max_fvg_to_inversion_bars": 0,
    },
    "5m_candidate": {
        "timeframe": "5m",
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "htf_trade_max_per_session": 2,
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "lsi_fvg_window_left": 20,
        "lsi_fvg_window_right": 2,
        "max_fvg_to_inversion_bars": 0,
    },
}


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


def build_branch_config(label: str, params: dict):
    return build_config(name=f"NQ NY HTF_LSI LRLR {label}", **params)


def with_lrlr(config, *, gate: str = "", name_suffix: str, **overrides):
    return dataclasses.replace(
        config,
        name=f"{config.name} {name_suffix}",
        lsi_lrlr_enabled=True,
        lsi_lrlr_gate=gate,
        **{
            **{k: v for k, v in LRLR_DEFAULTS.items() if k not in {"lsi_lrlr_enabled", "lsi_lrlr_gate"}},
            **overrides,
        },
    )


def lrlr_segment_payload(trades) -> dict:
    present = [trade for trade in trades if trade.lsi_lrlr_present]
    absent = [trade for trade in trades if not trade.lsi_lrlr_present]
    totals = summarize_periods(trades)
    present_metrics = summarize_periods(present)
    absent_metrics = summarize_periods(absent)
    coverage = {}
    for bucket in ("pre_holdout", "discovery", "validation"):
        total_signals = max(float(totals[bucket]["total_signals"]), 1.0)
        total_trades = max(float(totals[bucket]["total_trades"]), 1.0)
        coverage[bucket] = {
            "signal_share": round(float(present_metrics[bucket]["total_signals"]) / total_signals, 4),
            "filled_share": round(float(present_metrics[bucket]["total_trades"]) / total_trades, 4),
        }
    return {
        "all": totals,
        "present": present_metrics,
        "absent": absent_metrics,
        "coverage": coverage,
    }


def run_branch(label: str, params: dict) -> dict:
    timeframe = params["timeframe"]
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
    base = build_branch_config(label, params)
    annotated = with_lrlr(base, gate="", name_suffix="annotated")
    require = with_lrlr(base, gate="require", name_suffix="require")
    exclude = with_lrlr(base, gate="exclude", name_suffix="exclude")
    configs = [annotated, require, exclude]

    print(f"Running {label} ({timeframe}) baseline + LRLR gates...", flush=True)
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

    annotated_trades = by_name[annotated.name]
    require_trades = by_name[require.name]
    exclude_trades = by_name[exclude.name]
    return {
        "label": label,
        "timeframe": timeframe,
        "config": {k: v for k, v in params.items() if k != "timeframe"},
        "lrlr_defaults": LRLR_DEFAULTS,
        "annotated": lrlr_segment_payload(annotated_trades),
        "require_gate": summarize_periods(require_trades),
        "exclude_gate": summarize_periods(exclude_trades),
    }


def run_2m_sensitivity() -> list[dict]:
    params = BRANCHES["2m_anchor"]
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("2m")
    anchor = build_branch_config("2m_anchor_sensitivity", params)
    configs = []
    grid_rows = []
    for min_pivots, max_gap in product((2, 3, 4), (20, 30, 40)):
        cfg = with_lrlr(
            anchor,
            gate="require",
            name_suffix=f"p{min_pivots}_gap{max_gap}",
            lsi_lrlr_min_pivots=min_pivots,
            lsi_lrlr_max_pivot_gap_minutes=max_gap,
        )
        configs.append(cfg)
        grid_rows.append((min_pivots, max_gap, cfg.name))

    print("Running 2m LRLR sensitivity packet...", flush=True)
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

    rows = []
    for min_pivots, max_gap, name in grid_rows:
        metrics = summarize_periods(by_name[name])
        rows.append(
            {
                "min_pivots": min_pivots,
                "max_pivot_gap_minutes": max_gap,
                "pre_holdout": metrics["pre_holdout"],
                "discovery": metrics["discovery"],
                "validation": metrics["validation"],
            }
        )
    rows.sort(
        key=lambda row: (
            row["validation"]["calmar_ratio"],
            row["validation"]["profit_factor"],
            row["discovery"]["profit_factor"],
        ),
        reverse=True,
    )
    return rows


def write_report(branch_rows: list[dict], sensitivity_rows: list[dict]) -> None:
    lines = [
        "# NQ NY HTF-LSI LRLR Left Study",
        "",
        "- Scope: pre-holdout only (`2016-01-01` to `2025-03-31`). Holdout remains closed.",
        "- Question: does a left-side LRLR structure help HTF-LSI branches enough to justify a hard gate?",
        "- LRLR defaults: descending/ascending unswept pivot chain with `min_pivots=3`, `lookback=120m`, `max_gap=30m`, `max_price_span=0.18 ATR`, `line_tol=0.04 ATR`.",
        "",
    ]

    for row in branch_rows:
        annotated = row["annotated"]
        require_gate = row["require_gate"]["validation"]
        exclude_gate = row["exclude_gate"]["validation"]
        lines.extend(
            [
                f"## {row['label']}",
                "",
                f"- Timeframe: `{row['timeframe']}`",
                (
                    f"- Validation segmentation: LRLR-present PF `{annotated['present']['validation']['profit_factor']:.3f}` / "
                    f"Avg R `{annotated['present']['validation']['avg_r']:.3f}` / Calmar `{annotated['present']['validation']['calmar_ratio']:.3f}` "
                    f"vs LRLR-absent PF `{annotated['absent']['validation']['profit_factor']:.3f}` / "
                    f"Avg R `{annotated['absent']['validation']['avg_r']:.3f}` / Calmar `{annotated['absent']['validation']['calmar_ratio']:.3f}`"
                ),
                (
                    f"- Validation LRLR share: signals `{annotated['coverage']['validation']['signal_share']:.1%}`, "
                    f"filled trades `{annotated['coverage']['validation']['filled_share']:.1%}`"
                ),
                (
                    f"- Honest gate compare: `require` PF `{require_gate['profit_factor']:.3f}` / Avg R `{require_gate['avg_r']:.3f}` / "
                    f"Calmar `{require_gate['calmar_ratio']:.3f}` / trades `{int(require_gate['total_trades'])}`; "
                    f"`exclude` PF `{exclude_gate['profit_factor']:.3f}` / Avg R `{exclude_gate['avg_r']:.3f}` / "
                    f"Calmar `{exclude_gate['calmar_ratio']:.3f}` / trades `{int(exclude_gate['total_trades'])}`"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## 2m Sensitivity",
            "",
            "| Min Pivots | Max Gap (m) | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |",
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sensitivity_rows:
        lines.append(
            f"| {row['min_pivots']} | {row['max_pivot_gap_minutes']} | "
            f"{row['discovery']['profit_factor']:.3f} | {row['discovery']['avg_r']:.3f} | "
            f"{row['validation']['profit_factor']:.3f} | {row['validation']['avg_r']:.3f} | "
            f"{row['validation']['calmar_ratio']:.3f} | {int(row['validation']['total_trades'])} |"
        )
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()
    branch_rows = [run_branch(label, params) for label, params in BRANCHES.items()]
    sensitivity_rows = run_2m_sensitivity()
    payload = {
        "meta": {
            "discovery_start": DISCOVERY_START,
            "validation_start": VALIDATION_START,
            "holdout_start": HOLDOUT_START,
            "lrlr_defaults": LRLR_DEFAULTS,
        },
        "branches": branch_rows,
        "sensitivity_2m": sensitivity_rows,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", payload)
    write_report(branch_rows, sensitivity_rows)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
