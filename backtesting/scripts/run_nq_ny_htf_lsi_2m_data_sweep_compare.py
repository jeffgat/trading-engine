#!/usr/bin/env python3
"""Compare HTF-LSI data-sweep variants on the frozen NQ NY 2m anchor."""

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

OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_2m_data_sweep_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_2M_DATA_SWEEP_COMPARE.md"

DATA_LEVELS = (
    "data_high",
    "data_low",
)
DATA_SWEEP_MIN_DAILY_ATR_PCT = 15.0


def _build_variants():
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
        data_sweep_min_daily_atr_pct=DATA_SWEEP_MIN_DAILY_ATR_PCT,
        lsi_fvg_window_left=50,
        lsi_fvg_window_right=5,
        max_fvg_to_inversion_bars=0,
    )
    return [
        build_config(
            **base_kwargs,
            htf_lsi_include_htf_levels=True,
            htf_lsi_reference_levels=(),
            name="NQ NY HTF_LSI 2m anchor data-sweep htf_only",
        ),
        build_config(
            **base_kwargs,
            htf_lsi_include_htf_levels=False,
            htf_lsi_reference_levels=DATA_LEVELS,
            name="NQ NY HTF_LSI 2m anchor data-sweep data_only",
        ),
        build_config(
            **base_kwargs,
            htf_lsi_include_htf_levels=True,
            htf_lsi_reference_levels=DATA_LEVELS,
            name="NQ NY HTF_LSI 2m anchor data-sweep htf_plus_data",
        ),
    ]


def _variant_key(config) -> str:
    if config.htf_lsi_include_htf_levels and config.htf_lsi_reference_levels:
        return "htf_plus_data"
    if config.htf_lsi_include_htf_levels:
        return "htf_only"
    return "data_only"


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
    reference_counts = Counter(t.reference_level_name for t in pre_holdout if t.reference_level_name)
    validation_reference_counts = Counter(t.reference_level_name for t in validation if t.reference_level_name)
    return {
        "pre_holdout_filled_trades": len(pre_holdout),
        "validation_filled_trades": len(validation),
        "pre_holdout_htf_trades": sum(1 for t in pre_holdout if t.htf_level_tf_minutes > 0 and not t.reference_level_name),
        "pre_holdout_data_trades": sum(1 for t in pre_holdout if bool(t.reference_level_name)),
        "validation_htf_trades": sum(1 for t in validation if t.htf_level_tf_minutes > 0 and not t.reference_level_name),
        "validation_data_trades": sum(1 for t in validation if bool(t.reference_level_name)),
        "pre_holdout_data_levels": dict(reference_counts),
        "validation_data_levels": dict(validation_reference_counts),
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
    lines = [
        "# NQ NY HTF-LSI 2m Data-Sweep Compare",
        "",
        "- Objective: compare HTF pivots versus new `data_high/data_low` sweep sources on the frozen `2m` anchor.",
        "- Data level definition: completed `1m` candle with range >= `15%` of previous-day ATR; its high/low become valid on the first eligible base bar after the `1m` close and stay active for the rest of that day.",
        "- Anchor: `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `lag0`.",
        f"- Data-level basket: `{', '.join(DATA_LEVELS)}` at `data_sweep_min_daily_atr_pct={DATA_SWEEP_MIN_DAILY_ATR_PCT}`.",
        f"- Stitched OOS: `36m IS / 12m OOS / 12m step` from `{DISCOVERY_START}` to `{HOLDOUT_START}`.",
        "",
        "## Summary",
        "",
        "| Variant | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['variant']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['validation_trades']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | "
            f"{wf['trades']} | {wf['max_dd_r']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Source Use",
            "",
            "| Variant | Pre-Holdout Filled | Pre HTF | Pre Data | Validation Filled | Val HTF | Val Data |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        src = row["source_breakdown"]
        lines.append(
            f"| {row['variant']} | {src['pre_holdout_filled_trades']} | {src['pre_holdout_htf_trades']} | "
            f"{src['pre_holdout_data_trades']} | {src['validation_filled_trades']} | "
            f"{src['validation_htf_trades']} | {src['validation_data_trades']} |"
        )

    lines.extend(["", "## Data-Level Breakdown", ""])
    for row in rows:
        lines.append(f"### {row['variant']}")
        lines.append("")
        pre_counts = row["source_breakdown"]["pre_holdout_data_levels"]
        val_counts = row["source_breakdown"]["validation_data_levels"]
        if not pre_counts and not val_counts:
            lines.append("No data-driven filled trades.")
            lines.append("")
            continue
        lines.append("| Level | Pre-Holdout Trades | Validation Trades |")
        lines.append("| --- | ---: | ---: |")
        for level in DATA_LEVELS:
            lines.append(f"| {level} | {pre_counts.get(level, 0)} | {val_counts.get(level, 0)} |")
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data()
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("2m")
    configs = _build_variants()

    print("Running NQ NY HTF-LSI 2m data-sweep comparison...", flush=True)
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
    for cfg, trades in results:
        row = result_row(cfg.name, cfg, trades)
        row["variant"] = _variant_key(cfg)
        row["walkforward"] = _stitched_oos(cfg, df_base, df_1m, df_1s, signal_df_1m)
        row["source_breakdown"] = _source_breakdown(trades)
        rows.append(row)

    rows.sort(key=_sort_key, reverse=True)

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
            "data_sweep_min_daily_atr_pct": DATA_SWEEP_MIN_DAILY_ATR_PCT,
            "lsi_fvg_window_left": 50,
            "lsi_fvg_window_right": 5,
            "max_fvg_to_inversion_bars": 0,
        },
        "data_levels": list(DATA_LEVELS),
        "rows": rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", payload)
    _write_report(rows)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
