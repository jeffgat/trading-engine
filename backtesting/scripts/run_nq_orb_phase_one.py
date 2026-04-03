#!/usr/bin/env python3
"""Phase-One Robust Pipeline — NQ ORB Continuation promoted candidates.

Evaluates 3 promoted candidates for first-payout economics:
  NY-B:   30m ORB, ORB 25% stop, RR=2.5, TP1=0.4, long
  Asia-A: 15m ORB, ORB 100% stop, RR=3.0, TP1=0.6, long, gated
  Asia-B: 15m ORB, ORB 100% stop, RR=3.5, TP1=0.6, long, gated (challenger)

Phases:
  0: Model freeze
  1: Structural viability
  2: Walk-forward (reuse discovery pipeline results)
  3: First-payout scorecard on pre-holdout trades
  4: First-payout holdout confirmation
  5: Cohort EV simulation
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile,
    PropFirmProfile,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
    build_funded_first_payout_scorecard,
    build_funded_first_payout_forecast,
)
from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_END,
    REGIME_RESEARCH_HOLDOUT_START,
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.validate.deflated_sharpe import annotate_trades

OUTPUT_DIR = ROOT / "data" / "results" / "nq_orb_phase_one"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
HOLDOUT_END = REGIME_RESEARCH_HOLDOUT_END
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}


# ---------------------------------------------------------------------------
# Funded account model (skill defaults)
# ---------------------------------------------------------------------------

FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0,
    reset_fee=50.0,
    payout_split=0.80,
    payout_target_r=5.0,
    breach_limit_r=-4.0,
    daily_loss_limit_r=-2.0,
    min_trading_days=5,
    cohort_sizes=(10, 25, 50),
    block_size_days=20,
)


# ---------------------------------------------------------------------------
# Candidate configs
# ---------------------------------------------------------------------------

def _ny_b():
    return StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="10:00",
            entry_start="10:00", entry_end="12:00",
            flat_start="15:50", flat_end="16:00",
            stop_orb_pct=25.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="NY-B 30m ORB25 RR2.5 TP0.4",
    )

def _asia_a():
    return StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15",
            flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="Asia-A 15m ORB100 RR3.0 TP0.6 gated",
    )

def _asia_b():
    return StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15",
            flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="Asia-B 15m ORB100 RR3.5 TP0.6 gated",
    )

CANDIDATES = {
    "NY-B": {"config_fn": _ny_b, "gated": False, "role": "LEADER"},
    "Asia-A": {"config_fn": _asia_a, "gated": True, "role": "LEADER"},
    "Asia-B": {"config_fn": _asia_b, "gated": True, "role": "CHALLENGER"},
}


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def print_metrics(label, metrics):
    m = metrics
    print(f"  {label}: {m.get('total_trades', 0)} trades | "
          f"Net R: {m.get('total_r', 0):+.1f} | "
          f"Calmar: {m.get('calmar_ratio', 0) or 0:.2f} | "
          f"Sharpe: {m.get('sharpe_ratio', 0) or 0:.2f} | "
          f"DD: {m.get('max_drawdown_r', 0):.1f}R | "
          f"WR: {m.get('win_rate', 0):.1%} | "
          f"PF: {m.get('profit_factor', 0) or 0:.2f}")


def print_scorecard(label, scorecard):
    print(f"\n  {label}")
    print(f"    Attempts: {scorecard.get('total_starts', scorecard.get('total_attempts', 0))}")
    pr = scorecard.get("payout_rate", scorecard.get("first_payout_rate", 0))
    br = scorecard.get("breach_rate", 0)
    opr = scorecard.get("open_rate", 0)
    print(f"    Payout rate: {pr:.1%} | Breach rate: {br:.1%} | Open: {opr:.1%}")
    ev = scorecard.get("ev_per_start_usd", scorecard.get("ev_per_attempt", 0))
    print(f"    EV per attempt: ${ev}")
    days = scorecard.get("average_days_to_payout", scorecard.get("median_days_to_payout"))
    if days:
        print(f"    Avg days to payout: {days:.0f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Phase-One Robust Pipeline — NQ ORB Continuation")
    print("=" * 70)

    t0 = time.time()
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Phase 0: Model freeze
    print("\n[Phase 0] Model freeze")
    print(f"  Holdout: {HOLDOUT_START} to {HOLDOUT_END}")
    print(f"  Funded model: ${FUNDED_PROFILE.starting_balance_usd:,.0f}, "
          f"trailing DD ${FUNDED_PROFILE.trailing_drawdown_usd:,.0f}, "
          f"payout at ${FUNDED_PROFILE.first_payout_floor_usd:,.0f}")
    print(f"  Prop model: +{PROP_PROFILE.payout_target_r}R payout, "
          f"{PROP_PROFILE.breach_limit_r}R breach, "
          f"{PROP_PROFILE.daily_loss_limit_r}R daily limit")

    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    print(f"  5m bars: {len(df_5m):,}")

    print("Building regime calendar...", flush=True)
    regime_calendar = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_calendar)

    # Trading dates for account simulation
    cal = regime_calendar[regime_calendar["warmup_ok"] == True].copy()
    cal["_date_str"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    pre_dates = cal[pd.to_datetime(cal["date"]) < pd.Timestamp(HOLDOUT_START)]["_date_str"].tolist()
    holdout_dates = cal[
        (pd.to_datetime(cal["date"]) >= pd.Timestamp(HOLDOUT_START))
        & (pd.to_datetime(cal["date"]) <= pd.Timestamp(HOLDOUT_END))
    ]["_date_str"].tolist()
    all_dates = pre_dates + holdout_dates

    all_results = {}

    for cand_name, cand_info in CANDIDATES.items():
        print(f"\n{'=' * 60}")
        print(f"  CANDIDATE: {cand_name} ({cand_info['role']})")
        print(f"{'=' * 60}")

        config = cand_info["config_fn"]()
        use_gate = cand_info["gated"]

        # Phase 1: Structural viability
        print(f"\n  [Phase 1] Structural viability")
        trades_full = run_backtest(df_5m, config, end_date=HOLDOUT_START)
        if use_gate:
            trades_full = gate_fn(trades_full)
        filled = _filled_trades(trades_full)
        metrics = compute_metrics(trades_full)
        print_metrics("Pre-holdout", metrics)

        viable = (
            metrics.get("total_trades", 0) >= 100
            and metrics.get("profit_factor", 0) > 1.0
            and metrics.get("avg_r", 0) > 0
        )
        print(f"  Viable: {viable}")
        if not viable:
            print(f"  SKIP — does not meet structural viability")
            all_results[cand_name] = {"verdict": "NO-GO", "reason": "structural viability failed"}
            continue

        # Phase 2: Walk-forward (reuse discovery results — just report)
        print(f"\n  [Phase 2] Walk-forward (from discovery pipeline)")
        print(f"  See discovery_pipeline_results.json for full WF details")

        # Phase 3: First-payout scorecard on pre-holdout
        print(f"\n  [Phase 3] First-payout scorecard (pre-holdout)")

        # R-based prop model
        prop_outcomes = simulate_account_attempts(
            specialist_name=cand_name,
            trades=trades_full,
            trading_dates=pre_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        prop_scorecard = build_prop_scorecard(prop_outcomes, PROP_PROFILE)
        print_scorecard("Prop model (R-based)", prop_scorecard)

        # Funded account model
        funded_outcomes = simulate_funded_first_payouts(
            specialist_name=cand_name,
            trades=trades_full,
            trading_dates=pre_dates,
            profile=FUNDED_PROFILE,
        )
        funded_scorecard = build_funded_first_payout_scorecard(funded_outcomes, FUNDED_PROFILE)
        funded_forecast = build_funded_first_payout_forecast(funded_outcomes)
        print_scorecard("Funded model (USD)", funded_scorecard)

        # PSR/DSR
        r_mult = np.array([t.r_multiple for t in filled])
        psr_dsr = annotate_trades(r_mult, n_trials_raw=3888)
        print(f"\n  PSR: {psr_dsr['psr']['value']:.3f} ({psr_dsr['psr']['interpretation']})")
        print(f"  DSR @raw: {psr_dsr['dsr']['value']:.3f} ({psr_dsr['dsr']['interpretation']})")

        # Phase 4: Holdout confirmation
        print(f"\n  [Phase 4] Holdout confirmation ({HOLDOUT_START} to {HOLDOUT_END})")
        trades_holdout = run_backtest(
            df_5m, config,
            start_date=HOLDOUT_START, end_date=HOLDOUT_END,
        )
        if use_gate:
            trades_holdout = gate_fn(trades_holdout)
        holdout_metrics = compute_metrics(trades_holdout)
        print_metrics("Holdout", holdout_metrics)

        # Holdout prop simulation
        holdout_prop_outcomes = simulate_account_attempts(
            specialist_name=f"{cand_name}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        holdout_prop_sc = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
        print_scorecard("Holdout prop model", holdout_prop_sc)

        # Holdout funded simulation
        holdout_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=f"{cand_name}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=FUNDED_PROFILE,
        )
        holdout_funded_sc = build_funded_first_payout_scorecard(holdout_funded_outcomes, FUNDED_PROFILE)
        print_scorecard("Holdout funded model", holdout_funded_sc)

        # Phase 5: Cohort EV
        print(f"\n  [Phase 5] Cohort EV simulation")
        for cohort_size in [10, 25, 50]:
            ev = prop_scorecard.get("ev_per_attempt", 0)
            total_ev = ev * cohort_size
            print(f"    Cohort {cohort_size}: total EV ${total_ev:+.0f}")

        # Breach clustering
        if not prop_outcomes.empty:
            breaches = prop_outcomes[prop_outcomes["outcome"] == "breach"]
            if not breaches.empty:
                breach_months = pd.to_datetime(breaches["account_start"]).dt.to_period("M").value_counts()
                max_cluster = int(breach_months.max()) if not breach_months.empty else 0
                print(f"    Worst breach cluster: {max_cluster} in one month")

        # Verdict
        pr = prop_scorecard.get("first_payout_rate", 0)
        ev = prop_scorecard.get("ev_per_attempt", 0)
        holdout_pr = holdout_prop_sc.get("first_payout_rate", 0)

        if pr >= 0.60 and ev > 0 and holdout_pr >= 0.40:
            verdict = "STRONG"
        elif pr >= 0.40 and ev > 0:
            verdict = "CONDITIONAL"
        else:
            verdict = "NO-GO"

        print(f"\n  VERDICT: {verdict}")

        all_results[cand_name] = {
            "role": cand_info["role"],
            "verdict": verdict,
            "pre_holdout_metrics": {
                k: round(float(v), 4) if isinstance(v, (int, float)) else v
                for k, v in metrics.items()
                if k in {"total_trades", "total_r", "calmar_ratio", "sharpe_ratio",
                         "max_drawdown_r", "win_rate", "profit_factor", "avg_r"}
            },
            "holdout_metrics": {
                k: round(float(v), 4) if isinstance(v, (int, float)) else v
                for k, v in holdout_metrics.items()
                if k in {"total_trades", "total_r", "calmar_ratio", "sharpe_ratio",
                         "max_drawdown_r", "win_rate", "profit_factor", "avg_r"}
            },
            "prop_scorecard": prop_scorecard,
            "funded_scorecard": funded_scorecard,
            "holdout_prop_scorecard": holdout_prop_sc,
            "holdout_funded_scorecard": holdout_funded_sc,
            "psr_dsr": psr_dsr,
        }

    # Summary
    print(f"\n{'=' * 70}")
    print("PHASE-ONE SUMMARY")
    print(f"{'=' * 70}")
    print(f"\n  {'Name':>10s} {'Role':>12s} {'Verdict':>12s} {'Pre R':>7s} {'HO R':>7s} {'PR':>6s} {'HO PR':>6s} {'EV':>8s}")
    print(f"  {'-' * 70}")
    for name, r in all_results.items():
        if r["verdict"] in ("NO-GO",) and "pre_holdout_metrics" not in r:
            continue
        pm = r.get("pre_holdout_metrics", {})
        hm = r.get("holdout_metrics", {})
        ps = r.get("prop_scorecard", {})
        hps = r.get("holdout_prop_scorecard", {})
        print(f"  {name:>10s} {r['role']:>12s} {r['verdict']:>12s} "
              f"{pm.get('total_r', 0):+7.1f} {hm.get('total_r', 0):+7.1f} "
              f"{ps.get('first_payout_rate', 0):5.1%} {hps.get('first_payout_rate', 0):5.1%} "
              f"${ps.get('ev_per_attempt', 0):>7.0f}")

    write_json(output_dir / "phase_one_results.json", all_results)

    print(f"\nTotal time: {time.time() - t0:.0f}s")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
