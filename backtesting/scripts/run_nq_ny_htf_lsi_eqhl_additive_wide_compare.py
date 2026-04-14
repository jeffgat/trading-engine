#!/usr/bin/env python3
"""Wide additive EQHL comparison for the frozen NQ NY HTF-LSI 5m lag24 lead.

Keeps the full 5m lag24 operating branch frozen and varies only the additive EQHL
source family:

1. HTF-only base
2. Current additive incumbent: HTF + 15m EQHL tol1
3. Wide additive EQHL: source TF {5m, 15m, 60m} x tolerance {3, 5, 10, 15, 20} points

Holdout stays closed in this step. This is the selection packet before any further
downstream promotion.
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    VALIDATION_START,
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
    summarize_periods,
)
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_eqhl_additive_wide_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_EQHL_ADDITIVE_WIDE_COMPARE.md"
POINT_TOLERANCES = (3.0, 5.0, 10.0, 15.0, 20.0)
EQHL_SOURCE_TFS = (5, 15, 60)


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


def points_to_ticks(points: float) -> int:
    return int(round(points / float(NQ.min_tick)))


def make_candidates():
    base = build_current_nq_ny_htf_lsi_lag24_config(name="NQ NY HTF_LSI 5m lag24 htf_only control")
    incumbent = replace(
        base,
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 incumbent",
    )
    candidates = [
        {
            "label": "htf_only",
            "family": "htf_only",
            "config": base,
            "eqhl_tf": None,
            "eqhl_tolerance_ticks": None,
            "eqhl_tolerance_points": None,
        },
        {
            "label": "htf_plus_eqhl_15m_tol1_incumbent",
            "family": "incumbent_tight",
            "config": incumbent,
            "eqhl_tf": 15,
            "eqhl_tolerance_ticks": 1,
            "eqhl_tolerance_points": float(NQ.min_tick),
        },
    ]
    for eqhl_tf in EQHL_SOURCE_TFS:
        for points in POINT_TOLERANCES:
            ticks = points_to_ticks(points)
            cfg = replace(
                base,
                htf_lsi_include_eqhl_levels=True,
                eqhl_level_tf_minutes=eqhl_tf,
                eqhl_n_left=2,
                eqhl_tolerance_ticks=ticks,
                eqhl_min_touches=2,
                eqhl_lookback_bars=48,
                name=f"NQ NY HTF_LSI 5m lag24 + EQHL{eqhl_tf}m {points:g}pt",
            )
            candidates.append(
                {
                    "label": f"htf_plus_eqhl_{eqhl_tf}m_{points:g}pt",
                    "family": "wide_additive",
                    "config": cfg,
                    "eqhl_tf": eqhl_tf,
                    "eqhl_tolerance_ticks": ticks,
                    "eqhl_tolerance_points": float(points),
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
        "family": candidate["family"],
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
        "eqhl_tolerance_points": candidate["eqhl_tolerance_points"],
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
    family_order = {"wide_additive": 0, "incumbent_tight": 1, "htf_only": 2}
    return sorted(
        rows,
        key=lambda row: (
            family_order.get(row["family"], 9),
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


def top_wide(rows: list[dict]) -> dict | None:
    wide_rows = [row for row in rows if row["family"] == "wide_additive"]
    return wide_rows[0] if wide_rows else None


def write_report(rows: list[dict]) -> None:
    lines = [
        "# NQ NY HTF-LSI EQHL Additive Wide Compare",
        "",
        "- Objective: test whether wider EQHL zones help as an additive layer on top of the frozen `5m lag24` lead.",
        "- Scope: holdout stays closed. All non-source parameters are frozen to the current `5m lag24` operating lead (`08:30-13:30`, `rr3.5`, `tp1=0.4`, `gap3.0`, `htf60 n3`, `cap2`, `fvgL20`, `fvgR2`, `lag24`).",
        "- Controls: `HTF-only` and the current additive incumbent `HTF + 15m EQHL tol1`.",
        "- Wide additive shortlist: EQHL source TF `{5m,15m,60m}` x tolerance `{3,5,10,15,20}` points with `touches=2`, `eqhl_n_left=2`, `lookback=48`.",
        "",
        "| Label | Family | Source | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | WF PF | WF Avg R | WF Calmar | WF Trades |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        if row["family"] == "htf_only":
            source = "HTF-only"
        elif row["family"] == "incumbent_tight":
            source = "HTF+EQHL 15m tol1"
        else:
            source = f"HTF+EQHL {row['eqhl_level_tf_minutes']}m {row['eqhl_tolerance_points']:g}pt"
        lines.append(
            f"| {row['config_name']} | {row['family']} | {source} | "
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

    print(f"Loaded {len(candidates)} additive-wide candidates", flush=True)
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
    payload = {
        "rows": rows,
        "top_wide_row": top_wide(rows),
    }
    pd.DataFrame([{k: v for k, v in row.items() if k != "walkforward"} for row in rows]).to_csv(
        OUTPUT_DIR / "ranking.csv", index=False
    )
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2))
    write_report(rows)
    if payload["top_wide_row"] is not None:
        print("Top wide additive row:", flush=True)
        print(json.dumps({k: v for k, v in payload["top_wide_row"].items() if k != "walkforward"}, indent=2), flush=True)
    print(f"Saved additive-wide comparison to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
