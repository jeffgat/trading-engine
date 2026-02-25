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
python/
├── src/
│   ├── core/                      # Shared engine (all strategies use this)
│   │   ├── config.py              # Frozen dataclass configs (Instrument, SessionConfig, StrategyConfig)
│   │   ├── data/
│   │   │   ├── instruments.py     # Instrument definitions (NQ, ES, YM, GC, CL, etc.)
│   │   │   └── loader.py          # CSV → Parquet loading with hash-based caching
│   │   ├── engine/
│   │   │   └── simulator.py       # Core trade simulator (Numba-compiled)
│   │   ├── signals/
│   │   │   ├── fvg.py             # FVG detection (vectorized)
│   │   │   ├── orb.py             # ORB level computation (Numba)
│   │   │   ├── session.py         # Session time windows + cross-midnight handling
│   │   │   └── daily_atr.py       # Daily ATR, SMA, EMA, ROC, ADX, Donchian
│   │   ├── optimize/
│   │   │   ├── grid.py            # Parameter grid generation
│   │   │   └── parallel.py        # Multiprocessing sweep executor
│   │   ├── analysis/
│   │   │   └── pre_trade_gates.py # Gate simulation (trend, streak, volatility, etc.)
│   │   ├── results/
│   │   │   ├── metrics.py         # Performance metrics (Sharpe, Sortino, drawdown, etc.)
│   │   │   └── export.py          # Result serialization + DB persistence
│   │   └── viz/
│   │       └── equity.py          # Equity curve + monthly returns plots
│   ├── orb_continuation/          # Continuation strategy (bullish FVG → long)
│   │   ├── config.py              # Session defaults + production_config()
│   │   └── api.py                 # FastAPI server for frontend
│   └── orb_reversal/              # Reversal strategy (bullish FVG → short)
│       └── config.py              # Session defaults (strategy="reversal")
├── scripts/
│   ├── run_backtest.py            # CLI: single backtest with param overrides
│   ├── run_optimize.py            # CLI: grid search parameter sweep
│   ├── run_server.py              # FastAPI launcher (port 8000)
│   ├── download_data.py           # Databento data fetcher
│   ├── compare_tv.py              # Compare Python vs TradingView results
│   └── sync_data.py               # Cloudflare R2 data sync
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

One-trade-per-day enforced: when multiple signals exist on same session-day, only the first to fill is taken.

### Config System
Frozen dataclasses (hashable for caching):
- `Instrument`: symbol, point_value, min_tick, commission, data_file
- `SessionConfig`: name, time windows, ATR-based stop/gap params
- `StrategyConfig`: rr, tp1_ratio, risk_usd, atr_length, sessions, instrument

`with_overrides()` supports session-prefixed params: `ny_stop_atr_pct=12`, `asia_min_gap_atr_pct=1.5`

### Production Strategy

The **production strategy** is the current best no-gate NY+Asia combined config, defined as the single source of truth in `config.py`. All scripts that need the production baseline import from here — never hardcode these params locally.

**Defined in:** `src/orb_continuation/config.py` → `production_config()`, `PROD_NY_SESSION`, `PROD_ASIA_SESSION`, `PROD_NY_GLOBALS`, `PROD_ASIA_GLOBALS`

**Parameters** (from 2024-2025 NQ grid sweep + Bayesian refinement):

| Param | NY | Asia |
|-------|-----|------|
| stop_atr_pct | 6.75 | 4.75 |
| min_gap_atr_pct | 2.5 | 3.0 |
| max_gap_atr_pct | 25.0 | 8.0 |
| rr | 3.25 | 2.0 |
| tp1_ratio | 0.55 | 0.4 |


**Baseline performance** (NQ, Jan 2016 — Dec 2025):

| Metric | Value |
|--------|-------|
| Trades | 2362 |
| Win Rate | 47.1% |
| Total R | 304.9 |
| Sharpe | 1.593 |
| Calmar | 10.62 |
| Max DD | $-144K |
| PF | 1.25 |

**Usage** — when testing variants (gates, filters, new params), always compare against the production baseline:

```python
from orb_continuation.config import production_config

# Returns list of per-session StrategyConfigs [ny_cfg, asia_cfg]
configs = production_config()  # or production_config(instrument)

# Run and merge
all_trades = []
for cfg in configs:
    all_trades.extend(run_backtest(df, cfg, start_date=start))
all_trades.sort(key=lambda t: t.date)

# For metadata dicts, import the constants directly:
from orb_continuation.config import (
    PROD_NY_SESSION, PROD_ASIA_SESSION,
    PROD_NY_GLOBALS, PROD_ASIA_GLOBALS,
)
```

**When updating production params**: change only `config.py` — all scripts will pick up the new values automatically.

### Instruments
NQ, MNQ, ES, MES, YM, MYM, RTY (indices) + GC, MGC, CL, MCL (commodities). Primary: NQ ($20/pt, 0.25 tick).

### Optimization

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
8. **Robust pipeline** — only run WF + prop constraints + holdout + MC when the anchor has stabilized

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

### Results & Metrics
All CLI output and reporting uses **R (risk units)** — never raw USD PnL. Metrics include: win rate, profit factor, Sharpe, Sortino, Calmar, Net R, Max DD (R), avg R, streaks, exit type breakdown, R by year/month/weekday. Results persisted to SQLite (`experiments.db`) with config, summary, equity curve, and trade list.

### API Server
FastAPI on port 8000. Endpoints for running backtests, listing/loading/deleting results, running optimizations, and per-instrument testing coverage with a manual testing plan checklist. CORS enabled for frontend at localhost:3000.

`/api/candles` serves 1-minute candle data for trade chart visualization. Prefers 1m data when available (≥50 real traded bars), falls back to 5m. Forward-filled bars (volume=0) are stripped for chart display.

### Database Tables
- `runs` — Individual backtest/optimization run results with config, metrics, trades, equity curve
- `optimizations` — Grid sweep metadata with best-by results and all combinations
- `testing_plan` — Manual checklist items per instrument for tracking what to test next

### Per-Asset Learnings

Living documents in `learnings/` track what works and what doesn't for each asset. Check the relevant file before testing a strategy — if it's already NO-GO, don't re-test. Update after every conclusion with GO/NO-GO status, key metrics, and DB experiment name. See `learnings/GC.md` as the template.

### Findings Logs
Do NOT automatically record backtest/optimization results. Only append when the user explicitly says to record/log the results. Use the format documented at the top of each file.
- `FINDINGS_BACKTESTS.md` — Single backtest results (one metrics table per entry)
- `FINDINGS_PARAMATERS.md` — Optimization sweep results (three tables per entry: Best Net R, Best Sharpe, Best for Prop). Use Net R and Max DD (R) — never raw USD PnL. All values are normalized to risk units (R = risk_usd per trade).
