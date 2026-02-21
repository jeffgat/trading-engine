---
name: multi-phase-backtest
description: >
  Run structured multi-phase prop firm optimization workflow per instrument.
  Four phases + optional refinement: (1) structural exploration, (2) adaptive walk-forward optimization,
  (2.5) optional Bayesian refinement, (3) Monte Carlo stress test, (4) recency analysis.
  Use when the user says "multi-phase backtest", "run all phases", "optimize my strategy",
  "full optimization workflow", "prop firm test", or references testing across sessions/instruments
  systematically. Also triggers on "phase 1", "phase 2", etc. when referring to strategy optimization.
---

# Optimized Prop Firm Test Flow

Systematic 4-phase strategy optimization designed for prop firm constraints. Each phase builds on the previous. **Run per instrument** (NQ, YM, ES, CL, etc.).

## Primary Objective: Calmar

**Calmar ratio (Avg Annual R ÷ |Max DD R|) is the primary optimization metric — always rank by Calmar first.**

Absolute drawdown in R is NOT a hard filter. Position sizing handles dollar DD. A strategy with -15R DD and 15 R/yr (Calmar 1.0) is identical in practice to -10R DD and 10 R/yr — just trade at 2/3 size. What can't be fixed by sizing is a low Calmar.

**Optimization priority order:**
1. **Calmar** — primary objective, always
2. **0 negative full years** — consistency
3. **Sharpe** — secondary; walk-forward objective
4. **Net R / Avg Annual R** — only meaningful as Calmar

## Prop Firm Sizing Reference

These thresholds inform position sizing, not go/no-go decisions during optimization.

| Reference | Value | Purpose |
|-----------|-------|---------|
| Typical prop DD ceiling | 8-12R | Use to compute position size from strategy DD |
| Annual profit target | 24R+/year | Benchmark for trade worthiness |
| DD gate (WF sweep) | -12R (reject worse) | Keeps IS configs from being wildly bad |
| Ruin threshold (MC) | -8R | Dollar-scaled breach threshold |

## Before Starting

Ask the user for:
1. **Data file** and **instrument** (e.g., `NQ_5m.csv`, `NQ`)
2. **Date range** — use full dataset (~10 years) for phases 1-2
3. **Sessions** to test (any combination of `NY`, `Asia`, `LDN`)
4. **Strategy type** (`continuation` or `reversal`, default: continuation)

All commands run from `python/` directory using `uv run python scripts/core/<script>.py`.

---

## Variable Sweep Discipline — CRITICAL RULE

**Every time the anchor config changes, ALL variable sweeps must be rerun from scratch.**

Parameter sensitivities are anchor-dependent. A dimension that appears insensitive at one anchor may be highly impactful at another. Never carry forward sweep results from a different anchor.

### The sweep-and-grid loop

1. **Set anchor** — from structural exploration or previous iteration
2. **Variable sweeps** — sweep each dimension independently, all others fixed at anchor:
   - Structural: ORB window, ATR length, entry_end, flat_start, direction, DOW exclusion
   - Filters: max_gap_points, max_gap_atr_pct
3. **Update anchor** — adopt best value from each sweep
4. **Anchor changed?** → go back to step 2 (re-sweep everything on new anchor)
5. **Fine-tune** — sweep most impactful dimensions at higher resolution
6. **Grid sweep** — sweep continuous params together (stop × rr × min_gap × tp1)
7. **Anchor changed again?** → go back to step 2
8. **Only then run the robust pipeline** — WF + prop constraints + holdout + MC

Scripts: `run_{asset}_variable_sweeps_{N}.py`, incrementing N with each anchor change.

---

## Phase 1: Structural Exploration (full dataset)

Decide the **categorical/discrete** choices that define the strategy variant. These have low overfitting risk because they're not continuous parameters.

### What to decide
- Which sessions? (NY, Asia, NY+Asia)
- Strategy type? (continuation vs reversal)
- Direction filter? (both, long-only, short-only)
- Flat time sensitivity? (sweep flat_start across 3-5 values)

### How to run

Run quick single-param sweeps on the **full dataset**. Compare Calmar/Sharpe/DD across variants.

```bash
# Session comparison
uv run python scripts/run_backtest.py --data {DATA} --sessions NY \
  --name "{INSTRUMENT} NY Structural Baseline"
uv run python scripts/run_backtest.py --data {DATA} --sessions Asia \
  --name "{INSTRUMENT} Asia Structural Baseline"
uv run python scripts/run_backtest.py --data {DATA} --sessions NY,Asia \
  --name "{INSTRUMENT} NY+Asia Structural Baseline"

# Direction filter comparison
uv run python scripts/run_backtest.py --data {DATA} --sessions {SESSIONS} --direction long \
  --name "{INSTRUMENT} {SESSIONS} Long Only"
uv run python scripts/run_backtest.py --data {DATA} --sessions {SESSIONS} --direction short \
  --name "{INSTRUMENT} {SESSIONS} Short Only"
```

Run all variants **in parallel**. Pick the structural config based on Calmar, Sharpe, and DD.

### Pass criteria
- At least one variant shows positive total R
- Max DD below 12R
- Enough trades for statistical significance (100+ per session)

---

## Phase 2: Walk-Forward Optimization (full dataset, adaptive)

This IS the core optimization — not a validation step. **Re-optimizes params per fold** instead of testing a fixed config.

### Key settings
- **Window**: 12m IS / 3m OOS / 3m step, rolling (~35 folds over 10 years)
- **Sweep per fold**: 2-3 core params — `rr`, `stop_atr_pct`, `min_gap_atr_pct`
- **Objective**: `calmar` (directly targets return/DD ratio)
- **DD hard gate**: `--max-dd-r -12.0` rejects any IS config with DD worse than 12R

Each fold picks its own best config. OOS trades are genuinely unseen. Combined OOS = expected live performance estimate.

```bash
uv run python scripts/core/run_walkforward.py --data {DATA} \
  --start {START} --end {END} \
  --instrument {INSTRUMENT} --sessions {SESSIONS} \
  --sweep rr=2.0:4.0:0.5 \
  --sweep {prefix}_stop_atr_pct=4:15:1 \
  --sweep {prefix}_min_gap_atr_pct=1.0:3.0:0.5 \
  --is-months 12 --oos-months 3 --step-months 3 \
  --objective calmar --max-dd-r -12.0 \
  --workers 8 \
  --name "{INSTRUMENT} {SESSIONS} WF Calmar DD-gated"
```

### What to check
- **WF efficiency** > 0.5 = stable, tradeable
- **WF efficiency** 0.3-0.5 = marginal
- **WF efficiency** < 0.3 = overfit
- Per-fold params should vary (proving adaptive re-optimization works)
- Combined OOS should meet prop targets: 24R+/year, max DD < 12R
- Recency analysis (auto-printed) should show no degradation

### Pass criteria
- WF efficiency > 0.3
- Combined OOS annual R > 24R
- Combined OOS max DD better than -12R
- No degradation flag in recency analysis

---

## Phase 2.5 (Optional): Bayesian Refinement

After WF identifies which param region works across most folds, optionally fine-tune within that region.

### When to use
- Only if WF param selections **cluster tightly** (indicating a stable optimum worth refining)
- Skip if params drift across folds (indicates no stable optimum exists)
- Check the "Param Stability" section in the recency analysis output

### How to run

Narrow the search to +/-20% of the WF-dominant param values. Run on the most recent 3-5 years (not the full dataset).

```bash
uv run python scripts/core/run_bayesian.py --data {DATA} \
  --start {RECENT_START} --end {END} \
  --instrument {INSTRUMENT} --sessions {SESSIONS} \
  --param rr={LOW}:{HIGH}:{STEP} \
  --param {prefix}_stop_atr_pct={LOW}:{HIGH}:{STEP} \
  --param {prefix}_min_gap_atr_pct={LOW}:{HIGH}:{STEP} \
  --n-trials 200 --objective calmar --sampler tpe --seed 42 \
  --name "{INSTRUMENT} {SESSIONS} Bayesian Refinement"
```

Compare refined config vs WF-selected configs via a fresh OOS test on held-out data.

---

## Phase 3: Monte Carlo Stress Test (on combined OOS trades)

Run on the WF combined OOS trades only (not pre-optimized data). The `run_walkforward.py` script runs MC automatically with `--mc-sims` (default: 10000).

### What MC checks
- 10k bootstrap paths
- Ruin thresholds at -8R (prop breach) and -12R (hard ceiling)
- p25 annualized R meets 24R/year target
- Ruin probability < 5% at -8R

If you need to run MC separately (e.g., on a saved result):

```bash
uv run python scripts/core/run_monte_carlo.py --result {RESULT_ID} \
  --method bootstrap --sims 10000 --seed 42 \
  --ruin-threshold -8.0
```

### Pass criteria
- Ruin probability < 5% at -8R
- p25 final R > 0
- p75 max DD better than -8R

---

## Phase 4: Recency Analysis

Automatically printed by `run_walkforward.py` when there are 4+ folds. Extracts the last 4-8 OOS folds and computes separate metrics.

### What it checks
- Recent OOS Calmar/Sharpe vs historical average
- Param stability (std dev of each swept param across recent folds)
- Degradation flag: fires if recent Calmar < 50% of historical

### Pass criteria
- No degradation flag
- Recent Calmar within 50% of historical
- Param selections not wildly different fold-to-fold (low std dev)

---

## Decision Framework

After all phases, summarize with this table:

| Check | Threshold | Result |
|-------|-----------|--------|
| WF Efficiency | > 0.3 | |
| OOS Calmar | > 1.0 | |
| OOS Annual R | > 24R/year | |
| OOS Max DD | Report (sizing input) | |
| MC Ruin Prob (-8R) | < 5% | |
| MC p75 Max DD | > -8R | |
| Recency Degradation | No flag | |
| Param Stability | Low std dev | |

**GO**: WF efficiency > 0.3, OOS Calmar > 1.0, MC ruin < 5%, no recency degradation
**CAUTION**: Calmar 0.5-1.0, or MC ruin 5-15% — trade with reduced size
**NO-GO**: WF efficiency < 0.3, Calmar < 0.5, or MC ruin > 15%

Note: OOS Max DD is reported for position sizing purposes, not as a pass/fail gate. A strategy with Calmar > 1.0 but DD > 12R is still viable — reduce position size so the dollar DD fits your account.

## Execution Notes

- Run sessions in parallel when possible
- All results auto-save to the experiment DB and are viewable in the frontend dashboard
- Use `--name` labels consistently for identification (see naming convention in CLAUDE.md)
- Objectives: `calmar` (recommended for prop), `sharpe`, `pnl`, `profit_factor`, `avg_r`
- See [cli-reference.md](references/cli-reference.md) for full argument details
