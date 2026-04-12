#!/usr/bin/env python3
"""Targeted trade-count expansion sweep for NQ NY HTF-LSI 5m."""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.parallel import run_sweep

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    VALIDATION_START,
    RESULTS_ROOT,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    result_row,
    save_json,
)

OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_count_expansion"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_COUNT_EXPANSION.md"

TARGET_LOW = 60.0
TARGET_HIGH = 80.0
TARGET_CENTER = 70.0

ANCHOR = {
    "timeframe": "5m",
    "direction_filter": "long",
    "entry_mode": "fvg_limit",
    "entry_start": "08:30",
    "entry_end": "15:00",
    "rr": 3.0,
    "tp1_ratio": 0.6,
    "min_gap_atr_pct": 3.0,
    "atr_length": 14,
    "htf_level_tf_minutes": 60,
    "htf_n_left": 3,
    "htf_trade_max_per_session": 2,
    "lsi_fvg_window_left": 20,
    "lsi_fvg_window_right": 2,
    "max_fvg_to_inversion_bars": 24,
}


def _years_between(start: str, end: str) -> float:
    return (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25


PRE_HOLDOUT_YEARS = _years_between(DISCOVERY_START, HOLDOUT_START)
DISCOVERY_YEARS = _years_between(DISCOVERY_START, VALIDATION_START)
VALIDATION_YEARS = _years_between(VALIDATION_START, HOLDOUT_START)


def _config_key(row: dict) -> tuple:
    return (
        row["direction_filter"],
        row["entry_mode"],
        float(row["min_gap_atr_pct"]),
        int(row["lsi_fvg_window_right"]),
        int(row["max_fvg_to_inversion_bars"]),
        int(row["htf_trade_max_per_session"]),
    )


ANCHOR_KEY = (
    ANCHOR["direction_filter"],
    ANCHOR["entry_mode"],
    float(ANCHOR["min_gap_atr_pct"]),
    int(ANCHOR["lsi_fvg_window_right"]),
    int(ANCHOR["max_fvg_to_inversion_bars"]),
    int(ANCHOR["htf_trade_max_per_session"]),
)


def _build_configs() -> list:
    configs = []
    for direction, entry_mode, min_gap, right, lag, cap in product(
        ("long", "both"),
        ("fvg_limit", "close"),
        (2.0, 2.5, 3.0),
        (2, 3, 5),
        (0, 24, 30),
        (2, 3),
    ):
        cfg = build_config(
            timeframe=ANCHOR["timeframe"],
            direction_filter=direction,
            entry_mode=entry_mode,
            entry_start=ANCHOR["entry_start"],
            entry_end=ANCHOR["entry_end"],
            rr=ANCHOR["rr"],
            tp1_ratio=ANCHOR["tp1_ratio"],
            min_gap_atr_pct=min_gap,
            atr_length=ANCHOR["atr_length"],
            htf_level_tf_minutes=ANCHOR["htf_level_tf_minutes"],
            htf_n_left=ANCHOR["htf_n_left"],
            htf_trade_max_per_session=cap,
            lsi_fvg_window_left=ANCHOR["lsi_fvg_window_left"],
            lsi_fvg_window_right=right,
            max_fvg_to_inversion_bars=lag,
            name=(
                "NQ NY HTF_LSI count "
                f"5m {direction} {entry_mode} gap{min_gap} "
                f"right{right} lag{lag} cap{cap}"
            ),
        )
        configs.append(cfg)
    return configs


def _filled_year_counts(trades) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            continue
        if DISCOVERY_START <= trade.date < HOLDOUT_START:
            counts[trade.date[:4]] += 1
    return dict(sorted(counts.items()))


def _annotate_row(row: dict, trades) -> dict:
    year_counts = _filled_year_counts(trades)
    pre_ann = row["pre_holdout_trades"] / PRE_HOLDOUT_YEARS
    disc_ann = row["discovery_trades"] / DISCOVERY_YEARS
    val_ann = row["validation_trades"] / VALIDATION_YEARS
    target_distance = abs(pre_ann - TARGET_CENTER)
    return row | {
        "pre_holdout_trades_per_year": pre_ann,
        "discovery_trades_per_year": disc_ann,
        "validation_trades_per_year": val_ann,
        "calendar_year_counts": year_counts,
        "calendar_2024_trades": int(year_counts.get("2024", 0)),
        "calendar_2023_trades": int(year_counts.get("2023", 0)),
        "calendar_2025_q1_trades": int(year_counts.get("2025", 0)),
        "target_distance": target_distance,
        "pre_holdout_in_target_band": TARGET_LOW <= pre_ann <= TARGET_HIGH,
        "validation_in_target_band": TARGET_LOW <= val_ann <= TARGET_HIGH,
    }


def _rank_target_band(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["validation_calmar"],
            row["validation_pf"],
            row["discovery_pf"],
            -row["target_distance"],
        ),
        reverse=True,
    )


def _rank_all(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["pre_holdout_in_target_band"],
            row["validation_calmar"],
            row["validation_pf"],
            row["discovery_pf"],
            -row["target_distance"],
        ),
        reverse=True,
    )


def _param_effects(rows: list[dict], field: str) -> list[dict]:
    buckets: dict[object, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[row[field]].append(row)

    out = []
    for value, group in sorted(buckets.items(), key=lambda item: str(item[0])):
        out.append(
            {
                "field": field,
                "value": value,
                "configs": len(group),
                "avg_pre_holdout_trades_per_year": sum(r["pre_holdout_trades_per_year"] for r in group) / len(group),
                "avg_validation_trades_per_year": sum(r["validation_trades_per_year"] for r in group) / len(group),
                "avg_validation_pf": sum(r["validation_pf"] for r in group) / len(group),
                "avg_validation_calmar": sum(r["validation_calmar"] for r in group) / len(group),
                "best_validation_pf": max(r["validation_pf"] for r in group),
                "best_validation_calmar": max(r["validation_calmar"] for r in group),
            }
        )
    return out


def _row_brief(row: dict) -> str:
    return (
        f"{row['direction_filter']} {row['entry_mode']} gap{row['min_gap_atr_pct']} "
        f"right{row['lsi_fvg_window_right']} lag{row['max_fvg_to_inversion_bars']} "
        f"cap{row['htf_trade_max_per_session']}"
    )


def _write_report(anchor_row: dict, ranked: list[dict], target_rows: list[dict], effects: dict[str, list[dict]]) -> None:
    lines = [
        "# NQ NY HTF-LSI Count Expansion",
        "",
        "- Objective: move the 5m HTF-LSI branch closer to `60-80` filled trades per year without reopening the full discovery tree.",
        f"- Holdout remains frozen at `{HOLDOUT_START}+`; this report only uses `{DISCOVERY_START}` to `{pd.Timestamp(HOLDOUT_START) - pd.Timedelta(days=1):%Y-%m-%d}`.",
        f"- Anchor: `{_row_brief(anchor_row)}` with `{anchor_row['pre_holdout_trades_per_year']:.1f}` pre-holdout trades/year and `{anchor_row['validation_trades_per_year']:.1f}` validation trades/year.",
        "",
        "## Top Target-Band Candidates",
        "",
        "| Config | Pre/Yr | Val/Yr | Val PF | Val Avg R | Val Calmar | 2024 Trades | 2025 Q1 Trades |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in target_rows[:15]:
        lines.append(
            f"| `{_row_brief(row)}` | {row['pre_holdout_trades_per_year']:.1f} | "
            f"{row['validation_trades_per_year']:.1f} | {row['validation_pf']:.3f} | "
            f"{row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['calendar_2024_trades']} | {row['calendar_2025_q1_trades']} |"
        )

    lines.extend(
        [
            "",
            "## Best Overall Compromises",
            "",
            "| Config | In Band | Pre/Yr | Val/Yr | Val PF | Val Avg R | Val Calmar | 2024 Trades |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in ranked[:15]:
        lines.append(
            f"| `{_row_brief(row)}` | {'yes' if row['pre_holdout_in_target_band'] else 'no'} | "
            f"{row['pre_holdout_trades_per_year']:.1f} | {row['validation_trades_per_year']:.1f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
            f"{row['validation_calmar']:.3f} | {row['calendar_2024_trades']} |"
        )

    for field, field_rows in effects.items():
        lines.extend(
            [
                "",
                f"## Effect: `{field}`",
                "",
                "| Value | Avg Pre/Yr | Avg Val/Yr | Avg Val PF | Avg Val Calmar | Best Val PF | Best Val Calmar |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in field_rows:
            lines.append(
                f"| `{row['value']}` | {row['avg_pre_holdout_trades_per_year']:.1f} | "
                f"{row['avg_validation_trades_per_year']:.1f} | {row['avg_validation_pf']:.3f} | "
                f"{row['avg_validation_calmar']:.3f} | {row['best_validation_pf']:.3f} | "
                f"{row['best_validation_calmar']:.3f} |"
            )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    try:
        ensure_required_data()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    configs = _build_configs()
    print(f"Running {len(configs)} configs...", flush=True)
    results = run_sweep(
        df_base,
        configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )

    rows = [_annotate_row(result_row(cfg.name, cfg, trades), trades) for cfg, trades in results]
    rows = sorted(rows, key=lambda row: _config_key(row))
    anchor_row = next(row for row in rows if _config_key(row) == ANCHOR_KEY)

    target_rows = [
        row
        for row in rows
        if row["pre_holdout_in_target_band"]
        and row["validation_pf"] >= 1.20
        and row["validation_avg_r"] > 0.0
    ]
    ranked = _rank_all(rows)
    target_ranked = _rank_target_band(target_rows)

    effects = {
        field: _param_effects(rows, field)
        for field in (
            "direction_filter",
            "entry_mode",
            "min_gap_atr_pct",
            "lsi_fvg_window_right",
            "max_fvg_to_inversion_bars",
            "htf_trade_max_per_session",
        )
    }

    payload = {
        "target_low": TARGET_LOW,
        "target_high": TARGET_HIGH,
        "years": {
            "pre_holdout_years": PRE_HOLDOUT_YEARS,
            "discovery_years": DISCOVERY_YEARS,
            "validation_years": VALIDATION_YEARS,
        },
        "anchor": anchor_row,
        "top_target_band": target_ranked[:25],
        "top_overall": ranked[:25],
        "all_rows": rows,
        "effects": effects,
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", payload)
    _write_report(anchor_row, ranked, target_ranked, effects)

    print(json.dumps({"anchor": anchor_row, "top_target_band": target_ranked[:10]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
