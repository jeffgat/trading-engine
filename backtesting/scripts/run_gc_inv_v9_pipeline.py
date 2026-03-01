#!/usr/bin/env python3
"""Robust pipeline: GC NY Inversion Longs v9 (v8 + 10% qualifying sweep).

Validates through 5 phases using the qualifying-move engine:
  Phase 1: Structural validation (full history)
  Phase 2: Walk-forward + parameter stability
  Phase 3: Prop firm constraint filter
  Phase 4: Hold-out OOS test
  Phase 5: Monte Carlo survival simulation
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.optimize.walkforward_qm import run_walkforward_qm
from orb_backtest.optimize.walkforward import recency_analysis
from orb_backtest.optimize.prop_constraints import (
    evaluate_constraints,
    PropFirmConstraints,
)
from orb_backtest.optimize.stability import analyze_parameter_stability

# ── v9 Config (v8 + 10% qualifying sweep) ────────────────────────────────────

GC = get_instrument("GC")

GC_NY_INVERSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",
    entry_start="09:35",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=1.0,
    qualifying_move_atr_pct=10.0,  # NEW: require 10% ATR sweep depth
)

BASE_CONFIG = StrategyConfig(
    rr=3.5,
    tp1_ratio=0.2,
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_INVERSION,),
    instrument=GC,
    strategy="inversion",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

# ── Data splits ──────────────────────────────────────────────────────────────

WF_START = "2016-01-01"
WF_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-02-15"

# ── Pipeline thresholds ──────────────────────────────────────────────────────

MIN_TRADES = 100
MIN_WIN_RATE = 0.35
MIN_PF = 1.0
MAX_CONSEC_LOSSES = 15

MIN_WF_EFFICIENCY = 0.5
MIN_STABILITY = 0.4
MIN_FOLDS = 4

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=10.0,
    min_annual_r=-999.0,
    max_monthly_loss_r=5.0,
)

HOLDOUT_MIN_SHARPE = 0.5
HOLDOUT_MIN_PF = 1.0
HOLDOUT_MIN_TRADES = 15

MC_SIMS = 2000
MC_MIN_SURVIVAL = 0.70

PARAM_RANGES = {
    "rr": [3.0, 3.5, 4.0],
    "tp1_ratio": [0.15, 0.2, 0.3],
    "ny_stop_atr_pct": [6.0, 9.0, 12.0],
    "ny_min_gap_atr_pct": [0.75, 1.0, 1.25],
}

# ── Utilities ────────────────────────────────────────────────────────────────

def banner(phase, title):
    print()
    print("=" * 70)
    print(f"  PHASE {phase}: {title}")
    print("=" * 70)


def pf(passed):
    return "PASS" if passed else "** FAIL **"


# ── Phase 1 ──────────────────────────────────────────────────────────────────

def phase1(df, df_1m):
    banner(1, "STRUCTURAL VALIDATION")
    print(f"  Config: GC NY Inversion Longs v9 (v8 + 10% QM)")
    print(f"  Range:  {WF_START} to {HOLDOUT_END}")
    print()

    t0 = time.time()
    trades = run_backtest_qm(df, BASE_CONFIG, start_date=WF_START, df_1m=df_1m)
    print(f"  Completed in {time.time() - t0:.1f}s")

    m = compute_metrics(trades)
    print(f"  Signals: {m['total_signals']} | Filled: {m['total_trades']} | No-fill: {m['no_fills']}")
    print()

    checks = [
        ("Total trades", m["total_trades"], f">= {MIN_TRADES}", m["total_trades"] >= MIN_TRADES),
        ("Win rate", f"{m['win_rate']:.1%}", f">= {MIN_WIN_RATE:.0%}", m["win_rate"] >= MIN_WIN_RATE),
        ("Profit factor", f"{m['profit_factor']:.2f}", f">= {MIN_PF:.1f}", m["profit_factor"] >= MIN_PF),
        ("Max consec losses", m["max_consecutive_losses"], f"<= {MAX_CONSEC_LOSSES}", m["max_consecutive_losses"] <= MAX_CONSEC_LOSSES),
    ]

    all_pass = True
    print(f"  {'Metric':<25s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*57}")
    for label, val, thresh, passed in checks:
        print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {pf(passed):>10s}")
        if not passed:
            all_pass = False

    print()
    print(f"  Net R:    {m['total_r']:.1f}R")
    print(f"  Sharpe:   {m['sharpe_ratio']:.3f}")
    print(f"  Calmar:   {m['calmar_ratio']:.2f}")
    print(f"  Max DD:   {m['max_drawdown_r']:.1f}R")
    print(f"  Avg R:    {m['avg_r']:.3f}")
    print()

    r_by_year = m.get("r_by_year", {})
    if r_by_year:
        print(f"  R by year:")
        for year, r in sorted(r_by_year.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {year}: {r:>8.1f}R{flag}")
    print()

    print(f"  Phase 1 result: {'PASS' if all_pass else 'FAIL'}")
    return all_pass, m, trades


# ── Phase 2 ──────────────────────────────────────────────────────────────────

def phase2(df, df_1m):
    banner(2, "WALK-FORWARD + PARAMETER STABILITY")
    print(f"  IS: 36m | OOS: 12m | Step: 12m | Objective: sharpe")
    print(f"  Range: {WF_START} to {WF_END}")
    combos = 1
    for v in PARAM_RANGES.values():
        combos *= len(v)
    print(f"  Sweep: {combos} combos/fold")
    for k, v in PARAM_RANGES.items():
        print(f"    {k}: {v}")
    print()

    t0 = time.time()

    def progress(fold_idx, total, status):
        elapsed = time.time() - t0
        if status == "done":
            print(f"\r  Fold {fold_idx+1}/{total}: done [{elapsed:.0f}s]                    ")
        else:
            print(f"\r  Fold {fold_idx+1}/{total}: {status} ({combos} combos)              ", end="", flush=True)

    wf_df = df.loc[:WF_END]
    wf_1m = df_1m.loc[:WF_END] if df_1m is not None else None

    wf_result = run_walkforward_qm(
        wf_df,
        BASE_CONFIG,
        PARAM_RANGES,
        is_months=36,
        oos_months=12,
        step_months=12,
        anchored=False,
        objective="sharpe",
        n_workers=8,
        start_date=WF_START,
        progress_fn=progress,
        df_1m=wf_1m,
        max_dd_r=-10.0,
    )

    print(f"\n  Completed in {time.time() - t0:.1f}s")
    print()

    param_cols = list(PARAM_RANGES.keys())
    param_header = " | ".join(f"{p:>14s}" for p in param_cols)
    print(f"  {'Fold':>4s} | {'IS Period':<23s} | {'OOS Period':<23s} | "
          f"{'IS Sharpe':>10s} | {'OOS Sharpe':>11s} | {'OOS Trades':>10s} | {param_header}")
    print("  " + "-" * (85 + 17 * len(param_cols)))

    for fold in wf_result.folds:
        is_p = f"{fold.is_start[:7]} → {fold.is_end[:7]}"
        oos_p = f"{fold.oos_start[:7]} → {fold.oos_end[:7]}"
        pvals = " | ".join(f"{fold.best_params.get(p, 0):>14.2f}" for p in param_cols)
        print(f"  {fold.fold_index+1:>4d} | {is_p:<23s} | {oos_p:<23s} | "
              f"{fold.is_objective_value:>10.3f} | {fold.oos_objective_value:>11.3f} | "
              f"{fold.oos_metrics['total_trades']:>10d} | {pvals}")

    print()

    m = wf_result.combined_oos_metrics
    n_folds = len(wf_result.folds)
    print(f"  Combined OOS ({n_folds} folds):")
    print(f"    Trades:  {m['total_trades']}")
    print(f"    Win rate: {m['win_rate']:.1%}")
    print(f"    Net R:   {m['total_r']:.1f}R")
    print(f"    Sharpe:  {m['sharpe_ratio']:.3f}")
    print(f"    PF:      {m['profit_factor']:.2f}")
    print(f"    Max DD:  {m['max_drawdown_r']:.1f}R")
    print(f"    WF Efficiency: {wf_result.walk_forward_efficiency:.2f}")
    print()

    stability = analyze_parameter_stability(wf_result, PARAM_RANGES)
    print(f"  Parameter Stability:")
    print(f"    Overall score: {stability.overall_score:.2f} ({stability.interpretation})")
    for ps in stability.params:
        print(f"    {ps.name}: mode={ps.mode}, score={ps.stability_score:.2f}")
    print()

    if n_folds >= 4:
        ra = recency_analysis(wf_result)
        if ra["historical_metrics"] and ra["historical_metrics"]["total_trades"] > 0:
            print(f"  Recency Analysis:")
            hm = ra["historical_metrics"]
            rm = ra["recent_metrics"]
            print(f"    {'Metric':<20s} {'Historical':>12s} {'Recent':>12s}")
            print(f"    {'-'*44}")
            print(f"    {'Sharpe':<20s} {hm['sharpe_ratio']:>12.3f} {rm['sharpe_ratio']:>12.3f}")
            print(f"    {'Win Rate':<20s} {hm['win_rate']:>11.1%} {rm['win_rate']:>11.1%}")
            print(f"    {'Max DD (R)':<20s} {hm['max_drawdown_r']:>12.1f} {rm['max_drawdown_r']:>12.1f}")
            if ra["degradation_flag"]:
                print(f"    ** DEGRADATION WARNING **")
            print()

    checks = [
        ("Folds", n_folds, f">= {MIN_FOLDS}", n_folds >= MIN_FOLDS),
        ("WF Efficiency", f"{wf_result.walk_forward_efficiency:.2f}", f">= {MIN_WF_EFFICIENCY:.1f}", wf_result.walk_forward_efficiency >= MIN_WF_EFFICIENCY),
        ("Stability", f"{stability.overall_score:.2f}", f">= {MIN_STABILITY:.1f}", stability.overall_score >= MIN_STABILITY),
    ]

    all_pass = True
    print(f"  {'Check':<25s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*57}")
    for label, val, thresh, passed in checks:
        print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {pf(passed):>10s}")
        if not passed:
            all_pass = False

    print(f"\n  Phase 2 result: {'PASS' if all_pass else 'FAIL'}")
    return all_pass, wf_result, stability


# ── Phase 3 ──────────────────────────────────────────────────────────────────

def phase3(wf_result):
    banner(3, "PROP FIRM CONSTRAINT FILTER")
    print(f"  Evaluating on combined WF OOS trades ({len(wf_result.combined_oos_trades)} trades)")
    print()

    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)
    avg_annual_r = sum(cr.annual_r_values.values()) / len(cr.annual_r_values) if cr.annual_r_values else 0.0

    print(f"  {'Constraint':<30s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*62}")
    print(f"  {'Max Drawdown (R)':<30s} {cr.max_drawdown_r:>10.1f} {'<= 10.0':>12s} {pf(cr.max_drawdown_passed):>10s}")
    print(f"  {'Annual R (avg)':<30s} {avg_annual_r:>10.1f} {'>= -999.0':>12s} {pf(cr.annual_r_passed):>10s}")
    print(f"  {'Max Monthly Loss (R)':<30s} {cr.worst_month_r:>10.1f} {'>= -5.0':>12s} {pf(cr.monthly_loss_passed):>10s}")
    print(f"  {'Positive Expectancy':<30s} {cr.expectancy:>10.3f} {'> 0':>12s} {pf(cr.expectancy_passed):>10s}")

    if cr.annual_r_values:
        print()
        print(f"  Annual R breakdown:")
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")
    print()

    print(f"  Phase 3 result: {'PASS' if cr.passed else 'FAIL'}")
    return cr.passed, cr


# ── Phase 4 ──────────────────────────────────────────────────────────────────

def phase4(df, df_1m, stability):
    banner(4, "HOLD-OUT OOS TEST")
    print(f"  Reserved data: {HOLDOUT_START} to {HOLDOUT_END}")
    print()

    mode_overrides = {}
    for ps in stability.params:
        mode_overrides[ps.name] = ps.mode

    holdout_config = with_overrides(BASE_CONFIG, **mode_overrides)

    print(f"  Mode params applied:")
    for ps in stability.params:
        print(f"    {ps.name} = {ps.mode}")
    print()

    holdout_df = df.loc["2024-11-01":]
    holdout_1m = df_1m.loc["2024-11-01":] if df_1m is not None else None

    t0 = time.time()
    trades = run_backtest_qm(holdout_df, holdout_config, start_date=HOLDOUT_START, df_1m=holdout_1m)
    print(f"  Completed in {time.time() - t0:.1f}s")

    m = compute_metrics(trades)
    print(f"  Signals: {m['total_signals']} | Filled: {m['total_trades']}")
    print()
    print(f"  Net R:    {m['total_r']:.1f}R")
    print(f"  Sharpe:   {m['sharpe_ratio']:.3f}")
    print(f"  PF:       {m['profit_factor']:.2f}")
    print(f"  Win rate: {m['win_rate']:.1%}")
    print(f"  Max DD:   {m['max_drawdown_r']:.1f}R")
    print(f"  Avg R:    {m['avg_r']:.3f}")
    print()

    checks = [
        ("Trades", m["total_trades"], f">= {HOLDOUT_MIN_TRADES}", m["total_trades"] >= HOLDOUT_MIN_TRADES),
        ("Sharpe", f"{m['sharpe_ratio']:.3f}", f"> {HOLDOUT_MIN_SHARPE}", m["sharpe_ratio"] > HOLDOUT_MIN_SHARPE),
        ("PF", f"{m['profit_factor']:.2f}", f"> {HOLDOUT_MIN_PF}", m["profit_factor"] > HOLDOUT_MIN_PF),
        ("Net R", f"{m['total_r']:.1f}", "> 0", m["total_r"] > 0),
    ]

    all_pass = True
    print(f"  {'Check':<25s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*57}")
    for label, val, thresh, passed in checks:
        print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {pf(passed):>10s}")
        if not passed:
            all_pass = False

    print(f"\n  Phase 4 result: {'PASS' if all_pass else 'FAIL'}")
    return all_pass, m, trades


# ── Phase 5 ──────────────────────────────────────────────────────────────────

def phase5(wf_trades):
    banner(5, "MONTE CARLO SURVIVAL")

    filled = [t for t in wf_trades if t.exit_type != EXIT_NO_FILL]
    r_multiples = np.array([t.r_multiple for t in filled])
    n_trades = len(r_multiples)

    print(f"  Trades: {n_trades} | Sims: {MC_SIMS:,}")
    print(f"  Ruin threshold: -{PROP_CONSTRAINTS.max_drawdown_r}R")
    print()

    if n_trades < 10:
        print(f"  Too few trades for Monte Carlo. SKIP.")
        return False, {}

    t0 = time.time()
    rng = np.random.default_rng(42)

    indices = rng.integers(0, n_trades, size=(MC_SIMS, n_trades))
    paths = r_multiples[indices]
    equity = np.cumsum(paths, axis=1)
    final_pnl = equity[:, -1]

    running_max = np.maximum.accumulate(equity, axis=1)
    drawdowns = equity - running_max
    max_dd = np.min(drawdowns, axis=1)

    ruin_threshold = -PROP_CONSTRAINTS.max_drawdown_r
    survival_rate = float(np.mean(max_dd >= ruin_threshold))

    print(f"  Completed in {time.time() - t0:.1f}s")
    print()

    def pct(arr, p):
        return float(np.percentile(arr, p))

    print(f"  Final PnL (R):")
    print(f"    5th:   {pct(final_pnl, 5):>8.1f}R")
    print(f"    25th:  {pct(final_pnl, 25):>8.1f}R")
    print(f"    50th:  {pct(final_pnl, 50):>8.1f}R (median)")
    print(f"    75th:  {pct(final_pnl, 75):>8.1f}R")
    print(f"    95th:  {pct(final_pnl, 95):>8.1f}R")
    print()

    print(f"  Max Drawdown (R):")
    print(f"    5th:   {pct(max_dd, 5):>8.1f}R (worst)")
    print(f"    25th:  {pct(max_dd, 25):>8.1f}R")
    print(f"    50th:  {pct(max_dd, 50):>8.1f}R (median)")
    print(f"    75th:  {pct(max_dd, 75):>8.1f}R")
    print(f"    95th:  {pct(max_dd, 95):>8.1f}R (best)")
    print()

    if survival_rate >= 0.80:
        band = "STRONG"
    elif survival_rate >= 0.70:
        band = "ACCEPTABLE"
    elif survival_rate >= 0.50:
        band = "CONDITIONAL"
    else:
        band = "NO-GO"

    passed = survival_rate >= MC_MIN_SURVIVAL
    print(f"  Survival rate: {survival_rate:.1%} ({band})")
    print(f"  Threshold:     >= {MC_MIN_SURVIVAL:.0%}")
    print()
    print(f"  Phase 5 result: {'PASS' if passed else 'FAIL'}")

    return passed, {"survival_rate": survival_rate, "band": band,
                    "dd_p5": pct(max_dd, 5), "dd_median": pct(max_dd, 50),
                    "pnl_median": pct(final_pnl, 50)}


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 70)
    print("  ROBUST PIPELINE: GC NY Inversion Longs v9")
    print("  (v8 + 10% qualifying sweep depth)")
    print("=" * 70)
    print()

    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})")
    print(f"  1m: {len(df_1m):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    results = {}

    p1_pass, _, _ = phase1(df, df_1m)
    results["phase1"] = p1_pass
    if not p1_pass:
        _verdict(results)
        return

    p2_pass, wf_result, stability = phase2(df, df_1m)
    results["phase2"] = p2_pass
    if not p2_pass:
        _verdict(results)
        return

    p3_pass, _ = phase3(wf_result)
    results["phase3"] = p3_pass
    if not p3_pass:
        _verdict(results)
        return

    p4_pass, _, _ = phase4(df, df_1m, stability)
    results["phase4"] = p4_pass
    if not p4_pass:
        _verdict(results)
        return

    p5_pass, mc_stats = phase5(wf_result.combined_oos_trades)
    results["phase5"] = p5_pass

    _verdict(results, mc_stats)


def _verdict(results, mc_stats=None):
    print()
    print("=" * 70)
    print("  FINAL VERDICT")
    print("=" * 70)
    print()

    for phase, passed in results.items():
        print(f"  {phase.upper()}: {'PASS' if passed else 'FAIL'}")

    all_pass = all(results.values())
    print()

    if all_pass:
        band = mc_stats.get("band", "?") if mc_stats else "?"
        if band == "STRONG":
            print("  >>> GO — All phases pass. Deploy to prop firm. <<<")
        elif band == "ACCEPTABLE":
            print("  >>> GO — All phases pass. Acceptable survival. <<<")
        else:
            print("  >>> CONDITIONAL — All phases pass but survival is marginal. <<<")
    else:
        failed = [p for p, v in results.items() if not v]
        print(f"  >>> NO-GO — Failed: {', '.join(f.upper() for f in failed)} <<<")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
