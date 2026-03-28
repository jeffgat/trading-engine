# Execution Service

Live execution engine for ORB+FVG and LSI strategies. Streams market data from DataBento, detects setups, and sends bracket orders to TradersPost webhooks.

## Architecture

```
DataBento (1m+1s bars)  →  Feed (aggregates to 5m)  →  ORBEngine / LSIEngine  →  TradersPost (webhooks)
                                                     →  FastAPI Dashboard (REST + WS)  →  React Frontend
```

### Core Modules (`src/trader/`)

- **`feed.py`**: DataBento live connection, 1m→5m aggregation per symbol, 1s tick forwarding, daily ATR (multiple lengths per symbol), front-month contract election by volume, `preload_intraday_5m()` for mid-session restart recovery, `ReplayFeed` for historical CSV replay
- **`engine.py`**: ORB+FVG per-session state machine (`ORBEngine`):
  `IDLE → ORB_BUILDING → WAITING_FOR_GAP → ARMED_LIMIT → FILLED → MANAGING → FLAT → IDLE`
- **`lsi_engine.py`**: LSI reversal per-session state machine (`LSIEngine`):
  `IDLE → SCANNING → WAITING_FOR_GAP → COLLECTING_GAPS → WAITING_FOR_INVERSION → ARMED_LIMIT → MANAGING → FLAT`
- **`swing.py`**: Stateful bar-by-bar swing pivot detection and sweep tracking, used by `LSIEngine`
- **`broker.py`**: `TradersPostClient` — webhook client for entry brackets, TP1 partials, BE stop moves, flatten. `MultiBroker` — fan-out to multiple webhooks for multi-account execution
- **`sizing.py`**: `TradeLevels` computation — entry, stop, tp1, tp2, breakeven, position size
- **`api.py`**: FastAPI dashboard with REST endpoints + WebSocket streaming
- **`main.py`**: CLI entry point, config loading, portfolio definition (continuation + LSI sessions)
- **`checkpoint.py`**: Trade state persistence to JSON (`config/checkpoint.json`, `config/trade_history.json`) for crash recovery
- **`overrides.py`**: Runtime config override system persisted to `config/overrides.json`; defines `EDITABLE_FIELDS` and `LSI_EDITABLE_FIELDS`
- **`position_limits.py`**: `ContractCapManager` — shared per-config contract cap across engines; `resize_trade_levels()` helper
- **`logging_config.py`**: `setup_logging()` — console + rotating file handlers with ET-timezone formatting

## Deployment

### Droplet Details

- **Host**: `143.110.148.234` (DigitalOcean, Ubuntu 24.04)
- **App directory**: `/opt/orb-trader/`
- **Systemd service**: `orb-trader.service`
- **Secrets**: `/opt/orb-trader/.env` (DATABENTO_API_KEY, TRADERSPOST_WEBHOOK_URL)
- **Dashboard API**: port 8000 (uvicorn, bound to 0.0.0.0)

### Deploy Changes

Deploy rsyncs from the local `execution/` directory (whatever branch is checked out — no git operations in the script):

```bash
# From repo root:
bash execution/deploy/deploy.sh
```

This rsyncs source files (excluding .venv, .env, logs, and live runtime state files like checkpoint.json, trade_history.json, exec_configs.json, overrides.json), runs `uv sync`, restarts the service, and verifies it's listening on port 8000.

### Manual Deploy (individual commands)

```bash
# Sync files
rsync -avz --delete --exclude '.venv/' --exclude '__pycache__/' --exclude '.env' --exclude 'logs/' \
    execution/ root@143.110.148.234:/opt/orb-trader/

# Restart
ssh root@143.110.148.234 "cd /opt/orb-trader && uv sync && systemctl restart orb-trader"
```

### Verify Deployment

```bash
# Check service is running
ssh root@143.110.148.234 "systemctl status orb-trader --no-pager"

# Check API is listening
ssh root@143.110.148.234 "ss -tlnp | grep 8000"

# Check recent logs
ssh root@143.110.148.234 "journalctl -u orb-trader -n 50 --no-pager"

# Test API endpoint
curl http://143.110.148.234:8000/api/status
```

### Service Management (on droplet)

```bash
systemctl status orb-trader       # Check status
systemctl restart orb-trader      # Restart
systemctl stop orb-trader         # Stop
journalctl -u orb-trader -f       # Follow logs live
journalctl -u orb-trader -n 100   # Last 100 log lines
```

### Initial Setup (one-time)

For a fresh droplet, see `deploy/setup.sh` and `deploy/install-service.sh`.

## Running Locally

```bash
cd execution

# Run (configs with webhooks send live; others are dry-run)
uv run orb-trader

# Replay historical data (always dry-run)
uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01

# Custom config
uv run orb-trader --config config/live.toml
```

## Frontend

The React dashboard lives at `frontend/` (repo root, merged with backtesting dashboard). In development, Vite proxies `/exec-api/*` to the droplet at `143.110.148.234:8000` and `/bt-api/*` to `localhost:8000`.

```bash
cd frontend
npm run dev          # Dev server at localhost:5173
npm run build        # Production build → dist/
```

## Configuration

- **Config file**: `config/live.toml` — portfolio sessions, risk params, dates
- **Exec configs**: `config/exec_configs.json` — multi-account execution profiles (webhook URLs, session subsets, risk overrides)
- **Runtime overrides**: `config/overrides.json` — live-editable params (written by `overrides.py`)
- **Checkpoint state**: `config/checkpoint.json` + `config/trade_history.json` — crash-recovery persistence
- **Secrets**: `.env` file — API keys (never committed)
- **Portfolio sessions**: Defined in `main.py` — 6 continuation legs (`NQ_NY`, `NQ_Asia`, `GC_NY`, `ES_NY`, `ES_Asia`, `NQ_LDN`) + 2 LSI legs (`NQ_Asia_LSI`, `NQ_NY_LSI`)
- **Trade concurrency**: one-trade-per-session-day is enforced within each engine instance; portfolio legs/sessions run independently, so concurrent positions across legs are allowed by design

## Timezone Convention

**All times are US Eastern (America/New_York).** This applies to:

- Session config times (`orb_start`, `entry_end`, `flat_start`, etc.) in `main.py` and `live.toml`
- `Bar.timestamp` — the feed converts DataBento UTC timestamps to ET before passing to the engine
- Log timestamps — both `trader.log` and `trades.log` use ET via `_ETFormatter`
- Half-day flat times in `config/live.toml`

Eastern Time automatically handles EST/EDT transitions (UTC-5 in winter, UTC-4 in summer). The timezone is defined as `ZoneInfo("America/New_York")` in `feed.py` and `logging_config.py`.

## Key Design Decisions

- **async for** on DataBento client: The feed loop must use `async for record in client:` (not sync `for`), otherwise it blocks the event loop and uvicorn never binds
- **Dual-resolution bars**: 5m for signals (ORB, FVG), 1s for fill/exit precision
- **OCO simulation**: TradersPost doesn't have native OCO — the broker uses `cancel: true/false` sequencing to maintain BE stop + TP2 limit simultaneously
- **Idempotent flatten**: `{"action": "exit"}` is safe to send redundantly — TradersPost treats it as a no-op if no position exists
- **Auto-derived dry-run**: Each execution config is live if it has webhooks, dry-run if it doesn't — no global flag needed
- **MultiBroker fan-out**: Multi-account execution routes the same order to multiple TradersPost webhook URLs simultaneously
- **Crash recovery**: Checkpoint persistence writes trade state to JSON on every state transition; on restart, `preload_intraday_5m()` rebuilds bar state and the checkpoint restores trade positions
