#!/usr/bin/env python3
"""Narrow secondary packet for the 2m NQ NY HTF-LSI branch."""

from __future__ import annotations

import json
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.engine import simulator
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    result_row,
    save_json,
    slice_trades,
)

OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_2m_secondary_packet"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_2M_SECONDARY_PACKET.md"

# Honest 2m anchor from the transfer + follow-up work:
# long / fvg_limit / cap1 / lag0 / rr3.0 / tp1 0.6 / gap3 / n3 / left50 / right5.
GRID = {
    "min_gap_atr_pct": (3.0, 4.0),
    "htf_n_left": (3, 5),
    "lsi_fvg_window_left": (40, 50, 60),
    "lsi_fvg_window_right": (3, 5, 8),
    "rr": (2.5, 3.0, 3.5),
    "tp1_ratio": (0.5, 0.6, 0.7),
}


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["validation_calmar"],
            row["validation_pf"],
            row["discovery_pf"],
            row["discovery_avg_r"],
            -row["validation_max_dd_r"],
        ),
        reverse=True,
    )


def _survivors(rows: list[dict]) -> list[dict]:
    return [
        row
        for row in rows
        if row["discovery_pf"] >= 1.05
        and row["discovery_avg_r"] > 0.0
        and row["discovery_trades"] >= 200
        and row["validation_pf"] >= 1.05
        and row["validation_avg_r"] > 0.0
    ]


def _stitched_oos(cfg, df_base, df_1m, df_1s, signal_df_1m) -> dict:
    windows = generate_windows(DISCOVERY_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined = []
    folds = []
    for window in windows:
        trades = simulator.run_backtest(
            df_base,
            cfg,
            start_date=window.oos_start,
            end_date=window.oos_end,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        oos = slice_trades(trades, window.oos_start, window.oos_end)
        metrics = compute_metrics(oos)
        combined.extend(oos)
        folds.append(
            {
                "oos_start": window.oos_start,
                "oos_end": window.oos_end,
                "trades": int(metrics["total_trades"]),
                "avg_r": float(metrics["avg_r"]),
                "pf": float(metrics["profit_factor"]),
                "calmar": float(metrics["calmar_ratio"]),
                "max_dd_r": float(metrics["max_drawdown_r"]),
                "total_r": float(metrics["total_r"]),
            }
        )

    combined_metrics = compute_metrics(combined)
    return {
        "folds": folds,
        "combined": {
            "trades": int(combined_metrics["total_trades"]),
            "avg_r": float(combined_metrics["avg_r"]),
            "pf": float(combined_metrics["profit_factor"]),
            "calmar": float(combined_metrics["calmar_ratio"]),
            "max_dd_r": float(combined_metrics["max_drawdown_r"]),
            "total_r": float(combined_metrics["total_r"]),
        },
    }


def _write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI 2m Secondary Packet",
        "",
        "- Narrow pre-holdout packet around the honest `2m lag=0` branch.",
        "- Fixed branch shape: `long`, `fvg_limit`, `cap1`, `lag=0`, `08:30-15:00`.",
        f"- Search window: `{DISCOVERY_START}` to `{HOLDOUT_START}` with holdout still closed.",
        "",
        "## Grid",
        "",
        "| Param | Values |",
        "| --- | --- |",
        "| min_gap_atr_pct | 3.0, 4.0 |",
        "| htf_n_left | 3, 5 |",
        "| lsi_fvg_window_left | 40, 50, 60 |",
        "| lsi_fvg_window_right | 3, 5, 8 |",
        "| rr | 2.5, 3.0, 3.5 |",
        "| tp1_ratio | 0.5, 0.6, 0.7 |",
        "",
        f"- Total configs: `{payload['meta']['total_configs']}`",
        f"- Survivors by discovery filters: `{payload['meta']['survivor_count']}`",
        "",
        "## Top Pre-Holdout Rows",
        "",
        "| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["top_rows"]:
        lines.append(
            f"| {row['label']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
            f"{row['validation_calmar']:.3f} | {row['validation_trades']} |"
        )

    lines.extend(
        [
            "",
            "## Stitched OOS Follow-Up",
            "",
            "| Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["walkforward"]:
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['label']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | "
            f"{wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("2m")

    configs = []
    for min_gap, htf_n_left, left, right, rr, tp1 in product(
        GRID["min_gap_atr_pct"],
        GRID["htf_n_left"],
        GRID["lsi_fvg_window_left"],
        GRID["lsi_fvg_window_right"],
        GRID["rr"],
        GRID["tp1_ratio"],
    ):
        if rr * tp1 < 1.0:
            continue
        configs.append(
            build_config(
                timeframe="2m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_start="08:30",
                entry_end="15:00",
                rr=rr,
                tp1_ratio=tp1,
                min_gap_atr_pct=min_gap,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=htf_n_left,
                htf_trade_max_per_session=1,
                lsi_fvg_window_left=left,
                lsi_fvg_window_right=right,
                max_fvg_to_inversion_bars=0,
                name=(
                    "NQ NY HTF_LSI 2m packet "
                    f"gap{min_gap} n{htf_n_left} left{left} right{right} rr{rr} tp{tp1}"
                ),
            )
        )

    print(f"Running {len(configs)} 2m packet configs...", flush=True)
    results = run_sweep(
        df_base,
        configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    rows = _sort_rows([result_row(cfg.name, cfg, trades) for cfg, trades in results])
    survivors = _survivors(rows)

    # Keep the honest anchor-equivalent row in view even if other rows outrank it.
    anchor_rows = [
        row
        for row in rows
        if row["rr"] == 3.0
        and row["tp1_ratio"] == 0.6
        and row["min_gap_atr_pct"] == 3.0
        and row["htf_n_left"] == 3
        and row["lsi_fvg_window_left"] == 50
        and row["lsi_fvg_window_right"] == 5
    ]

    top_rows = survivors[:5]
    if anchor_rows and anchor_rows[0] not in top_rows:
        top_rows = [anchor_rows[0]] + top_rows[:4]
        top_rows = _sort_rows(top_rows)

    print("Running stitched OOS follow-up on top 5 rows...", flush=True)
    cfg_by_label = {cfg.name: cfg for cfg in configs}
    wf_rows = []
    for row in top_rows:
        cfg = cfg_by_label[row["label"]]
        wf_rows.append(row | {"walkforward": _stitched_oos(cfg, df_base, df_1m, df_1s, signal_df_1m)})

    wf_rows = sorted(
        wf_rows,
        key=lambda row: (
            row["walkforward"]["combined"]["calmar"],
            row["walkforward"]["combined"]["pf"],
            row["validation_calmar"],
        ),
        reverse=True,
    )

    payload = {
        "meta": {
            "total_configs": len(configs),
            "survivor_count": len(survivors),
        },
        "top_rows": top_rows,
        "walkforward": wf_rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "all_rows.json", rows)
    save_json(OUTPUT_DIR / "survivors.json", survivors)
    save_json(OUTPUT_DIR / "summary.json", payload)
    _write_report(payload)

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
