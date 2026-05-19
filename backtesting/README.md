# Backtesting Engine

Python research engine for ORB/FVG, LSI, VWAP, gap-fill, news, regime, and portfolio workflows. Signals are generated mostly from 5m futures data; 1m/1s data is used where available for drill-down, charting, and exact fill/exits.

## Quick Start

```bash
uv sync --extra data --extra storage --extra api --extra dev

uv run python scripts/run_backtest.py \
  --data NQ_5m.csv --instrument NQ --sessions NY \
  --name "NQ NY Baseline"

uv run python scripts/run_optimize.py \
  --data NQ_5m.csv --instrument NQ --sessions NY \
  --sweep ny_stop_atr_pct=5:25:1 \
  --name "NQ NY stop sweep"

uv run python scripts/run_server.py       # http://localhost:8000
```

## Layout

```
backtesting/
├── src/orb_backtest/
│   ├── config.py          # Instrument, SessionConfig, StrategyConfig
│   ├── api.py             # FastAPI for frontend
│   ├── experiments*.py    # local + remote experiment persistence
│   ├── data/              # loaders, instruments, fees, dates, bar mapping
│   ├── signals/           # FVG, ORB, swing/sweep, VWAP, IB, HTF/reference levels
│   ├── engine/            # ORB/FVG, QM, VWAP, gap-fill, news simulators
│   ├── optimize/          # grid/LHS/Optuna/WFO/stability/prop constraints
│   ├── analysis/          # gates, regimes, autocorrelation, conditional stats
│   └── results/           # metrics and serialization
├── scripts/               # run, sweep, pipeline, data, registry scripts
├── learnings/             # canonical research memory
├── data/                  # gitignored raw/cache/results
└── tests/
```

## Data

```bash
uv run --extra data python scripts/download_data.py NQ ES CL GC --start 2016-01-01 --save-1m
uv run python scripts/download_1s_data.py NQ --start 2024-01-01
uv run --extra storage python scripts/sync_data.py download
uv run --extra storage python scripts/sync_data.py upload
```

`data/raw` holds market data, `data/cache` holds parquet/hash caches, and `data/results` holds local evidence/results. All are gitignored.

## Conventions

- Always pass a unique descriptive `--name`.
- All research output should be in R units, not raw USD PnL.
- Timestamps/session logic are US Eastern unless a script says otherwise.
- `run_backtest()` enforces one trade per strategy/session day; portfolio scripts may intentionally allow overlaps across independent legs.
- Hard constraints: `rr >= 1.0`, `tp1_ratio * rr >= 1.0`, final stop distance >= `5%` daily ATR.

## Learnings

Read before testing:

1. `learnings/README.md`
2. `learnings/briefs/GLOBAL.md`
3. `learnings/briefs/assets/{ASSET}.md`

After meaningful conclusions, update detailed learnings with metrics and DB experiment names, then regenerate:

```bash
uv run python backtesting/scripts/build_learnings_registry.py
```

## Execution Profile Exception

Historical runs for `execution/config/exec_configs.json` profiles must use exact execution replay, not a hand-built research config:

```bash
cd ../execution
PYTHONUNBUFFERED=1 .venv/bin/python scripts/save_exact_exec_backtests.py \
  --profiles FAST_V1.1 FAST_V2.1 GENERAL_V1 \
  --years 5
```
