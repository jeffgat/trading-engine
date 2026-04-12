#!/usr/bin/env python3
"""Cross-timeframe inversion-lag curve study for NQ NY HTF-LSI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.optimize.parallel import run_sweep

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    result_row,
    save_json,
)

LAG_VALUES = list(range(0, 31))


def _transfer_summary_path(explicit_path: Path | None) -> Path:
    if explicit_path is not None:
        return explicit_path
    candidates = (
        RESULTS_ROOT / "nq_ny_htf_lsi_tf_transfer" / "summary_manual.json",
        RESULTS_ROOT / "nq_ny_htf_lsi_tf_transfer" / "summary.json",
    )
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Could not find HTF-LSI transfer summary JSON.")


def _load_best_transfer_rows(path: Path) -> dict[str, dict]:
    rows = json.loads(path.read_text())
    best_by_tf: dict[str, dict] = {}
    for timeframe in ("5m", "3m", "2m", "1m"):
        tf_rows = [row for row in rows if row.get("timeframe") == timeframe]
        if not tf_rows:
            raise ValueError(f"No transfer rows found for timeframe {timeframe}")
        tf_rows.sort(
            key=lambda row: (
                row["validation_calmar"],
                row["validation_pf"],
                row["discovery_pf"],
                -row["htf_trade_max_per_session"],
            ),
            reverse=True,
        )
        best_by_tf[timeframe] = tf_rows[0]
    return best_by_tf


def _build_lag_configs(timeframe: str, anchor_row: dict) -> list:
    configs = []
    for lag in LAG_VALUES:
        configs.append(
            build_config(
                timeframe=timeframe,
                direction_filter=anchor_row["direction_filter"],
                entry_mode=anchor_row["entry_mode"],
                entry_start=anchor_row["entry_start"],
                entry_end=anchor_row["entry_end"],
                rr=float(anchor_row["rr"]),
                tp1_ratio=float(anchor_row["tp1_ratio"]),
                min_gap_atr_pct=float(anchor_row["min_gap_atr_pct"]),
                atr_length=int(anchor_row["atr_length"]),
                htf_level_tf_minutes=int(anchor_row["htf_level_tf_minutes"]),
                htf_n_left=int(anchor_row["htf_n_left"]),
                htf_trade_max_per_session=int(anchor_row["htf_trade_max_per_session"]),
                lsi_fvg_window_left=int(anchor_row["lsi_fvg_window_left"]),
                lsi_fvg_window_right=int(anchor_row["lsi_fvg_window_right"]),
                max_fvg_to_inversion_bars=lag,
                entry_context_gate=anchor_row.get("entry_context_gate", ""),
                entry_context_min_atr=float(anchor_row.get("entry_context_min_atr", 0.0)),
                entry_context_max_atr=float(anchor_row.get("entry_context_max_atr", 0.0)),
                name=(
                    f"NQ NY HTF_LSI lagcurve {timeframe} lag{lag} "
                    f"{anchor_row['direction_filter']} {anchor_row['entry_mode']} "
                    f"cap{anchor_row['htf_trade_max_per_session']}"
                ),
            )
        )
    return configs


def _annotate_rows(rows: list[dict], anchor_row: dict) -> tuple[list[dict], dict]:
    lag0 = next(row for row in rows if row["max_fvg_to_inversion_bars"] == 0)
    base_disc_trades = max(int(lag0["discovery_trades"]), 1)
    base_val_trades = max(int(lag0["validation_trades"]), 1)
    base_pre_trades = max(int(lag0["pre_holdout_trades"]), 1)
    enriched = []
    for row in rows:
        enriched.append(
            row
            | {
                "timeframe": anchor_row["timeframe"],
                "anchor_label": anchor_row["label"],
                "anchor_direction_filter": anchor_row["direction_filter"],
                "anchor_entry_mode": anchor_row["entry_mode"],
                "anchor_trade_cap": anchor_row["htf_trade_max_per_session"],
                "pre_holdout_trade_retention": row["pre_holdout_trades"] / base_pre_trades,
                "discovery_trade_retention": row["discovery_trades"] / base_disc_trades,
                "validation_trade_retention": row["validation_trades"] / base_val_trades,
            }
        )

    best_val = max(
        enriched,
        key=lambda row: (
            row["validation_calmar"],
            row["validation_pf"],
            row["validation_avg_r"],
            row["validation_trades"],
        ),
    )
    best_disc = max(
        enriched,
        key=lambda row: (
            row["discovery_calmar"],
            row["discovery_pf"],
            row["discovery_avg_r"],
            row["discovery_trades"],
        ),
    )
    summary = {
        "timeframe": anchor_row["timeframe"],
        "anchor_label": anchor_row["label"],
        "anchor_direction_filter": anchor_row["direction_filter"],
        "anchor_entry_mode": anchor_row["entry_mode"],
        "anchor_trade_cap": anchor_row["htf_trade_max_per_session"],
        "anchor_lag0_discovery_pf": lag0["discovery_pf"],
        "anchor_lag0_validation_pf": lag0["validation_pf"],
        "anchor_lag0_validation_calmar": lag0["validation_calmar"],
        "anchor_lag0_discovery_trades": lag0["discovery_trades"],
        "anchor_lag0_validation_trades": lag0["validation_trades"],
        "best_validation_lag": best_val["max_fvg_to_inversion_bars"],
        "best_validation_calmar": best_val["validation_calmar"],
        "best_validation_pf": best_val["validation_pf"],
        "best_validation_avg_r": best_val["validation_avg_r"],
        "best_validation_trades": best_val["validation_trades"],
        "best_validation_trade_retention": best_val["validation_trade_retention"],
        "best_discovery_lag": best_disc["max_fvg_to_inversion_bars"],
        "best_discovery_calmar": best_disc["discovery_calmar"],
        "best_discovery_pf": best_disc["discovery_pf"],
        "best_discovery_avg_r": best_disc["discovery_avg_r"],
        "best_discovery_trades": best_disc["discovery_trades"],
        "best_discovery_trade_retention": best_disc["discovery_trade_retention"],
    }
    return enriched, summary


def _write_report(path: Path, summaries: list[dict], all_rows: dict[str, list[dict]]) -> None:
    lines = ["# NQ NY HTF-LSI Lag Curve", ""]
    lines.append("## Summary")
    lines.append("")
    lines.append("| Timeframe | Anchor | Best Val Lag | Val Calmar | Val PF | Val Trades | Trade Retention | Best Disc Lag | Disc Calmar | Disc PF | Disc Trades |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in summaries:
        lines.append(
            f"| {row['timeframe']} | {row['anchor_direction_filter']} / {row['anchor_entry_mode']} / cap{row['anchor_trade_cap']} | "
            f"{row['best_validation_lag']} | {row['best_validation_calmar']:.3f} | {row['best_validation_pf']:.3f} | "
            f"{row['best_validation_trades']} | {row['best_validation_trade_retention']:.3f} | "
            f"{row['best_discovery_lag']} | {row['best_discovery_calmar']:.3f} | {row['best_discovery_pf']:.3f} | "
            f"{row['best_discovery_trades']} |"
        )
    lines.append("")

    ordered_timeframes = [tf for tf in ("5m", "3m", "2m", "1m") if tf in all_rows]
    for timeframe in ordered_timeframes:
        lines.append(f"## {timeframe}")
        lines.append("")
        lines.append("| Lag | Disc PF | Disc Avg R | Disc Trades | Disc Retention | Val PF | Val Avg R | Val Calmar | Val Trades | Val Retention |")
        lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in all_rows[timeframe]:
            lines.append(
                f"| {row['max_fvg_to_inversion_bars']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
                f"{row['discovery_trades']} | {row['discovery_trade_retention']:.3f} | {row['validation_pf']:.3f} | "
                f"{row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | {row['validation_trades']} | "
                f"{row['validation_trade_retention']:.3f} |"
            )
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transfer-summary", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=RESULTS_ROOT / "nq_ny_htf_lsi_lag_curve")
    parser.add_argument("--timeframes", type=str, default="5m,3m,2m,1m")
    parser.add_argument(
        "--report-path",
        type=Path,
        default=ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_LAG_CURVE.md",
    )
    args = parser.parse_args()

    try:
        ensure_required_data()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    transfer_summary = _transfer_summary_path(args.transfer_summary)
    anchors = _load_best_transfer_rows(transfer_summary)
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    timeframes = tuple(item.strip() for item in args.timeframes.split(",") if item.strip())

    summaries = []
    rows_by_tf: dict[str, list[dict]] = {}

    for timeframe in timeframes:
        anchor = anchors[timeframe]
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        configs = _build_lag_configs(timeframe, anchor)
        results = run_sweep(
            df_base,
            configs,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        rows = [result_row(cfg.name, cfg, trades) | {"timeframe": timeframe} for cfg, trades in results]
        rows.sort(key=lambda row: row["max_fvg_to_inversion_bars"])
        enriched, summary = _annotate_rows(rows, anchor | {"timeframe": timeframe})
        rows_by_tf[timeframe] = enriched
        summaries.append(summary)
        save_json(out_dir / f"{timeframe}.json", enriched)

    ordered = tuple(tf for tf in ("5m", "3m", "2m", "1m") if tf in timeframes)
    summaries.sort(key=lambda row: ordered.index(row["timeframe"]))
    save_json(out_dir / "summary.json", summaries)
    _write_report(args.report_path, summaries, rows_by_tf)
    print(json.dumps(summaries, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
