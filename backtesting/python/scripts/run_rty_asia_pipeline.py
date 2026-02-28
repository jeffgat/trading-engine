#!/usr/bin/env python3
"""Robust pipeline: RTY Asia Continuation Longs (1m magnifier for WF speed).

Grid winner from R1 sweep (320 combos):
  stop=4.0% ATR, min_gap=0.9%, rr=2.5, tp1=0.3
  ATR 14, 15m ORB (20:00-20:15), entry≤23:15, flat_start=06:45
  long-only, excl Tue, 1m bar magnifier

Five phases:
  Phase 1: Structural validation (full history, base config)
  Phase 2: Walk-forward + parameter stability (36m IS / 12m OOS / 12m step)
  Phase 3: Prop firm constraint filter (on combined WF OOS trades)
  Phase 4: Hold-out OOS test (2025-01-01 onward, mode params from WF)
  Phase 5: Monte Carlo survival simulation
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.optimize.prop_constraints import PropFirmConstraints, evaluate_constraints
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import recency_analysis, run_walkforward
from orb_backtest.results.metrics import compute_metrics

# ── Instrument ────────────────────────────────────────────────────────────────

RTY = get_instrument("RTY")

# ── Base config (grid winner) ─────────────────────────────────────────────────

RTY_ASIA = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:15",        # 15m ORB
    entry_start="20:15",
    entry_end="23:15",
    flat_start="06:45",
    flat_end="07:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=0.9,
)

BASE_CONFIG = StrategyConfig(
    rr=2.5,
    tp1_ratio=0.3,
    risk_usd=5000.0,
    atr_length=14,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(RTY_ASIA,),
    instrument=RTY,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    impulse_close_filter=False,
    name="RTY Asia Pipeline",
)

DOW_EXCL = {1}  # excl Tue

# ── Data splits ───────────────────────────────────────────────────────────────

WF_START    = "2016-01-01"
WF_END      = "2024-12-31"
HOLDOUT_START = "2025-01-01"
HOLDOUT_END   = "2026-02-15"

# ── Pipeline thresholds ───────────────────────────────────────────────────────

MIN_TRADES        = 400
MIN_PF            = 1.1
MIN_WF_EFFICIENCY = 0.3
MIN_STABILITY     = 0.4
MIN_FOLDS         = 4
HOLDOUT_MIN_TRADES  = 20
HOLDOUT_MIN_SHARPE  = 0.3
HOLDOUT_MIN_PF      = 1.0
MC_SIMS             = 5000
MC_MIN_SURVIVAL     = 0.60
MC_RUIN_THRESHOLD_R = 25.0

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,     # INFO only
    min_annual_r=12.0,
    max_monthly_loss_r=999.0, # INFO only
    min_positive_expectancy=True,
)

# ── WF sweep params (centred on grid winner) ──────────────────────────────────

PARAM_RANGES = {
    "rr":                    [2.0, 2.5, 3.0],
    "tp1_ratio":             [0.3, 0.4, 0.5],
    "asia_stop_atr_pct":     [3.0, 3.5, 4.0, 4.5, 5.0],
    "asia_min_gap_atr_pct":  [0.5, 0.75, 0.9, 1.0],
}

GRID_SIZE = 1
for _v in PARAM_RANGES.values():
    GRID_SIZE *= len(_v)

WF_WORKERS = 1  # single-worker avoids IPC overhead with magnifier data


# ── DOW gate for walk-forward ─────────────────────────────────────────────────

def dow_gate(trades):
    """Apply DOW exclusion (Tue) to trade list — used as gate_fn in WF."""
    return apply_dow_filter(trades, DOW_EXCL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(phase, title):
    print()
    print("=" * 70)
    print(f"  PHASE {phase}: {title}")
    print("=" * 70)


def pf(passed):
    return "PASS" if passed else "** FAIL **"


def r_by_year_table(m_or_trades, label="R by year", indent="  "):
    if isinstance(m_or_trades, dict):
        rby = m_or_trades.get("r_by_year", {})
    else:
        rby = defaultdict(float)
        for t in m_or_trades:
            if t.exit_type != EXIT_NO_FILL:
                rby[t.date[:4]] += t.r_multiple
    print(f"{indent}{label}:")
    for y in sorted(rby):
        flag = " <--" if rby[y] < 0 else ""
        print(f"{indent}  {y}: {rby[y]:>8.1f}R{flag}")


# ── Phase 1 ───────────────────────────────────────────────────────────────────

def phase1(df, df_1m, df_1s):
    banner(1, "STRUCTURAL VALIDATION (full history)")
    print(f"  Config: stop=4.0% | rr=2.5 | min_gap=0.9% | tp1=0.3 | ATR 14 | 15m ORB | entry→23:15")
    print(f"  Direction: long-only | DOW excl: Tue | Magnifier: 1m")
    print(f"  Range:  {WF_START} to {HOLDOUT_END}")
    print()

    t0 = time.time()
    trades = run_backtest(df, BASE_CONFIG, start_date=WF_START, df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time() - t0:.1f}s")
    print(f"  Signals: {m['total_signals']} | Filled: {m['total_trades']} | No-fill: {m['no_fills']}")
    print()

    checks = [
        ("Total trades",       m["total_trades"],           f">= {MIN_TRADES}",  m["total_trades"] >= MIN_TRADES),
        ("Profit factor",      f"{m['profit_factor']:.2f}", f">= {MIN_PF:.1f}",  m["profit_factor"] >= MIN_PF),
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
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Sharpe:   {m['sharpe_ratio']:.3f}")
    print(f"  Calmar:   {m['calmar_ratio']:.2f}")
    print(f"  Max DD:   {m['max_drawdown_r']:.1f}R  [INFO]")
    print()
    r_by_year_table(m)
    print()
    print(f"  Phase 1 result: {'PASS' if all_pass else 'FAIL'}")
    return all_pass, m, trades


# ── Phase 2 ───────────────────────────────────────────────────────────────────

def phase2(df, df_1m, df_1s):
    banner(2, "WALK-FORWARD + PARAMETER STABILITY")
    print(f"  IS: 36m | OOS: 12m | Step: 12m | Objective: calmar")
    print(f"  Range: {WF_START} to {WF_END}  |  {GRID_SIZE} combos/fold  |  n_workers={WF_WORKERS}")
    print(f"  DOW gate: excl Tue | Magnifier: 1m")
    for k, v in PARAM_RANGES.items():
        print(f"    {k}: {v}")
    print()

    t0 = time.time()

    def progress(fold_idx, total, status):
        elapsed = time.time() - t0
        if status == "done":
            print(f"\r  Fold {fold_idx+1}/{total}: done [{elapsed:.0f}s]                    ")
        else:
            print(f"\r  Fold {fold_idx+1}/{total}: {status} ({GRID_SIZE} combos)              ",
                  end="", flush=True)

    wf_df = df.loc[:WF_END]
    wf_1m = df_1m.loc[:WF_END] if df_1m is not None else None
    wf_1s = df_1s.loc[:WF_END] if df_1s is not None else None

    wf_result = run_walkforward(
        wf_df,
        BASE_CONFIG,
        PARAM_RANGES,
        is_months=36,
        oos_months=12,
        step_months=12,
        anchored=False,
        objective="calmar",
        n_workers=WF_WORKERS,
        start_date=WF_START,
        progress_fn=progress,
        gate_fn=dow_gate,
        df_1m=wf_1m,
        df_1s=wf_1s,
    )

    print(f"\n  Completed in {time.time() - t0:.1f}s")
    print()

    param_cols = list(PARAM_RANGES.keys())
    param_hdr = " | ".join(f"{p:>18s}" for p in param_cols)
    print(f"  {'Fold':>4s} | {'IS Period':<23s} | {'OOS Period':<23s} | "
          f"{'IS Calmar':>9s} | {'OOS Calmar':>10s} | {'OOS Trd':>7s} | {param_hdr}")
    print("  " + "-" * (90 + 20 * len(param_cols)))

    for fold in wf_result.folds:
        is_p  = f"{fold.is_start[:7]} → {fold.is_end[:7]}"
        oos_p = f"{fold.oos_start[:7]} → {fold.oos_end[:7]}"
        pvals = " | ".join(f"{fold.best_params.get(p, 0):>18.2f}" for p in param_cols)
        print(f"  {fold.fold_index+1:>4d} | {is_p:<23s} | {oos_p:<23s} | "
              f"{fold.is_objective_value:>9.3f} | {fold.oos_objective_value:>10.3f} | "
              f"{fold.oos_metrics['total_trades']:>7d} | {pvals}")

    print()
    m = wf_result.combined_oos_metrics
    n_folds = len(wf_result.folds)
    print(f"  Combined OOS ({n_folds} folds):")
    print(f"    Trades:   {m['total_trades']}")
    print(f"    Win Rate: {m['win_rate']:.1%}")
    print(f"    Net R:    {m['total_r']:.1f}R")
    print(f"    Sharpe:   {m['sharpe_ratio']:.3f}")
    print(f"    Calmar:   {m['calmar_ratio']:.2f}")
    print(f"    PF:       {m['profit_factor']:.2f}")
    print(f"    Max DD:   {m['max_drawdown_r']:.1f}R  [INFO]")
    print(f"    WF Eff:   {wf_result.walk_forward_efficiency:.2f}")
    print()
    r_by_year_table(wf_result.combined_oos_trades, indent="    ")
    print()

    stability = analyze_parameter_stability(wf_result, PARAM_RANGES)
    print(f"  Parameter Stability:")
    print(f"    Overall: {stability.overall_score:.2f} ({stability.interpretation})")
    for ps in stability.params:
        print(f"    {ps.name}: mode={ps.mode}  score={ps.stability_score:.2f}")
    print()

    if n_folds >= 4:
        ra = recency_analysis(wf_result)
        hm = ra.get("historical_metrics", {})
        rm = ra.get("recent_metrics", {})
        if hm and hm.get("total_trades", 0) > 0:
            print(f"  Recency Analysis:")
            print(f"    {'Metric':<20s} {'Historical':>12s} {'Recent':>12s}")
            print(f"    {'-'*44}")
            for metric, key in [("Calmar","calmar_ratio"), ("Sharpe","sharpe_ratio"),
                                  ("Win Rate","win_rate"), ("Max DD","max_drawdown_r")]:
                hv = hm.get(key, 0)
                rv = rm.get(key, 0)
                fmt = ".1%" if key == "win_rate" else ".3f" if "ratio" in key else ".1f"
                print(f"    {metric:<20s} {format(hv, fmt):>12s} {format(rv, fmt):>12s}")
            if ra.get("degradation_flag"):
                print(f"    ** DEGRADATION WARNING **")
            print()

    checks = [
        ("Folds",         n_folds,                             f">= {MIN_FOLDS}",         n_folds >= MIN_FOLDS),
        ("WF Efficiency", f"{wf_result.walk_forward_efficiency:.2f}", f">= {MIN_WF_EFFICIENCY:.1f}", wf_result.walk_forward_efficiency >= MIN_WF_EFFICIENCY),
        ("Stability",     f"{stability.overall_score:.2f}",   f">= {MIN_STABILITY:.1f}", stability.overall_score >= MIN_STABILITY),
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


# ── Phase 3 ───────────────────────────────────────────────────────────────────

def phase3(wf_result):
    banner(3, "PROP FIRM CONSTRAINT FILTER")
    oos_filled = [t for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  Evaluating on combined WF OOS trades ({len(oos_filled)} filled)")
    print(f"  DD and monthly loss: INFO only (not gates)")
    print()

    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)
    avg_annual_r = (sum(cr.annual_r_values.values()) / len(cr.annual_r_values)
                    if cr.annual_r_values else 0.0)

    print(f"  {'Constraint':<30s} {'Value':>10s} {'Threshold':>12s} {'Status':>10s}")
    print(f"  {'-'*62}")
    print(f"  {'Max Drawdown (R)':<30s} {cr.max_drawdown_r:>10.1f} {'INFO':>12s} {'INFO':>10s}")
    print(f"  {'Annual R (avg full yrs)':<30s} {avg_annual_r:>10.1f} {'>= 12':>12s} {pf(cr.annual_r_passed):>10s}")
    print(f"  {'Max Monthly Loss (R)':<30s} {cr.worst_month_r:>10.1f} {'INFO':>12s} {'INFO':>10s}")
    print(f"  {'Positive Expectancy':<30s} {cr.expectancy:>10.3f} {'> 0':>12s} {pf(cr.expectancy_passed):>10s}")

    if cr.annual_r_values:
        print()
        print(f"  OOS Annual R:")
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")
    print()

    passed = cr.annual_r_passed and cr.expectancy_passed
    print(f"  Phase 3 result: {'PASS' if passed else 'FAIL'}")
    return passed, cr


# ── Phase 4 ───────────────────────────────────────────────────────────────────

def phase4(df, df_1m, df_1s, stability):
    banner(4, f"HOLD-OUT OOS TEST ({HOLDOUT_START} → {HOLDOUT_END})")
    print(f"  Mode params from WF stability analysis:")

    mode_overrides = {ps.name: ps.mode for ps in stability.params}
    for k, v in mode_overrides.items():
        print(f"    {k} = {v}")
    print()

    holdout_cfg = with_overrides(BASE_CONFIG, **mode_overrides)

    # Load from 2024-11-01 for ATR warmup
    holdout_df = df.loc["2024-11-01":]
    holdout_1m = df_1m.loc["2024-11-01":] if df_1m is not None else None
    holdout_1s = df_1s.loc["2024-11-01":] if df_1s is not None else None

    t0 = time.time()
    trades = run_backtest(holdout_df, holdout_cfg, start_date=HOLDOUT_START,
                          df_1m=holdout_1m, df_1s=holdout_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)
    m = compute_metrics(trades)
    print(f"  Completed in {time.time() - t0:.1f}s")
    print(f"  Signals: {m['total_signals']} | Filled: {m['total_trades']}")
    print()
    print(f"  Net R:    {m['total_r']:.1f}R")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Sharpe:   {m['sharpe_ratio']:.3f}")
    print(f"  PF:       {m['profit_factor']:.2f}")
    print(f"  Max DD:   {m['max_drawdown_r']:.1f}R  [INFO]")
    print(f"  Avg R:    {m['avg_r']:.3f}")
    print()
    r_by_year_table(m)
    print()

    checks = [
        ("Trades",  m["total_trades"],           f">= {HOLDOUT_MIN_TRADES}", m["total_trades"] >= HOLDOUT_MIN_TRADES),
        ("Sharpe",  f"{m['sharpe_ratio']:.3f}",  f"> {HOLDOUT_MIN_SHARPE}",  m["sharpe_ratio"] > HOLDOUT_MIN_SHARPE),
        ("PF",      f"{m['profit_factor']:.2f}", f"> {HOLDOUT_MIN_PF}",      m["profit_factor"] > HOLDOUT_MIN_PF),
        ("Net R",   f"{m['total_r']:.1f}",       "> 0",                      m["total_r"] > 0),
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


# ── Phase 5 ───────────────────────────────────────────────────────────────────

def phase5(wf_trades):
    banner(5, "MONTE CARLO SURVIVAL")
    filled = [t for t in wf_trades if t.exit_type != EXIT_NO_FILL]
    r_arr = np.array([t.r_multiple for t in filled])
    n = len(r_arr)

    print(f"  Trades: {n} | Sims: {MC_SIMS:,} | Ruin: -{MC_RUIN_THRESHOLD_R}R")
    print()

    if n < 10:
        print("  Too few trades. SKIP.")
        return False, {}

    t0 = time.time()
    rng = np.random.default_rng(42)
    paths   = r_arr[rng.integers(0, n, size=(MC_SIMS, n))]
    equity  = np.cumsum(paths, axis=1)
    final   = equity[:, -1]
    max_dd  = np.min(equity - np.maximum.accumulate(equity, axis=1), axis=1)

    survival = float(np.mean(max_dd >= -MC_RUIN_THRESHOLD_R))
    print(f"  Completed in {time.time() - t0:.1f}s")
    print()

    def p(arr, pct): return float(np.percentile(arr, pct))

    print(f"  Final PnL (R):   p5={p(final,5):.1f}  p25={p(final,25):.1f}  "
          f"p50={p(final,50):.1f}  p75={p(final,75):.1f}  p95={p(final,95):.1f}")
    print(f"  Max DD (R):      p5={p(max_dd,5):.1f}  p25={p(max_dd,25):.1f}  "
          f"p50={p(max_dd,50):.1f}  p75={p(max_dd,75):.1f}  p95={p(max_dd,95):.1f}")
    print()

    band = ("STRONG" if survival >= 0.80 else
            "ACCEPTABLE" if survival >= 0.70 else
            "CONDITIONAL" if survival >= 0.50 else "NO-GO")
    passed = survival >= MC_MIN_SURVIVAL

    print(f"  Survival at -{MC_RUIN_THRESHOLD_R}R: {survival:.1%} ({band})")
    print(f"  Threshold: >= {MC_MIN_SURVIVAL:.0%}")
    print(f"\n  Phase 5 result: {'PASS' if passed else 'FAIL'}")

    return passed, {"survival_rate": survival, "band": band,
                    "dd_p5": p(max_dd, 5), "dd_p50": p(max_dd, 50), "pnl_p50": p(final, 50)}


# ── Verdict ───────────────────────────────────────────────────────────────────

def verdict(results, mc_stats=None):
    print()
    print("=" * 70)
    print("  FINAL VERDICT")
    print("=" * 70)
    print()
    for phase, passed in results.items():
        print(f"  {phase.upper()}: {'PASS' if passed else 'FAIL'}")
    print()

    all_pass = all(results.values())
    if all_pass:
        band = (mc_stats or {}).get("band", "?")
        if band in ("STRONG", "ACCEPTABLE"):
            print("  >>> GO — All phases pass. Deploy to prop firm. <<<")
        else:
            print("  >>> CONDITIONAL — All phases pass but survival is marginal. <<<")
    else:
        failed = [p for p, v in results.items() if not v]
        print(f"  >>> NO-GO — Failed: {', '.join(f.upper() for f in failed)} <<<")
    print()
    print("=" * 70)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 70)
    print("  ROBUST PIPELINE: RTY Asia Cont Longs (1m magnifier)")
    print("  stop=4.0% | rr=2.5 | min_gap=0.9% | tp1=0.3 | ATR 14 | 15m ORB")
    print("  entry→23:15 | flat=06:45 | long-only | excl Tue")
    print(f"  WF sweep: {GRID_SIZE} combos/fold (3×3×5×4)")
    print("=" * 70)
    print()

    print("Loading data...")
    t0 = time.time()
    df    = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    df_1s = None  # 1m magnifier for WF speed; 1s too slow for multi-fold grid sweeps
    print(f"  5m: {len(df):,} bars  |  1m: {len(df_1m):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    results = {}

    p1_pass, _, _ = phase1(df, df_1m, df_1s)
    results["phase1"] = p1_pass
    if not p1_pass:
        verdict(results); return

    p2_pass, wf_result, stability = phase2(df, df_1m, df_1s)
    results["phase2"] = p2_pass
    # Continue to phases 3-5 even if WF efficiency is marginal

    p3_pass, _ = phase3(wf_result)
    results["phase3"] = p3_pass
    if not p3_pass:
        verdict(results); return

    p4_pass, _, _ = phase4(df, df_1m, df_1s, stability)
    results["phase4"] = p4_pass
    if not p4_pass:
        verdict(results); return

    p5_pass, mc_stats = phase5(wf_result.combined_oos_trades)
    results["phase5"] = p5_pass

    verdict(results, mc_stats)


if __name__ == "__main__":
    main()
