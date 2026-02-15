# Automation Ladder — Strategy Optimization Progression

The framework for how backtesting progresses from fully manual parameter tuning to automated strategy optimization.

---

## Automation Levels

```
Level 0: MANUAL
- User sets all parameters by hand
- Runs one backtest at a time
- Compares results by eyeballing metrics
- "I'll try sl_pct=0.08 and see what happens"

Level 1: INFORMED
- System displays metrics and historical comparisons
- Dashboard shows how current config compares to previous runs
- Parameter sensitivity hints based on past results
- "Show me how this config stacks up against my best runs"

Level 2: GRID SWEEP
- System runs parameter grid across specified ranges
- Heatmaps show metric landscape across parameter space
- User picks best config from results
- "Sweep sl_pct from 0.05 to 0.10, show me the heatmap"

Level 3: AUTO-OPTIMIZE
- System finds optimal parameters within user-defined constraints
- Walk-forward validation prevents overfitting
- Out-of-sample testing built into the workflow
- "Find the best params for NY session, Sharpe > 1.5"

Level 4: ADAPTIVE
- System detects market regime changes
- Suggests parameter adjustments for current regime
- Monitors live performance vs backtest expectations
- "Alert me when realized Sharpe drops below backtest Sharpe"
```

---

## Design Rules

1. **Every feature starts at Level 0.** The manual workflow must work before any automation is added.

2. **The ladder is per-feature, not global.** A user might be:
   - Level 2 on stop loss tuning (grid sweep)
   - Level 1 on session timing (informed comparison)
   - Level 0 on new signal filters (fully manual)

3. **Higher levels compose from lower levels:**
   - Level 2 (Grid Sweep) = Level 0 (Manual) called in a loop
   - Level 3 (Auto-Optimize) = Level 2 (Grid Sweep) with objective function
   - Level 4 (Adaptive) = Level 3 (Auto-Optimize) with regime detection

4. **Design every feature to support progression** up the ladder without architectural changes.

---

## Architecture Implications

### What to Build Now (Levels 0-2)

These are already partially implemented and should be solidified:

```
✅ Frozen config dataclasses (enables programmatic config generation)
✅ Composable pipeline (enables grid sweep by calling run_backtest in a loop)
✅ Result history with full config (enables comparison across runs)
✅ API endpoints (enables dashboard to run sweeps via API)
✅ Grid optimization with heatmap (Level 2 is operational)
```

### What to Prepare For (Levels 3-4)

Build the infrastructure now, activate later:

```
Config Layer:
- StrategyConfig already supports with_overrides() → ready for optimizer
- SessionConfig per-session params → ready for per-session optimization

Result Layer:
- Results already include full config → ready for comparison/ranking
- Metrics computation is independent → ready for custom objective functions

Data Layer:
- Data loading is parameterized → ready for walk-forward splits
- Parquet caching → ready for fast iteration during optimization
```

### What NOT to Build Yet

- Regime detection models (Level 4) — not enough validated data yet
- Live monitoring integration — focus on backtest accuracy first
- ML-based parameter selection — grid sweep hasn't been fully exploited yet

---

## Progressive Feature Disclosure

```
Phase 1 (Current):
User sees: Manual config, single backtest, grid sweep
Hidden: Pipeline composability, config serialization, result comparison infra

Phase 2 (Next):
User sees: Parameter sensitivity analysis, walk-forward validation
Reveal: "See how your strategy performs on unseen data"

Phase 3 (Future):
User sees: Auto-optimization with constraints
Reveal: "Set bounds and objectives, let the system find optimal params"

Phase 4 (Later):
User sees: Regime-aware parameter suggestions
Reveal: "Your strategy parameters may need adjustment for current conditions"
```

Each phase builds on infrastructure from the previous phase. No architectural changes needed.

---

## Data Collection for Automation

Capture these signals now (even if not analyzed yet):

### Backtest History Signals
- Which configs produce the best risk-adjusted returns?
- Which parameters are most sensitive (small changes → big impact)?
- Which session/instrument combos show consistent edge?
- How do optimal parameters change over time (regime sensitivity)?

### Optimization History Signals
- Which parameter ranges produce viable strategies?
- Where does the fitness landscape have plateaus vs peaks?
- Which constraints are binding (optimizer hits the limit)?
- How much do walk-forward results differ from in-sample?

### User Behavior Signals
- Which metrics does the user prioritize when comparing results?
- How often does the user override optimization suggestions?
- Which parameter ranges does the user explore most?

**Store it structured in result JSON, make it queryable. The automation ladder climbs itself when the data is there.**
