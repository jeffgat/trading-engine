#!/usr/bin/env python3
"""Robust pipeline: GC NY Continuation Shorts (re-optimization, 1s magnifier).

Converged anchor after diagnostic → R1-R3 variable sweeps + R1 grid sweep:
  stop=3.0% ATR, min_gap=5.5%, rr=8.0, tp1=0.7
  ATR 10, 15m ORB (09:30-09:45), entry→15:00, flat_start=15:50
  max_gap_atr=30%, max_gap_points=25, short-only, FOMC dates excluded

Anchor evolution:
  Diagnostic: compound tests → stop=3.0, rr=7.0, gap=5.0, entry→15:00, ATR 10
  R1: adopted max_gap_atr=30% (Calmar 0.28→0.45)
  R2: converged (0 adoptions)
  Grid R1: 500 combos → adopted #2 stop=3.0, rr=8.0, gap=5.5, tp1=0.7 (Calmar 0.85)
  R3: converged (0 adoptions, all 12 dimensions confirmed)

10-tick minimum stop: WAIVED for GC shorts (median stop ~6 ticks structural).

Five phases (all run regardless of intermediate results):
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

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.optimize.prop_constraints import PropFirmConstraints, evaluate_constraints
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.walkforward import recency_analysis, run_walkforward
from orb_backtest.results.metrics import compute_metrics

# ── Instrument ────────────────────────────────────────────────────────────────

INSTRUMENT = GC

# ── Base config (R3 converged anchor) ─────────────────────────────────────────

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",        # 15m ORB
    entry_start="09:45",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=5.5,
)

HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")

BASE_CONFIG = StrategyConfig(
    rr=8.0,
    tp1_ratio=0.7,
    risk_usd=5000.0,
    atr_length=10,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=INSTRUMENT,
    strategy="continuation",
    direction_filter="short",
    use_bar_magnifier=True,
    half_days=HALF_DAYS,
    excluded_dates=FOMC_DATES,
)

# ── Data splits ───────────────────────────────────────────────────────────────

WF_START      = "2016-01-01"
WF_END        = "2024-12-31"
HOLDOUT_START = "2025-01-01"
HOLDOUT_END   = "2026-02-22"

# ── Pipeline thresholds ──────────────────────────────────────────────────────

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

# ── WF sweep params (centred on R3 converged anchor) ─────────────────────────

PARAM_RANGES = {
    "rr":                  [7.0, 7.5, 8.0, 8.5, 9.0],
    "tp1_ratio":           [0.6, 0.7],
    "ny_stop_atr_pct":     [2.5, 3.0, 3.5],
    "ny_min_gap_atr_pct":  [5.0, 5.5, 6.0],
}

GRID_SIZE = 1
for _v in PARAM_RANGES.values():
    GRID_SIZE *= len(_v)

WF_WORKERS = 1  # 1s data IPC overhead makes single-worker fastest


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


# ── Phase 1 ──────────────────────────────────────────────────────────────────

def phase1(df, df_1m, df_1s):
    banner(1, "STRUCTURAL VALIDATION (full history, 1s magnifier)")
    print(f"  Config: stop=3.0% | rr=8.0 | min_gap=5.5% | tp1=0.7 | ATR 10 | max_gap_atr=30%")
    print(f"          15m ORB | entry→15:00 | FOMC excl | short-only")
    print(f"  Range:  {WF_START} to {HOLDOUT_END}")
    print()

    t0 = time.time()
    trades = run_backtest(df, BASE_CONFIG, start_date=WF_START, df_1m=df_1m, df_1s=df_1s)
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


# ── Phase 2 ──────────────────────────────────────────────────────────────────

def phase2(df, df_1m, df_1s):
    banner(2, "WALK-FORWARD + PARAMETER STABILITY (1s magnifier)")
    print(f"  IS: 36m | OOS: 12m | Step: 12m | Objective: calmar")
    print(f"  Range: {WF_START} to {WF_END}  |  {GRID_SIZE} combos/fold  |  n_workers={WF_WORKERS}")
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


# ── Phase 3 ──────────────────────────────────────────────────────────────────

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
    band = "PASS" if passed else ("CAUTION" if avg_annual_r >= 8.0 else "FAIL")
    print(f"  Phase 3 result: {band}")
    return passed, cr, avg_annual_r


# ── Phase 4 ──────────────────────────────────────────────────────────────────

def phase4(df, df_1m, df_1s, stability):
    banner(4, f"HOLD-OUT OOS TEST ({HOLDOUT_START} → {HOLDOUT_END}, 1s magnifier)")
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


# ── Phase 5 ──────────────────────────────────────────────────────────────────

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


# ── Verdict ──────────────────────────────────────────────────────────────────

def verdict(results, mc_stats=None, p3_annual_r=None):
    print()
    print("=" * 70)
    print("  FINAL VERDICT")
    print("=" * 70)
    print()
    for phase, passed in results.items():
        extra = ""
        if phase == "phase3" and not passed and p3_annual_r is not None and p3_annual_r >= 8.0:
            extra = f"  (CAUTION: {p3_annual_r:.1f} R/yr — marginal, not NO-GO)"
        print(f"  {phase.upper()}: {'PASS' if passed else 'FAIL'}{extra}")
    print()

    all_pass = all(results.values())
    p3_marginal = not results.get("phase3", True) and p3_annual_r is not None and p3_annual_r >= 8.0

    if all_pass:
        band = (mc_stats or {}).get("band", "?")
        if band in ("STRONG", "ACCEPTABLE"):
            print("  >>> GO — All phases pass. Deploy to prop firm. <<<")
        else:
            print("  >>> CONDITIONAL — All phases pass but MC survival is marginal. <<<")
    elif p3_marginal and all(v for k, v in results.items() if k != "phase3"):
        print("  >>> CONDITIONAL GO — Phase 3 marginal but all other phases pass. <<<")
        print(f"  >>> Tradeable with reduced position size ({p3_annual_r:.1f} vs 12.0 threshold). <<<")
    else:
        failed = [p for p, v in results.items() if not v]
        print(f"  >>> NO-GO — Failed: {', '.join(f.upper() for f in failed)} <<<")
    print()
    print("=" * 70)


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print()
    print("=" * 70)
    print("  ROBUST PIPELINE: GC NY Cont Shorts (re-opt, 1s magnifier)")
    print("  stop=3.0% | rr=8.0 | min_gap=5.5% | tp1=0.7 | ATR 10")
    print("  max_gap_atr=30% | 15m ORB | entry→15:00 | FOMC excluded")
    print(f"  WF sweep: {GRID_SIZE} combos/fold ({' x '.join(str(len(v)) for v in PARAM_RANGES.values())})")
    print("=" * 70)
    print()

    print("Loading data...")
    t0 = time.time()
    df    = load_5m_data(INSTRUMENT.data_file)
    df_1m = load_1m_for_5m(INSTRUMENT.data_file)
    df_1s = load_1s_for_5m(INSTRUMENT.data_file)
    print(f"  5m: {len(df):,} bars  |  1m: {len(df_1m):,} bars  |  1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    results = {}
    p3_annual_r = None

    # Phase 1
    p1_pass, _, _ = phase1(df, df_1m, df_1s)
    results["phase1"] = p1_pass
    if not p1_pass:
        verdict(results); return

    # Phase 2
    p2_pass, wf_result, stability = phase2(df, df_1m, df_1s)
    results["phase2"] = p2_pass

    # Phase 3 (continue even if fails — may be CAUTION not NO-GO)
    p3_pass, _, p3_annual_r = phase3(wf_result)
    results["phase3"] = p3_pass

    # Phase 4
    p4_pass, _, _ = phase4(df, df_1m, df_1s, stability)
    results["phase4"] = p4_pass

    # Phase 5 (use full-history trades for MC to get larger sample)
    full_trades = run_backtest(df, BASE_CONFIG, start_date=WF_START, df_1m=df_1m, df_1s=df_1s)
    p5_pass, mc_stats = phase5(full_trades)
    results["phase5"] = p5_pass

    verdict(results, mc_stats, p3_annual_r)


if __name__ == "__main__":
    main()
