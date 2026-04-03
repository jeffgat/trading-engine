#!/usr/bin/env python3
"""Sweep post-first-payout risk for the 4-leg portfolio lifetime-withdrawal model."""

from __future__ import annotations

import pandas as pd

from analyze_portfolio_4leg_weekly_withdrawal_ev import (
    START,
    START_BALANCE,
    INITIAL_BREACH,
    TRAILING_DD,
    MAX_BREACH,
    WITHDRAW_TRIGGER,
    RESET_BALANCE,
    CHALLENGE_FEE,
    RISK_PRE,
    load_portfolio_trades,
    last_trading_days_of_week,
)

POST_RISKS = (150.0, 175.0, 200.0, 225.0, 250.0, 275.0, 300.0)


def simulate_start(start_date: str, all_dates: list[str], day_to_r: dict[str, float], week_ends: set[str], risk_post: float) -> dict:
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
            risk_usd = risk_post

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
    }


def main() -> None:
    trades, all_dates, latest_date = load_portfolio_trades()
    day_to_r: dict[str, float] = {}
    for trade in trades:
        day_to_r[trade.date] = day_to_r.get(trade.date, 0.0) + float(trade.r_multiple)
    week_ends = last_trading_days_of_week(all_dates)

    rows = []
    for risk_post in POST_RISKS:
        starts = [
            simulate_start(start_date, all_dates, day_to_r, week_ends, risk_post)
            for start_date in all_dates
        ]
        outcomes = pd.DataFrame(starts)
        conditional = outcomes[outcomes["first_payout_hit"] == True]
        rows.append(
            {
                "risk_post_usd": int(risk_post),
                "first_payout_rate": float(outcomes["first_payout_hit"].mean()),
                "breach_rate": float((outcomes["outcome"] == "breach").mean()),
                "ev_per_start_after_fee": float(outcomes["net_after_fee"].mean()),
                "avg_total_withdrawals_per_start": float(outcomes["total_withdrawals"].mean()),
                "avg_payout_count_per_start": float(outcomes["payout_count"].mean()),
                "avg_net_given_first_payout": float(conditional["net_after_fee"].mean()) if not conditional.empty else 0.0,
            }
        )

    df = pd.DataFrame(rows).sort_values("risk_post_usd").reset_index(drop=True)
    best_ev = df.sort_values("ev_per_start_after_fee", ascending=False).iloc[0]

    print("4-Leg Portfolio Post-Payout Risk Sweep")
    print("=" * 72)
    print(f"Window: {START} to {latest_date}")
    print(df.to_string(index=False))
    print()
    print(
        f"Best EV in this sweep: risk_post ${int(best_ev['risk_post_usd'])} "
        f"-> EV/start ${best_ev['ev_per_start_after_fee']:.2f}, "
        f"avg withdrawals/start ${best_ev['avg_total_withdrawals_per_start']:.2f}, "
        f"avg payout count/start {best_ev['avg_payout_count_per_start']:.2f}"
    )


if __name__ == "__main__":
    main()
