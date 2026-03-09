#!/usr/bin/env python3
"""Re-simulate prop firm accounts with 2x risk for both winning configs.

2x risk = halved thresholds: +2.5R payout / -2.0R breach
(Same dollar amounts, double position size per trade)

Configs from phase 1 sweeps:
  1. NQ ASIA LSI Long: rr=1.75, tp1=0.7, gap=1.75
  2. ES NY ORB Long:   rr=3.0,  tp1=0.2, stop=5.0, gap=1.0
"""

import dataclasses
import datetime
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics


# ── Date range ─────────────────────────────────────────────────────────────

START_DATE = "2024-03-08"
END_DATE = "2026-03-08"

# ── Prop firm parameters ───────────────────────────────────────────────────

PAYOUT_1X = 5.0
BREACH_1X = -4.0
PAYOUT_2X = 2.5   # halved — 2x risk
BREACH_2X = -2.0   # halved — 2x risk
CYCLE_DAYS = 14


# ── Configs ────────────────────────────────────────────────────────────────

NQ_INSTRUMENT = get_instrument("NQ")
ES_INSTRUMENT = get_instrument("ES")

NQ_ASIA_LSI = StrategyConfig(
    strategy="lsi",
    direction_filter="long",
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
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
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
    instrument=NQ_INSTRUMENT,
)

ES_NY_ORB = StrategyConfig(
    strategy="continuation",
    direction_filter="long",
    rr=3.0,
    tp1_ratio=0.2,
    risk_usd=5000.0,
    atr_length=7,
    use_bar_magnifier=True,
    excluded_days=(3,),  # Thu excluded
    sessions=(SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.0,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    ),),
    instrument=ES_INSTRUMENT,
)


def simulate_staggered_accounts(
    trades, start_date, end_date,
    payout_r=5.0, breach_r=-4.0, stagger_days=14,
):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return _empty()

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
    ev = np.mean(capped_rs) if capped_rs else 0.0

    return {
        "total_accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(float(ev), 4),
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_trades_to_payout": round(float(np.mean([r["trades_taken"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "median_days_to_breach": round(float(np.median([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "avg_trades_to_breach": round(float(np.mean([r["trades_taken"] for r in breaches])), 1) if breaches else None,
        "avg_open_r": round(float(np.mean([r["final_r"] for r in opens])), 4) if opens else None,
        "account_details": results,
    }


def _empty():
    return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
            "success_rate": None, "ev_per_account": 0.0,
            "avg_days_to_payout": None, "median_days_to_payout": None,
            "avg_trades_to_payout": None, "avg_days_to_breach": None,
            "median_days_to_breach": None, "avg_trades_to_breach": None,
            "avg_open_r": None, "account_details": []}


def print_comparison(name, trades, metrics):
    print(f"\n{'=' * 120}")
    print(f"  {name}")
    print(f"{'=' * 120}")
    print(f"  Trades: {metrics['total_trades']}  |  WR: {metrics['win_rate']:.1%}  |  Net R: {metrics['total_r']:.2f}  |  Max DD: {metrics['max_drawdown_r']:.2f}R  |  Calmar: {metrics['calmar_ratio']:.2f}  |  Sharpe: {metrics['sharpe_ratio']:.2f}  |  PF: {metrics['profit_factor']:.2f}")

    for label, payout, breach in [("1x ($5k risk)", PAYOUT_1X, BREACH_1X), ("2x ($10k risk)", PAYOUT_2X, BREACH_2X)]:
        acct = simulate_staggered_accounts(trades, START_DATE, END_DATE, payout_r=payout, breach_r=breach, stagger_days=CYCLE_DAYS)
        sr = f"{acct['success_rate']:.1%}" if acct['success_rate'] is not None else "N/A"

        print(f"\n  ── {label}: +{payout}R payout / {breach}R breach ──")
        print(f"  Accounts: {acct['total_accounts']}  |  {acct['payouts']} payouts  |  {acct['breaches']} breaches  |  {acct['open']} open")
        print(f"  Success Rate: {sr}  |  EV per account: {acct['ev_per_account']:.3f}R")

        if acct['avg_days_to_payout'] is not None:
            print(f"  Payout: avg {acct['avg_trades_to_payout']:.1f} trades / {acct['avg_days_to_payout']:.0f} days  (median {acct['median_days_to_payout']:.0f} days)")
        if acct['avg_days_to_breach'] is not None:
            print(f"  Breach: avg {acct['avg_trades_to_breach']:.1f} trades / {acct['avg_days_to_breach']:.0f} days  (median {acct['median_days_to_breach']:.0f} days)")
        if acct['avg_open_r'] is not None:
            print(f"  Open accounts: avg {acct['avg_open_r']:.2f}R")

        # Account-by-account
        print(f"\n  {'Started':<12} {'Outcome':<10} {'Final R':>8} {'Peak R':>7} {'Trough':>7} {'Trades':>6} {'Days':>6} {'Resolved':<12}")
        for d in acct['account_details']:
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

    # ── Load data ──────────────────────────────────────────────────────────
    print("Loading NQ data...")
    nq_df = load_5m_data("NQ_5m.parquet")
    nq_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  NQ 5m: {len(nq_df):,}  |  1m: {len(nq_1m):,}")

    print("Loading ES data...")
    es_df = load_5m_data("ES_5m.parquet")
    es_1m = load_1m_for_5m("ES_5m.parquet")
    print(f"  ES 5m: {len(es_df):,}  |  1m: {len(es_1m):,}")

    # ── Run backtests ──────────────────────────────────────────────────────
    print("\nRunning NQ ASIA LSI Long (rr=1.75, tp1=0.7, gap=1.75)...")
    nq_trades = run_backtest(nq_df, NQ_ASIA_LSI, start_date=START_DATE, end_date=END_DATE, df_1m=nq_1m)
    nq_metrics = compute_metrics(nq_trades)

    print(f"Running ES NY ORB Long (rr=3.0, tp1=0.2, stop=5.0, gap=1.0, excl Thu)...")
    es_trades = run_backtest(es_df, ES_NY_ORB, start_date=START_DATE, end_date=END_DATE, df_1m=es_1m)
    es_metrics = compute_metrics(es_trades)

    # ── Compare 1x vs 2x ──────────────────────────────────────────────────
    print_comparison("NQ ASIA LSI Long — rr=1.75 tp1=0.7 gap=1.75", nq_trades, nq_metrics)
    print_comparison("ES NY ORB Long — rr=3.0 tp1=0.2 stop=5.0 gap=1.0 noThu", es_trades, es_metrics)

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
