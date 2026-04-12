#!/usr/bin/env python3
"""Phase-One Robust Pipeline — NQ NY HTF-LSI frozen lead.

Evaluates the frozen 5m HTF-LSI anchor for first-payout economics:
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
sys.path.insert(0, str(ROOT / "src"))

from htf_lsi_common import load_shortlist_config, load_timeframe_data  # noqa: E402
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    PropFirmProfile,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

SHORTLIST_PATH = ROOT / "data" / "results" / "nq_ny_htf_lsi_discovery" / "shortlist.json"
DISCOVERY_PACKET_PATH = (
    ROOT / "data" / "results" / "nq_ny_htf_lsi_discovery" / "stage_i_psr_dsr_holdout_manual.json"
)
DISCOVERY_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_DISCOVERY.md"

OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_phase_one"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_PHASE_ONE.md"

RESEARCH_START = "2016-01-01"
HOLDOUT_START = "2025-04-01"
WF_IS_MONTHS = 36
WF_OOS_MONTHS = 12
WF_STEP_MONTHS = 12

FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0,
    reset_fee=50.0,
    payout_split=0.80,
    payout_target_r=5.0,
    breach_limit_r=-4.0,
    daily_loss_limit_r=-2.0,
    min_trading_days=5,
    cohort_sizes=(10, 25, 50),
    block_size_days=20,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def metrics_snapshot(metrics: dict) -> dict:
    keep = {
        "total_trades",
        "total_r",
        "calmar_ratio",
        "sharpe_ratio",
        "max_drawdown_r",
        "win_rate",
        "profit_factor",
        "avg_r",
    }
    snap: dict[str, float | int | None] = {}
    for key, value in metrics.items():
        if key not in keep:
            continue
        if isinstance(value, (int, float)):
            snap[key] = round(float(value), 4)
        else:
            snap[key] = value
    return snap


def print_metrics(label: str, metrics: dict) -> None:
    print(
        f"  {label}: {metrics.get('total_trades', 0)} trades | "
        f"Net R: {metrics.get('total_r', 0):+.1f} | "
        f"Calmar: {metrics.get('calmar_ratio', 0) or 0:.2f} | "
        f"Sharpe: {metrics.get('sharpe_ratio', 0) or 0:.2f} | "
        f"DD: {metrics.get('max_drawdown_r', 0):.2f}R | "
        f"WR: {metrics.get('win_rate', 0):.1%} | "
        f"PF: {metrics.get('profit_factor', 0) or 0:.2f}",
        flush=True,
    )


def print_scorecard(label: str, scorecard: dict) -> None:
    print(f"\n  {label}", flush=True)
    print(f"    Attempts: {scorecard.get('total_starts', scorecard.get('total_attempts', 0))}", flush=True)
    payout_rate = scorecard.get("payout_rate", scorecard.get("first_payout_rate", 0.0))
    breach_rate = scorecard.get("breach_rate", 0.0)
    open_rate = scorecard.get("open_rate", 0.0)
    print(
        f"    Payout rate: {payout_rate:.1%} | Breach rate: {breach_rate:.1%} | Open: {open_rate:.1%}",
        flush=True,
    )
    ev = scorecard.get("ev_per_start_usd", scorecard.get("ev_per_attempt", 0.0))
    print(f"    EV per attempt: ${ev}", flush=True)
    days = scorecard.get("average_days_to_payout", scorecard.get("median_days_to_payout"))
    if days:
        print(f"    Avg days to payout: {days:.0f}", flush=True)


def trading_dates_between(
    df: pd.DataFrame,
    start: str,
    end_exclusive: str,
) -> list[str]:
    idx = df.index[(df.index >= start) & (df.index < end_exclusive)]
    if len(idx) == 0:
        return []
    dates = pd.Index(pd.to_datetime(idx.normalize()).unique()).sort_values()
    return [d.strftime("%Y-%m-%d") for d in dates]


def reconstruct_combined_oos_trades(
    df_base: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_1s: pd.DataFrame,
    signal_df_1m: pd.DataFrame,
    maps: dict,
    signal_cache: dict,
    config,
) -> list:
    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    combined = []
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
        combined.extend(trades)
    return combined


def verdict_from_scorecards(prop_scorecard: dict, holdout_prop_scorecard: dict) -> str:
    payout_rate = float(prop_scorecard.get("first_payout_rate", 0.0))
    ev_per_attempt = float(prop_scorecard.get("ev_per_attempt", 0.0))
    holdout_payout_rate = float(holdout_prop_scorecard.get("first_payout_rate", 0.0))

    if payout_rate >= 0.60 and ev_per_attempt > 0.0 and holdout_payout_rate >= 0.40:
        return "STRONG"
    if payout_rate >= 0.40 and ev_per_attempt > 0.0:
        return "CONDITIONAL"
    return "NO-GO"


def write_report(payload: dict, holdout_end_inclusive: str) -> None:
    row = payload["result"]
    prop_sc = row["oos_prop_scorecard"]
    funded_sc = row["oos_funded_scorecard"]
    holdout_prop = row["holdout_prop_scorecard"]
    holdout_funded = row["holdout_funded_scorecard"]
    lines = [
        "# NQ NY HTF-LSI Phase One",
        "",
        f"- Frozen shortlist source: [{DISCOVERY_REPORT_PATH.name}]({DISCOVERY_REPORT_PATH.as_posix()})",
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
            f"- discovery PSR / DSR: `{row['discovery_psr']}` / `{row['discovery_dsr']}` "
            f"(raw trials `{row['trial_counts']['raw_trials']}`, effective `{row['trial_counts']['effective_trials']}`)"
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
    print("Phase-One Robust Pipeline — NQ NY HTF-LSI", flush=True)
    print("=" * 72, flush=True)

    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    shortlist_payload = json.loads(SHORTLIST_PATH.read_text())
    discovery_packet = json.loads(DISCOVERY_PACKET_PATH.read_text())
    config = load_shortlist_config(SHORTLIST_PATH)
    leader_row = shortlist_payload[0] if isinstance(shortlist_payload, list) else shortlist_payload

    print("\n[Phase 0] Model freeze", flush=True)
    print(f"  Frozen candidate: {leader_row['label']}", flush=True)
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

    print("\nLoading NQ 5m HTF-LSI data (5m + 1m + 1s)...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
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
            "shortlist_source": str(SHORTLIST_PATH),
            "discovery_packet_source": str(DISCOVERY_PACKET_PATH),
        },
        "candidate": leader_row,
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
            "name": leader_row["label"],
            "verdict": "NO-GO",
            "reason": "structural viability failed",
            "pre_holdout_metrics": metrics_snapshot(pre_metrics),
        }
        write_json(OUTPUT_DIR / "phase_one_results.json", payload)
        REPORT_PATH.write_text(
            "\n".join(
                [
                    "# NQ NY HTF-LSI Phase One",
                    "",
                    f"- Frozen shortlist source: [{DISCOVERY_REPORT_PATH.name}]({DISCOVERY_REPORT_PATH.as_posix()})",
                    f"- Verdict: `NO-GO` because structural viability failed on pre-holdout data.",
                    "",
                ]
            )
        )
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
    print(
        f"  Discovery reference: WF avgR {discovery_packet['walkforward_oos']['metrics']['avg_r']:.4f} | "
        f"WF PF {discovery_packet['walkforward_oos']['metrics']['pf']:.4f}",
        flush=True,
    )

    print("\n[Phase 3] First-payout scorecard (stitched OOS stream)", flush=True)
    oos_prop_outcomes = simulate_account_attempts(
        specialist_name=leader_row["label"],
        trades=trades_oos,
        trading_dates=oos_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=config.risk_usd,
    )
    oos_prop_scorecard = build_prop_scorecard(oos_prop_outcomes, PROP_PROFILE)
    print_scorecard("Prop model (R-based)", oos_prop_scorecard)

    oos_funded_outcomes = simulate_funded_first_payouts(
        specialist_name=leader_row["label"],
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
        specialist_name=f"{leader_row['label']}_holdout",
        trades=trades_holdout,
        trading_dates=holdout_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=config.risk_usd,
    )
    holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
    print_scorecard("Holdout prop model", holdout_prop_scorecard)

    holdout_funded_outcomes = simulate_funded_first_payouts(
        specialist_name=f"{leader_row['label']}_holdout",
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

    verdict = verdict_from_scorecards(oos_prop_scorecard, holdout_prop_scorecard)
    print(f"\nVERDICT: {verdict}", flush=True)

    payload["result"] = {
        "name": leader_row["label"],
        "verdict": verdict,
        "config_summary": (
            f"{leader_row['direction_filter']} {leader_row['entry_mode']} "
            f"{leader_row['entry_start']}-{leader_row['entry_end']} "
            f"rr{leader_row['rr']} tp{leader_row['tp1_ratio']} "
            f"gap{leader_row['min_gap_atr_pct']} "
            f"htf{leader_row['htf_level_tf_minutes']} n{leader_row['htf_n_left']} "
            f"cap{leader_row['htf_trade_max_per_session']} "
            f"fvgL{leader_row['lsi_fvg_window_left']} fvgR{leader_row['lsi_fvg_window_right']}"
        ),
        "trial_counts": discovery_packet["trial_counts"],
        "discovery_psr": discovery_packet["pre_holdout_full"]["psr"]["psr"],
        "discovery_dsr": discovery_packet["pre_holdout_full"]["dsr"]["dsr"],
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
