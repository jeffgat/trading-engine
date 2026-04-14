#!/usr/bin/env python3
"""Screen and shortlist macro-window data-sweep variants on the NQ NY 2m anchor."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.engine import simulator
from orb_backtest.optimize.parallel import _load_or_build_signal_cache, run_sweep
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

OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_2m_data_macro_window_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_2M_DATA_MACRO_WINDOW_COMPARE.md"

DATA_LEVELS = (
    "data_high",
    "data_low",
)
DATA_SWEEP_MIN_DAILY_ATR_PCT = 15.0
EVENT_TYPES = ("NFP", "CPI", "PPI", "FOMC")
RELEASE_WINDOWS = (0, 1, 2, 5)
SHORTLIST_SIZE = 3


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
        data_sweep_require_session_extreme=True,
        data_sweep_event_types=EVENT_TYPES,
        lsi_fvg_window_left=50,
        lsi_fvg_window_right=5,
        max_fvg_to_inversion_bars=0,
    )
    variants = [
        build_config(
            **base_kwargs,
            htf_lsi_include_htf_levels=True,
            htf_lsi_reference_levels=(),
            name="NQ NY HTF_LSI 2m anchor data-macro htf_only",
        )
    ]
    for release_window_minutes in RELEASE_WINDOWS:
        variants.append(
            build_config(
                **base_kwargs,
                htf_lsi_include_htf_levels=False,
                htf_lsi_reference_levels=DATA_LEVELS,
                data_sweep_release_window_minutes=release_window_minutes,
                name=f"NQ NY HTF_LSI 2m anchor data-macro data_only w{release_window_minutes}",
            )
        )
        variants.append(
            build_config(
                **base_kwargs,
                htf_lsi_include_htf_levels=True,
                htf_lsi_reference_levels=DATA_LEVELS,
                data_sweep_release_window_minutes=release_window_minutes,
                name=f"NQ NY HTF_LSI 2m anchor data-macro htf_plus_data w{release_window_minutes}",
            )
        )
    return variants


def _source_mode(config) -> str:
    if config.htf_lsi_include_htf_levels and config.htf_lsi_reference_levels:
        return "htf_plus_data"
    if config.htf_lsi_include_htf_levels:
        return "htf_only"
    return "data_only"


def _variant_key(config) -> str:
    mode = _source_mode(config)
    if mode == "htf_only":
        return mode
    return f"{mode}_w{config.data_sweep_release_window_minutes}"


def _screen_sort_key(row: dict) -> tuple:
    return (
        row["validation_calmar"],
        row["validation_pf"],
        row["validation_avg_r"],
        row["validation_trades"],
    )


def _oos_sort_key(row: dict) -> tuple:
    wf = row["walkforward"]["combined"]
    return (
        wf["calmar"],
        wf["pf"],
        wf["avg_r"],
        row["validation_calmar"],
        row["validation_pf"],
    )


def _stitched_oos(cfg, df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache) -> dict:
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
            _maps=maps,
            _signal_cache=signal_cache,
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


def _write_report(screen_rows: list[dict], finalist_rows: list[dict]) -> None:
    lines = [
        "# NQ NY HTF-LSI 2m Data Macro-Window Compare",
        "",
        "- Objective: continue the `data_high/data_low` idea with the cleaner scheduled macro-release thesis.",
        "- Data level definition: completed `1m` candle with range >= `15%` of previous-day ATR; keep only candles that also print a new running NY-session extreme and occur within the configured post-release window for `NFP`, `CPI`, `PPI`, or `FOMC`.",
        "- Anchor: `long`, `fvg_limit`, `08:30-15:00`, `rr=3.0`, `tp1=0.6`, `gap=3.0`, `atr14`, `htf60 n3`, `cap1`, `left50`, `right5`, `lag0`.",
        f"- Data-level basket: `{', '.join(DATA_LEVELS)}` at `data_sweep_min_daily_atr_pct={DATA_SWEEP_MIN_DAILY_ATR_PCT}`, `data_sweep_require_session_extreme=True`, event types `{', '.join(EVENT_TYPES)}`.",
        f"- Screening packet: windows `{', '.join(str(window) for window in RELEASE_WINDOWS)}` minutes after the scheduled release (`0` = release-minute candle only).",
        f"- Shortlist policy: always keep `htf_only`, then stitch only the top `{SHORTLIST_SIZE}` challengers by validation Calmar / PF / avg R.",
        "",
        "## Screening",
        "",
        "| Variant | Mode | Window | Val PF | Val Avg R | Val Calmar | Val Trades | Disc PF | Disc Avg R |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in screen_rows:
        lines.append(
            f"| {row['variant']} | {row['source_mode']} | {row['release_window_minutes']} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['validation_trades']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} |"
        )

    lines.extend(
        [
            "",
            "## Finalists",
            "",
            "| Variant | Mode | Window | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD | Val PF | Val Avg R | Val Calmar |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in finalist_rows:
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['variant']} | {row['source_mode']} | {row['release_window_minutes']} | "
            f"{wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} |"
        )

    lines.extend(["", "## Finalist Source Use", ""])
    lines.extend(
        [
            "| Variant | Pre-Holdout Filled | Pre HTF | Pre Data | Validation Filled | Val HTF | Val Data |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in finalist_rows:
        src = row["source_breakdown"]
        lines.append(
            f"| {row['variant']} | {src['pre_holdout_filled_trades']} | {src['pre_holdout_htf_trades']} | "
            f"{src['pre_holdout_data_trades']} | {src['validation_filled_trades']} | "
            f"{src['validation_htf_trades']} | {src['validation_data_trades']} |"
        )

    lines.extend(["", "## Finalist Data-Level Breakdown", ""])
    for row in finalist_rows:
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

    maps = simulator.build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = _load_or_build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)

    print("Running NQ NY HTF-LSI 2m data macro-window screening...", flush=True)
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

    rows_by_variant = {}
    for cfg, trades in results:
        row = result_row(cfg.name, cfg, trades)
        row["variant"] = _variant_key(cfg)
        row["source_mode"] = _source_mode(cfg)
        row["release_window_minutes"] = int(cfg.data_sweep_release_window_minutes)
        row["source_breakdown"] = _source_breakdown(trades)
        rows_by_variant[row["variant"]] = row

    screen_rows = sorted(rows_by_variant.values(), key=_screen_sort_key, reverse=True)
    baseline = rows_by_variant["htf_only"]
    challengers = [row for row in screen_rows if row["variant"] != "htf_only"]
    finalist_rows = [baseline, *challengers[:SHORTLIST_SIZE]]

    print("Running stitched OOS on macro-window finalists...", flush=True)
    for row in finalist_rows:
        cfg = next(config for config in configs if _variant_key(config) == row["variant"])
        row["walkforward"] = _stitched_oos(cfg, df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache)

    finalist_rows.sort(key=_oos_sort_key, reverse=True)

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
            "data_sweep_require_session_extreme": True,
            "data_sweep_event_types": list(EVENT_TYPES),
            "release_windows": list(RELEASE_WINDOWS),
            "shortlist_size": SHORTLIST_SIZE,
            "lsi_fvg_window_left": 50,
            "lsi_fvg_window_right": 5,
            "max_fvg_to_inversion_bars": 0,
        },
        "data_levels": list(DATA_LEVELS),
        "screen_rows": screen_rows,
        "finalist_rows": finalist_rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", payload)
    _write_report(screen_rows, finalist_rows)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
