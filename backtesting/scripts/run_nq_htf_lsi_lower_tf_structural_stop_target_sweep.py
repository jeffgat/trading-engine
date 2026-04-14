#!/usr/bin/env python3
"""Compare structural stop/target constructions on lower-timeframe NQ HTF-LSI anchors.

Scope:
- honest `1m lag0` HTF-LSI anchor
- honest `2m lag0` HTF-LSI anchor
- honest `3m lag0` HTF-LSI anchor

To preserve holdout hygiene, this packet keeps `2025-04-01+` closed for every
timeframe and uses stitched OOS as the honest secondary read.
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import replace
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
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


OUTPUT_DIR = RESULTS_ROOT / "nq_htf_lsi_lower_tf_structural_stop_target_sweep"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_HTF_LSI_LOWER_TF_STRUCTURAL_STOP_TARGET_SWEEP.md"
LAG_CURVE_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lag_curve"

TIMEFRAMES = ("1m", "2m", "3m")
STOP_MODES = (
    "absolute",
    "gap_1x",
    "gap_2x",
    "gap_3x",
    "gap_4x",
    "struct_50pct",
    "struct_75pct",
)
TARGET_MODES = ("risk", "structural", "left_structure")


def _load_anchor_row(timeframe: str) -> dict:
    rows = json.loads((LAG_CURVE_DIR / f"{timeframe}.json").read_text())
    return next(row for row in rows if int(row["max_fvg_to_inversion_bars"]) == 0)


def _config_from_anchor(anchor_row: dict, *, stop_mode: str, target_mode: str):
    base = build_config(
        timeframe=anchor_row["timeframe"],
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
        htf_lsi_inversion_ordinal=int(anchor_row.get("htf_lsi_inversion_ordinal", 1)),
        lsi_fvg_window_left=int(anchor_row["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(anchor_row["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(anchor_row["max_fvg_to_inversion_bars"]),
        entry_context_gate=anchor_row.get("entry_context_gate", ""),
        entry_context_min_atr=float(anchor_row.get("entry_context_min_atr", 0.0)),
        entry_context_max_atr=float(anchor_row.get("entry_context_max_atr", 0.0)),
        name=(
            f"NQ NY HTF_LSI {anchor_row['timeframe']} "
            f"{stop_mode} {target_mode}"
        ),
    )
    return replace(
        base,
        lsi_stop_mode=stop_mode,
        lsi_target_mode=target_mode,
    )


def _trade_shape_stats(trades) -> dict:
    filled = [trade for trade in trades if trade.exit_type != 0]
    if not filled:
        return {
            "median_stop_ticks": 0.0,
            "median_tp1_r": 0.0,
            "median_tp2_r": 0.0,
        }
    return {
        "median_stop_ticks": median(trade.risk_points / NQ.min_tick for trade in filled),
        "median_tp1_r": median(
            abs(trade.tp1_price - trade.entry_price) / trade.risk_points
            for trade in filled
            if trade.risk_points > 0
        ),
        "median_tp2_r": median(
            abs(trade.tp2_price - trade.entry_price) / trade.risk_points
            for trade in filled
            if trade.risk_points > 0
        ),
    }


def _period_summary(trades) -> dict:
    metrics = compute_metrics(trades)
    shape = _trade_shape_stats(trades)
    return {
        "trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "profit_factor": float(metrics["profit_factor"]),
        "avg_r": float(metrics["avg_r"]),
        "total_r": float(metrics["total_r"]),
        "calmar": float(metrics["calmar_ratio"]),
        "max_dd_r": float(metrics["max_drawdown_r"]),
        **shape,
    }


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
                "profit_factor": float(metrics["profit_factor"]),
                "calmar": float(metrics["calmar_ratio"]),
                "max_dd_r": float(metrics["max_drawdown_r"]),
                "total_r": float(metrics["total_r"]),
            }
        )
    return {
        "folds": folds,
        "combined": _period_summary(combined),
    }


def _row(timeframe: str, anchor_row: dict, config, trades) -> dict:
    return {
        "timeframe": timeframe,
        "anchor_label": anchor_row["label"],
        "stop_mode": config.lsi_stop_mode,
        "target_mode": config.lsi_target_mode,
        "entry_mode": config.lsi_entry_mode,
        "trade_cap": int(config.htf_trade_max_per_session),
        "pre_holdout": _period_summary(trades),
        "discovery": _period_summary(slice_trades(trades, DISCOVERY_START, VALIDATION_START)),
        "validation": _period_summary(slice_trades(trades, VALIDATION_START, HOLDOUT_START)),
        "stitched_oos": _stitched_oos_payload(trades),
    }


def _rank_key(row: dict) -> tuple:
    stitched = row["stitched_oos"]["combined"]
    validation = row["validation"]
    discovery = row["discovery"]
    return (
        stitched["calmar"],
        stitched["profit_factor"],
        stitched["avg_r"],
        validation["calmar"],
        validation["profit_factor"],
        validation["avg_r"],
        discovery["profit_factor"],
        discovery["avg_r"],
        -stitched["max_dd_r"],
        validation["trades"],
    )


def _write_report(payload: dict) -> None:
    lines = [
        "# NQ HTF-LSI Lower-TF Structural Stop / Target Sweep",
        "",
        "- Date: `2026-04-13`",
        "- Scope: honest `1m`, `2m`, and `3m` lag-0 HTF-LSI anchors only.",
        "- Stop modes: `absolute`, `gap_1x`, `gap_2x`, `gap_3x`, `gap_4x`, `struct_50pct`, `struct_75pct`.",
        "- Target modes: `risk`, `structural`, `left_structure`.",
        "- Holdout hygiene: `2025-04-01+` stays closed for all three timeframes; stitched OOS is the honest secondary read.",
        "- Ranking: stitched OOS first, then validation.",
        "",
    ]

    for timeframe in TIMEFRAMES:
        anchor = payload[timeframe]["anchor"]
        rows = payload[timeframe]["rows"]
        top_rows = rows[:5]
        baseline = next(row for row in rows if row["stop_mode"] == "absolute" and row["target_mode"] == "risk")
        best_left = next(row for row in rows if row["target_mode"] == "left_structure")
        lines.extend(
            [
                f"## {timeframe}",
                "",
                f"- Anchor: `{anchor['label']}`",
                f"- Shape: `{anchor['direction_filter']} / {anchor['entry_mode']} / cap{anchor['htf_trade_max_per_session']} / "
                f"{anchor['entry_start']}-{anchor['entry_end']} / rr{anchor['rr']} / tp{anchor['tp1_ratio']} / "
                f"L{anchor['lsi_fvg_window_left']} / R{anchor['lsi_fvg_window_right']}`",
                f"- Baseline stitched OOS: PF `{baseline['stitched_oos']['combined']['profit_factor']:.3f}`, "
                f"avg R `{baseline['stitched_oos']['combined']['avg_r']:.3f}`, "
                f"Calmar `{baseline['stitched_oos']['combined']['calmar']:.3f}`, "
                f"DD `{baseline['stitched_oos']['combined']['max_dd_r']:.2f}`, "
                f"median stop `{baseline['pre_holdout']['median_stop_ticks']:.1f}` ticks",
                f"- Best `left_structure`: `{best_left['stop_mode']}` -> stitched PF "
                f"`{best_left['stitched_oos']['combined']['profit_factor']:.3f}`, avg R "
                f"`{best_left['stitched_oos']['combined']['avg_r']:.3f}`, Calmar "
                f"`{best_left['stitched_oos']['combined']['calmar']:.3f}`, DD "
                f"`{best_left['stitched_oos']['combined']['max_dd_r']:.2f}`",
                "",
                "| Rank | Stop | Target | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF DD | Stop Ticks | TP1 R | TP2 R |",
                "| ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for idx, row in enumerate(top_rows, start=1):
            stitched = row["stitched_oos"]["combined"]
            validation = row["validation"]
            discovery = row["discovery"]
            pre = row["pre_holdout"]
            lines.append(
                f"| {idx} | `{row['stop_mode']}` | `{row['target_mode']}` | "
                f"{discovery['profit_factor']:.3f} | {discovery['avg_r']:.3f} | "
                f"{validation['profit_factor']:.3f} | {validation['avg_r']:.3f} | {validation['calmar']:.3f} | "
                f"{stitched['profit_factor']:.3f} | {stitched['avg_r']:.3f} | {stitched['calmar']:.3f} | "
                f"{stitched['max_dd_r']:.2f} | {pre['median_stop_ticks']:.1f} | "
                f"{pre['median_tp1_r']:.2f} | {pre['median_tp2_r']:.2f} |"
            )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()
    overall = {
        "meta": {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "timeframes": list(TIMEFRAMES),
            "stop_modes": list(STOP_MODES),
            "target_modes": list(TARGET_MODES),
            "holdout_start": HOLDOUT_START,
        }
    }

    for timeframe in TIMEFRAMES:
        anchor_row = _load_anchor_row(timeframe)
        configs = [
            _config_from_anchor(anchor_row, stop_mode=stop_mode, target_mode=target_mode)
            for stop_mode in STOP_MODES
            for target_mode in TARGET_MODES
        ]

        print(f"Running {timeframe} lower-TF stop/target sweep...", flush=True)
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
        signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)
        results = run_sweep(
            df_base,
            configs,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _prebuilt_maps=maps,
            _prebuilt_signal_cache=signal_cache,
        )

        rows = [_row(timeframe, anchor_row, cfg, trades) for cfg, trades in results]
        rows.sort(key=_rank_key, reverse=True)
        overall[timeframe] = {
            "anchor": anchor_row,
            "rows": rows,
        }

    save_json(OUTPUT_DIR / "summary.json", overall)
    _write_report(overall)
    print(json.dumps(overall, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
