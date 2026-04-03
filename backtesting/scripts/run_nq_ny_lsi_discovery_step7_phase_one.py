#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 7: Phase-one robust pipeline (payout economics).

Evaluates the promoted candidate (NEW-A gated) for first-payout viability:
  - Staggered funded accounts (new every 14 days)
  - +5R payout / -4R breach thresholds
  - Pre-holdout + holdout comparison

Uses the regime-gated WF OOS trades for pre-holdout payout simulation,
then runs a clean holdout test (2025-04-01 onward) with the WF mode params.
"""

import datetime
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
)
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, run_monte_carlo
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints, evaluate_constraints, evaluate_constraints_mc,
)

# ── Config ────────────────────────────────────────────────────────────────
WF_START = "2016-01-01"
PRE_HOLDOUT_END = "2025-03-31"
HOLDOUT_START = "2025-04-01"
N_WORKERS = 4
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

# Payout model
PAYOUT_TARGET = 5.0
BREACH_LIMIT = -4.0
CYCLE_DAYS = 14

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

CANDIDATE = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=10,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="NQ NY LSI NEW-A gated RR2 TP0.5",
)

# WF mode params from Step 4: gap=5.0, atr=14 (4/6 folds each)
MODE_PARAMS = {"ny_min_gap_atr_pct": 5.0, "atr_length": 14}
WF_RANGES = {"ny_min_gap_atr_pct": [3.75, 5.0, 7.5], "atr_length": [10, 14]}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def simulate_staggered_accounts(trades, start_date, end_date,
                                 payout_r=PAYOUT_TARGET, breach_r=BREACH_LIMIT,
                                 stagger_days=CYCLE_DAYS):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return {"total_accounts": 0, "payouts": 0, "breaches": 0, "open": 0,
                "success_rate": None, "ev_per_account": 0, "details": []}

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

        for t in trade_data:
            if t["date"] < acct_start:
                continue
            cum_r += t["r"]
            trades_taken += 1
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
            "start": acct_start.isoformat(), "outcome": outcome,
            "final_r": round(cum_r, 3), "trades": trades_taken, "days": calendar_days,
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

    return {
        "total_accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "success_rate": round(success_rate, 4) if success_rate is not None else None,
        "ev_per_account": round(float(np.mean(capped_rs)), 4) if capped_rs else 0,
        "median_days_payout": round(float(np.median([r["days"] for r in payouts])), 0) if payouts else None,
        "median_days_breach": round(float(np.median([r["days"] for r in breaches])), 0) if breaches else None,
        "details": results,
    }


def fmt(p): return "PASS" if p else "FAIL"

def section(title):
    print(f"\n{'='*80}\n  {title}\n{'='*80}\n", flush=True)


def main():
    t0 = time.time()

    section("STEP 7: PHASE-ONE ROBUST PIPELINE")
    print(f"  Candidate: NEW-A gated (RR=2.0, TP1=0.5, ATR=10)", flush=True)
    print(f"  WF mode params: {MODE_PARAMS}", flush=True)
    print(f"  Payout model: +{PAYOUT_TARGET}R / {BREACH_LIMIT}R, new account every {CYCLE_DAYS} days", flush=True)
    print(f"  Holdout: {HOLDOUT_START} onward", flush=True)

    # Load data
    print("\nLoading data...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)

    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    # ── Phase 1: Structural Viability (pre-holdout, gated) ────────────
    section("PHASE 1: STRUCTURAL VIABILITY (pre-holdout, gated)")

    df_pre = df_5m.loc[:PRE_HOLDOUT_END]
    df_pre_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    trades_pre = run_backtest(df_pre, CANDIDATE, start_date=WF_START,
                               df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
    trades_pre_gated = gate_fn(trades_pre)
    m_pre = compute_metrics(trades_pre_gated)

    print(f"  Trades: {m_pre['total_trades']}", flush=True)
    print(f"  WR: {m_pre['win_rate']:.1%}  PF: {m_pre['profit_factor']:.2f}", flush=True)
    print(f"  Net R: {m_pre['total_r']:.1f}R  DD: {m_pre['max_drawdown_r']:.1f}R  Calmar: {m_pre['calmar_ratio']:.2f}", flush=True)
    print(f"  Sharpe: {m_pre['sharpe_ratio']:.3f}", flush=True)
    rby = m_pre.get("r_by_year", {})
    for y, r in sorted(rby.items()):
        flag = " <--" if r < 0 else ""
        print(f"    {y}: {r:>+7.1f}R{flag}", flush=True)

    # ── Phase 2: Gated Walk-Forward (reuse from Step 4 params) ────────
    section("PHASE 2: GATED WALK-FORWARD")

    df_wf = df_5m.loc[:PRE_HOLDOUT_END]
    df_wf_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_wf_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    wf_result = run_walkforward(
        df_wf, CANDIDATE, WF_RANGES,
        is_months=36, oos_months=12, step_months=12,
        anchored=False, objective="sharpe",
        n_workers=N_WORKERS, start_date=WF_START,
        df_1m=df_wf_1m, df_1s=df_wf_1s,
        gate_fn=gate_fn,
    )

    print(f"  {len(wf_result.folds)} folds, WFE: {wf_result.walk_forward_efficiency:.3f}", flush=True)
    oos_m = wf_result.combined_oos_metrics
    print(f"  OOS: {oos_m['total_trades']}tr, Sharpe {oos_m['sharpe_ratio']:.2f}, "
          f"Calmar {oos_m['calmar_ratio']:.2f}, Net R {oos_m['total_r']:.1f}", flush=True)

    stability = analyze_parameter_stability(wf_result, param_ranges=WF_RANGES)
    print(f"  Stability: {stability.overall_score:.3f} ({stability.interpretation})", flush=True)
    for p in stability.params:
        print(f"    {p.name:<24} mode={p.mode:<6} freq={p.mode_frequency}/{stability.n_folds}", flush=True)

    # ── Phase 3: First-Payout Scorecard (on WF OOS) ──────────────────
    section("PHASE 3: FIRST-PAYOUT SCORECARD (WF OOS)")

    # Get OOS date range
    oos_dates = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    oos_start = min(oos_dates) if oos_dates else WF_START
    oos_end = max(oos_dates) if oos_dates else PRE_HOLDOUT_END

    acct = simulate_staggered_accounts(wf_result.combined_oos_trades, oos_start, oos_end)

    print(f"  Accounts: {acct['total_accounts']} started", flush=True)
    print(f"  Payouts: {acct['payouts']}  Breaches: {acct['breaches']}  Open: {acct['open']}", flush=True)
    if acct['success_rate'] is not None:
        print(f"  Success rate (resolved): {acct['success_rate']:.1%}", flush=True)
    print(f"  EV per account: {acct['ev_per_account']:+.3f}R", flush=True)
    if acct['median_days_payout'] is not None:
        print(f"  Median days to payout: {acct['median_days_payout']:.0f}", flush=True)
    if acct['median_days_breach'] is not None:
        print(f"  Median days to breach: {acct['median_days_breach']:.0f}", flush=True)

    # Account-by-account
    print(f"\n  {'Start':<12} {'Outcome':<10} {'Final R':>8} {'Trades':>6} {'Days':>6}", flush=True)
    print(f"  {'-'*48}", flush=True)
    for d in acct['details']:
        print(f"  {d['start']:<12} {d['outcome']:<10} {d['final_r']:>+8.3f} {d['trades']:>6} {d['days']:>6}", flush=True)

    # ── Phase 4: Holdout Test ─────────────────────────────────────────
    section("PHASE 4: HOLDOUT TEST")

    holdout_config = with_overrides(CANDIDATE, **MODE_PARAMS)
    print(f"  Config: anchor + mode params {MODE_PARAMS}", flush=True)
    print(f"  Holdout: {HOLDOUT_START} onward", flush=True)

    trades_ho = run_backtest(df_5m, holdout_config, start_date=HOLDOUT_START,
                              df_1m=df_1m, df_1s=df_1s, _maps=maps)
    trades_ho_gated = gate_fn(trades_ho)
    m_ho = compute_metrics(trades_ho_gated)

    filled_ho = [t for t in trades_ho_gated if t.exit_type != EXIT_NO_FILL]
    print(f"  Trades: {m_ho['total_trades']}", flush=True)
    print(f"  WR: {m_ho['win_rate']:.1%}  PF: {m_ho['profit_factor']:.2f}", flush=True)
    print(f"  Net R: {m_ho['total_r']:.1f}R  DD: {m_ho['max_drawdown_r']:.1f}R", flush=True)
    print(f"  Sharpe: {m_ho['sharpe_ratio']:.3f}", flush=True)
    ho_rby = m_ho.get("r_by_year", {})
    for y, r in sorted(ho_rby.items()):
        print(f"    {y}: {r:>+7.1f}R", flush=True)

    # Holdout payout simulation
    if filled_ho:
        ho_dates = [t.date for t in filled_ho]
        ho_acct = simulate_staggered_accounts(trades_ho_gated, min(ho_dates), max(ho_dates))
        print(f"\n  Holdout payout simulation:", flush=True)
        print(f"    Accounts: {ho_acct['total_accounts']}  Payouts: {ho_acct['payouts']}  "
              f"Breaches: {ho_acct['breaches']}  Open: {ho_acct['open']}", flush=True)
        if ho_acct['success_rate'] is not None:
            print(f"    Success rate: {ho_acct['success_rate']:.1%}", flush=True)
        print(f"    EV per account: {ho_acct['ev_per_account']:+.3f}R", flush=True)

    # ── Phase 5: Monte Carlo ──────────────────────────────────────────
    section("PHASE 5: MONTE CARLO (WF OOS trades)")

    mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)
    mc_result = run_monte_carlo(wf_result.combined_oos_trades, mc_config, ruin_threshold=-15.0)

    mc_constraints = PropFirmConstraints(max_drawdown_r=15.0, min_annual_r=12.0, max_monthly_loss_r=5.0)
    trade_dates_mc = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_surv = evaluate_constraints_mc(mc_result, mc_constraints, trade_dates=trade_dates_mc)

    print(f"  Survival at 15R: {mc_surv['survival_rate']:.1%}", flush=True)
    print(f"  Ruin probability: {mc_result.ruin_probability:.1%}", flush=True)
    print(f"  DD percentiles: {mc_surv['dd_percentiles']}", flush=True)
    print(f"  Sharpe percentiles: {mc_result.sharpe_percentiles}", flush=True)

    # ── Final Verdict ─────────────────────────────────────────────────
    section("STEP 7 VERDICT")

    print(f"  Pre-holdout (gated):  Calmar {m_pre['calmar_ratio']:.2f}, Sharpe {m_pre['sharpe_ratio']:.2f}, {m_pre['total_trades']}tr", flush=True)
    print(f"  WF OOS (gated):      Calmar {oos_m['calmar_ratio']:.2f}, Sharpe {oos_m['sharpe_ratio']:.2f}, {oos_m['total_trades']}tr", flush=True)
    print(f"  Holdout (gated):     {m_ho['total_r']:+.1f}R, Sharpe {m_ho['sharpe_ratio']:.2f}, {m_ho['total_trades']}tr", flush=True)
    print(f"  WF OOS payout rate:  {acct['success_rate']:.1%}" if acct['success_rate'] else "  WF OOS payout rate:  N/A", flush=True)
    print(f"  MC survival:         {mc_surv['survival_rate']:.1%}, ruin {mc_result.ruin_probability:.1%}", flush=True)
    print(f"  WFE: {wf_result.walk_forward_efficiency:.3f}, Stability: {stability.overall_score:.3f}", flush=True)

    print(f"\n  Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
