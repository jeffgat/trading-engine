# Common Workflows

## Running a Single Backtest

### Via CLI

```bash
cd python && uv run python scripts/run_backtest.py \
  --instrument NQ \
  --sessions ny \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --name "baseline NQ NY" \
  --notes "Default params, full year"
```

Key CLI flags:
- `--instrument`: NQ, MNQ, ES
- `--sessions`: ny, asia, ldn (comma-separated for multi-session)
- `--start` / `--end`: Date range (YYYY-MM-DD)
- `--risk-usd`: Dollar risk per trade (default 5000)
- `--rr`: Reward-to-risk ratio (default 2.5)
- `--tp1-ratio`: TP1 size ratio (default 0.5)
- `--be-offset-ticks`: Breakeven offset in ticks (default 4)
- `--atr-length`: ATR period (default 14)
- `--stop-atr-pct` / `--ny-stop-atr-pct` / etc.: Stop as % of ATR
- `--min-gap-atr-pct` / `--ny-min-gap-atr-pct`: Min FVG size as % of ATR
- `--max-gap-points` / `--ny-max-gap-points`: Max FVG size in points
- `--plot`: Show equity curve and monthly returns
- `--name` / `--notes`: Experiment metadata
- `--no-save`: Skip saving to disk

Results auto-save to `experiments.db` (SQLite in `data/results/`).

### Via API

```bash
curl -X POST http://localhost:8000/api/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "instrument": "NQ",
    "sessions": ["ny"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "risk_usd": 5000,
    "rr": 2.5,
    "name": "baseline NQ NY"
  }'
```

### Programmatic

```python
from orb_backtest.config import StrategyConfig, NY_SESSION
from orb_backtest.data.loader import load_5m_data
from orb_backtest.data.instruments import INSTRUMENTS
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

instrument = INSTRUMENTS["NQ"]
config = StrategyConfig(instrument=instrument, sessions=(NY_SESSION,))
df = load_5m_data(instrument.data_file, start="2024-01-01", end="2024-12-31")
trades = run_backtest(df, config)
metrics = compute_metrics(trades, config)
```

## Running an Optimization Sweep

### Via CLI

```bash
cd python && uv run python scripts/run_optimize.py \
  --instrument NQ \
  --sessions ny \
  --start 2024-01-01 \
  --end 2024-12-31 \
  --sweep ny_stop_atr_pct=5:25:2.5 \
  --sweep rr=1.5,2.0,2.5,3.0 \
  --name "stop+rr sweep" \
  --workers 4
```

Sweep spec formats:
- Range: `param=start:end:step` (e.g., `rr=1.0:3.0:0.5`)
- Explicit: `param=val1,val2,val3` (e.g., `rr=1.5,2.0,2.5`)

### Via API

```bash
curl -X POST http://localhost:8000/api/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "instrument": "NQ",
    "sessions": ["ny"],
    "start_date": "2024-01-01",
    "end_date": "2024-12-31",
    "sweep": {
      "ny_stop_atr_pct": "5:25:2.5",
      "rr": "1.5,2.0,2.5,3.0"
    },
    "name": "stop+rr sweep"
  }'
```

## Querying Experiments

```bash
# Recent runs
cd python && uv run python scripts/query_experiments.py --limit 10

# Filter by instrument and min Sharpe
cd python && uv run python scripts/query_experiments.py \
  --instrument NQ --min-sharpe 1.0

# Compare specific runs
cd python && uv run python scripts/query_experiments.py \
  --compare 1,5,12

# Filter by parameter value
cd python && uv run python scripts/query_experiments.py \
  --param rr --min-val 2.0 --max-val 3.0

# Export to CSV
cd python && uv run python scripts/query_experiments.py \
  --instrument NQ --csv results.csv
```

## Starting the API Server

```bash
cd python && uv run python scripts/run_server.py
# Starts on http://localhost:8000
# Docs at http://localhost:8000/docs
```

## Downloading Market Data

```bash
cd python && uv run python scripts/download_data.py \
  --symbol NQ \
  --start 2023-01-01 \
  --end 2024-12-31

# Estimate cost first
cd python && uv run python scripts/download_data.py \
  --symbol NQ --start 2023-01-01 --end 2024-12-31 --cost-only
```

## Comparing with TradingView

```bash
cd python && uv run python scripts/compare_tv.py \
  --tv-csv path/to/tradingview_export.csv \
  --instrument NQ \
  --sessions ny
```

## Syncing Data to R2

```bash
# Manual upload
cd python && uv run python scripts/sync_data.py upload

# Manual download
cd python && uv run python scripts/sync_data.py download

# Auto-watch mode (runs via LaunchAgent)
cd python && uv run python scripts/sync_data.py watch
```
