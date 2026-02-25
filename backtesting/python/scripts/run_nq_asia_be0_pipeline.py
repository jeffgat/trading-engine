#!/usr/bin/env python3
"""NQ Asia v2 config — full 5-phase robust pipeline.
"""

import sys
import time
import pickle
from dataclasses import replace

import pandas as pd

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent / "src"))

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


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def main():
    asia = replace(
        ASIA_SESSION,
        orb_end="20:10",
        entry_start="20:10",
        entry_end="23:00",
        stop_atr_pct=5.75,
        min_gap_atr_pct=1.25,
        max_gap_atr_pct=11.0,
    )
    config = default_config(NQ)
    config = with_overrides(
        config,
        sessions=(asia,),
        rr=1.5,
        tp1_ratio=0.2,
        use_bar_magnifier=True,
        atr_length=5,
    )

    print("Config: NQ Asia v2")
    print(f"  use_bar_magnifier: {config.use_bar_magnifier}")
    print()

    print("Loading data...", flush=True)
    df = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")

    # ================================================================
    # PHASE 1: Structural Validation (full history)
    # ================================================================
    print("=" * 80)
    print("PHASE 1: STRUCTURAL VALIDATION (2015-01-01 to 2026-02)")
    print("=" * 80)
    t0 = time.time()
    all_trades = run_backtest(df, config, start_date="2015-01-01", df_1m=df_1m)
    all_trades = no_thursday_gate(all_trades)
    m1 = compute_metrics(all_trades)
    t1 = time.time() - t0
    print(f"  Completed in {t1:.1f}s")
    print(f"  Trades:     {m1['total_trades']}")
    print(f"  Win rate:   {m1['win_rate']:.1%}")
    print(f"  Net R:      {m1['total_r']:.1f}R")
    print(f"  Sharpe:     {m1['sharpe_ratio']:.3f}")
    print(f"  PF:         {m1['profit_factor']:.2f}")
    print(f"  Max DD (R): {m1['max_drawdown_r']:.1f}R")
    print(f"  Max consec losses: {m1.get('max_consecutive_losses', 'N/A')}")
    print()
    if "r_by_year" in m1:
        for yr, r in sorted(m1["r_by_year"].items()):
            print(f"    {yr}: {r:>8.1f}R")
    print()

    p1_1 = m1["total_trades"] >= 100
    p1_2 = m1["win_rate"] >= 0.35
    p1_3 = m1["profit_factor"] >= 1.0
    p1_4 = m1.get("max_consecutive_losses", 0) <= 15
    p1_pass = p1_1 and p1_2 and p1_3 and p1_4
    print("PASS CRITERIA:")
    print(f"  Trades >= 100:       {'PASS' if p1_1 else 'FAIL'} ({m1['total_trades']})")
    print(f"  Win rate >= 35%:     {'PASS' if p1_2 else 'FAIL'} ({m1['win_rate']:.1%})")
    print(f"  PF >= 1.0:           {'PASS' if p1_3 else 'FAIL'} ({m1['profit_factor']:.2f})")
    print(f"  Max consec <= 15:    {'PASS' if p1_4 else 'FAIL'} ({m1.get('max_consecutive_losses', 'N/A')})")
    print(f"  --> Phase 1: {'PASS' if p1_pass else 'FAIL'}")
    print("=" * 80)

    if not p1_pass:
        print("Phase 1 failed — aborting pipeline.")
        return

    # ================================================================
    # PHASE 2: Walk-Forward + Parameter Stability
    # ================================================================
    param_ranges = {
        "asia_stop_atr_pct": [4.5, 5.0, 5.5, 5.75, 6.0, 6.5, 7.0],
        "asia_min_gap_atr_pct": [0.75, 1.0, 1.25, 1.5, 1.75],
        "asia_max_gap_atr_pct": [8.0, 9.0, 10.0, 11.0, 12.0, 14.0],
        "rr": [1.25, 1.5, 1.75, 2.0],
        "tp1_ratio": [0.15, 0.2, 0.25, 0.3],
    }

    total_combos = 1
    for v in param_ranges.values():
        total_combos *= len(v)
    print(f"\nGrid: {total_combos} combos per fold", flush=True)

    def progress(fold_idx, total_folds, status):
        print(f"  Fold {fold_idx+1}/{total_folds}: {status}", flush=True)

    print("\nRunning walk-forward (36m IS / 12m OOS / 12m step, no-Thursday gate)...", flush=True)
    t0 = time.time()
    wf_result = run_walkforward(
        df.loc[:"2024-12-31"],
        config,
        param_ranges,
        is_months=36,
        oos_months=12,
        step_months=12,
        objective="sharpe",
        n_workers=8,
        start_date="2015-01-01",
        progress_fn=progress,
        df_1m=df_1m.loc[:"2024-12-31"],
        max_dd_r=-10.0,
        gate_fn=no_thursday_gate,
    )
    t_wf = time.time() - t0
    print(f"  Completed in {t_wf:.1f}s", flush=True)

    print()
    print("=" * 80)
    print("PHASE 2: WALK-FORWARD + PARAMETER STABILITY")
    print("=" * 80)
    print(f"Folds: {len(wf_result.folds)}")
    print(f"WF Efficiency: {wf_result.walk_forward_efficiency:.3f}")
    print()

    for fold in wf_result.folds:
        print(f"Fold {fold.fold_index}: IS {fold.is_start} to {fold.is_end} | OOS {fold.oos_start} to {fold.oos_end}")
        is_m = fold.is_metrics
        oos_m = fold.oos_metrics
        print(f"  IS:  Sharpe={is_m.get('sharpe_ratio', 0):.3f}, "
              f"trades={is_m.get('total_trades', 0)}, "
              f"R={is_m.get('total_r', 0):.1f}, "
              f"WR={is_m.get('win_rate', 0):.1%}")
        print(f"  OOS: Sharpe={oos_m.get('sharpe_ratio', 0):.3f}, "
              f"trades={oos_m.get('total_trades', 0)}, "
              f"R={oos_m.get('total_r', 0):.1f}, "
              f"WR={oos_m.get('win_rate', 0):.1%}")
        print(f"  Best: {fold.best_params}")
        print()

    cm = wf_result.combined_oos_metrics
    print("Combined OOS:")
    print(f"  Trades={cm['total_trades']}, R={cm['total_r']:.1f}, WR={cm['win_rate']:.1%}, "
          f"PF={cm['profit_factor']:.2f}, Sharpe={cm['sharpe_ratio']:.3f}, DD={cm['max_drawdown_r']:.1f}R")
    print()

    stability = analyze_parameter_stability(wf_result, param_ranges)
    print(f"Stability: {stability.overall_score:.3f} ({stability.interpretation})")
    for p in stability.params:
        print(f"  {p.name}: mode={p.mode}, score={p.stability_score:.2f}, "
              f"range={p.value_range}, unique={p.unique_values}")
    print()

    p2_1 = wf_result.walk_forward_efficiency >= 0.5
    p2_2 = stability.overall_score >= 0.4
    p2_3 = len(wf_result.folds) >= 4
    p2_pass = p2_1 and p2_2 and p2_3
    print("PASS CRITERIA:")
    print(f"  WF efficiency >= 0.5: {'PASS' if p2_1 else 'FAIL'} ({wf_result.walk_forward_efficiency:.3f})")
    print(f"  Stability >= 0.4:     {'PASS' if p2_2 else 'FAIL'} ({stability.overall_score:.3f})")
    print(f"  Folds >= 4:           {'PASS' if p2_3 else 'FAIL'} ({len(wf_result.folds)})")
    print(f"  --> Phase 2: {'PASS' if p2_pass else 'FAIL'}")
    print("=" * 80)

    with open("/tmp/wf_result_nq_asia_be0.pkl", "wb") as f:
        pickle.dump(wf_result, f)
    with open("/tmp/stability_nq_asia_be0.pkl", "wb") as f:
        pickle.dump(stability, f)

    # ================================================================
    # PHASE 3: Prop Firm Constraint Filter
    # ================================================================
    constraints = PropFirmConstraints(
        max_drawdown_r=10.0,
        min_annual_r=24.0,
        max_monthly_loss_r=5.0,
        min_positive_expectancy=True,
    )
    cr = evaluate_constraints(wf_result.combined_oos_trades, constraints)

    print()
    print("=" * 60)
    print("PHASE 3: PROP FIRM CONSTRAINT FILTER")
    print("=" * 60)
    print(f"  Max DD:      {cr.max_drawdown_r:.1f}R  {'PASS' if cr.max_drawdown_passed else 'FAIL'} (threshold: {constraints.max_drawdown_r}R)")
    print(f"  Annual R:    {'PASS' if cr.annual_r_passed else 'FAIL'}")
    for yr, r in sorted(cr.annual_r_values.items()):
        print(f"    {yr}: {r:>8.1f}R")
    print(f"  Monthly:     worst={cr.worst_month_r:.1f}R  {'PASS' if cr.monthly_loss_passed else 'FAIL'} (threshold: {constraints.max_monthly_loss_r}R)")
    print(f"  Expectancy:  {cr.expectancy:.4f}R  {'PASS' if cr.expectancy_passed else 'FAIL'}")
    print(f"  Stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, avg win {cr.avg_win_r:.3f}R, avg loss {cr.avg_loss_r:.3f}R")
    print(f"  Total R: {cr.total_r:.1f}R")
    worst_months = sorted(cr.monthly_r_values.items(), key=lambda x: x[1])[:5]
    print("  Worst 5 months:")
    for m_key, r in worst_months:
        print(f"    {m_key}: {r:>8.1f}R")
    print(f"  Overall: {'PASS' if cr.passed else 'FAIL'}")
    print("=" * 60)

    # ================================================================
    # PHASE 4: Hold-Out OOS
    # ================================================================
    holdout_trades = run_backtest(df, config, start_date="2025-01-01", df_1m=df_1m)
    holdout_trades = no_thursday_gate(holdout_trades)
    hm = compute_metrics(holdout_trades)

    print()
    print("=" * 60)
    print("PHASE 4: HOLD-OUT OOS TEST (2025-01 to 2026-02)")
    print("=" * 60)
    print(f"  Trades:       {hm['total_trades']}")
    print(f"  Win rate:     {hm['win_rate']:.1%}")
    print(f"  Net R:        {hm['total_r']:.1f}R")
    print(f"  Sharpe:       {hm['sharpe_ratio']:.3f}")
    print(f"  PF:           {hm['profit_factor']:.2f}")
    print(f"  Max DD (R):   {hm['max_drawdown_r']:.1f}R")
    if "r_by_year" in hm:
        for yr, r in sorted(hm["r_by_year"].items()):
            print(f"    {yr}: {r:>8.1f}R")

    p4_1 = hm["sharpe_ratio"] > 0.5
    p4_2 = hm["profit_factor"] > 1.0
    p4_3 = hm["total_r"] > 0
    p4_pass = p4_1 and p4_2 and p4_3
    print(f"  PASS CRITERIA:")
    print(f"    Sharpe > 0.5:   {'PASS' if p4_1 else 'FAIL'} ({hm['sharpe_ratio']:.3f})")
    print(f"    PF > 1.0:       {'PASS' if p4_2 else 'FAIL'} ({hm['profit_factor']:.2f})")
    print(f"    Total R > 0:    {'PASS' if p4_3 else 'FAIL'} ({hm['total_r']:.1f}R)")
    print(f"  --> Phase 4: {'PASS' if p4_pass else 'FAIL'}")
    print("=" * 60)

    # ================================================================
    # PHASE 5: Monte Carlo Survival
    # ================================================================
    filled_oos = [t for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_config = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    mc_result = run_monte_carlo(wf_result.combined_oos_trades, mc_config, ruin_threshold=-10.0)

    trade_dates = [t.date for t in filled_oos]
    mc_surv = evaluate_constraints_mc(mc_result, constraints, trade_dates=trade_dates)

    print()
    print("=" * 60)
    print("PHASE 5: MONTE CARLO SURVIVAL")
    print("=" * 60)
    print(f"  Sims: {mc_result.n_simulations}, Trades: {mc_result.n_trades}")
    print(f"  Actual: {mc_result.actual_final_pnl:.1f}R final, {mc_result.actual_max_drawdown:.1f}R DD")
    print(f"  Final PnL p5/p50/p95: {mc_result.final_pnl_percentiles['p5']:.1f} / {mc_result.final_pnl_percentiles['p50']:.1f} / {mc_result.final_pnl_percentiles['p95']:.1f}")
    print(f"  Max DD p5/p50/p95: {mc_result.max_dd_percentiles['p5']:.1f} / {mc_result.max_dd_percentiles['p50']:.1f} / {mc_result.max_dd_percentiles['p95']:.1f}")
    print(f"  Ruin probability (>{abs(mc_result.ruin_threshold)}R): {mc_result.ruin_probability:.1%}")
    print()
    print(f"  DD Survival rate (<=10R):   {mc_surv['survival_rate']:.1%}")
    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate:     {mc_surv['monthly_loss_pass_rate']:.1%}")
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate:         {mc_surv['annual_r_pass_rate']:.1%}")

    p5_1 = mc_surv["survival_rate"] >= 0.70
    p5_2 = mc_surv["dd_percentiles"]["p95"] <= constraints.max_drawdown_r * 1.2
    p5_pass = p5_1 and p5_2
    print(f"  PASS CRITERIA:")
    print(f"    Survival >= 70%:     {'PASS' if p5_1 else 'FAIL'} ({mc_surv['survival_rate']:.1%})")
    print(f"    p95 DD <= 12R:       {'PASS' if p5_2 else 'FAIL'} ({mc_surv['dd_percentiles']['p95']:.1f}R)")
    print(f"  --> Phase 5: {'PASS' if p5_pass else 'FAIL'}")
    print("=" * 60)

    # ================================================================
    # FINAL SUMMARY
    # ================================================================
    print()
    print("=" * 60)
    print("PIPELINE SUMMARY — NQ Asia v2")
    print("=" * 60)
    results = [
        ("Phase 1 (Structural)", p1_pass, f"{m1['total_trades']} trades, {m1['win_rate']:.1%} WR, PF {m1['profit_factor']:.2f}"),
        ("Phase 2 (Walk-Forward)", p2_pass, f"WF eff {wf_result.walk_forward_efficiency:.2f}, stab {stability.overall_score:.2f}"),
        ("Phase 3 (Prop Filter)", cr.passed, f"DD {cr.max_drawdown_r:.1f}R, worst mo {cr.worst_month_r:.1f}R"),
        ("Phase 4 (Hold-Out)", p4_pass, f"Sharpe {hm['sharpe_ratio']:.2f}, PF {hm['profit_factor']:.2f}, {hm['total_r']:.1f}R"),
        ("Phase 5 (MC Survival)", p5_pass, f"{mc_surv['survival_rate']:.0%} survival at 10R DD"),
    ]
    for name, passed, detail in results:
        print(f"  {name:25s} {'PASS' if passed else 'FAIL'} — {detail}")

    all_pass = p1_pass and p2_pass and cr.passed and p4_pass and p5_pass
    if all_pass:
        verdict = "GO"
    elif not p5_pass and mc_surv["survival_rate"] >= 0.50:
        verdict = "CONDITIONAL"
    elif p1_pass and p2_pass and not cr.passed and not p5_pass and mc_surv["survival_rate"] >= 0.50:
        verdict = "CONDITIONAL"
    else:
        verdict = "NO-GO"
    print(f"  --> VERDICT: {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    main()
