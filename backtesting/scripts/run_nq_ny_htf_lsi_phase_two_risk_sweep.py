#!/usr/bin/env python3
"""Post-payout risk sweep for NQ NY HTF-LSI after phase-two continuity review."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import load_shortlist_config, load_timeframe_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, run_monte_carlo  # noqa: E402
from run_nq_ny_htf_lsi_phase_two import (  # noqa: E402
    HOLDOUT_START,
    RESEARCH_START,
    SHORTLIST_PATH,
    WF_IS_MONTHS,
    WF_OOS_MONTHS,
    WF_STEP_MONTHS,
    build_day_to_r,
    build_post_payout_scorecard,
    last_trading_days_of_week,
    reconstruct_combined_oos_trades,
    trading_dates_between,
)

OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_phase_two_risk_sweep"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_PHASE_TWO_RISK_SWEEP.md"

RISK_SWEEP = (100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0)
POST_PAYOUT_START_BALANCE = 52_000.0
POST_PAYOUT_BREACH_BALANCE = 50_000.0
POST_PAYOUT_WITHDRAW_TRIGGER = 52_500.0
POST_PAYOUT_RESET_BALANCE = 52_000.0


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def simulate_for_risk(
    *,
    risk_usd: float,
    all_dates: list[str],
    day_to_r: dict[str, float],
    week_ends: set[str],
) -> pd.DataFrame:
    rows = []
    for start_date in all_dates:
        balance = POST_PAYOUT_START_BALANCE
        breach = POST_PAYOUT_BREACH_BALANCE
        total_withdrawals = 0.0
        payout_count = 0
        outcome = "open"
        outcome_date = start_date
        first_withdrawal_date = None

        for date_str in all_dates:
            if date_str < start_date:
                continue

            day_r = day_to_r.get(date_str, 0.0)
            if day_r != 0.0:
                balance += day_r * risk_usd
                if balance <= breach:
                    outcome = "breach"
                    outcome_date = date_str
                    break

            if date_str in week_ends and balance >= POST_PAYOUT_WITHDRAW_TRIGGER:
                withdrawal = balance - POST_PAYOUT_RESET_BALANCE
                total_withdrawals += withdrawal
                payout_count += 1
                balance = POST_PAYOUT_RESET_BALANCE
                if first_withdrawal_date is None:
                    first_withdrawal_date = date_str

            outcome_date = date_str

        days_to_first_withdrawal = None
        if first_withdrawal_date is not None:
            days_to_first_withdrawal = (
                pd.Timestamp(first_withdrawal_date) - pd.Timestamp(start_date)
            ).days + 1

        row = {
            "start_date": start_date,
            "outcome": outcome,
            "outcome_date": outcome_date,
            "first_withdrawal_hit": payout_count > 0,
            "first_withdrawal_date": first_withdrawal_date,
            "days_to_first_withdrawal": days_to_first_withdrawal,
            "payout_count": payout_count,
            "total_withdrawals": round(total_withdrawals, 2),
            "ending_balance": round(balance, 2),
            "breach_balance": round(breach, 2),
            "calendar_days_active": (pd.Timestamp(outcome_date) - pd.Timestamp(start_date)).days + 1,
        }
        rows.append(row)
    return pd.DataFrame(rows)


def continuity_score(
    oos_scorecard: dict,
    holdout_scorecard: dict,
    mc_survival: float,
) -> float:
    return (
        oos_scorecard["avg_total_withdrawals_per_start"]
        + holdout_scorecard["avg_total_withdrawals_per_start"]
        + 1000.0 * mc_survival
        - 1000.0 * oos_scorecard["breach_rate"]
    )


def write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI Phase Two Risk Sweep",
        "",
        "- Objective: reduce post-payout path risk without reopening strategy discovery.",
        "- Model: weekly withdrawals above `$52,500` back to `$52,000` after first payout.",
        "",
        "## Summary",
        "",
    ]

    best = payload["best_row"]
    lines.append(
        f"- Best balanced post-payout risk in this sweep: `${best['risk_post_usd']}` with "
        f"OOS withdrawals/start `${best['oos_avg_withdrawals_per_start']}`, "
        f"holdout withdrawals/start `${best['holdout_avg_withdrawals_per_start']}`, "
        f"OOS breach `{best['oos_breach_rate']:.1%}`, holdout breach `{best['holdout_breach_rate']:.1%}`, "
        f"and MC survival `{best['mc_survival_rate']:.1%}` at `{best['mc_dd_threshold_r']:.1f}R`."
    )
    lines.extend(["", "## Grid", ""])
    lines.append("| Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival | MC DD p95 |")
    lines.append("| ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for row in sorted(payload["rows"], key=lambda item: item["risk_post_usd"]):
        lines.append(
            f"| ${int(row['risk_post_usd'])} | "
            f"${row['oos_avg_withdrawals_per_start']:.2f} | "
            f"{row['oos_breach_rate']:.1%} | "
            f"${row['holdout_avg_withdrawals_per_start']:.2f} | "
            f"{row['holdout_breach_rate']:.1%} | "
            f"{row['mc_survival_rate']:.1%} | "
            f"{row['mc_dd_p95_r']:.2f}R |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("NQ NY HTF-LSI Phase Two Risk Sweep", flush=True)
    print("=" * 72, flush=True)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = load_shortlist_config(SHORTLIST_PATH)

    print("\nLoading NQ 5m HTF-LSI data...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    print("Building maps + signal cache...", flush=True)
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
    oos_dates = trading_dates_between(df_base, oos_start, HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    print("Reconstructing stitched OOS + holdout trades...", flush=True)
    trades_oos = reconstruct_combined_oos_trades(
        df_base,
        df_1m,
        df_1s,
        signal_df_1m,
        maps,
        signal_cache,
        config,
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

    oos_day_to_r = build_day_to_r(trades_oos)
    holdout_day_to_r = build_day_to_r(trades_holdout)
    oos_week_ends = last_trading_days_of_week(oos_dates)
    holdout_week_ends = last_trading_days_of_week(holdout_dates)

    base_mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)
    rows = []
    for risk_usd in RISK_SWEEP:
        dd_threshold_r = 2000.0 / risk_usd

        oos_outcomes = simulate_for_risk(
            risk_usd=risk_usd,
            all_dates=oos_dates,
            day_to_r=oos_day_to_r,
            week_ends=oos_week_ends,
        )
        holdout_outcomes = simulate_for_risk(
            risk_usd=risk_usd,
            all_dates=holdout_dates,
            day_to_r=holdout_day_to_r,
            week_ends=holdout_week_ends,
        )
        oos_scorecard = build_post_payout_scorecard(oos_outcomes)
        holdout_scorecard = build_post_payout_scorecard(holdout_outcomes)

        mc_result = run_monte_carlo(trades_oos, base_mc_config, ruin_threshold=-dd_threshold_r)
        mc_survival = 1.0 - float(mc_result.ruin_probability)

        row = {
            "risk_post_usd": float(risk_usd),
            "oos_withdrawal_rate": float(oos_scorecard["withdrawal_rate"]),
            "oos_breach_rate": float(oos_scorecard["breach_rate"]),
            "oos_avg_withdrawals_per_start": float(oos_scorecard["avg_total_withdrawals_per_start"]),
            "holdout_withdrawal_rate": float(holdout_scorecard["withdrawal_rate"]),
            "holdout_breach_rate": float(holdout_scorecard["breach_rate"]),
            "holdout_avg_withdrawals_per_start": float(holdout_scorecard["avg_total_withdrawals_per_start"]),
            "mc_survival_rate": float(mc_survival),
            "mc_dd_threshold_r": float(dd_threshold_r),
            "mc_dd_p95_r": float(abs(mc_result.max_dd_percentiles["p95"])),
        }
        row["balance_score"] = continuity_score(oos_scorecard, holdout_scorecard, mc_survival)
        rows.append(row)

        print(
            f"  Risk ${int(risk_usd)} | "
            f"OOS ${oos_scorecard['avg_total_withdrawals_per_start']:.0f} / {oos_scorecard['breach_rate']:.1%} | "
            f"Holdout ${holdout_scorecard['avg_total_withdrawals_per_start']:.0f} / {holdout_scorecard['breach_rate']:.1%} | "
            f"MC {mc_survival:.1%} @ {dd_threshold_r:.1f}R",
            flush=True,
        )

    rows.sort(key=lambda row: row["balance_score"], reverse=True)
    eligible = [
        row for row in rows
        if row["holdout_breach_rate"] == 0.0
        and row["oos_breach_rate"] <= 0.05
        and row["mc_survival_rate"] >= 0.50
    ]
    best_row = max(
        eligible or rows,
        key=lambda row: (
            row["oos_avg_withdrawals_per_start"],
            row["holdout_avg_withdrawals_per_start"],
            row["mc_survival_rate"],
        ),
    )
    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": (
                pd.Timestamp(HOLDOUT_START).normalize() - pd.Timedelta(days=1)
            ).strftime("%Y-%m-%d"),
            "risk_sweep": list(RISK_SWEEP),
            "post_payout_model": {
                "start_balance_usd": POST_PAYOUT_START_BALANCE,
                "breach_balance_usd": POST_PAYOUT_BREACH_BALANCE,
                "withdraw_trigger_usd": POST_PAYOUT_WITHDRAW_TRIGGER,
                "reset_balance_usd": POST_PAYOUT_RESET_BALANCE,
            },
        },
        "best_row": best_row,
        "rows": rows,
    }

    write_json(OUTPUT_DIR / "risk_sweep.json", payload)
    write_report(payload)
    print(f"\nBest row: {best_row}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
