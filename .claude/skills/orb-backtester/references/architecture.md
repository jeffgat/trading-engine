# Architecture Reference

## Project Layout

```
python/
  src/orb_backtest/
    config.py              # Instrument, SessionConfig, StrategyConfig, with_overrides()
    errors.py              # BacktestError + error catalog (8 factory functions)
    api.py                 # FastAPI server (11 endpoints)
    experiments.py         # SQLite experiment tracking
    engine/
      simulator.py         # Numba trade sim + orchestrator (710 lines)
    signals/
      fvg.py               # FVG detection, fully vectorized
      orb.py               # ORB levels via Numba
      session.py           # Session time masks, session-day boundaries
      daily_atr.py         # Daily ATR mapped to 5m bars
    results/
      metrics.py           # compute_metrics() — 30+ fields
      export.py            # Save/load/list/delete backtests and optimizations
    optimize/
      grid.py              # generate_param_grid(), linspace_range()
      parallel.py          # run_sweep() with multiprocessing Pool
    viz/
      equity.py            # plot_equity_curve(), plot_monthly_returns()
    data/
      loader.py            # load_5m_data() from CSV
      instruments.py       # NQ, MNQ, ES instrument registry
  scripts/
    run_backtest.py        # CLI for single backtests
    run_optimize.py        # CLI for grid sweep optimization
    run_server.py          # uvicorn launcher for FastAPI
    download_data.py       # Databento historical data downloader
    compare_tv.py          # Compare Python results vs TradingView export
    query_experiments.py   # CLI for querying experiment DB
    sync_data.py           # Cloudflare R2 sync
  data/
    raw/                   # NQ_5m.csv, MNQ_5m.csv, ES_5m.csv
    cache/                 # Parquet cached data
    results/               # Saved backtest JSONs + experiments.db
    optimizations/         # Saved optimization sweep JSONs
```

## Execution Model

**Hybrid vectorized + Numba approach:**

1. **Signal generation** (vectorized NumPy/Pandas): Session masks, ORB levels, FVG detection, daily ATR
2. **Trade simulation** (Numba @njit): `_simulate_single_trade()` handles fill scanning, partial TP, breakeven stops
3. **One trade per session-day**: When both long and short setups exist, the first-to-fill wins

## Configuration Hierarchy

Three frozen dataclasses:

```
Instrument          → symbol, point_value, min_tick, commission, data_file, exchange_tz
  └─ SessionConfig  → time windows, ATR-based filters (stop_atr_pct, min_gap_atr_pct, max_gap_points)
      └─ StrategyConfig → risk params, sessions tuple, instrument, half_days, excluded_dates, experiment metadata
```

**Default sessions:** NY (09:30-09:45 ORB), Asia (20:00-20:15 ORB), London (03:00-03:15 ORB)

**`with_overrides()`** creates new configs with session-prefixed keys like `ny_stop_atr_pct`.

## Trade Lifecycle (Exit Types)

| Code | Name | Description |
|------|------|-------------|
| 0 | EXIT_NO_FILL | Limit order never filled |
| 1 | EXIT_SL | Full stop loss |
| 2 | EXIT_TP1_TP2 | Partial TP1 then full TP2 |
| 3 | EXIT_TP1_BE | Partial TP1 then breakeven stop |
| 4 | EXIT_TP1_EOD | Partial TP1 then end-of-day flat |
| 5 | EXIT_EOD | End-of-day flat (no TP1 hit) |
| 6 | EXIT_TP2_SINGLE | Single contract, full target hit |

## TradeResult Schema (NamedTuple, 17 fields)

date, session, direction, signal_bar, fill_bar, entry_price, stop_price, tp1_price, tp2_price, exit_type, exit_bar, pnl_points, pnl_usd, r_multiple, qty, half_qty, gap_size, risk_points

## API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/instruments` | GET | List all registered instruments |
| `/api/sessions` | GET | List default session configs |
| `/api/backtest` | POST | Run single backtest with config overrides |
| `/api/backtests` | GET | List saved backtest results |
| `/api/backtests/{id}` | GET | Load specific backtest |
| `/api/backtests/{id}` | DELETE | Delete specific backtest |
| `/api/optimize` | POST | Run grid sweep optimization |
| `/api/optimizations` | GET | List saved optimizations |
| `/api/optimizations/{id}` | GET | Load specific optimization |
| `/api/optimizations/{id}` | DELETE | Delete specific optimization |
| `/api/experiments` | GET | Query experiment DB with filters |
| `/api/experiments/compare` | GET | Compare specific experiment runs |
| `/api/experiments/{id}` | GET | Get single experiment detail |

## Instruments Registry

| Symbol | point_value | min_tick | commission | data_file |
|--------|-------------|----------|------------|-----------|
| NQ | 20.0 | 0.25 | 0.05 | NQ_5m.csv |
| MNQ | 2.0 | 0.25 | 0.05 | MNQ_5m.csv |
| ES | 50.0 | 0.25 | 0.05 | ES_5m.csv |

## Dependencies

Core: numpy>=1.26, pandas>=2.1, numba>=0.59, matplotlib>=3.8, seaborn>=0.13, pyarrow>=14.0, tabulate>=0.9

Optional: databento (data), boto3+watchdog (storage), fastapi+uvicorn (api), pytest (dev)

Runtime: `python/.venv` managed with `uv`
