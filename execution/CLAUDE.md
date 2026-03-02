# Execution Service

Live execution engine for the ORB+FVG continuation strategy. Streams market data from DataBento, detects setups, and sends bracket orders to TradersPost webhooks.

## Architecture

```
DataBento (1m+1s bars)  →  Feed (aggregates to 5m)  →  ORBEngine (state machine)  →  TradersPost (webhooks)
                                                     →  FastAPI Dashboard (REST + WS)   →  React Frontend
```

- **Feed** (`feed.py`): DataBento live connection, 1m→5m aggregation, 1s tick forwarding, daily ATR
- **Engine** (`engine.py`): Per-session state machine (IDLE → ORB_BUILDING → SCANNING → ARMED → MANAGING → FLAT)
- **Broker** (`broker.py`): TradersPost webhook client — entry brackets, TP1 partial exits, BE stop moves, flatten
- **Sizing** (`sizing.py`): `TradeLevels` computation — entry, stop, tp1, tp2, breakeven, position size
- **API** (`api.py`): FastAPI dashboard with REST endpoints + WebSocket streaming
- **Main** (`main.py`): CLI entry point, config loading, 5-leg portfolio definition

## Deployment

### Droplet Details

- **Host**: `143.110.148.234` (DigitalOcean, Ubuntu 24.04, 1 vCPU / 1 GB RAM)
- **App directory**: `/opt/orb-trader/`
- **Systemd service**: `orb-trader.service`
- **Secrets**: `/opt/orb-trader/.env` (DATABENTO_API_KEY, TRADERSPOST_WEBHOOK_URL)
- **Dashboard API**: port 8000 (uvicorn, bound to 0.0.0.0)

### Deploy Changes

After pushing to the `execution-service` branch, deploy to the droplet:

```bash
# From repo root:
bash execution/deploy/deploy.sh
```

This rsyncs source files (excluding .venv, .env, logs), runs `uv sync`, and restarts the service.

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
cd execution/python

# Dry-run (default — logs webhooks but doesn't send)
uv run orb-trader

# Live mode (sends real webhooks)
uv run orb-trader --live

# Replay historical data
uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01

# Custom config
uv run orb-trader --config config/live.toml
```

## Frontend

The React dashboard lives at `frontend/` (merged with backtesting dashboard). In development, Vite proxies `/exec-api/*` to the droplet at `143.110.148.234:8000` and `/bt-api/*` to port 8100.

```bash
cd frontend
npm run dev          # Dev server at localhost:5173
npm run build        # Production build → dist/
```

## Configuration

- **Config file**: `config/live.toml` — portfolio sessions, risk params, dates
- **Secrets**: `.env` file — API keys (never committed)
- **5-leg portfolio**: Defined in `main.py` SESSION_CONFIGS — NQ NY, NQ Asia, GC NY, ES NY, ES Asia

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
- **Dry-run default**: All webhooks log only unless `--live` is explicitly passed
