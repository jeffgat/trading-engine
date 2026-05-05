---
name: strategy-optimizer
description: >
  Runs parameter optimization sweeps, walk-forward analysis, robustness testing, and Monte Carlo
  simulations on the ORB+FVG Python backtesting engine. Use when the user asks to optimize parameters,
  run a sweep, find the best config, do walk-forward validation, test robustness, run Monte Carlo,
  analyze parameter sensitivity, compare in-sample vs out-of-sample, or evaluate overfitting risk.
  Triggers on "optimize", "sweep", "walk-forward", "Monte Carlo", "robustness", "sensitivity",
  "in-sample", "out-of-sample", "overfit", "best params", "parameter surface", "grid search",
  or any request to find optimal strategy settings.
---

# Strategy Optimizer

Advanced parameter optimization for the ORB+FVG backtesting engine. Covers grid sweeps, walk-forward validation, Monte Carlo bootstrap, sensitivity analysis, and overfitting detection — all built on the existing `run_optimize.py` CLI and `optimize/` modules.

## When to Use

- Running parameter grid sweeps to find optimal settings
- Walk-forward optimization (rolling train/test windows)
- Monte Carlo bootstrap for drawdown confidence intervals
- Parameter sensitivity analysis (how stable are results to small param changes?)
- In-sample vs out-of-sample validation
- Comparing sweep results across instruments or sessions
- Evaluating overfitting risk on optimized parameter sets
- Building custom optimization scripts beyond the standard CLI

## Do NOT Use When

- Running a single backtest with known parameters (use `orb-backtester` skill)
- Adding new signals, instruments, or modifying engine code (use `orb-backtester` skill)
- Making architectural decisions (use `agent-first` skill)
- Building frontend components (use `frontend-design` skill)

## Shared Strategy Learnings

The optimization knowledge base now lives under `backtesting/learnings/`.

**Every optimization run MUST:**
1. **Read** `backtesting/learnings/README.md`, `backtesting/learnings/briefs/GLOBAL.md`, and the relevant `backtesting/learnings/briefs/assets/{SYMBOL}.md` before starting
2. **Label** every candidate row with `deployability`, `live_support_notes`, and `exact_replay_required` from `backtesting/learnings/CANDIDATE_DEPLOYABILITY.md`
3. **Update** the relevant detailed learnings file after discovering meaningful insights, then regenerate the access layer with `uv run python backtesting/scripts/build_learnings_registry.py`

## Workflow

### Step 0: Load Context

Before any optimization work:
1. Read `backtesting/learnings/README.md`, `backtesting/learnings/briefs/GLOBAL.md`, and the relevant `backtesting/learnings/briefs/assets/{SYMBOL}.md` for prior findings
2. Open `backtesting/learnings/global/strategy-memory.md`, `backtesting/learnings/asset/{SYMBOL}.md`, or `backtesting/learnings/indexes/assets/{SYMBOL}.md` only when the brief is not enough
3. Load `references/parameter-guide.md` for sweepable parameter ranges and recommendations
4. Load `references/optimization-methods.md` for the specific method being requested

### Step 1: Classify the Request

| Category | Action |
|----------|--------|
| **Grid sweep** | Use CLI `run_optimize.py` or programmatic `run_sweep()` |
| **Walk-forward** | Load `references/optimization-methods.md` — build rolling window script |
| **Monte Carlo** | Load `references/optimization-methods.md` — bootstrap trade returns |
| **Sensitivity analysis** | Run narrow sweeps around a candidate config |
| **In-sample/out-of-sample** | Split date range, optimize on train, validate on test |
| **Compare sweeps** | Query experiment DB, compare across runs |
| **Custom optimization** | Load `references/optimization-methods.md` for patterns |

### Step 2: Design the Optimization

**Before running any sweep:**

1. **Define the objective** — Which metric to optimize? Sharpe is default; profit factor, Sortino, or max drawdown may be better depending on the goal
2. **Choose parameters to sweep** — Load `references/parameter-guide.md` for ranges. Limit to 2-3 parameters per sweep to keep grid size manageable
3. **Set the date range** — Decide train vs test split if doing validation
4. **Estimate grid size** — Print with `describe_grid()` before running. Warn if >500 combinations (can be slow)
5. **Check for prior results** — Query experiment DB to avoid re-running identical sweeps

### Step 3: Execute

**Standard grid sweep via CLI:**

```bash
cd python && uv run python scripts/run_optimize.py \
  --instrument NQ \
  --sessions ny \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --sweep ny_stop_atr_pct=5:25:2.5 \
  --sweep rr=1.5,2.0,2.5,3.0 \
  --workers 4
```

**Programmatic sweep (for custom analysis):**

```python
from orb_backtest.config import default_config, with_overrides
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid, describe_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

instrument = get_instrument("NQ")
base = default_config(instrument)
param_ranges = {
    "ny_stop_atr_pct": [5, 7.5, 10, 12.5, 15],
    "rr": [2.0, 2.5, 3.0],
}
configs = generate_param_grid(base, param_ranges)
print(describe_grid(param_ranges))

df = load_5m_data(instrument.data_file, start="2024-01-01", end="2024-12-31")
results = run_sweep(df, configs, n_workers=4, start_date="2024-01-01")

scored = [(c, compute_metrics(t)) for c, t in results]
best = max(scored, key=lambda x: x[1]["sharpe_ratio"])
```

**Walk-forward and Monte Carlo:** Load `references/optimization-methods.md` for complete implementation patterns.

### Step 4: Analyze Results

After a sweep completes:

1. **Report the top configs** — Show top 3-5 by Sharpe (or chosen metric) with full param values
2. **Check for parameter clustering** — Do the best configs cluster around similar values? If so, the signal is robust
3. **Flag overfitting risks:**
   - Very few trades (<50) in the test period
   - Sharp performance cliff at nearby param values (sensitivity)
   - Unrealistic Sharpe (>3.0 on multi-year data)
   - Single metric looks great but others are poor (e.g., high Sharpe but low profit factor)
4. **Recommend validation** — Suggest out-of-sample test or walk-forward if not already done
5. **Compare with prior results** — Reference the learnings briefs first, then the detailed histories only if needed

### Step 5: Validate (When Applicable)

For any optimization that produces a "best" parameter set:

1. **Out-of-sample test** — Run the best config on held-out data (at least 20% of total period)
2. **Stability check** — Sweep a narrow range around the best values (best +/- 10-20%). Results should degrade gracefully, not cliff
3. **Cross-instrument check** — If NQ params look good, test on MNQ (same underlying, different contract) as a sanity check
4. **Monte Carlo bootstrap** — Resample trade returns 1000+ times to estimate drawdown confidence intervals

### Step 6: Update Strategy Learnings

After completing optimization work, update the appropriate detailed learnings source with:

- **Optimization Results** — Best param combos with instrument, session, date range, and key metrics
- **Parameter Insights** — Which params matter most, which are insensitive
- **Failed Hypotheses** — Sweeps that didn't improve results
- **Robustness Findings** — Walk-forward degradation, Monte Carlo confidence intervals

Use:
- `backtesting/learnings/global/strategy-memory.md` for cross-asset or cross-strategy conclusions
- `backtesting/learnings/asset/{SYMBOL}.md` for asset-specific conclusions
- `backtesting/learnings/reports/` for long-form optimization writeups
- `uv run python backtesting/scripts/build_learnings_registry.py` after updating learnings

## Error Handling

| Error | Recovery |
|-------|----------|
| Sweep taking too long | Reduce grid size; use `--workers` for parallelism |
| All configs produce 0 trades | Loosen filters (reduce `min_gap_atr_pct`, widen stop ATR range) |
| Memory error during large sweep | Reduce `--workers` count; run in batches |
| Numba cold start slow | First run compiles; subsequent runs are fast |
| `invalid_sweep_spec` | Format: `param=start:end:step` or `param=val1,val2,val3` |
| Walk-forward window too small | Need at least 6 months train, 2 months test minimum |

## Key Files

| Purpose | File |
|---------|------|
| Sweep CLI | `python/scripts/run_optimize.py` |
| Grid generation | `python/src/orb_backtest/optimize/grid.py` |
| Parallel execution | `python/src/orb_backtest/optimize/parallel.py` |
| Metrics computation | `python/src/orb_backtest/results/metrics.py` |
| Save/load results | `python/src/orb_backtest/results/export.py` |
| Experiment tracking | `python/src/orb_backtest/experiments.py` |
| Strategy config | `python/src/orb_backtest/config.py` |
| Data loader | `python/src/orb_backtest/data/loader.py` |
| Instruments | `python/src/orb_backtest/data/instruments.py` |

## References

- Load `references/parameter-guide.md` for all sweepable parameters, recommended ranges, and session-specific defaults
- Load `references/optimization-methods.md` for walk-forward, Monte Carlo, sensitivity analysis, and custom optimization patterns
- Load `backtesting/learnings/README.md`, `backtesting/learnings/briefs/GLOBAL.md`, and `backtesting/learnings/briefs/assets/{SYMBOL}.md` for accumulated insights before every sweep; follow with the detailed histories only when needed
- Load `.agents/skills/orb-backtester/references/bias-prevention.md` for overfitting prevention and optimization discipline
- Load `.agents/skills/orb-backtester/references/architecture.md` for engine execution model and config hierarchy
