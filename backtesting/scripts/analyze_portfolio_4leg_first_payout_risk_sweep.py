#!/usr/bin/env python3
"""Sweep first-payout funded risk for the 4-leg portfolio on the last 2 years."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd

from analyze_portfolio_4leg_weekly_withdrawal_ev import START, load_portfolio_trades
from run_portfolio_4leg_backtest import FUNDED_PROFILE
from orb_backtest.analysis.prop_regime_specialist import (
    build_funded_first_payout_scorecard,
    simulate_funded_first_payouts,
)

RISK_VALUES = (200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 500.0, 550.0, 600.0)


def rank_score(row: pd.Series) -> float:
    payout_rate = float(row["payout_rate"])
    breach_rate = float(row["breach_rate"])
    avg_days = float(row["average_days_to_payout"] or 999.0)
    median_days = float(row["median_days_to_payout"] or 999.0)
    return round(
        (payout_rate * 100.0)
        - (breach_rate * 35.0)
        - (avg_days * 0.35)
        - (median_days * 0.15),
        3,
    )


def main() -> None:
    trades, all_dates, latest_date = load_portfolio_trades()
    rows = []
    for risk in RISK_VALUES:
        profile = replace(
            FUNDED_PROFILE,
            risk_pre_payout_usd=risk,
            risk_post_payout_usd=max(100.0, risk / 2.0),
        )
        outcomes = simulate_funded_first_payouts(
            specialist_name=f"Portfolio_4leg_risk_{int(risk)}",
            trades=trades,
            trading_dates=all_dates,
            profile=profile,
        )
        score = build_funded_first_payout_scorecard(outcomes, profile)
        rows.append(
            {
                "risk_pre_usd": int(risk),
                "risk_post_usd": int(max(100.0, risk / 2.0)),
                "starts": int(score["total_starts"]),
                "payout_rate": float(score["payout_rate"]),
                "breach_rate": float(score["breach_rate"]),
                "open_rate": float(score["open_rate"]),
                "average_days_to_payout": score["average_days_to_payout"],
                "median_days_to_payout": score["median_days_to_payout"],
                "average_trades_to_payout": score["average_trades_to_payout"],
                "average_first_payout_amount_usd": score["average_first_payout_amount_usd"],
                "average_net_after_fee_usd": score["average_net_after_fee_usd"],
                "ev_per_start_usd": float(score["ev_per_start_usd"]),
            }
        )

    df = pd.DataFrame(rows)
    df["rank_score"] = df.apply(rank_score, axis=1)
    df = df.sort_values("risk_pre_usd").reset_index(drop=True)

    best = df.sort_values(
        by=["rank_score", "payout_rate", "breach_rate", "average_days_to_payout"],
        ascending=[False, False, True, True],
    ).iloc[0]
    risk_300 = df[df["risk_pre_usd"] == 300].iloc[0]
    risk_500 = df[df["risk_pre_usd"] == 500].iloc[0]

    display = df[
        [
            "risk_pre_usd",
            "payout_rate",
            "breach_rate",
            "open_rate",
            "average_days_to_payout",
            "median_days_to_payout",
            "average_first_payout_amount_usd",
            "ev_per_start_usd",
            "rank_score",
        ]
    ].copy()

    print("4-Leg Portfolio First-Payout Risk Sweep")
    print("=" * 72)
    print(f"Window: {START} to {latest_date}")
    print(display.to_string(index=False))
    print()
    print("Spot Checks")
    print(
        f"- $300 risk: payout {risk_300['payout_rate']:.1%}, breach {risk_300['breach_rate']:.1%}, "
        f"avg days {risk_300['average_days_to_payout']}, EV/start ${risk_300['ev_per_start_usd']:.2f}"
    )
    print(
        f"- $500 risk: payout {risk_500['payout_rate']:.1%}, breach {risk_500['breach_rate']:.1%}, "
        f"avg days {risk_500['average_days_to_payout']}, EV/start ${risk_500['ev_per_start_usd']:.2f}"
    )
    print()
    print(
        f"Suggested sweet spot: ${int(best['risk_pre_usd'])} risk "
        f"(payout {best['payout_rate']:.1%}, breach {best['breach_rate']:.1%}, "
        f"avg days {best['average_days_to_payout']}, EV/start ${best['ev_per_start_usd']:.2f})"
    )


if __name__ == "__main__":
    main()
