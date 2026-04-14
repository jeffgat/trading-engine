#!/usr/bin/env python3
"""Local promotion sweep around the surviving NQ NY EQHL-LSI branches.

This packet treats the broad EQHL discovery as complete and performs a narrow
pre-holdout promotion sweep around the two live branches:

1. 5m entry -> 5m EQHL source
2. 2m entry -> 15m EQHL source

Only the local knobs move:
- rr
- tp1_ratio
- lsi_fvg_window_left
- lsi_fvg_window_right

Everything else stays fixed to the branch winner.
"""

from __future__ import annotations

from dataclasses import replace
import json
import sys
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from orb_backtest.engine import simulator
from orb_backtest.engine.simulator import build_maps, build_signal_cache
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.optimize.walkforward import generate_windows
from orb_backtest.results.metrics import compute_metrics
from run_cross_asset_eqhl_lsi_broad_discovery import (
    RESEARCH_START,
    VALIDATION_START,
    HOLDOUT_START,
    build_config,
    ensure_required_data,
    load_timeframe_data,
)


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_eqhl_lsi_promotion_packet"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_EQHL_LSI_PROMOTION_PACKET.md"

BRANCH_SPECS = (
    {
        "slug": "5m_eqhl5m",
        "timeframe": "5m",
        "eqhl_level_tf_minutes": 5,
        "eqhl_tolerance_ticks": 2,
        "eqhl_min_touches": 2,
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "entry_end": "13:00",
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "eqhl_n_left": 2,
        "eqhl_lookback_bars": 48,
        "left_values": (16, 20, 24),
        "right_values": (1, 2, 3),
        "rr_values": (2.5, 2.75, 3.0, 3.25, 3.5),
        "tp1_values": (0.4, 0.5, 0.6),
        "min_discovery_trades": 180,
        "min_validation_trades": 50,
    },
    {
        "slug": "2m_eqhl15m",
        "timeframe": "2m",
        "eqhl_level_tf_minutes": 15,
        "eqhl_tolerance_ticks": 2,
        "eqhl_min_touches": 2,
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "entry_end": "15:00",
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "eqhl_n_left": 2,
        "eqhl_lookback_bars": 48,
        "left_values": (40, 50, 60),
        "right_values": (3, 5, 8),
        "rr_values": (2.5, 2.75, 3.0, 3.25, 3.5),
        "tp1_values": (0.4, 0.5, 0.6),
        "min_discovery_trades": 150,
        "min_validation_trades": 40,
    },
)


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def summarize_periods(trades) -> dict[str, dict]:
    return {
        "pre_holdout": compute_metrics(slice_trades(trades, RESEARCH_START, HOLDOUT_START)),
        "discovery": compute_metrics(slice_trades(trades, RESEARCH_START, VALIDATION_START)),
        "validation": compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START)),
    }


def make_row(config, trades, *, branch: dict) -> dict:
    summary = summarize_periods(trades)
    session = config.sessions[0]
    return {
        "label": config.name,
        "branch": branch["slug"],
        "timeframe": branch["timeframe"],
        "entry_end": session.entry_end,
        "rr": float(config.rr),
        "tp1_ratio": float(config.tp1_ratio),
        "eqhl_level_tf_minutes": int(config.eqhl_level_tf_minutes),
        "eqhl_tolerance_ticks": int(config.eqhl_tolerance_ticks),
        "eqhl_min_touches": int(config.eqhl_min_touches),
        "lsi_fvg_window_left": int(config.lsi_fvg_window_left),
        "lsi_fvg_window_right": int(config.lsi_fvg_window_right),
        "pre_holdout_trades": int(summary["pre_holdout"]["total_trades"]),
        "pre_holdout_pf": float(summary["pre_holdout"]["profit_factor"]),
        "pre_holdout_avg_r": float(summary["pre_holdout"]["avg_r"]),
        "pre_holdout_total_r": float(summary["pre_holdout"]["total_r"]),
        "pre_holdout_calmar": float(summary["pre_holdout"]["calmar_ratio"]),
        "pre_holdout_max_dd_r": float(summary["pre_holdout"]["max_drawdown_r"]),
        "discovery_trades": int(summary["discovery"]["total_trades"]),
        "discovery_pf": float(summary["discovery"]["profit_factor"]),
        "discovery_avg_r": float(summary["discovery"]["avg_r"]),
        "discovery_total_r": float(summary["discovery"]["total_r"]),
        "discovery_calmar": float(summary["discovery"]["calmar_ratio"]),
        "validation_trades": int(summary["validation"]["total_trades"]),
        "validation_pf": float(summary["validation"]["profit_factor"]),
        "validation_avg_r": float(summary["validation"]["avg_r"]),
        "validation_total_r": float(summary["validation"]["total_r"]),
        "validation_calmar": float(summary["validation"]["calmar_ratio"]),
        "validation_max_dd_r": float(summary["validation"]["max_drawdown_r"]),
    }


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["validation_calmar"],
            row["validation_pf"],
            row["validation_avg_r"],
            row["discovery_pf"],
            row["discovery_avg_r"],
            -row["validation_max_dd_r"],
            row["validation_trades"],
        ),
        reverse=True,
    )


def _survivors(rows: list[dict], *, min_discovery_trades: int, min_validation_trades: int) -> list[dict]:
    return [
        row
        for row in rows
        if row["discovery_pf"] >= 1.05
        and row["discovery_avg_r"] > 0.0
        and row["discovery_trades"] >= min_discovery_trades
        and row["validation_pf"] >= 1.0
        and row["validation_avg_r"] > 0.0
        and row["validation_trades"] >= min_validation_trades
    ]


def _stitched_oos(config, df_base, df_1m, df_1s, signal_df_1m, maps, signal_cache) -> dict:
    windows = generate_windows(RESEARCH_START, HOLDOUT_START, is_months=36, oos_months=12, step_months=12)
    combined = []
    folds = []
    for window in windows:
        trades = simulator.run_backtest(
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


def _build_configs(branch: dict) -> list:
    configs = []
    for left, right, rr, tp1 in product(
        branch["left_values"],
        branch["right_values"],
        branch["rr_values"],
        branch["tp1_values"],
    ):
        if rr * tp1 < 1.0:
            continue
        configs.append(
            build_config(
                symbol="NQ",
                timeframe=branch["timeframe"],
                eqhl_tf_minutes=branch["eqhl_level_tf_minutes"],
                eqhl_tolerance_ticks=branch["eqhl_tolerance_ticks"],
                eqhl_min_touches=branch["eqhl_min_touches"],
                direction_filter=branch["direction_filter"],
                entry_mode=branch["entry_mode"],
                entry_end=branch["entry_end"],
                rr=rr,
                tp1_ratio=tp1,
                min_gap_atr_pct=branch["min_gap_atr_pct"],
                atr_length=branch["atr_length"],
                eqhl_n_left=branch["eqhl_n_left"],
                eqhl_lookback_bars=branch["eqhl_lookback_bars"],
                left_minutes=left * (5 if branch["timeframe"] == "5m" else 2),
                right_minutes=right * (5 if branch["timeframe"] == "5m" else 2),
                min_stop_points=0.0,
                min_tp1_points=0.0,
            )
        )
        configs[-1] = replace(
            configs[-1],
            name=(
                f"NQ NY EQHL_LSI promote {branch['slug']} "
                f"left{left} right{right} rr{rr} tp{tp1}"
            ),
        )
    return configs


def _write_report(payload: dict) -> None:
    lines = [
        "# NQ NY EQHL-LSI Promotion Packet",
        "",
        "- Objective: local promotion sweep around the two surviving EQHL-LSI families.",
        "- Scope: only `rr`, `tp1_ratio`, `lsi_fvg_window_left`, and `lsi_fvg_window_right` move. All EQHL source settings stay frozen to the broad-discovery winners.",
        f"- Pre-holdout window: `{RESEARCH_START}` to `{HOLDOUT_START}`. Opened holdout remains closed.",
        "",
    ]
    for branch in payload["branches"]:
        lines.extend(
            [
                f"## {branch['slug']}",
                "",
                f"- Base entry TF: `{branch['timeframe']}`",
                f"- EQHL source TF: `{branch['eqhl_level_tf_minutes']}m`",
                f"- Frozen sweep semantics: `tol={branch['eqhl_tolerance_ticks']} ticks`, `touches={branch['eqhl_min_touches']}`, `{branch['direction_filter']}`, `{branch['entry_mode']}`, `entry_end={branch['entry_end']}`",
                f"- Configs tested: `{branch['total_configs']}`",
                f"- Survivors: `{branch['survivor_count']}`",
                "",
                "| Label | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades |",
                "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in branch["top_rows"]:
            lines.append(
                f"| {row['label']} | {row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
                f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
                f"{row['validation_calmar']:.3f} | {row['validation_trades']} |"
            )
        lines.extend(
            [
                "",
                "| WF Label | WF PF | WF Avg R | WF Calmar | WF Trades | WF DD |",
                "| --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in branch["walkforward"]:
            wf = row["walkforward"]["combined"]
            lines.append(
                f"| {row['label']} | {wf['pf']:.3f} | {wf['avg_r']:.3f} | "
                f"{wf['calmar']:.3f} | {wf['trades']} | {wf['max_dd_r']:.2f} |"
            )
        lines.append("")
    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    ensure_required_data("NQ")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    payload = {"branches": []}
    for branch in BRANCH_SPECS:
        print(f"[{branch['slug']}] loading {branch['timeframe']} data...", flush=True)
        df_base, df_1m, df_1s = load_timeframe_data("NQ", branch["timeframe"])
        signal_df_1m = df_1m
        configs = _build_configs(branch)
        print(f"[{branch['slug']}] running {len(configs)} configs...", flush=True)
        results = run_sweep(
            df_base,
            configs,
            start_date=RESEARCH_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        rows = _sort_rows([make_row(cfg, trades, branch=branch) for cfg, trades in results])
        survivors = _survivors(
            rows,
            min_discovery_trades=branch["min_discovery_trades"],
            min_validation_trades=branch["min_validation_trades"],
        )
        top_rows = survivors[:5] if survivors else rows[:5]

        print(f"[{branch['slug']}] building maps/cache for stitched OOS follow-up...", flush=True)
        maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
        signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)
        cfg_by_label = {cfg.name: cfg for cfg in configs}
        wf_rows = []
        for row in top_rows:
            cfg = cfg_by_label[row["label"]]
            wf_rows.append(
                row
                | {
                    "walkforward": _stitched_oos(
                        cfg,
                        df_base,
                        df_1m,
                        df_1s,
                        signal_df_1m,
                        maps,
                        signal_cache,
                    )
                }
            )
        wf_rows = sorted(
            wf_rows,
            key=lambda row: (
                row["walkforward"]["combined"]["calmar"],
                row["walkforward"]["combined"]["pf"],
                row["validation_calmar"],
            ),
            reverse=True,
        )

        branch_payload = {
            **branch,
            "total_configs": len(configs),
            "survivor_count": len(survivors),
            "top_rows": top_rows,
            "walkforward": wf_rows,
        }
        payload["branches"].append(branch_payload)

        pd.DataFrame(rows).to_csv(OUTPUT_DIR / f"{branch['slug']}_all_rows.csv", index=False)
        with open(OUTPUT_DIR / f"{branch['slug']}_summary.json", "w") as f:
            json.dump(branch_payload, f, indent=2)

    _write_report(payload)
    with open(OUTPUT_DIR / "summary.json", "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved packet to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
