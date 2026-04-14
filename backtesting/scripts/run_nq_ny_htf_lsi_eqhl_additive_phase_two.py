#!/usr/bin/env python3
"""Downstream phase-two comparison for NQ NY HTF-LSI base vs additive EQHL lead."""

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

from htf_lsi_common import (  # noqa: E402
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
    save_json,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache  # noqa: E402
from run_nq_ny_htf_lsi_lag24_promotion import compare_rows, evaluate_candidate  # noqa: E402
from run_nq_ny_htf_lsi_phase_one import (  # noqa: E402
    FUNDED_PROFILE,
    HOLDOUT_START,
    PROP_PROFILE,
    RESEARCH_START,
    WF_IS_MONTHS,
    WF_OOS_MONTHS,
    WF_STEP_MONTHS,
    trading_dates_between,
)
from run_nq_ny_htf_lsi_phase_two import (  # noqa: E402
    POST_PAYOUT_BREACH_BALANCE,
    POST_PAYOUT_RESET_BALANCE,
    POST_PAYOUT_START_BALANCE,
    POST_PAYOUT_WITHDRAW_TRIGGER,
)
from run_nq_ny_htf_lsi_phase_two_risk_sweep import RISK_SWEEP  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_eqhl_additive_phase_two"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_EQHL_ADDITIVE_PHASE_TWO.md"
POST_PAYOUT_DEFAULT_RISK_USD = 250.0


def build_candidates():
    base = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI 5m lag24 operating lead",
    )
    additive = replace(
        base,
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive challenger",
    )
    return [
        {
            "label": base.name,
            "lag": 24,
            "timeframe": "5m",
            "source_mode": "htf_only",
            "config": base,
        },
        {
            "label": additive.name,
            "lag": 24,
            "timeframe": "5m",
            "source_mode": "htf_plus_eqhl_15m_tol1",
            "config": additive,
        },
    ]


def write_report(payload: dict) -> None:
    base, challenger = payload["results"]
    lines = [
        "# NQ NY HTF-LSI EQHL Additive Phase Two",
        "",
        "- Objective: compare the current `5m lag24` HTF-only operating lead against the frozen additive `HTF + 15m EQHL tol1` challenger on the post-first-payout continuity path.",
        f"- Holdout: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "- Phase one model: standard 50k funded-account first-payout framework.",
        "- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.",
        "",
        "## Summary",
        "",
        (
            f"- Base `{base['name']}`: phase one `{base['phase_one_verdict']}`, "
            f"phase two `{base['phase_two_verdict']}`."
        ),
        (
            f"- Challenger `{challenger['name']}`: phase one `{challenger['phase_one_verdict']}`, "
            f"phase two `{challenger['phase_two_verdict']}`."
        ),
        "",
        "## Key Metrics",
        "",
        "| Candidate | Source | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (base, challenger):
        best = row["risk_sweep"]["best_row"]
        source = "HTF-only" if row["source_mode"] == "htf_only" else "HTF+EQHL 15m tol1"
        lines.append(
            f"| {row['name']} | {source} | "
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
    for row in (base, challenger):
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | ${int(best['risk_post_usd'])} | "
            f"${best['oos_avg_withdrawals_per_start']:.2f} | {best['oos_breach_rate']:.1%} | "
            f"${best['holdout_avg_withdrawals_per_start']:.2f} | {best['holdout_breach_rate']:.1%} | "
            f"{best['mc_survival_rate']:.1%} |"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    print("NQ NY HTF-LSI EQHL Additive Phase Two", flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = build_candidates()
    print("\nLoading 5m data...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print("Building maps + signal cache...", flush=True)
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
        row["timeframe"] = candidate["timeframe"]
        row["source_mode"] = candidate["source_mode"]
        rows.append(row)

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

    save_json(OUTPUT_DIR / "phase_two_compare.json", payload)
    write_report(payload)

    print("\nComparison deltas:", flush=True)
    print(json.dumps(payload["comparison"], indent=2), flush=True)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
