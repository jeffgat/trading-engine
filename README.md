# Trading Backtests

Workspace for futures strategy research, live execution, dashboards, and TradingView parity.

## Layout

```
├── backtesting/   # Python research engine, sweeps, data sync, learnings, experiment DB
├── execution/     # DataBento -> execution engines -> TradersPost service
├── frontend/      # React dashboard for research + execution
└── pinescript/    # TradingView references and alert-parity scripts
```

## Quick Start

```bash
# Frontend + local backtesting API
./start-dev.sh
```

Or run each service manually:

```bash
# Backtesting API
cd backtesting
uv sync --extra data --extra storage --extra api --extra dev
uv run python scripts/run_server.py

# Frontend
cd ../frontend
npm install
npm run dev

# Execution service
cd ../execution
uv sync
uv run orb-trader
```

Frontend routes:

- `/` — backtesting/research
- `/execution` — live execution

Vite proxies `/bt-api/*` to `BACKTESTING_API_TARGET`; `./start-dev.sh` sets that to local `localhost:8000`, while a standalone frontend run falls back to the remote backtesting API. `/exec-api/*` uses the deployed execution API unless `EXECUTION_API_TARGET` is overridden.

## Common Tasks

```bash
# Single research run
cd backtesting
uv run python scripts/run_backtest.py \
  --data NQ_5m.csv --instrument NQ --sessions NY \
  --name "NQ NY Baseline"

# Parameter sweep
uv run python scripts/run_optimize.py \
  --data NQ_5m.csv --instrument NQ --sessions NY \
  --sweep ny_stop_atr_pct=5:25:1 \
  --name "NQ NY stop sweep"

# Data sync
uv run --extra storage python scripts/sync_data.py download
uv run --extra storage python scripts/sync_data.py upload

# Deploy execution service
cd ..
bash execution/deploy/deploy.sh
```

## Research Memory

Before strategy work, always load the required briefing layer directly:

1. `backtesting/learnings/README.md`
2. `backtesting/learnings/briefs/GLOBAL.md`
3. `backtesting/learnings/briefs/assets/{SYMBOL}.md`

Use local research memory as the routing layer when prior work is unknown, for
example "have we tested this?" or "which report covers this gate?":

```bash
cd backtesting
uv run python scripts/research_memory.py index
uv run python scripts/research_memory.py ask "Have we tested NQ Asia ORB strict stress?"
```

Treat retrieved chunks as a map, not the final source of truth. Open and read
the cited learnings/reports before making a conclusion. Use experiment queries,
saved result artifacts, and deterministic replay/stress runs for metrics and
promotion decisions.

After updating detailed learnings or adding reports:

```bash
uv run python backtesting/scripts/build_learnings_registry.py
```

## Execution Profile Backtests

For historical runs of profiles from `execution/config/exec_configs.json`, use exact execution replay:

```bash
cd execution
PYTHONUNBUFFERED=1 .venv/bin/python scripts/save_exact_exec_backtests.py \
  --profiles FAST_V1.1 FAST_V2.1 GENERAL_V1 \
  --years 5
```

## More Detail

- [backtesting/README.md](backtesting/README.md)
- [execution/README.md](execution/README.md)
- [frontend/README.md](frontend/README.md)
- [pinescript/CLAUDE.md](pinescript/CLAUDE.md)
