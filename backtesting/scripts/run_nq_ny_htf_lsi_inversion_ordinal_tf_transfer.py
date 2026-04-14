#!/usr/bin/env python3
"""Cross-timeframe inversion-ordinal transfer study for NQ NY HTF-LSI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    load_timeframe_data,
    result_row,
    save_json,
    slice_trades,
)

LAG_CURVE_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lag_curve"
OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_inversion_ordinal_tf_transfer"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_INVERSION_ORDINAL_TF_TRANSFER.md"

SESSION_LEVELS = (
    "new_york_high",
    "new_york_low",
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
)
ORDINALS = (1, 2, 3)
FAMILIES = (
    {
        "family": "htf_only",
        "include_htf_levels": True,
        "reference_levels": (),
        "description": "HTF 1h unswept highs/lows only",
    },
    {
        "family": "htf_plus_session",
        "include_htf_levels": True,
        "reference_levels": SESSION_LEVELS,
        "description": "HTF 1h levels plus NY / Asia / London session highs/lows",
    },
)
ANCHORS = {
    "1m": {
        "lag": 0,
        "note": "honest 1m lag-curve baseline; the later lag10 pop was never promoted beyond validation",
    },
    "2m": {
        "lag": 0,
        "note": "frozen 2m secondary anchor used in the session/data source experiments",
    },
    "3m": {
        "lag": 0,
        "note": "honest 3m baseline; 3m remains closed because discovery stayed too weak",
    },
    "5m": {
        "lag": 24,
        "note": "promoted frozen 5m lead from the late-lag follow-up",
    },
}


def _load_anchor_row(timeframe: str) -> dict:
    lag = ANCHORS[timeframe]["lag"]
    rows = json.loads((LAG_CURVE_DIR / f"{timeframe}.json").read_text())
    return next(row for row in rows if int(row["max_fvg_to_inversion_bars"]) == lag)

def _config_from_anchor(anchor_row: dict, *, family: dict, ordinal: int):
    from htf_lsi_common import build_config

    return build_config(
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
        htf_lsi_inversion_ordinal=ordinal,
        htf_lsi_include_htf_levels=family["include_htf_levels"],
        htf_lsi_reference_levels=family["reference_levels"],
        lsi_fvg_window_left=int(anchor_row["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(anchor_row["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(anchor_row["max_fvg_to_inversion_bars"]),
        entry_context_gate=anchor_row.get("entry_context_gate", ""),
        entry_context_min_atr=float(anchor_row.get("entry_context_min_atr", 0.0)),
        entry_context_max_atr=float(anchor_row.get("entry_context_max_atr", 0.0)),
        name=(
            f"NQ NY HTF_LSI {anchor_row['timeframe']} inversion-ordinal "
            f"{family['family']} inv{ordinal}"
        ),
    )


def _stitched_oos_from_trades(trades) -> dict:
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


def _sort_key(row: dict) -> tuple:
    wf = row["walkforward"]["combined"]
    return (
        wf["calmar"],
        wf["pf"],
        wf["avg_r"],
        row["validation_calmar"],
        row["validation_pf"],
        row["validation_avg_r"],
    )


def _write_report(summary: dict[str, dict], rows: list[dict]) -> None:
    lines = [
        "# NQ NY HTF-LSI Inversion-Ordinal TF Transfer",
        "",
        "- Objective: test whether waiting for inversion `#2` or `#3` helps outside the original `2m` packet when we only keep the two live liquidity families: `htf_only` and `htf_plus_session`.",
        "- Holdout stays closed. This is a pre-holdout stitched-OOS transfer packet only.",
        "- Fixed-config stitched OOS is computed by slicing each full-period trade stream into the standard `36m IS / 12m OOS / 12m step` windows.",
        "- Families tested: `htf_only`, `htf_plus_session`.",
        "- Inversion ordinals tested: `1`, `2`, `3`.",
        "",
        "## Anchors",
        "",
        "| Timeframe | Anchor | Entry | Window | RR | TP1 | Cap | FVG Window | Note |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for timeframe in ("1m", "2m", "3m", "5m"):
        anchor = summary[timeframe]["anchor"]
        lines.append(
            f"| {timeframe} | lag={anchor['max_fvg_to_inversion_bars']} | "
            f"{anchor['direction_filter']} / {anchor['entry_mode']} | "
            f"{anchor['entry_start']}-{anchor['entry_end']} | {anchor['rr']:.1f} | {anchor['tp1_ratio']:.1f} | "
            f"{anchor['htf_trade_max_per_session']} | L{anchor['lsi_fvg_window_left']} / R{anchor['lsi_fvg_window_right']} | "
            f"{ANCHORS[timeframe]['note']} |"
        )

    lines.extend(
        [
            "",
            "## Best Row By Timeframe / Family",
            "",
            "| Timeframe | Family | Best Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for timeframe in ("1m", "2m", "3m", "5m"):
        for family in ("htf_only", "htf_plus_session"):
            best = summary[timeframe]["best_by_family"][family]
            wf = best["walkforward"]["combined"]
            lines.append(
                f"| {timeframe} | {family} | {best['htf_lsi_inversion_ordinal']} | "
                f"{best['discovery_pf']:.3f} | {best['discovery_avg_r']:.3f} | "
                f"{best['validation_pf']:.3f} | {best['validation_avg_r']:.3f} | {best['validation_calmar']:.3f} | "
                f"{wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} |"
            )

    lines.extend(
        [
            "",
            "## Full Matrix",
            "",
            "| Timeframe | Family | Ordinal | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(rows, key=lambda item: (item["timeframe"], item["family"], item["htf_lsi_inversion_ordinal"])):
        wf = row["walkforward"]["combined"]
        lines.append(
            f"| {row['timeframe']} | {row['family']} | {row['htf_lsi_inversion_ordinal']} | "
            f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['validation_trades']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | {wf['calmar']:.3f} | "
            f"{wf['trades']} | {wf['max_dd_r']:.2f} |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    all_rows: list[dict] = []
    summary: dict[str, dict] = {}

    for timeframe in ("1m", "2m", "3m", "5m"):
        anchor_row = _load_anchor_row(timeframe)
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        configs = [
            _config_from_anchor(anchor_row, family=family, ordinal=ordinal)
            for family in FAMILIES
            for ordinal in ORDINALS
        ]

        print(f"Running {timeframe} inversion-ordinal transfer packet ({len(configs)} configs)...", flush=True)
        results = run_sweep(
            df_base,
            configs,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )

        timeframe_rows = []
        total = len(results)
        for idx, (cfg, trades) in enumerate(results, start=1):
            family = "htf_plus_session" if tuple(cfg.htf_lsi_reference_levels) == SESSION_LEVELS else "htf_only"
            print(
                f"  {timeframe} stitched OOS {idx}/{total}: {family} inv{cfg.htf_lsi_inversion_ordinal}",
                flush=True,
            )
            row = result_row(cfg.name, cfg, trades) | {
                "timeframe": timeframe,
                "family": family,
                "anchor_lag": int(anchor_row["max_fvg_to_inversion_bars"]),
            }
            row["walkforward"] = _stitched_oos_from_trades(trades)
            timeframe_rows.append(row)

        best_by_family = {
            family["family"]: max(
                [row for row in timeframe_rows if row["family"] == family["family"]],
                key=_sort_key,
            )
            for family in FAMILIES
        }

        summary[timeframe] = {
            "anchor": {
                "max_fvg_to_inversion_bars": int(anchor_row["max_fvg_to_inversion_bars"]),
                "direction_filter": anchor_row["direction_filter"],
                "entry_mode": anchor_row["entry_mode"],
                "entry_start": anchor_row["entry_start"],
                "entry_end": anchor_row["entry_end"],
                "rr": float(anchor_row["rr"]),
                "tp1_ratio": float(anchor_row["tp1_ratio"]),
                "htf_trade_max_per_session": int(anchor_row["htf_trade_max_per_session"]),
                "lsi_fvg_window_left": int(anchor_row["lsi_fvg_window_left"]),
                "lsi_fvg_window_right": int(anchor_row["lsi_fvg_window_right"]),
            },
            "best_by_family": best_by_family,
            "rows": timeframe_rows,
        }
        save_json(OUTPUT_DIR / f"{timeframe}.json", timeframe_rows)
        all_rows.extend(timeframe_rows)

    save_json(OUTPUT_DIR / "summary.json", summary)
    _write_report(summary, all_rows)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
