# ORB+FVG Trading System

Opening Range Breakout strategies with Fair Value Gap entries for futures markets. Includes Pine Script strategies for TradingView, a Python backtesting engine, and a React dashboard for visualizing results.

## Project Structure

```
├── pinescript/            # TradingView Pine Script strategies & indicators
│   ├── orb_continuation/  # ORB continuation strategies (main model)
│   ├── orb_reversal/      # ORB reversal strategies
│   ├── ilm/               # ILM (internal liquidity model) strategies
│   ├── indicators/        # Standalone indicators (EMA, FVG, ICT killzones, etc.)
│   └── atlas_indicators/  # Custom ATR and ORB indicators
├── python/                # Python backtesting engine
│   ├── scripts/           # CLI scripts (backtest, optimize, compare, download)
│   ├── src/orb_backtest/  # Core backtester package
│   ├── data/raw/          # Raw 5m OHLCV CSVs
│   └── data/cache/        # Parquet cache for faster loads
├── frontend/              # React + TypeScript dashboard (Vite + Tailwind)
├── tradingview_reports/   # Exported trade reports from TradingView
└── test.pine              # FVG visualization indicator for debugging
```

## Pine Script Strategies

Located in [`pinescript/`](pinescript/). All strategies run on **5-minute charts** in TradingView.

### ORB Continuation (`pinescript/orb_continuation/`)

The main model. Detects opening range breakouts and enters on FVG retests with partial take-profits and breakeven stops.

- **[HEAD_testing_a.pine](pinescript/orb_continuation/HEAD_testing_a.pine)** — Canonical testing version with 3 sessions (NY, Asia, London)
- **[HEAD_prod_v5.pine](pinescript/orb_continuation/HEAD_prod_v5.pine)** — Production version with TradersPost alerts (NY + Asia)
- **HEAD_testing_b/c.pine** — A/B test variants
- **v1–v7** — Historical iterations exploring different entry types, stop methods, and filters

### Other Models

- **[`orb_reversal/`](pinescript/orb_reversal/)** — Mean reversion after ORB breakouts (early stage)
- **[`ilm/`](pinescript/ilm/)** — Internal liquidity model strategies
- **[`indicators/`](pinescript/indicators/)** — Standalone indicators (EMA, FVG/orderblocks, ICT killzones, swing highs/lows)

### Key Trading Logic

- **FVG detection**: 3-candle pattern where bar[2] high < bar[0] low (bullish) or bar[2] low > bar[0] high (bearish)
- **Entry**: Limit order at FVG retest level
- **Stop**: Low/high of the "before" candle (bar[2]), sized as a % of daily ATR
- **TP1**: 50% position at R:R midpoint, then move stop to breakeven
- **TP2**: Remaining position at full R:R target
- **Sessions**: NY (09:30–09:45 ORB), Asia (09:00–09:30 JST), London

## Python Backtester

Located in [`python/`](python/). Custom backtesting engine built for limit-order strategies with partial exits — something signal-based frameworks like vectorbt can't handle.

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Setup

```bash
cd python
uv sync                      # install dependencies
uv sync --extra data         # + Databento for data downloads
uv sync --extra api          # + FastAPI for the dashboard API
```

### Download Data

Fetches 5-minute OHLCV bars from [Databento](https://databento.com) (free $125 credits on signup).

```bash
export DATABENTO_API_KEY=db-your-key-here

# Download NQ front-month continuous
python scripts/download_data.py NQ --start 2015-01-01

# Download multiple instruments
python scripts/download_data.py NQ ES CL GC --start 2016-01-01

# Estimate cost before downloading
python scripts/download_data.py NQ ES --start 2015-01-01 --cost-only
```

Supported instruments: NQ, MNQ, ES, MES, YM, MYM, RTY, GC, MGC, CL, MCL

Data is saved to `python/data/raw/{SYMBOL}_5m.csv`.

### Run a Backtest

```bash
cd python

# Default parameters on NQ
python scripts/run_backtest.py --data NQ_5m.csv

# With date range and custom parameters
python scripts/run_backtest.py --data NQ_5m.csv --start 2020-01-01 --end 2025-01-01 --rr 3.0

# Multiple sessions
python scripts/run_backtest.py --data NQ_5m.csv --sessions NY,Asia

# With equity curve plot
python scripts/run_backtest.py --data NQ_5m.csv --plot

# Save results as JSON
python scripts/run_backtest.py --data NQ_5m.csv --output results.json
```

### Run Parameter Optimization

Grid sweep across parameter combinations with parallel execution.

```bash
cd python

# Sweep stop ATR% and min gap ATR%
python scripts/run_optimize.py --data NQ_5m.csv \
    --sweep ny_stop_atr_pct=5:25:1 \
    --sweep ny_min_gap_atr_pct=0.5:3.0:0.25

# Sweep R:R and TP1 ratio with heatmap
python scripts/run_optimize.py --data NQ_5m.csv \
    --sweep rr=1.5:4.0:0.5 \
    --sweep tp1_ratio=0.3:0.7:0.1 \
    --heatmap
```

### Compare Against TradingView

Validates Python backtest results against TradingView strategy exports to ensure parity.

```bash
cd python

python scripts/compare_tv.py \
    --tv-csv ../tradingview_reports/YOUR_EXPORT.csv \
    --data NQ_5m.csv \
    --start 2024-01-01 --end 2025-01-01
```

### Architecture

- **Hybrid approach**: Vectorized signal generation (numpy/pandas) + Numba-compiled trade simulation
- **Config**: Frozen dataclasses (hashable for caching)
- **Data pipeline**: Databento CSVs, cached as Parquet for fast reloads
- Primary instrument: NQ ($20/pt, 0.25 tick size)

## Frontend Dashboard

Located in [`frontend/`](frontend/). A React + TypeScript dashboard for running backtests and visualizing results, built with Vite and Tailwind CSS.

### Setup & Run

```bash
# Start the API server (from python/)
cd python
uv sync --extra api
python scripts/run_server.py         # runs on http://localhost:8000

# Start the frontend (from frontend/)
cd frontend
npm install
npm run dev                          # runs on http://localhost:5173
```

The dashboard connects to the Python API server to run backtests and display equity curves, trade statistics, and performance metrics.

### Build for Production

```bash
cd frontend
npm run build    # outputs to frontend/dist/
```

## Current Strategy Parameters (Pine Defaults)

| Parameter | NY | Asia | London |
|---|---|---|---|
| Stop (ATR %) | 15% | 5% | 10% |
| Min gap (ATR %) | 1.75% | 0.7% | 1% |
| Max gap (points) | 100 | 50 | 50 |
| R:R | 2.5 | 2.5 | 2.5 |
| TP1 ratio | 0.5 | 0.5 | 0.5 |
| ATR length | 14 | 14 | 14 |
| BE offset (ticks) | 4 | 4 | 4 |

## Execution Pipeline

TradingView (Pine Script alerts) → TradersPost → Broker

Optimal strategies are prefixed with `HEAD_`. Notes and ideas specific to each model are in `NOTES.md` within the respective directory.
