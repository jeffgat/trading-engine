# Robust Pipeline Script Template

This template generates a complete 5-phase robust pipeline script for prop firm validation.
Placeholders are wrapped in `{CURLY_BRACES}` and get filled in at generation time.

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} {STRATEGY} {DIRECTION} -- 5-Phase Robust Pipeline.

Anchor config: stop={STOP_ATR}%, rr={RR_RATIO}, gap={MIN_GAP_ATR}%, tp1={TP1_RATIO}
Structural: ORB {ORB_START}-{ORB_END}, flat {FLAT_TIME}, ATR {ATR_PERIOD}, {DIRECTION} dir, bar magnifier
Data range: {START_DATE} to present.

Phases:
  1. Structural validation -- full-history metrics check
  2. Walk-forward (36m IS / 12m OOS / 12m step) + param stability
  3. Prop constraint filter on WF OOS trades (DD is INFO only)
  4. Hold-out OOS -- {HOLDOUT_START}+ data never used in optimization
  5. Monte Carlo survival -- 2000 bootstrap sims, ruin at -25R
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints,
    evaluate_constraints,
    evaluate_constraints_mc,
)
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig

# -- Instrument & Dates --------------------------------------------------------

INST = {INSTRUMENT_IMPORT}
START_DATE = "{START_DATE}"
WF_END_SLICE = "{WF_END_SLICE}"  # slice WF data so OOS doesn't bleed into hold-out
HOLDOUT_START = "{HOLDOUT_START}"
N_WORKERS = 8

# -- Session & Strategy Config -------------------------------------------------

SESS = SessionConfig(
    name="{SESSION_UPPER}",
    orb_start="{ORB_START}",
    orb_end="{ORB_END}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_TIME}",
    flat_end="{FLAT_END}",
    stop_atr_pct={STOP_ATR},
    min_gap_atr_pct={MIN_GAP_ATR},
    max_gap_points={MAX_GAP_POINTS},
    max_gap_atr_pct={MAX_GAP_ATR},
)

ANCHOR = StrategyConfig(
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    risk_usd=5000.0,
    atr_length={ATR_PERIOD},
    min_qty=1.0,
    qty_step=1.0,
    sessions=(SESS,),
    instrument=INST,
    strategy="{STRATEGY}",
    direction_filter="{DIRECTION}",
    use_bar_magnifier=True,
    name="{INSTRUMENT} {SESSION_UPPER} Robust Pipeline",
)

# -- Prop Constraints (DD is NOT a hard filter) --------------------------------

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,     # DD is NOT a hard filter (user preference)
    min_annual_r={MIN_ANNUAL_R},
    max_monthly_loss_r={MAX_MONTHLY_LOSS_R},
    min_positive_expectancy=True,
)

MC_RUIN_THRESHOLD = -25.0  # standalone ruin threshold, not tied to prop DD

# -- Walk-Forward Sweep Ranges -------------------------------------------------

PARAM_RANGES = {PARAM_RANGES_DICT}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)

# -- Helpers -------------------------------------------------------------------


def median_stop_ticks(trades):
    """Median stop distance in ticks. Configs with < 10 ticks are rejected."""
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / INST.tick_size for t in filled)


def fmt(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


def section(title: str) -> None:
    print(flush=True)
    print("=" * 70, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 70, flush=True)


def print_metrics(m, label=""):
    if label:
        print(f"\n  {label}", flush=True)
    print(f"  {'Trades':<24s} {m['total_trades']:>10d}", flush=True)
    print(f"  {'Win Rate':<24s} {m['win_rate']:>9.1%}", flush=True)
    print(f"  {'Profit Factor':<24s} {m['profit_factor']:>10.2f}", flush=True)
    print(f"  {'Net R':<24s} {m['total_r']:>9.1f}R", flush=True)
    print(f"  {'Max DD':<24s} {m['max_drawdown_r']:>9.1f}R", flush=True)
    print(f"  {'Calmar':<24s} {m['calmar_ratio']:>10.2f}", flush=True)
    print(f"  {'Sharpe':<24s} {m['sharpe_ratio']:>10.3f}", flush=True)
    rby = m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)


def wf_progress(fold_idx, total, status):
    print(f"  [Fold {fold_idx + 1}/{total}] {status}", flush=True)


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    section("{INSTRUMENT} {SESSION_UPPER} {STRATEGY} {DIRECTION} -- ROBUST PIPELINE")
    print(f"  Anchor: stop={STOP_ATR}% | rr={RR_RATIO} | gap={MIN_GAP_ATR}% | tp1={TP1_RATIO}", flush=True)
    print(f"  Structural: ORB {ORB_START}-{ORB_END} | flat {FLAT_TIME} | ATR {ATR_PERIOD} | {DIRECTION} | magnifier", flush=True)

    # -- Load Data -------------------------------------------------------------
    print("\nLoading data...", flush=True)
    t_load = time.time()
    df = load_5m_data("{DATA_FILE_5M}")
    try:
        df_1m = load_1m_for_5m("{DATA_FILE_5M}")
    except FileNotFoundError:
        print("  WARNING: 1m data not found -- magnifier disabled", flush=True)
        df_1m = None
    df_1s = load_1s_for_5m("{DATA_FILE_5M}")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})", flush=True)
    if df_1m is not None:
        print(f"  1m: {len(df_1m):,} bars", flush=True)
    if df_1s is not None:
        print(f"  1s: {len(df_1s):,} bars", flush=True)
    else:
        print("  1s: NOT FOUND", flush=True)
    print(f"  Loaded in {time.time() - t_load:.1f}s", flush=True)

    t_start = time.time()

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 1: Structural Validation
    # ══════════════════════════════════════════════════════════════════════════
    section("PHASE 1: STRUCTURAL VALIDATION")
    print("  Running full-history backtest on anchor config...", flush=True)

    t0 = time.time()
    p1_trades = run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    p1_m = compute_metrics(p1_trades)
    print_metrics(p1_m, f"Full-history metrics ({time.time() - t0:.1f}s)")

    p1_med_ticks = median_stop_ticks(p1_trades)
    print(f"\n  Median stop: {p1_med_ticks:.1f} ticks", flush=True)

    p1_checks = {
        "Trades >= 100": p1_m["total_trades"] >= 100,
        "PF >= 1.2": p1_m["profit_factor"] >= 1.2,
        "Win rate >= 35%": p1_m["win_rate"] >= 0.35,
        "Calmar >= 0.5": p1_m["calmar_ratio"] >= 0.5,
        "Median stop >= 10 ticks": p1_med_ticks >= 10,
    }

    print(f"\n  Structural checks:", flush=True)
    for name, passed in p1_checks.items():
        print(f"    [{fmt(passed)}] {name}", flush=True)

    p1_passed = all(p1_checks.values())
    print(f"\n  >> PHASE 1: {fmt(p1_passed)}", flush=True)

    if not p1_passed:
        print("  Structural validation failed. Continuing for diagnostics...", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 2: Walk-Forward + Parameter Stability
    # ══════════════════════════════════════════════════════════════════════════
    section("PHASE 2: WALK-FORWARD + PARAMETER STABILITY")
    # NOTE: WF uses 1m magnifier only (not 1s). The 1s maps are too large
    # and serializing them for multiprocessing workers is prohibitively slow.
    # 1m fill precision is sufficient for parameter stability analysis.
    print(f"  Config: 36m IS / 12m OOS / 12m step (rolling)", flush=True)
    print(f"  Grid: {GRID_SIZE} combos per fold x {N_WORKERS} workers", flush=True)
    print(f"  Magnifier: 1m (1s too large for multiprocessing serialization)", flush=True)
    print(f"  Params: {list(PARAM_RANGES.keys())}", flush=True)

    df_wf = df.loc[:WF_END_SLICE]
    df_wf_1m = df_1m.loc[:WF_END_SLICE] if df_1m is not None else None
    if df_wf_1m is None:
        print("  NOTE: Walk-forward running without 1m magnifier", flush=True)

    t0 = time.time()
    wf_result = run_walkforward(
        df_wf,
        ANCHOR,
        param_ranges=PARAM_RANGES,
        is_months=36,
        oos_months=12,
        step_months=12,
        anchored=False,
        objective="sharpe",
        n_workers=N_WORKERS,
        start_date=START_DATE,
        progress_fn=wf_progress,
        df_1m=df_wf_1m,
    )
    print(f"\n  Walk-forward completed in {time.time() - t0:.0f}s ({len(wf_result.folds)} folds)", flush=True)

    # Per-fold summary table
    print(f"\n  {'Fold':<6s} {'IS Period':<24s} {'OOS Period':<24s} {'IS Shrp':>8s} {'OOS Shrp':>9s} {'Best Params'}", flush=True)
    print(f"  {'-' * 110}", flush=True)
    for f in wf_result.folds:
        params_str = ", ".join(f"{k}={v}" for k, v in f.best_params.items())
        print(
            f"  {f.fold_index + 1:<6d}"
            f" {f.is_start} -> {f.is_end:<10s}"
            f" {f.oos_start} -> {f.oos_end:<10s}"
            f" {f.is_objective_value:>8.3f}"
            f" {f.oos_objective_value:>9.3f}"
            f"  {params_str}",
            flush=True,
        )

    # Combined OOS metrics
    print_metrics(wf_result.combined_oos_metrics, "Combined OOS metrics")

    # WF efficiency
    p2_wfe_ok = wf_result.walk_forward_efficiency >= 0.5
    p2_folds_ok = len(wf_result.folds) >= 4
    print(f"\n  WF Efficiency: {wf_result.walk_forward_efficiency:.3f} ({fmt(p2_wfe_ok)})", flush=True)

    # Parameter stability
    stability = analyze_parameter_stability(wf_result, param_ranges=PARAM_RANGES)
    p2_stab_ok = stability.overall_score >= 0.4
    print(f"\n  Parameter Stability (overall={stability.overall_score:.3f}, {stability.interpretation}):", flush=True)
    for p in stability.params:
        print(
            f"    {p.name:<25s}  mode={p.mode:<8.2f}  score={p.stability_score:.3f}"
            f"  range=[{p.value_range[0]}, {p.value_range[1]}]  unique={p.unique_values}",
            flush=True,
        )

    p2_passed = p2_wfe_ok and p2_stab_ok and p2_folds_ok

    print(f"\n  Checks:", flush=True)
    print(f"    [{fmt(p2_wfe_ok)}] WF efficiency >= 0.5", flush=True)
    print(f"    [{fmt(p2_stab_ok)}] Stability score >= 0.4", flush=True)
    print(f"    [{fmt(p2_folds_ok)}] Folds >= 4 (got {len(wf_result.folds)})", flush=True)
    print(f"\n  >> PHASE 2: {fmt(p2_passed)}", flush=True)

    if not p2_passed:
        print("  Walk-forward validation failed. Continuing for diagnostics...", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 3: Prop Firm Constraint Filter
    # ══════════════════════════════════════════════════════════════════════════
    section("PHASE 3: PROP FIRM CONSTRAINTS (on WF OOS trades)")
    print(f"  Evaluating {len(wf_result.combined_oos_trades)} combined OOS trades...", flush=True)
    print(f"  Constraints:", flush=True)
    print(f"    max_drawdown_r:  {PROP_CONSTRAINTS.max_drawdown_r} (INFO only -- disabled as gate)", flush=True)
    print(f"    min_annual_r:    {PROP_CONSTRAINTS.min_annual_r}R", flush=True)
    print(f"    max_monthly_loss_r: {PROP_CONSTRAINTS.max_monthly_loss_r}R", flush=True)

    cr = evaluate_constraints(wf_result.combined_oos_trades, PROP_CONSTRAINTS)

    print(f"\n  Results:", flush=True)
    print(f"    [INFO ] Max DD: {cr.max_drawdown_r:.1f}R (not gated)", flush=True)
    print(f"    [{fmt(cr.monthly_loss_passed)}] Worst month: {cr.worst_month_r:.1f}R (<= {PROP_CONSTRAINTS.max_monthly_loss_r}R)", flush=True)
    print(f"    [{fmt(cr.expectancy_passed)}] Expectancy: {cr.expectancy:.3f}R (> 0)", flush=True)
    print(f"    [{fmt(cr.annual_r_passed)}] Avg annual R >= {PROP_CONSTRAINTS.min_annual_r}R", flush=True)

    if cr.annual_r_values:
        print(f"\n    Annual R by year (OOS):", flush=True)
        for y, r in sorted(cr.annual_r_values.items()):
            flag = " <--" if r < 0 else ""
            print(f"      {y}: {r:>8.1f}R{flag}", flush=True)

    print(f"\n  Supporting stats: {cr.total_trades} trades, {cr.win_rate:.1%} WR, "
          f"avg win {cr.avg_win_r:.2f}R, avg loss {cr.avg_loss_r:.2f}R, "
          f"max consec losses {cr.max_consecutive_losses}", flush=True)

    # Overall pass ignoring DD (since it's info-only)
    p3_passed = cr.annual_r_passed and cr.monthly_loss_passed and cr.expectancy_passed
    print(f"\n  >> PHASE 3: {fmt(p3_passed)}", flush=True)

    if not p3_passed:
        print("  Prop constraint filter failed. Continuing for diagnostics...", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 4: Hold-Out OOS Test
    # ══════════════════════════════════════════════════════════════════════════
    section("PHASE 4: HOLD-OUT OOS TEST ({HOLDOUT_START}+)")
    mode_params = {p.name: p.mode for p in stability.params}
    holdout_cfg = with_overrides(ANCHOR, **mode_params)
    print(f"  Hold-out start: {HOLDOUT_START}", flush=True)
    print(f"  This data was NEVER used during optimization.", flush=True)
    print(f"  Mode params from WF: {mode_params}", flush=True)

    t0 = time.time()
    ho_trades = run_backtest(df, holdout_cfg, start_date=HOLDOUT_START, df_1m=df_1m, df_1s=df_1s)
    ho_m = compute_metrics(ho_trades)
    print_metrics(ho_m, f"Hold-out OOS metrics ({time.time() - t0:.1f}s)")

    p4_pf_ok = ho_m["profit_factor"] > 0.9
    p4_r_ok = ho_m["total_r"] > 0
    p4_sharpe_ok = ho_m.get("sharpe_ratio", 0) > 0.5
    p4_passed = p4_pf_ok and p4_r_ok and p4_sharpe_ok

    print(f"\n  Hold-out checks:", flush=True)
    print(f"    [{fmt(p4_pf_ok)}] PF > 0.9", flush=True)
    print(f"    [{fmt(p4_r_ok)}] Total R > 0 ({ho_m['total_r']:+.1f}R)", flush=True)
    print(f"    [{fmt(p4_sharpe_ok)}] Sharpe > 0.5 ({ho_m.get('sharpe_ratio', 0):.3f})", flush=True)
    print(f"\n  >> PHASE 4: {fmt(p4_passed)}", flush=True)

    if not p4_passed:
        print("  Hold-out test failed. Continuing for diagnostics...", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # PHASE 5: Monte Carlo Survival
    # ══════════════════════════════════════════════════════════════════════════
    section("PHASE 5: MONTE CARLO SURVIVAL")
    mc_config = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    print(f"  Method:      {mc_config.method}", flush=True)
    print(f"  Simulations: {mc_config.n_simulations}", flush=True)
    print(f"  Ruin at:     {MC_RUIN_THRESHOLD}R", flush=True)
    print(f"  Trades in:   {len(wf_result.combined_oos_trades)}", flush=True)

    t0 = time.time()
    mc_result = run_monte_carlo(
        wf_result.combined_oos_trades,
        mc_config,
        ruin_threshold=MC_RUIN_THRESHOLD,
    )
    print(f"\n  MC completed in {time.time() - t0:.1f}s", flush=True)

    # Prop constraint MC evaluation
    trade_dates = [t.date for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL]
    mc_surv = evaluate_constraints_mc(mc_result, PROP_CONSTRAINTS, trade_dates=trade_dates)

    survival = mc_surv["survival_rate"]
    p5_strong = survival >= 0.85
    p5_pass = survival >= 0.60
    p5_surv_ok = p5_pass  # 60% is the minimum pass; 85%+ is strong
    p5_passed = p5_surv_ok

    print(f"\n  Actual performance:", flush=True)
    print(f"    Final PnL:  {mc_result.actual_final_pnl:.1f}R", flush=True)
    print(f"    Max DD:     {mc_result.actual_max_drawdown:.1f}R", flush=True)
    print(f"    Sharpe:     {mc_result.actual_sharpe:.3f}", flush=True)

    print(f"\n  MC percentiles -- Final PnL (R):", flush=True)
    for k, v in mc_result.final_pnl_percentiles.items():
        print(f"    {k}: {v:>8.1f}R", flush=True)

    print(f"\n  MC percentiles -- Max DD (R):", flush=True)
    for k, v in mc_result.max_dd_percentiles.items():
        print(f"    {k}: {v:>8.1f}R", flush=True)

    print(f"\n  Ruin probability: {mc_result.ruin_probability:.1%}", flush=True)
    print(f"  Survival rate:    {survival:.1%}", flush=True)
    print(f"  DD percentiles:   {mc_surv['dd_percentiles']}", flush=True)
    if "monthly_loss_pass_rate" in mc_surv:
        print(f"  Monthly loss pass rate: {mc_surv['monthly_loss_pass_rate']:.1%}", flush=True)
    if "annual_r_pass_rate" in mc_surv:
        print(f"  Annual R pass rate: {mc_surv['annual_r_pass_rate']:.1%}", flush=True)

    # Interpret survival
    if survival >= 0.85:
        interp = "Strong -- deploy with full size"
    elif survival >= 0.70:
        interp = "Acceptable -- deploy, monitor closely"
    elif survival >= 0.50:
        interp = "Conditional -- reduce size or tighten stops"
    else:
        interp = "No-go -- strategy will likely breach"
    print(f"  Interpretation: {interp}", flush=True)

    print(f"    [{'PASS' if p5_strong else 'WEAK' if p5_pass else 'FAIL'}] Survival: {survival:.1%} (strong >= 85%, pass >= 60%)", flush=True)
    print(f"\n  >> PHASE 5: {fmt(p5_passed)}", flush=True)

    # ══════════════════════════════════════════════════════════════════════════
    # FINAL VERDICT
    # ══════════════════════════════════════════════════════════════════════════
    total_elapsed = time.time() - t_start
    section("FINAL VERDICT")
    print(f"  Anchor: stop={STOP_ATR}% | rr={RR_RATIO} | gap={MIN_GAP_ATR}% | tp1={TP1_RATIO}", flush=True)

    phases = [
        ("Phase 1 (Structural)", p1_passed,
         f"{p1_m['total_trades']} trades, {p1_m['win_rate']:.1%} WR, PF {p1_m['profit_factor']:.2f}, Calmar {p1_m['calmar_ratio']:.2f}"),
        ("Phase 2 (Walk-Forward)", p2_passed,
         f"WF eff {wf_result.walk_forward_efficiency:.2f}, stability {stability.overall_score:.2f} ({stability.interpretation})"),
        ("Phase 3 (Prop Filter)", p3_passed,
         f"DD {cr.max_drawdown_r:.1f}R, worst month {cr.worst_month_r:.1f}R, expectancy {cr.expectancy:.3f}R"),
        ("Phase 4 (Hold-Out)", p4_passed,
         f"PF {ho_m['profit_factor']:.2f}, {ho_m['total_r']:+.1f}R, {ho_m['total_trades']} trades"),
        ("Phase 5 (MC Survival)", p5_passed,
         f"{survival:.0%} survival at {MC_RUIN_THRESHOLD}R ruin"),
    ]

    for name, passed, detail in phases:
        status = fmt(passed)
        print(f"  {name + ':':<28s} {status:<6s} -- {detail}", flush=True)

    n_passed = sum(1 for _, p, _ in phases if p)
    if n_passed == 5:
        verdict = "GO"
        verdict_detail = "All phases pass. Strategy is prop-firm ready."
    elif n_passed == 4:
        failed = [n for n, p, _ in phases if not p]
        verdict = "CONDITIONAL"
        verdict_detail = f"4/5 passed. Failed: {', '.join(failed)}. Trade with caution."
    else:
        failed = [n for n, p, _ in phases if not p]
        verdict = "NO-GO"
        verdict_detail = f"{n_passed}/5 passed. Failed: {', '.join(failed)}. Revisit parameters."

    print(f"\n  >> VERDICT: {verdict}", flush=True)
    print(f"     {verdict_detail}", flush=True)
    print(f"\n  Recommended params (WF mode): {mode_params}", flush=True)
    print(f"\n  Total pipeline time: {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
```

## Placeholders

| Placeholder | Example | Description |
|---|---|---|
| `{INSTRUMENT}` | ES | Instrument symbol |
| `{INSTRUMENT_IMPORT}` | ES, SIX_B, GC | Python import name from instruments.py |
| `{SESSION_UPPER}` | NY, ASIA, LDN | Session name for display and SessionConfig |
| `{STRATEGY}` | continuation, reversal, inversion | Strategy type |
| `{DIRECTION}` | both, long, short | Direction filter |
| `{ORB_START}` | "09:30" | ORB window start time |
| `{ORB_END}` | "09:45" | ORB window end time |
| `{ENTRY_START}` | "09:45" | Entry window start (usually same as ORB_END) |
| `{ENTRY_END}` | "12:00" | Last time an FVG entry can fill |
| `{FLAT_TIME}` | "15:50" | Flatten all positions |
| `{FLAT_END}` | "16:00" | Session close |
| `{STOP_ATR}` | 5.2 | Stop distance as % of daily ATR |
| `{RR_RATIO}` | 2.0 | Risk-reward ratio |
| `{TP1_RATIO}` | 0.40 | Fraction taken at first take-profit |
| `{MIN_GAP_ATR}` | 1.25 | Min FVG size as % of daily ATR |
| `{MAX_GAP_ATR}` | 0.0 | Max FVG size as % of daily ATR (0 = no limit) |
| `{MAX_GAP_POINTS}` | 50.0 | Max FVG size in points |
| `{ATR_PERIOD}` | 50 | ATR lookback length |
| `{DATA_FILE_5M}` | ES_5m.csv | Filename passed to loader |
| `{START_DATE}` | 2016-01-01 | Backtest start date |
| `{WF_END_SLICE}` | 2025-01-31 | End slice for WF data (prevents OOS bleed into hold-out) |
| `{HOLDOUT_START}` | 2025-01-01 | Hold-out OOS start date |
| `{MIN_ANNUAL_R}` | 12.0 | Prop constraint: min avg annual R |
| `{MAX_MONTHLY_LOSS_R}` | 5.0 | Prop constraint: max monthly loss in R |
| `{PARAM_RANGES_DICT}` | (see below) | Walk-forward sweep ranges dict |

### PARAM_RANGES_DICT Format

Use session-prefixed param names matching the session (ny_, asia_, ldn_):

```python
# Example for NY session
{
    "rr": [2.0, 2.5, 3.0],
    "ny_stop_atr_pct": [5.0, 7.5, 10.0],
    "ny_min_gap_atr_pct": [1.0, 1.5, 2.0],
    "tp1_ratio": [0.4, 0.5, 0.6],
}

# Example for LDN session
{
    "ldn_stop_atr_pct": [5.0, 5.2, 5.4],
    "rr": [1.75, 2.0, 2.25],
    "ldn_min_gap_atr_pct": [1.0, 1.25, 1.5],
    "tp1_ratio": [0.35, 0.4, 0.45],
}
```

## Phase Thresholds Summary

| Phase | Check | Threshold | Hard Gate? |
|---|---|---|---|
| 1 - Structural | Total trades | >= 100 | Yes |
| 1 - Structural | Profit factor | >= 1.2 | Yes |
| 1 - Structural | Win rate | >= 35% | Yes |
| 1 - Structural | Calmar | >= 0.5 | Yes |
| 1 - Structural | Median stop | >= 10 ticks | Yes |
| 2 - Walk-Forward | WF efficiency | >= 0.5 | Yes |
| 2 - Walk-Forward | Stability score | >= 0.4 | Yes |
| 2 - Walk-Forward | Folds completed | >= 4 | Yes (ensures statistical significance) |
| 3 - Prop Filter | Max drawdown | 999.0R | INFO only |
| 3 - Prop Filter | Worst monthly loss | <= {MAX_MONTHLY_LOSS_R}R | Yes |
| 3 - Prop Filter | Expectancy | > 0 | Yes |
| 3 - Prop Filter | Avg annual R | >= {MIN_ANNUAL_R}R | Yes |
| 4 - Hold-Out | Profit factor | > 0.9 | Yes |
| 4 - Hold-Out | Total R | > 0 | Yes |
| 4 - Hold-Out | Sharpe ratio | > 0.5 | Yes |
| 5 - Monte Carlo | Survival rate | >= 60% (pass), >= 85% (strong) | Yes (60%) |

## Verdict Logic

- **GO**: All 5 phases pass
- **CONDITIONAL**: 4 of 5 pass (note which failed)
- **NO-GO**: 3 or fewer pass

## Key Design Decisions

1. **DD is NOT a hard filter** -- `max_drawdown_r=999.0` disables DD as a gate. DD is reported as INFO only. This is a critical user preference.
2. **MC ruin threshold is standalone** -- Set to -25R, not tied to prop constraints DD limit.
3. **WF uses 1m magnifier only** -- 1s maps are too large for multiprocessing serialization. 1m precision is sufficient for parameter stability analysis.
4. **Full-history backtest uses 1s** -- Phase 1 and Phase 4 use the full hierarchical 5m->1m->1s magnifier for accurate fill simulation.
5. **WF data is sliced** -- `WF_END_SLICE` prevents OOS windows from bleeding into the hold-out period.
6. **Mode params for hold-out** -- Phase 4 uses the statistical mode of each parameter across WF folds, not the last fold's params.
