---
name: prop-firm-phase1
description: "Prop firm phase 1 optimization: grid sweep + staggered account simulation for the -4R breach / +5R payout model. Start a fresh funded account every 2 weeks, each runs indefinitely until it hits +5R (payout) or -4R (breach). Finds configs that maximize success rate (payouts / resolved accounts), EV per account, and time to payout. Use when the user asks to 'prop firm phase 1', 'optimize for prop firm', '-4R/+5R optimization', 'staggered account optimization', 'prop firm payout analysis', or references optimizing a backtest or config for the biweekly funded account model."
---

# Prop Firm Phase 1 Optimization

Grid sweep optimization + staggered prop firm account simulation. Finds the best config for repeatedly starting fresh funded accounts.

## Account Model

- **New account every 14 calendar days** (staggered starts)
- Each account runs **indefinitely** until resolution:
  - **PAYOUT**: cumulative R reaches +5R from start
  - **BREACH**: cumulative R drops to -4R from start
  - **OPEN**: still alive at end of backtest data
- Multiple accounts are alive simultaneously
- Accounts are independent (no shared equity)

## Inputs

Gather from user:
1. **Source**: either a backtest name/ID from the DB, or an explicit config
2. **Instrument** (NQ, ES, GC, etc.) — inferred from source if DB run
3. **Date range** — default: last 2 years from today
4. **Payout target** — default: +5R
5. **Breach limit** — default: -4R
6. **Stagger interval** — default: 14 days

If the user provides a DB run name, query the local experiments DB to extract the full config:

```python
import sqlite3
conn = sqlite3.connect("backtesting/data/results/experiments.db")
row = conn.execute(
    "SELECT config_json FROM runs WHERE experiment_name LIKE ?",
    (f"%{name_fragment}%",)
).fetchone()
```

## Workflow

### Step 1: Reconstruct Anchor Config

Build the `StrategyConfig` + `SessionConfig` from the source. Confirm with user before proceeding. Key fields to verify:
- `strategy`, `direction_filter`, `rr`, `tp1_ratio`, `risk_usd`
- `excluded_days` (DOW filter)
- Session times, `min_gap_atr_pct`, `lsi_*` params (if LSI)
- `use_bar_magnifier`

### Step 2: Design Grid

Choose params to sweep based on strategy type. General guidelines:

**Always sweep:**
- `rr` — 5-7 values centered on anchor
- `tp1_ratio` — 4-6 values (min 0.15, never below 0.2 for production)

**Strategy-specific sweeps (pick 1-2 more):**
- LSI: `ny_min_gap_atr_pct`, `lsi_n_left`
- Continuation/Reversal: `ny_stop_atr_pct`, `ny_min_gap_atr_pct`

**DOW variants** — sweep 2-3 exclusion patterns from prior analysis:
- Run the grid on each DOW variant as a separate batch

**Target**: 500-2000 total configs (including DOW variants). At ~3 configs/s, this is 3-10 minutes.

### Step 3: Run Sweep

Generate a self-contained Python script: `backtesting/scripts/run_{asset}_propfirm_sweep.py`

Script structure:
```python
#!/usr/bin/env python3
"""Prop firm phase 1 sweep: {INSTRUMENT} {SESSION} {STRATEGY}"""

import sys, time, json, dataclasses, datetime
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.engine.simulator import EXIT_NO_FILL

# 1. Define anchor config (from DB/user)
# 2. Define PARAM_GRID dict
# 3. Define DOW_VARIANTS
# 4. Define simulate_staggered_accounts() function
# 5. Load data, generate configs, run sweep
# 6. Compute metrics + account simulation for each result
# 7. Sort by Calmar and by success rate
# 8. Print tables + detailed account breakdowns
# 9. Save JSON results
```

### Step 4: Simulate Staggered Accounts

For each config's trade list, run the staggered account simulation:

```python
def simulate_staggered_accounts(trades, start_date, end_date,
                                 payout_r=5.0, breach_r=-4.0, stagger_days=14):
    """Start a new account every stagger_days.
    Each runs until +payout_r (PAYOUT), breach_r (BREACH), or end of data (OPEN)."""
```

Key implementation details:
- Walk forward through sorted trade list from each account start date
- Track `cum_r`, `peak_r`, `trough_r` per account
- Account resolves the moment cumulative R crosses either threshold
- Open accounts use current R value for EV calculation

### Step 5: Rank and Report

**Two rankings:**

1. **By Calmar** — primary optimization objective per codebase convention
2. **By Success Rate** — `payouts / (payouts + breaches)` for resolved accounts only

**Key metrics per config:**
| Metric | Description |
|--------|-------------|
| Success Rate | payouts / resolved (payout + breach) |
| Payout Rate | payouts / all accounts started |
| Breach Rate | breaches / all accounts started |
| Avg Days to Payout | calendar days from account start to +5R |
| Median Days to Payout | median calendar days to +5R |
| Avg Days to Breach | calendar days from account start to -4R |
| EV per Account | mean R outcome (capped at payout/breach for resolved) |
| Open Accounts | still alive at end of data + avg R position |

**Detailed breakdown** for top 5 configs: show every account with start date, outcome, final R, peak R, trough R, trades taken, calendar days, resolution date.

### Step 6: Save Results

Save to `backtesting/data/results/{asset}_propfirm_sweep.json` with:
- `sweep_info` — anchor name, model description, date range, grid, timing
- `top50_by_calmar` — ranked configs with all metrics
- `top50_by_propfirm` — ranked configs by success rate

## Interpreting Results

**Good config characteristics:**
- Success rate >80% (of resolved accounts)
- EV per account >+2R
- No breach clusters >3 consecutive (indicates regime sensitivity)
- Open accounts trending positive (avg open R > 0)

**Red flags:**
- Breaches cluster in time (all 3 hit in same month) — regime-dependent
- Very few resolved accounts (mostly open) — need more data
- High success rate but very long time to payout (>300 days) — capital efficiency issue
- Success rate high but driven by favorable start dates — check if early-started accounts dominate

**What the open accounts tell you:**
- Many open accounts with positive R — bullish, likely would resolve as payouts with more data
- Open accounts with R near breach — strategy may be deteriorating
- Median open R is the best indicator of forward trajectory

## Reference Script

A complete working example is at:
`backtesting/scripts/run_nq_lsi_propfirm_sweep.py`

This handles NQ LSI with the full pipeline: data loading, grid generation, parallel sweep, staggered account simulation, ranking, and JSON output.

## Constraints

- **Calmar is still the primary optimization objective** — don't sacrifice Calmar for marginal success rate gains
- **DD is NOT a hard filter** — report alongside Calmar for position sizing decisions
- **Minimum 50 trades** to include a config in rankings
- **tp1_ratio minimum 0.2** for production configs (0.15 acceptable for exploration)
- Always use `use_bar_magnifier=True`
- Load 1m data when available for fill precision
