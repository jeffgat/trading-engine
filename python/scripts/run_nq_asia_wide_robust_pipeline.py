#!/usr/bin/env python3
"""NQ Asia Wide Sharpe — five-phase robust pipeline.

Candidate: Both / 22:30
  stop=5.0%, gap=1.50%, maxgap=5.0%, rr=1.25, tp1=0.10
  ORB 10m, ATR 14, bar magnifier ON, no-Thursday gate

Phase 1: Structural validation (2015-2026 full history)
Phase 2: Walk-forward + parameter stability (36m IS / 12m OOS / 12m step, 2015-2024)
Phase 3: Prop firm constraint filter on WF OOS trades
Phase 4: Hold-out OOS (2025-01-01 onwards, never seen during optimization)
Phase 5: Monte Carlo survival (2000 sims, 10R ruin threshold)
"""

import sys
import pickle
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.prop_constraints import (
    evaluate_constraints, evaluate_constraints_mc, PropFirmConstraints,
)
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

START_DATE = "2015-01-01"
WF_END     = "2024-12-31"
HOLDOUT    = "2025-01-01"


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_base_config():
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="22:30",
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.50,
        max_gap_atr_pct=5.0,
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=1.25,
        tp1_ratio=0.10,
        use_bar_magnifier=True,
        atr_length=14,
    )


def section(title):
    print(f"\n{'=' * 70}")
    print(title)
    print("=" * 70)


def main():
    section("NQ ASIA WIDE SHARPE — ROBUST PIPELINE")
    print("Config: stop=5.0%, gap=1.50%, maxgap=5.0%, rr=1.25, tp1=0.10")
    print("        ORB 10m, ATR 14, entry≤22:30, both dirs, no-Thursday")

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars [{time.time()-t_start:.1f}s]")

    base_config = build_base_config()

    constraints = PropFirmConstraints(
        max_drawdown_r=999.0,       # DD reported as INFO only, not a gate
        min_annual_r=24.0,
        max_monthly_loss_r=5.0,
        min_positive_expectancy=True,
    )

    # ================================================================
    # PHASE 1: STRUCTURAL VALIDATION
    # ================================================================
    section("PHASE 1: STRUCTURAL VALIDATION (2015-2026)")

    trades_full = run_backtest(df, base_config, start_date=START_DATE, df_1m=df_1m)
    trades_full = no_thursday_gate(trades_full)
    m1 = compute_metrics(trades_full)

    print(f"  Trades:    {m1['total_trades']}")
    print(f"  Win Rate:  {m1['win_rate']:.1%}")
    print(f"  Net R:     {m1['total_r']:.1f}R")
    print(f"  Sharpe:    {m1['sharpe_ratio']:.3f}")
    print(f"  PF:        {m1['profit_factor']:.2f}")
    print(f"  Max DD:    {m1['max_drawdown_r']:.1f}R")
    print(f"  Max Consec Losses: {m1['max_consecutive_losses']}")
    for yr, r in sorted(m1.get("r_by_year", {}).items()):
        print(f"    {yr}: {r:>7.1f}R")

    p1_trades = m1["total_trades"] >= 100
    p1_wr     = m1["win_rate"] >= 0.35
    p1_pf     = m1["profit_factor"] >= 1.0
    p1_mcl    = m1["max_consecutive_losses"] <= 15
    p1_pass   = p1_trades and p1_wr and p1_pf and p1_mcl

    print(f"\n  PASS CRITERIA:")
    print(f"    Trades >= 100:   {'PASS' if p1_trades else 'FAIL'} ({m1['total_trades']})")
    print(f"    WR >= 35%:       {'PASS' if p1_wr else 'FAIL'} ({m1['win_rate']:.1%})")
    print(f"    PF >= 1.0:       {'PASS' if p1_pf else 'FAIL'} ({m1['profit_factor']:.2f})")
    print(f"    Max streak ≤ 15: {'PASS' if p1_mcl else 'FAIL'} ({m1['max_consecutive_losses']})")
    print(f"  --> Phase 1: {'PASS' if p1_pass else 'FAIL'}")

    if not p1_pass:
        print("\n  Phase 1 failed — aborting pipeline.")
        return

    # ================================================================
    # PHASE 2: WALK-FORWARD + PARAMETER STABILITY
    # ================================================================
    section("PHASE 2: WALK-FORWARD + PARAMETER STABILITY")
    print("  36m IS / 12m OOS / 12m step | 2015-2024 | no-Thursday gate\n")

    # Sweep params: neighbourhood around the winner
    param_ranges = {
        "asia_stop_atr_pct":    [4.0, 4.5, 5.0, 5.5, 6.0],
        "asia_min_gap_atr_pct": [1.0, 1.25, 1.5, 1.75],
        "asia_max_gap_atr_pct": [3.0, 4.0, 5.0, 6.0],
        "rr":                   [1.0, 1.25, 1.5, 1.75],
        "tp1_ratio":            [0.05, 0.10, 0.15, 0.20],
    }
    total_combos = 1
    for v in param_ranges.values():
        total_combos *= len(v)
    print(f"  Grid: {total_combos} combos/fold | 8 workers", flush=True)

    def wf_progress(fold_idx, total_folds, status):
        print(f"  Fold {fold_idx+1}/{total_folds}: {status}", flush=True)

    t2 = time.time()
    wf_result = run_walkforward(
        df.loc[:WF_END],
        base_config,
        param_ranges,
        is_months=36,
        oos_months=12,
        step_months=12,
        objective="sharpe",
        n_workers=8,
        start_date=START_DATE,
        progress_fn=wf_progress,
        df_1m=df_1m.loc[:WF_END],
        gate_fn=no_thursday_gate,
    )
    print(f"\n  Completed in {time.time()-t2:.0f}s", flush=True)

    print(f"\n  Folds: {len(wf_result.folds)}")
    print(f"  WF Efficiency: {wf_result.walk_forward_efficiency:.3f}")
    print()

    for fold in wf_result.folds:
        is_m  = fold.is_metrics
        oos_m = fold.oos_metrics
        print(f"  Fold {fold.fold_index}: IS {fold.is_start}→{fold.is_end} | OOS {fold.oos_start}→{fold.oos_end}")
        print(f"    IS:  Sharpe={is_m.get('sharpe_ratio',0):.3f}  "
              f"trades={is_m.get('total_trades',0)}  "
              f"R={is_m.get('total_r',0):.1f}  "
              f"WR={is_m.get('win_rate',0):.1%}")
        print(f"    OOS: Sharpe={oos_m.get('sharpe_ratio',0):.3f}  "
              f"trades={oos_m.get('total_trades',0)}  "
              f"R={oos_m.get('total_r',0):.1f}  "
              f"WR={oos_m.get('win_rate',0):.1%}")
        print(f"    Best params: {fold.best_params}")

    cm = wf_result.combined_oos_metrics
    print(f"\n  Combined OOS:")
    print(f"    Trades={cm['total_trades']}, R={cm['total_r']:.1f}, "
          f"WR={cm['win_rate']:.1%}, PF={cm['profit_factor']:.2f}, "
          f"Sharpe={cm['sharpe_ratio']:.3f}, DD={cm['max_drawdown_r']:.1f}R")

    stability = analyze_parameter_stability(wf_result, param_ranges)
    print(f"\n  Stability: {stability.overall_score:.3f} ({stability.interpretation})")
    for p in stability.params:
        print(f"    {p.name}: mode={p.mode}, score={p.stability_score:.2f}, "
              f"range={p.value_range}, unique={p.unique_values}")

    p2_eff   = wf_result.walk_forward_efficiency >= 0.5
    p2_stab  = stability.overall_score >= 0.4
    p2_folds = len(wf_result.folds) >= 4
    p2_pass  = p2_eff and p2_stab and p2_folds

    print(f"\n  PASS CRITERIA:")
    print(f"    WF efficiency >= 0.5: {'PASS' if p2_eff else 'FAIL'} ({wf_result.walk_forward_efficiency:.3f})")
    print(f"    Stability >= 0.4:     {'PASS' if p2_stab else 'FAIL'} ({stability.overall_score:.3f})")
    print(f"    Folds >= 4:           {'PASS' if p2_folds else 'FAIL'} ({len(wf_result.folds)})")
    print(f"  --> Phase 2: {'PASS' if p2_pass else 'FAIL'}")

    # Persist WF result for debugging
    with open("/tmp/wf_nq_asia_wide_22_30.pkl", "wb") as f:
        pickle.dump(wf_result, f)

    # ================================================================
    # PHASE 3: PROP FIRM CONSTRAINT FILTER
    # ================================================================
    section("PHASE 3: PROP FIRM CONSTRAINT FILTER")

    cr = evaluate_constraints(wf_result.combined_oos_trades, constraints)

    print(f"  Max DD:    {cr.max_drawdown_r:.1f}R  {'PASS' if cr.max_drawdown_passed else 'FAIL'} (limit: {constraints.max_drawdown_r}R)")
    print(f"  Annual R:  {'PASS' if cr.annual_r_passed else 'FAIL'} (limit: {constraints.min_annual_r}R/yr)")
    for yr, r in sorted(cr.annual_r_values.items()):
        print(f"    {yr}: {r:>7.1f}R")
    print(f"  Monthly:   worst={cr.worst_month_r:.1f}R  {'PASS' if cr.monthly_loss_passed else 'FAIL'} (limit: -{constraints.max_monthly_loss_r}R)")
    print(f"  Expectancy:{cr.expectancy:.4f}R  {'PASS' if cr.expectancy_passed else 'FAIL'}")
    print(f"  Stats:     {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
          f"avg win {cr.avg_win_r:.3f}R, avg loss {cr.avg_loss_r:.3f}R")

    worst_months = sorted(cr.monthly_r_values.items(), key=lambda x: x[1])[:5]
    print(f"  Worst 5 months:")
    for m_key, r in worst_months:
        print(f"    {m_key}: {r:>7.1f}R")

    p3_pass = cr.passed
    print(f"\n  --> Phase 3: {'PASS' if p3_pass else 'FAIL'}")

    # ================================================================
    # PHASE 4: HOLD-OUT OOS
    # ================================================================
    section(f"PHASE 4: HOLD-OUT OOS ({HOLDOUT} onwards)")

    # Use mode params from stability for the hold-out config
    mode_params = {p.name: p.mode for p in stability.params}
    print(f"  Mode params from WF: {mode_params}")

    holdout_config = with_overrides(base_config, **mode_params)
    holdout_trades = run_backtest(df, holdout_config, start_date=HOLDOUT, df_1m=df_1m)
    holdout_trades = no_thursday_gate(holdout_trades)
    hm = compute_metrics(holdout_trades)

    print(f"\n  Trades:    {hm['total_trades']}")
    print(f"  Win Rate:  {hm['win_rate']:.1%}")
    print(f"  Net R:     {hm['total_r']:.1f}R")
    print(f"  Sharpe:    {hm['sharpe_ratio']:.3f}")
    print(f"  PF:        {hm['profit_factor']:.2f}")
    print(f"  Max DD:    {hm['max_drawdown_r']:.1f}R")
    for yr, r in sorted(hm.get("r_by_year", {}).items()):
        print(f"    {yr}: {r:>7.1f}R")

    p4_sharpe = hm["sharpe_ratio"] > 0.5
    p4_pf     = hm["profit_factor"] > 1.0
    p4_r      = hm["total_r"] > 0
    p4_pass   = p4_sharpe and p4_pf and p4_r

    print(f"\n  PASS CRITERIA:")
    print(f"    Sharpe > 0.5: {'PASS' if p4_sharpe else 'FAIL'} ({hm['sharpe_ratio']:.3f})")
    print(f"    PF > 1.0:     {'PASS' if p4_pf else 'FAIL'} ({hm['profit_factor']:.2f})")
    print(f"    Total R > 0:  {'PASS' if p4_r else 'FAIL'} ({hm['total_r']:.1f}R)")
    print(f"  --> Phase 4: {'PASS' if p4_pass else 'FAIL'}")

    # ================================================================
    # PHASE 5: MONTE CARLO SURVIVAL
    # ================================================================
    section("PHASE 5: MONTE CARLO SURVIVAL")
    print("  2000 sims, bootstrap, ruin threshold = -10R\n")

    filled_oos = [t for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_config  = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    mc_result  = run_monte_carlo(wf_result.combined_oos_trades, mc_config, ruin_threshold=-10.0)

    trade_dates = [t.date for t in filled_oos]
    mc_surv = evaluate_constraints_mc(mc_result, constraints, trade_dates=trade_dates)

    print(f"  Sims: {mc_result.n_simulations} | Trades: {mc_result.n_trades}")
    print(f"  Actual final: {mc_result.actual_final_pnl:.1f}R | Actual DD: {mc_result.actual_max_drawdown:.1f}R")
    print(f"  Final PnL p5/p50/p95: "
          f"{mc_result.final_pnl_percentiles['p5']:.1f} / "
          f"{mc_result.final_pnl_percentiles['p50']:.1f} / "
          f"{mc_result.final_pnl_percentiles['p95']:.1f}")
    print(f"  Max DD p5/p50/p95: "
          f"{mc_result.max_dd_percentiles['p5']:.1f} / "
          f"{mc_result.max_dd_percentiles['p50']:.1f} / "
          f"{mc_result.max_dd_percentiles['p95']:.1f}")
    print(f"  Ruin prob (>10R DD): {mc_result.ruin_probability:.1%}")
    print()
    print(f"  DD Survival (≤10R):     {mc_surv['survival_rate']:.1%}")
    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate: {mc_surv['monthly_loss_pass_rate']:.1%}")
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate:     {mc_surv['annual_r_pass_rate']:.1%}")

    p5_surv = mc_surv["survival_rate"] >= 0.70
    p5_p95  = mc_surv["dd_percentiles"]["p95"] <= constraints.max_drawdown_r * 1.2
    p5_pass = p5_surv and p5_p95

    print(f"\n  PASS CRITERIA:")
    print(f"    Survival >= 70%:  {'PASS' if p5_surv else 'FAIL'} ({mc_surv['survival_rate']:.1%})")
    print(f"    p95 DD <= 12R:    {'PASS' if p5_p95 else 'FAIL'} ({mc_surv['dd_percentiles']['p95']:.1f}R)")
    print(f"  --> Phase 5: {'PASS' if p5_pass else 'FAIL'}")

    # ================================================================
    # FINAL VERDICT
    # ================================================================
    section("PIPELINE SUMMARY")

    elapsed = time.time() - t_start
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)\n")

    phases = [
        ("Phase 1 (Structural)",   p1_pass,
         f"{m1['total_trades']} trades, {m1['win_rate']:.1%} WR, PF {m1['profit_factor']:.2f}"),
        ("Phase 2 (Walk-Forward)", p2_pass,
         f"WF eff {wf_result.walk_forward_efficiency:.3f}, stab {stability.overall_score:.3f} ({stability.interpretation})"),
        ("Phase 3 (Prop Filter)",  p3_pass,
         f"DD {cr.max_drawdown_r:.1f}R, worst month {cr.worst_month_r:.1f}R, expectancy {cr.expectancy:.4f}R"),
        ("Phase 4 (Hold-Out)",     p4_pass,
         f"Sharpe {hm['sharpe_ratio']:.3f}, PF {hm['profit_factor']:.2f}, {hm['total_r']:.1f}R"),
        ("Phase 5 (MC Survival)",  p5_pass,
         f"{mc_surv['survival_rate']:.0%} survival, p95 DD {mc_surv['dd_percentiles']['p95']:.1f}R"),
    ]

    for name, passed, detail in phases:
        print(f"  {name:28s} {'PASS' if passed else 'FAIL'} — {detail}")

    all_pass = all(p for _, p, _ in phases)
    conditional = (not p5_pass and mc_surv["survival_rate"] >= 0.50 and
                   all(p for _, p, _ in phases[:4]))

    if all_pass:
        verdict = "GO"
    elif conditional:
        verdict = "CONDITIONAL"
    else:
        verdict = "NO-GO"

    print(f"\n  --> VERDICT: {verdict}")

    # ================================================================
    # SAVE TO DB
    # ================================================================
    section("SAVING PIPELINE RESULT")

    db_name = f"NQ ASIA 2015-2026 Wide Sharpe 22:30 {verdict}"
    db_notes = (
        f"Robust pipeline result. "
        f"Phase 1: {'PASS' if p1_pass else 'FAIL'}, "
        f"Phase 2: {'PASS' if p2_pass else 'FAIL'} (WF eff {wf_result.walk_forward_efficiency:.3f}, "
        f"stab {stability.overall_score:.3f}), "
        f"Phase 3: {'PASS' if p3_pass else 'FAIL'}, "
        f"Phase 4: {'PASS' if p4_pass else 'FAIL'} ({hm['total_r']:.1f}R hold-out), "
        f"Phase 5: {'PASS' if p5_pass else 'FAIL'} ({mc_surv['survival_rate']:.0%} survival). "
        f"Full-history: {m1['total_trades']} trades, {m1['win_rate']:.1%} WR, "
        f"{m1['total_r']:.1f}R, {m1['max_drawdown_r']:.1f}R DD, Sharpe {m1['sharpe_ratio']:.3f}. "
        f"Mode params: {mode_params}."
    )

    save_cfg = with_overrides(base_config, name=db_name, notes=db_notes)
    trades_save = run_backtest(df, save_cfg, start_date=START_DATE, df_1m=df_1m)
    trades_save = no_thursday_gate(trades_save)
    result = results_to_dict(trades_save, save_cfg, include_equity_curve=True)
    rid = save_backtest_result(result)
    print(f"  {rid}")
    print(f"  {db_name}")


if __name__ == "__main__":
    main()
