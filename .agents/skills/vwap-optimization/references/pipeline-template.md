# VWAP Robust Pipeline Script Template

This template generates a complete 5-phase robust pipeline script for VWAP strategy prop firm validation.
Placeholders are wrapped in `{CURLY_BRACES}` and get filled in at generation time.

Uses `run_walkforward_vwap` for Phase 2 walk-forward analysis (parallel, signal-cached, with warmup).

```python
#!/usr/bin/env python3
"""{INSTRUMENT} {SESSION_UPPER} VWAP {DIRECTION} -- 5-Phase Robust Pipeline.

Anchor config: stop_buf={STOP_ATR}%, rr={RR_RATIO}, tp1={TP1_RATIO}
  dev_mode={DEV_MODE}, dev_thresh={DEV_THRESH}, rejection={REJECTION_MODE}, tp2={TP2_MODE}
Structural: entry {ENTRY_START}-{ENTRY_END}, flat {FLAT_START}, ATR {ATR_PERIOD}, {DIRECTION} dir, bar magnifier
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
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.vwap_config import (
    VWAPSessionConfig, VWAPStrategyConfig,
    with_vwap_overrides,
)
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.optimize.walkforward_vwap import run_walkforward_vwap
from orb_backtest.optimize.prop_constraints import (
    PropFirmConstraints,
    evaluate_constraints,
)
from orb_backtest.simulate.monte_carlo import run_monte_carlo, MonteCarloConfig

# -- Instrument & Dates --------------------------------------------------------

INST = {INSTRUMENT_IMPORT}
START_DATE = "{START_DATE}"
WF_END_SLICE = "{WF_END_SLICE}"
HOLDOUT_START = "{HOLDOUT_START}"
N_WORKERS = 8

# -- Session & Strategy Config -------------------------------------------------

SESS = VWAPSessionConfig(
    name="{SESSION_UPPER}",
    session_open="{SESSION_OPEN}",
    entry_start="{ENTRY_START}",
    entry_end="{ENTRY_END}",
    flat_start="{FLAT_START}",
    flat_end="{FLAT_END}",
    deviation_mode="{DEV_MODE}",
    deviation_atr_pct={DEV_ATR_PCT},
    deviation_std={DEV_STD},
    rejection_mode="{REJECTION_MODE}",
    stop_atr_pct={STOP_ATR},
)

ANCHOR = VWAPStrategyConfig(
    rr={RR_RATIO},
    tp1_ratio={TP1_RATIO},
    risk_usd=5000.0,
    atr_length={ATR_PERIOD},
    tp2_mode="{TP2_MODE}",
    min_qty=1.0,
    qty_step=1.0,
    sessions=(SESS,),
    instrument=INST,
    direction_filter="{DIRECTION}",
    use_bar_magnifier=True,
    name="{INSTRUMENT} {SESSION_UPPER} VWAP Robust Pipeline",
)

# -- Prop Constraints (DD is NOT a hard filter) --------------------------------

PROP_CONSTRAINTS = PropFirmConstraints(
    max_drawdown_r=999.0,
    min_annual_r={MIN_ANNUAL_R},
    max_monthly_loss_r={MAX_MONTHLY_LOSS_R},
    min_positive_expectancy=True,
)

MC_RUIN_THRESHOLD = -25.0

# -- Walk-Forward Sweep Ranges -------------------------------------------------
# Use session-prefixed names for session-level params

PARAM_RANGES = {PARAM_RANGES_DICT}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)

# -- Helpers -------------------------------------------------------------------


def median_stop_ticks(trades):
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / INST.min_tick for t in filled)


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


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    section("{INSTRUMENT} {SESSION_UPPER} VWAP {DIRECTION} -- ROBUST PIPELINE")
    print(f"  Anchor: stop_buf={STOP_ATR}% | rr={RR_RATIO} | tp1={TP1_RATIO}", flush=True)
    dev_desc = f"dev_atr={DEV_ATR_PCT}%" if "{DEV_MODE}" == "atr" else f"dev_std={DEV_STD}"
    print(f"  {dev_desc} | reject={REJECTION_MODE} | tp2={TP2_MODE}", flush=True)
    print(f"  entry {ENTRY_START}-{ENTRY_END} | flat {FLAT_START} | ATR {ATR_PERIOD} | {DIRECTION} | magnifier", flush=True)

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
    print(f"  Loaded in {time.time() - t_load:.1f}s", flush=True)

    t_start = time.time()

    # ======================================================================
    # PHASE 1: Structural Validation
    # ======================================================================
    section("PHASE 1: STRUCTURAL VALIDATION")
    print("  Running full-history VWAP backtest on anchor config...", flush=True)

    t0 = time.time()
    p1_trades = run_vwap_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
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

    # ======================================================================
    # PHASE 2: Walk-Forward + Parameter Stability
    # ======================================================================
    section("PHASE 2: WALK-FORWARD + PARAMETER STABILITY")
    print(f"  Config: 36m IS / 12m OOS / 12m step (rolling)", flush=True)
    print(f"  Grid: {GRID_SIZE} combos per fold", flush=True)
    print(f"  Workers: {N_WORKERS}", flush=True)
    print(f"  Magnifier: 1m (1s too large for multiprocessing serialization)", flush=True)
    print(f"  Params: {list(PARAM_RANGES.keys())}", flush=True)

    df_wf = df.loc[:WF_END_SLICE]
    df_wf_1m = df_1m.loc[:WF_END_SLICE] if df_1m is not None else None

    t0 = time.time()
    wf = run_walkforward_vwap(
        df_wf, df_wf_1m, ANCHOR, PARAM_RANGES,
        is_months=36, oos_months=12, step_months=12,
        objective="sharpe",
        n_workers=N_WORKERS,
        start_date=START_DATE,
    )
    print(f"\n  Walk-forward completed in {time.time() - t0:.0f}s ({len(wf.folds)} folds)", flush=True)

    print_metrics(wf.combined_oos_metrics, "Combined OOS metrics")

    # Compute parameter stability from fold best_params
    param_names = list(PARAM_RANGES.keys())
    param_modes = {}
    param_stability = {}
    for pname in param_names:
        values = [fold.best_params.get(pname) for fold in wf.folds]
        counter = Counter(values)
        mode_val = counter.most_common(1)[0][0]
        param_modes[pname] = mode_val
        param_stability[pname] = counter[mode_val] / len(values)
    overall_stability = sum(param_stability.values()) / len(param_stability) if param_stability else 0

    p2_wfe_ok = wf.walk_forward_efficiency >= 0.5
    p2_folds_ok = len(wf.folds) >= 4
    p2_stab_ok = overall_stability >= 0.4

    print(f"\n  WF Efficiency: {wf.walk_forward_efficiency:.3f} ({fmt(p2_wfe_ok)})", flush=True)
    print(f"\n  Parameter Stability (overall={overall_stability:.3f}):", flush=True)
    for pname, score in param_stability.items():
        print(f"    {pname:<30s}  mode={param_modes[pname]:<8}  stability={score:.3f}", flush=True)

    p2_passed = p2_wfe_ok and p2_stab_ok and p2_folds_ok

    print(f"\n  Checks:", flush=True)
    print(f"    [{fmt(p2_wfe_ok)}] WF efficiency >= 0.5", flush=True)
    print(f"    [{fmt(p2_stab_ok)}] Stability score >= 0.4", flush=True)
    print(f"    [{fmt(p2_folds_ok)}] Folds >= 4 (got {len(wf.folds)})", flush=True)
    print(f"\n  >> PHASE 2: {fmt(p2_passed)}", flush=True)

    # ======================================================================
    # PHASE 3: Prop Firm Constraints
    # ======================================================================
    section("PHASE 3: PROP FIRM CONSTRAINTS (on WF OOS trades)")
    oos_trades = wf.combined_oos_trades
    print(f"  Evaluating {len(oos_trades)} combined OOS trades...", flush=True)

    cr = evaluate_constraints(oos_trades, PROP_CONSTRAINTS)

    print(f"\n  Results:", flush=True)
    print(f"    [INFO ] Max DD: {cr.max_drawdown_r:.1f}R (not gated)", flush=True)
    print(f"    [{fmt(cr.monthly_loss_passed)}] Worst month: {cr.worst_month_r:.1f}R", flush=True)
    print(f"    [{fmt(cr.expectancy_passed)}] Expectancy: {cr.expectancy:.3f}R", flush=True)
    print(f"    [{fmt(cr.annual_r_passed)}] Avg annual R >= {PROP_CONSTRAINTS.min_annual_r}R", flush=True)

    p3_passed = cr.annual_r_passed and cr.monthly_loss_passed and cr.expectancy_passed
    print(f"\n  >> PHASE 3: {fmt(p3_passed)}", flush=True)

    # ======================================================================
    # PHASE 4: Hold-Out OOS
    # ======================================================================
    section(f"PHASE 4: HOLD-OUT OOS TEST ({HOLDOUT_START}+)")
    holdout_cfg = with_vwap_overrides(ANCHOR, **param_modes)
    print(f"  Mode params: {param_modes}", flush=True)

    t0 = time.time()
    ho_trades = run_vwap_backtest(df, holdout_cfg, start_date=HOLDOUT_START, df_1m=df_1m, df_1s=df_1s)
    ho_m = compute_metrics(ho_trades)
    print_metrics(ho_m, f"Hold-out OOS metrics ({time.time() - t0:.1f}s)")

    p4_pf_ok = ho_m["profit_factor"] > 0.9
    p4_r_ok = ho_m["total_r"] > 0
    p4_sharpe_ok = ho_m.get("sharpe_ratio", 0) > 0.5
    p4_passed = p4_pf_ok and p4_r_ok and p4_sharpe_ok

    print(f"\n  [{fmt(p4_pf_ok)}] PF > 0.9", flush=True)
    print(f"  [{fmt(p4_r_ok)}] Total R > 0 ({ho_m['total_r']:+.1f}R)", flush=True)
    print(f"  [{fmt(p4_sharpe_ok)}] Sharpe > 0.5 ({ho_m.get('sharpe_ratio', 0):.3f})", flush=True)
    print(f"\n  >> PHASE 4: {fmt(p4_passed)}", flush=True)

    # ======================================================================
    # PHASE 5: Monte Carlo Survival
    # ======================================================================
    section("PHASE 5: MONTE CARLO SURVIVAL")
    mc_config = MonteCarloConfig(n_simulations=2000, method="bootstrap", seed=42)
    print(f"  Sims: {mc_config.n_simulations} | Ruin: {MC_RUIN_THRESHOLD}R", flush=True)

    t0 = time.time()
    mc_result = run_monte_carlo(oos_trades, mc_config, ruin_threshold=MC_RUIN_THRESHOLD)
    print(f"  MC completed in {time.time() - t0:.1f}s", flush=True)

    survival = 1.0 - mc_result.ruin_probability
    p5_passed = survival >= 0.60

    print(f"\n  Survival: {survival:.1%} (strong >= 85%, pass >= 60%)", flush=True)
    print(f"  Ruin prob: {mc_result.ruin_probability:.1%}", flush=True)
    print(f"\n  >> PHASE 5: {fmt(p5_passed)}", flush=True)

    # ======================================================================
    # FINAL VERDICT
    # ======================================================================
    total_elapsed = time.time() - t_start
    section("FINAL VERDICT")

    phases = [
        ("Phase 1 (Structural)", p1_passed),
        ("Phase 2 (Walk-Forward)", p2_passed),
        ("Phase 3 (Prop Filter)", p3_passed),
        ("Phase 4 (Hold-Out)", p4_passed),
        ("Phase 5 (MC Survival)", p5_passed),
    ]

    for name, passed in phases:
        print(f"  {name + ':':<28s} {fmt(passed)}", flush=True)

    n_passed = sum(1 for _, p in phases if p)
    if n_passed == 5:
        verdict = "GO"
    elif n_passed == 4:
        verdict = "CONDITIONAL"
    else:
        verdict = "NO-GO"

    print(f"\n  >> VERDICT: {verdict}", flush=True)
    print(f"  Mode params: {param_modes}", flush=True)
    print(f"  Total pipeline time: {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
```

## Placeholders

| Placeholder | Example | Description |
|---|---|---|
| `{INSTRUMENT}` | NQ | Instrument symbol |
| `{INSTRUMENT_IMPORT}` | NQ | Python import name |
| `{SESSION_UPPER}` | NY | Session name |
| `{SESSION_OPEN}` | "09:30" | Session open |
| `{DIRECTION}` | both | Direction filter |
| `{ENTRY_START}` | "09:35" | Entry window start |
| `{ENTRY_END}` | "12:00" | Entry window end |
| `{FLAT_START}` | "15:50" | Flat time |
| `{FLAT_END}` | "16:00" | Session close |
| `{DEV_MODE}` | "atr" | Deviation mode |
| `{DEV_ATR_PCT}` | 30.0 | Deviation ATR % |
| `{DEV_STD}` | 2.0 | Deviation std |
| `{DEV_THRESH}` | "atr=30%" | Display label |
| `{REJECTION_MODE}` | "close" | Rejection mode |
| `{TP2_MODE}` | "fixed_rr" | TP2 mode |
| `{STOP_ATR}` | 3.0 | Stop buffer % |
| `{RR_RATIO}` | 2.5 | Risk-reward |
| `{TP1_RATIO}` | 0.5 | TP1 ratio |
| `{ATR_PERIOD}` | 14 | ATR length |
| `{DATA_FILE_5M}` | NQ_5m.csv | Data file |
| `{START_DATE}` | 2016-01-01 | Start date |
| `{WF_END_SLICE}` | 2025-01-31 | WF data end |
| `{HOLDOUT_START}` | 2025-01-01 | Hold-out start |
| `{MIN_ANNUAL_R}` | 12.0 | Prop min annual R |
| `{MAX_MONTHLY_LOSS_R}` | 5.0 | Prop max monthly loss |
| `{PARAM_RANGES_DICT}` | (see below) | WF sweep ranges |

### PARAM_RANGES_DICT Format

Use session-prefixed param names for session-level params:

```python
# Example for NY session with ATR deviation mode
{
    "rr": [2.0, 2.5, 3.0],
    "ny_stop_atr_pct": [1.0, 2.0, 3.0],
    "ny_deviation_atr_pct": [20.0, 25.0, 30.0],
    "tp1_ratio": [0.4, 0.5, 0.6],
}

# Example for LDN session with std deviation mode
{
    "rr": [1.5, 2.0, 2.5],
    "ldn_stop_atr_pct": [2.0, 3.0, 4.0],
    "ldn_deviation_std": [1.5, 2.0, 2.5],
    "tp1_ratio": [0.3, 0.4, 0.5],
}
```

## Key Design Decisions

1. **DD is NOT a hard filter** -- `max_drawdown_r=999.0`. DD is INFO only.
2. **MC ruin threshold** -- standalone at -25R, not tied to prop DD.
3. **WF uses 1m magnifier only** -- 1s too large for serialization.
4. **Walk-forward via `run_walkforward_vwap`** -- parallel, signal-cached, with warmup buffer. Handles fold generation, IS sweep, OOS testing, and WF efficiency computation.
5. **WF data sliced** -- `WF_END_SLICE` prevents OOS bleed into hold-out.
6. **Mode params for hold-out** -- Phase 4 uses the statistical mode of each parameter across WF folds.
