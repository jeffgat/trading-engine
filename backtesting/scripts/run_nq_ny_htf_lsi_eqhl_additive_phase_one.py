#!/usr/bin/env python3
"""Phase-one head-to-head: current 5m lag24 lead vs additive EQHL challenger."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402
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
from run_nq_ny_htf_lsi_phase_one import (  # noqa: E402
    FUNDED_PROFILE,
    HOLDOUT_START,
    PROP_PROFILE,
    RESEARCH_START,
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


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_eqhl_additive_phase_one"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_EQHL_ADDITIVE_PHASE_ONE.md"
ADDITIVE_COMPARE_PATH = ROOT / "data" / "results" / "nq_ny_htf_lsi_eqhl_additive_compare" / "summary.json"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def build_candidates() -> list[dict]:
    lead = build_current_nq_ny_htf_lsi_lag24_config(name="NQ NY HTF_LSI 5m lag24 operating lead")
    additive = replace(
        lead,
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive challenger",
    )
    return [
        {"label": lead.name, "candidate_id": "htf_only", "config": lead},
        {"label": additive.name, "candidate_id": "htf_plus_eqhl_15m_tol1", "config": additive},
    ]


def config_summary(config) -> str:
    session = config.sessions[0]
    source = "htf_only"
    if config.htf_lsi_include_eqhl_levels:
        source = f"htf_plus_eqhl{config.eqhl_level_tf_minutes}m_tol{config.eqhl_tolerance_ticks}"
    return (
        f"{config.direction_filter} {config.lsi_entry_mode} {session.entry_start}-{session.entry_end} "
        f"rr{config.rr} tp{config.tp1_ratio} gap{session.min_gap_atr_pct} "
        f"htf{config.htf_level_tf_minutes} n{config.htf_n_left} cap{config.htf_trade_max_per_session} "
        f"fvgL{config.lsi_fvg_window_left} fvgR{config.lsi_fvg_window_right} "
        f"lag{config.max_fvg_to_inversion_bars} {source}"
    )


def load_additive_reference(candidate_id: str) -> dict | None:
    if not ADDITIVE_COMPARE_PATH.exists():
        return None
    rows = json.loads(ADDITIVE_COMPARE_PATH.read_text())
    for row in rows:
        if row.get("label") == candidate_id:
            return row
    return None


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

    verdict = verdict_from_scorecards(oos_prop_scorecard, holdout_prop_scorecard)
    additive_reference = load_additive_reference(candidate["candidate_id"])

    return {
        "name": label,
        "candidate_id": candidate["candidate_id"],
        "verdict": verdict,
        "config_summary": config_summary(config),
        "pre_holdout_metrics": metrics_snapshot(pre_metrics),
        "oos_metrics": metrics_snapshot(oos_metrics),
        "holdout_metrics": metrics_snapshot(holdout_metrics),
        "oos_prop_scorecard": oos_prop_scorecard,
        "oos_funded_scorecard": oos_funded_scorecard,
        "oos_funded_forecast": oos_funded_forecast,
        "holdout_prop_scorecard": holdout_prop_scorecard,
        "holdout_funded_scorecard": holdout_funded_scorecard,
        "holdout_funded_forecast": holdout_funded_forecast,
        "additive_compare_reference": {
            "wf_pf": round(float(additive_reference["wf_pf"]), 4),
            "wf_avg_r": round(float(additive_reference["wf_avg_r"]), 4),
            "wf_calmar": round(float(additive_reference["wf_calmar"]), 4),
            "validation_pf": round(float(additive_reference["validation_pf"]), 4),
            "validation_avg_r": round(float(additive_reference["validation_avg_r"]), 4),
            "validation_calmar": round(float(additive_reference["validation_calmar"]), 4),
        }
        if additive_reference
        else None,
    }


def compare_rows(base: dict, challenger: dict) -> dict:
    return {
        "oos_funded_ev_delta": round(
            float(challenger["oos_funded_scorecard"]["ev_per_start_usd"])
            - float(base["oos_funded_scorecard"]["ev_per_start_usd"]),
            2,
        ),
        "holdout_funded_ev_delta": round(
            float(challenger["holdout_funded_scorecard"]["ev_per_start_usd"])
            - float(base["holdout_funded_scorecard"]["ev_per_start_usd"]),
            2,
        ),
        "oos_payout_rate_delta": round(
            float(challenger["oos_funded_scorecard"]["payout_rate"])
            - float(base["oos_funded_scorecard"]["payout_rate"]),
            4,
        ),
        "holdout_payout_rate_delta": round(
            float(challenger["holdout_funded_scorecard"]["payout_rate"])
            - float(base["holdout_funded_scorecard"]["payout_rate"]),
            4,
        ),
        "oos_avg_days_delta": round(
            float(challenger["oos_funded_scorecard"]["average_days_to_payout"])
            - float(base["oos_funded_scorecard"]["average_days_to_payout"]),
            2,
        ),
        "holdout_avg_days_delta": round(
            float(challenger["holdout_funded_scorecard"]["average_days_to_payout"])
            - float(base["holdout_funded_scorecard"]["average_days_to_payout"]),
            2,
        ),
    }


def write_report(payload: dict) -> None:
    base, challenger = payload["results"]
    lines = [
        "# NQ NY HTF-LSI EQHL Additive Phase One",
        "",
        "- Objective: compare the current `5m lag24` operating lead against the frozen additive `HTF + 15m EQHL tol1` challenger on the one-time phase-one holdout path.",
        f"- Holdout opened here for the additive challenger: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "",
        "## Summary",
        "",
        f"- Base `{base['name']}`: verdict `{base['verdict']}`, OOS funded payout `{base['oos_funded_scorecard']['payout_rate']:.1%}`, holdout funded payout `{base['holdout_funded_scorecard']['payout_rate']:.1%}`, OOS EV/start `${base['oos_funded_scorecard']['ev_per_start_usd']:.2f}`, holdout EV/start `${base['holdout_funded_scorecard']['ev_per_start_usd']:.2f}`.",
        f"- Challenger `{challenger['name']}`: verdict `{challenger['verdict']}`, OOS funded payout `{challenger['oos_funded_scorecard']['payout_rate']:.1%}`, holdout funded payout `{challenger['holdout_funded_scorecard']['payout_rate']:.1%}`, OOS EV/start `${challenger['oos_funded_scorecard']['ev_per_start_usd']:.2f}`, holdout EV/start `${challenger['holdout_funded_scorecard']['ev_per_start_usd']:.2f}`.",
        "",
        "## Key Metrics",
        "",
        "| Candidate | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Payout | Holdout Payout | OOS Avg Days | Holdout Avg Days |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (base, challenger):
        lines.append(
            f"| {row['name']} | "
            f"{row['oos_metrics']['profit_factor']:.3f} | {row['oos_metrics']['avg_r']:.3f} | "
            f"{row['holdout_metrics']['profit_factor']:.3f} | {row['holdout_metrics']['avg_r']:.3f} | "
            f"${row['oos_funded_scorecard']['ev_per_start_usd']:.2f} | "
            f"${row['holdout_funded_scorecard']['ev_per_start_usd']:.2f} | "
            f"{row['oos_funded_scorecard']['payout_rate']:.1%} | "
            f"{row['holdout_funded_scorecard']['payout_rate']:.1%} | "
            f"{row['oos_funded_scorecard']['average_days_to_payout']:.1f} | "
            f"{row['holdout_funded_scorecard']['average_days_to_payout']:.1f} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    print("NQ NY HTF-LSI EQHL Additive Phase One", flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading NQ 5m data...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print("Building maps + signal cache...", flush=True)
    candidates = build_candidates()
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, [candidate["config"] for candidate in candidates], signal_df_1m=signal_df_1m)

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
        row = evaluate_candidate(
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
        rows.append(row)
        print_metrics("Pre-holdout", row["pre_holdout_metrics"])
        print_metrics("Combined OOS", row["oos_metrics"])
        print_metrics("Holdout", row["holdout_metrics"])
        print_scorecard("OOS funded", row["oos_funded_scorecard"])
        print_scorecard("Holdout funded", row["holdout_funded_scorecard"])

    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": (
                pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "funded_profile": asdict(FUNDED_PROFILE),
            "prop_profile": asdict(PROP_PROFILE),
            "additive_compare_source": str(ADDITIVE_COMPARE_PATH),
        },
        "results": rows,
        "comparison": compare_rows(rows[0], rows[1]),
    }

    write_json(OUTPUT_DIR / "phase_one_compare.json", payload)
    write_report(payload)
    print("\nComparison deltas:", flush=True)
    print(json.dumps(payload["comparison"], indent=2), flush=True)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
