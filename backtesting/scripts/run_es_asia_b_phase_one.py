#!/usr/bin/env python3
"""Phase-One Robust Pipeline — ES Asia-B (missed candidate from discovery).

ES Asia-B: 15m ORB, ATR 12% stop, RR=3.0, TP1=0.6, long only, continuation.
Holdout showed +49.4R ungated (Cal 8.09) vs +36.1R gated (Cal 6.97).
Runs both gated and ungated variants.

Phases:
  0: Model freeze
  1: Structural viability
  2: Walk-forward (run fresh — not in original pipeline)
  3: First-payout scorecard on pre-holdout trades
  4: First-payout holdout confirmation
  5: Cohort EV simulation
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
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.validate.deflated_sharpe import annotate_trades

OUTPUT_DIR = ROOT / "data" / "results" / "es_asia_b_phase_one"
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
# Candidate config
# ---------------------------------------------------------------------------

BASE_CONFIG = StrategyConfig(
    sessions=(SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="23:15",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=12.0, min_gap_atr_pct=1.0,
    ),),
    instrument=ES, strategy="continuation", use_bar_magnifier=False,
    risk_usd=5000.0, direction_filter="long",
    rr=3.0, tp1_ratio=0.6, atr_length=14,
    name="ES Asia-B 15m ATR12 RR3.0 TP0.6 long",
)

CANDIDATES = {
    "Asia-B ungated": {"gated": False},
    "Asia-B gated":   {"gated": True},
}

# Walk-forward local grid
LOCAL_SWEEP = {"rr": [-0.5, 0.0, +0.5], "tp1_ratio": [-0.1, 0.0, +0.1]}


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


# ---------------------------------------------------------------------------
# Walk-forward param grid
# ---------------------------------------------------------------------------

def build_param_ranges(config):
    base_rr, base_tp1 = config.rr, config.tp1_ratio
    rr_cands = sorted(set([max(1.5, base_rr + d) for d in LOCAL_SWEEP["rr"]]))
    tp1_cands = sorted(set([round(max(0.2, min(1.0, base_tp1 + d)), 2) for d in LOCAL_SWEEP["tp1_ratio"]]))

    rr_vals, tp1_set = [], set()
    for r in rr_cands:
        valid = [t for t in tp1_cands if t * r >= 1.0]
        if valid:
            rr_vals.append(r)
            tp1_set.update(valid)
    tp1_vals = sorted(tp1_set)
    if rr_vals:
        tp1_vals = [t for t in tp1_vals if t >= 1.0 / min(rr_vals)]
    if not rr_vals or not tp1_vals:
        rr_vals, tp1_vals = [base_rr], [base_tp1]
    return {"rr": rr_vals, "tp1_ratio": tp1_vals}


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
    print("Phase-One Robust Pipeline — ES Asia-B (ungated + gated)")
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

    print("\nLoading ES data...", flush=True)
    df_5m = load_5m_data(ES.data_file)
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

    all_results = {}

    for cand_name, cand_info in CANDIDATES.items():
        print(f"\n{'=' * 60}")
        print(f"  CANDIDATE: {cand_name}")
        print(f"{'=' * 60}")

        use_gate = cand_info["gated"]
        config = BASE_CONFIG

        # Phase 1: Structural viability
        print(f"\n  [Phase 1] Structural viability")
        trades_pre = run_backtest(df_5m, config, end_date=HOLDOUT_START)
        if use_gate:
            trades_pre = gate_fn(trades_pre)
        filled_pre = _filled_trades(trades_pre)
        metrics = compute_metrics(trades_pre)
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

        # R by year
        r_by_year = metrics.get("r_by_year", {})
        if r_by_year:
            neg_years = sum(1 for v in r_by_year.values() if float(v) < 0)
            print(f"  R by year: {' '.join(f'{k}:{float(v):+.1f}' for k, v in sorted(r_by_year.items()))}")
            print(f"  Negative years: {neg_years}")

        # Phase 2: Walk-forward
        print(f"\n  [Phase 2] Walk-forward (12m IS / 3m OOS / 3m step)")
        df_pre = df_5m.loc[:HOLDOUT_START]
        param_ranges = build_param_ranges(config)
        n_configs = len(param_ranges["rr"]) * len(param_ranges["tp1_ratio"])
        print(f"    Grid: {len(param_ranges['rr'])} RR x {len(param_ranges['tp1_ratio'])} TP1 = {n_configs}")
        print(f"    RR={param_ranges['rr']} TP1={param_ranges['tp1_ratio']}")
        print(f"    Gated: {use_gate}")

        t1 = time.time()
        wf = run_walkforward(
            df=df_pre, base_config=config, param_ranges=param_ranges,
            is_months=12, oos_months=3, step_months=3, objective="calmar",
            n_workers=4,
            start_date=df_pre.index[0].strftime("%Y-%m-%d"),
            gate_fn=gate_fn if use_gate else None,
        )
        stab = analyze_parameter_stability(wf, param_ranges)
        wf_elapsed = time.time() - t1

        cm = wf.combined_oos_metrics
        wf_filled = len([t for t in wf.combined_oos_trades if t.exit_type != EXIT_NO_FILL])
        print(f"\n    WF Results ({len(wf.folds)} folds, {wf_filled} OOS trades) [{wf_elapsed:.0f}s]")
        print(f"    OOS: R={cm.get('total_r', 0):+.1f} Cal={cm.get('calmar_ratio', 0) or 0:.2f} "
              f"Shp={cm.get('sharpe_ratio', 0) or 0:.2f} DD={cm.get('max_drawdown_r', 0):.1f}R "
              f"WR={cm.get('win_rate', 0):.1%}")
        print(f"    WFE={wf.walk_forward_efficiency:.3f} Stab={stab.overall_score:.3f} ({stab.interpretation})")

        # Phase 3: First-payout scorecard on pre-holdout
        print(f"\n  [Phase 3] First-payout scorecard (pre-holdout)")

        prop_outcomes = simulate_account_attempts(
            specialist_name=cand_name,
            trades=trades_pre,
            trading_dates=pre_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        prop_scorecard = build_prop_scorecard(prop_outcomes, PROP_PROFILE)
        print_scorecard("Prop model (R-based)", prop_scorecard)

        funded_outcomes = simulate_funded_first_payouts(
            specialist_name=cand_name,
            trades=trades_pre,
            trading_dates=pre_dates,
            profile=FUNDED_PROFILE,
        )
        funded_scorecard = build_funded_first_payout_scorecard(funded_outcomes, FUNDED_PROFILE)
        print_scorecard("Funded model (USD)", funded_scorecard)

        # PSR/DSR
        r_mult = np.array([t.r_multiple for t in filled_pre])
        psr_dsr = annotate_trades(r_mult, n_trials_raw=3888)
        print(f"\n  PSR: {psr_dsr['psr']['value']:.3f} ({psr_dsr['psr']['interpretation']})")
        print(f"  DSR @raw 3888 trials: {psr_dsr['dsr']['value']:.3f} ({psr_dsr['dsr']['interpretation']})")

        # Phase 4: Holdout confirmation
        print(f"\n  [Phase 4] Holdout confirmation ({HOLDOUT_START} to {HOLDOUT_END})")
        trades_holdout = run_backtest(
            df_5m, config,
            start_date=HOLDOUT_START, end_date=HOLDOUT_END,
        )
        if use_gate:
            trades_holdout = gate_fn(trades_holdout)
        holdout_filled = _filled_trades(trades_holdout)
        holdout_metrics = compute_metrics(trades_holdout)
        print_metrics("Holdout", holdout_metrics)

        ho_r_by_year = holdout_metrics.get("r_by_year", {})
        if ho_r_by_year:
            print(f"  Holdout R by year: {' '.join(f'{k}:{float(v):+.1f}' for k, v in sorted(ho_r_by_year.items()))}")

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
            "gated": use_gate,
            "verdict": verdict,
            "pre_holdout_metrics": {
                k: round(float(v), 4) if isinstance(v, (int, float)) else v
                for k, v in metrics.items()
                if k in {"total_trades", "total_r", "calmar_ratio", "sharpe_ratio",
                         "max_drawdown_r", "win_rate", "profit_factor", "avg_r"}
            },
            "wf_metrics": {
                "oos_net_r": round(float(cm.get("total_r", 0)), 2),
                "oos_calmar": round(float(cm.get("calmar_ratio", 0) or 0), 4),
                "oos_sharpe": round(float(cm.get("sharpe_ratio", 0) or 0), 4),
                "oos_max_dd": round(float(cm.get("max_drawdown_r", 0)), 2),
                "wf_efficiency": round(wf.walk_forward_efficiency, 4),
                "stability_score": round(stab.overall_score, 4),
                "stability_interp": stab.interpretation,
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
    print("PHASE-ONE SUMMARY — ES Asia-B")
    print(f"{'=' * 70}")
    print(f"\n  {'Name':>18s} {'Verdict':>12s} {'Pre R':>7s} {'WF R':>7s} {'HO R':>7s} {'PR':>6s} {'HO PR':>6s} {'EV':>8s}")
    print(f"  {'-' * 80}")
    for name, r in all_results.items():
        if "pre_holdout_metrics" not in r:
            continue
        pm = r.get("pre_holdout_metrics", {})
        wm = r.get("wf_metrics", {})
        hm = r.get("holdout_metrics", {})
        ps = r.get("prop_scorecard", {})
        hps = r.get("holdout_prop_scorecard", {})
        print(f"  {name:>18s} {r['verdict']:>12s} "
              f"{pm.get('total_r', 0):+7.1f} {wm.get('oos_net_r', 0):+7.1f} {hm.get('total_r', 0):+7.1f} "
              f"{ps.get('first_payout_rate', 0):5.1%} {hps.get('first_payout_rate', 0):5.1%} "
              f"${ps.get('ev_per_attempt', 0):>7.0f}")

    write_json(output_dir / "phase_one_results.json", all_results)

    print(f"\nTotal time: {time.time() - t0:.0f}s")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
