#!/usr/bin/env python3
"""Prop firm phase 1 analysis for NQ NY 10yr_opt phase_1 config.

No optimization — just run the existing config and simulate staggered
prop firm accounts (-4R breach / +5R payout, biweekly starts) over
the last 2 years. Also runs 2x risk variant (+2.5R/-2.0R).
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Config from nq_ny 10yr_opt phase_1 ──────────────────────────────────────

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="12:00",
    flat_start="15:30",
    flat_end="16:00",
    stop_atr_pct=7.0,
    min_gap_atr_pct=2.5,
)

CONFIG = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.5,
    tp1_ratio=0.4,
    atr_length=12,
    name="NQ NY 10yr_opt phase_1 — Prop Firm Phase 1",
)

# ── Date range: last 2 years ────────────────────────────────────────────────

START_DATE = "2024-03-08"
END_DATE = "2026-03-08"

# ── Prop firm parameters ────────────────────────────────────────────────────

PAYOUT_1X = 5.0
BREACH_1X = -4.0
PAYOUT_2X = 2.5
BREACH_2X = -2.0
CYCLE_DAYS = 14


def simulate_staggered_accounts(trades, start_date, end_date, payout_r, breach_r, stagger_days=14):
    """Simulate staggered prop firm accounts."""
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
                "success_rate": None, "ev_per_account": 0, "account_details": []}

    trade_data = sorted(
        [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in filled],
        key=lambda x: x["date"],
    )

    d_start = datetime.date.fromisoformat(start_date)
    d_end = datetime.date.fromisoformat(end_date)

    account_starts = []
    s = d_start
    while s <= d_end:
        account_starts.append(s)
        s += datetime.timedelta(days=stagger_days)

    results = []
    for acct_start in account_starts:
        cum_r = 0.0
        outcome = "open"
        trades_taken = 0
        outcome_date = None
        peak_r = 0.0
        trough_r = 0.0

        for t in trade_data:
            if t["date"] < acct_start:
                continue
            cum_r += t["r"]
            trades_taken += 1
            peak_r = max(peak_r, cum_r)
            trough_r = min(trough_r, cum_r)

            if cum_r >= payout_r:
                outcome = "payout"
                outcome_date = t["date"]
                break
            elif cum_r <= breach_r:
                outcome = "breach"
                outcome_date = t["date"]
                break

        if outcome == "open":
            future_trades = [t for t in trade_data if t["date"] >= acct_start]
            outcome_date = future_trades[-1]["date"] if future_trades else acct_start

        calendar_days = (outcome_date - acct_start).days + 1

        results.append({
            "account_start": acct_start.isoformat(),
            "outcome": outcome,
            "final_r": round(cum_r, 4),
            "peak_r": round(peak_r, 4),
            "trough_r": round(trough_r, 4),
            "trades_taken": trades_taken,
            "calendar_days": calendar_days,
            "outcome_date": outcome_date.isoformat(),
        })

    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]

    n_payouts = len(payouts)
    n_breaches = len(breaches)
    n_open = len(opens)
    resolved = n_payouts + n_breaches
    success_rate = n_payouts / resolved if resolved > 0 else None

    capped_rs = []
    for r in results:
        if r["outcome"] == "payout":
            capped_rs.append(payout_r)
        elif r["outcome"] == "breach":
            capped_rs.append(breach_r)
        else:
            capped_rs.append(r["final_r"])
    ev = float(np.mean(capped_rs)) if capped_rs else 0.0

    return {
        "total_accounts": len(results),
        "payouts": n_payouts,
        "breaches": n_breaches,
        "open": n_open,
        "success_rate": success_rate,
        "ev_per_account": round(ev, 4),
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "median_days_to_breach": round(float(np.median([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "avg_open_r": round(float(np.mean([r["final_r"] for r in opens])), 4) if opens else None,
        "account_details": results,
    }


def print_account_table(details):
    """Print account-by-account breakdown."""
    print(f"  {'Started':<12} {'Outcome':<10} {'Final R':>8} {'Peak R':>7} {'Trough':>7} {'Trades':>6} {'Days':>6} {'Resolved':<12}")
    print(f"  {'-'*75}")
    for d in details:
        outcome_col = d['outcome'].upper()
        if d['outcome'] == 'payout':
            outcome_col = f"\033[92m{outcome_col}\033[0m"
        elif d['outcome'] == 'breach':
            outcome_col = f"\033[91m{outcome_col}\033[0m"
        else:
            outcome_col = f"\033[93m{outcome_col}\033[0m"
        print(f"  {d['account_start']:<12} {outcome_col:<19} {d['final_r']:>8.3f} {d['peak_r']:>7.3f} {d['trough_r']:>7.3f} {d['trades_taken']:>6} {d['calendar_days']:>6} {d['outcome_date']:<12}")


def main():
    t0 = time.time()

    print("NQ NY 10yr_opt phase_1 — Prop Firm Phase 1 Analysis")
    print("=" * 70)
    print(f"Config: continuation, long, rr=3.5, tp1=0.4, stop=7.0%, gap=2.5%")
    print(f"        ORB=20m (09:30-09:50), entry<=12:00, flat=15:30, ATR=12")
    print(f"Period: {START_DATE} to {END_DATE}")
    print()

    # Load data
    print("Loading data...")
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    # Run backtest
    print("Running backtest...")
    trades = run_backtest(df_5m, CONFIG, start_date=START_DATE, end_date=END_DATE, df_1m=df_1m)

    m = compute_metrics(trades)
    print(f"\n  Strategy Performance (2Y window):")
    print(f"  Trades: {m['total_trades']}  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}")
    print(f"  PF: {m['profit_factor']:.2f}  |  Sharpe: {m['sharpe_ratio']:.2f}  |  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}  |  Avg R: {m['avg_r']:.3f}")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.1f}" for yr, r in years)
        print(f"  R by year: {yr_str}")

    # ── 1x Risk: +5R / -4R ─────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"1x RISK: $5k/trade → +5R payout / -4R breach")
    print(f"{'=' * 70}")

    acct_1x = simulate_staggered_accounts(trades, START_DATE, END_DATE, PAYOUT_1X, BREACH_1X, CYCLE_DAYS)

    sr = acct_1x["success_rate"]
    sr_str = f"{sr:.1%}" if sr is not None else "N/A"
    print(f"\n  Accounts: {acct_1x['total_accounts']}  |  Payouts: {acct_1x['payouts']}  |  Breaches: {acct_1x['breaches']}  |  Open: {acct_1x['open']}")
    print(f"  Success Rate: {sr_str}  |  EV per Account: {acct_1x['ev_per_account']:+.3f}R")

    if acct_1x["median_days_to_payout"] is not None:
        print(f"  Payout: avg {acct_1x['avg_days_to_payout']:.0f} days  (median {acct_1x['median_days_to_payout']:.0f} days)")
    if acct_1x["median_days_to_breach"] is not None:
        print(f"  Breach: avg {acct_1x['avg_days_to_breach']:.0f} days  (median {acct_1x['median_days_to_breach']:.0f} days)")
    if acct_1x["avg_open_r"] is not None:
        print(f"  Open accounts avg R: {acct_1x['avg_open_r']:+.3f}")

    print(f"\n  Account-by-account:")
    print_account_table(acct_1x["account_details"])

    # ── 2x Risk: +2.5R / -2.0R ─────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"2x RISK: $10k/trade → +2.5R payout / -2.0R breach")
    print(f"{'=' * 70}")

    acct_2x = simulate_staggered_accounts(trades, START_DATE, END_DATE, PAYOUT_2X, BREACH_2X, CYCLE_DAYS)

    sr2 = acct_2x["success_rate"]
    sr2_str = f"{sr2:.1%}" if sr2 is not None else "N/A"
    print(f"\n  Accounts: {acct_2x['total_accounts']}  |  Payouts: {acct_2x['payouts']}  |  Breaches: {acct_2x['breaches']}  |  Open: {acct_2x['open']}")
    print(f"  Success Rate: {sr2_str}  |  EV per Account: {acct_2x['ev_per_account']:+.3f}R")

    if acct_2x["median_days_to_payout"] is not None:
        print(f"  Payout: avg {acct_2x['avg_days_to_payout']:.0f} days  (median {acct_2x['median_days_to_payout']:.0f} days)")
    if acct_2x["median_days_to_breach"] is not None:
        print(f"  Breach: avg {acct_2x['avg_days_to_breach']:.0f} days  (median {acct_2x['median_days_to_breach']:.0f} days)")
    if acct_2x["avg_open_r"] is not None:
        print(f"  Open accounts avg R: {acct_2x['avg_open_r']:+.3f}")

    print(f"\n  Account-by-account:")
    print_account_table(acct_2x["account_details"])

    print(f"\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
