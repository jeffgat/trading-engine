#!/usr/bin/env python3
"""NQ Asia Wide Prop config — robust pipeline Phases 1-5.

Config under test:
  stop=6.5%, gap=1.25%, maxgap=5.0%, rr=1.5, tp1=0.25
  ORB 10m, ATR 14, no-Thursday gate, entry 20:10–23:00

Comparison baseline (v2 CONDITIONAL):
  stop=5.75%, gap=1.25%, maxgap=11.0%, rr=1.5, tp1=0.2
  ORB 10m, ATR 5, no-Thursday gate
  Full-history: 1,757 trades, 78.5% WR, 113.4R, Sharpe 1.745, DD -9.3R
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


def build_config():
    asia = replace(
        ASIA_SESSION,
        orb_end="20:10",
        entry_start="20:10",
        entry_end="23:00",
        stop_atr_pct=6.5,
        min_gap_atr_pct=1.25,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=1.5,
        tp1_ratio=0.25,
        use_bar_magnifier=True,
        atr_length=14,
    )


def main():
    config = build_config()

    param_ranges = {
        "asia_stop_atr_pct":    [5.5, 6.0, 6.5, 7.0],
        "asia_min_gap_atr_pct": [0.75, 1.0, 1.25, 1.5],
        "asia_max_gap_atr_pct": [5.0, 7.0, 9.0, 11.0],
        "rr":                   [1.0, 1.25, 1.5, 1.75, 2.0],
        "tp1_ratio":            [0.15, 0.2, 0.25, 0.3],
    }

    total = 1
    for v in param_ranges.values():
        total *= len(v)

    print("NQ Asia Wide Prop — Robust Pipeline")
    print("Config: stop=6.5%, gap=1.25%, maxgap=5.0%, rr=1.5, tp1=0.25, ATR 14, ORB 10m, no-Thu")
    print(f"WF grid: {total:,} combos per fold")
    print()

    print("Loading data...", flush=True)
    t_start = time.time()
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t_start:.1f}s]")

    # ================================================================
    # PHASE 1: Structural check (full history)
    # ================================================================
    print()
    print("=" * 70)
    print("PHASE 1: STRUCTURAL CHECK (2015-01-01 to present)")
    print("=" * 70)

    all_trades = run_backtest(df, config, start_date="2015-01-01", df_1m=df_1m)
    all_trades = no_thursday_gate(all_trades)
    filled     = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
    m1         = compute_metrics(all_trades)

    print(f"  Trades:     {m1['total_trades']} ({len(filled)} filled)")
    print(f"  Win rate:   {m1['win_rate']:.1%}")
    print(f"  Net R:      {m1['total_r']:.1f}R")
    print(f"  Sharpe:     {m1['sharpe_ratio']:.3f}")
    print(f"  PF:         {m1['profit_factor']:.2f}")
    print(f"  Max DD:     {m1['max_drawdown_r']:.1f}R")
    print(f"  R/trade:    {m1['avg_r']:.4f}")
    print()
    for yr, r in sorted(m1.get("r_by_year", {}).items()):
        flag = " *" if r < 0 else ""
        print(f"    {yr}: {r:>7.1f}R{flag}")

    p1_1 = m1["total_trades"] >= 100
    p1_2 = m1["win_rate"] >= 0.35
    p1_3 = m1["profit_factor"] >= 1.0
    p1_pass = p1_1 and p1_2 and p1_3
    print()
    print("  PASS CRITERIA:")
    print(f"    Trades >= 100:  {'PASS' if p1_1 else 'FAIL'} ({m1['total_trades']})")
    print(f"    WR >= 35%:      {'PASS' if p1_2 else 'FAIL'} ({m1['win_rate']:.1%})")
    print(f"    PF >= 1.0:      {'PASS' if p1_3 else 'FAIL'} ({m1['profit_factor']:.2f})")
    print(f"  --> Phase 1: {'PASS' if p1_pass else 'FAIL'}")
    print("=" * 70)

    if not p1_pass:
        print("\nPhase 1 FAIL — aborting pipeline.")
        return

    # ================================================================
    # PHASE 2: Walk-forward + parameter stability
    # ================================================================
    print()
    print("Running walk-forward (36m IS / 12m OOS / 12m step, no-Thursday gate)...", flush=True)

    def progress(fold_idx, total_folds, status):
        print(f"  Fold {fold_idx+1}/{total_folds}: {status}", flush=True)

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
    print(f"  Completed in {time.time()-t0:.1f}s", flush=True)

    print()
    print("=" * 70)
    print("PHASE 2: WALK-FORWARD + PARAMETER STABILITY")
    print("=" * 70)
    print(f"Folds: {len(wf_result.folds)}")
    print(f"WF Efficiency: {wf_result.walk_forward_efficiency:.3f}")
    print()

    for fold in wf_result.folds:
        print(f"Fold {fold.fold_index}: IS {fold.is_start} → {fold.is_end} | OOS {fold.oos_start} → {fold.oos_end}")
        is_m  = fold.is_metrics
        oos_m = fold.oos_metrics
        print(f"  IS:  Sharpe={is_m.get('sharpe_ratio',0):.3f}, "
              f"trades={is_m.get('total_trades',0)}, "
              f"R={is_m.get('total_r',0):.1f}, "
              f"WR={is_m.get('win_rate',0):.1%}")
        print(f"  OOS: Sharpe={oos_m.get('sharpe_ratio',0):.3f}, "
              f"trades={oos_m.get('total_trades',0)}, "
              f"R={oos_m.get('total_r',0):.1f}, "
              f"WR={oos_m.get('win_rate',0):.1%}")
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
    print("  PASS CRITERIA:")
    print(f"    WF efficiency >= 0.5: {'PASS' if p2_1 else 'FAIL'} ({wf_result.walk_forward_efficiency:.3f})")
    print(f"    Stability >= 0.4:     {'PASS' if p2_2 else 'FAIL'} ({stability.overall_score:.3f})")
    print(f"    Folds >= 4:           {'PASS' if p2_3 else 'FAIL'} ({len(wf_result.folds)})")
    print(f"  --> Phase 2: {'PASS' if p2_pass else 'FAIL'}")
    print("=" * 70)

    with open("/tmp/wf_result_nq_asia_wide_prop.pkl", "wb") as f:
        pickle.dump(wf_result, f)

    # ================================================================
    # PHASE 3: Prop firm constraints
    # ================================================================
    constraints = PropFirmConstraints(
        max_drawdown_r=10.0,
        min_annual_r=24.0,
        max_monthly_loss_r=5.0,
        min_positive_expectancy=True,
    )
    cr = evaluate_constraints(wf_result.combined_oos_trades, constraints)

    print()
    print("=" * 70)
    print("PHASE 3: PROP FIRM CONSTRAINT FILTER")
    print("=" * 70)
    print(f"  Max DD:     {cr.max_drawdown_r:.1f}R  {'PASS' if cr.max_drawdown_passed else 'FAIL'} (limit: {constraints.max_drawdown_r}R)")
    print(f"  Annual R:   {'PASS' if cr.annual_r_passed else 'FAIL'} (target: {constraints.min_annual_r}R/yr)")
    for yr, r in sorted(cr.annual_r_values.items()):
        flag = " *" if r < constraints.min_annual_r else ""
        print(f"    {yr}: {r:>8.1f}R{flag}")
    print(f"  Monthly:    worst={cr.worst_month_r:.1f}R  {'PASS' if cr.monthly_loss_passed else 'FAIL'} (limit: {constraints.max_monthly_loss_r}R)")
    print(f"  Expectancy: {cr.expectancy:.4f}R  {'PASS' if cr.expectancy_passed else 'FAIL'}")
    print(f"  Stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
          f"avg win {cr.avg_win_r:.3f}R, avg loss {cr.avg_loss_r:.3f}R, total {cr.total_r:.1f}R")
    worst_months = sorted(cr.monthly_r_values.items(), key=lambda x: x[1])[:5]
    print("  Worst 5 months:")
    for m_key, r in worst_months:
        print(f"    {m_key}: {r:>8.1f}R")
    print(f"  --> Phase 3: {'PASS' if cr.passed else 'FAIL'}")
    print("=" * 70)

    # ================================================================
    # PHASE 4: Hold-out OOS (2025+)
    # ================================================================
    holdout_trades = run_backtest(df, config, start_date="2025-01-01", df_1m=df_1m)
    holdout_trades = no_thursday_gate(holdout_trades)
    hm = compute_metrics(holdout_trades)

    print()
    print("=" * 70)
    print("PHASE 4: HOLD-OUT OOS (2025-01-01 to present)")
    print("=" * 70)
    print(f"  Trades:     {hm['total_trades']}")
    print(f"  Win rate:   {hm['win_rate']:.1%}")
    print(f"  Net R:      {hm['total_r']:.1f}R")
    print(f"  Sharpe:     {hm['sharpe_ratio']:.3f}")
    print(f"  PF:         {hm['profit_factor']:.2f}")
    print(f"  Max DD:     {hm['max_drawdown_r']:.1f}R")
    for yr, r in sorted(hm.get("r_by_year", {}).items()):
        print(f"    {yr}: {r:>8.1f}R")

    p4_1 = hm["sharpe_ratio"] > 0.5
    p4_2 = hm["profit_factor"] > 1.0
    p4_3 = hm["total_r"] > 0
    p4_pass = p4_1 and p4_2 and p4_3
    print("  PASS CRITERIA:")
    print(f"    Sharpe > 0.5:  {'PASS' if p4_1 else 'FAIL'} ({hm['sharpe_ratio']:.3f})")
    print(f"    PF > 1.0:      {'PASS' if p4_2 else 'FAIL'} ({hm['profit_factor']:.2f})")
    print(f"    Total R > 0:   {'PASS' if p4_3 else 'FAIL'} ({hm['total_r']:.1f}R)")
    print(f"  --> Phase 4: {'PASS' if p4_pass else 'FAIL'}")
    print("=" * 70)

    # ================================================================
    # PHASE 5: Monte Carlo survival
    # ================================================================
    filled_oos = [t for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_config  = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    mc_result  = run_monte_carlo(wf_result.combined_oos_trades, mc_config, ruin_threshold=-10.0)

    trade_dates = [t.date for t in filled_oos]
    mc_surv = evaluate_constraints_mc(mc_result, constraints, trade_dates=trade_dates)

    print()
    print("=" * 70)
    print("PHASE 5: MONTE CARLO SURVIVAL (2,000 sims, OOS trades)")
    print("=" * 70)
    print(f"  Sims: {mc_result.n_simulations}, Trades/sim: {mc_result.n_trades}")
    print(f"  Actual: {mc_result.actual_final_pnl:.1f}R final, {mc_result.actual_max_drawdown:.1f}R DD")
    print(f"  Final PnL  p5/p50/p95: "
          f"{mc_result.final_pnl_percentiles['p5']:.1f} / "
          f"{mc_result.final_pnl_percentiles['p50']:.1f} / "
          f"{mc_result.final_pnl_percentiles['p95']:.1f}")
    print(f"  Max DD     p5/p50/p95: "
          f"{mc_result.max_dd_percentiles['p5']:.1f} / "
          f"{mc_result.max_dd_percentiles['p50']:.1f} / "
          f"{mc_result.max_dd_percentiles['p95']:.1f}")
    print(f"  Ruin probability (>{abs(mc_result.ruin_threshold)}R DD): {mc_result.ruin_probability:.1%}")
    print()
    print(f"  DD survival rate (<=10R):  {mc_surv['survival_rate']:.1%}")
    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate:    {mc_surv['monthly_loss_pass_rate']:.1%}")
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate:        {mc_surv['annual_r_pass_rate']:.1%}")

    p5_1 = mc_surv["survival_rate"] >= 0.70
    p5_2 = mc_surv["dd_percentiles"]["p95"] <= constraints.max_drawdown_r * 1.2
    p5_pass = p5_1 and p5_2
    print("  PASS CRITERIA:")
    print(f"    Survival >= 70%:  {'PASS' if p5_1 else 'FAIL'} ({mc_surv['survival_rate']:.1%})")
    print(f"    p95 DD <= 12R:    {'PASS' if p5_2 else 'FAIL'} ({mc_surv['dd_percentiles']['p95']:.1f}R)")
    print(f"  --> Phase 5: {'PASS' if p5_pass else 'FAIL'}")
    print("=" * 70)

    # ================================================================
    # FINAL SUMMARY
    # ================================================================
    print()
    print("=" * 70)
    print("PIPELINE SUMMARY — NQ Asia Wide Prop")
    print("Config: stop=6.5%, gap=1.25%, maxgap=5.0%, rr=1.5, tp1=0.25, ATR 14")
    print("=" * 70)
    phases = [
        ("Phase 1 (Structural)",   p1_pass,  f"{m1['total_trades']} trades, {m1['win_rate']:.1%} WR, PF {m1['profit_factor']:.2f}"),
        ("Phase 2 (Walk-Forward)", p2_pass,  f"WF eff {wf_result.walk_forward_efficiency:.2f}, stab {stability.overall_score:.2f}"),
        ("Phase 3 (Prop Filter)",  cr.passed, f"DD {cr.max_drawdown_r:.1f}R, worst mo {cr.worst_month_r:.1f}R"),
        ("Phase 4 (Hold-Out)",     p4_pass,  f"Sharpe {hm['sharpe_ratio']:.2f}, PF {hm['profit_factor']:.2f}, {hm['total_r']:.1f}R"),
        ("Phase 5 (MC Survival)",  p5_pass,  f"{mc_surv['survival_rate']:.0%} survival at 10R DD"),
    ]
    for name, passed, detail in phases:
        print(f"  {name:25s} {'PASS' if passed else 'FAIL'} — {detail}")

    all_pass = all(p for _, p, _ in phases)
    if all_pass:
        verdict = "GO"
    elif not p5_pass and mc_surv["survival_rate"] >= 0.50:
        verdict = "CONDITIONAL"
    elif not cr.passed and p2_pass and p4_pass and p5_pass:
        verdict = "CONDITIONAL (annual R target not met)"
    else:
        verdict = "NO-GO"

    print(f"\n  --> VERDICT: {verdict}")
    print()
    print("  v2 CONDITIONAL baseline (for comparison):")
    print("    Full-history: 1,757 trades, 78.5% WR, 113.4R, Sharpe 1.745, DD -9.3R")
    print("    WF OOS: 875 trades, 45.4R, Sharpe 1.607, DD -7.6R")
    print("    Phase 3 FAIL (annual R < 24R), Phase 5 CONDITIONAL (74.2% survival)")
    print("=" * 70)
    print(f"\nTotal runtime: {time.time()-t_start:.0f}s ({(time.time()-t_start)/60:.1f}m)")


if __name__ == "__main__":
    main()
