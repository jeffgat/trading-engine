#!/usr/bin/env python3
"""Prop firm phase 1 analysis for the 6-leg FAST_V2 portfolio.

Runs all 6 strategies from exec_configs.json FAST_V2 profile, merges trades
chronologically, then simulates staggered prop firm accounts.

Half-risk assumption: each trade risks 0.5R on the account, so thresholds are:
  -8R breach (= -4R at full risk × 2)
  +10R payout (= +5R at full risk × 2)

Date range: last 2 years (2024-03-08 to 2026-03-08).
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Date range ─────────────────────────────────────────────────────────────

START_DATE = "2024-03-08"
END_DATE = "2026-03-08"

# ── Prop firm parameters (half-risk: each trade = 0.5R on account) ─────────

RISK_FRACTION = 0.5  # each trade risks 0.5R on the account
PAYOUT_TARGET = 10.0  # +10R to payout (= +5R full-risk equivalent)
BREACH_LIMIT = -8.0   # -8R to breach (= -4R full-risk equivalent)
CYCLE_DAYS = 14

# ── 6-Leg FAST_V2 configs (from exec_configs.json) ────────────────────────

CONFIGS = {
    "NQ_NY": StrategyConfig(
        sessions=(SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end="09:50",
            entry_start="09:50",
            entry_end="12:00",
            flat_start="15:30",
            flat_end="16:00",
            stop_atr_pct=7.0,
            min_gap_atr_pct=2.5,
        ),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        risk_usd=5000.0,
        excluded_days=(4,),  # Friday
    ),
    "NQ_Asia": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia",
            orb_start="20:00",
            orb_end="20:15",
            entry_start="20:15",
            entry_end="22:30",
            flat_start="04:00",
            flat_end="07:00",
            stop_atr_pct=4.0,
            stop_orb_pct=150.0,
            min_gap_atr_pct=0.9,
            min_gap_orb_pct=15.0,
        ),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=5.0,
        tp1_ratio=0.25,
        atr_length=5,
        risk_usd=5000.0,
        excluded_days=(1,),  # Tuesday
        excluded_dates=("20241218",),
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    ),
    "ES_NY": StrategyConfig(
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
        instrument=ES,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=3.0,
        tp1_ratio=0.2,
        atr_length=7,
        risk_usd=5000.0,
        excluded_days=(3,),  # Thursday
    ),
    "ES_Asia": StrategyConfig(
        sessions=(SessionConfig(
            name="Asia",
            orb_start="20:00",
            orb_end="20:10",
            entry_start="20:10",
            entry_end="03:00",
            flat_start="06:45",
            flat_end="07:00",
            stop_atr_pct=2.5,
            min_gap_atr_pct=1.0,
        ),),
        instrument=ES,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=1.75,
        tp1_ratio=0.3,
        atr_length=5,
        risk_usd=5000.0,
        excluded_dates=("20241218",),
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    ),
    "NQ_Asia_LSI": StrategyConfig(
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
        instrument=NQ,
        strategy="lsi",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=1.75,
        tp1_ratio=0.7,
        atr_length=40,
        risk_usd=5000.0,
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
    ),
    "NQ_NY_LSI": StrategyConfig(
        sessions=(SessionConfig(
            name="NY",
            rth_start="09:30",
            entry_start="09:35",
            entry_end="15:30",
            flat_start="15:50",
            flat_end="16:00",
            stop_atr_pct=0.0,
            min_gap_atr_pct=3.75,
        ),),
        instrument=NQ,
        strategy="lsi",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=2.5,
        tp1_ratio=0.2,
        atr_length=10,
        risk_usd=5000.0,
        lsi_n_left=5,
        lsi_n_right=60,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=5,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        lsi_first_fvg_only=False,
        lsi_clean_path=False,
        lsi_be_swing_n_left=0,
        lsi_cancel_on_swing=False,
        excluded_days=(2, 3),  # Wed, Thu
    ),
}


# ── Staggered account simulation ──────────────────────────────────────────

def simulate_staggered_accounts(
    trade_data: list[dict],
    start_date: str,
    end_date: str,
    payout_r: float,
    breach_r: float,
    stagger_days: int = 14,
) -> dict:
    """Simulate staggered prop firm accounts on merged portfolio trades.

    trade_data: list of {"date": datetime.date, "r": float} already scaled.
    """
    if not trade_data:
        return _empty()

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
    ev = float(np.mean(capped_rs)) if capped_rs else 0.0

    return {
        "total_accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(ev, 4),
        "avg_trades_to_payout": round(float(np.mean([r["trades_taken"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_trades_to_breach": round(float(np.mean([r["trades_taken"] for r in breaches])), 1) if breaches else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "median_days_to_breach": round(float(np.median([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "avg_open_r": round(float(np.mean([r["final_r"] for r in opens])), 4) if opens else None,
        "account_details": results,
    }


def _empty():
    return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
            "success_rate": None, "ev_per_account": 0.0,
            "avg_trades_to_payout": None, "avg_days_to_payout": None,
            "median_days_to_payout": None, "avg_trades_to_breach": None,
            "avg_days_to_breach": None, "median_days_to_breach": None,
            "avg_open_r": None, "account_details": []}


def print_account_table(details):
    print(f"  {'Started':<12} {'Outcome':<10} {'Final R':>8} {'Peak R':>7} {'Trough':>7} {'Trades':>6} {'Days':>6} {'Resolved':<12}")
    print(f"  {'-'*75}")
    for d in details:
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

    print("=" * 100)
    print("6-LEG FAST_V2 PORTFOLIO — Prop Firm Phase 1 Analysis")
    print("=" * 100)
    print(f"Half-risk model: each trade = {RISK_FRACTION}R on account")
    print(f"Thresholds: +{PAYOUT_TARGET}R payout / {BREACH_LIMIT}R breach")
    print(f"New account every {CYCLE_DAYS} days")
    print(f"Period: {START_DATE} to {END_DATE}")
    print()

    # ── Load data ──────────────────────────────────────────────────────────

    print("Loading data...")
    nq_5m = load_5m_data("NQ_5m.parquet")
    nq_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  NQ: {len(nq_5m):,} 5m bars  |  {len(nq_1m):,} 1m bars")

    es_5m = load_5m_data("ES_5m.parquet")
    es_1m = load_1m_for_5m("ES_5m.parquet")
    print(f"  ES: {len(es_5m):,} 5m bars  |  {len(es_1m):,} 1m bars")

    data_map = {
        "NQ": (nq_5m, nq_1m),
        "ES": (es_5m, es_1m),
    }

    # ── Run backtests per leg ──────────────────────────────────────────────

    all_trade_data = []  # merged list of {"date", "r", "leg"}
    leg_stats = {}

    for leg_name, cfg in CONFIGS.items():
        symbol = cfg.instrument.symbol
        df_5m, df_1m = data_map[symbol]

        print(f"\nRunning {leg_name}...")
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, end_date=END_DATE, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

        m = compute_metrics(trades)
        leg_stats[leg_name] = {
            "trades": m["total_trades"],
            "wr": m["win_rate"],
            "net_r": m["total_r"],
            "avg_r": m["avg_r"],
            "max_dd_r": m["max_drawdown_r"],
            "sharpe": m["sharpe_ratio"],
            "calmar": m["calmar_ratio"],
        }

        print(f"  {m['total_trades']} trades  |  WR: {m['win_rate']:.1%}  |  Net R: {m['total_r']:+.1f}  |  DD: {m['max_drawdown_r']:.1f}R  |  Calmar: {m['calmar_ratio']:.2f}")

        for t in filled:
            all_trade_data.append({
                "date": datetime.date.fromisoformat(t.date),
                "r": t.r_multiple * RISK_FRACTION,  # scale to account R
                "leg": leg_name,
            })

    # Sort by date for chronological simulation
    all_trade_data.sort(key=lambda x: x["date"])

    total_trades = len(all_trade_data)
    total_net_r = sum(t["r"] for t in all_trade_data)

    print(f"\n{'=' * 100}")
    print(f"PORTFOLIO SUMMARY")
    print(f"{'=' * 100}")
    print(f"\n  {'Leg':<15} {'Trades':>6} {'WR':>6} {'Net R':>7} {'Avg R':>7} {'Max DD':>7} {'Shrp':>6} {'Calm':>6}")
    print(f"  {'-'*64}")
    for leg_name, s in leg_stats.items():
        print(f"  {leg_name:<15} {s['trades']:>6} {s['wr']:>5.1%} {s['net_r']:>+7.1f} {s['avg_r']:>7.3f} {s['max_dd_r']:>7.1f} {s['sharpe']:>6.2f} {s['calmar']:>6.2f}")

    print(f"\n  Combined: {total_trades} trades  |  Portfolio Net R (at {RISK_FRACTION}R/trade): {total_net_r:+.1f}R")

    # ── Per-leg trade count by month ───────────────────────────────────────

    trades_by_leg_month = {}
    for t in all_trade_data:
        month_key = t["date"].strftime("%Y-%m")
        leg = t["leg"]
        trades_by_leg_month.setdefault(month_key, {}).setdefault(leg, []).append(t["r"])

    # ── Staggered account simulation ───────────────────────────────────────

    print(f"\n{'=' * 100}")
    print(f"PROP FIRM ACCOUNTS: +{PAYOUT_TARGET}R / {BREACH_LIMIT}R  (half-risk, new every {CYCLE_DAYS} days)")
    print(f"{'=' * 100}")

    acct = simulate_staggered_accounts(
        all_trade_data, START_DATE, END_DATE,
        payout_r=PAYOUT_TARGET, breach_r=BREACH_LIMIT, stagger_days=CYCLE_DAYS,
    )

    sr = acct["success_rate"]
    sr_str = f"{sr:.1%}" if sr is not None else "N/A"

    print(f"\n  Total accounts: {acct['total_accounts']}")
    print(f"  Payouts:  {acct['payouts']}")
    print(f"  Breaches: {acct['breaches']}")
    print(f"  Open:     {acct['open']}")
    print(f"\n  Success Rate (resolved): {sr_str}")
    print(f"  EV per account: {acct['ev_per_account']:+.3f}R")

    if acct["avg_days_to_payout"] is not None:
        print(f"  Avg trades to payout: {acct['avg_trades_to_payout']:.1f}")
        print(f"  Avg days to payout:   {acct['avg_days_to_payout']:.0f}  (median {acct['median_days_to_payout']:.0f})")
    if acct["avg_days_to_breach"] is not None:
        print(f"  Avg trades to breach: {acct['avg_trades_to_breach']:.1f}")
        print(f"  Avg days to breach:   {acct['avg_days_to_breach']:.0f}  (median {acct['median_days_to_breach']:.0f})")
    if acct["avg_open_r"] is not None:
        print(f"  Open accounts avg R:  {acct['avg_open_r']:+.3f}")

    # ── Breach cluster analysis ────────────────────────────────────────────

    details = acct["account_details"]
    breach_dates = [d["outcome_date"] for d in details if d["outcome"] == "breach"]
    if breach_dates:
        print(f"\n  Breach dates: {', '.join(breach_dates)}")

    # Count consecutive breaches in account sequence
    outcomes = [d["outcome"] for d in details]
    max_consec_breach = 0
    cur_streak = 0
    for o in outcomes:
        if o == "breach":
            cur_streak += 1
            max_consec_breach = max(max_consec_breach, cur_streak)
        else:
            cur_streak = 0
    print(f"  Max consecutive breaches: {max_consec_breach}")

    # ── Account-by-account table ───────────────────────────────────────────

    print(f"\n  Account-by-account:")
    print_account_table(details)

    # ── Also run at full-risk thresholds for comparison ─────────────────────

    print(f"\n\n{'=' * 100}")
    print(f"COMPARISON: FULL-RISK thresholds +5R / -4R  (same trades at {RISK_FRACTION}R each)")
    print(f"{'=' * 100}")

    acct_full = simulate_staggered_accounts(
        all_trade_data, START_DATE, END_DATE,
        payout_r=5.0, breach_r=-4.0, stagger_days=CYCLE_DAYS,
    )

    sr2 = acct_full["success_rate"]
    sr2_str = f"{sr2:.1%}" if sr2 is not None else "N/A"

    print(f"\n  Total accounts: {acct_full['total_accounts']}")
    print(f"  Payouts:  {acct_full['payouts']}")
    print(f"  Breaches: {acct_full['breaches']}")
    print(f"  Open:     {acct_full['open']}")
    print(f"\n  Success Rate (resolved): {sr2_str}")
    print(f"  EV per account: {acct_full['ev_per_account']:+.3f}R")

    if acct_full["avg_days_to_payout"] is not None:
        print(f"  Avg trades to payout: {acct_full['avg_trades_to_payout']:.1f}")
        print(f"  Avg days to payout:   {acct_full['avg_days_to_payout']:.0f}  (median {acct_full['median_days_to_payout']:.0f})")
    if acct_full["avg_days_to_breach"] is not None:
        print(f"  Avg trades to breach: {acct_full['avg_trades_to_breach']:.1f}")
        print(f"  Avg days to breach:   {acct_full['avg_days_to_breach']:.0f}  (median {acct_full['median_days_to_breach']:.0f})")

    print(f"\n  Account-by-account:")
    print_account_table(acct_full["account_details"])

    print(f"\n\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
