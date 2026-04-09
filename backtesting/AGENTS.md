# Python Backtester

Custom backtesting engine for the ORB + FVG strategy. Uses a hybrid architecture: vectorized signal generation (numpy/pandas) + Numba-compiled trade simulation.

## Why Custom (Not Vectorbt/Backtrader)

Limit orders that fill 1-20 bars after signal, partial exits (50% at TP1), and breakeven stops that move mid-trade don't fit signal-based frameworks. Numba lets us write straight-forward state machine logic without vectorization gymnastics.

## Commands

```bash
# Install dependencies
uv sync

# Single backtest
uv run python scripts/run_backtest.py --data NQ_5m.csv --sessions NY,Asia --name "test"

# Parameter sweep
uv run python scripts/run_optimize.py --data NQ_5m.csv \
  --sweep ny_stop_atr_pct=5:25:1 --sweep rr=1.5:4.0:0.5 --workers 8

# API server (serves results to frontend dashboard)
uv run python scripts/run_server.py

# Download market data from Databento
uv run python scripts/download_data.py

# Sync data to/from Cloudflare R2
uv run python scripts/sync_data.py upload|download|watch
```

## Project Structure

```
backtesting/
├── src/orb_backtest/              # Single package (all strategies)
│   ├── config.py                  # Frozen dataclass configs (Instrument, SessionConfig, StrategyConfig)
│   ├── gapfill_config.py          # GapFill strategy config
│   ├── vwap_config.py             # VWAP strategy config
│   ├── api.py                     # FastAPI server for frontend
│   ├── experiments.py             # Experiment tracking (dual-write: local + remote)
│   ├── experiments_remote.py      # Remote API client
│   ├── errors.py                  # Custom exception types
│   ├── data/
│   │   ├── instruments.py         # Instrument definitions (NQ, ES, YM, GC, CL, etc.)
│   │   ├── loader.py              # CSV → Parquet loading with hash-based caching
│   │   ├── bar_mapping.py         # Multi-timeframe bar index mapping
│   │   └── news_dates.py          # FOMC, NFP, CPI, PPI date lookups
│   ├── engine/
│   │   ├── simulator.py           # Core ORB+FVG trade simulator (Numba-compiled)
│   │   ├── qualifying_move.py     # QM engine: run_backtest_qm(), run_backtest_no_orb()
│   │   ├── vwap_simulator.py      # VWAP strategy engine
│   │   ├── gapfill_simulator.py   # Gap-fill strategy engine
│   │   └── news_straddle.py       # News event straddle strategy
│   ├── signals/
│   │   ├── fvg.py                 # FVG detection (vectorized)
│   │   ├── orb.py                 # ORB level computation (Numba)
│   │   ├── session.py             # Session time windows + cross-midnight handling
│   │   ├── daily_atr.py           # Daily ATR, SMA, EMA, ROC, ADX, Donchian
│   │   ├── swing.py               # Swing high/low pivot detection
│   │   ├── liquidity_sweep.py     # Liquidity sweep pipeline
│   │   ├── vwap.py                # Session VWAP + std bands + deviation/rejection
│   │   ├── ib.py                  # Initial Balance level computation
│   │   └── structure_15m.py       # 15m market structure (HH/HL patterns, regime)
│   ├── optimize/
│   │   ├── grid.py                # Parameter grid generation
│   │   ├── parallel.py            # Multiprocessing sweep executor
│   │   ├── walkforward.py         # Rolling walk-forward optimization
│   │   ├── bayesian.py            # Optuna-based Bayesian optimization
│   │   ├── objectives.py          # Optimization objective functions
│   │   ├── stability.py           # Parameter stability analysis
│   │   ├── prop_constraints.py    # Prop firm constraint simulation
│   │   └── parallel_{qm,vwap,gapfill}.py, walkforward_{qm,vwap,gapfill}.py
│   ├── analysis/
│   │   ├── gates.py               # Post-trade filter gates (SMA, ATR, DOW, sweep, etc.)
│   │   ├── holdout_log.py         # OOS holdout period tracking
│   │   ├── regime_change.py       # Regime detection (Kolmogorov-Smirnov)
│   │   ├── regime_reports.py      # Regime reporting utilities
│   │   ├── news_regime.py         # News regime reporting
│   │   ├── autocorrelation.py     # Autocorrelation + MC assumption checks
│   │   ├── conditional_stats.py   # Streak and conditional win-rate analysis
│   │   └── prop_regime_specialist.py  # Prop firm account simulation by regime
│   ├── simulate/
│   │   └── monte_carlo.py         # Monte Carlo bootstrap simulation
│   ├── results/
│   │   ├── metrics.py             # Performance metrics (Sharpe, Sortino, drawdown, etc.)
│   │   └── export.py              # Result serialization
│   └── viz/
│       └── equity.py              # Equity curve + monthly returns plots
├── scripts/
│   ├── run_backtest.py            # CLI: single backtest with param overrides
│   ├── run_optimize.py            # CLI: grid search parameter sweep
│   ├── run_server.py              # FastAPI launcher (port 8000)
│   ├── download_data.py           # Databento data fetcher
│   ├── compare_tv.py              # Compare Python vs TradingView results
│   ├── sync_data.py               # Cloudflare R2 data sync
│   └── run_{asset}_{session}_*.py # Per-asset optimization/sweep/pipeline scripts
└── data/                          # git-ignored
    ├── raw/                       # 5m + 1m OHLCV CSVs ({SYMBOL}_5m.csv, {SYMBOL}_1m.csv)
    ├── cache/                     # Parquet caches (keyed by file hash)
    └── results/                   # experiments.db (SQLite) + synced to R2
```

## Architecture

### Data Pipeline
1. **Source**: Databento 1-min OHLCV bars, resampled to 5m and stored in `data/raw/`
   - Both `{SYMBOL}_5m.csv` and `{SYMBOL}_1m.csv` are saved (use `--save-1m` flag)
   - Index futures (NQ, ES, YM, etc.) use `.c.0` calendar roll
   - Commodity futures (GC, MGC) use `.v.0` volume-based roll (liquidity concentrates in specific months)
   - Gaps during market hours are forward-filled with last close (volume=0) so the engine sees continuous bars
2. **Caching**: Parquet files keyed by MD5 hash of source CSV, stored in `data/cache/`
3. **Warmup**: Loads 30 days before `start_date` for ATR initialization
4. **Timezone**: All timestamps in America/New_York (Eastern)

### Signal Generation (Vectorized)
- `daily_atr.py`: Resample 5m → daily, Wilder's ATR, map back via searchsorted
- `orb.py`: Accumulate high/low during ORB window per session-day (Numba)
- `fvg.py`: 3-candle pattern detection, ATR-based gap filtering, ORB directional filter
- `session.py`: Time window masks, cross-midnight session-day IDs, half-day handling

### Trade Simulation (Numba)
Two-phase design in `simulator.py`:
1. **Extract candidates**: First long + first short FVG per session-day (vectorized)
2. **Simulate fills/exits**: Numba JIT loop per candidate

Exit types:
- `EXIT_NO_FILL` (0): Limit order never triggered
- `EXIT_SL` (1): Stop loss before TP1
- `EXIT_TP1_TP2` (2): Partial at TP1, full target at TP2
- `EXIT_TP1_BE` (3): Partial at TP1, then breakeven stop
- `EXIT_TP1_EOD` (4): Partial at TP1, then end-of-day exit
- `EXIT_EOD` (5): End-of-day exit, no TP1
- `EXIT_TP2_SINGLE` (6): Single contract, full target

One-trade-per-day is enforced per strategy/session run: when multiple signals exist on the same session-day, only the first to fill is taken. Portfolio scripts that merge multiple legs/sessions intentionally allow overlapping trades across legs.

### Config System
Frozen dataclasses (hashable for caching):
- `Instrument`: symbol, point_value, min_tick, commission, data_file
- `SessionConfig`: name, time windows, ATR-based stop/gap params
- `StrategyConfig`: rr, tp1_ratio, risk_usd, atr_length, sessions, instrument

`with_overrides()` supports session-prefixed params: `ny_stop_atr_pct=12`, `asia_min_gap_atr_pct=1.5`

#### Hard Trade Constraints (NEVER override)

These are enforced at both config creation and trade execution. Any attempt to create a config or run a backtest that violates them will raise an error or be clamped by the engine:

1. **`rr >= 1.0`** — Minimum 1:1 reward-to-risk. Validated in `StrategyConfig.__post_init__()`.
2. **`tp1_ratio * rr >= 1.0`** — TP1 distance from entry must be >= stop distance. Validated in `__post_init__()` and clamped in the simulator (`tp1_dist = max(tp1_dist, risk_pts)`).
3. **Stop >= 5% of daily ATR** — Applied in the simulator after computing stop_dist from any source (ATR, ORB, structural). `stop_dist = max(stop_dist, 0.05 * atr)`.

These apply to all engine variants: ORB+FVG (`simulator.py`), qualifying move (`qualifying_move.py`). Do not add param ranges or grid values that violate constraints 1-2 — they will raise `ValueError` at config creation time.

### Production Strategy

> **Note:** The `orb_continuation/` package and `production_config()` function have been removed. Production configs are now defined per-asset in individual run/save scripts rather than a centralized location. When comparing against a baseline, use the config from the relevant save script (e.g., `scripts/save_nq_ny_r20_final.py`) or query the experiment DB for the saved baseline run.

### Instruments
NQ, MNQ, ES, MES, YM, MYM, RTY (indices) + GC, MGC, CL, MCL (commodities). Primary: NQ ($20/pt, 0.25 tick).

### Optimization

### From-Scratch Strategy Workflow

When starting from scratch with a new strategy or strategy variant, use this workflow:

1. **Start with the thesis and the asset learnings**
   - Read the relevant `learnings/asset/{ASSET}.md` file first.
   - Define the strategy family clearly: continuation, inversion, LSI, VWAP, gap fill, regime specialist, etc.
   - Decide the instrument, session, direction bias, and rough execution logic before sweeping.

2. **Build a baseline, not a winner**
   - Create a simple baseline config or baseline script with reasonable defaults.
   - Run a full-history pre-holdout backtest to confirm the strategy is structurally alive.
   - Reject obviously dead ideas early: too few trades, no edge, pathological DD shape, or strategy logic that only works in a tiny slice of history.

3. **Freeze a final hold-out before discovery**
   - Reserve the most recent `12-24` months as the final untouched hold-out.
   - Do not let baseline screening, variable sweeps, discovery ranking, or structural tuning touch this hold-out.
   - Bailey posture matters more than any single backtest metric.

4. **Run exploratory sweeps on pre-holdout data only**
   - Use `strategy-optimizer`, per-asset sweep scripts, or manual variable sweeps to explore the search space.
   - Start coarse, then narrow.
   - Sweep only `2-3` dimensions at a time unless the user explicitly wants a broader brute-force pass.
   - Track how many rounds and combinations were tried.

5. **Use `discovery-pipeline` to promote candidates**
   - `discovery-pipeline` is the pre-holdout robustness workflow.
   - Its job is not final live approval. Its job is to turn a noisy search space into a frozen shortlist.
   - Rank candidates by combined OOS behavior, walk-forward retention, and local plateau stability.
   - Prefer stable neighborhoods over single-point maxima.
   - Promote a very small shortlist: ideally `1` leader plus at most `1-2` challengers.

6. **Hand frozen candidates into `phase-one-robust-pipeline`**
   - `phase-one-robust-pipeline` is downstream of discovery.
   - It evaluates whether a promoted all-weather candidate can reach first payout fast enough and often enough to justify the funded-account model.
   - Do not use phase one as the primary parameter search loop.

7. **Save the winning config only after downstream validation**
   - Once a candidate survives the downstream pipeline, save the final config/result.
   - Update the relevant `learnings/asset/{ASSET}.md` with the final conclusion, key evidence, and DB run IDs.

In short:

`baseline -> exploratory sweeps -> discovery-pipeline -> phase-one-robust-pipeline -> save final candidate`

#### Variable Sweep Discipline — CRITICAL RULE
**Every time the anchor config changes, all variable sweeps must be rerun from scratch.**

Parameter sensitivities interact. A dimension that appeared insensitive at anchor A may be highly sensitive at anchor B, and vice versa. Skipping re-sweeps after an anchor change leads to a suboptimal or mischaracterized final config.

The full sweep-and-grid loop:
1. **Set anchor** — initial config from structural exploration or previous iteration
2. **Variable sweeps** — sweep each dimension independently (ORB window, ATR length, entry_end, flat_start, direction, DOW exclusion, max_gap_points, etc.), holding all others at anchor
3. **Update anchor** — adopt the best value from each sweep
4. **If anchor changed significantly** → return to step 2 (re-sweep everything on the new anchor)
5. **Fine-tune winners** — sweep the most impactful dimensions at higher resolution around their winning values
6. **Grid sweep** — sweep all continuous params (stop × rr × min_gap × tp1) together in the winning structural config region
7. **Anchor changed again?** → return to step 2
8. **Discovery pipeline** — only run the pre-holdout robustness/promotion workflow once the anchor has stabilized
9. **Phase-one robust pipeline** — evaluate the frozen promoted shortlist on first-payout economics

This applies even if sweeps previously showed a dimension was "insensitive" — that result was anchor-specific. Common examples:
- ATR length: appeared optimal at 50 with old config, then 14 with new ORB, then possibly 12 or 16 after stop changes
- DOW exclusion: Mon+Fri showed +3.5 Calmar on one anchor; magnitude can shift on another
- Entry end: borderline between 11:00 and 12:00 can flip with different stop/rr profiles

Scripts follow naming convention `run_{asset}_variable_sweeps_{N}.py` where N increments with each anchor change.

- Grid search: `param=start:stop:step` or `param=v1,v2,v3`
- Parallel via multiprocessing.Pool
- Results saved to `experiments.db` in `data/results/`

### Risk Context
Traded on prop firm accounts. Risk unit = R.

**Primary optimization objective: Calmar ratio (Avg Annual R ÷ |Max DD R|).**

Absolute drawdown in R is NOT a hard constraint. Position sizing can always be scaled down to bring dollar drawdown within prop firm limits. A strategy with -15R DD and 15 R/yr (Calmar 1.0) is identical in practice to -10R DD and 10 R/yr — just trade at 2/3 the position size. What cannot be fixed by sizing is a low Calmar.

Optimization priority order:
1. **Calmar** — primary objective, always
2. **0 negative full years** — consistency across all full calendar years
3. **Sharpe** — secondary, useful for walk-forward objective
4. **Net R / Avg Annual R** — only meaningful relative to DD (i.e., as Calmar)

Do NOT use a fixed DD threshold (e.g., "must be < 10R") as a hard filter during optimization. Report DD alongside Calmar so the user can set position size accordingly.

### Prop Firm Phase 1 — Staggered Account Model

The primary deployment model: start a fresh funded account every 2 weeks, each running indefinitely until it reaches **+5R** (payout) or **-4R** (breach).

**How it works:**
- New account starts every 14 calendar days (staggered)
- Each account trades independently with unlimited time horizon
- Multiple accounts are alive simultaneously
- An account resolves as PAYOUT (+5R), BREACH (-4R), or remains OPEN

**Key metrics:**
- **Success Rate** = payouts / (payouts + breaches) — only resolved accounts
- **EV per Account** = mean R outcome (capped at +5/-4 for resolved, current R for open)
- **Avg Days to Payout/Breach** — how long until resolution
- **Open accounts avg R** — forward trajectory indicator

**Optimization workflow after discovery** (see `phase-one-robust-pipeline` skill):
1. Take a frozen promoted candidate from `discovery-pipeline`
2. Convert combined OOS behavior into funded-account first-payout outcomes
3. Simulate staggered accounts on the candidate or very small frozen shortlist
4. Rank by payout rate, EV per attempt, and time to payout
5. Report detailed account-by-account breakdowns

**Reference script:** `scripts/run_nq_lsi_propfirm_sweep.py` — complete working example with `simulate_staggered_accounts()` function.

**What makes a good config for this model:**
- Success rate >80%, EV per account >+2R
- No breach clusters >3 consecutive (regime sensitivity)
- Open accounts trending positive (avg open R > 0)
- Time to payout <200 days (capital efficiency)

### Results & Metrics
All CLI output and reporting uses **R (risk units)** — never raw USD PnL. Metrics include: win rate, profit factor, Sharpe, Sortino, Calmar, Net R, Max DD (R), avg R, streaks, exit type breakdown, R by year/month/weekday. Results persisted to SQLite (`experiments.db`) with config, summary, equity curve, and trade list.

**IMPORTANT: Every backtest run must be saved to the remote DB** using `results_to_dict()` + `save_backtest_result()` (which dual-writes to local SQLite and the remote API). The frontend dashboard reads from the remote DB, so results that aren't saved there are invisible. Always include `include_trades=True` and `include_equity_curve=True` when saving.

**Execution-profile exception:** if the user wants a historical run of a profile from `execution/config/exec_configs.json`, do **not** manually recreate that profile in the research backtester and save it through `results_to_dict()` / `save_backtest_result()`. Use the exact execution replay path instead:

- [historical_backtest.py](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/execution/src/trader/historical_backtest.py)
- [save_exact_exec_backtests.py](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/execution/scripts/save_exact_exec_backtests.py)

That path runs the live execution engines on local `5m` + `1s` parquet and saves the frontend-visible result directly to the shared DB. This is now the required path for execution-profile history because the older translated approximation layer was not guaranteed to stay 1:1 with execution logic.

For these exact execution-profile backtests, save a top-level `config.risk_usd = 5000` for dashboard/backtest R reporting. Keep the live execution sizing in the exported per-session `*_risk_usd` fields rather than using the live `$400` execution risk as the portfolio reporting R.

### API Server
FastAPI on port 8000. Endpoints for running backtests, listing/loading/deleting results, running optimizations, and per-instrument testing coverage with a manual testing plan checklist. CORS enabled for frontend at localhost:3000.

`/api/candles` serves 1-minute candle data for trade chart visualization. Prefers 1m data when available (≥50 real traded bars), falls back to 5m. Forward-filled bars (volume=0) are stripped for chart display.

### Database Tables
- `runs` — Individual backtest/optimization run results with config, metrics, trades, equity curve
- `optimizations` — Grid sweep metadata with best-by results and all combinations
- `testing_plan` — Manual checklist items per instrument for tracking what to test next

### Per-Asset Learnings

Living documents in `learnings/` track what works and what doesn't for each asset. Check the relevant file before testing a strategy — if it's already NO-GO, don't re-test. Update after every conclusion with GO/NO-GO status, key metrics, and DB experiment name. See `learnings/asset/GC.md` as the template.

### Findings Logs
Do NOT automatically record backtest/optimization results. Only append when the user explicitly says to record/log the results. Use the format documented at the top of each file.
- `FINDINGS_BACKTESTS.md` — Single backtest results (one metrics table per entry)
- `FINDINGS_PARAMATERS.md` — Optimization sweep results (three tables per entry: Best Net R, Best Sharpe, Best for Prop). Use Net R and Max DD (R) — never raw USD PnL. All values are normalized to risk units (R = risk_usd per trade).
