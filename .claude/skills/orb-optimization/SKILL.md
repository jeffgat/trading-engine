---
triggers:
  - "optimize {instrument}"
  - "full optimization"
  - "end-to-end optimization"
  - "fresh optimization"
  - "start from scratch on {instrument}"
  - "baseline to pipeline"
---

# Full Optimization

Six-step end-to-end workflow that takes an instrument from baseline through validated, prop-firm-ready strategy. Generates runnable Python scripts at each step.

**Steps**: (1) Baseline, (2) Variable Sweeps, (3) Grid Sweep, (4) Robust Pipeline, (5) Save Final Config, (6) Update Learnings.

Orchestrates `multi-phase-backtest` sweep discipline with `discovery-pipeline` validation. Calmar ratio is the primary optimization objective. DD is NOT a hard filter -- set `max_drawdown_r=999.0` everywhere.

**HARD CONSTRAINT — 10-Tick Minimum Stop**: Never test, adopt, or save a config where the median stop is less than 10 ticks. Stops below 10 ticks are unrealistic — slippage eats the edge. Compute as `median(t.risk_points / instrument.tick_size for filled trades)`. Skip and print `SKIP (median stop < 10 ticks)` for any variant that fails this check. This applies at EVERY step: baseline, sweeps, grid, pipeline, and save.

**HARD CONSTRAINT — Minimum TP1 Ratio 0.2**: Never test, adopt, or save a config with `tp1_ratio < 0.2`. A TP1 ratio below 0.2 takes too little off the table at the first target, leaving nearly all risk on for the full R:R move. Skip and print `SKIP (tp1_ratio < 0.2)` for any variant that fails this check. This applies at EVERY step: sweeps, grid, and save.

## Before Starting

Gather from the user:
1. **Instrument** symbol (NQ, ES, GC, CL, YM, RTY, 6B)
2. **Session** (NY, ASIA, LDN)
3. **Strategy type** (continuation or reversal)
4. **Direction hint** (longs, shorts, or both)

Then verify:
- Read `python/learnings/{SYMBOL}.md` -- if the same strategy/session/direction combo is already NO-GO, stop and inform the user. Only proceed if they have a fundamentally different approach.
- Confirm data files exist: `{SYMBOL}_5m.csv` (required), `{SYMBOL}_1m.csv` (magnifier), `{SYMBOL}_1s.parquet` (optional, preferred magnifier).
- Check if an instrument-specific skill exists (e.g., `gc-optimization`, `nq-ny-optimization`) and load it for hardcoded constraints or known pitfalls.
- Determine `START_DATE` -- default `2016-01-01` unless the instrument has less data.
- Compute `DATA_YEARS` from start to current date (used for R/yr calculation).
- Query the experiment DB for existing names with the same instrument/session prefix to avoid duplicates (per CLAUDE.md naming convention).

## Progress Tracking (CRITICAL — survives context compaction)

Maintain a temporary file `python/{asset}_{session}_progress.md` throughout the workflow. This file is the single source of truth for workflow state and survives context compaction.

- **Create** it at the start of Step 1 using `references/progress-template.md`.
- **Read it first** at the beginning of every step — if context was compacted, this file tells you exactly where you are and what to do next.
- **Update it** after every significant result: baseline metrics, each sweep round (adoptions + new anchor), grid sweep winner, pipeline phase results.
- **Delete it** after Step 6 completes — the learnings doc now has the permanent record.

If you find an existing progress file when starting, **resume from where it left off** rather than starting over. The "Next Action" section tells you exactly what to do.

## Step 1: Baseline

Generate `run_{asset}_{session}_baseline.py` in `python/scripts/`.

Use the instrument's default `SessionConfig` times and standard StrategyConfig defaults. Run a single backtest on the full date range.

```python
# Key structure -- always include
import sys
sys.path.insert(0, "src")

from dataclasses import replace
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}  # e.g. ES, NQ, GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = {INSTRUMENT_IMPORT}  # direct import, e.g. INSTRUMENT = ES
START_DATE = "2016-01-01"
# Load df_5m, df_1m, df_1s
# Build SessionConfig + StrategyConfig with defaults
# Run backtest, compute metrics, print results + R by year
```

**Pass criteria**: >100 trades AND profit factor >1.0 AND median stop >= 10 ticks.
- FAIL: Record as NO-GO in learnings, stop workflow.
- PASS: This becomes the initial anchor config for Step 2.
- Also print median stop in ticks for the baseline — this is the sanity check before sweeps begin.

**Progress**: Create `python/{asset}_{session}_progress.md` from `references/progress-template.md`. Record baseline metrics, anchor config, and set Next Action to "Run variable sweeps R1".

**Experiment name**: `{INSTRUMENT} {SESSION} Baseline`

## Step 2: Variable Sweeps

Generate `run_{asset}_{session}_variable_sweeps_{N}.py` in `python/scripts/`. N starts at 1 and increments each round.

Variable sweeps are split into two phases. Analysis of 30+ sweep rounds across NQ, ES, and GC showed that only 3 dimensions (Stop × RR × TP1) form a feedback loop requiring iterative convergence. The other 13 are largely independent — changes never trigger re-adoptions in other dimensions.

### Step 2a: Stand-Alone Sweeps (single pass, no re-sweep)

Sweep 13 dimensions once, in this order. Adopt any that pass the threshold. No re-sweeping — these are decided once and feed into the core loop as fixed context.

| # | Dimension | Config field | Typical values | Why stand-alone |
|---|-----------|-------------|----------------|-----------------|
| 1 | Direction | `direction_filter` | both, long, short | One-time structural choice; never flips back once adopted |
| 2 | Stop method | ATR vs ORB% | Tests alternative stop method to anchor | Structural — decides how stops scale; one-time decision |
| 3 | ORB window | `orb_start/orb_end/entry_start` | 5m, 10m, 15m, 20m, 25m, 30m, 45m | Structural; weak cascade to entry end only |
| 4 | Entry end time | `entry_end` | Session-appropriate times (NY: 11:00-15:30) | Session boundary; no cascade to core params |
| 5 | Flat time | `flat_start` | Session-appropriate times | Session boundary; no cascade |
| 6 | ATR length | `atr_length` | 5, 7, 10, 14, 20, 30 | Major lever for GC (+5.76 Calmar); decisive for NQ Asia/ES Asia (ATR 5); always test |
| 7 | Min gap ATR % | `min_gap_atr_pct` | 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0 | Filter layer; orthogonal to stop/RR/TP1 risk engine |
| 8 | DOW exclusion | post-backtest filter | none, Mon, Tue, Wed, Thu, Fri, M+F, Th+F | Post-filter; no cascade; data-mining risk |
| 9 | ICF | `impulse_close_filter` | True, False | Binary; context-dependent — adopted at +2.72 on NQ Asia, harmful on NQ NY shorts |
| 10 | SMA Trend Gate | `apply_sma_trend_gate(trades, df_5m, sma_period)` | OFF, 10, 20, 50, 100, 200 | Post-trade filter; independent of core risk engine |
| 11 | Qualifying Move | `qualifying_move_atr_pct` on SessionConfig | 0 (off), 25, 50, 75, 100, 150, 200 | **Inversion only** — skip for continuation/reversal |
| 12 | Weekly Loss Cap | `apply_weekly_loss_cap(trades, cap_r)` | OFF, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0 | Order-sensitive risk overlay; apply after DOW+SMA filters |
| 13 | Monthly Loss Cap | `apply_monthly_loss_cap(trades, cap_r)` | OFF, 3.0, 5.0, 7.0, 10.0, 15.0 | Order-sensitive risk overlay; apply after DOW+SMA filters |

After the stand-alone pass completes, update the anchor with any adoptions. This becomes the fixed context for the core convergence loop.

### Step 2b: Core Convergence Loop (iterative re-sweep)

Sweep 3 core dimensions iteratively until convergence (0 adoptions in a full pass):

| # | Dimension | Config field | Typical values | Why core |
|---|-----------|-------------|----------------|----------|
| 1 | Stop size | `stop_atr_pct` or `stop_orb_pct` | ATR: 1.0–15.0% / ORB: 25–200% | PRIMARY cascade driver — changes force RR + TP1 re-evaluation |
| 2 | R:R ratio | `rr` | 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0 | Tightly coupled to stop; re-adopted after every significant stop change |
| 3 | TP1 ratio | `tp1_ratio` | 0.2, 0.3, 0.4, 0.5, 0.6, 0.7 (min 0.2 — hard constraint) | Weakly coupled to RR; adjusts after RR shifts |

**Convergence**: Typically 2-3 rounds (vs 5-11 rounds when all 16 dims are re-swept). The stop-RR-TP1 loop is the only one that actually oscillates.

### Sweep Script Requirements

Each script must:
- Print a formatted table per dimension with: Trades, WR, PF, Sharpe, Net R, R/yr, MaxDD, Calmar.
- Print R by year for key comparisons.
- Track `neg_year_set()` -- negative full calendar years (exclude current partial year).
- Print a summary table at the end showing the best value per dimension and whether to adopt.

**Adoption rule**: Calmar delta > +0.3 AND no new negative full years AND trade count stays >100 AND median stop >= 10 ticks.

**Convergence logic**:
- **Stand-alone (Step 2a)**: Single pass (13 dims). Adopt qualifying dims. Update anchor. Move to Step 2b.
- **Core (Step 2b)**: If any of the 3 core dims is adopted, update anchor, increment N, re-sweep only the 3 core dims. Converged when 0 core adoptions in a full pass.
- On convergence, print "Ready for grid sweep."

**Script naming**: Stand-alone pass uses `_variable_sweeps_1.py`. Core rounds use `_variable_sweeps_2.py`, `_variable_sweeps_3.py`, etc. (N increments each core round).

**DOW filter**: Applied post-backtest via `apply_dow_filter()`, not in config.

**SMA trend gate**: Applied post-backtest via `apply_sma_trend_gate()` from `gates.py`. Needs `df_5m`.

**Qualifying move**: Uses `run_backtest_qm()` from `orb_backtest.engine.qualifying_move` instead of `run_backtest()`. Only applies to `strategy="inversion"` — skip for continuation/reversal.

**Loss caps (weekly/monthly)**: Applied post-backtest via `apply_weekly_loss_cap()` / `apply_monthly_loss_cap()` from `gates.py`. Order-sensitive — apply LAST in the filter chain (after DOW and SMA filters).

**Progress**: After each pass/round completes, update the progress file: append a Stand-alone or Core Round entry to the Adoption Log with entering/exiting anchor and adoptions. Update Current Anchor Config/Metrics tables. Update Next Action. Add the sweep script to Scripts Generated.

**Experiment name**: Not saved to DB (these are diagnostic sweeps printed to stdout).

## Step 3: Grid Sweep

Generate `run_{asset}_{session}_grid_sweep_r{N}.py` in `python/scripts/`.

4D grid over continuous parameters, using narrow ranges around the converged anchor:

```python
STOP_VALUES = [anchor-1, anchor-0.5, anchor, anchor+0.5, anchor+1]  # ~4-5 values
RR_VALUES   = [anchor-1, anchor-0.5, anchor, anchor+0.5, anchor+1]  # ~5-6 values
GAP_VALUES  = [anchor-1, anchor-0.5, anchor, anchor+0.5]            # ~4-5 values
TP1_VALUES  = [anchor-0.1, anchor-0.05, anchor, anchor+0.05, anchor+0.1]  # ~5-6 values
```

Target: 200-600 total combos.

Each script must:
- Iterate all combos, run backtest, compute metrics.
- **Skip combos where median stop < 10 ticks** (10-tick minimum stop rule).
- Print progress every 50 combos (elapsed time, rate, ETA).
- Print Top 20 by Calmar (all combos).
- Print Top 20 by Calmar (0 negative full years only).
- Print grid summary: total combos, % with 0 neg years, % profitable, combos skipped for <10 tick stop.

**Decision logic**:
- If grid winner differs from anchor by >0.5 Calmar: adopt new anchor, return to Step 2 variable sweeps.
- If grid winner is close to anchor (<0.5 Calmar delta): convergence confirmed, proceed to Step 4.

**Progress**: Update the progress file: append a Grid entry to the Grid Sweep Log with winner, delta, and decision. Update Current Anchor if changed. Update Next Action.

## Step 4: Robust Pipeline

Generate `run_{asset}_{session}_robust_pipeline.py` in `python/scripts/`.

Five phases, each with pass/fail (except DD which is INFO only):

### Phase 1: Structural Validation
Run full-history backtest on the final anchor config.
- PASS: Trades >100, WR >35%, PF >1.2, Calmar >0.5, median stop >= 10 ticks

### Phase 2: Walk-Forward + Stability
Rolling 36m IS / 12m OOS / 12m step. Tight param grid around anchor (3 values per dimension, ~81 combos/fold). Objective: sharpe.
- Uses 1m magnifier only (1s too large for multiprocessing serialization).
- Print per-fold IS/OOS metrics and best params.
- PASS: WF efficiency >0.5, parameter stability score >=0.4

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

If GO or CONDITIONAL: generate `save_{asset}_{session}_r{N}_final.py` in `python/scripts/`.

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import {INSTRUMENT_IMPORT}  # e.g. ES, NQ, GC
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

# Build final config with name and notes
CONFIG = StrategyConfig(
    ...,
    name="{INSTRUMENT} {SESSION} {strategy} {direction} 2016-2026 Final",
    notes="Post orb-optimization pipeline. See run_{asset}_{session}_robust_pipeline.py.",
)

# Run backtest, print metrics, save to DB
result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
result_id = save_backtest_result(result)
```

## Step 6: Update Learnings

Open `python/learnings/{SYMBOL}.md` (create from GC.md template if it does not exist).

Add a strategy section with:
- GO / CONDITIONAL / NO-GO status
- Final config table (all params)
- Key metrics from each pipeline phase
- List of all scripts generated during the workflow
- DB experiment name from the save step
- Parameter sensitivity notes (which dimensions mattered, which were insensitive)
- Update "what works / what doesn't" sections

**Progress**: Delete `python/{asset}_{session}_progress.md` — the learnings doc now has the permanent record. The progress file is no longer needed.

## Script Naming Convention

All generated scripts go in `python/scripts/`:

| Step | Pattern | Example |
|------|---------|---------|
| Baseline | `run_{asset}_{session}_baseline.py` | `run_es_ny_baseline.py` |
| Variable sweeps | `run_{asset}_{session}_variable_sweeps_{N}.py` | `run_es_ny_variable_sweeps_1.py` |
| Grid sweep | `run_{asset}_{session}_grid_sweep_r{N}.py` | `run_es_ny_grid_sweep_r1.py` |
| Robust pipeline | `run_{asset}_{session}_robust_pipeline.py` | `run_es_ny_robust_pipeline.py` |
| Save final | `save_{asset}_{session}_r{N}_final.py` | `save_es_ny_r1_final.py` |

Use lowercase asset and session. For multi-word strategies, use underscores: `run_gc_cont_long_variable_sweeps_1.py`.

## Key Code Conventions

Every generated script must follow these rules:

1. **sys.path**: `sys.path.insert(0, "src")` at the top (or `Path(__file__).resolve().parent.parent / "src"` for robustness).
2. **START_DATE**: `"2016-01-01"` unless the instrument has less data.
3. **Bar magnifier**: Always enabled (`use_bar_magnifier=True`). Load 1s data via `load_1s_for_5m` (returns `None` if 1s file doesn't exist). The *simulator* handles the fallback chain: uses 1s if available, else 1m via `load_1m_for_5m`, else 5m only.
4. **DOW filter**: Applied post-backtest via `apply_dow_filter()`, not baked into config.
5. **Config mutation**: Use `dataclasses.replace()` to create variants, never direct assignment on frozen dataclasses.
6. **Experiment naming**: Follow `{INSTRUMENT} {SESSION} {description}` per CLAUDE.md convention.
7. **Negative year tracking**: Exclude the current partial year when counting negative years.
8. **Imports**: Use direct import like `from orb_backtest.data.instruments import ES` (not `get_instrument()`).
9. **Working directory**: Scripts run from `python/` via `cd python && uv run python scripts/{script}.py`.
10. **10-tick minimum stop**: Every generated script must include a `median_stop_ticks()` helper that computes `median(t.risk_points / instrument.tick_size)` for filled trades. Any config with median stop < 10 ticks must be skipped (sweeps/grids) or flagged as FAIL (baseline/pipeline). This is a hard constraint — no exceptions.
11. **Minimum TP1 ratio 0.2**: Never test or adopt a config with `tp1_ratio < 0.2`. In sweep scripts, skip values below 0.2. In grid sweeps, exclude tp1 values below 0.2 from the grid. This is a hard constraint — no exceptions.
12. **Progress tracking**: Every optimization maintains a `python/{asset}_{session}_progress.md` file. Read it at the start of every step. Update it after every significant result. Delete it after Step 6. This file survives context compaction and is the single source of truth for workflow state.

## Relationship to Other Skills

This skill orchestrates but does NOT replace:

| Skill | Role | When to load |
|-------|------|-------------|
| `multi-phase-backtest` | Sweep discipline theory, variable sweep methodology | For sweep-and-grid loop details |
| `discovery-pipeline` | Detailed phase documentation, prop constraint thresholds | For `references/phases.md` and `references/prop-constraints.md` |
| `strategy-optimizer` | Individual optimization tasks, parameter guide | For `references/parameter-guide.md` |
| Instrument-specific (e.g., `gc-optimization`) | Hardcoded constraints, known pitfalls | When that instrument is being optimized |

All existing skills remain independently usable. This skill provides the sequencing and decision logic that ties them together.
