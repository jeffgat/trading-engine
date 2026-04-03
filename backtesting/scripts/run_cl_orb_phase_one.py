#!/usr/bin/env python3
"""Phase-One Robust Pipeline — CL ORB Continuation promoted candidates.

3 promoted + 3 challengers from discovery pipeline:
  LDN-4: 10m ORB, ORB 25%, RR=3.5, TP1=0.6, long  (WF Cal 7.62, WFE 0.416) — PROMOTE
  LDN-1: 30m ORB, ATR 8%, RR=3.5, TP1=0.6, long   (WF Cal 5.32, WFE 0.463) — PROMOTE
  Asia-2: 5m ORB, ORB 75%, RR=2.5, TP1=0.4, long   (WF Cal 3.65, WFE 0.469) — PROMOTE
  LDN-3: 30m ORB, ATR 8%, RR=3.5, TP1=0.5, long   (WF Cal 3.65, WFE 0.470) — CHALLENGER
  LDN-2: 30m ORB, ATR 8%, RR=3.0, TP1=0.6, long   (WF Cal 3.62, WFE 0.415) — CHALLENGER
  Asia-1: 5m ORB, ATR 8%, RR=3.5, TP1=0.3, long    (WF Cal 2.56, WFE 0.495) — CHALLENGER
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile, PropFirmProfile,
    build_prop_scorecard, simulate_account_attempts,
    simulate_funded_first_payouts, build_funded_first_payout_scorecard,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import CL
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.validate.deflated_sharpe import annotate_trades

OUTPUT_DIR = ROOT / "data" / "results" / "cl_orb_phase_one"
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-03-01"
N_DISCOVERY_CONFIGS = 1296

FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0, starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0, max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0, risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0, reset_fee=50.0, payout_split=0.80,
    payout_target_r=5.0, breach_limit_r=-4.0, daily_loss_limit_r=-2.0,
    min_trading_days=5, cohort_sizes=(10, 25, 50), block_size_days=20)

CANDIDATES = {
    "LDN-4": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:10",
            entry_start="03:10", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="CL LDN-4 10m ORB25 RR3.5 TP0.6 long"),

    "LDN-1": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:30",
            entry_start="03:30", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="CL LDN-1 30m ATR8 RR3.5 TP0.6 long"),

    "Asia-2": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:05",
            entry_start="20:05", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="CL Asia-2 5m ORB75 RR2.5 TP0.4 long"),

    "LDN-3": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:30",
            entry_start="03:30", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.5, atr_length=14,
        name="CL LDN-3 30m ATR8 RR3.5 TP0.5 long"),

    "LDN-2": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:30",
            entry_start="03:30", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="CL LDN-2 30m ATR8 RR3.0 TP0.6 long"),

    "Asia-1": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:05",
            entry_start="20:05", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="CL Asia-1 5m ATR8 RR3.5 TP0.3 long"),
}

def _filled_trades(trades):
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))

def print_metrics(label, metrics):
    m = metrics
    print(f"  {label}: {m.get('total_trades', 0)} trades | "
          f"Net R: {m.get('total_r', 0):+.1f} | Calmar: {m.get('calmar_ratio', 0) or 0:.2f} | "
          f"Sharpe: {m.get('sharpe_ratio', 0) or 0:.2f} | DD: {m.get('max_drawdown_r', 0):.1f}R | "
          f"WR: {m.get('win_rate', 0):.1%} | PF: {m.get('profit_factor', 0) or 0:.2f}")

def print_scorecard(label, scorecard):
    print(f"\n  {label}")
    attempts = scorecard.get("total_starts", scorecard.get("total_attempts", 0))
    pr = scorecard.get("payout_rate", scorecard.get("first_payout_rate", 0))
    br = scorecard.get("breach_rate", 0)
    ev = scorecard.get("ev_per_start_usd", scorecard.get("ev_per_attempt", 0))
    days = scorecard.get("average_days_to_payout", scorecard.get("median_days_to_payout"))
    print(f"    Attempts: {attempts} | PR: {pr:.1%} | BR: {br:.1%} | EV: ${ev}")
    if days: print(f"    Avg days to payout: {days:.0f}")

def main():
    print("Phase-One Robust Pipeline — CL ORB Continuation (6 candidates)")
    print("=" * 70)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"\n[Phase 0] Model freeze — Holdout: {HOLDOUT_START} to {HOLDOUT_END}")
    print("\nLoading CL data (5m + 1m)...", flush=True)
    df_5m = load_5m_data(CL.data_file)
    df_1m = load_1m_for_5m(CL.data_file)
    print(f"  5m bars: {len(df_5m):,}")

    dates_all = pd.Series(df_5m.index.date).drop_duplicates().astype(str).tolist()
    pre_dates = [d for d in dates_all if d < HOLDOUT_START]
    holdout_dates = [d for d in dates_all if HOLDOUT_START <= d < HOLDOUT_END]

    all_results = {}
    for cand_name, config in CANDIDATES.items():
        print(f"\n{'=' * 60}")
        print(f"  CANDIDATE: {cand_name} — {config.name}")
        print(f"{'=' * 60}")

        print(f"\n  [Phase 1] Structural viability")
        trades_pre = run_backtest(df_5m, config, end_date=HOLDOUT_START, df_1m=df_1m)
        filled_pre = _filled_trades(trades_pre)
        metrics = compute_metrics(trades_pre)
        print_metrics("Pre-holdout", metrics)
        viable = (metrics.get("total_trades", 0) >= 50 and metrics.get("profit_factor", 0) > 1.0 and metrics.get("avg_r", 0) > 0)
        if not viable:
            all_results[cand_name] = {"verdict": "NO-GO", "reason": "structural fail"}
            continue
        r_by_year = metrics.get("r_by_year", {})
        if r_by_year:
            print(f"  R by year: {' '.join(f'{k}:{float(v):+.1f}' for k, v in sorted(r_by_year.items()))}")

        print(f"\n  [Phase 3] First-payout scorecard")
        prop_outcomes = simulate_account_attempts(specialist_name=cand_name, trades=trades_pre, trading_dates=pre_dates, profile=PROP_PROFILE, risk_per_r_usd=config.risk_usd)
        prop_scorecard = build_prop_scorecard(prop_outcomes, PROP_PROFILE)
        print_scorecard("Prop model", prop_scorecard)
        funded_outcomes = simulate_funded_first_payouts(specialist_name=cand_name, trades=trades_pre, trading_dates=pre_dates, profile=FUNDED_PROFILE)
        funded_scorecard = build_funded_first_payout_scorecard(funded_outcomes, FUNDED_PROFILE)
        print_scorecard("Funded model", funded_scorecard)

        print(f"\n  [Phase 4] Holdout confirmation ({HOLDOUT_START} to {HOLDOUT_END})")
        trades_holdout = run_backtest(df_5m, config, start_date=HOLDOUT_START, end_date=HOLDOUT_END, df_1m=df_1m)
        holdout_metrics = compute_metrics(trades_holdout)
        print_metrics("Holdout", holdout_metrics)
        ho_r = holdout_metrics.get("r_by_year", {})
        if ho_r: print(f"  Holdout R by year: {' '.join(f'{k}:{float(v):+.1f}' for k, v in sorted(ho_r.items()))}")
        holdout_prop = simulate_account_attempts(specialist_name=f"{cand_name}_ho", trades=trades_holdout, trading_dates=holdout_dates, profile=PROP_PROFILE, risk_per_r_usd=config.risk_usd)
        holdout_prop_sc = build_prop_scorecard(holdout_prop, PROP_PROFILE)
        print_scorecard("Holdout prop", holdout_prop_sc)

        print(f"\n  [Phase 5] PSR/DSR")
        r_mult = np.array([t.r_multiple for t in filled_pre])
        psr_dsr = annotate_trades(r_mult, n_trials_raw=N_DISCOVERY_CONFIGS)
        print(f"    PSR: {psr_dsr['psr']['value']:.3f} ({psr_dsr['psr']['interpretation']})")
        print(f"    DSR @{N_DISCOVERY_CONFIGS}: {psr_dsr['dsr']['value']:.3f} ({psr_dsr['dsr']['interpretation']})")

        pr = prop_scorecard.get("first_payout_rate", prop_scorecard.get("payout_rate", 0))
        ev = prop_scorecard.get("ev_per_attempt", prop_scorecard.get("ev_per_start_usd", 0))
        holdout_pr = holdout_prop_sc.get("first_payout_rate", holdout_prop_sc.get("payout_rate", 0))
        verdict = "STRONG" if pr >= 0.60 and ev > 0 and holdout_pr >= 0.40 else ("CONDITIONAL" if pr >= 0.40 and ev > 0 else "NO-GO")
        print(f"\n  VERDICT: {verdict}")

        all_results[cand_name] = {
            "verdict": verdict,
            "pre_holdout_metrics": {k: round(float(v), 4) if isinstance(v, (int, float)) else v for k, v in metrics.items() if k in {"total_trades", "total_r", "calmar_ratio", "sharpe_ratio", "max_drawdown_r", "win_rate", "profit_factor", "avg_r", "r_by_year"}},
            "holdout_metrics": {k: round(float(v), 4) if isinstance(v, (int, float)) else v for k, v in holdout_metrics.items() if k in {"total_trades", "total_r", "calmar_ratio", "sharpe_ratio", "max_drawdown_r", "win_rate", "profit_factor", "avg_r", "r_by_year"}},
            "prop_scorecard": prop_scorecard, "funded_scorecard": funded_scorecard,
            "holdout_prop_scorecard": holdout_prop_sc, "psr_dsr": psr_dsr,
        }

    print(f"\n{'=' * 70}")
    print("PHASE-ONE SUMMARY — CL ORB Continuation")
    print(f"{'=' * 70}")
    print(f"\n  {'Name':>8s} {'Verdict':>12s} {'Pre R':>7s} {'HO R':>7s} {'PR':>6s} {'HO PR':>6s} {'EV':>8s} {'PSR':>6s} {'DSR':>6s}")
    print(f"  {'-' * 75}")
    for name, r in all_results.items():
        if "pre_holdout_metrics" not in r:
            print(f"  {name:>8s} {r['verdict']:>12s}   (skipped)")
            continue
        pm, hm, ps, hps = r["pre_holdout_metrics"], r["holdout_metrics"], r["prop_scorecard"], r["holdout_prop_scorecard"]
        psr = r.get("psr_dsr", {}).get("psr", {}).get("value", 0)
        dsr = r.get("psr_dsr", {}).get("dsr", {}).get("value", 0)
        pr_val = ps.get("first_payout_rate", ps.get("payout_rate", 0))
        ho_pr = hps.get("first_payout_rate", hps.get("payout_rate", 0))
        ev_val = ps.get("ev_per_attempt", ps.get("ev_per_start_usd", 0))
        print(f"  {name:>8s} {r['verdict']:>12s} {pm.get('total_r', 0):+7.1f} {hm.get('total_r', 0):+7.1f} {pr_val:5.1%} {ho_pr:5.1%} ${ev_val:>7.0f} {psr:5.3f} {dsr:5.3f}")

    write_json(OUTPUT_DIR / "phase_one_results.json", all_results)
    print(f"\nTotal time: {time.time() - t0:.0f}s | Output: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
