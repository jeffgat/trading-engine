#!/usr/bin/env python3
"""Phase-One Robust Pipeline — NQ NY EQHL-LSI frozen lead.

Evaluates the promoted 5m -> 5m EQHL lead for first-payout economics:
  0. Model freeze
  1. Structural viability on full pre-holdout
  2. Reconstruct the stitched discovery walk-forward OOS stream
  3. First-payout scorecard on the combined OOS stream
  4. First-payout holdout read on 2025-04-01+
  5. Cohort EV summary
"""

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
from run_cross_asset_eqhl_lsi_broad_discovery import (  # noqa: E402
    HOLDOUT_START,
    RESEARCH_START,
    build_config,
    ensure_required_data,
    load_timeframe_data,
)
from run_nq_ny_htf_lsi_phase_one import (  # noqa: E402
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
)


PROMOTION_PACKET_PATH = ROOT / "data" / "results" / "nq_ny_eqhl_lsi_promotion_packet" / "5m_eqhl5m_summary.json"
OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_eqhl_lsi_phase_one"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_EQHL_LSI_PHASE_ONE.md"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def build_frozen_config():
    return build_config(
        symbol="NQ",
        timeframe="5m",
        eqhl_tf_minutes=5,
        eqhl_tolerance_ticks=2,
        eqhl_min_touches=2,
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_end="13:00",
        rr=3.25,
        tp1_ratio=0.6,
        min_gap_atr_pct=3.0,
        atr_length=14,
        eqhl_n_left=2,
        eqhl_lookback_bars=48,
        left_minutes=100,
        right_minutes=15,
        min_stop_points=0.0,
        min_tp1_points=0.0,
    )


def config_summary(config) -> str:
    session = config.sessions[0]
    return (
        f"{config.direction_filter} {config.lsi_entry_mode} "
        f"{session.entry_start}-{session.entry_end} "
        f"rr{config.rr} tp{config.tp1_ratio} gap{session.min_gap_atr_pct} atr{config.atr_length} "
        f"eqhl{config.eqhl_level_tf_minutes}m tol{config.eqhl_tolerance_ticks}t "
        f"touches{config.eqhl_min_touches} left{config.lsi_fvg_window_left} right{config.lsi_fvg_window_right}"
    )


def load_promotion_reference() -> dict | None:
    if not PROMOTION_PACKET_PATH.exists():
        return None
    payload = json.loads(PROMOTION_PACKET_PATH.read_text())
    for row in payload.get("walkforward", []):
        if (
            row.get("rr") == 3.25
            and row.get("tp1_ratio") == 0.6
            and row.get("lsi_fvg_window_left") == 20
            and row.get("lsi_fvg_window_right") == 3
        ):
            return row
    return None


def write_report(payload: dict, holdout_end_inclusive: str) -> None:
    row = payload["result"]
    prop_sc = row["oos_prop_scorecard"]
    funded_sc = row["oos_funded_scorecard"]
    holdout_prop = row["holdout_prop_scorecard"]
    holdout_funded = row["holdout_funded_scorecard"]
    lines = [
        "# NQ NY EQHL-LSI Phase One",
        "",
        f"- Frozen candidate source: [{PROMOTION_PACKET_PATH.name}]({PROMOTION_PACKET_PATH.as_posix()})",
        f"- Holdout opened once for phase one: `{HOLDOUT_START}` to `{holdout_end_inclusive}`.",
        f"- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`{payload['info']['oos_stream_start']}` to `{payload['info']['oos_stream_end_inclusive']}`).",
        "",
        "## Summary",
        "",
        (
            f"- `{row['name']}`: verdict `{row['verdict']}`, OOS prop payout "
            f"`{prop_sc['first_payout_rate']:.1%}`, OOS funded payout `{funded_sc['payout_rate']:.1%}`, "
            f"holdout prop payout `{holdout_prop['first_payout_rate']:.1%}`, "
            f"holdout funded payout `{holdout_funded['payout_rate']:.1%}`"
        ),
        "",
        "## Candidate Details",
        "",
        f"### {row['name']}",
        "",
        f"- verdict: `{row['verdict']}`",
        f"- config: `{row['config_summary']}`",
        (
            f"- promotion source metrics: validation PF `{row['promotion_reference']['validation_pf']}`, "
            f"validation avgR `{row['promotion_reference']['validation_avg_r']}`, "
            f"stitched OOS PF `{row['promotion_reference']['wf_pf']}`, "
            f"stitched OOS avgR `{row['promotion_reference']['wf_avg_r']}`"
            if row.get("promotion_reference")
            else "- promotion source metrics: `unavailable`"
        ),
        (
            f"- discovery PSR / DSR: `{row['discovery_psr']}` / `{row['discovery_dsr']}`"
        ),
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
            f"${row['oos_prop_scorecard']['ev_by_cohort']['25']} / "
            f"${row['oos_prop_scorecard']['ev_by_cohort']['50']}`, funded `10/25/50 = "
            f"${row['oos_funded_cohort_ev']['10']} / ${row['oos_funded_cohort_ev']['25']} / "
            f"${row['oos_funded_cohort_ev']['50']}`"
        ),
        (
            f"- holdout cohort EV: prop `10/25/50 = ${row['holdout_prop_scorecard']['ev_by_cohort']['10']} / "
            f"${row['holdout_prop_scorecard']['ev_by_cohort']['25']} / "
            f"${row['holdout_prop_scorecard']['ev_by_cohort']['50']}`, funded `10/25/50 = "
            f"${row['holdout_funded_cohort_ev']['10']} / ${row['holdout_funded_cohort_ev']['25']} / "
            f"${row['holdout_funded_cohort_ev']['50']}`"
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("Phase-One Robust Pipeline — NQ NY EQHL-LSI", flush=True)
    print("=" * 72, flush=True)

    t0 = time.time()
    ensure_required_data("NQ")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = build_frozen_config()
    promotion_reference = load_promotion_reference()

    print("\n[Phase 0] Model freeze", flush=True)
    print(f"  Frozen candidate: {config.name}", flush=True)
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

    print("\nLoading NQ 5m EQHL-LSI data (5m + 1m + 1s)...", flush=True)
    df_base, df_1m, df_1s = load_timeframe_data("NQ", "5m")
    signal_df_1m = df_1m
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    print(f"  5m bars: {len(df_base):,}", flush=True)
    print(f"  1m bars: {len(signal_df_1m):,}", flush=True)
    print(f"  1s bars: {len(df_1s):,}", flush=True)
    print(f"  Holdout end: {holdout_end_inclusive}", flush=True)

    print("\nBuilding maps + signal cache...", flush=True)
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)

    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start
    oos_end_inclusive = (pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
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
            "promotion_packet_source": str(PROMOTION_PACKET_PATH),
        }
    }

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
        payload["result"] = {
            "name": config.name,
            "verdict": "NO-GO",
            "reason": "structural viability failed",
            "config_summary": config_summary(config),
            "pre_holdout_metrics": metrics_snapshot(pre_metrics),
            "discovery_psr": "not_run",
            "discovery_dsr": "not_run",
            "promotion_reference": None,
        }
        write_json(OUTPUT_DIR / "phase_one_results.json", payload)
        write_report(payload, holdout_end_inclusive)
        print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
        print(f"Output: {OUTPUT_DIR}", flush=True)
        print(f"Report: {REPORT_PATH}", flush=True)
        return

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
    holdout_funded_scorecard = build_funded_first_payout_scorecard(holdout_funded_outcomes, FUNDED_PROFILE)
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

    verdict = verdict_from_scorecards(oos_prop_scorecard, holdout_prop_scorecard)
    print(f"\nVERDICT: {verdict}", flush=True)

    payload["result"] = {
        "name": config.name,
        "verdict": verdict,
        "config_summary": config_summary(config),
        "discovery_psr": "not_run",
        "discovery_dsr": "not_run",
        "promotion_reference": {
            "validation_pf": round(float(promotion_reference["validation_pf"]), 4),
            "validation_avg_r": round(float(promotion_reference["validation_avg_r"]), 4),
            "wf_pf": round(float(promotion_reference["walkforward"]["combined"]["pf"]), 4),
            "wf_avg_r": round(float(promotion_reference["walkforward"]["combined"]["avg_r"]), 4),
        }
        if promotion_reference
        else None,
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

    write_json(OUTPUT_DIR / "phase_one_results.json", payload)
    write_report(payload, holdout_end_inclusive)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
