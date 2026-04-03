#!/usr/bin/env python3
"""Exact payout analysis for selected execution-engine profiles.

Profiles:
- FAST_V1.1
- FAST_V2
- FAST_V2.1

Analysis:
- Exact historical replay through the live execution engines
- Last 2 years of common data across the symbols used by the requested profiles
- First-payout funded-account stats
- Lifetime EV with immediate first 500 USD payout, then weekly withdrawals above 52.5k
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date as dt_date
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader.historical_backtest import (  # noqa: E402
    latest_common_end,
    rolling_year_window_endpoints,
    run_profile_backtest_sync,
)
from trader.main import DEFAULT_CONFIG, load_config, load_exec_configs  # noqa: E402

PROFILES = ("FAST_V1.1", "FAST_V2", "FAST_V2.1")
CHALLENGE_FEE = 100.0
START_BALANCE = 50_000.0
INITIAL_BREACH = 48_000.0
TRAILING_DD = 2_000.0
MAX_BREACH = 50_000.0
WITHDRAW_TRIGGER = 52_500.0
RESET_BALANCE = 52_000.0


def _profile_symbols(exec_config) -> list[str]:
    symbols: set[str] = set()
    for session_name, overrides in exec_config.session_overrides.items():
        instrument = overrides.get("instrument")
        if instrument is None:
            instrument = session_name.split("_", 1)[0]
        symbols.add(instrument)
    for session_name, overrides in exec_config.lsi_session_overrides.items():
        instrument = overrides.get("instrument")
        if instrument is None:
            instrument = session_name.split("_", 1)[0]
        symbols.add(instrument)
    return sorted(symbols)


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
                ).days
                + 1,
                "trading_days_to_outcome": sum(1 for d in all_dates if start_date <= d <= outcome_date),
                "trades_to_outcome": trades_taken,
            }
        )
    return pd.DataFrame(rows)


def first_payout_summary(outcomes: pd.DataFrame) -> dict:
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


def lifetime_summary(outcomes: pd.DataFrame) -> dict:
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


def main() -> None:
    config = load_config(DEFAULT_CONFIG)
    exec_configs = {cfg.name: cfg for cfg in load_exec_configs(config)}
    requested = [exec_configs[name] for name in PROFILES]
    symbols = sorted({symbol for cfg in requested for symbol in _profile_symbols(cfg)})
    common_end = latest_common_end(symbols)
    start_date, end_date = rolling_year_window_endpoints(common_end, 2)

    print("Exact Execution Profile Payout Analysis")
    print("=" * 72)
    print(f"Common latest data timestamp: {common_end.isoformat()}")
    print(f"Replay window: {start_date} -> {end_date}")
    print()

    records = []
    for profile_name in PROFILES:
        print(f"Running exact replay for {profile_name}...", flush=True)
        result = run_profile_backtest_sync(
            config=config,
            profile_name=profile_name,
            start_date=start_date,
            end_date=end_date,
            latest_data_ts=common_end,
            label=f"EXEC EXACT {profile_name} Last 2Y {start_date} to {end_date}",
        )
        trades = result["trades"]
        day_to_pnl = _day_to_pnl(trades)
        all_dates = sorted(day_to_pnl.keys())
        first_outcomes = simulate_first_payout(day_to_pnl, all_dates)
        life_outcomes = simulate_lifetime_weekly(day_to_pnl, all_dates)
        first = first_payout_summary(first_outcomes)
        life = lifetime_summary(life_outcomes)
        records.append(
            {
                "profile": profile_name,
                "trades": len(trades),
                "total_pnl_usd": round(float(result["summary"]["total_pnl_usd"]), 2),
                "total_r": round(float(result["summary"]["total_r"]), 2),
                "sharpe": round(float(result["summary"]["sharpe_ratio"]), 2),
                "calmar": round(float(result["summary"]["calmar_ratio"]), 2),
                **{f"first_{k}": v for k, v in first.items()},
                **life,
            }
        )

    df = pd.DataFrame(records)
    print("Summary")
    print(
        df[
            [
                "profile",
                "trades",
                "total_pnl_usd",
                "total_r",
                "sharpe",
                "calmar",
                "first_payout_rate",
                "first_breach_rate",
                "first_average_days_to_payout",
                "first_ev_per_start_usd",
                "ev_per_start_after_fee",
                "avg_total_withdrawals_per_start",
                "avg_payout_count_per_start",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
