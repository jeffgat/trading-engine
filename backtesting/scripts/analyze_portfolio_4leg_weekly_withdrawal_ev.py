#!/usr/bin/env python3
"""Quick EV check for the 4-leg portfolio under immediate-first + weekly withdrawals.

Assumptions:
- Use 4-leg portfolio trades from 2025-01-01 onward.
- Start each simulated account at 50,000 with initial breach at 48,000.
- Trailing EOD drawdown of 2,000 capped at 50,000 breach balance.
- Pre-first-payout risk = 500 USD per R.
- After first payout, risk = 250 USD per R.
- First payout: as soon as balance first reaches 52,500, withdraw 500 immediately
  and reset balance to 52,000.
- After first payout: on the last trading day of the week, if balance >= 52,500,
  withdraw everything above 52,000 and reset balance to 52,000.
- EV is average net withdrawals minus the 100 USD challenge fee across all start dates.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pandas as pd

from run_portfolio_4leg_backtest import build_legs, _filled
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest

START = "2025-01-01"
START_BALANCE = 50_000.0
INITIAL_BREACH = 48_000.0
TRAILING_DD = 2_000.0
MAX_BREACH = 50_000.0
WITHDRAW_TRIGGER = 52_500.0
RESET_BALANCE = 52_000.0
CHALLENGE_FEE = 100.0
RISK_PRE = 500.0
RISK_POST = 250.0


def load_portfolio_trades() -> tuple[list, list[str], str]:
    legs = build_legs()
    data: dict[str, dict] = {}
    all_trades = []

    for leg in legs.values():
        inst = leg["instrument"]
        symbol = inst.symbol
        if symbol not in data:
            data[symbol] = {
                "5m": load_5m_data(inst.data_file),
                "1m": load_1m_for_5m(inst.data_file),
                "1s": load_1s_for_5m(inst.data_file),
            }

        series = data[symbol]
        trades = run_backtest(
            series["5m"],
            leg["config"],
            df_1m=series["1m"],
            df_1s=series["1s"],
        )
        dow_excl = leg["dow_excl"]
        if dow_excl:
            trades = [
                trade
                for trade in trades
                if trade.exit_type == 0
                or dt.date.fromisoformat(trade.date).weekday() not in dow_excl
            ]
        all_trades.extend(_filled(trades))

    all_trades = [trade for trade in all_trades if trade.date >= START]
    all_trades.sort(key=lambda t: (t.date, t.fill_time or "", t.fill_bar, t.exit_time or ""))
    all_dates = sorted({trade.date for trade in all_trades})
    return all_trades, all_dates, all_dates[-1]


def last_trading_days_of_week(all_dates: list[str]) -> set[str]:
    result: set[str] = set()
    for index, date_str in enumerate(all_dates):
        current_week = dt.date.fromisoformat(date_str).isocalendar()[:2]
        next_week = None
        if index + 1 < len(all_dates):
            next_week = dt.date.fromisoformat(all_dates[index + 1]).isocalendar()[:2]
        if next_week != current_week:
            result.add(date_str)
    return result


def simulate_start(
    start_date: str,
    all_dates: list[str],
    day_to_r: dict[str, float],
    week_ends: set[str],
) -> dict:
    balance = START_BALANCE
    highest_eod = START_BALANCE
    breach = INITIAL_BREACH
    risk_usd = RISK_PRE
    first_payout_hit = False
    total_withdrawals = 0.0
    payout_count = 0
    outcome = "open"
    outcome_date = start_date

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

        if not first_payout_hit and balance >= WITHDRAW_TRIGGER:
            total_withdrawals += WITHDRAW_TRIGGER - RESET_BALANCE
            payout_count += 1
            balance = RESET_BALANCE
            first_payout_hit = True
            risk_usd = RISK_POST

        highest_eod = max(highest_eod, balance)
        breach = min(highest_eod - TRAILING_DD, MAX_BREACH)

        if first_payout_hit and date_str in week_ends and balance >= WITHDRAW_TRIGGER:
            withdrawal = balance - RESET_BALANCE
            total_withdrawals += withdrawal
            payout_count += 1
            balance = RESET_BALANCE

        outcome_date = date_str

    net_after_fee = total_withdrawals - CHALLENGE_FEE if first_payout_hit else -CHALLENGE_FEE
    return {
        "start_date": start_date,
        "outcome": outcome,
        "outcome_date": outcome_date,
        "first_payout_hit": first_payout_hit,
        "payout_count": payout_count,
        "total_withdrawals": round(total_withdrawals, 2),
        "net_after_fee": round(net_after_fee, 2),
        "ending_balance": round(balance, 2),
        "breach_balance": round(breach, 2),
    }


def main() -> None:
    trades, all_dates, latest_date = load_portfolio_trades()
    day_to_r: dict[str, float] = defaultdict(float)
    for trade in trades:
        day_to_r[trade.date] += float(trade.r_multiple)

    week_ends = last_trading_days_of_week(all_dates)
    rows = [simulate_start(start_date, all_dates, day_to_r, week_ends) for start_date in all_dates]
    outcomes = pd.DataFrame(rows)

    first_payout_rate = float(outcomes["first_payout_hit"].mean())
    breach_rate = float((outcomes["outcome"] == "breach").mean())
    ev_per_start = float(outcomes["net_after_fee"].mean())
    avg_total_withdrawals = float(outcomes["total_withdrawals"].mean())
    avg_payout_count = float(outcomes["payout_count"].mean())
    positive_share = float((outcomes["net_after_fee"] > 0).mean())
    conditional = outcomes[outcomes["first_payout_hit"] == True]
    avg_net_given_first = float(conditional["net_after_fee"].mean()) if not conditional.empty else 0.0

    print("4-Leg Portfolio Immediate-First + Weekly Withdrawal EV")
    print("=" * 72)
    print(f"Window: {START} to {latest_date}")
    print(f"Starts: {len(outcomes)}")
    print(f"First payout rate: {first_payout_rate:.1%}")
    print(f"Breach rate: {breach_rate:.1%}")
    print(f"EV per start after fee: ${ev_per_start:.2f}")
    print(f"Avg withdrawals per start: ${avg_total_withdrawals:.2f}")
    print(f"Avg payout count per start: {avg_payout_count:.2f}")
    print(f"Avg net after fee | given first payout: ${avg_net_given_first:.2f}")
    print(f"Positive-EV start share: {positive_share:.1%}")
    print()
    print("Top 5 starts by net after fee:")
    print(
        outcomes.sort_values("net_after_fee", ascending=False)
        .head(5)[
            [
                "start_date",
                "outcome",
                "first_payout_hit",
                "payout_count",
                "total_withdrawals",
                "net_after_fee",
                "outcome_date",
            ]
        ]
        .to_string(index=False)
    )
    print()
    print("Bottom 5 starts by net after fee:")
    print(
        outcomes.sort_values("net_after_fee", ascending=True)
        .head(5)[
            [
                "start_date",
                "outcome",
                "first_payout_hit",
                "payout_count",
                "total_withdrawals",
                "net_after_fee",
                "outcome_date",
            ]
        ]
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
