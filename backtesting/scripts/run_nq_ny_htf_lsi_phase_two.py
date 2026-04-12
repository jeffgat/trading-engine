#!/usr/bin/env python3
"""Phase-Two Robust Pipeline — NQ NY HTF-LSI frozen lead.

Evaluates the frozen 5m HTF-LSI anchor for post-first-payout continuity:
  1. Structural validation on full pre-holdout
  2. Reconstruct the stitched discovery walk-forward OOS stream
  3. Post-payout continuity filter on the stitched OOS stream
  4. Holdout continuity confirmation on 2025-04-01+
  5. Monte Carlo path-risk on the stitched OOS stream
"""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from htf_lsi_common import load_shortlist_config, load_timeframe_data  # noqa: E402
from orb_backtest.config import StrategyConfig  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.prop_constraints import (  # noqa: E402
    PropFirmConstraints,
    evaluate_constraints,
    evaluate_constraints_mc,
)
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, mc_result_to_dict, run_monte_carlo  # noqa: E402

SHORTLIST_PATH = ROOT / "data" / "results" / "nq_ny_htf_lsi_discovery" / "shortlist.json"
DISCOVERY_PACKET_PATH = (
    ROOT / "data" / "results" / "nq_ny_htf_lsi_discovery" / "stage_i_psr_dsr_holdout_manual.json"
)
PHASE_ONE_PACKET_PATH = ROOT / "data" / "results" / "nq_ny_htf_lsi_phase_one" / "phase_one_results.json"
PHASE_ONE_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_PHASE_ONE.md"

OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_phase_two"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_PHASE_TWO.md"

RESEARCH_START = "2016-01-01"
HOLDOUT_START = "2025-04-01"
WF_IS_MONTHS = 36
WF_OOS_MONTHS = 12
WF_STEP_MONTHS = 12

# Post-payout operating model: after first withdrawal the account sits at 52k
# with a fixed monetized breach line of 50k and weekly withdrawals above 52.5k.
POST_PAYOUT_START_BALANCE = 52_000.0
POST_PAYOUT_BREACH_BALANCE = 50_000.0
POST_PAYOUT_RISK_USD = 250.0
POST_PAYOUT_WITHDRAW_TRIGGER = 52_500.0
POST_PAYOUT_RESET_BALANCE = 52_000.0

CONTINUITY_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=12.0,
    min_annual_r=12.0,
    max_monthly_loss_r=5.0,
)
MC_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=8.0,
    min_annual_r=12.0,
    max_monthly_loss_r=5.0,
)
MC_RUIN_THRESHOLD_R = 8.0


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
    config: StrategyConfig,
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


def last_trading_days_of_week(all_dates: list[str]) -> set[str]:
    out: set[str] = set()
    for idx, date_str in enumerate(all_dates):
        current_week = pd.Timestamp(date_str).isocalendar()[:2]
        next_week = None
        if idx + 1 < len(all_dates):
            next_week = pd.Timestamp(all_dates[idx + 1]).isocalendar()[:2]
        if next_week != current_week:
            out.add(date_str)
    return out


def build_day_to_r(trades: list) -> dict[str, float]:
    day_to_r: dict[str, float] = defaultdict(float)
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            continue
        day_to_r[trade.date] += float(trade.r_multiple)
    return dict(day_to_r)


def simulate_post_payout_start(
    start_date: str,
    all_dates: list[str],
    day_to_r: dict[str, float],
    week_ends: set[str],
) -> dict:
    balance = POST_PAYOUT_START_BALANCE
    breach = POST_PAYOUT_BREACH_BALANCE
    total_withdrawals = 0.0
    payout_count = 0
    outcome = "open"
    outcome_date = start_date
    first_withdrawal_date: str | None = None

    for date_str in all_dates:
        if date_str < start_date:
            continue

        day_r = day_to_r.get(date_str, 0.0)
        if day_r != 0.0:
            balance += day_r * POST_PAYOUT_RISK_USD
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

    return {
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


def build_post_payout_scorecard(outcomes: pd.DataFrame) -> dict:
    if outcomes.empty:
        return {
            "total_starts": 0,
            "withdrawal_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "avg_total_withdrawals_per_start": 0.0,
            "median_total_withdrawals_given_withdrawal": None,
            "avg_payout_count_per_start": 0.0,
            "avg_payout_count_given_withdrawal": None,
            "average_days_to_first_withdrawal": None,
            "median_days_to_first_withdrawal": None,
            "average_calendar_days_active": None,
            "average_ending_balance_open": None,
        }

    withdrawals = outcomes[outcomes["first_withdrawal_hit"] == True].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    opens = outcomes[outcomes["outcome"] == "open"].copy()
    total = int(len(outcomes))

    return {
        "total_starts": total,
        "withdrawal_rate": round(len(withdrawals) / total, 4),
        "breach_rate": round(len(breaches) / total, 4),
        "open_rate": round(len(opens) / total, 4),
        "avg_total_withdrawals_per_start": round(float(outcomes["total_withdrawals"].mean()), 2),
        "median_total_withdrawals_given_withdrawal": (
            round(float(withdrawals["total_withdrawals"].median()), 2)
            if not withdrawals.empty else None
        ),
        "avg_payout_count_per_start": round(float(outcomes["payout_count"].mean()), 2),
        "avg_payout_count_given_withdrawal": (
            round(float(withdrawals["payout_count"].mean()), 2)
            if not withdrawals.empty else None
        ),
        "average_days_to_first_withdrawal": (
            round(float(withdrawals["days_to_first_withdrawal"].dropna().mean()), 2)
            if not withdrawals.empty and withdrawals["days_to_first_withdrawal"].notna().any() else None
        ),
        "median_days_to_first_withdrawal": (
            round(float(withdrawals["days_to_first_withdrawal"].dropna().median()), 2)
            if not withdrawals.empty and withdrawals["days_to_first_withdrawal"].notna().any() else None
        ),
        "average_calendar_days_active": round(float(outcomes["calendar_days_active"].mean()), 2),
        "average_ending_balance_open": (
            round(float(opens["ending_balance"].mean()), 2) if not opens.empty else None
        ),
    }


def print_post_payout_scorecard(label: str, scorecard: dict) -> None:
    print(f"\n  {label}", flush=True)
    print(
        f"    Starts: {scorecard['total_starts']} | "
        f"Withdrawal: {scorecard['withdrawal_rate']:.1%} | "
        f"Breach: {scorecard['breach_rate']:.1%} | "
        f"Open: {scorecard['open_rate']:.1%}",
        flush=True,
    )
    print(
        f"    Avg withdrawals/start: ${scorecard['avg_total_withdrawals_per_start']:.2f} | "
        f"Avg payout count/start: {scorecard['avg_payout_count_per_start']:.2f}",
        flush=True,
    )
    if scorecard["average_days_to_first_withdrawal"] is not None:
        print(
            f"    Avg days to first withdrawal: {scorecard['average_days_to_first_withdrawal']:.1f} | "
            f"Median: {scorecard['median_days_to_first_withdrawal']:.1f}",
            flush=True,
        )
    if scorecard["average_ending_balance_open"] is not None:
        print(
            f"    Avg ending balance of open starts: ${scorecard['average_ending_balance_open']:.2f}",
            flush=True,
        )


def phase_3_pass(constraint_result, continuity_scorecard: dict) -> bool:
    return bool(
        constraint_result.expectancy_passed
        and constraint_result.annual_r_passed
        and constraint_result.monthly_loss_passed
        and continuity_scorecard["avg_total_withdrawals_per_start"] > 0.0
        and continuity_scorecard["withdrawal_rate"] > continuity_scorecard["breach_rate"]
    )


def phase_4_pass(holdout_metrics: dict, continuity_scorecard: dict) -> bool:
    return bool(
        holdout_metrics.get("profit_factor", 0.0) > 1.0
        and holdout_metrics.get("avg_r", 0.0) > 0.0
        and continuity_scorecard["avg_total_withdrawals_per_start"] > 0.0
        and continuity_scorecard["withdrawal_rate"] >= continuity_scorecard["breach_rate"]
    )


def phase_5_pass(mc_eval: dict, mc_result) -> bool:
    survival = float(mc_eval.get("survival_rate", 0.0))
    ruin_prob = float(mc_result.ruin_probability)
    monthly_pass = float(mc_eval.get("monthly_loss_pass_rate", 0.0))
    return bool(survival >= 0.70 and ruin_prob < 0.10 and monthly_pass >= 0.60)


def verdict_from_phases(results: dict[str, bool]) -> tuple[str, str]:
    if all(results.values()):
        return "GO", "All five phases passed under the post-payout continuity model."

    p1_to_p4 = all(results[k] for k in list(results.keys())[:4])
    if p1_to_p4 and not results["Phase 5: Path-Risk"]:
        return "CONDITIONAL", "Core post-payout continuity passed, but Monte Carlo path risk stayed borderline."

    passed = sum(1 for ok in results.values() if ok)
    failed = ", ".join(name for name, ok in results.items() if not ok)
    if passed >= 3:
        return "CONDITIONAL", f"{passed}/5 phases passed; weak points were {failed}."
    return "NO-GO", f"{passed}/5 phases passed; failed phases were {failed}."


def write_report(payload: dict, holdout_end_inclusive: str) -> None:
    result = payload["result"]
    lines = [
        "# NQ NY HTF-LSI Phase Two",
        "",
        f"- Frozen phase-one source: [{PHASE_ONE_REPORT_PATH.name}]({PHASE_ONE_REPORT_PATH.as_posix()})",
        f"- Holdout opened once for phase two: `{HOLDOUT_START}` to `{holdout_end_inclusive}`.",
        "- Post-payout model: start from `$52,000`, fixed breach at `$50,000`, risk `$250/R`, and withdraw weekly above `$52,500` back to `$52,000`.",
        "",
        "## Summary",
        "",
        (
            f"- `{result['name']}`: verdict `{result['verdict']}`, "
            f"OOS withdrawal `{result['oos_post_payout_scorecard']['withdrawal_rate']:.1%}`, "
            f"OOS breach `{result['oos_post_payout_scorecard']['breach_rate']:.1%}`, "
            f"holdout withdrawal `{result['holdout_post_payout_scorecard']['withdrawal_rate']:.1%}`, "
            f"holdout breach `{result['holdout_post_payout_scorecard']['breach_rate']:.1%}`, "
            f"MC survival `{result['mc_eval']['survival_rate']:.1%}` at `{result['mc_eval']['dd_threshold']}R`"
        ),
        "",
        "## Candidate Details",
        "",
        f"### {result['name']}",
        "",
        f"- verdict: `{result['verdict']}`",
        f"- detail: {result['verdict_detail']}",
        f"- config: `{result['config_summary']}`",
        (
            f"- stitched OOS metrics: trades `{result['oos_metrics']['total_trades']}`, PF "
            f"`{result['oos_metrics']['profit_factor']}`, avgR `{result['oos_metrics']['avg_r']}`, "
            f"DD `{result['oos_metrics']['max_drawdown_r']}`"
        ),
        (
            f"- phase 3 continuity filter: DD pass `{result['phase_3']['constraint_result']['max_drawdown_passed']}`, "
            f"annual pass `{result['phase_3']['constraint_result']['annual_r_passed']}`, "
            f"monthly pass `{result['phase_3']['constraint_result']['monthly_loss_passed']}`, "
            f"expectancy `{result['phase_3']['constraint_result']['expectancy']}`"
        ),
        (
            f"- OOS post-payout scorecard: withdrawal `{result['oos_post_payout_scorecard']['withdrawal_rate']:.1%}`, "
            f"breach `{result['oos_post_payout_scorecard']['breach_rate']:.1%}`, "
            f"avg withdrawals/start `${result['oos_post_payout_scorecard']['avg_total_withdrawals_per_start']}`, "
            f"avg payout count/start `{result['oos_post_payout_scorecard']['avg_payout_count_per_start']}`"
        ),
        (
            f"- holdout metrics: trades `{result['holdout_metrics']['total_trades']}`, PF "
            f"`{result['holdout_metrics']['profit_factor']}`, avgR `{result['holdout_metrics']['avg_r']}`, "
            f"DD `{result['holdout_metrics']['max_drawdown_r']}`"
        ),
        (
            f"- holdout post-payout scorecard: withdrawal `{result['holdout_post_payout_scorecard']['withdrawal_rate']:.1%}`, "
            f"breach `{result['holdout_post_payout_scorecard']['breach_rate']:.1%}`, "
            f"avg withdrawals/start `${result['holdout_post_payout_scorecard']['avg_total_withdrawals_per_start']}`, "
            f"avg payout count/start `{result['holdout_post_payout_scorecard']['avg_payout_count_per_start']}`"
        ),
        (
            f"- phase 5 MC: survival `{result['mc_eval']['survival_rate']:.1%}` at "
            f"`{result['mc_eval']['dd_threshold']}R`, ruin `{result['mc_result']['ruin_probability']:.1%}`, "
            f"monthly pass `{result['mc_eval'].get('monthly_loss_pass_rate', 0.0):.1%}`, "
            f"annual pass `{result['mc_eval'].get('annual_r_pass_rate', 0.0):.1%}`"
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("Phase-Two Robust Pipeline — NQ NY HTF-LSI", flush=True)
    print("=" * 72, flush=True)

    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    config = load_shortlist_config(SHORTLIST_PATH)
    discovery_packet = json.loads(DISCOVERY_PACKET_PATH.read_text())
    phase_one_packet = json.loads(PHASE_ONE_PACKET_PATH.read_text())
    shortlist_payload = json.loads(SHORTLIST_PATH.read_text())
    leader_row = shortlist_payload[0] if isinstance(shortlist_payload, list) else shortlist_payload

    print("\n[Phase 0] Model freeze", flush=True)
    print(f"  Frozen candidate: {leader_row['label']}", flush=True)
    print(f"  Holdout start: {HOLDOUT_START}", flush=True)
    print(
        f"  Post-payout model: start ${POST_PAYOUT_START_BALANCE:,.0f}, "
        f"breach ${POST_PAYOUT_BREACH_BALANCE:,.0f}, risk ${POST_PAYOUT_RISK_USD:,.0f}/R, "
        f"weekly withdraw above ${POST_PAYOUT_WITHDRAW_TRIGGER:,.0f}",
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

    results: dict[str, bool] = {}

    print("\n[Phase 1] Structural validation", flush=True)
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
    phase_1_ok = bool(
        pre_metrics.get("total_trades", 0) >= 100
        and pre_metrics.get("profit_factor", 0) > 1.0
        and pre_metrics.get("avg_r", 0) > 0.0
    )
    print(f"  Phase 1 verdict: {'PASS' if phase_1_ok else 'FAIL'}", flush=True)
    results["Phase 1: Structural"] = phase_1_ok

    print("\n[Phase 2] Rolling walk-forward", flush=True)
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
        f"  Discovery packet: PSR {discovery_packet['walkforward_oos']['psr']['psr']:.4f} | "
        f"DSR {discovery_packet['walkforward_oos']['dsr']['dsr']:.4f}",
        flush=True,
    )
    phase_2_ok = bool(
        oos_metrics.get("profit_factor", 0.0) > 1.0
        and oos_metrics.get("avg_r", 0.0) > 0.0
        and discovery_packet["walkforward_oos"]["psr"]["psr"] >= 0.95
        and discovery_packet["walkforward_oos"]["dsr"]["dsr"] >= 0.70
    )
    print(f"  Phase 2 verdict: {'PASS' if phase_2_ok else 'FAIL'}", flush=True)
    results["Phase 2: Walk-Forward"] = phase_2_ok

    print("\n[Phase 3] Post-payout continuity filter", flush=True)
    continuity_result = evaluate_constraints(trades_oos, CONTINUITY_CONSTRAINTS)
    print(
        f"  Constraints: DD {continuity_result.max_drawdown_r:.2f}R | "
        f"Worst month {continuity_result.worst_month_r:.2f}R | "
        f"Expectancy {continuity_result.expectancy:.4f} | "
        f"Max consec losses {continuity_result.max_consecutive_losses}",
        flush=True,
    )
    oos_day_to_r = build_day_to_r(trades_oos)
    oos_week_ends = last_trading_days_of_week(oos_dates)
    oos_post_payout_outcomes = pd.DataFrame(
        [simulate_post_payout_start(start_date, oos_dates, oos_day_to_r, oos_week_ends) for start_date in oos_dates]
    )
    oos_post_payout_scorecard = build_post_payout_scorecard(oos_post_payout_outcomes)
    print_post_payout_scorecard("OOS post-payout extraction", oos_post_payout_scorecard)
    phase_3_ok = phase_3_pass(continuity_result, oos_post_payout_scorecard)
    print(f"  Phase 3 verdict: {'PASS' if phase_3_ok else 'FAIL'}", flush=True)
    results["Phase 3: Continuity"] = phase_3_ok

    print("\n[Phase 4] Holdout continuity confirmation", flush=True)
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
    holdout_day_to_r = build_day_to_r(trades_holdout)
    holdout_week_ends = last_trading_days_of_week(holdout_dates)
    holdout_post_payout_outcomes = pd.DataFrame(
        [
            simulate_post_payout_start(start_date, holdout_dates, holdout_day_to_r, holdout_week_ends)
            for start_date in holdout_dates
        ]
    )
    holdout_post_payout_scorecard = build_post_payout_scorecard(holdout_post_payout_outcomes)
    print_post_payout_scorecard("Holdout post-payout extraction", holdout_post_payout_scorecard)
    phase_4_ok = phase_4_pass(holdout_metrics, holdout_post_payout_scorecard)
    print(f"  Phase 4 verdict: {'PASS' if phase_4_ok else 'FAIL'}", flush=True)
    results["Phase 4: Holdout"] = phase_4_ok

    print("\n[Phase 5] Monte Carlo path-risk", flush=True)
    mc_config = MonteCarloConfig(
        n_simulations=2000,
        method="block_bootstrap",
        seed=42,
    )
    mc_result = run_monte_carlo(trades_oos, mc_config, ruin_threshold=-MC_RUIN_THRESHOLD_R)
    trade_dates = [trade.date for trade in trades_oos if trade.exit_type != EXIT_NO_FILL]
    mc_eval = evaluate_constraints_mc(mc_result, MC_CONSTRAINTS, trade_dates=trade_dates)
    print(
        f"  Survival at {mc_eval['dd_threshold']}R: {mc_eval['survival_rate']:.1%} | "
        f"Ruin: {mc_result.ruin_probability:.1%} | "
        f"Monthly pass: {mc_eval.get('monthly_loss_pass_rate', 0.0):.1%} | "
        f"Annual pass: {mc_eval.get('annual_r_pass_rate', 0.0):.1%}",
        flush=True,
    )
    print(f"  DD percentiles: {mc_eval['dd_percentiles']}", flush=True)
    phase_5_ok = phase_5_pass(mc_eval, mc_result)
    print(f"  Phase 5 verdict: {'PASS' if phase_5_ok else 'FAIL'}", flush=True)
    results["Phase 5: Path-Risk"] = phase_5_ok

    verdict, verdict_detail = verdict_from_phases(results)
    print("\nFINAL SUMMARY", flush=True)
    print("=" * 72, flush=True)
    for phase_name, ok in results.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {phase_name}", flush=True)
    print(f"\n  VERDICT: {verdict}", flush=True)
    print(f"  Detail: {verdict_detail}", flush=True)

    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_inclusive": oos_end_inclusive,
            "shortlist_source": str(SHORTLIST_PATH),
            "discovery_packet_source": str(DISCOVERY_PACKET_PATH),
            "phase_one_packet_source": str(PHASE_ONE_PACKET_PATH),
            "post_payout_model": {
                "start_balance_usd": POST_PAYOUT_START_BALANCE,
                "breach_balance_usd": POST_PAYOUT_BREACH_BALANCE,
                "risk_usd_per_r": POST_PAYOUT_RISK_USD,
                "withdraw_trigger_usd": POST_PAYOUT_WITHDRAW_TRIGGER,
                "reset_balance_usd": POST_PAYOUT_RESET_BALANCE,
            },
            "continuity_constraints": asdict(CONTINUITY_CONSTRAINTS),
            "mc_constraints": asdict(MC_CONSTRAINTS),
            "mc_ruin_threshold_r": MC_RUIN_THRESHOLD_R,
        },
        "candidate": leader_row,
        "result": {
            "name": leader_row["label"],
            "verdict": verdict,
            "verdict_detail": verdict_detail,
            "config_summary": (
                f"{leader_row['direction_filter']} {leader_row['entry_mode']} "
                f"{leader_row['entry_start']}-{leader_row['entry_end']} "
                f"rr{leader_row['rr']} tp{leader_row['tp1_ratio']} "
                f"gap{leader_row['min_gap_atr_pct']} htf{leader_row['htf_level_tf_minutes']} "
                f"n{leader_row['htf_n_left']} cap{leader_row['htf_trade_max_per_session']} "
                f"fvgL{leader_row['lsi_fvg_window_left']} fvgR{leader_row['lsi_fvg_window_right']}"
            ),
            "phase_results": results,
            "discovery_psr": discovery_packet["pre_holdout_full"]["psr"]["psr"],
            "discovery_dsr": discovery_packet["pre_holdout_full"]["dsr"]["dsr"],
            "phase_one_verdict": phase_one_packet["result"]["verdict"],
            "pre_holdout_metrics": metrics_snapshot(pre_metrics),
            "oos_metrics": metrics_snapshot(oos_metrics),
            "holdout_metrics": metrics_snapshot(holdout_metrics),
            "phase_3": {
                "constraint_result": asdict(continuity_result),
            },
            "oos_post_payout_scorecard": oos_post_payout_scorecard,
            "holdout_post_payout_scorecard": holdout_post_payout_scorecard,
            "mc_result": mc_result_to_dict(mc_result),
            "mc_eval": mc_eval,
        },
    }

    write_json(OUTPUT_DIR / "phase_two_results.json", payload)
    write_report(payload, holdout_end_inclusive)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
