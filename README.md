# ORB+FVG Trading System

Opening Range Breakout strategies with Fair Value Gap entries for futures markets. Includes a Python backtesting engine and a React dashboard for visualizing results.

## Project Structure

```
├── python/                # Python backtesting engine
│   ├── scripts/           # CLI scripts (backtest, optimize, compare, download)
│   ├── src/orb_backtest/  # Core backtester package
│   ├── data/raw/          # Raw 5m OHLCV CSVs
│   └── data/cache/        # Parquet cache for faster loads
├── frontend/              # React + TypeScript dashboard (Vite + Tailwind)
└── pinescript/            # Legacy Pine Script strategies (archived)
```

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

## Default Strategy Parameters

| Parameter | NY | Asia | London |
|---|---|---|---|
| Stop (ATR %) | 15% | 5% | 10% |
| Min gap (ATR %) | 1.75% | 0.7% | 1% |
| Max gap (points) | 100 | 50 | 50 |
| R:R | 2.5 | 2.5 | 2.5 |
| TP1 ratio | 0.5 | 0.5 | 0.5 |
| ATR length | 14 | 14 | 14 |
| BE offset (ticks) | 4 | 4 | 4 |
