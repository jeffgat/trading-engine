#!/usr/bin/env python3
"""4-Leg Portfolio Backtest — NQ + CL + RTY + ES (no GC/SI).

Legs:
  1. NQ Asia Cont Long — R9 restart (15m ORB, ATR 4.0%, RR 3.0, long, excl Tue, ICF)
  2. CL LDN Cont Long  — LDN-1 (30m ORB, ATR 8.0%, RR 3.5, long)
  3. RTY NY Cont Both  — NY-4 (10m ORB, ORB 100%, RR 3.0, both)
  4. ES NY Cont Long   — Final (15m ORB, ATR 5.0%, RR 5.0, long, excl Thu, dual floor)

Outputs:
  - Per-leg and combined equity curves
  - Daily R correlation matrix
  - Combined R by year
  - Phase 3 prop-firm payout simulation on combined portfolio
  - Save to remote DB
"""

from __future__ import annotations

import datetime
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import TUE, THU
from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile,
    PropFirmProfile,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
    build_funded_first_payout_scorecard,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, CL, RTY, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "portfolio_4leg"
HOLDOUT_START = "2025-01-01"


FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0, starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0, max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0, risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0, reset_fee=50.0, payout_split=0.80,
    payout_target_r=5.0, breach_limit_r=-4.0, daily_loss_limit_r=-2.0,
    min_trading_days=5, cohort_sizes=(10, 25, 50), block_size_days=14)


def build_legs():
    # Leg 1: NQ Asia Cont Long (R9 restart final)
    nq_session = SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=4.0, min_gap_atr_pct=0.90)
    nq_config = StrategyConfig(
        sessions=(nq_session,), instrument=NQ, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
        rr=3.0, tp1_ratio=0.6, atr_length=5, impulse_close_filter=True,
        name="NQ Asia Cont Long R9")

    # Leg 2: CL LDN Cont Long (LDN-1)
    cl_session = SessionConfig(
        name="LDN", orb_start="03:00", orb_end="03:30",
        entry_start="03:30", entry_end="07:00",
        flat_start="08:20", flat_end="08:25",
        stop_atr_pct=8.0, min_gap_atr_pct=1.0)
    cl_config = StrategyConfig(
        sessions=(cl_session,), instrument=CL, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
        rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="CL LDN Cont Long")

    # Leg 3: RTY NY Cont Both (NY-4)
    rty_session = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:40",
        entry_start="09:40", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_orb_pct=100.0, min_gap_atr_pct=1.0)
    rty_config = StrategyConfig(
        sessions=(rty_session,), instrument=RTY, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
        rr=3.0, tp1_ratio=0.4, atr_length=14,
        name="RTY NY Cont Both")

    # Leg 4: ES NY Cont Long (Final)
    es_session = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0, min_gap_atr_pct=0.25,
        min_stop_points=3.0, min_tp1_points=3.0)
    es_config = StrategyConfig(
        sessions=(es_session,), instrument=ES, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
        rr=5.0, tp1_ratio=0.2, atr_length=7,
        name="ES NY Cont Long")

    return {
        "NQ_Asia_L": {"config": nq_config, "dow_excl": {TUE}, "instrument": NQ},
        "CL_LDN_L": {"config": cl_config, "dow_excl": set(), "instrument": CL},
        "RTY_NY_B": {"config": rty_config, "dow_excl": set(), "instrument": RTY},
        "ES_NY_L": {"config": es_config, "dow_excl": {THU}, "instrument": ES},
    }


def _filled(trades):
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def daily_r_series(trades) -> dict[str, float]:
    daily = defaultdict(float)
    for t in trades:
        if t.exit_type != EXIT_NO_FILL:
            daily[t.date] += t.r_multiple
    return dict(daily)


def main():
    print("4-Leg Portfolio Backtest + Phase 3 Prop Simulation")
    print("=" * 70)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    legs = build_legs()

    # Load all data
    print("\nLoading data for all instruments...")
    data = {}
    for leg_name, leg_info in legs.items():
        inst = leg_info["instrument"]
        sym = inst.symbol
        if sym not in data:
            print(f"  {sym}...", end=" ", flush=True)
            d5 = load_5m_data(inst.data_file)
            d1m = load_1m_for_5m(inst.data_file)
            d1s = load_1s_for_5m(inst.data_file)
            data[sym] = {"5m": d5, "1m": d1m, "1s": d1s}
            print(f"{len(d5):,} 5m bars")

    # Run each leg
    print(f"\n{'=' * 70}")
    print("PER-LEG BACKTESTS")
    print(f"{'=' * 70}")

    leg_trades = {}
    leg_daily_r = {}

    for leg_name, leg_info in legs.items():
        config = leg_info["config"]
        inst = leg_info["instrument"]
        sym = inst.symbol
        dow_excl = leg_info["dow_excl"]

        print(f"\n  {leg_name}: {config.name}")
        d = data[sym]
        trades = run_backtest(d["5m"], config, df_1m=d["1m"], df_1s=d["1s"])

        if dow_excl:
            trades = [t for t in trades if t.exit_type == EXIT_NO_FILL or
                      datetime.date.fromisoformat(t.date).weekday() not in dow_excl]

        filled = _filled(trades)
        metrics = compute_metrics(trades)
        leg_trades[leg_name] = trades
        leg_daily_r[leg_name] = daily_r_series(trades)

        print(f"    {len(filled)} trades | Net R: {metrics.get('total_r', 0):+.1f} | "
              f"Calmar: {metrics.get('calmar_ratio', 0) or 0:.2f} | "
              f"Sharpe: {metrics.get('sharpe_ratio', 0) or 0:.2f} | "
              f"DD: {metrics.get('max_drawdown_r', 0):.1f}R | "
              f"WR: {metrics.get('win_rate', 0):.1%}")

        r_by_year = metrics.get("r_by_year", {})
        if r_by_year:
            print(f"    R/yr: {' '.join(f'{k}:{float(v):+.1f}' for k, v in sorted(r_by_year.items()))}")

    # Combined daily R
    print(f"\n{'=' * 70}")
    print("CORRELATION ANALYSIS")
    print(f"{'=' * 70}")

    all_dates = sorted(set().union(*[set(dr.keys()) for dr in leg_daily_r.values()]))
    df_daily = pd.DataFrame(index=all_dates)
    for leg_name, dr in leg_daily_r.items():
        df_daily[leg_name] = pd.Series(dr)
    df_daily = df_daily.fillna(0.0)

    corr = df_daily.corr()
    print("\n  Daily R Correlation Matrix:")
    print(f"  {'':>12s}", end="")
    for c in corr.columns:
        print(f" {c:>12s}", end="")
    print()
    for r in corr.index:
        print(f"  {r:>12s}", end="")
        for c in corr.columns:
            print(f" {corr.loc[r, c]:>12.3f}", end="")
        print()

    mask = np.triu(np.ones(corr.shape), k=1).astype(bool)
    avg_corr = corr.where(mask).stack().mean()
    print(f"\n  Average pairwise correlation: {avg_corr:.3f}")

    df_daily["PORTFOLIO"] = df_daily.sum(axis=1)

    df_daily_dt = df_daily.copy()
    df_daily_dt.index = pd.to_datetime(df_daily_dt.index)
    yearly = df_daily_dt.resample("YE").sum()

    print(f"\n  Combined Portfolio R by Year:")
    print(f"  {'Year':>6s}", end="")
    for leg in list(leg_daily_r.keys()) + ["PORTFOLIO"]:
        print(f" {leg:>12s}", end="")
    print()
    for idx, row in yearly.iterrows():
        print(f"  {idx.year:>6d}", end="")
        for leg in list(leg_daily_r.keys()) + ["PORTFOLIO"]:
            print(f" {row[leg]:>+12.1f}", end="")
        print()

    portfolio_r = df_daily["PORTFOLIO"].values
    cum_r = np.cumsum(portfolio_r)
    peak = np.maximum.accumulate(cum_r)
    dd = cum_r - peak
    max_dd = float(dd.min())
    total_r = float(cum_r[-1])
    n_years = len(yearly)
    avg_annual = total_r / max(n_years, 1)
    calmar = avg_annual / abs(max_dd) if max_dd != 0 else 0
    sharpe = float(np.mean(portfolio_r) / np.std(portfolio_r) * np.sqrt(252)) if np.std(portfolio_r) > 0 else 0
    neg_years = int((yearly["PORTFOLIO"] < 0).sum())

    print(f"\n  Portfolio Summary:")
    print(f"    Total R: {total_r:+.1f} | Avg Annual: {avg_annual:+.1f} | Max DD: {max_dd:.1f}R")
    print(f"    Calmar: {calmar:.2f} | Sharpe: {sharpe:.2f} | Negative years: {neg_years}")

    pre_mask = df_daily.index < HOLDOUT_START
    ho_mask = df_daily.index >= HOLDOUT_START
    pre_r = df_daily.loc[pre_mask, "PORTFOLIO"].values
    ho_r = df_daily.loc[ho_mask, "PORTFOLIO"].values
    pre_total = float(np.sum(pre_r))
    ho_total = float(np.sum(ho_r))
    pre_dd = float((np.cumsum(pre_r) - np.maximum.accumulate(np.cumsum(pre_r))).min())
    ho_dd = float((np.cumsum(ho_r) - np.maximum.accumulate(np.cumsum(ho_r))).min()) if len(ho_r) > 0 else 0

    print(f"\n    Pre-holdout (<{HOLDOUT_START}): {pre_total:+.1f}R, DD {pre_dd:.1f}R")
    print(f"    Holdout (>={HOLDOUT_START}): {ho_total:+.1f}R, DD {ho_dd:.1f}R")

    # Phase 3: Prop simulation
    print(f"\n{'=' * 70}")
    print("PHASE 3 — PROP FIRM PAYOUT SIMULATION (Combined Portfolio)")
    print(f"{'=' * 70}")

    all_portfolio_trades = []
    for leg_name, trades in leg_trades.items():
        all_portfolio_trades.extend(_filled(trades))
    all_portfolio_trades.sort(key=lambda t: t.date)

    all_trade_dates = sorted(set(t.date for t in all_portfolio_trades))
    pre_dates = [d for d in all_trade_dates if d < HOLDOUT_START]
    holdout_dates = [d for d in all_trade_dates if d >= HOLDOUT_START]

    pre_trades = [t for t in all_portfolio_trades if t.date < HOLDOUT_START]
    ho_trades = [t for t in all_portfolio_trades if t.date >= HOLDOUT_START]

    print(f"\n  Pre-holdout: {len(pre_trades)} trades across {len(pre_dates)} trading days")
    prop_outcomes = simulate_account_attempts(
        specialist_name="Portfolio_4leg", trades=pre_trades,
        trading_dates=pre_dates, profile=PROP_PROFILE, risk_per_r_usd=5000.0)
    prop_sc = build_prop_scorecard(prop_outcomes, PROP_PROFILE)
    pr = prop_sc.get("payout_rate", prop_sc.get("first_payout_rate", 0))
    br = prop_sc.get("breach_rate", 0)
    ev = prop_sc.get("ev_per_start_usd", prop_sc.get("ev_per_attempt", 0))
    days = prop_sc.get("average_days_to_payout", prop_sc.get("median_days_to_payout", 0))
    print(f"    PR: {pr:.1%} | BR: {br:.1%} | EV: ${ev} | Days: {days:.0f}" if days else f"    PR: {pr:.1%} | BR: {br:.1%} | EV: ${ev}")

    funded = simulate_funded_first_payouts(
        specialist_name="Portfolio_4leg", trades=pre_trades,
        trading_dates=pre_dates, profile=FUNDED_PROFILE)
    f_sc = build_funded_first_payout_scorecard(funded, FUNDED_PROFILE)
    f_pr = f_sc.get("payout_rate", f_sc.get("first_payout_rate", 0))
    f_ev = f_sc.get("ev_per_start_usd", f_sc.get("ev_per_attempt", 0))
    f_days = f_sc.get("average_days_to_payout", f_sc.get("median_days_to_payout", 0))
    print(f"  Funded: PR {f_pr:.1%} | EV ${f_ev} | Days {f_days:.0f}" if f_days else f"  Funded: PR {f_pr:.1%} | EV ${f_ev}")

    if ho_trades:
        print(f"\n  Holdout: {len(ho_trades)} trades across {len(holdout_dates)} trading days")
        ho_prop = simulate_account_attempts(
            specialist_name="Portfolio_4leg_HO", trades=ho_trades,
            trading_dates=holdout_dates, profile=PROP_PROFILE, risk_per_r_usd=5000.0)
        ho_sc = build_prop_scorecard(ho_prop, PROP_PROFILE)
        ho_pr = ho_sc.get("payout_rate", ho_sc.get("first_payout_rate", 0))
        ho_ev = ho_sc.get("ev_per_start_usd", ho_sc.get("ev_per_attempt", 0))
        ho_days = ho_sc.get("average_days_to_payout", ho_sc.get("median_days_to_payout", 0))
        print(f"    PR: {ho_pr:.1%} | EV: ${ho_ev} | Days: {ho_days:.0f}" if ho_days else f"    PR: {ho_pr:.1%} | EV: ${ho_ev}")

        ho_funded = simulate_funded_first_payouts(
            specialist_name="Portfolio_4leg_HO", trades=ho_trades,
            trading_dates=holdout_dates, profile=FUNDED_PROFILE)
        hf_sc = build_funded_first_payout_scorecard(ho_funded, FUNDED_PROFILE)
        hf_pr = hf_sc.get("payout_rate", hf_sc.get("first_payout_rate", 0))
        hf_ev = hf_sc.get("ev_per_start_usd", hf_sc.get("ev_per_attempt", 0))
        print(f"  Funded HO: PR {hf_pr:.1%} | EV ${hf_ev}")

    # Save to DB
    print(f"\n{'=' * 70}")
    print("SAVING TO REMOTE DB")
    print(f"{'=' * 70}")

    all_sessions = tuple(leg_info["config"].sessions[0] for leg_info in legs.values())
    combined_config = StrategyConfig(
        sessions=all_sessions, instrument=NQ, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
        rr=1.0, tp1_ratio=1.0, atr_length=14,
        name="4-Leg Portfolio (NQ+CL+RTY+ES)",
        notes=(
            f"4-leg uncorrelated portfolio (no GC/SI). Avg pairwise corr: {avg_corr:.3f}. "
            "Legs: NQ Asia Long R9 (rr=3.0, tp1=0.6, stop=4.0%, 15m ORB, excl Tue, ICF) | "
            "CL LDN Long LDN-1 (rr=3.5, tp1=0.6, stop=8.0%, 30m ORB) | "
            "RTY NY Both NY-4 (rr=3.0, tp1=0.4, ORB 100% stop, 10m ORB) | "
            "ES NY Long Final (rr=5.0, tp1=0.2, stop=5.0%, 15m ORB, excl Thu, dual floor). "
            f"Total R: {total_r:+.1f} | Calmar: {calmar:.2f} | Sharpe: {sharpe:.2f} | "
            f"DD: {max_dd:.1f}R | {neg_years} neg years. "
            f"Holdout: {ho_total:+.1f}R. "
            f"Funded: PR {f_pr:.1%}, EV ${f_ev:.0f}."
        ),
    )

    db_result = results_to_dict(
        all_portfolio_trades, combined_config,
        include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(db_result)
    print(f"  Saved as: {result_id}")

    # Save JSON
    results = {
        "legs": list(leg_daily_r.keys()),
        "correlation_matrix": corr.to_dict(),
        "avg_pairwise_correlation": round(avg_corr, 4),
        "portfolio_total_r": round(total_r, 2),
        "portfolio_calmar": round(calmar, 2),
        "portfolio_sharpe": round(sharpe, 2),
        "portfolio_max_dd": round(max_dd, 2),
        "negative_years": neg_years,
        "pre_holdout_r": round(pre_total, 2),
        "holdout_r": round(ho_total, 2),
    }
    OUTPUT_DIR.joinpath("portfolio_results.json").write_text(
        json.dumps(results, indent=2, sort_keys=False, default=str))

    print(f"\n{'=' * 70}")
    print(f"Total time: {time.time() - t0:.0f}s")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
