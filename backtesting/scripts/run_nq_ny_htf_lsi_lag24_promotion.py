#!/usr/bin/env python3
"""Promotion comparison for NQ NY HTF-LSI 5m lag0 vs lag24."""

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

from htf_lsi_common import (  # noqa: E402
    build_config,
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
    save_json,
)
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.prop_constraints import evaluate_constraints, evaluate_constraints_mc  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, run_monte_carlo  # noqa: E402
from run_nq_ny_htf_lsi_phase_one import (  # noqa: E402
    FUNDED_PROFILE,
    HOLDOUT_START,
    PROP_PROFILE,
    RESEARCH_START,
    WF_IS_MONTHS,
    WF_OOS_MONTHS,
    WF_STEP_MONTHS,
    metrics_snapshot,
    reconstruct_combined_oos_trades,
    trading_dates_between,
    verdict_from_scorecards,
)
from run_nq_ny_htf_lsi_phase_two import (  # noqa: E402
    CONTINUITY_CONSTRAINTS,
    MC_CONSTRAINTS,
    MC_RUIN_THRESHOLD_R,
    POST_PAYOUT_BREACH_BALANCE,
    POST_PAYOUT_RESET_BALANCE,
    POST_PAYOUT_START_BALANCE,
    POST_PAYOUT_WITHDRAW_TRIGGER,
    build_day_to_r,
    build_post_payout_scorecard,
    last_trading_days_of_week,
    phase_3_pass,
    phase_4_pass,
    phase_5_pass,
    simulate_post_payout_start,
    verdict_from_phases,
)
from run_nq_ny_htf_lsi_phase_two_risk_sweep import RISK_SWEEP, simulate_for_risk  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_lag24_promotion"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_LAG24_PROMOTION.md"
POST_PAYOUT_DEFAULT_RISK_USD = 250.0


def build_candidates():
    baseline = build_config(
        timeframe="5m",
        direction_filter="long",
        entry_mode="fvg_limit",
        entry_start="08:30",
        entry_end="15:00",
        rr=3.0,
        tp1_ratio=0.6,
        min_gap_atr_pct=3.0,
        atr_length=14,
        htf_level_tf_minutes=60,
        htf_n_left=3,
        htf_trade_max_per_session=2,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=2,
        max_fvg_to_inversion_bars=0,
        name="NQ NY HTF_LSI 5m lag0 baseline",
    )
    lag24 = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI 5m lag24 lead",
    )
    return [
        {"label": baseline.name, "lag": 0, "config": baseline},
        {"label": lag24.name, "lag": 24, "config": lag24},
    ]


def build_config_summary(config) -> str:
    session = config.sessions[0]
    return (
        f"{config.direction_filter} {config.lsi_entry_mode} "
        f"{session.entry_start}-{session.entry_end} "
        f"rr{config.rr} tp{config.tp1_ratio} "
        f"gap{session.min_gap_atr_pct} "
        f"htf{config.htf_level_tf_minutes} n{config.htf_n_left} "
        f"cap{config.htf_trade_max_per_session} "
        f"fvgL{config.lsi_fvg_window_left} fvgR{config.lsi_fvg_window_right} "
        f"lag{config.max_fvg_to_inversion_bars}"
    )


def pick_best_risk(rows: list[dict]) -> dict:
    eligible = [
        row for row in rows
        if row["holdout_breach_rate"] == 0.0
        and row["oos_breach_rate"] <= 0.05
        and row["mc_survival_rate"] >= 0.50
    ]
    return max(
        eligible or rows,
        key=lambda row: (
            row["oos_avg_withdrawals_per_start"],
            row["holdout_avg_withdrawals_per_start"],
            row["mc_survival_rate"],
        ),
    )


def evaluate_candidate(
    *,
    candidate: dict,
    df_base: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_1s: pd.DataFrame,
    signal_df_1m: pd.DataFrame,
    maps: dict,
    signal_cache: dict,
    oos_dates: list[str],
    holdout_dates: list[str],
    holdout_end_exclusive: str,
) -> dict:
    config = candidate["config"]
    label = candidate["label"]

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

    oos_prop_outcomes = simulate_account_attempts(
        specialist_name=label,
        trades=trades_oos,
        trading_dates=oos_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=config.risk_usd,
    )
    oos_prop_scorecard = build_prop_scorecard(oos_prop_outcomes, PROP_PROFILE)
    oos_funded_outcomes = simulate_funded_first_payouts(
        specialist_name=label,
        trades=trades_oos,
        trading_dates=oos_dates,
        profile=FUNDED_PROFILE,
    )
    oos_funded_scorecard = build_funded_first_payout_scorecard(oos_funded_outcomes, FUNDED_PROFILE)
    oos_funded_forecast = build_funded_first_payout_forecast(oos_funded_outcomes)

    holdout_prop_outcomes = simulate_account_attempts(
        specialist_name=f"{label}_holdout",
        trades=trades_holdout,
        trading_dates=holdout_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=config.risk_usd,
    )
    holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
    holdout_funded_outcomes = simulate_funded_first_payouts(
        specialist_name=f"{label}_holdout",
        trades=trades_holdout,
        trading_dates=holdout_dates,
        profile=FUNDED_PROFILE,
    )
    holdout_funded_scorecard = build_funded_first_payout_scorecard(holdout_funded_outcomes, FUNDED_PROFILE)
    holdout_funded_forecast = build_funded_first_payout_forecast(holdout_funded_outcomes)
    phase_one_verdict = verdict_from_scorecards(oos_prop_scorecard, holdout_prop_scorecard)

    continuity_result = evaluate_constraints(trades_oos, CONTINUITY_CONSTRAINTS)
    oos_day_to_r = build_day_to_r(trades_oos)
    oos_week_ends = last_trading_days_of_week(oos_dates)
    oos_post_payout_outcomes = pd.DataFrame(
        [simulate_post_payout_start(start_date, oos_dates, oos_day_to_r, oos_week_ends) for start_date in oos_dates]
    )
    oos_post_payout_scorecard = build_post_payout_scorecard(oos_post_payout_outcomes)

    holdout_day_to_r = build_day_to_r(trades_holdout)
    holdout_week_ends = last_trading_days_of_week(holdout_dates)
    holdout_post_payout_outcomes = pd.DataFrame(
        [
            simulate_post_payout_start(start_date, holdout_dates, holdout_day_to_r, holdout_week_ends)
            for start_date in holdout_dates
        ]
    )
    holdout_post_payout_scorecard = build_post_payout_scorecard(holdout_post_payout_outcomes)

    mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)
    mc_result = run_monte_carlo(trades_oos, mc_config, ruin_threshold=-MC_RUIN_THRESHOLD_R)
    trade_dates = [trade.date for trade in trades_oos if trade.exit_type != EXIT_NO_FILL]
    mc_eval = evaluate_constraints_mc(mc_result, MC_CONSTRAINTS, trade_dates=trade_dates)

    phase_results = {
        "Phase 1: Structural": bool(
            pre_metrics.get("total_trades", 0) >= 100
            and pre_metrics.get("profit_factor", 0) > 1.0
            and pre_metrics.get("avg_r", 0) > 0.0
        ),
        "Phase 2: Walk-Forward": bool(
            oos_metrics.get("profit_factor", 0) > 1.0
            and oos_metrics.get("avg_r", 0) > 0.0
        ),
        "Phase 3: Continuity": phase_3_pass(continuity_result, oos_post_payout_scorecard),
        "Phase 4: Holdout": phase_4_pass(holdout_metrics, holdout_post_payout_scorecard),
        "Phase 5: Path-Risk": phase_5_pass(mc_eval, mc_result),
    }
    phase_two_verdict, phase_two_detail = verdict_from_phases(phase_results)

    risk_rows = []
    base_mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)
    for risk_usd in RISK_SWEEP:
        dd_threshold_r = 2000.0 / risk_usd
        oos_risk_outcomes = simulate_for_risk(
            risk_usd=risk_usd,
            all_dates=oos_dates,
            day_to_r=oos_day_to_r,
            week_ends=oos_week_ends,
        )
        holdout_risk_outcomes = simulate_for_risk(
            risk_usd=risk_usd,
            all_dates=holdout_dates,
            day_to_r=holdout_day_to_r,
            week_ends=holdout_week_ends,
        )
        oos_risk_scorecard = build_post_payout_scorecard(oos_risk_outcomes)
        holdout_risk_scorecard = build_post_payout_scorecard(holdout_risk_outcomes)
        risk_mc_result = run_monte_carlo(trades_oos, base_mc_config, ruin_threshold=-dd_threshold_r)
        mc_survival = 1.0 - float(risk_mc_result.ruin_probability)
        risk_rows.append(
            {
                "risk_post_usd": float(risk_usd),
                "oos_withdrawal_rate": float(oos_risk_scorecard["withdrawal_rate"]),
                "oos_breach_rate": float(oos_risk_scorecard["breach_rate"]),
                "oos_avg_withdrawals_per_start": float(oos_risk_scorecard["avg_total_withdrawals_per_start"]),
                "holdout_withdrawal_rate": float(holdout_risk_scorecard["withdrawal_rate"]),
                "holdout_breach_rate": float(holdout_risk_scorecard["breach_rate"]),
                "holdout_avg_withdrawals_per_start": float(holdout_risk_scorecard["avg_total_withdrawals_per_start"]),
                "mc_survival_rate": float(mc_survival),
                "mc_dd_threshold_r": float(dd_threshold_r),
                "mc_dd_p95_r": float(abs(risk_mc_result.max_dd_percentiles["p95"])),
            }
        )
    risk_rows.sort(key=lambda row: row["risk_post_usd"])
    best_risk_row = pick_best_risk(risk_rows)

    return {
        "name": label,
        "lag": int(candidate["lag"]),
        "config_summary": build_config_summary(config),
        "phase_one_verdict": phase_one_verdict,
        "phase_two_verdict": phase_two_verdict,
        "phase_two_detail": phase_two_detail,
        "phase_two_default_risk_usd": POST_PAYOUT_DEFAULT_RISK_USD,
        "pre_holdout_metrics": metrics_snapshot(pre_metrics),
        "oos_metrics": metrics_snapshot(oos_metrics),
        "holdout_metrics": metrics_snapshot(holdout_metrics),
        "oos_prop_scorecard": oos_prop_scorecard,
        "oos_funded_scorecard": oos_funded_scorecard,
        "oos_funded_forecast": oos_funded_forecast,
        "holdout_prop_scorecard": holdout_prop_scorecard,
        "holdout_funded_scorecard": holdout_funded_scorecard,
        "holdout_funded_forecast": holdout_funded_forecast,
        "phase_3": {
            "constraint_result": asdict(continuity_result),
        },
        "oos_post_payout_scorecard": oos_post_payout_scorecard,
        "holdout_post_payout_scorecard": holdout_post_payout_scorecard,
        "mc_result": {
            "ruin_probability": float(mc_result.ruin_probability),
            "ruin_threshold": float(mc_result.ruin_threshold),
            "max_dd_percentiles": {
                key: float(value) for key, value in mc_result.max_dd_percentiles.items()
            },
        },
        "mc_eval": mc_eval,
        "phase_results": phase_results,
        "risk_sweep": {
            "best_row": best_risk_row,
            "rows": risk_rows,
        },
    }


def compare_rows(baseline: dict, challenger: dict) -> dict:
    phase_one_delta = float(challenger["oos_funded_scorecard"]["ev_per_start_usd"]) - float(
        baseline["oos_funded_scorecard"]["ev_per_start_usd"]
    )
    holdout_delta = float(challenger["holdout_funded_scorecard"]["ev_per_start_usd"]) - float(
        baseline["holdout_funded_scorecard"]["ev_per_start_usd"]
    )
    phase_two_delta = float(
        challenger["oos_post_payout_scorecard"]["avg_total_withdrawals_per_start"]
    ) - float(baseline["oos_post_payout_scorecard"]["avg_total_withdrawals_per_start"])
    best_risk_delta = float(challenger["risk_sweep"]["best_row"]["oos_avg_withdrawals_per_start"]) - float(
        baseline["risk_sweep"]["best_row"]["oos_avg_withdrawals_per_start"]
    )
    return {
        "phase_one_oos_funded_ev_delta": round(phase_one_delta, 2),
        "phase_one_holdout_funded_ev_delta": round(holdout_delta, 2),
        "phase_two_default_withdrawals_delta": round(phase_two_delta, 2),
        "best_risk_oos_withdrawals_delta": round(best_risk_delta, 2),
    }


def write_report(payload: dict) -> None:
    baseline, challenger = payload["results"]
    lines = [
        "# NQ NY HTF-LSI Lag24 Promotion",
        "",
        "- Objective: compare the frozen `5m lag=0` lead against the `5m lag=24` late-lag challenger on the downstream promotion path only.",
        f"- Holdout: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "- Phase one model: standard 50k funded-account first-payout framework.",
        "- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.",
        "",
        "## Summary",
        "",
        (
            f"- Baseline `{baseline['name']}`: phase one `{baseline['phase_one_verdict']}`, "
            f"phase two `{baseline['phase_two_verdict']}`."
        ),
        (
            f"- Challenger `{challenger['name']}`: phase one `{challenger['phase_one_verdict']}`, "
            f"phase two `{challenger['phase_two_verdict']}`."
        ),
        "",
        "## Key Metrics",
        "",
        "| Candidate | Lag | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (baseline, challenger):
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | {row['lag']} | "
            f"{row['oos_metrics']['profit_factor']:.3f} | {row['oos_metrics']['avg_r']:.3f} | "
            f"{row['holdout_metrics']['profit_factor']:.3f} | {row['holdout_metrics']['avg_r']:.3f} | "
            f"${row['oos_funded_scorecard']['ev_per_start_usd']:.2f} | "
            f"${row['holdout_funded_scorecard']['ev_per_start_usd']:.2f} | "
            f"${row['oos_post_payout_scorecard']['avg_total_withdrawals_per_start']:.2f} | "
            f"${row['holdout_post_payout_scorecard']['avg_total_withdrawals_per_start']:.2f} | "
            f"{row['mc_eval']['survival_rate']:.1%} | "
            f"${int(best['risk_post_usd'])} |"
        )
    lines.extend(
        [
            "",
            "## Risk Sweep",
            "",
            "| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in (baseline, challenger):
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | ${int(best['risk_post_usd'])} | "
            f"${best['oos_avg_withdrawals_per_start']:.2f} | {best['oos_breach_rate']:.1%} | "
            f"${best['holdout_avg_withdrawals_per_start']:.2f} | {best['holdout_breach_rate']:.1%} | "
            f"{best['mc_survival_rate']:.1%} |"
        )
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("NQ NY HTF-LSI Lag24 Promotion", flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading NQ 5m HTF-LSI data...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print("Building maps + signal cache for both candidates...", flush=True)
    candidates = build_candidates()
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(
        df_base,
        [candidate["config"] for candidate in candidates],
        signal_df_1m=signal_df_1m,
    )

    from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402

    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start
    oos_dates = trading_dates_between(df_base, oos_start, HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    rows = []
    for candidate in candidates:
        print(f"\nEvaluating {candidate['label']}...", flush=True)
        rows.append(
            evaluate_candidate(
                candidate=candidate,
                df_base=df_base,
                df_1m=df_1m,
                df_1s=df_1s,
                signal_df_1m=signal_df_1m,
                maps=maps,
                signal_cache=signal_cache,
                oos_dates=oos_dates,
                holdout_dates=holdout_dates,
                holdout_end_exclusive=holdout_end_exclusive,
            )
        )

    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": (
                pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "phase_one_profile": {
                "funded": asdict(FUNDED_PROFILE),
                "prop": asdict(PROP_PROFILE),
            },
            "phase_two_model": {
                "start_balance_usd": POST_PAYOUT_START_BALANCE,
                "breach_balance_usd": POST_PAYOUT_BREACH_BALANCE,
                "risk_usd_per_r": POST_PAYOUT_DEFAULT_RISK_USD,
                "withdraw_trigger_usd": POST_PAYOUT_WITHDRAW_TRIGGER,
                "reset_balance_usd": POST_PAYOUT_RESET_BALANCE,
            },
            "risk_sweep": list(RISK_SWEEP),
        },
        "results": rows,
        "comparison": compare_rows(rows[0], rows[1]),
    }
    save_json(OUTPUT_DIR / "promotion_compare.json", payload)
    write_report(payload)

    print("\nComparison deltas:", flush=True)
    print(json.dumps(payload["comparison"], indent=2), flush=True)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
