#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 4: Medium-vol regime avoidance gate.

Applies the proven medium-vol avoidance gate (skip bull_medium_vol + sideways_medium_vol)
to both candidates from Step 1-3. Per REGIME.md, this gate:
  - Survived 28-fold walk-forward (+13-14R improvement)
  - Holdout confirmed (flipped FVGLimit from -5.8R to +3.0R)
  - Structural: medium-vol chop produces false LSI sweeps without sharp dislocations

Tests:
  1. Ungated vs gated comparison on pre-holdout (structural screen)
  2. Gated walk-forward with RR/TP1 FROZEN at 2.0/0.5 (sweep only gap + atr)
  3. Local stability check on gated candidates
  4. Monte Carlo on gated WF OOS trades

Candidates:
  A: fvg_limit (RR=2.0, TP1=0.5, ATR=10)
  B: fvg_limit + 1stFVG (RR=2.0, TP1=0.5, ATR=14)

Uses 1s magnifier. Hold-out frozen at 2025-04-01.
"""

import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
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

# ── Config ────────────────────────────────────────────────────────────────
WF_START = "2016-01-01"
HOLDOUT_START = "2025-04-01"
PRE_HOLDOUT_END = "2025-03-31"
N_WORKERS = 4
MC_SURVIVAL_DD = 15.0
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

NY_SESSION = SessionConfig(
    name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
    flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
)

CANDIDATE_A = StrategyConfig(
    sessions=(NY_SESSION,), instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=2.0, tp1_ratio=0.5, atr_length=10,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
    name="NQ NY LSI A fvg_limit RR2 TP0.5",
)

CANDIDATE_B = dataclasses.replace(
    CANDIDATE_A, lsi_first_fvg_only=True, atr_length=14,
    name="NQ NY LSI B 1stFVG ATR14 RR2 TP0.5",
)

# WF param ranges — RR and TP1 are FROZEN, only sweep gap and atr
WF_RANGES_A = {
    "ny_min_gap_atr_pct": [3.75, 5.0, 7.5],
    "atr_length": [10, 14],
}
WF_RANGES_B = {
    "ny_min_gap_atr_pct": [3.75, 5.0, 7.5],
    "atr_length": [10, 14, 20],
}

CANDIDATES = {
    "A": (CANDIDATE_A, WF_RANGES_A),
    "B": (CANDIDATE_B, WF_RANGES_B),
}


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


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS
        ]
    return gate


def wf_progress(fold_idx, total, status):
    print(f"    [Fold {fold_idx + 1}/{total}] {status}", flush=True)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    t_global = time.time()

    # Load data
    section("LOADING DATA")
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)

    # Build regime calendar
    print("  Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)
    print(f"  Regime calendar: {len(regime_cal)} days", flush=True)

    df_pre = df_5m.loc[:PRE_HOLDOUT_END]
    df_pre_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
    df_pre_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

    for cname, (candidate, wf_ranges) in CANDIDATES.items():

        # ── Part 1: Ungated vs Gated Structural Screen ────────────────
        section(f"[{cname}] PART 1: UNGATED vs GATED (pre-holdout)")

        t0 = time.time()
        trades = run_backtest(df_pre, candidate, start_date=WF_START,
                              df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
        gated_trades = gate_fn(trades)

        m_ungated = compute_metrics(trades)
        m_gated = compute_metrics(gated_trades)

        filled_ug = _filled_trades(trades)
        filled_g = _filled_trades(gated_trades)
        removed = len(filled_ug) - len(filled_g)
        pct_removed = 100 * removed / len(filled_ug) if filled_ug else 0

        print(f"  Completed in {time.time() - t0:.1f}s", flush=True)
        print(f"  Trades removed: {removed} ({pct_removed:.1f}%)", flush=True)

        print_metrics(m_ungated, "UNGATED")
        print_metrics(m_gated, "GATED (skip medium-vol)")

        calmar_delta = m_gated["calmar_ratio"] - m_ungated["calmar_ratio"]
        sharpe_delta = m_gated["sharpe_ratio"] - m_ungated["sharpe_ratio"]
        dd_delta = m_gated["max_drawdown_r"] - m_ungated["max_drawdown_r"]
        neg_yr_ug = sum(1 for v in m_ungated.get("r_by_year", {}).values() if v < 0)
        neg_yr_g = sum(1 for v in m_gated.get("r_by_year", {}).values() if v < 0)

        print(f"\n  DELTA: Calmar {calmar_delta:+.2f}  Sharpe {sharpe_delta:+.3f}  DD {dd_delta:+.1f}R"
              f"  NegYr {neg_yr_ug}→{neg_yr_g}", flush=True)

        # ── Part 2: Gated Walk-Forward (RR/TP1 frozen) ───────────────
        section(f"[{cname}] PART 2: GATED WALK-FORWARD (RR=2.0 TP1=0.5 frozen)")

        grid_size = 1
        for v in wf_ranges.values():
            grid_size *= len(v)
        print(f"  Config: 36m IS / 12m OOS / 12m step", flush=True)
        print(f"  Grid: {grid_size} combos per fold (gap × atr only)", flush=True)
        print(f"  RR=2.0 and TP1=0.5 FROZEN", flush=True)
        print(f"  Gate: medium-vol avoidance applied in IS and OOS", flush=True)

        df_wf = df_5m.loc[:PRE_HOLDOUT_END]
        df_wf_1m = df_1m.loc[:PRE_HOLDOUT_END] if df_1m is not None else None
        df_wf_1s = df_1s.loc[:PRE_HOLDOUT_END] if df_1s is not None else None

        t0 = time.time()
        wf_result = run_walkforward(
            df_wf, candidate, wf_ranges,
            is_months=36, oos_months=12, step_months=12,
            anchored=False, objective="sharpe",
            n_workers=N_WORKERS, start_date=WF_START,
            progress_fn=wf_progress,
            df_1m=df_wf_1m, df_1s=df_wf_1s,
            gate_fn=gate_fn,
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
        print_metrics(oos_m, "Combined OOS metrics (gated)")

        wfe = wf_result.walk_forward_efficiency
        stability = analyze_parameter_stability(wf_result, param_ranges=wf_ranges)

        print(f"\n  WF Efficiency: {wfe:.3f} (threshold >=0.30)", flush=True)
        print(f"  Stability: {stability.overall_score:.3f} ({stability.interpretation})", flush=True)
        for p in stability.params:
            print(f"    {p.name:<24} mode={p.mode:<6} freq={p.mode_frequency}/{stability.n_folds}", flush=True)

        # OOS neg years
        oos_rby = oos_m.get("r_by_year", {})
        oos_neg = sum(1 for v in oos_rby.values() if v < 0)
        print(f"  OOS neg years: {oos_neg}", flush=True)

        # ── Part 3: Local Stability (gated) ───────────────────────────
        section(f"[{cname}] PART 3: LOCAL STABILITY (gated)")

        local_dims = {
            "ny_min_gap_atr_pct": [max(2.0, candidate.sessions[0].min_gap_atr_pct - 1.25),
                                   candidate.sessions[0].min_gap_atr_pct,
                                   candidate.sessions[0].min_gap_atr_pct + 1.25],
            "atr_length": [max(5, candidate.atr_length - 4), candidate.atr_length, candidate.atr_length + 4],
            "lsi_n_left": [max(3, candidate.lsi_n_left - 3), candidate.lsi_n_left, candidate.lsi_n_left + 3],
            "lsi_n_right": [max(30, candidate.lsi_n_right - 15), candidate.lsi_n_right, candidate.lsi_n_right + 15],
        }

        anchor_calmar = m_gated["calmar_ratio"]
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
                    print(f"    {v:<10} SKIPPED", flush=True)
                    continue
                tr = run_backtest(df_pre, cfg, start_date=WF_START,
                                  df_1m=df_pre_1m, df_1s=df_pre_1s, _maps=maps)
                tr_gated = gate_fn(tr)
                lm = compute_metrics(tr_gated)
                delta = lm["calmar_ratio"] - anchor_calmar
                neg = sum(1 for rv in lm.get("r_by_year", {}).values() if rv < 0)
                is_anchor = (dim == "ny_min_gap_atr_pct" and v == candidate.sessions[0].min_gap_atr_pct) or \
                            (dim != "ny_min_gap_atr_pct" and v == getattr(candidate, dim, None))
                marker = " ◄ anchor" if is_anchor else ""
                collapse = " ✗ COLLAPSE" if delta < -5.0 else ""
                print(f"    {v:<10} {lm['total_trades']}tr  Calm {lm['calmar_ratio']:>7.2f} ({delta:>+.2f})"
                      f"  NegYr {neg}{marker}{collapse}", flush=True)
                if collapse:
                    local_ok = False

        plateau = "PLATEAU" if local_ok else "SPIKE"
        print(f"\n  Plateau judgment: {plateau}", flush=True)

        # ── Part 4: Monte Carlo on gated WF OOS ──────────────────────
        section(f"[{cname}] PART 4: MONTE CARLO (gated WF OOS)")

        mc_config = MonteCarloConfig(n_simulations=2000, method="block_bootstrap", seed=42)
        mc_result = run_monte_carlo(wf_result.combined_oos_trades, mc_config,
                                    ruin_threshold=-MC_SURVIVAL_DD)

        trade_dates = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
        mc_constraints = PropFirmConstraints(max_drawdown_r=MC_SURVIVAL_DD, min_annual_r=12.0, max_monthly_loss_r=5.0)
        mc_surv = evaluate_constraints_mc(mc_result, mc_constraints, trade_dates=trade_dates)

        survival_ok = mc_surv["survival_rate"] >= 0.70
        ruin_ok = mc_result.ruin_probability < 0.10  # relaxed from 5% for gated lower-volume

        print(f"  DD percentiles: {mc_surv['dd_percentiles']}", flush=True)
        print(f"  Sharpe percentiles: {mc_result.sharpe_percentiles}", flush=True)
        print(f"  Survival at {MC_SURVIVAL_DD}R: {mc_surv['survival_rate']:.1%}", flush=True)
        print(f"  Ruin probability: {mc_result.ruin_probability:.1%}", flush=True)

        # ── Summary ───────────────────────────────────────────────────
        section(f"[{cname}] SUMMARY")
        print(f"  Ungated: Calmar {m_ungated['calmar_ratio']:.2f}, DD {m_ungated['max_drawdown_r']:.1f}R, NegYr {neg_yr_ug}", flush=True)
        print(f"  Gated:   Calmar {m_gated['calmar_ratio']:.2f}, DD {m_gated['max_drawdown_r']:.1f}R, NegYr {neg_yr_g}", flush=True)
        print(f"  WF OOS:  Calmar {oos_m['calmar_ratio']:.2f}, Sharpe {oos_m['sharpe_ratio']:.2f}, WFE {wfe:.3f}", flush=True)
        print(f"  Plateau: {plateau}", flush=True)
        print(f"  MC surv: {mc_surv['survival_rate']:.1%}, ruin {mc_result.ruin_probability:.1%}", flush=True)

    print(f"\nTotal time: {time.time() - t_global:.0f}s", flush=True)


if __name__ == "__main__":
    main()
