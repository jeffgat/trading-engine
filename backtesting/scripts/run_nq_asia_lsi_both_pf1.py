#!/usr/bin/env python3
"""Prop firm phase 1 stats for NQ ASIA LSI Both (rr=1.75, tp1=0.7, gap=1.75).

No sweep — single config, 1x and 2x risk comparison.
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2024-03-08"
END_DATE = "2026-03-08"
CYCLE_DAYS = 14

CONFIG = StrategyConfig(
    strategy="lsi",
    direction_filter="both",
    rr=1.75,
    tp1_ratio=0.7,
    risk_usd=5000.0,
    atr_length=40,
    use_bar_magnifier=True,
    lsi_n_left=3,
    lsi_n_right=3,
    lsi_fvg_window_left=10,
    lsi_fvg_window_right=10,
    lsi_stop_mode="absolute",
    lsi_entry_mode="close",
    sessions=(SessionConfig(
        name="ASIA",
        rth_start="20:00",
        entry_start="20:40",
        entry_end="23:30",
        flat_start="00:00",
        flat_end="01:00",
        stop_atr_pct=0.0,
        min_gap_atr_pct=1.75,
    ),),
    instrument=get_instrument("NQ"),
)


def simulate_staggered_accounts(trades, payout_r, breach_r):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return None

    trade_data = sorted(
        [{"date": datetime.date.fromisoformat(t.date), "r": t.r_multiple} for t in filled],
        key=lambda x: x["date"],
    )

    d_start = datetime.date.fromisoformat(START_DATE)
    d_end = datetime.date.fromisoformat(END_DATE)
    account_starts = []
    s = d_start
    while s <= d_end:
        account_starts.append(s)
        s += datetime.timedelta(days=CYCLE_DAYS)

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
            future = [t for t in trade_data if t["date"] >= acct_start]
            outcome_date = future[-1]["date"] if future else acct_start

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

    total = len(results)
    payouts = [r for r in results if r["outcome"] == "payout"]
    breaches = [r for r in results if r["outcome"] == "breach"]
    opens = [r for r in results if r["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    success_rate = len(payouts) / resolved if resolved > 0 else None

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
        "total": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": success_rate,
        "ev": ev,
        "avg_days_pay": float(np.mean([r["calendar_days"] for r in payouts])) if payouts else None,
        "med_days_pay": float(np.median([r["calendar_days"] for r in payouts])) if payouts else None,
        "avg_tr_pay": float(np.mean([r["trades_taken"] for r in payouts])) if payouts else None,
        "avg_days_breach": float(np.mean([r["calendar_days"] for r in breaches])) if breaches else None,
        "med_days_breach": float(np.median([r["calendar_days"] for r in breaches])) if breaches else None,
        "avg_tr_breach": float(np.mean([r["trades_taken"] for r in breaches])) if breaches else None,
        "avg_open_r": float(np.mean([r["final_r"] for r in opens])) if opens else None,
        "details": results,
    }


def print_accounts(label, acct, payout_r, breach_r):
    sr = f"{acct['success_rate']:.1%}" if acct['success_rate'] is not None else "N/A"
    print(f"\n  ── {label}: +{payout_r}R payout / {breach_r}R breach ──")
    print(f"  Accounts: {acct['total']}  |  {acct['payouts']} payouts  |  {acct['breaches']} breaches  |  {acct['open']} open")
    print(f"  Success Rate: {sr}  |  EV per account: {acct['ev']:.3f}R")
    if acct['avg_days_pay'] is not None:
        print(f"  Payout: avg {acct['avg_tr_pay']:.1f} trades / {acct['avg_days_pay']:.0f} days  (median {acct['med_days_pay']:.0f} days)")
    if acct['avg_days_breach'] is not None:
        print(f"  Breach: avg {acct['avg_tr_breach']:.1f} trades / {acct['avg_days_breach']:.0f} days  (median {acct['med_days_breach']:.0f} days)")
    if acct['avg_open_r'] is not None:
        print(f"  Open accounts: avg {acct['avg_open_r']:.2f}R")

    print(f"\n  {'Started':<12} {'Outcome':<10} {'Final R':>8} {'Peak R':>7} {'Trough':>7} {'Trades':>6} {'Days':>6} {'Resolved':<12}")
    for d in acct['details']:
        oc = d['outcome'].upper()
        if d['outcome'] == 'payout':
            oc = f"\033[92m{oc}\033[0m"
        elif d['outcome'] == 'breach':
            oc = f"\033[91m{oc}\033[0m"
        else:
            oc = f"\033[93m{oc}\033[0m"
        print(f"  {d['account_start']:<12} {oc:<19} {d['final_r']:>8.3f} {d['peak_r']:>7.3f} {d['trough_r']:>7.3f} {d['trades_taken']:>6} {d['calendar_days']:>6} {d['outcome_date']:<12}")


def main():
    t0 = time.time()

    print("Loading NQ data...")
    df = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")

    print("Running NQ ASIA LSI Both (rr=1.75, tp1=0.7, gap=1.75)...")
    trades = run_backtest(df, CONFIG, start_date=START_DATE, end_date=END_DATE, df_1m=df_1m)
    m = compute_metrics(trades)

    print(f"\n{'=' * 100}")
    print(f"  NQ ASIA LSI Both — Prop Firm Phase 1 Stats")
    print(f"{'=' * 100}")
    print(f"  {m['total_trades']} trades  |  WR {m['win_rate']:.1%}  |  Net R {m['total_r']:.2f}  |  DD {m['max_drawdown_r']:.2f}R  |  Calmar {m['calmar_ratio']:.2f}  |  Sharpe {m['sharpe_ratio']:.2f}  |  PF {m['profit_factor']:.2f}")

    acct_1x = simulate_staggered_accounts(trades, 5.0, -4.0)
    acct_2x = simulate_staggered_accounts(trades, 2.5, -2.0)

    print_accounts("1x Risk ($5k)", acct_1x, 5.0, -4.0)
    print_accounts("2x Risk ($10k)", acct_2x, 2.5, -2.0)

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
