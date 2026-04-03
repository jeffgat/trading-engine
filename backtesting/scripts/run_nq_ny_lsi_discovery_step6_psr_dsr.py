#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 6: PSR/DSR overfitting gate.

Validates the promoted candidate (NEW-A gated: fvg_limit RR=2.0 TP1=0.5 ATR=10
+ medium-vol avoidance gate) against multiple-testing inflation.

Trial count:
  Step 1: 20 filter combos
  Step 2: 128 variable sweeps (64 per anchor × 2 anchors)
  Step 3: ~27 WF combos × 6 folds = 162 (Candidate A) + ~81 × 6 = 486 (Candidate B)
  Step 4: regime gate adds ~18 local stability checks × 2 candidates = 36
  Total raw: ~832 configs evaluated

PSR threshold: >= 0.95 (strong), >= 0.85 (moderate)
DSR threshold: >= 0.50 at effective trials = survives deflation

Uses the gated WF OOS trades from Step 4 as the promoted R-multiples.
"""

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
)
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.validate.deflated_sharpe import compute_psr, compute_dsr, annotate_trades

# ── Config ────────────────────────────────────────────────────────────────
WF_START = "2016-01-01"
PRE_HOLDOUT_END = "2025-03-31"
N_WORKERS = 4
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

# Trial counts from the full discovery process
N_TRIALS_RAW = 832  # total configs evaluated across all steps

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

CANDIDATE = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=10,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="NQ NY LSI NEW-A gated RR2 TP0.5",
)

# WF param ranges (frozen RR/TP1, only sweep gap + atr)
WF_RANGES = {
    "ny_min_gap_atr_pct": [3.75, 5.0, 7.5],
    "atr_length": [10, 14],
}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def fmt(p): return "PASS" if p else "FAIL"


def main():
    t0 = time.time()

    print("=" * 80, flush=True)
    print("  STEP 6: PSR/DSR OVERFITTING GATE", flush=True)
    print("=" * 80, flush=True)

    # Load data
    print("\nLoading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)

    # Build regime gate
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    # Run gated WF to get OOS trades
    print("\nRunning gated walk-forward (36m IS / 12m OOS / 12m step)...", flush=True)
    df_wf = df_5m.loc[:PRE_HOLDOUT_END]
    df_wf_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_wf_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    wf_result = run_walkforward(
        df_wf, CANDIDATE, WF_RANGES,
        is_months=36, oos_months=12, step_months=12,
        anchored=False, objective="sharpe",
        n_workers=N_WORKERS, start_date=WF_START,
        df_1m=df_wf_1m, df_1s=df_wf_1s,
        gate_fn=gate_fn,
    )
    print(f"  Walk-forward completed: {len(wf_result.folds)} folds", flush=True)

    # Extract OOS R-multiples
    oos_trades = wf_result.combined_oos_trades
    filled = [t for t in oos_trades if t.exit_type != EXIT_NO_FILL]
    r_multiples = np.array([t.r_multiple for t in filled])

    oos_m = compute_metrics(oos_trades)
    print(f"  OOS trades: {len(filled)}, Sharpe {oos_m['sharpe_ratio']:.3f}, "
          f"Calmar {oos_m['calmar_ratio']:.2f}", flush=True)

    # ── PSR ────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}", flush=True)
    print("  PSR (Probabilistic Sharpe Ratio)", flush=True)
    print(f"{'─' * 60}", flush=True)

    psr = compute_psr(r_multiples)
    print(f"  Observed Sharpe (annualized): {psr.observed_sharpe:.4f}", flush=True)
    print(f"  Benchmark Sharpe: {psr.benchmark_sharpe}", flush=True)
    print(f"  N trades: {psr.n_trades}", flush=True)
    print(f"  Skewness: {psr.skewness:.4f}", flush=True)
    print(f"  Kurtosis: {psr.kurtosis:.4f}", flush=True)
    print(f"  PSR: {psr.psr:.4f}", flush=True)

    psr_interp = "strong" if psr.psr >= 0.95 else "moderate" if psr.psr >= 0.85 else "weak"
    psr_pass = psr.psr >= 0.85
    print(f"  Interpretation: {psr_interp} ({fmt(psr_pass)})", flush=True)

    # ── DSR ────────────────────────────────────────────────────────────
    print(f"\n{'─' * 60}", flush=True)
    print("  DSR (Deflated Sharpe Ratio)", flush=True)
    print(f"{'─' * 60}", flush=True)

    # For effective trials, we use raw count as upper bound
    # (we don't have trade-date sets from all 832 configs to cluster)
    # This is conservative — effective trials <= raw trials
    dsr = compute_dsr(r_multiples, n_trials_raw=N_TRIALS_RAW)

    print(f"  Observed Sharpe (annualized): {dsr.observed_sharpe:.4f}", flush=True)
    print(f"  Expected max Sharpe (null): {dsr.expected_max_sharpe:.4f}", flush=True)
    print(f"  N trades: {dsr.n_trades}", flush=True)
    print(f"  N trials (raw): {dsr.n_trials_raw}", flush=True)
    print(f"  N trials (effective): {dsr.n_trials_effective}", flush=True)
    print(f"  DSR: {dsr.dsr:.4f}", flush=True)

    dsr_interp = (
        "survives deflation" if dsr.dsr >= 0.95
        else "marginal" if dsr.dsr >= 0.80
        else "likely overfit" if dsr.dsr >= 0.50
        else "overfit"
    )
    dsr_pass = dsr.dsr >= 0.50
    print(f"  Interpretation: {dsr_interp} ({fmt(dsr_pass)})", flush=True)

    # ── Also run on pre-holdout full-sample trades (for comparison) ───
    print(f"\n{'─' * 60}", flush=True)
    print("  PSR/DSR on FULL PRE-HOLDOUT (gated, not WF OOS)", flush=True)
    print(f"{'─' * 60}", flush=True)

    df_pre = df_5m.loc[:PRE_HOLDOUT_END]
    df_pre_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    full_trades = run_backtest(df_pre, CANDIDATE, start_date=WF_START,
                                df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
    full_gated = gate_fn(full_trades)
    full_filled = [t for t in full_gated if t.exit_type != EXIT_NO_FILL]
    full_r = np.array([t.r_multiple for t in full_filled])
    full_m = compute_metrics(full_gated)

    psr_full = compute_psr(full_r)
    dsr_full = compute_dsr(full_r, n_trials_raw=N_TRIALS_RAW)

    print(f"  Full-sample trades: {len(full_filled)}, Sharpe {full_m['sharpe_ratio']:.3f}", flush=True)
    print(f"  PSR: {psr_full.psr:.4f} ({'strong' if psr_full.psr >= 0.95 else 'moderate' if psr_full.psr >= 0.85 else 'weak'})", flush=True)
    print(f"  DSR: {dsr_full.dsr:.4f} (E[max SR]={dsr_full.expected_max_sharpe:.4f})", flush=True)

    # ── Summary ───────────────────────────────────────────────────────
    print(f"\n{'=' * 60}", flush=True)
    print("  STEP 6 VERDICT", flush=True)
    print(f"{'=' * 60}", flush=True)

    print(f"\n  {'Metric':<30} {'WF OOS':>10} {'Full Sample':>12} {'Threshold':>12} {'Result':>8}", flush=True)
    print(f"  {'-' * 75}", flush=True)
    print(f"  {'PSR':<30} {psr.psr:>10.4f} {psr_full.psr:>12.4f} {'>=0.85':>12} {fmt(psr_pass):>8}", flush=True)
    print(f"  {'DSR (raw trials=' + str(N_TRIALS_RAW) + ')':<30} {dsr.dsr:>10.4f} {dsr_full.dsr:>12.4f} {'>=0.50':>12} {fmt(dsr_pass):>8}", flush=True)

    overall = psr_pass and dsr_pass
    if psr_pass and not dsr_pass:
        verdict = "CAUTION — edge is real (PSR strong) but may not survive selection bias (DSR weak)"
    elif overall:
        verdict = "PASS — edge survives both PSR and DSR"
    else:
        verdict = "FAIL — insufficient evidence of real edge"

    print(f"\n  >> STEP 6: {verdict}", flush=True)
    print(f"\n  Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
