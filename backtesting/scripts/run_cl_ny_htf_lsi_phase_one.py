#!/usr/bin/env python3
"""Phase-One Robust Pipeline — CL NY HTF-LSI frozen shortlist."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

from run_cross_asset_htf_lsi_broad_discovery import (  # noqa: E402
    DISCOVERY_START,
    HOLDOUT_START,
    build_config,
    load_timeframe_data,
)
from run_gc_ny_htf_lsi_phase_one import (  # noqa: E402
    FUNDED_PROFILE,
    PROP_PROFILE,
    WF_IS_MONTHS,
    WF_OOS_MONTHS,
    WF_STEP_MONTHS,
    metrics_snapshot,
    print_metrics,
    print_scorecard,
    reconstruct_combined_oos_trades,
    trading_dates_between,
    verdict_from_scorecards,
    write_json,
)

SHORTLIST_SOURCE = ROOT / "data" / "results" / "cl_ny_htf_lsi_stitched_followup" / "summary.json"
STITCHED_REPORT_PATH = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_STITCHED_FOLLOWUP.md"
OUTPUT_DIR = ROOT / "data" / "results" / "cl_ny_htf_lsi_phase_one"
REPORT_PATH = ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_PHASE_ONE.md"

CANDIDATE_ORDER = (
    "structural_alt_htf60_end14",
    "htf_n7_end14",
    "early_end1030",
    "control_stage_b_end13",
    "control_stage_b_end14",
)


def load_shortlist_rows() -> list[dict]:
    rows = json.loads(SHORTLIST_SOURCE.read_text())
    row_map = {row["candidate_id"]: row for row in rows}
    return [row_map[candidate_id] for candidate_id in CANDIDATE_ORDER]


def config_from_summary_row(row: dict):
    cfg = row["config"]
    return build_config(
        symbol="CL",
        timeframe=row["timeframe"],
        direction_filter=cfg["direction_filter"],
        entry_mode=cfg["entry_mode"],
        entry_start=cfg["entry_start"],
        entry_end=cfg["entry_end"],
        rr=float(cfg["rr"]),
        tp1_ratio=float(cfg["tp1_ratio"]),
        min_gap_atr_pct=float(cfg["min_gap_atr_pct"]),
        atr_length=int(cfg["atr_length"]),
        htf_level_tf_minutes=int(cfg["htf_level_tf_minutes"]),
        htf_n_left=int(cfg["htf_n_left"]),
        htf_trade_max_per_session=int(cfg["htf_trade_max_per_session"]),
        lsi_fvg_window_left=int(cfg["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(cfg["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(cfg["max_fvg_to_inversion_bars"]),
        min_stop_points=0.0,
        min_tp1_points=0.0,
        name=row["label"],
    )


def write_report(payload: dict, holdout_end_inclusive: str) -> None:
    lines = [
        "# CL NY HTF-LSI Phase One",
        "",
        f"- Frozen shortlist source: [{STITCHED_REPORT_PATH.name}]({STITCHED_REPORT_PATH.as_posix()})",
        f"- Holdout opened once for phase one: `{HOLDOUT_START}` to `{holdout_end_inclusive}`.",
        f"- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`{payload['info']['oos_stream_start']}` to `{payload['info']['oos_stream_end_inclusive']}`).",
        "- Bailey-style PSR / DSR was not rerun on this CL packet; phase-one verdicts here are downstream scorecard reads on a frozen pre-holdout shortlist.",
        "",
        "## Summary",
        "",
    ]

    for row in payload["results"]:
        prop_sc = row["oos_prop_scorecard"]
        funded_sc = row["oos_funded_scorecard"]
        holdout_prop = row["holdout_prop_scorecard"]
        holdout_funded = row["holdout_funded_scorecard"]
        lines.append(
            f"- `{row['name']}`: verdict `{row['verdict']}`, OOS prop payout "
            f"`{prop_sc['first_payout_rate']:.1%}`, OOS funded payout `{funded_sc['payout_rate']:.1%}`, "
            f"holdout prop payout `{holdout_prop['first_payout_rate']:.1%}`, "
            f"holdout funded payout `{holdout_funded['payout_rate']:.1%}`"
        )

    lines.extend(["", "## Candidate Details", ""])

    for row in payload["results"]:
        prop_sc = row["oos_prop_scorecard"]
        funded_sc = row["oos_funded_scorecard"]
        holdout_prop = row["holdout_prop_scorecard"]
        holdout_funded = row["holdout_funded_scorecard"]
        lines.extend(
            [
                f"### {row['name']}",
                "",
                f"- verdict: `{row['verdict']}`",
                f"- candidate_id: `{row['candidate_id']}`",
                f"- config: `{row['config_summary']}`",
                f"- discovery deflation: `{row['discovery_psr']}` / `{row['discovery_dsr']}`",
                (
                    f"- pre-holdout structural metrics: trades `{row['pre_holdout_metrics']['total_trades']}`, "
                    f"PF `{row['pre_holdout_metrics']['profit_factor']}`, avgR `{row['pre_holdout_metrics']['avg_r']}`, "
                    f"totalR `{row['pre_holdout_metrics']['total_r']}`"
                ),
                (
                    f"- stitched OOS metrics: trades `{row['oos_metrics']['total_trades']}`, "
                    f"PF `{row['oos_metrics']['profit_factor']}`, avgR `{row['oos_metrics']['avg_r']}`, "
                    f"totalR `{row['oos_metrics']['total_r']}`"
                ),
                (
                    f"- OOS prop scorecard: payout `{prop_sc['first_payout_rate']:.1%}`, "
                    f"breach `{prop_sc['breach_rate']:.1%}`, open `{prop_sc['open_rate']:.1%}`, "
                    f"EV `${prop_sc['ev_per_attempt']}`, avg days `{prop_sc['average_days_to_payout']}`"
                ),
                (
                    f"- OOS funded scorecard: payout `{funded_sc['payout_rate']:.1%}`, "
                    f"breach `{funded_sc['breach_rate']:.1%}`, open `{funded_sc['open_rate']:.1%}`, "
                    f"EV `${funded_sc['ev_per_start_usd']}`, avg days `{funded_sc['average_days_to_payout']}`"
                ),
                (
                    f"- holdout metrics: trades `{row['holdout_metrics']['total_trades']}`, "
                    f"PF `{row['holdout_metrics']['profit_factor']}`, avgR `{row['holdout_metrics']['avg_r']}`, "
                    f"totalR `{row['holdout_metrics']['total_r']}`"
                ),
                (
                    f"- holdout prop scorecard: payout `{holdout_prop['first_payout_rate']:.1%}`, "
                    f"breach `{holdout_prop['breach_rate']:.1%}`, open `{holdout_prop['open_rate']:.1%}`, "
                    f"EV `${holdout_prop['ev_per_attempt']}`, avg days `{holdout_prop['average_days_to_payout']}`"
                ),
                (
                    f"- holdout funded scorecard: payout `{holdout_funded['payout_rate']:.1%}`, "
                    f"breach `{holdout_funded['breach_rate']:.1%}`, open `{holdout_funded['open_rate']:.1%}`, "
                    f"EV `${holdout_funded['ev_per_start_usd']}`, avg days `{holdout_funded['average_days_to_payout']}`"
                ),
                (
                    f"- OOS cohort EV: prop `10/25/50 = ${row['oos_prop_scorecard']['ev_by_cohort']['10']} / "
                    f"${row['oos_prop_scorecard']['ev_by_cohort']['25']} / ${row['oos_prop_scorecard']['ev_by_cohort']['50']}`, "
                    f"funded `10/25/50 = ${row['oos_funded_cohort_ev']['10']} / "
                    f"${row['oos_funded_cohort_ev']['25']} / ${row['oos_funded_cohort_ev']['50']}`"
                ),
                (
                    f"- holdout cohort EV: prop `10/25/50 = ${row['holdout_prop_scorecard']['ev_by_cohort']['10']} / "
                    f"${row['holdout_prop_scorecard']['ev_by_cohort']['25']} / ${row['holdout_prop_scorecard']['ev_by_cohort']['50']}`, "
                    f"funded `10/25/50 = ${row['holdout_funded_cohort_ev']['10']} / "
                    f"${row['holdout_funded_cohort_ev']['25']} / ${row['holdout_funded_cohort_ev']['50']}`"
                ),
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("Phase-One Robust Pipeline — CL NY HTF-LSI", flush=True)
    print("=" * 72, flush=True)

    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    shortlist_rows = load_shortlist_rows()
    configs = [config_from_summary_row(row) for row in shortlist_rows]

    print("\n[Phase 0] Model freeze", flush=True)
    print(f"  Frozen candidates: {', '.join(row['candidate_id'] for row in shortlist_rows)}", flush=True)
    print(f"  Holdout start: {HOLDOUT_START}", flush=True)
    print(
        f"  Funded model: ${FUNDED_PROFILE.starting_balance_usd:,.0f} start, "
        f"${FUNDED_PROFILE.trailing_drawdown_usd:,.0f} trailing DD, "
        f"payout at ${FUNDED_PROFILE.first_payout_floor_usd:,.0f}",
        flush=True,
    )
    print(
        f"  Prop model: +{PROP_PROFILE.payout_target_r}R payout, "
        f"{PROP_PROFILE.breach_limit_r}R breach, {PROP_PROFILE.daily_loss_limit_r}R daily limit",
        flush=True,
    )

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

    print("\nBuilding maps + signal cache...", flush=True)
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)

    windows = generate_windows(
        DISCOVERY_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start
    oos_end_inclusive = (
        pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    oos_dates = trading_dates_between(df_base, oos_start, HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    payload: dict[str, object] = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": oos_end_inclusive,
            "oos_stream_end_exclusive": HOLDOUT_START,
            "funded_profile": asdict(FUNDED_PROFILE),
            "prop_profile": asdict(PROP_PROFILE),
            "shortlist_source": str(SHORTLIST_SOURCE),
        },
        "results": [],
    }

    for source_row, config in zip(shortlist_rows, configs):
        print(f"\n{'=' * 72}", flush=True)
        print(f"CANDIDATE: {source_row['candidate_id']} | {config.name}", flush=True)

        print("\n[Phase 1] Structural viability", flush=True)
        trades_pre = run_backtest(
            df_base,
            config,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        pre_metrics = compute_metrics(trades_pre)
        print_metrics("Pre-holdout", pre_metrics)

        viable = (
            pre_metrics.get("total_trades", 0) >= 100
            and pre_metrics.get("profit_factor", 0) > 1.0
            and pre_metrics.get("avg_r", 0) > 0.0
        )
        print(f"  Viable: {viable}", flush=True)

        if not viable:
            payload["results"].append(
                {
                    "name": config.name,
                    "candidate_id": source_row["candidate_id"],
                    "verdict": "NO-GO",
                    "reason": "structural viability failed",
                    "discovery_psr": "not_run",
                    "discovery_dsr": "not_run",
                    "pre_holdout_metrics": metrics_snapshot(pre_metrics),
                }
            )
            continue

        print("\n[Phase 2] Reconstructed walk-forward OOS stream", flush=True)
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
        print_metrics("Combined OOS", oos_metrics)

        print("\n[Phase 3] First-payout scorecard (stitched OOS stream)", flush=True)
        oos_prop_outcomes = simulate_account_attempts(
            specialist_name=config.name,
            trades=trades_oos,
            trading_dates=oos_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        oos_prop_scorecard = build_prop_scorecard(oos_prop_outcomes, PROP_PROFILE)
        print_scorecard("Prop model (R-based)", oos_prop_scorecard)

        oos_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=config.name,
            trades=trades_oos,
            trading_dates=oos_dates,
            profile=FUNDED_PROFILE,
        )
        oos_funded_scorecard = build_funded_first_payout_scorecard(oos_funded_outcomes, FUNDED_PROFILE)
        oos_funded_forecast = build_funded_first_payout_forecast(oos_funded_outcomes)
        print_scorecard("Funded model (USD)", oos_funded_scorecard)

        print("\n[Phase 4] Holdout confirmation", flush=True)
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
        print_metrics("Holdout", holdout_metrics)

        holdout_prop_outcomes = simulate_account_attempts(
            specialist_name=f"{config.name}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
        print_scorecard("Holdout prop model", holdout_prop_scorecard)

        holdout_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=f"{config.name}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=FUNDED_PROFILE,
        )
        holdout_funded_scorecard = build_funded_first_payout_scorecard(
            holdout_funded_outcomes,
            FUNDED_PROFILE,
        )
        holdout_funded_forecast = build_funded_first_payout_forecast(holdout_funded_outcomes)
        print_scorecard("Holdout funded model", holdout_funded_scorecard)

        print("\n[Phase 5] Cohort EV", flush=True)
        oos_funded_cohort_ev = {
            str(cohort_size): round(float(oos_funded_scorecard.get("ev_per_start_usd", 0.0)) * cohort_size, 2)
            for cohort_size in PROP_PROFILE.cohort_sizes
        }
        holdout_funded_cohort_ev = {
            str(cohort_size): round(float(holdout_funded_scorecard.get("ev_per_start_usd", 0.0)) * cohort_size, 2)
            for cohort_size in PROP_PROFILE.cohort_sizes
        }
        for cohort_size in PROP_PROFILE.cohort_sizes:
            prop_ev = float(oos_prop_scorecard.get("ev_by_cohort", {}).get(str(cohort_size), 0.0))
            funded_ev = float(oos_funded_cohort_ev[str(cohort_size)])
            print(
                f"  OOS cohort {cohort_size}: prop EV ${prop_ev:+.0f} | funded EV ${funded_ev:+.0f}",
                flush=True,
            )
        for cohort_size in PROP_PROFILE.cohort_sizes:
            prop_ev = float(holdout_prop_scorecard.get("ev_by_cohort", {}).get(str(cohort_size), 0.0))
            funded_ev = float(holdout_funded_cohort_ev[str(cohort_size)])
            print(
                f"  Holdout cohort {cohort_size}: prop EV ${prop_ev:+.0f} | funded EV ${funded_ev:+.0f}",
                flush=True,
            )

        verdict = verdict_from_scorecards(oos_funded_scorecard, holdout_funded_scorecard)
        print(f"\nVERDICT: {verdict}", flush=True)

        payload["results"].append(
            {
                "name": config.name,
                "candidate_id": source_row["candidate_id"],
                "verdict": verdict,
                "config_summary": (
                    f"{config.direction_filter} {config.lsi_entry_mode} "
                    f"{config.sessions[0].entry_start}-{config.sessions[0].entry_end} "
                    f"rr{config.rr} tp{config.tp1_ratio} gap{config.sessions[0].min_gap_atr_pct} "
                    f"htf{config.htf_level_tf_minutes} n{config.htf_n_left} "
                    f"cap{config.htf_trade_max_per_session} "
                    f"fvgL{config.lsi_fvg_window_left} fvgR{config.lsi_fvg_window_right} "
                    f"lag{config.max_fvg_to_inversion_bars}"
                ),
                "discovery_psr": "not_run",
                "discovery_dsr": "not_run",
                "pre_holdout_metrics": metrics_snapshot(pre_metrics),
                "oos_metrics": metrics_snapshot(oos_metrics),
                "holdout_metrics": metrics_snapshot(holdout_metrics),
                "oos_prop_scorecard": oos_prop_scorecard,
                "oos_funded_scorecard": oos_funded_scorecard,
                "oos_funded_forecast": oos_funded_forecast,
                "holdout_prop_scorecard": holdout_prop_scorecard,
                "holdout_funded_scorecard": holdout_funded_scorecard,
                "holdout_funded_forecast": holdout_funded_forecast,
                "oos_funded_cohort_ev": oos_funded_cohort_ev,
                "holdout_funded_cohort_ev": holdout_funded_cohort_ev,
            }
        )

    payload["results"].sort(
        key=lambda row: (
            {"STRONG": 2, "CONDITIONAL": 1, "NO-GO": 0}.get(row["verdict"], 0),
            float(row.get("oos_funded_scorecard", {}).get("ev_per_start_usd", 0.0)),
            float(row.get("oos_funded_scorecard", {}).get("payout_rate", 0.0)),
            float(row.get("holdout_funded_scorecard", {}).get("ev_per_start_usd", 0.0)),
            float(row.get("holdout_funded_scorecard", {}).get("payout_rate", 0.0)),
        ),
        reverse=True,
    )

    write_json(OUTPUT_DIR / "phase_one_results.json", payload)
    write_report(payload, holdout_end_inclusive)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
