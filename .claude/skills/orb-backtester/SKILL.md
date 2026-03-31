---
name: orb-backtester
description: >
  Operates the ORB+FVG Python backtesting engine for running backtests, optimization sweeps, experiment
  tracking, and extending the engine with new signals or instruments. Use when the user asks to run a
  backtest, optimize parameters, query experiments, compare results, add new signals or instruments,
  modify the simulation engine, debug trade execution, or analyze strategy performance. Triggers on
  "backtest", "optimize", "sweep", "experiment", "metrics", "performance", "win rate", "drawdown",
  "Sharpe", "equity curve", "add signal", "add instrument", "run on NQ/ES/MNQ", "stop ATR", "FVG",
  "ORB", or strategy analysis requests.
---

# ORB Backtester

Python backtesting engine for Opening Range Breakout + Fair Value Gap trading strategies. Hybrid vectorized (NumPy/Pandas) signal generation with Numba-compiled trade simulation, supporting multi-session backtests, grid sweep optimization, and SQLite experiment tracking.

## When to Use

- Running single backtests or optimization sweeps on NQ, MNQ, ES, GC, CL, YM, etc.
- Analyzing strategy performance (metrics, equity curves, drawdowns)
- Querying or comparing experiment history
- Adding new signal modules, instruments, or session configurations
- Modifying the trade simulation engine (fills, exits, position sizing)
- Debugging trade execution or signal generation issues
- Downloading market data or syncing results to R2
- Working with the FastAPI endpoints

## Do NOT Use When

- Making architectural decisions about new features (use `agent-first` skill)
- Building frontend dashboard components (use `frontend-design` skill)

## Shared Strategy Learnings

A persistent knowledge base lives at `references/strategy-learnings.md`. It captures parameter insights, session behavior, signal observations, failed hypotheses, edge cases, and optimization results discovered across all sessions.

**Every agent MUST:**
1. **Read** `references/strategy-learnings.md` before running backtests, sweeps, or proposing strategy changes
2. **Update** it after discovering meaningful insights — new parameter findings, failed hypotheses, edge cases, or notable optimization results

**What to record:**
- Parameter values that consistently help or hurt (with data: instrument, session, date range, metric impact)
- Session-specific behavior differences (e.g., "Asia sessions need tighter stops")
- Ideas that were tested and did NOT work — prevents re-testing dead ends
- Specific dates or conditions that cause anomalies
- Sweep results worth referencing later

**What NOT to record:**
- Routine run outputs with no new insight
- Speculative ideas not yet tested
- Temporary debugging notes

## Workflow

### Step 0: Load Strategy Learnings

Before any backtest, optimization, or strategy modification, load `references/strategy-learnings.md` and review relevant sections. Use prior findings to inform parameter choices and avoid repeating failed experiments.

### Step 1: Understand the Request

Classify the request:

| Category | Action |
|----------|--------|
| **Run backtest** | Load `references/workflows.md` for CLI, API, or programmatic usage |
| **Optimize params** | Load `references/workflows.md` for sweep syntax and execution |
| **Query experiments** | Load `references/workflows.md` for experiment querying |
| **Analyze results** | Load `references/architecture.md` for metrics and result schema |
| **Add/modify signal** | Load `references/signals.md` for signal module patterns |
| **Add instrument** | Load `references/architecture.md` for instrument registry |
| **Modify engine** | Load `references/architecture.md` for execution model and exit types |
| **Debug issues** | Load `references/signals.md` and `references/architecture.md` |

### Step 2: Execute

**For running backtests or sweeps:**

1. Determine instrument (NQ, MNQ, ES), sessions (ny, asia, ldn), and date range
2. Identify any parameter overrides (risk_usd, rr, tp1_ratio, stop_atr_pct, etc.)
3. Execute via CLI script: `cd python && uv run python scripts/run_backtest.py` or `run_optimize.py`
4. Results auto-save to `python/data/results/` and log to `experiments.db`

**For historical execution-profile replays (profiles from `execution/config/exec_configs.json`):**

1. Do **not** reconstruct the profile by hand inside the research backtester.
2. Use the exact replay path from `execution/`:
   `cd execution && PYTHONUNBUFFERED=1 .venv/bin/python scripts/save_exact_exec_backtests.py --profiles ... --years N`
3. Treat `execution/src/trader/historical_backtest.py` as the source of truth for these runs.
4. Use `orb-trader --replay ...` only for narrow single-symbol engine debugging, not for saved portfolio backtests.
5. Save a top-level `config.risk_usd = 5000` for backtesting/dashboard R reporting; preserve the live per-session execution sizing in the exported `*_risk_usd` fields.
6. Verify the resulting backtest IDs from the shared API so the frontend can review them.

**For modifying the engine:**

1. Read the relevant source file(s) before making changes
2. Follow the hybrid architecture: vectorized signals (NumPy), Numba for bar-by-bar state
3. Load `references/bias-prevention.md` before adding signals or filters to guard against lookahead
4. Ensure new parameters flow through `StrategyConfig` or `SessionConfig` frozen dataclasses
5. Use `with_overrides()` for session-prefixed parameter support

**For adding a new signal module:**

1. Create pure function in `python/src/orb_backtest/signals/` — arrays in, arrays out
2. Use Numba @njit only when vectorization is insufficient (stateful bar-by-bar logic)
3. Shift indicators by 1 bar to prevent look-ahead bias
4. Integrate into `_extract_setup_candidates()` in `engine/simulator.py`

**For adding a new instrument:**

1. Add entry to `INSTRUMENTS` dict in `python/src/orb_backtest/data/instruments.py`
2. Provide: symbol, point_value, min_tick, commission, data_file, exchange_tz
3. Ensure CSV data file exists in `python/data/raw/`

### Step 3: Validate and Report

After running a backtest:
- Report key metrics: total trades, win rate, profit factor, Sharpe ratio, max drawdown
- Note the exit type breakdown (SL, TP1+TP2, TP1+BE, EOD, no-fills)
- Flag if results were auto-saved and the experiment ID

After modifying engine code:
- Run existing backtests to verify no regression
- Compare metrics before/after the change

### Step 4: Update Strategy Learnings

After completing the task, determine if any new insight was discovered. If so, update `references/strategy-learnings.md` under the appropriate section:

- **Parameter Insights** — include instrument, session, date range, and metric impact
- **Session Behavior** — note session-specific differences
- **Signal Observations** — FVG quality, gap size patterns, ORB behavior
- **Failed Hypotheses** — what was tested, what the result was, why it failed
- **Known Edge Cases** — specific dates or conditions causing anomalies
- **Optimization Results** — best parameter combos from sweeps with context

## Error Handling

| Error | Recovery |
|-------|----------|
| `unknown_instrument` | Check spelling; valid: NQ, MNQ, ES. Add new ones to `instruments.py` |
| `unknown_session` | Valid sessions: ny, asia, ldn. Check `config.py` for session definitions |
| `data_not_found` | Run `scripts/download_data.py {SYMBOL} --start YYYY-MM-DD --save-1m` (always use `--save-1m` for chart data) |
| `invalid_sweep_spec` | Format: `param=start:end:step` or `param=val1,val2,val3` |
| Numba compilation slow on first run | Normal cold-start behavior; subsequent calls are fast |
| `ModuleNotFoundError` | Run `cd python && uv sync` to install dependencies |

## Key Files Quick Reference

| Purpose | File |
|---------|------|
| Strategy config | `python/src/orb_backtest/config.py` |
| Trade simulator | `python/src/orb_backtest/engine/simulator.py` |
| FVG detection | `python/src/orb_backtest/signals/fvg.py` |
| ORB levels | `python/src/orb_backtest/signals/orb.py` |
| Session masks | `python/src/orb_backtest/signals/session.py` |
| Daily ATR | `python/src/orb_backtest/signals/daily_atr.py` |
| Metrics | `python/src/orb_backtest/results/metrics.py` |
| Save/load results | `python/src/orb_backtest/results/export.py` |
| Grid optimization | `python/src/orb_backtest/optimize/grid.py` |
| Parallel execution | `python/src/orb_backtest/optimize/parallel.py` |
| API endpoints | `python/src/orb_backtest/api.py` |
| Experiments DB | `python/src/orb_backtest/experiments.py` |
| Instruments | `python/src/orb_backtest/data/instruments.py` |
| Data loader | `python/src/orb_backtest/data/loader.py` |
| Equity plots | `python/src/orb_backtest/viz/equity.py` |
| Exact execution replay | `execution/src/trader/historical_backtest.py` |
| Exact execution replay CLI | `execution/scripts/save_exact_exec_backtests.py` |

## References

- Load `references/architecture.md` for project layout, execution model, config hierarchy, exit types, API endpoints, and instrument registry
- Load `references/signals.md` for FVG detection logic, ORB levels, session masks, daily ATR, and how to add new signal modules
- Load `references/workflows.md` for CLI commands, API calls, and programmatic usage examples
- Load `references/bias-prevention.md` for look-ahead bias prevention, optimization discipline, and engine safeguards
- Load `references/strategy-learnings.md` for accumulated parameter insights, session behavior, failed hypotheses, and optimization results — **read before every backtest/sweep, update after new discoveries**
