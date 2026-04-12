#!/usr/bin/env python3
"""CL NY HTF-LSI local refinement around the promoted htf60 lead.

Primary read:
  - pre-holdout discovery/validation metrics
  - stitched OOS scorecards

Secondary read only:
  - the already-opened 2025-04-01+ holdout

Workflow:
  1. One-at-a-time sweeps around the current promoted lead
  2. Small interaction grid on the strongest remaining primary dimensions
  3. Stitched OOS + secondary holdout read on a frozen finalist set
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

from run_cross_asset_htf_lsi_broad_discovery import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    build_config,
    ensure_required_data,
    load_timeframe_data,
    make_row,
)
from run_gc_ny_htf_lsi_phase_one import (  # noqa: E402
    FUNDED_PROFILE,
    PROP_PROFILE,
    WF_IS_MONTHS,
    WF_OOS_MONTHS,
    WF_STEP_MONTHS,
    metrics_snapshot,
    reconstruct_combined_oos_trades,
    trading_dates_between,
)

OUTPUT_DIR = ROOT / "data" / "results" / "cl_ny_htf_lsi_local_refinement"
OAT_PATH = OUTPUT_DIR / "oat_results.json"
INTERACTION_PATH = OUTPUT_DIR / "interaction_results.json"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"
REPORT_PATH = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_LOCAL_REFINEMENT.md"

BASE = {
    "timeframe": "1m",
    "direction_filter": "long",
    "entry_mode": "close",
    "entry_start": "08:30",
    "entry_end": "14:00",
    "rr": 3.0,
    "tp1_ratio": 0.6,
    "min_gap_atr_pct": 3.0,
    "atr_length": 20,
    "htf_level_tf_minutes": 60,
    "htf_n_left": 3,
    "htf_trade_max_per_session": 2,
    "left_minutes": 100,
    "right_minutes": 10,
    "max_fvg_to_inversion_bars": 15,
}

OAT_SWEEPS = {
    "entry_end": ("13:30", "13:45", "14:00", "14:15", "14:30"),
    "atr_length": (16, 18, 20, 22),
    "htf_n_left": (2, 3, 4, 5),
    "left_minutes": (80, 100, 120),
    "right_minutes": (8, 10, 12),
    "max_fvg_to_inversion_bars": (10, 12, 13, 14, 15, 16, 18, 20),
}

PRIMARY_INTERACTION_DIMS = ("entry_end", "atr_length", "htf_n_left", "max_fvg_to_inversion_bars")
AUXILIARY_DIMS = ("left_minutes", "right_minutes")
DIM_ROW_KEY = {
    "entry_end": "entry_end_variant",
    "atr_length": "atr_variant",
    "htf_n_left": "htf_n_variant",
    "left_minutes": "left_variant",
    "right_minutes": "right_variant",
    "max_fvg_to_inversion_bars": "lag_variant",
}

CURRENT_LEAD_ID = "base_lead"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-workers", type=int, default=None)
    parser.add_argument("--top-overall", type=int, default=8)
    parser.add_argument("--force-rerun-oat", action="store_true")
    parser.add_argument("--force-rerun-interaction", action="store_true")
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def clean_end(end: str) -> str:
    return end.replace(":", "")


def config_summary(row: dict) -> str:
    return (
        f"{row['direction_filter']} {row['entry_mode']} {row['entry_start']}-{row['entry_end']} "
        f"rr{row['rr']} tp{row['tp1_ratio']} gap{row['min_gap_atr_pct']} "
        f"htf{row['htf_level_tf_minutes']} n{row['htf_n_left']} cap{row['htf_trade_max_per_session']} "
        f"fvgL{row['lsi_fvg_window_left']} fvgR{row['lsi_fvg_window_right']} "
        f"lag{row['max_fvg_to_inversion_bars']} atr{row['atr_length']}"
    )


def pre_rank_key(row: dict) -> tuple:
    return (
        1 if row["verdict"] == "alive" else 0,
        row["validation_calmar"],
        row["validation_pf"],
        row["validation_avg_r"],
        row["discovery_pf"],
        row["discovery_avg_r"],
        row["pre_holdout_pf"],
        row["pre_holdout_avg_r"],
        -row["validation_max_dd_r"],
    )


def stitched_rank_key(row: dict) -> tuple:
    return (
        1 if float(row["holdout_funded_scorecard"]["ev_per_start_usd"]) > 0.0 else 0,
        float(row["oos_funded_scorecard"]["ev_per_start_usd"]),
        float(row["oos_funded_scorecard"]["payout_rate"]),
        float(row["oos_metrics"]["calmar_ratio"]),
        float(row["oos_metrics"]["profit_factor"]),
        float(row["oos_metrics"]["avg_r"]),
        float(row["holdout_funded_scorecard"]["ev_per_start_usd"]),
        float(row["holdout_metrics"]["profit_factor"]),
        float(row["holdout_metrics"]["avg_r"]),
    )


def build_candidate_config(candidate_id: str, params: dict, stage: str, varied: dict):
    name = f"CL NY HTF_LSI refine {stage} {candidate_id}"
    cfg = build_config(
        symbol="CL",
        timeframe="1m",
        direction_filter="long",
        entry_mode="close",
        entry_start="08:30",
        entry_end=params["entry_end"],
        rr=3.0,
        tp1_ratio=0.6,
        min_gap_atr_pct=3.0,
        atr_length=params["atr_length"],
        htf_level_tf_minutes=60,
        htf_n_left=params["htf_n_left"],
        htf_trade_max_per_session=2,
        left_minutes=params["left_minutes"],
        right_minutes=params["right_minutes"],
        max_fvg_to_inversion_bars=params["max_fvg_to_inversion_bars"],
        min_stop_points=0.0,
        min_tp1_points=0.0,
        name=name,
    )
    meta = {
        "candidate_id": candidate_id,
        "stage_family": stage,
        "timeframe": "1m",
        "entry_end_variant": params["entry_end"],
        "atr_variant": params["atr_length"],
        "htf_n_variant": params["htf_n_left"],
        "left_variant": params["left_minutes"],
        "right_variant": params["right_minutes"],
        "lag_variant": params["max_fvg_to_inversion_bars"],
        "varied_params": varied,
    }
    return cfg, meta


def build_oat_configs() -> tuple[list, dict[str, dict]]:
    configs = []
    meta_by_name: dict[str, dict] = {}

    base_cfg, base_meta = build_candidate_config(CURRENT_LEAD_ID, dict(BASE), "oat", {})
    configs.append(base_cfg)
    meta_by_name[base_cfg.name] = base_meta

    for dim, values in OAT_SWEEPS.items():
        for value in values:
            if value == BASE[dim]:
                continue
            params = dict(BASE)
            params[dim] = value
            if dim == "entry_end":
                suffix = clean_end(value)
            else:
                suffix = str(value)
            candidate_id = f"oat_{dim}_{suffix}"
            cfg, meta = build_candidate_config(candidate_id, params, "oat", {dim: value})
            configs.append(cfg)
            meta_by_name[cfg.name] = meta
    return configs, meta_by_name


def rows_from_results(results, meta_by_name: dict[str, dict], stage: str) -> list[dict]:
    rows = []
    for config, trades in results:
        meta = meta_by_name[config.name]
        row = make_row(config, trades, stage=stage, extra=meta)
        row["config_summary"] = config_summary(row)
        rows.append(row)
    return sorted(rows, key=pre_rank_key, reverse=True)


def top_values_for_dim(rows: list[dict], dim: str, top_n: int) -> list:
    by_value: dict[str, list[dict]] = {}
    row_key = DIM_ROW_KEY[dim]
    for row in rows:
        if row["candidate_id"] == CURRENT_LEAD_ID:
            continue
        if not row["candidate_id"].startswith(f"oat_{dim}_"):
            continue
        by_value.setdefault(str(row[row_key]), []).append(row)
    ordered_values = sorted(
        by_value.items(),
        key=lambda item: pre_rank_key(sorted(item[1], key=pre_rank_key, reverse=True)[0]),
        reverse=True,
    )
    out = [BASE[dim]]
    for value_str, _ in ordered_values:
        value = BASE[dim]
        if isinstance(BASE[dim], int):
            value = int(value_str)
        else:
            value = value_str
        if value not in out:
            out.append(value)
        if len(out) >= top_n:
            break
    return out


def best_aux_values(rows: list[dict]) -> dict[str, int]:
    best = {}
    for dim in AUXILIARY_DIMS:
        values = top_values_for_dim(rows, dim, top_n=2)
        best[dim] = values[0]
    return best


def build_interaction_configs(oat_rows: list[dict]) -> tuple[list, dict[str, dict], dict[str, list]]:
    best_aux = best_aux_values(oat_rows)
    selected = {
        "entry_end": top_values_for_dim(oat_rows, "entry_end", top_n=2),
        "atr_length": top_values_for_dim(oat_rows, "atr_length", top_n=2),
        "htf_n_left": top_values_for_dim(oat_rows, "htf_n_left", top_n=2),
        "max_fvg_to_inversion_bars": top_values_for_dim(
            oat_rows,
            "max_fvg_to_inversion_bars",
            top_n=3,
        ),
        "left_minutes": [best_aux["left_minutes"]],
        "right_minutes": [best_aux["right_minutes"]],
    }

    configs = []
    meta_by_name: dict[str, dict] = {}
    seen_ids: set[str] = set()

    for entry_end, atr_length, htf_n_left, lag in product(
        selected["entry_end"],
        selected["atr_length"],
        selected["htf_n_left"],
        selected["max_fvg_to_inversion_bars"],
    ):
        params = dict(BASE)
        params.update(
            {
                "entry_end": entry_end,
                "atr_length": atr_length,
                "htf_n_left": htf_n_left,
                "left_minutes": selected["left_minutes"][0],
                "right_minutes": selected["right_minutes"][0],
                "max_fvg_to_inversion_bars": lag,
            }
        )
        candidate_id = (
            f"int_end{clean_end(entry_end)}_atr{atr_length}_n{htf_n_left}_lag{lag}_"
            f"l{params['left_minutes']}_r{params['right_minutes']}"
        )
        if candidate_id in seen_ids:
            continue
        seen_ids.add(candidate_id)
        varied = {
            "entry_end": entry_end,
            "atr_length": atr_length,
            "htf_n_left": htf_n_left,
            "left_minutes": params["left_minutes"],
            "right_minutes": params["right_minutes"],
            "max_fvg_to_inversion_bars": lag,
        }
        cfg, meta = build_candidate_config(candidate_id, params, "interaction", varied)
        configs.append(cfg)
        meta_by_name[cfg.name] = meta
    return configs, meta_by_name, selected


def config_from_row(row: dict):
    return build_config(
        symbol="CL",
        timeframe=row["timeframe"],
        direction_filter=row["direction_filter"],
        entry_mode=row["entry_mode"],
        entry_start=row["entry_start"],
        entry_end=row["entry_end"],
        rr=float(row["rr"]),
        tp1_ratio=float(row["tp1_ratio"]),
        min_gap_atr_pct=float(row["min_gap_atr_pct"]),
        atr_length=int(row["atr_length"]),
        htf_level_tf_minutes=int(row["htf_level_tf_minutes"]),
        htf_n_left=int(row["htf_n_left"]),
        htf_trade_max_per_session=int(row["htf_trade_max_per_session"]),
        lsi_fvg_window_left=int(row["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(row["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(row["max_fvg_to_inversion_bars"]),
        min_stop_points=float(row["min_stop_points"]),
        min_tp1_points=float(row["min_tp1_points"]),
        name=row["label"],
    )


def finalists_from_rows(
    combined_rows: list[dict],
    oat_rows: list[dict],
    interaction_rows: list[dict],
    top_overall: int,
) -> list[dict]:
    ordered_ids: list[str] = []

    def add(candidate_id: str) -> None:
        if candidate_id not in ordered_ids:
            ordered_ids.append(candidate_id)

    add(CURRENT_LEAD_ID)
    for row in combined_rows[:top_overall]:
        add(row["candidate_id"])
    for dim in OAT_SWEEPS:
        dim_rows = [row for row in oat_rows if row["candidate_id"].startswith(f"oat_{dim}_")]
        if dim_rows:
            add(sorted(dim_rows, key=pre_rank_key, reverse=True)[0]["candidate_id"])
    if interaction_rows:
        add(interaction_rows[0]["candidate_id"])
    row_map = {row["candidate_id"]: row for row in combined_rows}
    return [row_map[candidate_id] for candidate_id in ordered_ids if candidate_id in row_map]


def write_report(payload: dict) -> None:
    current = payload["current_lead"]
    recommended = payload["recommended_restart"]
    info = payload["info"]

    lines = [
        "# CL NY HTF-LSI Local Refinement",
        "",
        "- This packet stayed inside the promoted CL HTF-LSI lead family and did not reopen broad discovery.",
        "- Primary ranking is still pre-holdout + stitched OOS. The already-opened `2025-04-01+` holdout is only a secondary read.",
        (
            f"- Base lead entering this packet: `{current['candidate_id']}` "
            f"(`{current['config_summary']}`)."
        ),
        "",
        "## Recommendation",
        "",
        (
            f"- Best restart point after local refinement: `{recommended['candidate_id']}` "
            f"(`{recommended['config_summary']}`)."
        ),
        (
            f"- Stitched OOS funded EV/start moved `{current['oos_funded_scorecard']['ev_per_start_usd']}` "
            f"→ `{recommended['oos_funded_scorecard']['ev_per_start_usd']}`."
        ),
        (
            f"- Secondary holdout funded EV/start moved `{current['holdout_funded_scorecard']['ev_per_start_usd']}` "
            f"→ `{recommended['holdout_funded_scorecard']['ev_per_start_usd']}`."
        ),
        "",
        "## OAT Leaders",
        "",
    ]

    for dim, row in payload["oat_leaders"].items():
        lines.append(
            f"- `{dim}`: `{row['candidate_id']}` | `{row['config_summary']}` | "
            f"validation PF/avgR/calmar `{row['validation_pf']}` / `{row['validation_avg_r']}` / `{row['validation_calmar']}`"
        )

    lines.extend(["", "## Finalists", ""])
    for row in payload["finalists"]:
        lines.extend(
            [
                f"### {row['candidate_id']}",
                "",
                f"- config: `{row['config_summary']}`",
                (
                    f"- pre-holdout: discovery PF/avgR `{row['discovery_pf']}` / `{row['discovery_avg_r']}`, "
                    f"validation PF/avgR/calmar `{row['validation_pf']}` / `{row['validation_avg_r']}` / `{row['validation_calmar']}`"
                ),
                (
                    f"- stitched OOS: trades `{row['oos_metrics']['total_trades']}`, PF `{row['oos_metrics']['profit_factor']}`, "
                    f"avgR `{row['oos_metrics']['avg_r']}`, funded payout `{row['oos_funded_scorecard']['payout_rate']:.1%}`, "
                    f"funded EV/start `${row['oos_funded_scorecard']['ev_per_start_usd']}`"
                ),
                (
                    f"- secondary holdout: trades `{row['holdout_metrics']['total_trades']}`, PF `{row['holdout_metrics']['profit_factor']}`, "
                    f"avgR `{row['holdout_metrics']['avg_r']}`, funded payout `{row['holdout_funded_scorecard']['payout_rate']:.1%}`, "
                    f"funded EV/start `${row['holdout_funded_scorecard']['ev_per_start_usd']}`"
                ),
                "",
            ]
        )

    lines.extend(
        [
            "## Search Space",
            "",
            f"- OAT dimensions: `{', '.join(OAT_SWEEPS.keys())}`",
            f"- Interaction values used: `{info['interaction_values']}`",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    t0 = time.time()
    ensure_required_data("CL")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("CL NY HTF-LSI local refinement", flush=True)
    print("=" * 72, flush=True)
    print("Base lead: htf60 n3 / 14:00 / atr20 / lag15", flush=True)

    print("\nLoading CL 1m HTF-LSI data (1m + 1m + 1s)...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("CL", "1m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    oat_configs, oat_meta = build_oat_configs()
    if OAT_PATH.exists() and not args.force_rerun_oat:
        print("\n[Phase 1] Reusing saved OAT packet", flush=True)
        oat_rows = json.loads(OAT_PATH.read_text())["rows"]
    else:
        print(f"\n[Phase 1] OAT packet ({len(oat_configs)} configs)", flush=True)
        oat_results = run_sweep(
            df_base,
            oat_configs,
            n_workers=args.n_workers,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        oat_rows = rows_from_results(oat_results, oat_meta, "local_refinement_oat")
        write_json(OAT_PATH, {"rows": oat_rows})

    interaction_configs, interaction_meta, interaction_values = build_interaction_configs(oat_rows)
    if INTERACTION_PATH.exists() and not args.force_rerun_interaction:
        print("\n[Phase 2] Reusing saved interaction packet", flush=True)
        interaction_rows = json.loads(INTERACTION_PATH.read_text())["rows"]
    else:
        print(f"\n[Phase 2] Interaction packet ({len(interaction_configs)} configs)", flush=True)
        interaction_results = run_sweep(
            df_base,
            interaction_configs,
            n_workers=args.n_workers,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        interaction_rows = rows_from_results(
            interaction_results,
            interaction_meta,
            "local_refinement_interaction",
        )
        write_json(INTERACTION_PATH, {"rows": interaction_rows})

    combined_rows = sorted(
        {row["candidate_id"]: row for row in (oat_rows + interaction_rows)}.values(),
        key=pre_rank_key,
        reverse=True,
    )
    finalists = finalists_from_rows(combined_rows, oat_rows, interaction_rows, args.top_overall)
    print(f"\n[Phase 3] Downstream reads for {len(finalists)} finalists", flush=True)

    finalist_configs = [config_from_row(row) for row in finalists]
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, finalist_configs, signal_df_1m=signal_df_1m)
    windows = generate_windows(
        DISCOVERY_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start
    oos_dates = trading_dates_between(df_base, oos_start, HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    finalist_payload = []
    for source_row, config in zip(finalists, finalist_configs):
        print(f"  Candidate: {source_row['candidate_id']}", flush=True)
        trades_oos = reconstruct_combined_oos_trades(
            df_base,
            df_1m,
            df_1s,
            signal_df_1m,
            maps,
            signal_cache,
            config,
        )
        oos_metrics = compute_metrics(trades_oos)
        oos_prop_scorecard = build_prop_scorecard(
            simulate_account_attempts(
                specialist_name=config.name,
                trades=trades_oos,
                trading_dates=oos_dates,
                profile=PROP_PROFILE,
                risk_per_r_usd=config.risk_usd,
            ),
            PROP_PROFILE,
        )
        oos_funded_scorecard = build_funded_first_payout_scorecard(
            simulate_funded_first_payouts(
                specialist_name=config.name,
                trades=trades_oos,
                trading_dates=oos_dates,
                profile=FUNDED_PROFILE,
            ),
            FUNDED_PROFILE,
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
        holdout_metrics = compute_metrics(trades_holdout)
        holdout_prop_scorecard = build_prop_scorecard(
            simulate_account_attempts(
                specialist_name=f"{config.name} holdout",
                trades=trades_holdout,
                trading_dates=holdout_dates,
                profile=PROP_PROFILE,
                risk_per_r_usd=config.risk_usd,
            ),
            PROP_PROFILE,
        )
        holdout_funded_scorecard = build_funded_first_payout_scorecard(
            simulate_funded_first_payouts(
                specialist_name=f"{config.name} holdout",
                trades=trades_holdout,
                trading_dates=holdout_dates,
                profile=FUNDED_PROFILE,
            ),
            FUNDED_PROFILE,
        )

        payload_row = dict(source_row)
        payload_row.update(
            {
                "pre_holdout_metrics": {
                    "total_trades": source_row["pre_holdout_trades"],
                    "profit_factor": source_row["pre_holdout_pf"],
                    "avg_r": source_row["pre_holdout_avg_r"],
                    "calmar_ratio": source_row["pre_holdout_calmar"],
                    "total_r": source_row["pre_holdout_total_r"],
                    "max_drawdown_r": source_row["pre_holdout_max_dd_r"],
                },
                "oos_metrics": metrics_snapshot(oos_metrics),
                "oos_prop_scorecard": oos_prop_scorecard,
                "oos_funded_scorecard": oos_funded_scorecard,
                "holdout_metrics": metrics_snapshot(holdout_metrics),
                "holdout_prop_scorecard": holdout_prop_scorecard,
                "holdout_funded_scorecard": holdout_funded_scorecard,
            }
        )
        finalist_payload.append(payload_row)

    finalists_sorted = sorted(finalist_payload, key=stitched_rank_key, reverse=True)
    finalist_map = {row["candidate_id"]: row for row in finalists_sorted}
    current_lead = finalist_map[CURRENT_LEAD_ID]
    recommended = finalists_sorted[0]

    oat_leaders = {}
    for dim in OAT_SWEEPS:
        dim_rows = [row for row in finalists_sorted if row["candidate_id"].startswith(f"oat_{dim}_")]
        if dim_rows:
            oat_leaders[dim] = dim_rows[0]

    payload = {
        "info": {
            "discovery_start": DISCOVERY_START,
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": (
                pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "base": BASE,
            "oat_dims": list(OAT_SWEEPS.keys()),
            "interaction_values": interaction_values,
            "primary_note": "Pre-holdout + stitched OOS are primary; holdout is secondary only.",
            "funded_profile": asdict(FUNDED_PROFILE),
            "prop_profile": asdict(PROP_PROFILE),
        },
        "current_lead": current_lead,
        "recommended_restart": recommended,
        "oat_leaders": oat_leaders,
        "finalists": finalists_sorted,
        "pre_holdout_top10": combined_rows[:10],
    }

    write_json(SUMMARY_PATH, payload)
    write_report(payload)

    print("\nDone.", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"JSON:   {SUMMARY_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
