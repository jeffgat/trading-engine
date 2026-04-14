#!/usr/bin/env python3
"""Compare 1st/2nd/3rd inversion selection on the frozen NQ NY HTF-LSI 2m anchor."""

from __future__ import annotations

import json
import sys
from collections import Counter
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
    VALIDATION_START,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    result_row,
    save_json,
    slice_trades,
)

OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_2m_inversion_ordinal_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_2M_INVERSION_ORDINAL_COMPARE.md"

SESSION_LEVELS = (
    "new_york_high",
    "new_york_low",
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
)
DATA_LEVELS = (
    "data_high",
    "data_low",
)
ORDINALS = (1, 2, 3)

VARIANTS = (
    {
        "family": "htf_only",
        "include_htf_levels": True,
        "reference_levels": (),
        "description": "HTF 1h unswept highs/lows only",
    },
    {
        "family": "session_only",
        "include_htf_levels": False,
        "reference_levels": SESSION_LEVELS,
        "description": "NY / Asia / London session highs/lows only",
    },
    {
        "family": "htf_plus_session",
        "include_htf_levels": True,
        "reference_levels": SESSION_LEVELS,
        "description": "HTF 1h levels plus session highs/lows",
    },
    {
        "family": "data_only",
        "include_htf_levels": False,
        "reference_levels": DATA_LEVELS,
        "description": "Same-day data_high/data_low only",
    },
    {
        "family": "htf_plus_data",
        "include_htf_levels": True,
        "reference_levels": DATA_LEVELS,
        "description": "HTF 1h levels plus data_high/data_low",
    },
    {
        "family": "all_sources",
        "include_htf_levels": True,
        "reference_levels": SESSION_LEVELS + DATA_LEVELS,
        "description": "HTF 1h levels plus session highs/lows plus data_high/data_low",
    },
)


def _build_configs():
    base_kwargs = dict(
        timeframe="2m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start="08:30",
        entry_end="15:00",
        rr=3.0,
        tp1_ratio=0.6,
        min_gap_atr_pct=3.0,
        atr_length=14,
        htf_level_tf_minutes=60,
        htf_n_left=3,
        htf_trade_max_per_session=1,
        data_sweep_min_daily_atr_pct=15.0,
        lsi_fvg_window_left=50,
        lsi_fvg_window_right=5,
        max_fvg_to_inversion_bars=0,
    )
    configs = []
    for variant in VARIANTS:
        for ordinal in ORDINALS:
            configs.append(
                build_config(
                    **base_kwargs,
                    htf_lsi_inversion_ordinal=ordinal,
                    htf_lsi_include_htf_levels=variant["include_htf_levels"],
                    htf_lsi_reference_levels=variant["reference_levels"],
                    name=f"NQ NY HTF_LSI 2m inversion-ordinal {variant['family']} inv{ordinal}",
                )
            )
    return configs


def _family_from_config(config) -> str:
    include_htf = config.htf_lsi_include_htf_levels
    ref_levels = tuple(config.htf_lsi_reference_levels)
    if include_htf and not ref_levels:
        return "htf_only"
    if (not include_htf) and ref_levels == SESSION_LEVELS:
        return "session_only"
    if include_htf and ref_levels == SESSION_LEVELS:
        return "htf_plus_session"
    if (not include_htf) and ref_levels == DATA_LEVELS:
        return "data_only"
    if include_htf and ref_levels == DATA_LEVELS:
        return "htf_plus_data"
    return "all_sources"


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


def _source_breakdown(trades) -> dict:
    pre_holdout = [t for t in trades if t.exit_type != simulator.EXIT_NO_FILL and t.date < HOLDOUT_START]
    validation = [t for t in pre_holdout if t.date >= VALIDATION_START]
    pre_ref_counts = Counter(t.reference_level_name for t in pre_holdout if t.reference_level_name)
    val_ref_counts = Counter(t.reference_level_name for t in validation if t.reference_level_name)
    return {
        "pre_holdout_filled_trades": len(pre_holdout),
        "validation_filled_trades": len(validation),
        "pre_holdout_htf_trades": sum(1 for t in pre_holdout if t.htf_level_tf_minutes > 0 and not t.reference_level_name),
        "pre_holdout_reference_trades": sum(1 for t in pre_holdout if bool(t.reference_level_name)),
        "validation_htf_trades": sum(1 for t in validation if t.htf_level_tf_minutes > 0 and not t.reference_level_name),
        "validation_reference_trades": sum(1 for t in validation if bool(t.reference_level_name)),
        "pre_holdout_reference_levels": dict(pre_ref_counts),
        "validation_reference_levels": dict(val_ref_counts),
    }


def _sort_key(row: dict) -> tuple:
    wf = row["walkforward"]["combined"]
    return (
        wf["calmar"],
        wf["pf"],
        wf["avg_r"],
        row["validation_calmar"],
        row["validation_pf"],
    )


def _write_report(rows: list[dict]) -> None:
    best_by_family = []
    for variant in VARIANTS:
        family_rows = [row for row in rows if row["family"] == variant["family"]]
        if family_rows:
            best_by_family.append(max(family_rows, key=_sort_key))

    lines = [
        "# NQ NY HTF-LSI 2m Inversion-Ordinal Compare",
        "",
        "- Objective: test whether waiting for inversion `#2` or `#3` after the sweep improves the frozen `2m` HTF-LSI anchor versus the base `#1` inversion.",
        "- Holdout stays closed. This is a pre-holdout stitched-OOS packet only.",
        "- Fixed anchor: `2m`, `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `max_fvg_to_inversion_bars=0`.",
        "- Tested inversion ordinals: `1`, `2`, `3`.",
        "",
        "## Liquidity Families",
        "",
        "| Family | Description |",
        "| --- | --- |",
    ]
    for variant in VARIANTS:
        lines.append(f"| {variant['family']} | {variant['description']} |")

    lines.extend(
        [
            "",
            "## Best Row By Family",
            "",
            "| Family | Best Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(best_by_family, key=_sort_key, reverse=True):
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['family']} | {row['htf_lsi_inversion_ordinal']} | "
            f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Full Matrix",
            "",
            "| Family | Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(rows, key=lambda row: (row["family"], row["htf_lsi_inversion_ordinal"])):
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['family']} | {row['htf_lsi_inversion_ordinal']} | "
            f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['validation_trades']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | "
            f"{wf['trades']} | {wf['max_dd_r']:.2f} |"
        )

    lines.extend(["", "## Reference-Level Flow", ""])
    for row in sorted(best_by_family, key=_sort_key, reverse=True):
        lines.append(f"### {row['family']} (best ordinal = {row['htf_lsi_inversion_ordinal']})")
        lines.append("")
        src = row["source_breakdown"]
        lines.append(
            f"- Pre-holdout filled `{src['pre_holdout_filled_trades']}`, HTF `{src['pre_holdout_htf_trades']}`, reference/data `{src['pre_holdout_reference_trades']}`"
        )
        lines.append(
            f"- Validation filled `{src['validation_filled_trades']}`, HTF `{src['validation_htf_trades']}`, reference/data `{src['validation_reference_trades']}`"
        )
        pre_counts = src["pre_holdout_reference_levels"]
        val_counts = src["validation_reference_levels"]
        if not pre_counts and not val_counts:
            lines.append("- No reference/data-driven filled trades.")
            lines.append("")
            continue
        lines.append("")
        lines.append("| Level | Pre-Holdout Trades | Validation Trades |")
        lines.append("| --- | ---: | ---: |")
        for level in SESSION_LEVELS + DATA_LEVELS:
            lines.append(f"| {level} | {pre_counts.get(level, 0)} | {val_counts.get(level, 0)} |")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("2m")
    configs = _build_configs()

    print(f"Running {len(configs)} NQ NY HTF-LSI 2m inversion-ordinal configs...", flush=True)
    results = run_sweep(
        df_base,
        configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )

    rows = []
    total = len(results)
    for idx, (cfg, trades) in enumerate(results, start=1):
        print(f"Stitched OOS {idx}/{total}: {_family_from_config(cfg)} inv{cfg.htf_lsi_inversion_ordinal}", flush=True)
        row = result_row(cfg.name, cfg, trades)
        row["family"] = _family_from_config(cfg)
        row["walkforward"] = _stitched_oos(cfg, df_base, df_1m, df_1s, signal_df_1m)
        row["source_breakdown"] = _source_breakdown(trades)
        rows.append(row)

    rows.sort(key=lambda row: (row["family"], row["htf_lsi_inversion_ordinal"]))

    payload = {
        "anchor": {
            "timeframe": "2m",
            "direction_filter": "long",
            "entry_mode": "fvg_limit",
            "entry_window": "08:30-15:00",
            "rr": 3.0,
            "tp1_ratio": 0.6,
            "min_gap_atr_pct": 3.0,
            "atr_length": 14,
            "htf_level_tf_minutes": 60,
            "htf_n_left": 3,
            "htf_trade_max_per_session": 1,
            "htf_lsi_inversion_ordinal_values": list(ORDINALS),
            "lsi_fvg_window_left": 50,
            "lsi_fvg_window_right": 5,
            "max_fvg_to_inversion_bars": 0,
        },
        "families": [
            {
                "family": variant["family"],
                "description": variant["description"],
                "include_htf_levels": variant["include_htf_levels"],
                "reference_levels": list(variant["reference_levels"]),
            }
            for variant in VARIANTS
        ],
        "rows": rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", payload)
    _write_report(rows)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
