#!/usr/bin/env python3
"""Fixed stitched-OOS follow-up for cross-asset HTF-LSI discovery leaders."""

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
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics

from run_cross_asset_htf_lsi_broad_discovery import (
    DISCOVERY_START,
    HOLDOUT_START,
    VALIDATION_START,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    slice_trades,
    summarize_periods,
    timeframe_minutes,
)


def _config_from_row(row: dict, symbol: str):
    return build_config(
        symbol=symbol,
        timeframe=row["timeframe"],
        direction_filter=row["direction_filter"],
        entry_mode=row["entry_mode"],
        entry_start=row["entry_start"],
        entry_end=row["entry_end"],
        rr=float(row["rr"]),
        tp1_ratio=float(row["tp1_ratio"]),
        min_gap_atr_pct=float(row["min_gap_atr_pct"]),
        atr_length=int(row["atr_length"]),
        htf_level_tf_minutes=int(row["htf_level_tf_minutes"]),
        htf_n_left=int(row["htf_n_left"]),
        htf_trade_max_per_session=int(row["htf_trade_max_per_session"]),
        lsi_fvg_window_left=int(row["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(row["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(row["max_fvg_to_inversion_bars"]),
        min_stop_points=float(row["min_stop_points"]),
        min_tp1_points=float(row["min_tp1_points"]),
        name=row["label"],
    )


def _stitched_oos_payload(trades) -> dict:
    windows = generate_windows(DISCOVERY_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined = []
    folds = []
    for window in windows:
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


def _pick_es_candidates(stage_b_rows: list[dict], stage_e_rows: list[dict]) -> list[dict]:
    def match(rows: list[dict], **criteria):
        for row in rows:
            if all(row[k] == v for k, v in criteria.items()):
                return row
        raise ValueError(f"Could not find candidate with criteria {criteria}")

    candidates = [
        (
            "control_stage_b",
            match(
                stage_b_rows,
                timeframe="3m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=33,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "quality_lag16_gap2",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=2.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=2.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=16,
            ),
        ),
        (
            "count_lag0_gap2_r15",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=2.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=2.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=5,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "balanced_lag0_gap3",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=2.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "discovery_lag0_gap2_r9",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=2.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=2.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "late_lag24_gap3",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=2.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=24,
            ),
        ),
    ]
    out = []
    for candidate_id, row in candidates:
        copied = dict(row)
        copied["candidate_id"] = candidate_id
        out.append(copied)
    return out


def _pick_rty_candidates(stage_b_rows: list[dict], stage_e_rows: list[dict]) -> list[dict]:
    def match(rows: list[dict], **criteria):
        for row in rows:
            if all(row[k] == v for k, v in criteria.items()):
                return row
        raise ValueError(f"Could not find candidate with criteria {criteria}")

    candidates = [
        (
            "control_stage_b_end14",
            match(
                stage_b_rows,
                timeframe="5m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "control_stage_b_end15",
            match(
                stage_b_rows,
                timeframe="5m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "quality_lag12_n5",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.4,
                min_gap_atr_pct=2.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=12,
                lsi_fvg_window_right=1,
                max_fvg_to_inversion_bars=12,
            ),
        ),
        (
            "balanced_lag20_n5",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.4,
                min_gap_atr_pct=2.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=12,
                lsi_fvg_window_right=1,
                max_fvg_to_inversion_bars=20,
            ),
        ),
        (
            "rr4_lag20_atr14_l100",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=4.0,
                tp1_ratio=0.5,
                min_gap_atr_pct=2.0,
                atr_length=14,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=20,
            ),
        ),
        (
            "rr4_lag30_atr10_l60",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=4.0,
                tp1_ratio=0.5,
                min_gap_atr_pct=2.0,
                atr_length=10,
                htf_level_tf_minutes=90,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=12,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=30,
            ),
        ),
    ]
    out = []
    for candidate_id, row in candidates:
        copied = dict(row)
        copied["candidate_id"] = candidate_id
        out.append(copied)
    return out


def _pick_gc_candidates(stage_b_rows: list[dict], stage_e_rows: list[dict]) -> list[dict]:
    def match(rows: list[dict], **criteria):
        for row in rows:
            if all(row[k] == v for k, v in criteria.items()):
                return row
        raise ValueError(f"Could not find candidate with criteria {criteria}")

    candidates = [
        (
            "control_stage_b_1030",
            match(
                stage_b_rows,
                timeframe="3m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="10:30",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=33,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "balanced_lag0_1030_r9",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="10:30",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "quality_lag0_1030_r15",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="10:30",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=5,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "late_lag24_1100_r15",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="11:00",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=5,
                max_fvg_to_inversion_bars=24,
            ),
        ),
        (
            "late_lag30_1100_r15",
            match(
                stage_e_rows,
                timeframe="3m",
                direction_filter="short",
                entry_mode="fvg_limit",
                entry_end="11:00",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=5,
                max_fvg_to_inversion_bars=30,
            ),
        ),
    ]
    out = []
    for candidate_id, row in candidates:
        copied = dict(row)
        copied["candidate_id"] = candidate_id
        out.append(copied)
    return out


def _pick_si_candidates(stage_b_rows: list[dict], stage_e_rows: list[dict]) -> list[dict]:
    def match(rows: list[dict], **criteria):
        for row in rows:
            if all(row[k] == v for k, v in criteria.items()):
                return row
        raise ValueError(f"Could not find candidate with criteria {criteria}")

    candidates = [
        (
            "control_stage_b_end14",
            match(
                stage_b_rows,
                timeframe="5m",
                direction_filter="both",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "control_stage_b_end13_cap1",
            match(
                stage_b_rows,
                timeframe="5m",
                direction_filter="both",
                entry_mode="fvg_limit",
                entry_end="13:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=1,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "late_lag30_end14",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="both",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=28,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=30,
            ),
        ),
        (
            "balanced_lag0_end14",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="both",
                entry_mode="fvg_limit",
                entry_end="14:00",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=28,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "balanced_lag0_end13",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="both",
                entry_mode="fvg_limit",
                entry_end="13:00",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=28,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
            ),
        ),
        (
            "late_lag30_end13",
            match(
                stage_e_rows,
                timeframe="5m",
                direction_filter="both",
                entry_mode="fvg_limit",
                entry_end="13:00",
                rr=3.5,
                tp1_ratio=0.5,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=5,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=28,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=30,
            ),
        ),
    ]
    out = []
    for candidate_id, row in candidates:
        copied = dict(row)
        copied["candidate_id"] = candidate_id
        out.append(copied)
    return out


def _write_report(path: Path, symbol: str, payload: list[dict]) -> None:
    lines = [
        f"# {symbol} NY HTF-LSI Stitched Follow-Up",
        "",
        f"- Fixed stitched OOS comparison over `{DISCOVERY_START}` to `{HOLDOUT_START}` using `36m IS / 12m OOS / 12m step` slices.",
        "- Holdout remains unopened.",
        "",
        "| Candidate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload:
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['candidate_id']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", default="ES")
    parser.add_argument("--n-workers", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.instrument.upper()
    ensure_required_data(symbol)

    broad_dir = ROOT / "data" / "results" / f"{symbol.lower()}_ny_htf_lsi_broad_discovery"
    stage_b_rows = json.loads((broad_dir / "stage_b_trade_cap.json").read_text())
    stage_e_rows = json.loads((broad_dir / "stage_e_lag.json").read_text())

    if symbol == "ES":
        candidate_rows = _pick_es_candidates(stage_b_rows, stage_e_rows)
    elif symbol == "RTY":
        candidate_rows = _pick_rty_candidates(stage_b_rows, stage_e_rows)
    elif symbol == "GC":
        candidate_rows = _pick_gc_candidates(stage_b_rows, stage_e_rows)
    elif symbol == "SI":
        candidate_rows = _pick_si_candidates(stage_b_rows, stage_e_rows)
    else:
        raise ValueError("This stitched follow-up packet is currently curated for ES, RTY, GC, and SI only.")
    row_map = {row["label"]: row for row in candidate_rows}
    payload = []
    timeframes = sorted({row["timeframe"] for row in candidate_rows})
    print(f"Running stitched follow-up for {symbol} ({len(candidate_rows)} configs)...", flush=True)
    for timeframe in timeframes:
        timeframe_rows = [row for row in candidate_rows if row["timeframe"] == timeframe]
        configs = [_config_from_row(row, symbol) for row in timeframe_rows]
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(symbol, timeframe)
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
                        "left_minutes": cfg.lsi_fvg_window_left * timeframe_minutes(timeframe),
                        "right_minutes": cfg.lsi_fvg_window_right * timeframe_minutes(timeframe),
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
            row["walkforward"]["combined"]["pf"],
            row["walkforward"]["combined"]["avg_r"],
            row["validation_calmar"],
        ),
        reverse=True,
    )

    out_dir = ROOT / "data" / "results" / f"{symbol.lower()}_ny_htf_lsi_stitched_followup"
    report_path = ROOT / "learnings" / "reports" / f"{symbol}_NY_HTF_LSI_STITCHED_FOLLOWUP.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2))
    _write_report(report_path, symbol, payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
