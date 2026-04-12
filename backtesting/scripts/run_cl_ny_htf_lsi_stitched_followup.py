#!/usr/bin/env python3
"""Stitched OOS follow-up for the CL NY HTF-LSI partial discovery freeze.

CL discovery was frozen after Stage C because the generic 1m Stage D/E packet
is disproportionately expensive on the full 10y 1m history. This follow-up
uses the saved Stage B/C rows to tie-break the real candidate family before
opening holdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from orb_backtest.optimize.parallel import run_sweep

from run_cross_asset_htf_lsi_stitched_followup import (  # noqa: E402
    _config_from_row,
    _stitched_oos_payload,
    _write_report,
)
from run_cross_asset_htf_lsi_broad_discovery import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    ensure_required_data,
    load_timeframe_data,
    summarize_periods,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-workers", type=int, default=None)
    return parser.parse_args()


def _match(rows: list[dict], **criteria) -> dict:
    for row in rows:
        if all(row[k] == v for k, v in criteria.items()):
            return row
    raise ValueError(f"Could not find candidate with criteria {criteria}")


def _pick_cl_candidates(stage_b_rows: list[dict], stage_c_rows: list[dict]) -> list[dict]:
    candidates = [
        (
            "control_stage_b_end14",
            _match(
                stage_b_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=30,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "control_stage_b_end13",
            _match(
                stage_b_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="13:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=30,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "count_stage_b_end15",
            _match(
                stage_b_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=30,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "structural_alt_htf60_end14",
            _match(
                stage_b_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "atr10_end14",
            _match(
                stage_c_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=10,
                htf_level_tf_minutes=30,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "htf_n7_end14",
            _match(
                stage_c_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=30,
                htf_n_left=7,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "early_end1030",
            _match(
                stage_c_rows,
                timeframe="1m",
                direction_filter="long",
                entry_mode="close",
                entry_end="10:30",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=30,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=100,
                lsi_fvg_window_right=10,
                max_fvg_to_inversion_bars=0,
            ),
        ),
    ]
    out = []
    for candidate_id, row in candidates:
        copied = dict(row)
        copied["candidate_id"] = candidate_id
        out.append(copied)
    return out


def main() -> int:
    args = parse_args()
    symbol = "CL"
    ensure_required_data(symbol)

    broad_dir = ROOT / "data" / "results" / "cl_ny_htf_lsi_broad_discovery"
    stage_b_rows = json.loads((broad_dir / "stage_b_trade_cap.json").read_text())
    stage_c_rows = json.loads((broad_dir / "stage_c_oat.json").read_text())
    candidate_rows = _pick_cl_candidates(stage_b_rows, stage_c_rows)

    row_map = {row["label"]: row for row in candidate_rows}
    payload = []
    print(f"Running stitched follow-up for {symbol} ({len(candidate_rows)} configs)...", flush=True)

    configs = [_config_from_row(row, symbol) for row in candidate_rows]
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(symbol, "1m")
    results = run_sweep(
        df_base,
        configs,
        n_workers=args.n_workers,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )

    for cfg, trades in results:
        source = row_map[cfg.name]
        summary = summarize_periods(trades)
        payload.append(
            {
                "candidate_id": source["candidate_id"],
                "label": cfg.name,
                "timeframe": source["timeframe"],
                "config": {
                    "direction_filter": cfg.direction_filter,
                    "entry_mode": cfg.lsi_entry_mode,
                    "entry_start": cfg.sessions[0].entry_start,
                    "entry_end": cfg.sessions[0].entry_end,
                    "rr": cfg.rr,
                    "tp1_ratio": cfg.tp1_ratio,
                    "min_gap_atr_pct": cfg.sessions[0].min_gap_atr_pct,
                    "atr_length": cfg.atr_length,
                    "htf_level_tf_minutes": cfg.htf_level_tf_minutes,
                    "htf_n_left": cfg.htf_n_left,
                    "htf_trade_max_per_session": cfg.htf_trade_max_per_session,
                    "lsi_fvg_window_left": cfg.lsi_fvg_window_left,
                    "lsi_fvg_window_right": cfg.lsi_fvg_window_right,
                    "max_fvg_to_inversion_bars": cfg.max_fvg_to_inversion_bars,
                    "left_minutes": cfg.lsi_fvg_window_left,
                    "right_minutes": cfg.lsi_fvg_window_right,
                },
                "pre_holdout_pf": float(summary["pre_holdout"]["profit_factor"]),
                "pre_holdout_avg_r": float(summary["pre_holdout"]["avg_r"]),
                "pre_holdout_calmar": float(summary["pre_holdout"]["calmar_ratio"]),
                "pre_holdout_trades": int(summary["pre_holdout"]["total_trades"]),
                "discovery_pf": float(summary["discovery"]["profit_factor"]),
                "discovery_avg_r": float(summary["discovery"]["avg_r"]),
                "discovery_calmar": float(summary["discovery"]["calmar_ratio"]),
                "discovery_trades": int(summary["discovery"]["total_trades"]),
                "validation_pf": float(summary["validation"]["profit_factor"]),
                "validation_avg_r": float(summary["validation"]["avg_r"]),
                "validation_calmar": float(summary["validation"]["calmar_ratio"]),
                "validation_trades": int(summary["validation"]["total_trades"]),
                "walkforward": _stitched_oos_payload(trades),
            }
        )

    payload.sort(
        key=lambda row: (
            row["walkforward"]["combined"]["calmar"],
            row["walkforward"]["combined"]["avg_r"],
            row["walkforward"]["combined"]["pf"],
            row["validation_calmar"],
            row["discovery_avg_r"],
        ),
        reverse=True,
    )

    out_dir = ROOT / "data" / "results" / "cl_ny_htf_lsi_stitched_followup"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2))
    report_path = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md"
    _write_report(report_path, symbol, payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
