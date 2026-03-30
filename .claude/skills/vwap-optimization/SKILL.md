---
triggers:
  - "vwap optimize"
  - "vwap optimization"
  - "optimize vwap"
  - "vwap baseline to pipeline"
  - "full vwap optimization"
  - "end-to-end vwap"
---

# VWAP Optimization

Six-step end-to-end workflow that takes an instrument's VWAP Reversion strategy from baseline through validated, prop-firm-ready configuration. Generates runnable Python scripts at each step.

**Steps**: (1) Baseline, (2) Variable Sweeps, (3) Grid Sweep, (4) Robust Pipeline, (5) Save Final Config, (6) Update Learnings.

Orchestrates sweep discipline with robust pipeline validation. Calmar ratio is the primary optimization objective. DD is NOT a hard filter -- set `max_drawdown_r=999.0` everywhere.

**HARD CONSTRAINT -- 10-Tick Minimum Stop**: Never test, adopt, or save a config where the median stop is less than 10 ticks. Stops below 10 ticks are unrealistic -- slippage eats the edge. Compute as `median(t.risk_points / instrument.min_tick for filled trades)`. Skip and print `SKIP (median stop < 10 ticks)` for any variant that fails this check. This applies at EVERY step: baseline, sweeps, grid, pipeline, and save.

**HARD CONSTRAINT -- Minimum TP1 Ratio 0.2**: Never test, adopt, or save a config with `tp1_ratio < 0.2`. A TP1 ratio below 0.2 takes too little off the table at the first target. Skip and print `SKIP (tp1_ratio < 0.2)` for any variant that fails this check. This applies at EVERY step: sweeps, grid, and save.

## Strategy Overview

VWAP Reversion trades mean-reversion entries when price deviates significantly from the session-anchored VWAP, then shows a rejection candle. Unlike ORB strategies, there is no Opening Range Breakout or Fair Value Gap detection -- the signal is purely VWAP deviation + rejection.

**Key differences from ORB optimization**:
- No ORB window, no FVG detection, no min_gap_atr_pct, no max_gap_atr_pct, no ICF, no qualifying move, no SMA trend gate
- Deviation threshold replaces gap filtering (either ATR%-based or std-dev-based)
- Rejection mode (close vs pinbar) is a structural choice
- TP2 can target VWAP touch instead of fixed R:R
- Stop is placed beyond rejection candle extreme + optional ATR buffer (stop_atr_pct)

## Before Starting

Gather from the user:
1. **Instrument** symbol (NQ, ES, GC, CL, YM, RTY, 6B)
2. **Session** (NY, ASIA, LDN)
3. **Direction hint** (longs, shorts, or both)
4. **Deviation mode preference** (atr, std, or sweep both)
5. **Rejection mode preference** (close, pinbar, or sweep both)
6. **TP2 mode** (fixed_rr or vwap)

Then verify:
- Read `python/learnings/{SYMBOL}.md` -- if the same VWAP strategy/session/direction combo is already NO-GO, stop and inform the user. Only proceed if they have a fundamentally different approach.
- Confirm data files exist: `{SYMBOL}_5m.csv` (required), `{SYMBOL}_1m.csv` (magnifier), `{SYMBOL}_1s.parquet` (optional, preferred magnifier).
- Determine `START_DATE` -- default `2016-01-01` unless the instrument has less data.
- Compute `DATA_YEARS` from start to current date (used for R/yr calculation).
- Query the experiment DB for existing names with the same instrument/session prefix to avoid duplicates (per CLAUDE.md naming convention).

## Progress Tracking (CRITICAL -- survives context compaction)

Maintain a temporary file `python/{asset}_{session}_vwap_progress.md` throughout the workflow. This file is the single source of truth for workflow state and survives context compaction.

- **Create** it at the start of Step 1 using `references/progress-template.md`.
- **Read it first** at the beginning of every step -- if context was compacted, this file tells you exactly where you are and what to do next.
- **Update it** after every significant result: baseline metrics, each sweep round (adoptions + new anchor), grid sweep winner, pipeline phase results.
- **Delete it** after Step 6 completes -- the learnings doc now has the permanent record.

If you find an existing progress file when starting, **resume from where it left off** rather than starting over. The "Next Action" section tells you exactly what to do.

## Step 1: Baseline

Generate `run_{asset}_{session}_vwap_baseline.py` in `python/scripts/`.

Use the instrument's default VWAP session config times and standard VWAPStrategyConfig defaults. Run a single backtest on the full date range.

```python
# Key structure -- always include
import sys
sys.path.insert(0, "src")

from dataclasses import replace
from orb_backtest.vwap_config import (
    VWAPSessionConfig, VWAPStrategyConfig,
    NY_VWAP_SESSION, ASIA_VWAP_SESSION, LDN_VWAP_SESSION,
    with_vwap_overrides,
)
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}  # e.g. ES, NQ, GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = {INSTRUMENT_IMPORT}
START_DATE = "2016-01-01"
# Load df_5m, df_1m, df_1s
# Build VWAPSessionConfig + VWAPStrategyConfig with defaults
# Run backtest, compute metrics, print results + R by year
```

**Pass criteria**: >100 trades AND profit factor >1.0 AND median stop >= 10 ticks.
- FAIL: Record as NO-GO in learnings, stop workflow.
- PASS: This becomes the initial anchor config for Step 2.
- Also print median stop in ticks for the baseline -- this is the sanity check before sweeps begin.

**Progress**: Create `python/{asset}_{session}_vwap_progress.md` from `references/progress-template.md`. Record baseline metrics, anchor config, and set Next Action to "Run variable sweeps R1".

**Experiment name**: `{INSTRUMENT} {SESSION} VWAP Baseline`

## Step 2: Variable Sweeps

Generate `run_{asset}_{session}_vwap_variable_sweeps_{N}.py` in `python/scripts/`. N starts at 1 and increments each round.

Variable sweeps are split into two phases -- the same structural logic as ORB optimization but with VWAP-specific dimensions.

### Step 2a: Stand-Alone Sweeps (single pass, no re-sweep)

Sweep 12 dimensions once, in this order. Adopt any that pass the threshold. No re-sweeping -- these are decided once and feed into the core loop as fixed context.

| # | Dimension | Config field | Typical values | Why stand-alone |
|---|-----------|-------------|----------------|-----------------|
| 1 | Direction | `direction_filter` | both, long, short | One-time structural choice; never flips back once adopted |
| 2 | Deviation mode | `deviation_mode` on session | "atr", "std" | Structural -- decides how bands scale; one-time decision |
| 3 | Rejection mode | `rejection_mode` on session | "close", "pinbar" | Structural -- decides entry candle type; one-time decision |
| 4 | TP2 mode | `tp2_mode` | "fixed_rr", "vwap" | Structural -- decides TP2 exit logic; one-time decision |
| 5 | Entry end time | `entry_end` on session | Session-appropriate times | Session boundary; no cascade to core params |
| 6 | Flat time | `flat_start` on session | Session-appropriate times | Session boundary; no cascade |
| 7 | ATR length | `atr_length` | 5, 7, 10, 14, 20, 30 | Major lever; decisive for deviation threshold scaling |
| 8 | Deviation ATR % | `deviation_atr_pct` on session | 10, 15, 20, 25, 30, 40, 50 | **Only if deviation_mode="atr"** -- threshold for entry signal |
| 9 | Deviation std | `deviation_std` on session | 1.0, 1.5, 2.0, 2.5, 3.0 | **Only if deviation_mode="std"** -- band width multiplier |
| 10 | DOW exclusion | post-backtest filter | none, Mon, Tue, Wed, Thu, Fri, M+F, Th+F | Post-filter; no cascade; data-mining risk |
| 11 | Weekly loss cap | `apply_weekly_loss_cap` | OFF, 2, 3, 4, 5, 7, 10 | Order-sensitive risk overlay; apply last |
| 12 | Monthly loss cap | `apply_monthly_loss_cap` | OFF, 3, 5, 7, 10, 15 | Order-sensitive risk overlay; apply last |

**Mode-dependent sweeping**:
- If the anchor (or adopted) deviation_mode is "atr": sweep dim 8 (deviation_atr_pct), skip dim 9.
- If the anchor (or adopted) deviation_mode is "std": sweep dim 9 (deviation_std), skip dim 8.
- If the user requests "sweep both", first sweep deviation_mode in dim 2. If "atr" wins, sweep dim 8. If "std" wins, sweep dim 9.

After the stand-alone pass completes, update the anchor with any adoptions. This becomes the fixed context for the core convergence loop.

### Step 2b: Core Convergence Loop (iterative re-sweep)

Sweep 3 core dimensions iteratively until convergence (0 adoptions in a full pass):

| # | Dimension | Config field | Typical values | Why core |
|---|-----------|-------------|----------------|----------|
| 1 | Stop buffer | `stop_atr_pct` on session | 0, 1, 2, 3, 5, 7.5, 10 | Buffer beyond rejection candle -- changes force RR + TP1 re-evaluation |
| 2 | R:R ratio | `rr` | 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0 | Tightly coupled to stop; re-adopted after every significant stop change |
| 3 | TP1 ratio | `tp1_ratio` | 0.2, 0.3, 0.4, 0.5, 0.6, 0.7 (min 0.2 -- hard constraint) | Weakly coupled to RR; adjusts after RR shifts |

**Note on TP2 mode interaction**: If tp2_mode="vwap", the RR sweep may be less impactful (TP2 exits at VWAP, not at fixed R:R). Still sweep it -- the RR value affects TP1 placement and the fixed_rr fallback when VWAP touch doesn't occur.

**Convergence**: Typically 2-3 rounds. The stop-RR-TP1 loop is the only one that actually oscillates.

### Sweep Script Requirements

Each script must:
- Print a formatted table per dimension with: Trades, WR, PF, Sharpe, Net R, R/yr, MaxDD, Calmar.
- Print R by year for key comparisons.
- Track `neg_year_set()` -- negative full calendar years (exclude current partial year).
- Print a summary table at the end showing the best value per dimension and whether to adopt.

**Adoption rule**: Calmar delta > +0.3 AND no new negative full years AND trade count stays >100 AND median stop >= 10 ticks.

**Convergence logic**:
- **Stand-alone (Step 2a)**: Single pass (12 dims). Adopt qualifying dims. Update anchor. Move to Step 2b.
- **Core (Step 2b)**: If any of the 3 core dims is adopted, update anchor, increment N, re-sweep only the 3 core dims. Converged when 0 core adoptions in a full pass.
- On convergence, print "Ready for grid sweep."

**Script naming**: Stand-alone pass uses `_vwap_variable_sweeps_1.py`. Core rounds use `_vwap_variable_sweeps_2.py`, `_vwap_variable_sweeps_3.py`, etc. (N increments each core round).

**DOW filter**: Applied post-backtest via `apply_dow_filter()`, not in config.

**Loss caps (weekly/monthly)**: Applied post-backtest via `apply_weekly_loss_cap()` / `apply_monthly_loss_cap()` from `gates.py`. Order-sensitive -- apply LAST in the filter chain (after DOW filter).

**Config mutation**: Use `dataclasses.replace()` for VWAPStrategyConfig. For session-level params, replace the session within the sessions tuple:
```python
new_sess = replace(anchor_session, deviation_atr_pct=25.0)
cfg = replace(anchor_config, sessions=(new_sess,))
```
Or use `with_vwap_overrides()` for session-prefixed params:
```python
cfg = with_vwap_overrides(anchor_config, ny_deviation_atr_pct=25.0)
```

**Progress**: After each pass/round completes, update the progress file: append a Stand-alone or Core Round entry to the Adoption Log with entering/exiting anchor and adoptions. Update Current Anchor Config/Metrics tables. Update Next Action. Add the sweep script to Scripts Generated.

**Experiment name**: Not saved to DB (these are diagnostic sweeps printed to stdout).

## Step 3: Grid Sweep

Generate `run_{asset}_{session}_vwap_grid_sweep_r{N}.py` in `python/scripts/`.

Grid dimensionality depends on TP2 mode:

### tp2_mode="fixed_rr" -- 4D grid

```python
STOPS    = [anchor-1, anchor-0.5, anchor, anchor+0.5, anchor+1]    # stop_atr_pct ~4-5 values
RRS      = [anchor-1, anchor-0.5, anchor, anchor+0.5, anchor+1]    # rr ~5-6 values
TP1S     = [anchor-0.1, anchor-0.05, anchor, anchor+0.05, anchor+0.1]  # tp1_ratio ~5-6 values
DEV_VALS = [...]  # deviation_atr_pct or deviation_std ~4-5 values around anchor
```

4D grid: stop_buffer x rr x tp1 x deviation_threshold. Target: 200-600 total combos.

### tp2_mode="vwap" -- 3D grid

When TP2 exits at VWAP touch, the RR value has less direct impact (it mainly affects TP1 placement). The grid may collapse to 3D:

```python
STOPS    = [...]  # stop_atr_pct ~5-6 values
DEV_VALS = [...]  # deviation threshold ~5-6 values
TP1S     = [...]  # tp1_ratio ~4-5 values (optional if TP1 is well-converged)
```

3D grid: stop_buffer x deviation_threshold x tp1. Target: 100-300 combos.

### Grid Script Requirements

Each script must:
- Iterate all combos, run `run_vwap_backtest`, compute metrics.
- **Skip combos where median stop < 10 ticks** (10-tick minimum stop rule).
- **Skip combos where tp1_ratio < 0.2** (minimum TP1 rule).
- Print progress every 50 combos (elapsed time, rate, ETA).
- Print Top 20 by Calmar (all combos).
- Print Top 20 by Calmar (0 negative full years only).
- Print grid summary: total combos, % with 0 neg years, % profitable, combos skipped.
- Warn if winner is at grid boundary.

**Decision logic**:
- If grid winner differs from anchor by >0.5 Calmar: adopt new anchor, return to Step 2 variable sweeps.
- If grid winner is close to anchor (<0.5 Calmar delta): convergence confirmed, proceed to Step 4.

**Progress**: Update the progress file: append a Grid entry to the Grid Sweep Log with winner, delta, and decision. Update Current Anchor if changed. Update Next Action.

## Step 4: Robust Pipeline

Generate `run_{asset}_{session}_vwap_robust_pipeline.py` in `python/scripts/`.

Five phases, each with pass/fail (except DD which is INFO only):

### Phase 1: Structural Validation
Run full-history backtest on the final anchor config using `run_vwap_backtest`.
- PASS: Trades >100, WR >35%, PF >1.2, Calmar >0.5, median stop >= 10 ticks

### Phase 2: Walk-Forward + Stability
Rolling 36m IS / 12m OOS / 12m step. Tight param grid around anchor (3 values per dimension, ~81 combos/fold). Objective: sharpe.

Use `run_walkforward_vwap()` from `orb_backtest.optimize.walkforward_vwap`:
```python
from orb_backtest.optimize.walkforward_vwap import run_walkforward_vwap
```
- Same API as `run_walkforward()` but uses VWAP engine internally.
- Takes `df`, `df_1m`, `base_config` (VWAPStrategyConfig), `param_ranges`, plus `is_months`, `oos_months`, `step_months`.
- Uses 1m magnifier only (1s too large for multiprocessing serialization).
- Print per-fold IS/OOS metrics and best params.
- PASS: WF efficiency >0.5, parameter stability score >=0.4

**Walk-forward param ranges** use session-prefixed names with `with_vwap_overrides`:
```python
# Example for NY session
PARAM_RANGES = {
    "rr": [2.0, 2.5, 3.0],
    "ny_stop_atr_pct": [1.0, 2.0, 3.0],
    "ny_deviation_atr_pct": [20.0, 25.0, 30.0],
    "tp1_ratio": [0.4, 0.5, 0.6],
}
```

### Phase 3: Prop Firm Constraints
Evaluate on WF combined OOS trades.
```python
constraints = PropFirmConstraints(
    max_drawdown_r=999.0,       # DD is NOT a filter
    min_annual_r=12.0,           # configurable per instrument, default 12.0
    max_monthly_loss_r=5.0,
    min_positive_expectancy=True,
)
```
- DD is INFO only -- print but do not gate.
- PASS: Annual R, monthly loss, and expectancy all pass.

### Phase 4: Hold-Out OOS
Test on 2025+ data (never used during optimization).
- PASS: PF >0.9, total R >0, Sharpe >0.5

### Phase 5: Monte Carlo Survival
1000-2000 bootstrap sims on full-history trades. Ruin threshold: -25R.
- PASS: Survival >=60% (minimum), >=85% (strong)

### Verdict
- **GO**: All 5 phases pass.
- **CONDITIONAL**: 4/5 pass.
- **NO-GO**: 3 or fewer pass.

**Progress**: Update the progress file: fill in the Pipeline Result table with each phase's result and key metrics. Record the verdict. Update Next Action.

## Step 5: Save Final Config

If GO or CONDITIONAL: generate `save_{asset}_{session}_vwap_r{N}_final.py` in `python/scripts/`.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.vwap_config import (
    VWAPSessionConfig, VWAPStrategyConfig,
    with_vwap_overrides,
)
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import vwap_results_to_dict, save_backtest_result

# Build final config with name and notes
SESS = VWAPSessionConfig(
    name="{SESSION}",
    ...
)

CONFIG = VWAPStrategyConfig(
    sessions=(SESS,),
    instrument={INSTRUMENT_IMPORT},
    ...,
    name="{INSTRUMENT} {SESSION} VWAP {direction} 2016-2026 Final",
    notes="Post VWAP optimization pipeline. See run_{asset}_{session}_vwap_robust_pipeline.py.",
)

# Run backtest, print metrics, save to DB
trades = run_vwap_backtest(df_5m, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
result = vwap_results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
result_id = save_backtest_result(result)
```

## Step 6: Update Learnings

Open `python/learnings/{SYMBOL}.md` (create from GC.md template if it does not exist).

Add a VWAP strategy section with:
- GO / CONDITIONAL / NO-GO status
- Final config table (all params including session-level)
- Key metrics from each pipeline phase
- List of all scripts generated during the workflow
- DB experiment name from the save step
- Parameter sensitivity notes (which dimensions mattered, which were insensitive)
- Update "what works / what doesn't" sections

**Progress**: Delete `python/{asset}_{session}_vwap_progress.md` -- the learnings doc now has the permanent record. The progress file is no longer needed.

## Script Naming Convention

All generated scripts go in `python/scripts/`:

| Step | Pattern | Example |
|------|---------|---------|
| Baseline | `run_{asset}_{session}_vwap_baseline.py` | `run_nq_ny_vwap_baseline.py` |
| Variable sweeps | `run_{asset}_{session}_vwap_variable_sweeps_{N}.py` | `run_nq_ny_vwap_variable_sweeps_1.py` |
| Grid sweep | `run_{asset}_{session}_vwap_grid_sweep_r{N}.py` | `run_nq_ny_vwap_grid_sweep_r1.py` |
| Robust pipeline | `run_{asset}_{session}_vwap_robust_pipeline.py` | `run_nq_ny_vwap_robust_pipeline.py` |
| Save final | `save_{asset}_{session}_vwap_r{N}_final.py` | `save_nq_ny_vwap_r1_final.py` |

Use lowercase asset and session. Include `vwap` in all script names to distinguish from ORB optimization scripts.

## Key Code Conventions

Every generated script must follow these rules:

1. **sys.path**: `sys.path.insert(0, "src")` at the top (or `Path(__file__).resolve().parent.parent / "src"` for robustness).
2. **START_DATE**: `"2016-01-01"` unless the instrument has less data.
3. **Bar magnifier**: Always enabled (`use_bar_magnifier=True`). Load 1s data via `load_1s_for_5m` (returns `None` if 1s file doesn't exist). The simulator handles the fallback chain: uses 1s if available, else 1m via `load_1m_for_5m`, else 5m only.
4. **DOW filter**: Applied post-backtest via `apply_dow_filter()`, not baked into config.
5. **Config mutation**: Use `dataclasses.replace()` to create variants. For session-level params, rebuild the sessions tuple. Or use `with_vwap_overrides()` for session-prefixed params.
6. **Experiment naming**: Follow `{INSTRUMENT} {SESSION} VWAP {description}` per CLAUDE.md convention.
7. **Negative year tracking**: Exclude the current partial year when counting negative years.
8. **Imports**: Use direct import like `from orb_backtest.data.instruments import ES` (not `get_instrument()`).
9. **Working directory**: Scripts run from `python/` via `cd python && uv run python scripts/{script}.py`.
10. **10-tick minimum stop**: Every generated script must include a `median_stop_ticks()` helper that computes `median(t.risk_points / instrument.min_tick)` for filled trades. Any config with median stop < 10 ticks must be skipped (sweeps/grids) or flagged as FAIL (baseline/pipeline). This is a hard constraint -- no exceptions.
11. **Minimum TP1 ratio 0.2**: Never test or adopt a config with `tp1_ratio < 0.2`. In sweep scripts, skip values below 0.2. In grid sweeps, exclude tp1 values below 0.2 from the grid. This is a hard constraint -- no exceptions.
12. **Progress tracking**: Every optimization maintains a `python/{asset}_{session}_vwap_progress.md` file. Read it at the start of every step. Update it after every significant result. Delete it after Step 6. This file survives context compaction and is the single source of truth for workflow state.

## VWAP-Specific Config Reference

### VWAPSessionConfig fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | str | (required) | "NY", "Asia", "LDN" |
| `vwap_anchor` | str | "session" | Always session-anchored |
| `session_open` | str | "" | Session data start (for cross-midnight sessions) |
| `entry_start` | str | "09:35" | Entry window open |
| `entry_end` | str | "12:00" | Entry window close |
| `flat_start` | str | "15:50" | Flatten positions |
| `flat_end` | str | "16:00" | Session close |
| `deviation_atr_pct` | float | 30.0 | Deviation threshold as % of daily ATR (mode="atr") |
| `deviation_std` | float | 2.0 | Std dev multiplier for bands (mode="std") |
| `deviation_mode` | str | "atr" | "atr" or "std" |
| `rejection_mode` | str | "close" | "close" or "pinbar" |
| `stop_atr_pct` | float | 0.0 | Stop buffer as % of daily ATR beyond rejection candle |
| `min_wick_atr_pct` | float | 0.0 | Pinbar min wick length as % of ATR |
| `max_body_atr_pct` | float | 0.0 | Pinbar max body size as % of ATR |
| `min_stop_points` | float | 0.0 | Minimum stop distance in points (0 = disabled) |
| `min_tp1_points` | float | 0.0 | Minimum TP1 distance in points (0 = disabled) |

### VWAPStrategyConfig fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `risk_usd` | float | 5000.0 | Risk per trade in USD |
| `rr` | float | 2.5 | Risk-reward ratio |
| `tp1_ratio` | float | 0.5 | Fraction taken at first take-profit |
| `min_qty` | float | 1.0 | Minimum position size |
| `qty_step` | float | 1.0 | Position size increment |
| `atr_length` | int | 14 | ATR lookback period |
| `tp2_mode` | str | "fixed_rr" | "fixed_rr" or "vwap" |
| `sessions` | tuple | () | Tuple of VWAPSessionConfig |
| `instrument` | Instrument | None | Instrument definition |
| `half_days` | tuple | () | Half-day dates (YYYYMMDD) |
| `excluded_dates` | tuple | () | Excluded dates (YYYYMMDD) |
| `direction_filter` | str | "both" | "both", "long", or "short" |
| `use_bar_magnifier` | bool | True | Use 1m sub-bars for fill simulation |
| `name` | str | "" | Experiment name |
| `notes` | str | "" | Experiment notes |

### Default Session Configs

**NY** (`NY_VWAP_SESSION`):
- session_open: 09:30, entry_start: 09:35, entry_end: 12:00, flat_start: 15:50, flat_end: 16:00
- deviation_atr_pct: 30.0, deviation_std: 2.0, deviation_mode: "atr"
- rejection_mode: "close", stop_atr_pct: 0.0
- Timezone: America/New_York

**Asia** (`ASIA_VWAP_SESSION`):
- session_open: 20:00, entry_start: 20:15, entry_end: 23:15, flat_start: 06:45, flat_end: 07:00
- deviation_atr_pct: 25.0, deviation_std: 2.0, deviation_mode: "atr"
- rejection_mode: "close", stop_atr_pct: 0.0
- Timezone: America/New_York (crosses midnight)

**LDN** (`LDN_VWAP_SESSION`):
- session_open: 03:00, entry_start: 03:15, entry_end: 08:20, flat_start: 08:20, flat_end: 08:25
- deviation_atr_pct: 25.0, deviation_std: 2.0, deviation_mode: "atr"
- rejection_mode: "close", stop_atr_pct: 0.0
- Timezone: America/New_York

### Session-Appropriate Sweep Values

**NY session** (entry from 09:35):
- entry_end: `["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "14:00", "15:00"]`
- flat_start: `["13:00", "14:00", "14:30", "15:00", "15:30", "15:50"]`

**Asia session** (entry from 20:15, crosses midnight):
- entry_end: `["21:30", "22:00", "23:00", "23:15", "00:00", "01:00", "02:00"]`
- flat_start: `["04:00", "05:00", "06:00", "06:30", "06:45"]`

**LDN session** (entry from 03:15):
- entry_end: `["04:30", "05:00", "06:00", "07:00", "08:00", "08:20"]`
- flat_start: `["07:00", "07:30", "08:00", "08:20"]`

## Key Functions and Imports

### Backtest Engine
```python
from orb_backtest.engine.vwap_simulator import run_vwap_backtest

trades = run_vwap_backtest(
    df_5m, config,
    start_date=START_DATE,
    df_1m=df_1m,
    df_1s=df_1s,
)
```

### Config Construction
```python
from orb_backtest.vwap_config import (
    VWAPSessionConfig, VWAPStrategyConfig,
    NY_VWAP_SESSION, ASIA_VWAP_SESSION, LDN_VWAP_SESSION,
    with_vwap_overrides, default_vwap_config,
)
from dataclasses import replace

# Create from defaults
config = default_vwap_config(INSTRUMENT)

# Override specific params
config = with_vwap_overrides(config, rr=3.0, ny_deviation_atr_pct=25.0)

# Or build manually
sess = VWAPSessionConfig(name="NY", entry_start="09:35", entry_end="12:00", ...)
config = VWAPStrategyConfig(sessions=(sess,), instrument=INSTRUMENT, rr=2.5, ...)
```

### Results Export
```python
from orb_backtest.results.export import vwap_results_to_dict, save_backtest_result

result = vwap_results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
result_id = save_backtest_result(result)
```

### Post-Backtest Filters
```python
from orb_backtest.analysis.gates import (
    apply_dow_filter,
    apply_weekly_loss_cap,
    apply_monthly_loss_cap,
)

# Filter order: DOW -> Weekly cap -> Monthly cap
if dow_excl:
    trades = apply_dow_filter(trades, dow_excl)
if weekly_cap > 0:
    trades = apply_weekly_loss_cap(trades, cap_r=weekly_cap)
if monthly_cap > 0:
    trades = apply_monthly_loss_cap(trades, cap_r=monthly_cap)
```

### Parallel Grid Sweep
```python
from orb_backtest.optimize.parallel_vwap import run_vwap_sweep
# For large grids, use run_vwap_sweep for parallel execution
```

### Walk-Forward
```python
from orb_backtest.optimize.walkforward_vwap import run_walkforward_vwap
# VWAP counterpart to run_walkforward -- same API but uses VWAP engine
```

## Dimensions NOT Swept (ORB-specific, not applicable to VWAP)

These dimensions exist in the ORB orb-optimization skill but are **not present** in the VWAP strategy and must NOT be included in VWAP sweeps:

| ORB Dimension | Why excluded |
|---------------|-------------|
| ORB window (orb_start/orb_end) | No opening range in VWAP strategy |
| Stop method (ATR vs ORB%) | VWAP uses stop_atr_pct buffer only (no ORB range) |
| Min gap ATR % (min_gap_atr_pct) | No FVG detection in VWAP strategy |
| Max gap points (max_gap_points) | No FVG detection in VWAP strategy |
| Max gap ATR % (max_gap_atr_pct) | No FVG detection in VWAP strategy |
| ICF (impulse_close_filter) | No FVG impulse candle in VWAP strategy |
| SMA Trend Gate | Not implemented for VWAP (could be added later) |
| Qualifying Move | Inversion-only ORB concept; not applicable |

## Relationship to Other Skills

This skill is the VWAP counterpart to `orb-optimization`. It shares the same workflow structure but uses entirely different config classes, engine functions, and sweep dimensions.

| Skill | Role | When to load |
|-------|------|-------------|
| `orb-optimization` | ORB-specific optimization workflow | Reference for workflow structure only |
| `discovery-pipeline` | Detailed phase documentation, prop constraint thresholds | For prop constraint reference |
| Instrument-specific (e.g., `gc-optimization`) | Hardcoded constraints, known pitfalls | When that instrument is being optimized |

All existing skills remain independently usable. This skill provides the sequencing and decision logic for VWAP strategy optimization.
