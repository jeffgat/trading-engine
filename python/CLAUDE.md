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
    ├── raw/                       # 5-min OHLCV CSVs
    ├── cache/                     # Parquet caches (keyed by file hash)
    └── results/                   # experiments.db (SQLite) + synced to R2
```

## Architecture

### Data Pipeline
1. **Source**: Databento CSVs (5-min OHLCV), stored in `data/raw/`
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
- `StrategyConfig`: rr, tp1_ratio, risk_usd, atr_length, be_offset_ticks, sessions, instrument

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
| be_offset_ticks | 4 | 4 |

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
- Grid search: `param=start:stop:step` or `param=v1,v2,v3`
- Parallel via multiprocessing.Pool
- Results saved to `experiments.db` in `data/results/`

### Risk Context
Traded on prop firm accounts. Risk unit = R. Accounts breach at ~8-10R drawdown. Acceptable to breach 1-2x/year if payout collection and ROI multiple justify it. Optimize Sharpe/max drawdown with 8-10R as the hard ceiling; lower is better.

### Results & Metrics
Metrics include: win rate, profit factor, Sharpe, Sortino, max drawdown (USD, %, R), avg R, streaks, exit type breakdown, PnL by year/month/weekday. Results persisted to SQLite (`experiments.db`) with config, summary, equity curve, and trade list.

### API Server
FastAPI on port 8000. Endpoints for running backtests, listing/loading/deleting results, running optimizations, and per-instrument testing coverage with a manual testing plan checklist. CORS enabled for frontend at localhost:3000.

### Database Tables
- `runs` — Individual backtest/optimization run results with config, metrics, trades, equity curve
- `optimizations` — Grid sweep metadata with best-by results and all combinations
- `testing_plan` — Manual checklist items per instrument for tracking what to test next

### Findings Logs
Do NOT automatically record backtest/optimization results. Only append when the user explicitly says to record/log the results. Use the format documented at the top of each file.
- `FINDINGS_BACKTESTS.md` — Single backtest results (one metrics table per entry)
- `FINDINGS_PARAMATERS.md` — Optimization sweep results (three tables per entry: Best Net R, Best Sharpe, Best for Prop). Use Net R and Max DD (R) — never raw USD PnL. All values are normalized to risk units (R = risk_usd per trade).
