# ORB+FVG Python Backtester

Custom backtesting engine for the Opening Range Breakout + Fair Value Gap strategy. Uses vectorized signal generation (numpy/pandas) with a Numba-compiled trade simulator for limit orders and partial exits.

## Quick Start

```bash
cd python
uv sync

# Single backtest
uv run python scripts/run_backtest.py --data NQ_5m.csv --instrument NQ --sessions NY

# With experiment label
uv run python scripts/run_backtest.py --data NQ_5m.csv --name "baseline" --notes "default params, NY only"

# Parameter sweep
uv run python scripts/run_optimize.py --data NQ_5m.csv --sweep ny_stop_atr_pct=5:25:1

# Start API + frontend
uv run python scripts/run_server.py
```

## Development Flow

The Pine Script workflow of creating `v5_atr.pine`, `v5_sweeps.pine`, etc. for each experiment doesn't translate well to Python. Here's how to approach it instead:

### Parameter experiments → use config overrides

Don't copy files. The config system parameterizes everything — session times, ATR percentages, gap filters, R:R. What would be `v5_atr.pine` vs `v5_fixed_gaps.pine` in Pine is just different `--ny-stop-atr-pct` values here.

```bash
# Testing wider stops
uv run python scripts/run_backtest.py --data NQ_5m.csv \
  --ny-stop-atr-pct 20 --name "wider_stops" --notes "testing 20% vs default 15%"

# Testing tighter gaps
uv run python scripts/run_backtest.py --data NQ_5m.csv \
  --ny-min-gap-atr-pct 2.5 --name "tight_gaps"
```

For systematic sweeps:

```bash
uv run python scripts/run_optimize.py --data NQ_5m.csv \
  --sweep ny_stop_atr_pct=5:25:1 --sweep rr=1.5,2.0,2.5,3.0
```

### Structural changes → use git branches

New entry logic, exit types, or simulation mechanics belong in git branches — not duplicated scripts.

```
main                      ← production-equivalent config
feat/reentry-on-sl        ← what would be v6_x_reentry_on_sl.pine
feat/respected-gaps       ← what would be v6_x_respected_gaps.pine
```

The code diff is the documentation. When a branch proves out, merge it.

### Tracking results → use saved JSON + labels

Every backtest auto-saves to `data/results/` with full config, metrics, and trade list. Use `--name` and `--notes` to tag what you were testing:

```bash
# CLI
uv run python scripts/run_backtest.py --data NQ_5m.csv \
  --name "asia_5pct_stops" --notes "confirming Asia session with 5% ATR stops"

# API (POST /api/backtest)
{"instrument": "NQ", "sessions": ["NY", "Asia"], "name": "multi_session_v1"}
```

Result files are named: `{timestamp}_{instrument}_{sessions}_{name}.json`

The dashboard history panel shows the name label on each run for quick identification.

### Comparing runs → use the dashboard or JSON

- **Dashboard**: Run backtests and browse history in the sidebar. Named runs show their label.
- **CLI**: Results print a formatted summary to stdout after each run.
- **JSON**: Load any saved result from `data/results/` for programmatic comparison.

### Summary

| Pine Script approach | Python equivalent |
|---|---|
| New file per variant (`v5_atr.pine`) | Different config params via `--flags` |
| HEAD files for canonical versions | `main` branch + default config |
| Visual comparison in TradingView | Dashboard history / saved JSON |
| New entry model (`v6_x_*.pine`) | Git branch (`feat/...`) |
| Keeping old versions around | Git history + saved result JSON |

## Data Sync (Cloudflare R2)

Market data and results in `data/` are stored in Cloudflare R2 so all collaborators can share them. The `data/` directory is gitignored.

### Setup

1. Copy the env template and fill in your R2 credentials:
   ```bash
   cp .env.example .env
   # Edit .env with your R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY
   ```

2. Sync:
   ```bash
   uv run --extra storage python scripts/sync_data.py upload          # push local → R2
   uv run --extra storage python scripts/sync_data.py download        # pull R2 → local
   uv run --extra storage python scripts/sync_data.py upload raw      # sync only raw/
   ```

## Project Structure

```
python/
├── src/orb_backtest/
│   ├── config.py              # Strategy config (frozen dataclasses)
│   ├── api.py                 # FastAPI server
│   ├── data/
│   │   ├── instruments.py     # Instrument specs (NQ, ES, YM, etc.)
│   │   └── loader.py          # CSV → Parquet caching
│   ├── engine/
│   │   └── simulator.py       # Numba-compiled trade simulation
│   ├── signals/
│   │   ├── fvg.py             # FVG detection (vectorized)
│   │   ├── orb.py             # ORB high/low per session
│   │   ├── daily_atr.py       # Daily ATR calculation
│   │   └── session.py         # Session time masking
│   ├── optimize/
│   │   ├── grid.py            # Parameter grid generation
│   │   └── parallel.py        # Multiprocessing sweep runner
│   ├── results/
│   │   ├── export.py          # JSON serialization
│   │   └── metrics.py         # Trade metrics (Sharpe, PF, etc.)
│   └── viz/
│       ├── equity.py          # Equity curve plotting
│       └── heatmap.py         # Parameter sweep heatmaps
├── scripts/
│   ├── run_backtest.py        # Single backtest CLI
│   ├── run_optimize.py        # Grid sweep CLI
│   ├── run_server.py          # FastAPI launcher
│   ├── compare_tv.py          # TradingView report comparison
│   └── download_data.py       # Databento data fetcher
├── data/
│   ├── raw/                   # 5-min OHLCV CSVs
│   ├── cache/                 # Parquet caches
│   └── results/               # Saved backtest JSON
└── tests/
```

## CLI Reference

### run_backtest.py

```
--data            Data file (required)
--instrument      Symbol: NQ, ES, YM, MNQ, etc. (default: NQ)
--sessions        Comma-separated: NY,Asia,LDN (default: NY)
--start/--end     Date range (YYYY-MM-DD)
--name            Experiment label
--notes           Free-text notes
--rr              Risk-reward ratio
--risk-usd        Dollar risk per trade
--ny-stop-atr-pct NY stop as % of ATR
--output          Custom output path
--plot            Show equity curve
--quiet           Minimal output
```

### run_optimize.py

```
--sweep key=start:end:step    Range sweep (e.g. rr=1.5:3.5:0.5)
--sweep key=v1,v2,v3          Discrete values
--workers N                   Parallel processes (default: CPU count)
--heatmap                     2D parameter heatmap
```
