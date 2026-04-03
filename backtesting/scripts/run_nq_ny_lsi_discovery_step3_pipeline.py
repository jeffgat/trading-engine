#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 3: Discovery Pipeline (Phases 1-5) for 2 candidates.

Candidate A (leader):   fvg_limit, RR=2.0, TP1=0.5, ATR=10 — Calmar 13.94, 1 neg yr
Candidate B (challenger): fvg_limit + 1stFVG, RR=2.0, TP1=0.5, ATR=14 — Calmar 15.02, 0 neg yr

Hold-out frozen at 2025-04-01.
1s magnifier throughout.
Walk-forward: 36m IS / 12m OOS / 12m step.
Local stability: narrow ±1 step sweep on rr, tp1, gap, atr, n_left, n_right.

Bailey caveat: PSR/DSR implemented (deflated_sharpe.py). PBO/CSCV not implemented.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.holdout_log import check_holdout_period, log_holdout_test
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints, evaluate_constraints, evaluate_constraints_mc,
)
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.simulate.monte_carlo import MonteCarloConfig, run_monte_carlo

# ── Configuration ─────────────────────────────────────────────────────────
WF_START = "2016-01-01"
HOLDOUT_START = "2025-04-01"
PRE_HOLDOUT_END = "2025-03-31"
N_WORKERS = 4
MC_SURVIVAL_DD = 15.0

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,  # DD is informational only during discovery
    min_annual_r=12.0,
    max_monthly_loss_r=5.0,
    min_positive_expectancy=True,
)

# ── Candidates ────────────────────────────────────────────────────────────

NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

CANDIDATE_A = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=10,
    lsi_n_left=8,
    lsi_n_right=60,
    lsi_fvg_window_left=20,
    lsi_fvg_window_right=5,
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="NQ NY LSI A fvg_limit RR2 TP0.5",
)

CANDIDATE_B = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    lsi_n_left=8,
    lsi_n_right=60,
    lsi_fvg_window_left=20,
    lsi_fvg_window_right=5,
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=True,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="NQ NY LSI B 1stFVG ATR14 RR2 TP0.5",
)

CANDIDATES = {"A": CANDIDATE_A, "B": CANDIDATE_B}

# ── Walk-forward param ranges ────────────────────────────────────────────
# Narrow neighborhood around anchor values
PARAM_RANGES_A = {
    "rr": [2.0, 2.25, 2.5],
    "tp1_ratio": [0.5, 0.6, 0.7],
    "ny_min_gap_atr_pct": [3.75, 5.0, 7.5],
}

PARAM_RANGES_B = {
    "rr": [2.0, 2.25, 2.5],
    "tp1_ratio": [0.5, 0.6, 0.7],
    "ny_min_gap_atr_pct": [3.75, 5.0, 7.5],
    "atr_length": [10, 14, 20],
}


def tp1_filter(configs):
    return [c for c in configs if c.tp1_ratio * c.rr >= 1.0]


# ── Helpers ───────────────────────────────────────────────────────────────

def fmt(p): return "PASS" if p else "FAIL"

def section(title):
    print(f"\n{'='*80}\n  {title}\n{'='*80}\n", flush=True)

def print_metrics(m, label=""):
    if label:
        print(f"\n  {label}", flush=True)
    print(f"  {'Trades':<24} {m['total_trades']:>10d}", flush=True)
    print(f"  {'Win Rate':<24} {m['win_rate']:>9.1%}", flush=True)
    print(f"  {'Profit Factor':<24} {m['profit_factor']:>10.2f}", flush=True)
    print(f"  {'Net R':<24} {m['total_r']:>9.1f}R", flush=True)
    print(f"  {'Max DD':<24} {m['max_drawdown_r']:>9.1f}R", flush=True)
    print(f"  {'Calmar':<24} {m['calmar_ratio']:>10.2f}", flush=True)
    print(f"  {'Sharpe':<24} {m['sharpe_ratio']:>10.3f}", flush=True)
    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)

def wf_progress(fold_idx, total, status):
    print(f"    [Fold {fold_idx + 1}/{total}] {status}", flush=True)


# ── Pipeline execution per candidate ─────────────────────────────────────

def run_pipeline(name, candidate, param_ranges, df_5m, df_1m, df_1s, maps):
    section(f"CANDIDATE {name}: {candidate.name}")
    results = {}

    # ── Phase 1: Structural Validation ────────────────────────────────
    section(f"[{name}] PHASE 1: STRUCTURAL VALIDATION")
    t0 = time.time()
    df_pre = df_5m.loc[:PRE_HOLDOUT_END]
    df_pre_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    trades = run_backtest(df_pre, candidate, start_date=WF_START,
                          df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time() - t0:.1f}s", flush=True)
    print_metrics(m, "Full pre-holdout metrics")

    checks = {
        "Trades >= 100": (m["total_trades"] >= 100, m["total_trades"], ">=100"),
        "Win rate >= 35%": (m["win_rate"] >= 0.35, f"{m['win_rate']:.1%}", ">=35%"),
        "PF >= 1.0": (m["profit_factor"] >= 1.0, f"{m['profit_factor']:.2f}", ">=1.0"),
        "Max consec losses <= 15": (m["max_consecutive_losses"] <= 15, m["max_consecutive_losses"], "<=15"),
    }
    print(f"\n  {'Check':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}", flush=True)
    print(f"  {'-'*62}", flush=True)
    p1_pass = True
    for check_name, (passed, val, thresh) in checks.items():
        print(f"  {check_name:<28} {str(val):>10}  {thresh:>10}  {fmt(passed):>8}", flush=True)
        if not passed:
            p1_pass = False
    print(f"\n  >> PHASE 1: {fmt(p1_pass)}", flush=True)
    results["Phase 1"] = p1_pass

    # ── Phase 2: Walk-Forward + Stability ─────────────────────────────
    section(f"[{name}] PHASE 2: WALK-FORWARD + STABILITY")
    n_valid = sum(1 for r in param_ranges.get("rr", [2.0])
                  for t in param_ranges.get("tp1_ratio", [0.5])
                  if t * r >= 1.0)
    grid_mult = 1
    for k, v in param_ranges.items():
        if k not in ("rr", "tp1_ratio"):
            grid_mult *= len(v)
    grid_size = n_valid * grid_mult
    print(f"  Config: 36m IS / 12m OOS / 12m step", flush=True)
    print(f"  Grid: ~{grid_size} valid combos per fold", flush=True)
    print(f"  Objective: sharpe", flush=True)
    print(f"  1s magnifier: YES", flush=True)

    df_wf = df_5m.loc[:PRE_HOLDOUT_END]
    df_wf_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_wf_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    t0 = time.time()
    wf_result = run_walkforward(
        df_wf, candidate, param_ranges,
        is_months=36, oos_months=12, step_months=12,
        anchored=False, objective="sharpe",
        n_workers=N_WORKERS, start_date=WF_START,
        progress_fn=wf_progress,
        df_1m=df_wf_1m, df_1s=df_wf_1s,
        config_filter=tp1_filter,
    )
    elapsed = time.time() - t0
    print(f"\n  Walk-forward completed in {elapsed:.0f}s ({len(wf_result.folds)} folds)", flush=True)

    print(f"\n  {'Fold':<6} {'IS Period':<24} {'OOS Period':<24} {'IS Shrp':>8} {'OOS Shrp':>9} {'Best Params'}", flush=True)
    print(f"  {'-'*110}", flush=True)
    for f in wf_result.folds:
        ps = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
        print(f"  {f.fold_index + 1:<6} {f.is_start} -> {f.is_end:<10} {f.oos_start} -> {f.oos_end:<10}"
              f" {f.is_objective_value:>8.3f} {f.oos_objective_value:>9.3f}  {ps}", flush=True)

    oos_m = wf_result.combined_oos_metrics
    print_metrics(oos_m, "Combined OOS metrics")

    wfe_pass = wf_result.walk_forward_efficiency >= 0.3
    folds_pass = len(wf_result.folds) >= 4

    stability = analyze_parameter_stability(wf_result, param_ranges=param_ranges)
    stab_pass = stability.overall_score >= 0.4

    print(f"\n  Parameter Stability (overall: {stability.overall_score:.3f} — {stability.interpretation}):", flush=True)
    for p in stability.params:
        print(f"    {p.name:<24} mode={p.mode:<6} freq={p.mode_frequency}/{stability.n_folds}"
              f"  score={p.stability_score:.3f}", flush=True)

    print(f"\n  {'Check':<28} {'Value':>10}  {'Threshold':>10}  {'Result':>8}", flush=True)
    print(f"  {'-'*62}", flush=True)
    print(f"  {'WF efficiency':<28} {wf_result.walk_forward_efficiency:>10.3f}  {'>=0.30':>10}  {fmt(wfe_pass):>8}", flush=True)
    print(f"  {'Stability score':<28} {stability.overall_score:>10.3f}  {'>=0.40':>10}  {fmt(stab_pass):>8}", flush=True)
    print(f"  {'Folds completed':<28} {len(wf_result.folds):>10}  {'>=4':>10}  {fmt(folds_pass):>8}", flush=True)

    p2_pass = wfe_pass and stab_pass and folds_pass
    print(f"\n  >> PHASE 2: {fmt(p2_pass)}", flush=True)
    results["Phase 2"] = p2_pass

    # ── Phase 3: Prop Firm Constraints ────────────────────────────────
    section(f"[{name}] PHASE 3: PROP FIRM CONSTRAINTS (on WF OOS)")
    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)

    print(f"\n  {'Constraint':<28} {'Value':>12}  {'Threshold':>12}  {'Result':>8}", flush=True)
    print(f"  {'-'*66}", flush=True)
    print(f"  {'Max drawdown':<28} {cr.max_drawdown_r:>12.1f}R {'(INFO)':>12}  {'INFO':>8}", flush=True)
    print(f"  {'Worst monthly loss':<28} {cr.worst_month_r:>12.1f}R {'<=5.0R':>12}  {fmt(cr.monthly_loss_passed):>8}", flush=True)
    print(f"  {'Expectancy':<28} {cr.expectancy:>12.3f}R {'> 0':>12}  {fmt(cr.expectancy_passed):>8}", flush=True)
    print(f"  {'Annual R (full years)':<28} {'':>12}  {'>=12.0R':>12}  {fmt(cr.annual_r_passed):>8}", flush=True)

    if cr.annual_r_values:
        print(f"\n  Annual R by year (OOS):", flush=True)
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)

    p3_pass = cr.monthly_loss_passed and cr.expectancy_passed and cr.annual_r_passed
    print(f"\n  >> PHASE 3: {fmt(p3_pass)}", flush=True)
    results["Phase 3"] = p3_pass

    # ── Phase 4: Local Stability / Plateau Check ──────────────────────
    section(f"[{name}] PHASE 4: LOCAL STABILITY CHECK")
    print(f"  Narrow sweep ±1 step around candidate on key params", flush=True)

    import dataclasses
    local_dims = {
        "rr": [max(2.0, candidate.rr - 0.25), candidate.rr, candidate.rr + 0.25],
        "tp1_ratio": [max(0.3, candidate.tp1_ratio - 0.1), candidate.tp1_ratio, candidate.tp1_ratio + 0.1],
        "ny_min_gap_atr_pct": [max(2.0, candidate.sessions[0].min_gap_atr_pct - 1.25),
                               candidate.sessions[0].min_gap_atr_pct,
                               candidate.sessions[0].min_gap_atr_pct + 1.25],
        "atr_length": [max(5, candidate.atr_length - 4), candidate.atr_length, candidate.atr_length + 4],
        "lsi_n_left": [max(3, candidate.lsi_n_left - 3), candidate.lsi_n_left, candidate.lsi_n_left + 3],
        "lsi_n_right": [max(30, candidate.lsi_n_right - 15), candidate.lsi_n_right, candidate.lsi_n_right + 15],
    }

    baseline_m = m  # from Phase 1
    anchor_calmar = baseline_m["calmar_ratio"]
    local_ok = True

    for dim, vals in local_dims.items():
        print(f"\n  {dim}: {vals}", flush=True)
        for v in vals:
            try:
                if dim.startswith("ny_"):
                    cfg = with_overrides(candidate, **{dim: v})
                else:
                    cfg = dataclasses.replace(candidate, **{dim: v})
            except ValueError:
                print(f"    {v:<10} SKIPPED (constraint)", flush=True)
                continue
            tr = run_backtest(df_pre, cfg, start_date=WF_START,
                              df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
            lm = compute_metrics(tr)
            delta = lm["calmar_ratio"] - anchor_calmar
            marker = " ◄ anchor" if v == getattr(candidate, dim.replace("ny_", ""), None) or (
                dim == "ny_min_gap_atr_pct" and v == candidate.sessions[0].min_gap_atr_pct) else ""
            collapse = " ✗ COLLAPSE" if delta < -5.0 else ""
            print(f"    {v:<10} {lm['total_trades']}tr  Calm {lm['calmar_ratio']:>7.2f} ({delta:>+.2f})"
                  f"  NegYr {sum(1 for rv in lm.get('r_by_year', {}).values() if rv < 0)}{marker}{collapse}", flush=True)
            if collapse:
                local_ok = False

    plateau = "PLATEAU" if local_ok else "SPIKE"
    print(f"\n  Plateau judgment: {plateau}", flush=True)
    print(f"\n  >> PHASE 4: {fmt(local_ok)}", flush=True)
    results["Phase 4"] = local_ok

    # ── Phase 5: Monte Carlo Survival ─────────────────────────────────
    section(f"[{name}] PHASE 5: MONTE CARLO SURVIVAL")
    mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)

    t0 = time.time()
    mc_result = run_monte_carlo(wf_result.combined_oos_trades, mc_config,
                                ruin_threshold=-MC_SURVIVAL_DD)
    print(f"  Completed in {time.time() - t0:.1f}s", flush=True)

    trade_dates = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_constraints = PropFirmConstraints(max_drawdown_r=MC_SURVIVAL_DD, min_annual_r=12.0, max_monthly_loss_r=5.0)
    mc_surv = evaluate_constraints_mc(mc_result, mc_constraints, trade_dates=trade_dates)

    survival_ok = mc_surv["survival_rate"] >= 0.70
    ruin_ok = mc_result.ruin_probability < 0.05

    print(f"\n  DD percentiles: {mc_surv['dd_percentiles']}", flush=True)
    print(f"  Sharpe percentiles: {mc_result.sharpe_percentiles}", flush=True)

    print(f"\n  {'Check':<28} {'Value':>12}  {'Threshold':>12}  {'Result':>8}", flush=True)
    print(f"  {'-'*66}", flush=True)
    print(f"  {'Survival at ' + str(MC_SURVIVAL_DD) + 'R':<28} {mc_surv['survival_rate']:>12.1%}  {'>=70%':>12}  {fmt(survival_ok):>8}", flush=True)
    print(f"  {'Ruin probability':<28} {mc_result.ruin_probability:>12.1%}  {'<5%':>12}  {fmt(ruin_ok):>8}", flush=True)

    p5_pass = survival_ok and ruin_ok
    print(f"\n  >> PHASE 5: {fmt(p5_pass)}", flush=True)
    results["Phase 5"] = p5_pass

    # ── Summary ───────────────────────────────────────────────────────
    section(f"[{name}] VERDICT")
    all_pass = all(results.values())
    for phase, passed in results.items():
        print(f"  {phase:<20} {fmt(passed)}", flush=True)

    if all_pass:
        verdict = "PROMOTE"
    elif sum(results.values()) >= 4:
        verdict = "CHALLENGER"
    else:
        verdict = "REJECT"

    print(f"\n  >> CANDIDATE {name}: {verdict}", flush=True)
    print(f"  Bailey caveat: PBO/CSCV not implemented; verdict is heuristic.", flush=True)

    return {
        "name": name,
        "verdict": verdict,
        "results": results,
        "wf_result": wf_result,
        "stability": stability,
        "mc_surv": mc_surv,
        "phase1_metrics": m,
        "oos_metrics": oos_m,
    }


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    t_global = time.time()

    # Phase 0: Hold-out freeze
    section("PHASE 0: HOLD-OUT PRE-REGISTRATION")
    check = check_holdout_period(HOLDOUT_START, "2026-03-31")
    if check.is_clean:
        print(f"  Hold-out {HOLDOUT_START} -> present is CLEAN.", flush=True)
    else:
        print(f"  WARNING: {check.warning}", flush=True)
    print(f"  All discovery work is pre-holdout only.", flush=True)

    # Load data
    section("LOADING DATA")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)
    print(f"  Maps built in {time.time() - t0:.1f}s", flush=True)

    # Run pipeline for each candidate
    verdicts = {}
    for cname, (candidate, pranges) in {
        "A": (CANDIDATE_A, PARAM_RANGES_A),
        "B": (CANDIDATE_B, PARAM_RANGES_B),
    }.items():
        verdicts[cname] = run_pipeline(cname, candidate, pranges, df_5m, df_1m, df_1s, maps)

    # ── Final Comparison ──────────────────────────────────────────────
    section("PROMOTION PACKET")
    print(f"  Hold-out: frozen at {HOLDOUT_START}", flush=True)
    print(f"  Search: Step 1 (20 filter combos) + Step 2 (128 sweeps) + Step 3 (this pipeline)", flush=True)
    print(f"  Bailey caveat: PBO/CSCV not implemented; verdict is heuristic.\n", flush=True)

    for cname, v in verdicts.items():
        r = v["results"]
        phases_passed = sum(r.values())
        oos = v["oos_metrics"]
        p1 = v["phase1_metrics"]
        print(f"  Candidate {cname}: {v['verdict']} ({phases_passed}/5 phases)", flush=True)
        print(f"    Pre-holdout: {p1['total_trades']}tr, Calmar {p1['calmar_ratio']:.2f}, Sharpe {p1['sharpe_ratio']:.2f}", flush=True)
        print(f"    WF OOS:      {oos['total_trades']}tr, Calmar {oos['calmar_ratio']:.2f}, Sharpe {oos['sharpe_ratio']:.2f}", flush=True)
        print(f"    MC survival: {v['mc_surv']['survival_rate']:.1%} at {MC_SURVIVAL_DD}R", flush=True)
        print(f"    Stability:   {v['stability'].overall_score:.3f} ({v['stability'].interpretation})", flush=True)
        print(flush=True)

    print(f"Total pipeline time: {time.time() - t_global:.0f}s", flush=True)


if __name__ == "__main__":
    main()
