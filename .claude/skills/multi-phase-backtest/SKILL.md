---
name: multi-phase-backtest
description: >
  Run structured multi-phase strategy optimization workflow across trading sessions and instruments.
  Five phases - (1) baseline backtests, (2) grid sweep parameter optimization, (3) Bayesian refinement,
  (4) walk-forward validation, (5) Monte Carlo stress testing. Use when the user says "multi-phase backtest",
  "run all phases", "optimize my strategy", "full optimization workflow", or references testing across
  multiple sessions/instruments systematically. Also triggers on "phase 1", "phase 2", etc. when referring
  to strategy optimization.
---

# Multi-Phase Backtest Workflow

Systematic 5-phase strategy optimization. Each phase builds on the previous.

## Before Starting

Ask the user for:
1. **Data file** and **instrument** (e.g., `NQ_5m.csv`, `NQ`)
2. **Date range** (`--start`, `--end`)
3. **Sessions** to test (any combination of `NY`, `Asia`, `LDN`)
4. **Strategy type** (`continuation` or `reversal`, default: continuation)

All commands run from `python/` directory using `uv run python scripts/<script>.py`.

## Phase 1: Baseline Backtests

Run one backtest per session with default parameters. This is the benchmark.

```bash
uv run python scripts/run_backtest.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} --name "{SESSION} Baseline"
```

Run all sessions **in parallel**. Record each session's Sharpe, PnL, win rate, max drawdown.

## Phase 2: Grid Sweep (Coarse Discovery)

**3 rounds per session** (e.g., 9 sweeps for 3 sessions). All 9 can run in parallel.

**Ask the user** which parameters to sweep and their ranges before running. Present the suggested defaults below but let them customize. Session-specific params use prefixes: `ny_`, `asia_`, `ldn_`.

### Round 1 — Entry Filters
Controls *which* trades are taken. These interact, sweep together.

```bash
uv run python scripts/run_optimize.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} \
  --sweep {prefix}_min_gap_atr_pct=0.5:3.0:0.25 \
  --sweep {prefix}_max_gap_atr_pct=25:200:25 \
  --name "{SESSION} R1 Entry Filters"
```

### Round 2 — Risk/Reward
Controls *how* trades are managed. These interact, sweep together.

```bash
uv run python scripts/run_optimize.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} \
  --sweep {prefix}_stop_atr_pct=5:15:1 \
  --sweep rr=1.5:4.0:0.5 \
  --name "{SESSION} R2 Risk Reward"
```

### Round 3 — Exit Management
Fine-tuning. Only matters once entries and R:R are good.

```bash
uv run python scripts/run_optimize.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} \
  --sweep tp1_ratio=0.3:0.7:0.1 \
  --sweep be_offset_ticks=2:8:2 \
  --name "{SESSION} R3 Exit Management"
```

## Phase 3: Bayesian Refinement

Narrow search around Phase 2 winners. Set param ranges ~20-30% around best values. Can sweep all session params simultaneously (5-6 params).

```bash
uv run python scripts/run_bayesian.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} \
  --param {prefix}_stop_atr_pct={LOW}:{HIGH}:{STEP} \
  --param {prefix}_min_gap_atr_pct={LOW}:{HIGH}:{STEP} \
  --param {prefix}_max_gap_atr_pct={LOW}:{HIGH}:{STEP} \
  --param rr={LOW}:{HIGH}:{STEP} \
  --param tp1_ratio={LOW}:{HIGH}:{STEP} \
  --n-trials 200 --objective sharpe --sampler tpe --seed 42 \
  --name "{SESSION} Bayesian Refinement"
```

## Phase 4: Walk-Forward Validation

**Most important phase.** Tests if parameters generalize to unseen data.

```bash
uv run python scripts/run_walkforward.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} \
  --sweep {PARAM1}={RANGE} --sweep {PARAM2}={RANGE} \
  --is-months 12 --oos-months 3 --step-months 3 \
  --objective sharpe --name "{SESSION} Walk-Forward"
```

Sweep the top 2-3 most impactful parameters from Phase 2/3.

**Walk-forward efficiency** (OOS/IS ratio):
- \> 0.5 = stable, tradeable
- 0.3-0.5 = marginal, may be overfit
- < 0.3 = overfit, parameter values are noise

Also try `--anchored` for expanding-window comparison.

## Phase 5: Monte Carlo Stress Testing

### A) Trade Resampling — Drawdown risk
```bash
uv run python scripts/run_monte_carlo.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} --method bootstrap --sims 1000 --seed 42 \
  --ruin-threshold -8.0
```

Ruin probability > 5% = sizing too aggressive or edge too thin.

### B) Parameter-Space LHS — Sensitivity
```bash
uv run python scripts/run_monte_carlo.py --data {DATA} --start {START} --end {END} \
  --sessions {SESSION} --param-sample \
  --param {PARAM1}={LOW}:{HIGH}:{STEP} \
  --sims 500 --workers 8
```

If Sharpe drops with +/-10% perturbation, move toward flatter regions.

## Execution Notes

- Run sessions in parallel when possible
- All results auto-save to the experiment DB (`python/data/results/experiments.db`) and are viewable in the frontend dashboard
- Use `--name` labels consistently for identification
- Objectives: `sharpe` (recommended), `pnl`, `profit_factor`, `calmar`, `avg_r`
- See [cli-reference.md](references/cli-reference.md) for full argument details
