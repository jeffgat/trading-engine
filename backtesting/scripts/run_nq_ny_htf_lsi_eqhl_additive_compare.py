#!/usr/bin/env python3
"""Focused additive comparison for NQ NY HTF-LSI 5m lag24 lead.

Compares the current 5m lag24 HTF-only operating lead against a narrow
HTF+EQHL additive shortlist, keeping the holdout closed:

1. HTF-only current lead
2. HTF + 5m EQHL (tol 1)
3. HTF + 5m EQHL (tol 2)
4. HTF + 15m EQHL (tol 1)
5. HTF + 15m EQHL (tol 2)

All non-source parameters stay frozen to the current operating lead.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    PRE_HOLDOUT_END,
    VALIDATION_START,
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
    summarize_periods,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_eqhl_additive_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_EQHL_ADDITIVE_COMPARE.md"


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def stitched_oos(config, df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache) -> dict:
    windows = generate_windows(DISCOVERY_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined = []
    folds = []
    for window in windows:
        trades = run_backtest(
            df_base,
            config,
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
                "pf": float(metrics["profit_factor"]),
                "avg_r": float(metrics["avg_r"]),
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
            "pf": float(combined_metrics["profit_factor"]),
            "avg_r": float(combined_metrics["avg_r"]),
            "calmar": float(combined_metrics["calmar_ratio"]),
            "max_dd_r": float(combined_metrics["max_drawdown_r"]),
            "total_r": float(combined_metrics["total_r"]),
        },
    }


def make_candidates():
    base = build_current_nq_ny_htf_lsi_lag24_config(name="NQ NY HTF_LSI 5m lag24 lead")
    candidates = [
        {
            "label": "htf_only",
            "config": base,
            "source_mode": "htf_only",
            "eqhl_tf": None,
            "eqhl_tolerance_ticks": None,
        }
    ]
    for eqhl_tf in (5, 15):
        for tol in (1, 2):
            cfg = replace(
                base,
                htf_lsi_include_eqhl_levels=True,
                eqhl_level_tf_minutes=eqhl_tf,
                eqhl_n_left=2,
                eqhl_tolerance_ticks=tol,
                eqhl_min_touches=2,
                eqhl_lookback_bars=48,
                name=f"NQ NY HTF_LSI 5m lag24 + EQHL{eqhl_tf}m tol{tol}",
            )
            candidates.append(
                {
                    "label": f"htf_plus_eqhl_{eqhl_tf}m_tol{tol}",
                    "config": cfg,
                    "source_mode": "htf_plus_eqhl",
                    "eqhl_tf": eqhl_tf,
                    "eqhl_tolerance_ticks": tol,
                }
            )
    return candidates


def make_row(candidate: dict, trades, wf: dict) -> dict:
    config = candidate["config"]
    summary = summarize_periods(trades)
    session = config.sessions[0]
    return {
        "label": candidate["label"],
        "config_name": config.name,
        "source_mode": candidate["source_mode"],
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "rr": float(config.rr),
        "tp1_ratio": float(config.tp1_ratio),
        "min_gap_atr_pct": float(session.min_gap_atr_pct),
        "htf_level_tf_minutes": int(config.htf_level_tf_minutes),
        "htf_n_left": int(config.htf_n_left),
        "htf_trade_max_per_session": int(config.htf_trade_max_per_session),
        "max_fvg_to_inversion_bars": int(config.max_fvg_to_inversion_bars),
        "lsi_fvg_window_left": int(config.lsi_fvg_window_left),
        "lsi_fvg_window_right": int(config.lsi_fvg_window_right),
        "eqhl_level_tf_minutes": candidate["eqhl_tf"],
        "eqhl_tolerance_ticks": candidate["eqhl_tolerance_ticks"],
        "pre_holdout_trades": int(summary["pre_holdout"]["total_trades"]),
        "pre_holdout_pf": float(summary["pre_holdout"]["profit_factor"]),
        "pre_holdout_avg_r": float(summary["pre_holdout"]["avg_r"]),
        "pre_holdout_total_r": float(summary["pre_holdout"]["total_r"]),
        "pre_holdout_calmar": float(summary["pre_holdout"]["calmar_ratio"]),
        "discovery_trades": int(summary["discovery"]["total_trades"]),
        "discovery_pf": float(summary["discovery"]["profit_factor"]),
        "discovery_avg_r": float(summary["discovery"]["avg_r"]),
        "discovery_total_r": float(summary["discovery"]["total_r"]),
        "validation_trades": int(summary["validation"]["total_trades"]),
        "validation_pf": float(summary["validation"]["profit_factor"]),
        "validation_avg_r": float(summary["validation"]["avg_r"]),
        "validation_total_r": float(summary["validation"]["total_r"]),
        "validation_calmar": float(summary["validation"]["calmar_ratio"]),
        "validation_max_dd_r": float(summary["validation"]["max_drawdown_r"]),
        "wf_trades": int(wf["combined"]["trades"]),
        "wf_pf": float(wf["combined"]["pf"]),
        "wf_avg_r": float(wf["combined"]["avg_r"]),
        "wf_total_r": float(wf["combined"]["total_r"]),
        "wf_calmar": float(wf["combined"]["calmar"]),
        "wf_max_dd_r": float(wf["combined"]["max_dd_r"]),
        "walkforward": wf,
    }


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["wf_calmar"],
            row["wf_pf"],
            row["wf_avg_r"],
            row["validation_calmar"],
            row["validation_pf"],
            row["discovery_pf"],
            row["discovery_avg_r"],
        ),
        reverse=True,
    )


def write_report(rows: list[dict]) -> None:
    lines = [
        "# NQ NY HTF-LSI EQHL Additive Compare",
        "",
        "- Objective: compare the current `5m lag24` HTF-only lead against a narrow additive `HTF + EQHL` shortlist.",
        "- Scope: holdout stays closed. All non-source parameters are frozen to the current `5m lag24` operating lead (`08:30-13:30`, `rr3.5`, `tp1=0.4`, `gap3.0`, `htf60 n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`).",
        "- Additive shortlist: EQHL source TF `{5m,15m}` x tolerance `{1,2}` with `touches=2`, `eqhl_n_left=2`, `lookback=48`.",
        "",
        "| Label | Source | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        source = "HTF-only" if row["source_mode"] == "htf_only" else f"HTF+EQHL {row['eqhl_level_tf_minutes']}m tol{row['eqhl_tolerance_ticks']}"
        lines.append(
            f"| {row['config_name']} | {source} | "
            f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
            f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | "
            f"{row['wf_pf']:.3f} | {row['wf_avg_r']:.3f} | {row['wf_calmar']:.3f} | {row['wf_trades']} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    candidates = make_candidates()
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    configs = [candidate["config"] for candidate in candidates]

    print(f"Loaded {len(candidates)} additive candidates", flush=True)
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)

    rows: list[dict] = []
    for candidate in candidates:
        print(f"[{candidate['label']}] running pre-holdout stream...", flush=True)
        trades = run_backtest(
            df_base,
            candidate["config"],
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        print(f"[{candidate['label']}] reconstructing stitched OOS...", flush=True)
        wf = stitched_oos(candidate["config"], df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache)
        rows.append(make_row(candidate, trades, wf))

    rows = sort_rows(rows)
    pd.DataFrame([{k: v for k, v in row.items() if k != "walkforward"} for row in rows]).to_csv(
        OUTPUT_DIR / "ranking.csv", index=False
    )
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(rows, indent=2))
    write_report(rows)
    print(f"Saved additive comparison to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
