#!/usr/bin/env python3
"""Execution-friction robustness test for the live NQ NY HTF-LSI lag24 profile.

Method:
- Replay the exact live execution profile `HTF_LSI_5M_LAG24`
- Keep same-bar luck honest by using the live engine itself as the base stream
- Apply adverse execution overlays to the filled trades:
  - per-side slippage in ticks on every trade
  - random missed fills to approximate queue / latency misses
- Recompute trade metrics plus funded/post-payout scorecards on:
  - pre-holdout (`2019-01-01` -> `2025-03-31`)
  - holdout (`2025-04-01` -> exact latest common NQ date)

Important caveat:
- The engine does not currently model causal spread / queue position / delayed
  fills directly, so the missed-fill component is a Monte Carlo overlay rather
  than a structural replay parameter.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import date as dt_date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.historical_backtest import _compute_summary, latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, INSTRUMENTS, SIGNAL_TO_EXEC, load_config  # noqa: E402


PROFILE_NAME = "HTF_LSI_5M_LAG24"
SIGNAL_SYMBOL = "NQ"
EXEC_SYMBOL = SIGNAL_TO_EXEC[SIGNAL_SYMBOL]
MIN_TICK = float(INSTRUMENTS[EXEC_SYMBOL]["min_tick"])
POINT_VALUE = float(INSTRUMENTS[EXEC_SYMBOL]["point_value"])

FULL_START = "2019-01-01"
PRE_HOLDOUT_END = "2025-03-31"
HOLDOUT_START = "2025-04-01"

CHALLENGE_FEE = 100.0
START_BALANCE = 50_000.0
INITIAL_BREACH = 48_000.0
TRAILING_DD = 2_000.0
MAX_BREACH = 50_000.0
WITHDRAW_TRIGGER = 52_500.0
RESET_BALANCE = 52_000.0

MONTE_CARLO_RUNS = 400

OUTPUT_DIR = ROOT / "backtesting" / "data" / "results" / "nq_ny_htf_lsi_execution_robustness"
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "NQ_NY_HTF_LSI_EXECUTION_ROBUSTNESS.md"


@dataclass(frozen=True)
class Scenario:
    name: str
    slippage_ticks_per_side: int
    miss_rate: float
    monte_carlo_runs: int


SCENARIOS = (
    Scenario("baseline_exact", 0, 0.00, 1),
    Scenario("slip_1t_side", 1, 0.00, 1),
    Scenario("slip_2t_side", 2, 0.00, 1),
    Scenario("slip_1t_side__miss_5pct", 1, 0.05, MONTE_CARLO_RUNS),
    Scenario("slip_2t_side__miss_10pct", 2, 0.10, MONTE_CARLO_RUNS),
    Scenario("slip_3t_side__miss_15pct", 3, 0.15, MONTE_CARLO_RUNS),
)


def _day_to_pnl(trades: list[dict]) -> dict[str, float]:
    daily: dict[str, float] = defaultdict(float)
    for trade in trades:
        daily[str(trade["date"])] += float(trade["pnl_usd"])
    return dict(daily)


def _week_end_dates(all_dates: list[str]) -> set[str]:
    result: set[str] = set()
    for idx, date_str in enumerate(all_dates):
        current_week = dt_date.fromisoformat(date_str).isocalendar()[:2]
        next_week = None
        if idx + 1 < len(all_dates):
            next_week = dt_date.fromisoformat(all_dates[idx + 1]).isocalendar()[:2]
        if next_week != current_week:
            result.add(date_str)
    return result


def simulate_first_payout(day_to_pnl: dict[str, float], all_dates: list[str]) -> pd.DataFrame:
    rows = []
    for start_date in all_dates:
        balance = START_BALANCE
        highest_eod = START_BALANCE
        breach = INITIAL_BREACH
        outcome = "open"
        outcome_date = start_date
        trades_taken = 0

        for date_str in all_dates:
            if date_str < start_date:
                continue
            day_pnl = float(day_to_pnl.get(date_str, 0.0))
            if day_pnl != 0.0:
                balance += day_pnl
                trades_taken += 1
                if balance <= breach:
                    outcome = "breach"
                    outcome_date = date_str
                    break
            if balance >= WITHDRAW_TRIGGER:
                outcome = "payout"
                outcome_date = date_str
                break
            highest_eod = max(highest_eod, balance)
            breach = min(highest_eod - TRAILING_DD, MAX_BREACH)
            outcome_date = date_str

        if outcome == "payout":
            first_payout_amount = WITHDRAW_TRIGGER - RESET_BALANCE
            net_after_fee = first_payout_amount - CHALLENGE_FEE
        else:
            first_payout_amount = 0.0
            net_after_fee = -CHALLENGE_FEE

        rows.append(
            {
                "start_date": start_date,
                "outcome": outcome,
                "outcome_date": outcome_date,
                "first_payout_amount_usd": round(first_payout_amount, 2),
                "net_after_fee_usd": round(net_after_fee, 2),
                "calendar_days_to_outcome": (
                    dt_date.fromisoformat(outcome_date) - dt_date.fromisoformat(start_date)
                ).days + 1,
                "trading_days_to_outcome": sum(1 for d in all_dates if start_date <= d <= outcome_date),
                "trades_to_outcome": trades_taken,
            }
        )
    return pd.DataFrame(rows)


def first_payout_summary(outcomes: pd.DataFrame) -> dict[str, float | int | None]:
    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    opens = outcomes[outcomes["outcome"] == "open"].copy()
    total = int(len(outcomes))
    return {
        "starts": total,
        "payout_rate": round(len(payouts) / total, 4) if total else 0.0,
        "breach_rate": round(len(breaches) / total, 4) if total else 0.0,
        "open_rate": round(len(opens) / total, 4) if total else 0.0,
        "average_days_to_payout": round(float(payouts["calendar_days_to_outcome"].mean()), 2)
        if not payouts.empty
        else None,
        "median_days_to_payout": round(float(payouts["calendar_days_to_outcome"].median()), 2)
        if not payouts.empty
        else None,
        "average_first_payout_amount_usd": round(float(payouts["first_payout_amount_usd"].mean()), 2)
        if not payouts.empty
        else None,
        "ev_per_start_usd": round(float(outcomes["net_after_fee_usd"].mean()), 2),
    }


def simulate_lifetime_weekly(day_to_pnl: dict[str, float], all_dates: list[str]) -> pd.DataFrame:
    week_ends = _week_end_dates(all_dates)
    rows = []
    for start_date in all_dates:
        balance = START_BALANCE
        highest_eod = START_BALANCE
        breach = INITIAL_BREACH
        first_payout_hit = False
        total_withdrawals = 0.0
        payout_count = 0
        outcome = "open"
        outcome_date = start_date

        for date_str in all_dates:
            if date_str < start_date:
                continue

            day_pnl = float(day_to_pnl.get(date_str, 0.0))
            if day_pnl != 0.0:
                balance += day_pnl
                if balance <= breach:
                    outcome = "breach"
                    outcome_date = date_str
                    break

            if not first_payout_hit and balance >= WITHDRAW_TRIGGER:
                total_withdrawals += WITHDRAW_TRIGGER - RESET_BALANCE
                payout_count += 1
                balance = RESET_BALANCE
                first_payout_hit = True

            highest_eod = max(highest_eod, balance)
            breach = min(highest_eod - TRAILING_DD, MAX_BREACH)

            if first_payout_hit and date_str in week_ends and balance >= WITHDRAW_TRIGGER:
                withdrawal = balance - RESET_BALANCE
                total_withdrawals += withdrawal
                payout_count += 1
                balance = RESET_BALANCE

            outcome_date = date_str

        net_after_fee = total_withdrawals - CHALLENGE_FEE if first_payout_hit else -CHALLENGE_FEE
        rows.append(
            {
                "start_date": start_date,
                "outcome": outcome,
                "outcome_date": outcome_date,
                "first_payout_hit": first_payout_hit,
                "payout_count": payout_count,
                "total_withdrawals": round(total_withdrawals, 2),
                "net_after_fee": round(net_after_fee, 2),
            }
        )
    return pd.DataFrame(rows)


def lifetime_summary(outcomes: pd.DataFrame) -> dict[str, float]:
    conditional = outcomes[outcomes["first_payout_hit"] == True]
    return {
        "first_payout_rate": round(float(outcomes["first_payout_hit"].mean()), 4),
        "breach_rate": round(float((outcomes["outcome"] == "breach").mean()), 4),
        "ev_per_start_after_fee": round(float(outcomes["net_after_fee"].mean()), 2),
        "avg_total_withdrawals_per_start": round(float(outcomes["total_withdrawals"].mean()), 2),
        "avg_payout_count_per_start": round(float(outcomes["payout_count"].mean()), 2),
        "avg_net_after_fee_given_first_payout": round(float(conditional["net_after_fee"].mean()), 2)
        if not conditional.empty
        else 0.0,
    }


def _slice_trades(trades: list[dict], *, start: str, end: str) -> list[dict]:
    return [trade for trade in trades if start <= trade["date"] <= end]


def _risk_usd_for_trade(trade: dict) -> float:
    return float(trade["risk_points"]) * float(trade["qty"]) * POINT_VALUE


def _slippage_cost_usd(trade: dict, ticks_per_side: int) -> float:
    if ticks_per_side <= 0:
        return 0.0
    roundtrip_points = 2.0 * float(ticks_per_side) * MIN_TICK
    return roundtrip_points * float(trade["qty"]) * POINT_VALUE


def _apply_friction_to_trade(trade: dict, ticks_per_side: int) -> dict:
    adjusted = deepcopy(trade)
    if ticks_per_side <= 0:
        return adjusted
    slip_cost_usd = _slippage_cost_usd(trade, ticks_per_side)
    risk_usd = _risk_usd_for_trade(trade)
    slip_r = slip_cost_usd / risk_usd if risk_usd > 0 else 0.0
    adjusted["pnl_usd"] = round(float(trade["pnl_usd"]) - slip_cost_usd, 2)
    adjusted["r_multiple"] = round(float(trade["r_multiple"]) - slip_r, 3)
    adjusted["pnl_points"] = round(float(adjusted["r_multiple"]) * float(trade["risk_points"]), 4)
    return adjusted


def _simulate_scenario_once(trades: list[dict], scenario: Scenario, rng: np.random.Generator) -> list[dict]:
    kept: list[dict] = []
    for trade in trades:
        if scenario.miss_rate > 0.0 and rng.random() < scenario.miss_rate:
            continue
        kept.append(_apply_friction_to_trade(trade, scenario.slippage_ticks_per_side))
    return kept


def _daily_pnl_metrics(trades: list[dict], *, start: str, end: str) -> dict:
    window_trades = _slice_trades(trades, start=start, end=end)
    trade_summary_full = _compute_summary(window_trades)
    trade_summary = {
        "total_trades": int(trade_summary_full.get("total_trades", 0)),
        "profit_factor": float(trade_summary_full.get("profit_factor", 0.0)),
        "avg_r": float(trade_summary_full.get("avg_r", 0.0)),
        "total_r": float(trade_summary_full.get("total_r", 0.0)),
        "max_drawdown_r": float(trade_summary_full.get("max_drawdown_r", 0.0)),
        "calmar_ratio": float(trade_summary_full.get("calmar_ratio", 0.0)),
    }
    daily = _day_to_pnl(window_trades)
    dates = sorted(daily.keys())
    if not dates:
        return {
            "trade_summary": trade_summary,
            "funded": first_payout_summary(pd.DataFrame(columns=["outcome"])),
            "post_payout": lifetime_summary(pd.DataFrame(columns=["outcome", "first_payout_hit", "net_after_fee", "total_withdrawals", "payout_count"])),
        }
    funded = first_payout_summary(simulate_first_payout(daily, dates))
    post_payout = lifetime_summary(simulate_lifetime_weekly(daily, dates))
    return {
        "trade_summary": trade_summary,
        "funded": funded,
        "post_payout": post_payout,
    }


def _aggregate_numeric_dicts(rows: list[dict]) -> dict:
    keys = rows[0].keys()
    out = {}
    for key in keys:
        values = [row[key] for row in rows]
        if values[0] is None:
            out[key] = None
            continue
        arr = np.array(values, dtype=float)
        out[key] = {
            "mean": round(float(arr.mean()), 4),
            "p10": round(float(np.percentile(arr, 10)), 4),
            "p50": round(float(np.percentile(arr, 50)), 4),
            "p90": round(float(np.percentile(arr, 90)), 4),
        }
    return out


def _summarize_runs(run_outputs: list[dict]) -> dict:
    trade_summary = _aggregate_numeric_dicts([run["trade_summary"] for run in run_outputs])
    funded = _aggregate_numeric_dicts([run["funded"] for run in run_outputs])
    post_payout = _aggregate_numeric_dicts([run["post_payout"] for run in run_outputs])
    return {
        "trade_summary": trade_summary,
        "funded": funded,
        "post_payout": post_payout,
    }


def _scenario_payload(trades: list[dict], scenario: Scenario) -> dict:
    run_metrics = []
    for run_idx in range(scenario.monte_carlo_runs):
        rng = np.random.default_rng(20260413 + run_idx * 101 + scenario.slippage_ticks_per_side * 17 + int(scenario.miss_rate * 1000))
        adjusted = _simulate_scenario_once(trades, scenario, rng)
        run_metrics.append(
            {
                "pre_holdout": _daily_pnl_metrics(adjusted, start=FULL_START, end=PRE_HOLDOUT_END),
                "holdout": _daily_pnl_metrics(adjusted, start=HOLDOUT_START, end=HOLDOUT_END_INCLUSIVE),
            }
        )

    return {
        "name": scenario.name,
        "slippage_ticks_per_side": scenario.slippage_ticks_per_side,
        "miss_rate": scenario.miss_rate,
        "monte_carlo_runs": scenario.monte_carlo_runs,
        "pre_holdout": _summarize_runs([run["pre_holdout"] for run in run_metrics]),
        "holdout": _summarize_runs([run["holdout"] for run in run_metrics]),
    }


def _metric_mean(block: dict, *path: str) -> float:
    current = block
    for key in path:
        current = current[key]
    if isinstance(current, dict) and "mean" in current:
        return float(current["mean"])
    return float(current)


def _write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI Execution Robustness",
        "",
        "- Objective: stress the live exact `HTF_LSI_5M_LAG24` profile under harsher execution assumptions.",
        "- Base stream: exact historical replay through the live execution engine.",
        "- Stress model: per-side slippage plus Monte Carlo missed fills on the exact trade stream.",
        "- Important note: same-bar exit luck is already removed by the live engine, so this packet focuses on extra slippage / queue-miss style degradation rather than re-testing same-bar assumptions.",
        f"- Replay window: `{FULL_START}` to `{payload['holdout_end_inclusive']}`",
        "",
        "## Scenario Table",
        "",
        "| Scenario | Pre PF | Pre Avg R | Pre Funded EV | Pre Withdrawals | Holdout PF | Holdout Avg R | Holdout Funded EV | Holdout Withdrawals |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["scenarios"]:
        lines.append(
            f"| {row['name']} | "
            f"{_metric_mean(row, 'pre_holdout', 'trade_summary', 'profit_factor'):.3f} | "
            f"{_metric_mean(row, 'pre_holdout', 'trade_summary', 'avg_r'):.3f} | "
            f"{_metric_mean(row, 'pre_holdout', 'funded', 'ev_per_start_usd'):.2f} | "
            f"{_metric_mean(row, 'pre_holdout', 'post_payout', 'avg_total_withdrawals_per_start'):.2f} | "
            f"{_metric_mean(row, 'holdout', 'trade_summary', 'profit_factor'):.3f} | "
            f"{_metric_mean(row, 'holdout', 'trade_summary', 'avg_r'):.3f} | "
            f"{_metric_mean(row, 'holdout', 'funded', 'ev_per_start_usd'):.2f} | "
            f"{_metric_mean(row, 'holdout', 'post_payout', 'avg_total_withdrawals_per_start'):.2f} |"
        )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    common_end = latest_common_end([SIGNAL_SYMBOL])
    holdout_end = common_end.date().isoformat()

    result = run_profile_backtest_sync(
        config=config,
        profile_name=PROFILE_NAME,
        start_date=FULL_START,
        end_date=holdout_end,
        latest_data_ts=common_end,
        label=f"EXEC ROBUSTNESS {PROFILE_NAME} {FULL_START} to {holdout_end}",
    )

    global HOLDOUT_END_INCLUSIVE
    HOLDOUT_END_INCLUSIVE = holdout_end

    scenarios = []
    for scenario in SCENARIOS:
        print(
            f"Running scenario {scenario.name} "
            f"(slip={scenario.slippage_ticks_per_side}t/side miss={scenario.miss_rate:.0%} runs={scenario.monte_carlo_runs})...",
            flush=True,
        )
        scenarios.append(_scenario_payload(result["trades"], scenario))

    payload = {
        "profile_name": PROFILE_NAME,
        "signal_symbol": SIGNAL_SYMBOL,
        "exec_symbol": EXEC_SYMBOL,
        "point_value": POINT_VALUE,
        "min_tick": MIN_TICK,
        "full_start": FULL_START,
        "pre_holdout_end_inclusive": PRE_HOLDOUT_END,
        "holdout_start": HOLDOUT_START,
        "holdout_end_inclusive": holdout_end,
        "base_trade_count": len(result["trades"]),
        "base_summary": result["summary"],
        "scenarios": scenarios,
    }

    (OUTPUT_DIR / "execution_robustness.json").write_text(json.dumps(payload, indent=2, default=str))
    _write_report(payload)
    print(f"Saved execution robustness packet to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
