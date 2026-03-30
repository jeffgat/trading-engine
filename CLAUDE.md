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
- Entry (continuation/reversal): Limit order at FVG retest level (top for longs, bottom for shorts)
- Entry (inversion/cisd/lsi): Market-at-close on the signal/displacement bar
- Stop: ATR-percentage-based distance from entry (configurable via `stop_atr_pct` per session)
- TP1: 50% at halfway to full R:R target (configurable via `tp1_ratio`)
- TP2: Remaining at full R:R target
- Breakeven: Stop moves to entry after TP1 hit

### Hard Trade Constraints (enforced in engine — cannot be overridden)

These rules are enforced at both config validation and trade execution level. No backtest or optimization can violate them.

1. **Minimum stop distance**: Stop must be at least **5% of daily ATR**, regardless of stop source (ATR-based, ORB-based, or structural). Enforced in the simulator after computing stop_dist from any source.
2. **Minimum TP1 distance**: TP1 must be at least as far from entry as the stop loss (`tp1_ratio * rr >= 1.0`). Enforced both in `StrategyConfig.__post_init__()` (rejects invalid configs) and in the simulator (clamps `tp1_dist` to `max(tp1_dist, risk_pts)`).
3. **Minimum R:R ratio**: `rr` must be >= 1.0. Enforced in `StrategyConfig.__post_init__()`.

These constraints exist because sub-1R TP1 distances produce scalp-like behavior that doesn't survive transaction costs and slippage in live execution, and tiny ATR stops get stopped out by normal price noise.

### Strategy Types

The `StrategyConfig.strategy` field controls signal generation mode:

- `"continuation"` — Bullish/bearish FVG in the direction of ORB breakout; entry at FVG retest
- `"reversal"` — FVG forms against the ORB direction; entry at FVG retest (fade the breakout)
- `"inversion"` — FVG forms, price trades through it (invalidation), then retests from the other side; entry at close of inversion bar
- `"cisd"` — Change in State of Delivery: ORB liquidity sweep + displacement candle reversal; does NOT require FVG detection — pure price-action signal; entry at displacement candle close
- `"lsi"` — Liquidity Sweep Inversion: swing level swept → FVG forms within N bars → FVG inverted → entry at inversion bar close
- `"ib"` — Initial Balance mean-reversion: 9:30–10:30 range defines the IB; entry at midpoint based on which extreme (high/low) formed first; no FVG required

### Liquidity Sweep Signal

**Definition** (canonical — all agents must use this):

A **swing high** at bar[i]: `high[i]` is strictly greater than all `n_bars` bars to its left AND all `n_bars` bars to its right. Equivalent to Pine Script's `ta.pivothigh(n_bars, n_bars)`.

A **swing low** at bar[i]: `low[i]` is strictly less than all `n_bars` bars to its left AND all `n_bars` bars to its right.

A **liquidity sweep** occurs when:
- Price trades **above** a prior confirmed swing high → **high sweep** (buy-side liquidity taken)
- Price trades **below** a prior confirmed swing low → **low sweep** (sell-side liquidity taken)

**Implementation**: two modules work together:
- `signals/swing.py` — low-level pivot detection: `detect_swing_highs(high, n_left, n_right)`, `detect_swing_lows(low, n_left, n_right)`
- `signals/liquidity_sweep.py` — sweep pipeline (wraps `swing.py`):
  - `detect_swing_pivots(high, low, n_bars)` → pivot bool + level arrays (confirmation delayed by `n_bars`)
  - `track_latest_swing(...)` → forward-filled most recent pivot levels
  - `detect_liquidity_sweeps(high, low, latest_swing_high, latest_swing_low)` → `{high_swept, low_swept, swept_high_level, swept_low_level}` (internally shifts swing levels by 1 bar — pass raw output from `track_latest_swing`, do not pre-shift)

**Sweep detection uses strict `>` / `<`** so tick-perfect touches do not count as sweeps.

**Config parameter**: `StrategyConfig.swing_n_bars` (default 10). Controls the pivot width — higher values = fewer, more significant pivots.

**When to use this**: Any agent asked to test "reversals off liquidity sweeps", "fade the sweep", or "sweep-and-reverse" must use this module. The ATR-based `qualifying_move_atr_pct` gate in `SessionConfig` is a separate, older concept that measures extension from ORB levels — it can be used alongside sweep detection but is not a substitute for it.

### Session Times (all times Eastern)
- US: ORB 09:30-09:45, entries until 13:00, flat by 15:50
- Asia: ORB 20:00-20:15, entries until 23:15, flat by 06:45 (next day)

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

Maintain a living document for each asset in `backtesting/learnings/`. These files capture what works, what doesn't, and why — so no strategy is re-tested and no insight is lost.

- **Location**: `backtesting/learnings/{SYMBOL}.md` (e.g., `GC.md`, `NQ.md`, `CL.md`)
- **When to update**: After completing a strategy test, robust pipeline run, or discovering a significant finding for any asset
- **What to include**: Instrument profile, strategies tested (with GO/NO-GO status), winning configs, key findings, parameter sensitivity, prop firm considerations
- **Format**: See `backtesting/learnings/GC.md` as the reference template

### Rules for agents

1. **Check learnings before testing** — read the asset's learnings file before proposing or running a strategy. If it's already marked NO-GO, don't re-test without a fundamentally different approach.
2. **Update after every conclusion** — when a strategy is validated (GO) or ruled out (NO-GO), add it to the learnings doc immediately.
3. **Include the evidence** — record key metrics (trades, WR, Net R, Sharpe, DD) and the DB experiment name so results are traceable.
4. **Create new files as needed** — when testing a new asset for the first time, create its learnings file following the GC.md template.

## Backtesting Best Practices

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
