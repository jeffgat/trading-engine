#!/usr/bin/env python3
"""Downstream compare for the additive HTF lead vs promoted wide-EQHL branches."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, save_json  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from run_cross_asset_eqhl_lsi_broad_discovery import (  # noqa: E402
    build_config as build_eqhl_config,
    load_timeframe_data as load_eqhl_timeframe_data,
)
from run_nq_ny_htf_lsi_lag24_promotion import evaluate_candidate  # noqa: E402
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


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_eqhl_wide_branches_downstream_compare"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_EQHL_WIDE_BRANCHES_DOWNSTREAM_COMPARE.md"
POST_PAYOUT_DEFAULT_RISK_USD = 250.0
SYMBOL = "NQ"


def build_candidates() -> list[dict]:
    additive_base = replace(
        build_current_nq_ny_htf_lsi_lag24_config(
            name="NQ NY HTF_LSI 5m lag24 operating lead",
        ),
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        name="NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead",
    )

    eqhl_5m = replace(
        build_eqhl_config(
            symbol=SYMBOL,
            timeframe="5m",
            eqhl_tf_minutes=5,
            eqhl_tolerance_ticks=20,
            tolerance_label="5p",
            eqhl_min_touches=2,
            direction_filter="long",
            entry_mode="fvg_limit",
            entry_end="13:00",
            rr=2.75,
            tp1_ratio=0.6,
            min_gap_atr_pct=3.0,
            atr_length=14,
            eqhl_n_left=2,
            eqhl_lookback_bars=48,
            left_minutes=80,
            right_minutes=10,
            min_stop_points=0.0,
            min_tp1_points=0.0,
        ),
        name="NQ NY EQHL_LSI 5m eqhl5m tol5p lead",
    )

    eqhl_1m = replace(
        build_eqhl_config(
            symbol=SYMBOL,
            timeframe="1m",
            eqhl_tf_minutes=60,
            eqhl_tolerance_ticks=60,
            tolerance_label="15p",
            eqhl_min_touches=2,
            direction_filter="long",
            entry_mode="fvg_limit",
            entry_end="15:00",
            rr=3.0,
            tp1_ratio=0.5,
            min_gap_atr_pct=3.0,
            atr_length=14,
            eqhl_n_left=2,
            eqhl_lookback_bars=48,
            left_minutes=100,
            right_minutes=12,
            min_stop_points=0.0,
            min_tp1_points=0.0,
        ),
        name="NQ NY EQHL_LSI 1m eqhl60m tol15p lead",
    )

    eqhl_3m = replace(
        build_eqhl_config(
            symbol=SYMBOL,
            timeframe="3m",
            eqhl_tf_minutes=15,
            eqhl_tolerance_ticks=60,
            tolerance_label="15p",
            eqhl_min_touches=2,
            direction_filter="long",
            entry_mode="fvg_limit",
            entry_end="13:00",
            rr=2.75,
            tp1_ratio=0.5,
            min_gap_atr_pct=3.0,
            atr_length=14,
            eqhl_n_left=2,
            eqhl_lookback_bars=48,
            left_minutes=81,
            right_minutes=12,
            min_stop_points=0.0,
            min_tp1_points=0.0,
        ),
        name="NQ NY EQHL_LSI 3m eqhl15m tol15p lead",
    )

    return [
        {
            "label": additive_base.name,
            "lag": 24,
            "timeframe": "5m",
            "family": "htf_plus_eqhl_15m_tol1",
            "config": additive_base,
        },
        {
            "label": eqhl_5m.name,
            "lag": 0,
            "timeframe": "5m",
            "family": "eqhl_5m_to_5m_5pt",
            "config": eqhl_5m,
        },
        {
            "label": eqhl_1m.name,
            "lag": 0,
            "timeframe": "1m",
            "family": "eqhl_1m_to_60m_15pt",
            "config": eqhl_1m,
        },
        {
            "label": eqhl_3m.name,
            "lag": 0,
            "timeframe": "3m",
            "family": "eqhl_3m_to_15m_15pt",
            "config": eqhl_3m,
        },
    ]


def build_bundle(timeframe: str, configs: list) -> dict:
    df_base, signal_df_1m, df_1s = load_eqhl_timeframe_data(SYMBOL, timeframe)
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start
    maps = build_maps(df_base, df_1m=signal_df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)
    return {
        "df_base": df_base,
        "df_1m": signal_df_1m,
        "df_1s": df_1s,
        "signal_df_1m": signal_df_1m,
        "maps": maps,
        "signal_cache": signal_cache,
        "holdout_end_inclusive": holdout_end_inclusive,
        "holdout_end_exclusive": holdout_end_exclusive,
        "oos_start": oos_start,
        "oos_dates": trading_dates_between(df_base, oos_start, HOLDOUT_START),
        "holdout_dates": trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive),
    }


def verdict_sort_key(row: dict) -> tuple:
    phase_one_order = {"STRONG": 0, "CONDITIONAL": 1, "WEAK": 2, "FAIL": 3}
    phase_two_order = {"GO": 0, "CONDITIONAL": 1, "NO-GO": 2, "NO_GO": 2, "FAIL": 3}
    return (
        phase_one_order.get(row["phase_one_verdict"], 9),
        phase_two_order.get(row["phase_two_verdict"], 9),
        -float(row["oos_funded_scorecard"]["ev_per_start_usd"]),
        -float(row["oos_post_payout_scorecard"]["avg_total_withdrawals_per_start"]),
        -float(row["risk_sweep"]["best_row"]["oos_avg_withdrawals_per_start"]),
        -float(row["oos_metrics"]["profit_factor"]),
    )


def summarize_winners(rows: list[dict]) -> dict:
    return {
        "phase_one_oos_funded_ev": max(rows, key=lambda row: row["oos_funded_scorecard"]["ev_per_start_usd"])["name"],
        "phase_one_holdout_funded_ev": max(
            rows, key=lambda row: row["holdout_funded_scorecard"]["ev_per_start_usd"]
        )["name"],
        "phase_two_default_withdrawals": max(
            rows, key=lambda row: row["oos_post_payout_scorecard"]["avg_total_withdrawals_per_start"]
        )["name"],
        "phase_two_best_risk_withdrawals": max(
            rows, key=lambda row: row["risk_sweep"]["best_row"]["oos_avg_withdrawals_per_start"]
        )["name"],
    }


def compare_vs_anchor(anchor: dict, rows: list[dict]) -> list[dict]:
    comparisons = []
    for row in rows:
        comparisons.append(
            {
                "name": row["name"],
                "family": row["family"],
                "phase_one_oos_funded_ev_delta": round(
                    float(row["oos_funded_scorecard"]["ev_per_start_usd"])
                    - float(anchor["oos_funded_scorecard"]["ev_per_start_usd"]),
                    2,
                ),
                "phase_one_holdout_funded_ev_delta": round(
                    float(row["holdout_funded_scorecard"]["ev_per_start_usd"])
                    - float(anchor["holdout_funded_scorecard"]["ev_per_start_usd"]),
                    2,
                ),
                "phase_two_default_withdrawals_delta": round(
                    float(row["oos_post_payout_scorecard"]["avg_total_withdrawals_per_start"])
                    - float(anchor["oos_post_payout_scorecard"]["avg_total_withdrawals_per_start"]),
                    2,
                ),
                "best_risk_oos_withdrawals_delta": round(
                    float(row["risk_sweep"]["best_row"]["oos_avg_withdrawals_per_start"])
                    - float(anchor["risk_sweep"]["best_row"]["oos_avg_withdrawals_per_start"]),
                    2,
                ),
            }
        )
    return comparisons


def write_report(payload: dict) -> None:
    rows = payload["results"]
    anchor_name = payload["anchor_name"]
    lines = [
        "# NQ NY Wide-EQHL Branches Downstream Compare",
        "",
        "- Objective: compare the current additive `5m lag24 + 15m EQHL tol1` operating lead against the promoted wide-tolerance standalone EQHL challengers on the downstream phase-one and phase-two path.",
        f"- Holdout: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "- Phase one model: standard 50k funded-account first-payout framework.",
        "- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.",
        "",
        "## Winner Snapshot",
        "",
        f"- Highest stitched-OOS funded EV: `{payload['winners']['phase_one_oos_funded_ev']}`.",
        f"- Highest holdout funded EV: `{payload['winners']['phase_one_holdout_funded_ev']}`.",
        f"- Highest default post-payout stitched-OOS withdrawals: `{payload['winners']['phase_two_default_withdrawals']}`.",
        f"- Highest best-risk stitched-OOS withdrawals: `{payload['winners']['phase_two_best_risk_withdrawals']}`.",
        "",
        "## Scorecard",
        "",
        "| Candidate | Family | TF | Phase 1 | Phase 2 | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Best Risk | MC Survival @250 |",
        "| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | {row['family']} | {row['timeframe']} | "
            f"{row['phase_one_verdict']} | {row['phase_two_verdict']} | "
            f"{row['oos_metrics']['profit_factor']:.3f} | {row['oos_metrics']['avg_r']:.3f} | "
            f"{row['holdout_metrics']['profit_factor']:.3f} | {row['holdout_metrics']['avg_r']:.3f} | "
            f"${row['oos_funded_scorecard']['ev_per_start_usd']:.2f} | "
            f"${row['holdout_funded_scorecard']['ev_per_start_usd']:.2f} | "
            f"${row['oos_post_payout_scorecard']['avg_total_withdrawals_per_start']:.2f} | "
            f"${int(best['risk_post_usd'])} | "
            f"{row['mc_eval']['survival_rate']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Delta Vs Additive Anchor",
            "",
            f"- Anchor: `{anchor_name}`.",
            "",
            "| Candidate | OOS Funded EV Delta | Holdout Funded EV Delta | Default OOS Withdraw Delta | Best-Risk OOS Withdraw Delta |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["comparisons_vs_anchor"]:
        if row["name"] == anchor_name:
            continue
        lines.append(
            f"| {row['name']} | ${row['phase_one_oos_funded_ev_delta']:.2f} | "
            f"${row['phase_one_holdout_funded_ev_delta']:.2f} | "
            f"${row['phase_two_default_withdrawals_delta']:.2f} | "
            f"${row['best_risk_oos_withdrawals_delta']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Best-Risk Rows",
            "",
            "| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in rows:
        best = row["risk_sweep"]["best_row"]
        lines.append(
            f"| {row['name']} | ${int(best['risk_post_usd'])} | "
            f"${best['oos_avg_withdrawals_per_start']:.2f} | {best['oos_breach_rate']:.1%} | "
            f"${best['holdout_avg_withdrawals_per_start']:.2f} | {best['holdout_breach_rate']:.1%} | "
            f"{best['mc_survival_rate']:.1%} |"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    print("NQ NY Wide-EQHL Branches Downstream Compare", flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    candidates = build_candidates()
    bundles: dict[str, dict] = {}
    for timeframe in sorted({candidate["timeframe"] for candidate in candidates}):
        tf_candidates = [candidate["config"] for candidate in candidates if candidate["timeframe"] == timeframe]
        print(f"\nLoading {timeframe} data...", flush=True)
        bundles[timeframe] = build_bundle(timeframe, tf_candidates)

    holdout_end_inclusive = bundles["5m"]["holdout_end_inclusive"]
    rows = []
    for candidate in candidates:
        bundle = bundles[candidate["timeframe"]]
        print(f"\nEvaluating {candidate['label']}...", flush=True)
        row = evaluate_candidate(
            candidate=candidate,
            df_base=bundle["df_base"],
            df_1m=bundle["df_1m"],
            df_1s=bundle["df_1s"],
            signal_df_1m=bundle["signal_df_1m"],
            maps=bundle["maps"],
            signal_cache=bundle["signal_cache"],
            oos_dates=bundle["oos_dates"],
            holdout_dates=bundle["holdout_dates"],
            holdout_end_exclusive=bundle["holdout_end_exclusive"],
        )
        row["timeframe"] = candidate["timeframe"]
        row["family"] = candidate["family"]
        rows.append(row)

    rows = sorted(rows, key=verdict_sort_key)
    anchor = next(row for row in rows if row["family"] == "htf_plus_eqhl_15m_tol1")
    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": bundles["5m"]["oos_start"],
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
        "anchor_name": anchor["name"],
        "winners": summarize_winners(rows),
        "comparisons_vs_anchor": compare_vs_anchor(anchor, rows),
    }

    save_json(OUTPUT_DIR / "downstream_compare.json", payload)
    write_report(payload)

    print("\nWinner snapshot:", flush=True)
    print(json.dumps(payload["winners"], indent=2), flush=True)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
