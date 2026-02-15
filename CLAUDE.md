# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This repository contains TradingView Pine Script strategies for backtesting Opening Range Breakout (ORB) trading strategies with Fair Value Gap (FVG) entries. The strategies are designed for 5-minute charts and implement risk management with partial take-profits and breakeven stops.

**Terminology**: "Gap" and "FVG" (Fair Value Gap) are used interchangeably throughout this codebase.

## Strategy Versions

- **orb_v1.pine**: Original ORB strategy (Pine Script v6) - has execution issues with entry timing
- **orb_v2.pine**: Improved version with bar magnifier and better fill handling for US markets (NY time)
- **orb_v2_asia.pine**: Adapted for Japan markets (JST timezone, Nikkei 225)
- **orb_v2_min_5pt_gap.pine**: V2 with minimum 5-point gap filter to reduce false signals
- **test.pine**: FVG visualization indicator (Pine Script v5) - used for debugging gap detection

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
- US (orb_v2): ORB 09:30-09:45 NY, entries until 12:00, flat by 15:50
- Asia (orb_v2_asia): ORB 09:00-09:30 JST, entries until 12:30, flat by 14:50

## Known Issues (from README)

1. Entries triggering on gap creation instead of retest
2. Adverse executions causing >1R losses (stop execution issues, overnight holds)
3. Max wins capped at 1.1-1.2R instead of expected 1.5R

## Python Backtesting Engine

The `python/` directory contains a standalone backtesting engine that replicates the Pine Script logic with full programmatic control.

### Architecture (Hybrid Vectorized + Numba)
- **Signal generation** (vectorized): Session masks, ORB levels, FVG detection via NumPy/Pandas
- **Trade simulation** (Numba-compiled): `_simulate_single_trade()` handles fill scanning, partial TP, breakeven stops
- **One trade per session-day**: When both long and short setups exist, the first-to-fill wins (matching Pine behavior)

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

## Pine Script Conventions Used

- Uses `barstate.isconfirmed` for confirmed bar signals (V2)
- `process_orders_on_close = true` and `use_bar_magnifier = true` for better fill simulation
- Position sizing via `floorToStep()` helper for CFD/futures lot sizing
- State reset on `newDay` detection
- Single trade per day enforcement via `hasTradedToday` flag
