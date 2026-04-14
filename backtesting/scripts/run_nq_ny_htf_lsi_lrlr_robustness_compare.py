#!/usr/bin/env python3
"""Robustness and holdout compare for LRLR finalists on the NQ NY 2m HTF-LSI anchor."""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    RESULTS_ROOT,
    VALIDATION_START,
    build_config,
    load_timeframe_data,
    save_json,
    slice_trades,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from run_nq_ny_htf_lsi_phase_one import reconstruct_combined_oos_trades  # noqa: E402


OUTPUT_DIR = RESULTS_ROOT / "nq_ny_htf_lsi_lrlr_robustness_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_LRLR_ROBUSTNESS_COMPARE.md"

BASE_PARAMS = {
    "timeframe": "2m",
    "direction_filter": "long",
    "entry_mode": "fvg_limit",
    "htf_trade_max_per_session": 1,
    "rr": 3.0,
    "tp1_ratio": 0.6,
    "min_gap_atr_pct": 3.0,
    "atr_length": 14,
    "htf_level_tf_minutes": 60,
    "htf_n_left": 3,
    "lsi_fvg_window_left": 50,
    "lsi_fvg_window_right": 5,
    "max_fvg_to_inversion_bars": 0,
}

LRLR_COMMON = {
    "lsi_lrlr_enabled": True,
    "lsi_lrlr_gate": "require",
    "lsi_lrlr_swing_n_left": 2,
    "lsi_lrlr_swing_n_right": 2,
    "lsi_lrlr_min_pivots": 2,
    "lsi_lrlr_lookback_minutes": 120,
    "lsi_lrlr_max_pivot_gap_minutes": 30,
    "lsi_lrlr_max_cluster_span_minutes": 120,
    "lsi_lrlr_max_price_span_atr": 0.18,
    "lsi_lrlr_monotonic_tolerance_atr": 0.03,
    "lsi_lrlr_line_tolerance_atr": 0.04,
}


def _snapshot(metrics: dict) -> dict:
    keep = (
        "total_signals",
        "total_trades",
        "no_fills",
        "win_rate",
        "profit_factor",
        "avg_r",
        "total_r",
        "calmar_ratio",
        "max_drawdown_r",
        "sharpe_ratio",
    )
    out = {}
    for key in keep:
        value = metrics.get(key, 0.0)
        out[key] = round(float(value), 4) if isinstance(value, (int, float)) else value
    return out


def _period_metrics(trades) -> dict[str, dict]:
    return {
        "pre_holdout": _snapshot(compute_metrics(slice_trades(trades, DISCOVERY_START, HOLDOUT_START))),
        "discovery": _snapshot(compute_metrics(slice_trades(trades, DISCOVERY_START, VALIDATION_START))),
        "validation": _snapshot(compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START))),
    }


def _window_metrics(trades, start: str, end_exclusive: str) -> dict:
    return _snapshot(compute_metrics(slice_trades(trades, start, end_exclusive)))


def _build_candidates():
    baseline = build_config(name="NQ NY HTF_LSI 2m baseline", **BASE_PARAMS)
    lite = dataclasses.replace(
        baseline,
        name="NQ NY HTF_LSI 2m LRLR-lite 30m require",
        **LRLR_COMMON,
    )
    tp1 = dataclasses.replace(
        baseline,
        name="NQ NY HTF_LSI 2m LRLR-lite 30m TP1 0.2 require",
        lsi_lrlr_tp1_path_enabled=True,
        lsi_lrlr_tp1_buffer_atr=0.2,
        **LRLR_COMMON,
    )
    return [
        {
            "label": "baseline",
            "thesis": "ungated anchor",
            "config": baseline,
        },
        {
            "label": "lrlr_lite_30m",
            "thesis": "2 pivots + 30m spacing",
            "config": lite,
        },
        {
            "label": "lrlr_tp1_30m_buffer_0.2",
            "thesis": "2 pivots + 30m spacing + nearest LRLR level within 0.2 ATR beyond TP1",
            "config": tp1,
        },
    ]


def _write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI LRLR Robustness Compare",
        "",
        "- Scope: frozen `2m` NQ NY HTF-LSI anchor versus the two LRLR follow-up finalists.",
        "- Selection discipline: LRLR variants were frozen from pre-holdout work before this one-time holdout compare.",
        f"- Stitched OOS stream uses `36m IS / 12m OOS / 12m step` from `{DISCOVERY_START}` to `{HOLDOUT_START}`.",
        f"- Holdout window: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "",
        "## Summary",
        "",
        "| Candidate | Validation PF | Validation Avg R | Validation Calmar | OOS PF | OOS Avg R | OOS Calmar | OOS Trades | Holdout PF | Holdout Avg R | Holdout Calmar | Holdout Trades |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for row in payload["results"]:
        val = row["pre_holdout"]["validation"]
        oos = row["stitched_oos"]
        holdout = row["holdout"]
        lines.append(
            f"| `{row['label']}` | {val['profit_factor']:.3f} | {val['avg_r']:.3f} | {val['calmar_ratio']:.3f} | "
            f"{oos['profit_factor']:.3f} | {oos['avg_r']:.3f} | {oos['calmar_ratio']:.3f} | {int(oos['total_trades'])} | "
            f"{holdout['profit_factor']:.3f} | {holdout['avg_r']:.3f} | {holdout['calmar_ratio']:.3f} | {int(holdout['total_trades'])} |"
        )

    lines.extend(["", "## Details", ""])
    for row in payload["results"]:
        lines.extend(
            [
                f"### {row['label']}",
                "",
                f"- thesis: `{row['thesis']}`",
                f"- config: `{row['config_summary']}`",
                f"- pre-holdout validation: `{row['pre_holdout']['validation']}`",
                f"- stitched OOS: `{row['stitched_oos']}`",
                f"- holdout: `{row['holdout']}`",
                f"- holdout `2025-04-01` to `2025-12-31`: `{row['holdout_2025']}`",
                f"- holdout `2026-01-01` to `{payload['info']['holdout_end_inclusive']}`: `{row['holdout_2026_ytd']}`",
                "",
            ]
        )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("2m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    candidates = _build_candidates()
    configs = [row["config"] for row in candidates]
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)

    rows = []
    for row in candidates:
        config = row["config"]
        trades_full = run_backtest(
            df_base,
            config,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        trades_oos = reconstruct_combined_oos_trades(
            df_base,
            df_1m,
            df_1s,
            signal_df_1m,
            maps,
            signal_cache,
            config,
        )
        trades_holdout = run_backtest(
            df_base,
            config,
            start_date=HOLDOUT_START,
            end_date=holdout_end_exclusive,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )

        session = config.sessions[0]
        rows.append(
            {
                "label": row["label"],
                "thesis": row["thesis"],
                "config_summary": (
                    f"{config.direction_filter} {config.lsi_entry_mode} {session.entry_start}-{session.entry_end} "
                    f"cap{config.htf_trade_max_per_session} rr{config.rr} tp1{config.tp1_ratio} "
                    f"left{config.lsi_fvg_window_left} right{config.lsi_fvg_window_right} lag{config.max_fvg_to_inversion_bars}"
                ),
                "pre_holdout": _period_metrics(trades_full),
                "stitched_oos": _snapshot(compute_metrics(trades_oos)),
                "holdout": _snapshot(compute_metrics(trades_holdout)),
                "holdout_2025": _window_metrics(trades_holdout, HOLDOUT_START, "2026-01-01"),
                "holdout_2026_ytd": _window_metrics(trades_holdout, "2026-01-01", holdout_end_exclusive),
            }
        )

    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "holdout_end_exclusive": holdout_end_exclusive,
        },
        "results": rows,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "summary.json", payload)
    _write_report(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
