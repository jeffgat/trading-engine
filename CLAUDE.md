# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains a Python backtesting engine for Opening Range Breakout (ORB) trading strategies with Fair Value Gap (FVG) entries. The engine is designed for 5-minute futures data and implements risk management with partial take-profits and breakeven stops.

**Terminology**: "Gap" and "FVG" (Fair Value Gap) are used interchangeably throughout this codebase.

## Key Trading Logic

### FVG Detection (3-candle pattern)
- Bar [2] = "before" candle
- Bar [1] = impulse candle (creates the gap)
- Bar [0] = "after" candle (confirms gap exists)
- Bullish FVG: `high[2] < low AND high[2] < high[1] AND low[2] < low`
- Bearish FVG: `low[2] > high AND low[2] > low[1] AND high[2] > high`

### Entry/Exit Structure
- Entry: Limit order at FVG retest level (top for longs, bottom for shorts)
- Stop: Low/high of the "before" candle (bar [2])
- TP1: 50% at halfway point (configurable via `tp1Ratio`)
- TP2: Remaining at full R:R target
- Breakeven: Stop moves to entry after TP1 hit

### Session Times
- US: ORB 09:30-09:45 NY, entries until 12:00, flat by 15:50
- Asia: ORB 09:00-09:30 JST, entries until 12:30, flat by 14:50

## Backtest Naming Convention

Every backtest and optimization **must** have a unique, descriptive `experiment_name`. Duplicate names make it impossible to identify runs in the history dashboard.

### Format

```
{INSTRUMENT} {SESSIONS} {description}
```

- **INSTRUMENT**: Symbol (NQ, ES, CL, GC, MNQ, YM, etc.)
- **SESSIONS**: Which sessions ran (NY, ASIA+NY, ASIA, etc.)
- **description**: What this run is testing — this is what makes names unique

### Description guidelines

| Run type | Description pattern | Example |
|----------|-------------------|---------|
| Default params | `{year_range} Defaults` | `NQ ASIA+NY 2024-2025 Defaults` |
| Post-optimization | `{year_range} Optimized` | `NQ NY 2024-2025 Optimized` |
| Specific param test | `{what changed}` | `NQ ASIA+NY 2015-2026 rr3` |
| Variant/iteration | append `v2`, `v3`, or `(detail)` | `MNQ ASIA+NY 2024-2025 Optimized v2` |
| Walk-forward OOS | `WF{N} OOS` | `WF1 OOS` |
| Feature/gate test | descriptive label | `CL SMA20 Trend Gated` |
| Baseline reference | `Baseline` | `GC NY Baseline` |

### Rules for agents

1. **Always pass `--name`** on CLI runs or `name` in API requests — never rely on auto-naming alone
2. **Check existing names** before running: query the DB or dashboard to avoid duplicates
3. **Include the differentiator** — if two runs share instrument/sessions/dates, the description must explain what's different (params, risk size, feature toggle, etc.)
4. The auto-namer appends a session-config fingerprint as a safety net, but explicit names are always preferred

## Per-Asset Learnings

Maintain a living document for each asset in `python/learnings/`. These files capture what works, what doesn't, and why — so no strategy is re-tested and no insight is lost.

- **Location**: `python/learnings/{SYMBOL}.md` (e.g., `GC.md`, `NQ.md`, `CL.md`)
- **When to update**: After completing a strategy test, robust pipeline run, or discovering a significant finding for any asset
- **What to include**: Instrument profile, strategies tested (with GO/NO-GO status), winning configs, key findings, parameter sensitivity, prop firm considerations
- **Format**: See `python/learnings/GC.md` as the reference template

### Rules for agents

1. **Check learnings before testing** — read the asset's learnings file before proposing or running a strategy. If it's already marked NO-GO, don't re-test without a fundamentally different approach.
2. **Update after every conclusion** — when a strategy is validated (GO) or ruled out (NO-GO), add it to the learnings doc immediately.
3. **Include the evidence** — record key metrics (trades, WR, Net R, Sharpe, DD) and the DB experiment name so results are traceable.
4. **Create new files as needed** — when testing a new asset for the first time, create its learnings file following the GC.md template.

## Backtesting Engine

### Architecture (Hybrid Vectorized + Numba)
- **Signal generation** (vectorized): Session masks, ORB levels, FVG detection via NumPy/Pandas
- **Trade simulation** (Numba-compiled): `_simulate_single_trade()` handles fill scanning, partial TP, breakeven stops
- **One trade per session-day**: When both long and short setups exist, the first-to-fill wins

### Key Modules
- `engine/simulator.py` — Core backtest loop, `run_backtest()` entry point, `TradeResult` schema
- `signals/` — `fvg.py` (FVG detection), `orb.py` (ORB levels), `session.py` (time windows), `daily_atr.py`
- `results/metrics.py` — Sharpe, Sortino, drawdown, profit factor, win rate, exit breakdown
- `optimize/grid.py` — Parameter grid generation for sweep optimization
- `optimize/parallel.py` — Parallel execution of grid sweeps
- `config.py` — `StrategyConfig` and `SessionConfig` dataclasses
- `data/loader.py` — OHLCV data loading, `instruments.py` — instrument definitions
- `api.py` — FastAPI endpoints for running backtests
- `experiments.py` — Experiment tracking and comparison

### Backtesting Best Practices

When building or modifying the backtesting engine, guard against these biases:

| Bias | Description | Mitigation |
|------|-------------|------------|
| **Look-ahead** | Using future data in signals | Point-in-time data only; signals shift by 1 bar before acting |
| **Overfitting** | Curve-fitting params to history | Walk-forward analysis; out-of-sample holdout |
| **Transaction costs** | Ignoring slippage/commissions | Realistic cost model (commission already implemented) |
| **Selection bias** | Cherry-picking best param set | Pre-register hypotheses; test on unseen data |

**Optimization discipline:**
- Split data into **train / validation / test** sets — never optimize on the test set
- Prefer **walk-forward optimization** (rolling train→test windows) over single in-sample optimization
- Use **Monte Carlo bootstrap** (resample trade returns) to estimate drawdown confidence intervals
- Limit free parameters to reduce overfitting risk — simpler models generalize better
