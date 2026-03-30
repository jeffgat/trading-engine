#!/usr/bin/env python3
"""Prop firm phase 1 analysis for the 5-leg FAST_V2 portfolio.

Runs all 5 strategies from the FAST_V2 exec config, evaluates each leg
independently, then simulates staggered prop firm accounts per leg.

Hard constraints enforced: tp1_ratio * rr >= 1.0.
Legs where the original tp1_ratio violates this have tp1_ratio bumped
to the minimum valid value.

Thresholds: +5R payout / -4R breach, new account every 14 calendar days.
Date range: 2016-01-01 to present.
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter, FRI, TUE, WED, THU
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Date range ─────────────────────────────────────────────────────────────

START_DATE = "2016-01-01"

# ── Prop firm parameters ───────────────────────────────────────────────────

PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14

# ── 5-Leg FAST_V2 configs ─────────────────────────────────────────────────

ALL_LEGS = {
    "NQ_NY": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=8.0,
                min_gap_atr_pct=2.25,
            ),),
            instrument=NQ,
            strategy="continuation",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=2.5,
            tp1_ratio=0.4,  # bumped from 0.3 to satisfy tp1*rr >= 1.0
            atr_length=14,
            risk_usd=5000.0,
            excluded_days=(FRI,),
            excluded_dates=("20241218",),
        ),
        "instrument": "NQ",
        "dow_exclude": {FRI},
    },
    "NQ_Asia": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="22:30",
                flat_start="04:00",
                flat_end="04:10",
                stop_orb_pct=150.0,
                min_gap_orb_pct=15.0,
            ),),
            instrument=NQ,
            strategy="continuation",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=5.0,
            tp1_ratio=0.25,
            atr_length=5,
            risk_usd=5000.0,
            excluded_days=(TUE,),
            excluded_dates=("20241218",),
        ),
        "instrument": "NQ",
        "dow_exclude": {TUE},
    },
    "ES_Asia": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:10",
                entry_start="20:10",
                entry_end="03:00",
                flat_start="06:45",
                flat_end="06:55",
                stop_atr_pct=2.5,
                min_gap_atr_pct=1.0,
            ),),
            instrument=ES,
            strategy="continuation",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=1.75,
            tp1_ratio=0.58,  # bumped from 0.3 to satisfy tp1*rr >= 1.0
            atr_length=5,
            risk_usd=5000.0,
            excluded_dates=("20241218",),
        ),
        "instrument": "ES",
        "dow_exclude": set(),
    },
    "NQ_Asia_LSI": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="ASIA",
                rth_start="20:00",
                orb_start="20:00",
                orb_end="20:05",
                entry_start="20:45",
                entry_end="22:00",
                flat_start="00:00",
                flat_end="00:10",
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
            excluded_dates=("20241218",),
        ),
        "instrument": "NQ",
        "dow_exclude": set(),
    },
    "NQ_NY_LSI": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY",
                rth_start="09:30",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="10:10",
                entry_end="14:30",
                flat_start="15:50",
                flat_end="16:00",
                min_gap_atr_pct=3.75,
            ),),
            instrument=NQ,
            strategy="lsi",
            direction_filter="long",
            use_bar_magnifier=True,
            rr=2.5,
            tp1_ratio=0.4,  # bumped from 0.2 to satisfy tp1*rr >= 1.0
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
            excluded_days=(WED, THU),
            excluded_dates=("20241218",),
        ),
        "instrument": "NQ",
        "dow_exclude": {WED, THU},
    },
}


# ── Staggered account simulation ──────────────────────────────────────────

def simulate_staggered_accounts(trades, start_date, end_date, payout_r, breach_r, stagger_days=14):
    """Simulate staggered prop firm accounts."""
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

    # Max consecutive breaches
    max_consec = 0
    cur_streak = 0
    for r in results:
        if r["outcome"] == "breach":
            cur_streak += 1
            max_consec = max(max_consec, cur_streak)
        else:
            cur_streak = 0

    return {
        "total_accounts": len(results),
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(ev, 4),
        "avg_days_to_payout": round(float(np.mean([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "median_days_to_payout": round(float(np.median([r["calendar_days"] for r in payouts])), 1) if payouts else None,
        "avg_days_to_breach": round(float(np.mean([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "median_days_to_breach": round(float(np.median([r["calendar_days"] for r in breaches])), 1) if breaches else None,
        "avg_open_r": round(float(np.mean([r["final_r"] for r in opens])), 4) if opens else None,
        "max_consec_breach": max_consec,
        "account_details": results,
    }


def _empty():
    return {
        "total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
        "success_rate": None, "ev_per_account": 0.0,
        "avg_days_to_payout": None, "median_days_to_payout": None,
        "avg_days_to_breach": None, "median_days_to_breach": None,
        "avg_open_r": None, "max_consec_breach": 0, "account_details": [],
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

    print("=" * 110)
    print("5-LEG FAST_V2 PORTFOLIO -- Prop Firm Phase 1 Analysis (Per-Leg)")
    print("=" * 110)
    print(f"Thresholds: +{PAYOUT_TARGET}R payout / {BREACH_LIMIT}R breach")
    print(f"New account every {CYCLE_DAYS} days")
    print(f"Period: {START_DATE} to present")
    print()

    # ── Load data ──────────────────────────────────────────────────────────

    print("Loading data...")
    nq_5m = load_5m_data("NQ_5m.parquet")
    nq_1m = load_1m_for_5m("NQ_5m.parquet")
    try:
        nq_1s = load_1s_for_5m("NQ_5m.parquet")
    except (FileNotFoundError, Exception):
        nq_1s = None
    print(f"  NQ: {len(nq_5m):,} 5m bars  |  {len(nq_1m):,} 1m bars  |  1s: {'yes' if nq_1s is not None else 'no'}")

    es_5m = load_5m_data("ES_5m.parquet")
    es_1m = load_1m_for_5m("ES_5m.parquet")
    try:
        es_1s = load_1s_for_5m("ES_5m.parquet")
    except (FileNotFoundError, Exception):
        es_1s = None
    print(f"  ES: {len(es_5m):,} 5m bars  |  {len(es_1m):,} 1m bars  |  1s: {'yes' if es_1s is not None else 'no'}")

    data_map = {
        "NQ": {"5m": nq_5m, "1m": nq_1m, "1s": nq_1s},
        "ES": {"5m": es_5m, "1m": es_1m, "1s": es_1s},
    }

    # Determine end date from available data
    end_date = nq_5m.index[-1].strftime("%Y-%m-%d")

    # ── Run backtests per leg ──────────────────────────────────────────────

    leg_results = {}

    for leg_name, leg_info in ALL_LEGS.items():
        cfg = leg_info["config"]
        symbol = leg_info["instrument"]
        d = data_map[symbol]

        print(f"\n{'─' * 90}")
        print(f"  LEG: {leg_name}")
        print(f"{'─' * 90}")

        # Run backtest
        trades = run_backtest(
            d["5m"], cfg,
            start_date=START_DATE, end_date=end_date,
            df_1m=d["1m"], df_1s=d["1s"],
        )

        # Apply DOW filter (post-trade)
        dow_excl = leg_info["dow_exclude"]
        if dow_excl:
            trades_filtered = apply_dow_filter(trades, dow_excl)
        else:
            trades_filtered = trades

        # Compute metrics
        m = compute_metrics(trades_filtered)
        leg_results[leg_name] = {"metrics": m, "trades": trades_filtered}

        # Print per-leg results
        print(f"  Trades: {m['total_trades']}  |  WR: {m['win_rate']:.1%}  |  PF: {m['profit_factor']:.2f}  |  Net R: {m['total_r']:+.1f}")
        print(f"  Sharpe: {m['sharpe_ratio']:.2f}  |  Calmar: {m['calmar_ratio']:.2f}  |  Max DD: {m['max_drawdown_r']:.2f}R")

        # R by year
        if "r_by_year" in m and m["r_by_year"]:
            years = sorted(m["r_by_year"].items())
            yr_str = "  ".join(f"{yr}:{r:+.1f}" for yr, r in years)
            print(f"  R by year: {yr_str}")

        # Simulate staggered accounts
        acct = simulate_staggered_accounts(
            trades_filtered, START_DATE, end_date,
            payout_r=PAYOUT_TARGET, breach_r=BREACH_LIMIT, stagger_days=CYCLE_DAYS,
        )

        sr = acct["success_rate"]
        sr_str = f"{sr:.1%}" if sr is not None else "N/A"
        adp = f"{acct['avg_days_to_payout']:.0f}" if acct["avg_days_to_payout"] is not None else "-"
        adb = f"{acct['avg_days_to_breach']:.0f}" if acct["avg_days_to_breach"] is not None else "-"

        print(f"\n  Prop Accounts: P={acct['payouts']} / B={acct['breaches']} / O={acct['open']}  "
              f"(total={acct['total_accounts']})")
        print(f"  Success Rate: {sr_str}  |  EV: {acct['ev_per_account']:+.3f}R  |  "
              f"Max Consec Breach: {acct['max_consec_breach']}")
        print(f"  Avg Days to Payout: {adp}  |  Avg Days to Breach: {adb}")

        leg_results[leg_name]["prop"] = acct

    # ── Summary table ──────────────────────────────────────────────────────

    print(f"\n\n{'=' * 140}")
    print("SUMMARY TABLE")
    print(f"{'=' * 140}")
    print(f"{'Leg':<15} {'Tr':>5} {'WR%':>6} {'PF':>5} {'Net R':>7} {'Shrp':>5} {'Calm':>5} {'DD':>6} "
          f"{'P/B/O':>10} {'Succ%':>6} {'EV':>6} {'MaxCB':>5} {'AvgDP':>5}")
    print("-" * 140)

    for leg_name, lr in leg_results.items():
        m = lr["metrics"]
        a = lr["prop"]
        sr = f"{a['success_rate']:.0%}" if a["success_rate"] is not None else "N/A"
        adp = f"{a['avg_days_to_payout']:.0f}" if a["avg_days_to_payout"] is not None else "-"
        pbo = f"{a['payouts']}/{a['breaches']}/{a['open']}"
        print(f"{leg_name:<15} {m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['total_r']:>+7.1f} {m['sharpe_ratio']:>5.2f} {m['calmar_ratio']:>5.2f} {m['max_drawdown_r']:>6.2f} "
              f"{pbo:>10} {sr:>6} {a['ev_per_account']:>+6.3f} {a['max_consec_breach']:>5} {adp:>5}")

    # ── R by year for each leg ─────────────────────────────────────────────

    print(f"\n\n{'=' * 140}")
    print("R BY YEAR (per leg)")
    print(f"{'=' * 140}")

    # Collect all years
    all_years = set()
    for lr in leg_results.values():
        if "r_by_year" in lr["metrics"]:
            all_years.update(lr["metrics"]["r_by_year"].keys())
    all_years = sorted(all_years)

    if all_years:
        yr_header = "  ".join(f"{yr:>7}" for yr in all_years)
        print(f"{'Leg':<15} {yr_header}")
        print("-" * (15 + 9 * len(all_years)))

        for leg_name, lr in leg_results.items():
            r_by_year = lr["metrics"].get("r_by_year", {})
            yr_vals = "  ".join(f"{r_by_year.get(yr, 0.0):>+7.1f}" for yr in all_years)
            print(f"{leg_name:<15} {yr_vals}")

    print(f"\nTotal time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
