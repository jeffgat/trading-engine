#!/usr/bin/env python3
"""Robust pipeline: GC NY Continuation Shorts with magnifier.

Validates the strategy through 5 phases:
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
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.optimize.walkforward import run_walkforward, recency_analysis
from orb_backtest.optimize.prop_constraints import (
    evaluate_constraints,
    evaluate_constraints_mc,
    PropFirmConstraints,
)
from orb_backtest.optimize.stability import analyze_parameter_stability

# ── Config ────────────────────────────────────────────────────────────────────

GC = get_instrument("GC")

GC_NY_CONTINUATION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",       # 5-min ORB
    entry_start="09:35",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=1.0,
)

BASE_CONFIG = StrategyConfig(
    rr=3.0,
    tp1_ratio=0.3,
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_CONTINUATION,),
    instrument=GC,
    strategy="continuation",
    direction_filter="short",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

# ── Data splits ──────────────────────────────────────────────────────────────

WF_START = "2016-01-01"
WF_END = "2024-12-31"       # Walk-forward boundary
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-02-15"  # Reserved data (never seen during WF)

# ── Pipeline thresholds ──────────────────────────────────────────────────────

# Phase 1: Structural
MIN_TRADES = 80
MIN_WIN_RATE = 0.30
MIN_PF = 1.0
MAX_CONSEC_LOSSES = 15

# Phase 2: Walk-forward
MIN_WF_EFFICIENCY = 0.3
MIN_STABILITY = 0.3
MIN_FOLDS = 4

# Phase 3: Prop constraints
PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=10.0,
    min_annual_r=-999.0,     # Disabled: low-frequency shorts-only
    max_monthly_loss_r=5.0,
)

# Phase 4: Hold-out OOS
HOLDOUT_MIN_SHARPE = 0.3
HOLDOUT_MIN_PF = 1.0
HOLDOUT_MIN_TRADES = 10     # ~14 months of holdout, shorts-only

# Phase 5: Monte Carlo
MC_SIMS = 2000
MC_MIN_SURVIVAL = 0.70

# ── Walk-forward sweep ranges ────────────────────────────────────────────────

PARAM_RANGES = {
    "rr": [2.0, 2.5, 3.0, 3.5, 4.0],
    "tp1_ratio": [0.2, 0.3, 0.4, 0.5],
    "ny_stop_atr_pct": [5.0, 7.0, 9.0, 12.0, 15.0],
    "ny_min_gap_atr_pct": [0.5, 0.75, 1.0, 1.5, 2.0],
}

# ── Utilities ────────────────────────────────────────────────────────────────

def banner(phase: int, title: str):
    print()
    print("=" * 70)
    print(f"  PHASE {phase}: {title}")
    print("=" * 70)


def pass_fail(passed: bool) -> str:
    return "PASS" if passed else "** FAIL **"


# ── Phase 1 ──────────────────────────────────────────────────────────────────

def phase1(df, df_1m):
    banner(1, "STRUCTURAL VALIDATION")
    print(f"  Config: GC NY Continuation Shorts rr=3.0/tp1=0.3/atr50 + magnifier")
    print(f"  Range:  {WF_START} to {HOLDOUT_END} (full history)")
    print()

    t0 = time.time()
    trades = run_backtest(df, BASE_CONFIG, start_date=WF_START, df_1m=df_1m)
    elapsed = time.time() - t0

    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    print(f"  Completed in {elapsed:.1f}s")
    print(f"  Signals: {m['total_signals']} | Filled: {m['total_trades']} | No-fill: {m['no_fills']}")
    print()
    print(f"  {'Metric':<25s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*57}")

    checks = [
        ("Total trades", m["total_trades"], f">= {MIN_TRADES}", m["total_trades"] >= MIN_TRADES),
        ("Win rate", f"{m['win_rate']:.1%}", f">= {MIN_WIN_RATE:.0%}", m["win_rate"] >= MIN_WIN_RATE),
        ("Profit factor", f"{m['profit_factor']:.2f}", f">= {MIN_PF:.1f}", m["profit_factor"] >= MIN_PF),
        ("Max consec losses", m["max_consecutive_losses"], f"<= {MAX_CONSEC_LOSSES}", m["max_consecutive_losses"] <= MAX_CONSEC_LOSSES),
    ]

    all_pass = True
    for label, val, thresh, passed in checks:
        print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {pass_fail(passed):>10s}")
        if not passed:
            all_pass = False

    print()
    print(f"  Net R:    {m['total_r']:.1f}R")
    print(f"  Sharpe:   {m['sharpe_ratio']:.3f}")
    print(f"  Calmar:   {m['calmar_ratio']:.2f}")
    print(f"  Max DD:   {m['max_drawdown_r']:.1f}R")
    print(f"  Avg R:    {m['avg_r']:.3f}")
    print()

    # R by year
    r_by_year = m.get("r_by_year", {})
    if r_by_year:
        print(f"  R by year:")
        for year, r in sorted(r_by_year.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {year}: {r:>8.1f}R{flag}")
    print()

    result = "PASS" if all_pass else "FAIL"
    print(f"  Phase 1 result: {result}")
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

    wf_result = run_walkforward(
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

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s")
    print()

    # Per-fold table
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

    # Combined OOS metrics
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

    # Stability analysis
    stability = analyze_parameter_stability(wf_result, PARAM_RANGES)
    print(f"  Parameter Stability:")
    print(f"    Overall score: {stability.overall_score:.2f} ({stability.interpretation})")
    for ps in stability.params:
        print(f"    {ps.name}: mode={ps.mode}, score={ps.stability_score:.2f}")
    print()

    # Recency
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

    # Pass/fail
    checks = [
        ("Folds", n_folds, f">= {MIN_FOLDS}", n_folds >= MIN_FOLDS),
        ("WF Efficiency", f"{wf_result.walk_forward_efficiency:.2f}", f">= {MIN_WF_EFFICIENCY:.1f}", wf_result.walk_forward_efficiency >= MIN_WF_EFFICIENCY),
        ("Stability", f"{stability.overall_score:.2f}", f">= {MIN_STABILITY:.1f}", stability.overall_score >= MIN_STABILITY),
    ]

    all_pass = True
    print(f"  {'Check':<25s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*57}")
    for label, val, thresh, passed in checks:
        print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {pass_fail(passed):>10s}")
        if not passed:
            all_pass = False

    result = "PASS" if all_pass else "FAIL"
    print(f"\n  Phase 2 result: {result}")
    return all_pass, wf_result, stability


# ── Phase 3 ──────────────────────────────────────────────────────────────────

def phase3(wf_result):
    banner(3, "PROP FIRM CONSTRAINT FILTER")
    print(f"  Evaluating on combined WF OOS trades ({len(wf_result.combined_oos_trades)} trades)")
    print(f"  Thresholds: max DD={PROP_CONSTRAINTS.max_drawdown_r}R, "
          f"min annual R={PROP_CONSTRAINTS.min_annual_r}, "
          f"max monthly loss={PROP_CONSTRAINTS.max_monthly_loss_r}R")
    print()

    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)

    avg_annual_r = sum(cr.annual_r_values.values()) / len(cr.annual_r_values) if cr.annual_r_values else 0.0

    print(f"  {'Constraint':<30s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*62}")
    print(f"  {'Max Drawdown (R)':<30s} {cr.max_drawdown_r:>10.1f} {'<= ' + str(PROP_CONSTRAINTS.max_drawdown_r):>12s} {pass_fail(cr.max_drawdown_passed):>10s}")
    print(f"  {'Annual R (avg)':<30s} {avg_annual_r:>10.1f} {'>= ' + str(PROP_CONSTRAINTS.min_annual_r):>12s} {pass_fail(cr.annual_r_passed):>10s}")
    print(f"  {'Max Monthly Loss (R)':<30s} {cr.worst_month_r:>10.1f} {'>= -' + str(PROP_CONSTRAINTS.max_monthly_loss_r):>12s} {pass_fail(cr.monthly_loss_passed):>10s}")
    print(f"  {'Positive Expectancy':<30s} {cr.expectancy:>10.3f} {'> 0':>12s} {pass_fail(cr.expectancy_passed):>10s}")

    if cr.annual_r_values:
        print()
        print(f"  Annual R breakdown:")
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")
    print()

    result = "PASS" if cr.passed else "FAIL"
    print(f"  Phase 3 result: {result}")
    return cr.passed, cr


# ── Phase 4 ──────────────────────────────────────────────────────────────────

def phase4(df, df_1m, stability):
    banner(4, "HOLD-OUT OOS TEST")
    print(f"  Reserved data: {HOLDOUT_START} to {HOLDOUT_END}")
    print(f"  Using mode params from stability analysis")
    print()

    # Build config with mode params from WF stability
    mode_overrides = {}
    for ps in stability.params:
        mode_overrides[ps.name] = ps.mode

    holdout_config = with_overrides(BASE_CONFIG, **mode_overrides)

    print(f"  Mode params applied:")
    for ps in stability.params:
        print(f"    {ps.name} = {ps.mode}")
    print()

    holdout_df = df.loc["2024-11-01":]  # warmup before holdout
    holdout_1m = df_1m.loc["2024-11-01":] if df_1m is not None else None

    t0 = time.time()
    trades = run_backtest(holdout_df, holdout_config, start_date=HOLDOUT_START, df_1m=holdout_1m)
    elapsed = time.time() - t0

    m = compute_metrics(trades)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    print(f"  Completed in {elapsed:.1f}s")
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
        print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {pass_fail(passed):>10s}")
        if not passed:
            all_pass = False

    result = "PASS" if all_pass else "FAIL"
    print(f"\n  Phase 4 result: {result}")
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

    # Bootstrap: resample with replacement
    indices = rng.integers(0, n_trades, size=(MC_SIMS, n_trades))
    paths = r_multiples[indices]

    # Cumulative equity
    equity = np.cumsum(paths, axis=1)
    final_pnl = equity[:, -1]

    # Max drawdown per path
    running_max = np.maximum.accumulate(equity, axis=1)
    drawdowns = equity - running_max
    max_dd = np.min(drawdowns, axis=1)

    # Survival rate
    ruin_threshold = -PROP_CONSTRAINTS.max_drawdown_r
    survival_rate = float(np.mean(max_dd >= ruin_threshold))

    elapsed = time.time() - t0
    print(f"  Completed in {elapsed:.1f}s")
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

    # Survival classification
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

    result = "PASS" if passed else "FAIL"
    print(f"  Phase 5 result: {result}")

    return passed, {
        "survival_rate": survival_rate,
        "band": band,
        "dd_p5": pct(max_dd, 5),
        "dd_median": pct(max_dd, 50),
        "pnl_median": pct(final_pnl, 50),
    }


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 70)
    print("  ROBUST PIPELINE: GC NY Continuation Shorts (magnifier)")
    print("=" * 70)
    print()

    # Load data
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})")
    print(f"  1m: {len(df_1m):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    results = {}

    # Phase 1
    p1_pass, p1_metrics, p1_trades = phase1(df, df_1m)
    results["phase1"] = p1_pass
    if not p1_pass:
        _final_verdict(results)
        return

    # Phase 2
    p2_pass, wf_result, stability = phase2(df, df_1m)
    results["phase2"] = p2_pass
    if not p2_pass:
        _final_verdict(results)
        return

    # Phase 3
    p3_pass, constraints = phase3(wf_result)
    results["phase3"] = p3_pass
    if not p3_pass:
        _final_verdict(results)
        return

    # Phase 4
    p4_pass, p4_metrics, p4_trades = phase4(df, df_1m, stability)
    results["phase4"] = p4_pass
    if not p4_pass:
        _final_verdict(results)
        return

    # Phase 5
    p5_pass, mc_stats = phase5(wf_result.combined_oos_trades)
    results["phase5"] = p5_pass

    _final_verdict(results, mc_stats)


def _final_verdict(results, mc_stats=None):
    print()
    print("=" * 70)
    print("  FINAL VERDICT")
    print("=" * 70)
    print()

    for phase, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {phase.upper()}: {status}")

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
            print("  >>> Consider reduced size or tighter DD limits. <<<")
    else:
        failed = [p for p, v in results.items() if not v]
        print(f"  >>> NO-GO — Failed: {', '.join(f.upper() for f in failed)} <<<")
        print(f"  >>> Do not trade this config on a prop firm account. <<<")

    print()
    print("=" * 70)


if __name__ == "__main__":
    main()
