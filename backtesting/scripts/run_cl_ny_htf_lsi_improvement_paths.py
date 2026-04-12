#!/usr/bin/env python3
"""CL NY HTF-LSI narrow improvement-path packet around the current lead.

This is intentionally not a fresh discovery reopen. It keeps the thesis fixed to
the alive CL family:
  - 1m
  - long
  - close
  - cap=2
  - rr=3.0
  - tp1=0.6
  - gap=3.0
  - fvg=100/10

Then it walks every narrow improvement path that still looks justified:
  1. Structure: htf60 n3 vs htf60 n5 vs htf30 n7
  2. Entry cutoff: 13:30 vs 14:00 vs 14:30
  3. ATR length: 14 vs 20
  4. Inversion lag: 0, 5, 8, 10, 12, 15

Holdout was already opened previously on 2025-04-01, so this packet uses
pre-holdout + stitched OOS as the primary ranking surface and reports holdout
only as a secondary read on the finalists.
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

OUTPUT_DIR = ROOT / "data" / "results" / "cl_ny_htf_lsi_improvement_paths"
REPORT_PATH = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_IMPROVEMENT_PATHS.md"
GRID_RESULTS_PATH = OUTPUT_DIR / "grid_results.json"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"

CURRENT_LEAD_ID = "lead_htf60_n3_end1400_atr14_lag0"

STRUCTURES = (
    ("lead_htf60_n3", 60, 3),
    ("alt_htf60_n5", 60, 5),
    ("challenger_htf30_n7", 30, 7),
)
ENTRY_ENDS = ("13:30", "14:00", "14:30")
ATR_LENGTHS = (14, 20)
LAGS = (0, 5, 8, 10, 12, 15)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n-workers", type=int, default=None)
    parser.add_argument("--top-overall", type=int, default=8)
    parser.add_argument("--force-rerun-grid", action="store_true")
    return parser.parse_args()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def clean_end(end: str) -> str:
    return end.replace(":", "")


def build_candidate_configs() -> tuple[list, dict[str, dict]]:
    configs = []
    meta_by_name: dict[str, dict] = {}
    for (structure_id, htf_tf, htf_n_left), entry_end, atr_length, lag in product(
        STRUCTURES,
        ENTRY_ENDS,
        ATR_LENGTHS,
        LAGS,
    ):
        candidate_id = (
            f"{structure_id}_end{clean_end(entry_end)}_atr{atr_length}_lag{lag}"
        )
        name = (
            f"CL NY HTF_LSI improve {structure_id} "
            f"end{clean_end(entry_end)} atr{atr_length} lag{lag}"
        )
        cfg = build_config(
            symbol="CL",
            timeframe="1m",
            direction_filter="long",
            entry_mode="close",
            entry_start="08:30",
            entry_end=entry_end,
            rr=3.0,
            tp1_ratio=0.6,
            min_gap_atr_pct=3.0,
            atr_length=atr_length,
            htf_level_tf_minutes=htf_tf,
            htf_n_left=htf_n_left,
            htf_trade_max_per_session=2,
            lsi_fvg_window_left=100,
            lsi_fvg_window_right=10,
            max_fvg_to_inversion_bars=lag,
            min_stop_points=0.0,
            min_tp1_points=0.0,
            name=name,
        )
        configs.append(cfg)
        meta_by_name[name] = {
            "candidate_id": candidate_id,
            "structure_id": structure_id,
            "entry_end_variant": entry_end,
            "atr_variant": atr_length,
            "lag_variant": lag,
            "timeframe": "1m",
            "path_family": "cl_htf_lsi_improvement",
        }
    return configs, meta_by_name


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
    oos_funded = row["oos_funded_scorecard"]
    holdout_funded = row["holdout_funded_scorecard"]
    oos = row["oos_metrics"]
    holdout = row["holdout_metrics"]
    return (
        1 if float(holdout_funded["ev_per_start_usd"]) > 0.0 else 0,
        float(oos_funded["ev_per_start_usd"]),
        float(oos_funded["payout_rate"]),
        float(oos["calmar_ratio"]),
        float(oos["profit_factor"]),
        float(oos["avg_r"]),
        float(holdout_funded["ev_per_start_usd"]),
        float(holdout["profit_factor"]),
        float(holdout["avg_r"]),
    )


def best_by_group(rows: list[dict], key_name: str) -> dict[str, dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row[key_name]), []).append(row)
    return {
        group: sorted(group_rows, key=pre_rank_key, reverse=True)[0]
        for group, group_rows in grouped.items()
    }


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


def finalist_candidate_ids(
    rows_sorted: list[dict],
    *,
    top_overall: int,
    leaders_by_structure: dict[str, dict],
    leaders_by_end: dict[str, dict],
    leaders_by_atr: dict[str, dict],
    leaders_by_lag: dict[str, dict],
) -> list[str]:
    ordered: list[str] = []

    def add(candidate_id: str) -> None:
        if candidate_id not in ordered:
            ordered.append(candidate_id)

    add(CURRENT_LEAD_ID)
    for row in rows_sorted[:top_overall]:
        add(row["candidate_id"])
    for mapping in (leaders_by_structure, leaders_by_end, leaders_by_atr, leaders_by_lag):
        for row in mapping.values():
            add(row["candidate_id"])
    return ordered


def write_report(payload: dict) -> None:
    info = payload["info"]
    current = payload["current_lead"]
    recommended = payload["recommended_restart"]

    lines = [
        "# CL NY HTF-LSI Improvement Paths",
        "",
        "- This packet stayed inside the existing CL HTF-LSI family instead of reopening broad discovery.",
        (
            f"- Holdout had already been opened previously on `{HOLDOUT_START}` and remains a "
            "secondary read only in this report."
        ),
        (
            "- Fixed family: `1m`, `long`, `close`, `cap=2`, `rr=3.0`, `tp1=0.6`, "
            "`gap=3.0`, `fvg=100/10`."
        ),
        (
            f"- Improvement paths tested: structure `{', '.join(info['structures'])}`, "
            f"entry end `{', '.join(info['entry_ends'])}`, ATR `{', '.join(str(x) for x in info['atr_lengths'])}`, "
            f"lag `{', '.join(str(x) for x in info['lags'])}`."
        ),
        (
            f"- Current phase-one lead entering this packet: `{current['candidate_id']}` "
            f"(`{current['config_summary']}`)."
        ),
        "",
        "## Recommendation",
        "",
        (
            f"- Best restart point after the micro-packet: `{recommended['candidate_id']}` "
            f"(`{recommended['config_summary']}`)."
        ),
        (
            f"- Stitched OOS: `{recommended['oos_metrics']['total_trades']}` trades, PF "
            f"`{recommended['oos_metrics']['profit_factor']}`, avgR `{recommended['oos_metrics']['avg_r']}`, "
            f"funded payout `{recommended['oos_funded_scorecard']['payout_rate']:.1%}`, "
            f"funded EV/start `${recommended['oos_funded_scorecard']['ev_per_start_usd']}`."
        ),
        (
            f"- Secondary holdout read (`{HOLDOUT_START}` to `{info['holdout_end_inclusive']}`): "
            f"`{recommended['holdout_metrics']['total_trades']}` trades, PF "
            f"`{recommended['holdout_metrics']['profit_factor']}`, avgR `{recommended['holdout_metrics']['avg_r']}`, "
            f"funded payout `{recommended['holdout_funded_scorecard']['payout_rate']:.1%}`, "
            f"funded EV/start `${recommended['holdout_funded_scorecard']['ev_per_start_usd']}`."
        ),
        (
            f"- Compared with the old lead, the stitched funded EV/start moved "
            f"`{current['oos_funded_scorecard']['ev_per_start_usd']}` → "
            f"`{recommended['oos_funded_scorecard']['ev_per_start_usd']}` and the secondary holdout funded "
            f"EV/start moved `{current['holdout_funded_scorecard']['ev_per_start_usd']}` → "
            f"`{recommended['holdout_funded_scorecard']['ev_per_start_usd']}`."
        ),
        "",
        "## Path Leaders",
        "",
    ]

    for label, mapping in (
        ("Structure", payload["path_leaders"]["structure"]),
        ("Entry End", payload["path_leaders"]["entry_end"]),
        ("ATR", payload["path_leaders"]["atr"]),
        ("Lag", payload["path_leaders"]["lag"]),
    ):
        lines.append(f"### {label}")
        lines.append("")
        for key, row in mapping.items():
            holdout = row.get("holdout_metrics")
            holdout_funded = row.get("holdout_funded_scorecard")
            extra = ""
            if holdout and holdout_funded:
                extra = (
                    f"; secondary holdout PF `{holdout['profit_factor']}`, avgR `{holdout['avg_r']}`, "
                    f"funded EV/start `${holdout_funded['ev_per_start_usd']}`"
                )
            lines.append(
                (
                    f"- `{key}`: `{row['candidate_id']}` | pre rank PF/avgR/calmar "
                    f"`{row['validation_pf']}` / `{row['validation_avg_r']}` / `{row['validation_calmar']}`"
                    f"{extra}"
                )
            )
        lines.append("")

    lines.extend(["## Finalists", ""])
    for row in payload["finalists"]:
        lines.extend(
            [
                f"### {row['candidate_id']}",
                "",
                f"- config: `{row['config_summary']}`",
                (
                    f"- pre-holdout: trades `{row['pre_holdout_trades']}`, discovery PF/avgR "
                    f"`{row['discovery_pf']}` / `{row['discovery_avg_r']}`, validation PF/avgR/calmar "
                    f"`{row['validation_pf']}` / `{row['validation_avg_r']}` / `{row['validation_calmar']}`"
                ),
                (
                    f"- stitched OOS: trades `{row['oos_metrics']['total_trades']}`, PF "
                    f"`{row['oos_metrics']['profit_factor']}`, avgR `{row['oos_metrics']['avg_r']}`, "
                    f"calmar `{row['oos_metrics']['calmar_ratio']}`, funded payout "
                    f"`{row['oos_funded_scorecard']['payout_rate']:.1%}`, funded EV/start "
                    f"`$ {row['oos_funded_scorecard']['ev_per_start_usd']}`".replace("$ ", "$")
                ),
                (
                    f"- secondary holdout: trades `{row['holdout_metrics']['total_trades']}`, PF "
                    f"`{row['holdout_metrics']['profit_factor']}`, avgR `{row['holdout_metrics']['avg_r']}`, "
                    f"funded payout `{row['holdout_funded_scorecard']['payout_rate']:.1%}`, funded EV/start "
                    f"`$ {row['holdout_funded_scorecard']['ev_per_start_usd']}`".replace("$ ", "$")
                ),
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    args = parse_args()
    t0 = time.time()
    ensure_required_data("CL")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("CL NY HTF-LSI improvement paths", flush=True)
    print("=" * 72, flush=True)
    print("Packet: structure x cutoff x ATR x lag around current lead", flush=True)

    configs, meta_by_name = build_candidate_configs()
    print(f"Configs: {len(configs)}", flush=True)

    print("\nLoading CL 1m HTF-LSI data (1m + 1m + 1s)...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("CL", "1m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    print(f"  1m bars: {len(df_base):,}", flush=True)
    print(f"  signal 1m bars: {len(signal_df_1m):,}", flush=True)
    print(f"  1s bars: {len(df_1s):,}", flush=True)
    print(f"  Holdout end: {holdout_end_inclusive}", flush=True)

    if GRID_RESULTS_PATH.exists() and not args.force_rerun_grid:
        print("\n[Phase 1] Reusing saved pre-holdout packet", flush=True)
        rows_sorted = json.loads(GRID_RESULTS_PATH.read_text())["rows"]
    else:
        print("\n[Phase 1] Pre-holdout packet", flush=True)
        results = run_sweep(
            df_base,
            configs,
            n_workers=args.n_workers,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )

        rows = []
        for config, trades in results:
            meta = meta_by_name[config.name]
            row = make_row(config, trades, stage="improvement_paths", extra=meta)
            row["config_summary"] = (
                f"{row['direction_filter']} {row['entry_mode']} {row['entry_start']}-{row['entry_end']} "
                f"rr{row['rr']} tp{row['tp1_ratio']} gap{row['min_gap_atr_pct']} "
                f"htf{row['htf_level_tf_minutes']} n{row['htf_n_left']} cap{row['htf_trade_max_per_session']} "
                f"fvgL{row['lsi_fvg_window_left']} fvgR{row['lsi_fvg_window_right']} "
                f"lag{row['max_fvg_to_inversion_bars']} atr{row['atr_length']}"
            )
            rows.append(row)

        rows_sorted = sorted(rows, key=pre_rank_key, reverse=True)
        write_json(GRID_RESULTS_PATH, {"rows": rows_sorted})

    leaders_by_structure = best_by_group(rows_sorted, "structure_id")
    leaders_by_end = best_by_group(rows_sorted, "entry_end_variant")
    leaders_by_atr = best_by_group(rows_sorted, "atr_variant")
    leaders_by_lag = best_by_group(rows_sorted, "lag_variant")

    finalist_ids = finalist_candidate_ids(
        rows_sorted,
        top_overall=args.top_overall,
        leaders_by_structure=leaders_by_structure,
        leaders_by_end=leaders_by_end,
        leaders_by_atr=leaders_by_atr,
        leaders_by_lag=leaders_by_lag,
    )
    row_map = {row["candidate_id"]: row for row in rows_sorted}
    finalists = [row_map[candidate_id] for candidate_id in finalist_ids]
    print(f"  Finalists for downstream read: {len(finalists)}", flush=True)

    print("\n[Phase 2] Stitched OOS + secondary holdout reads", flush=True)
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
        oos_prop_outcomes = simulate_account_attempts(
            specialist_name=config.name,
            trades=trades_oos,
            trading_dates=oos_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        oos_prop_scorecard = build_prop_scorecard(oos_prop_outcomes, PROP_PROFILE)
        oos_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=config.name,
            trades=trades_oos,
            trading_dates=oos_dates,
            profile=FUNDED_PROFILE,
        )
        oos_funded_scorecard = build_funded_first_payout_scorecard(
            oos_funded_outcomes,
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
        holdout_prop_outcomes = simulate_account_attempts(
            specialist_name=f"{config.name} holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
        holdout_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=f"{config.name} holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=FUNDED_PROFILE,
        )
        holdout_funded_scorecard = build_funded_first_payout_scorecard(
            holdout_funded_outcomes,
            FUNDED_PROFILE,
        )

        payload_row = dict(source_row)
        payload_row.update(
            {
                "pre_holdout_metrics": {
                    "total_trades": payload_row["pre_holdout_trades"],
                    "profit_factor": payload_row["pre_holdout_pf"],
                    "avg_r": payload_row["pre_holdout_avg_r"],
                    "calmar_ratio": payload_row["pre_holdout_calmar"],
                    "total_r": payload_row["pre_holdout_total_r"],
                    "max_drawdown_r": payload_row["pre_holdout_max_dd_r"],
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

    payload = {
        "info": {
            "discovery_start": DISCOVERY_START,
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": (
                pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "structures": [item[0] for item in STRUCTURES],
            "entry_ends": list(ENTRY_ENDS),
            "atr_lengths": list(ATR_LENGTHS),
            "lags": list(LAGS),
            "packet_size": len(configs),
            "finalist_count": len(finalists_sorted),
            "primary_read_note": (
                "Pre-holdout + stitched OOS are primary. The already-opened holdout is "
                "reported only as a secondary read."
            ),
            "funded_profile": asdict(FUNDED_PROFILE),
            "prop_profile": asdict(PROP_PROFILE),
        },
        "current_lead": current_lead,
        "recommended_restart": recommended,
        "path_leaders": {
            "structure": {
                key: finalist_map[row["candidate_id"]]
                for key, row in leaders_by_structure.items()
            },
            "entry_end": {
                key: finalist_map[row["candidate_id"]]
                for key, row in leaders_by_end.items()
            },
            "atr": {
                key: finalist_map[row["candidate_id"]]
                for key, row in leaders_by_atr.items()
            },
            "lag": {
                key: finalist_map[row["candidate_id"]]
                for key, row in leaders_by_lag.items()
            },
        },
        "finalists": finalists_sorted,
        "pre_holdout_top10": rows_sorted[:10],
    }

    write_json(SUMMARY_PATH, payload)
    write_report(payload)

    print("\nDone.", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"JSON:   {SUMMARY_PATH}", flush=True)
    print(f"Elapsed: {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
