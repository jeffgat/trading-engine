#!/usr/bin/env python3
"""Pre-holdout NQ NY HTF-LSI discovery sweeps."""

from __future__ import annotations

import dataclasses
import json
import sys
from itertools import product
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.optimize.parallel import run_sweep

from htf_lsi_common import (
    DISCOVERY_START,
    HOLDOUT_START,
    REPORT_PATH,
    RESULTS_ROOT,
    PRE_HOLDOUT_END,
    VALIDATION_START,
    apply_gate,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    make_regime_gate,
    result_row,
    save_json,
    write_markdown_report,
)


def _survivors(rows: list[dict]) -> list[dict]:
    return [
        row for row in rows
        if row["discovery_pf"] >= 1.05
        and row["discovery_avg_r"] > 0.0
        and row["discovery_trades"] >= 150
        and row["validation_pf"] >= 1.00
    ]


def _sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: (
            row["validation_calmar"],
            row["validation_pf"],
            row["discovery_pf"],
            -row["validation_max_dd_r"],
        ),
        reverse=True,
    )


def main() -> int:
    try:
        ensure_required_data()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    gate_fn = make_regime_gate(df_base)
    out_dir = RESULTS_ROOT / "nq_ny_htf_lsi_discovery"
    out_dir.mkdir(parents=True, exist_ok=True)

    stage_a_configs = []
    for htf_tf, direction, entry_mode, entry_end in product(
        (30, 60, 90),
        ("long", "short", "both"),
        ("fvg_limit", "close"),
        ("11:00", "12:00", "13:00", "14:00", "15:00"),
    ):
        cfg = build_config(
            timeframe="5m",
            direction_filter=direction,
            entry_mode=entry_mode,
            entry_start="08:30",
            entry_end=entry_end,
            htf_level_tf_minutes=htf_tf,
            htf_n_left=5,
            htf_trade_max_per_session=1,
            rr=2.0,
            tp1_ratio=0.5,
            min_gap_atr_pct=3.0,
            atr_length=14,
            lsi_fvg_window_left=20,
            lsi_fvg_window_right=5,
        )
        stage_a_configs.append(
            dataclasses.replace(
                cfg,
                name=f"NQ NY HTF_LSI 5m stageA htf{htf_tf} {direction} {entry_mode} 08:30-{entry_end}",
            )
        )

    stage_a_results = run_sweep(
        df_base,
        stage_a_configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    stage_a_rows = [result_row(cfg.name, cfg, trades) for cfg, trades in stage_a_results]
    stage_a_ranked = _sort_rows(stage_a_rows)
    stage_a_keep = _survivors(stage_a_ranked)
    save_json(out_dir / "stage_a_structural.json", stage_a_ranked)

    if not stage_a_keep:
        write_markdown_report(REPORT_PATH, "NQ NY HTF-LSI Discovery", [("Stage A", stage_a_ranked[:10])])
        print("No structural survivors cleared the discovery thresholds.", file=sys.stderr)
        return 1

    top_families = stage_a_keep[:2]
    trade_cap_configs = []
    for family, cap in product(top_families, (1, 2, 3)):
        trade_cap_configs.append(
            build_config(
                direction_filter=family["direction_filter"],
                entry_mode=family["entry_mode"],
                entry_start=family["entry_start"],
                entry_end=family["entry_end"],
                rr=family["rr"],
                tp1_ratio=family["tp1_ratio"],
                min_gap_atr_pct=family["min_gap_atr_pct"],
                atr_length=family["atr_length"],
                htf_level_tf_minutes=family["htf_level_tf_minutes"],
                htf_n_left=family["htf_n_left"],
                htf_trade_max_per_session=cap,
                lsi_fvg_window_left=family["lsi_fvg_window_left"],
                lsi_fvg_window_right=family["lsi_fvg_window_right"],
                name=f"NQ NY HTF_LSI 5m cap {cap} {family['label']}",
            )
        )

    trade_cap_results = run_sweep(
        df_base,
        trade_cap_configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    trade_cap_rows = _sort_rows([result_row(cfg.name, cfg, trades) for cfg, trades in trade_cap_results])
    save_json(out_dir / "stage_b_trade_cap.json", trade_cap_rows)
    best_base = trade_cap_rows[0]

    param_configs = []
    for min_gap, left, right, rr, tp1, htf_n_left in product(
        (2.0, 3.0, 4.0, 5.0),
        (10, 15, 20, 25),
        (2, 3, 5, 8),
        (2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5),
        (0.4, 0.5, 0.6),
        (3, 5, 7),
    ):
        if rr * tp1 < 1.0:
            continue
        param_configs.append(
            build_config(
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=rr,
                tp1_ratio=tp1,
                min_gap_atr_pct=min_gap,
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=htf_n_left,
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=left,
                lsi_fvg_window_right=right,
                name=(
                    "NQ NY HTF_LSI 5m param "
                    f"gap{min_gap} left{left} right{right} rr{rr} tp{tp1} n{htf_n_left}"
                ),
            )
        )

    param_results = run_sweep(
        df_base,
        param_configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    param_rows = _sort_rows([result_row(cfg.name, cfg, trades) for cfg, trades in param_results])[:25]
    save_json(out_dir / "stage_c_params.json", param_rows)

    lag_configs = []
    for base_row, lag in product(param_rows[:5], (0, 1, 2, 3, 5, 8)):
        lag_configs.append(
            build_config(
                direction_filter=base_row["direction_filter"],
                entry_mode=base_row["entry_mode"],
                entry_start=base_row["entry_start"],
                entry_end=base_row["entry_end"],
                rr=base_row["rr"],
                tp1_ratio=base_row["tp1_ratio"],
                min_gap_atr_pct=base_row["min_gap_atr_pct"],
                atr_length=base_row["atr_length"],
                htf_level_tf_minutes=base_row["htf_level_tf_minutes"],
                htf_n_left=base_row["htf_n_left"],
                htf_trade_max_per_session=base_row["htf_trade_max_per_session"],
                lsi_fvg_window_left=base_row["lsi_fvg_window_left"],
                lsi_fvg_window_right=base_row["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=lag,
                name=f"NQ NY HTF_LSI 5m lag {lag} {base_row['label']}",
            )
        )

    lag_results = run_sweep(
        df_base,
        lag_configs,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    lag_rows = _sort_rows([result_row(cfg.name, cfg, trades) for cfg, trades in lag_results])
    save_json(out_dir / "stage_d_inversion_lag.json", lag_rows)

    gate_rows = []
    for cfg, trades in lag_results[:5]:
        gate_rows.append(result_row(cfg.name, cfg, trades, gate_label="ungated"))
        gate_rows.append(result_row(cfg.name, cfg, apply_gate(trades, gate_fn), gate_label="skip_medium_vol"))
    gate_rows = _sort_rows(gate_rows)
    save_json(out_dir / "stage_e_regime_gate.json", gate_rows)

    write_markdown_report(
        REPORT_PATH,
        "NQ NY HTF-LSI Discovery",
        [
            ("Stage A Structural", stage_a_ranked[:10]),
            ("Stage B Trade Cap", trade_cap_rows[:10]),
            ("Stage C Parameters", param_rows[:10]),
            ("Stage D Inversion Lag", lag_rows[:10]),
            ("Stage E Regime Gate", gate_rows[:10]),
        ],
    )

    shortlist = [row for row in gate_rows if row["gate"] == "skip_medium_vol"][:5]
    save_json(out_dir / "shortlist.json", shortlist)
    print(json.dumps(shortlist[:3], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
