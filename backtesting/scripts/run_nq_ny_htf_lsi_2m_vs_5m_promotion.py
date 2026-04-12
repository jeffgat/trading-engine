#!/usr/bin/env python3
"""Downstream comparison for NQ NY HTF-LSI 2m anchor vs 5m lag24 lead."""

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


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_2m_vs_5m_promotion"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_2M_VS_5M_PROMOTION.md"
POST_PAYOUT_DEFAULT_RISK_USD = 250.0


def build_candidates():
    lead_5m = build_current_nq_ny_htf_lsi_lag24_config(
        name="NQ NY HTF_LSI 5m lag24 lead",
    )
    anchor_2m = build_config(
        timeframe="2m",
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
        htf_trade_max_per_session=1,
        lsi_fvg_window_left=50,
        lsi_fvg_window_right=5,
        max_fvg_to_inversion_bars=0,
        name="NQ NY HTF_LSI 2m anchor secondary branch",
    )
    return [
        {"label": lead_5m.name, "lag": 24, "timeframe": "5m", "config": lead_5m},
        {"label": anchor_2m.name, "lag": 0, "timeframe": "2m", "config": anchor_2m},
    ]


def write_report(payload: dict) -> None:
    lead, challenger = payload["results"]
    lines = [
        "# NQ NY HTF-LSI 2m vs 5m Promotion",
        "",
        "- Objective: compare the current `5m lag24` operating lead against the promoted `2m` secondary anchor on the same downstream path.",
        f"- Holdout: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "- Phase one model: standard 50k funded-account first-payout framework.",
        "- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.",
        "",
        "## Summary",
        "",
        (
            f"- Lead `{lead['name']}`: phase one `{lead['phase_one_verdict']}`, "
            f"phase two `{lead['phase_two_verdict']}`."
        ),
        (
            f"- Challenger `{challenger['name']}`: phase one `{challenger['phase_one_verdict']}`, "
            f"phase two `{challenger['phase_two_verdict']}`."
        ),
        "",
        "## Key Metrics",
        "",
        "| Candidate | TF | Lag | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in (lead, challenger):
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | {row['timeframe']} | {row['lag']} | "
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
    for row in (lead, challenger):
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | ${int(best['risk_post_usd'])} | "
            f"${best['oos_avg_withdrawals_per_start']:.2f} | {best['oos_breach_rate']:.1%} | "
            f"${best['holdout_avg_withdrawals_per_start']:.2f} | {best['holdout_breach_rate']:.1%} | "
            f"{best['mc_survival_rate']:.1%} |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("NQ NY HTF-LSI 2m vs 5m Promotion", flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = build_candidates()
    data_cache: dict[str, dict] = {}
    holdout_end_inclusive = None
    holdout_end_exclusive = None

    for timeframe in {candidate["timeframe"] for candidate in candidates}:
        print(f"\nLoading {timeframe} data...", flush=True)
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(timeframe)
        data_cache[timeframe] = {
            "df_base": df_base,
            "df_1m": df_1m,
            "df_1s": df_1s,
            "signal_df_1m": signal_df_1m,
            "maps": build_maps(df_base, df_1m=df_1m, df_1s=df_1s),
            "signal_cache": build_signal_cache(
                df_base,
                [candidate["config"] for candidate in candidates if candidate["timeframe"] == timeframe],
                signal_df_1m=signal_df_1m,
            ),
        }
        if holdout_end_inclusive is None:
            holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
            holdout_end_exclusive = (
                pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d")

    from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402

    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start

    rows = []
    for candidate in candidates:
        timeframe = candidate["timeframe"]
        cache = data_cache[timeframe]
        oos_dates = trading_dates_between(cache["df_base"], oos_start, HOLDOUT_START)
        holdout_dates = trading_dates_between(cache["df_base"], HOLDOUT_START, holdout_end_exclusive)
        print(f"\nEvaluating {candidate['label']}...", flush=True)
        row = evaluate_candidate(
            candidate=candidate,
            df_base=cache["df_base"],
            df_1m=cache["df_1m"],
            df_1s=cache["df_1s"],
            signal_df_1m=cache["signal_df_1m"],
            maps=cache["maps"],
            signal_cache=cache["signal_cache"],
            oos_dates=oos_dates,
            holdout_dates=holdout_dates,
            holdout_end_exclusive=holdout_end_exclusive,
        )
        row["timeframe"] = timeframe
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

    save_json(OUTPUT_DIR / "promotion_compare.json", payload)
    write_report(payload)

    print("\nComparison deltas:", flush=True)
    print(json.dumps(payload["comparison"], indent=2), flush=True)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
