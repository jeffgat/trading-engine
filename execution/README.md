# Execution Service

Live/dry execution service for ORB/FVG, LSI, and specialist variants.

```
DataBento 1m/1s -> Feed -> ORBEngine/LSIEngine/specialists -> TradersPost
                                      -> FastAPI REST/WS -> frontend
```

## Quick Start

```bash
uv sync
uv run orb-trader
uv run orb-trader --config config/live.toml
uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01
```

`--replay` is for narrow single-symbol debugging. Saved profile history uses exact replay below.

## Layout

```
execution/
├── src/trader/       # feed, engines, broker, API, sizing, checkpoints, overrides
├── scripts/          # exact historical replay and ops helpers
├── config/           # live.toml, exec_configs.json, overrides/checkpoints
└── deploy/           # droplet setup/deploy scripts
```

## Exact Historical Backtests

For profiles in `config/exec_configs.json`:

```bash
PYTHONUNBUFFERED=1 .venv/bin/python scripts/save_exact_exec_backtests.py \
  --profiles FAST_V1.1 FAST_V2.1 GENERAL_V1 \
  --years 5
```

This runs the live engines on local 5m + 1s parquet and saves frontend-compatible results to the shared DB.

## Deployment

Production:

- Host: `143.110.148.234`
- App dir: `/opt/orb-trader/`
- Service: `orb-trader.service`
- API: `http://143.110.148.234:8000/api/status`

Deploy from repo root:

```bash
bash execution/deploy/deploy.sh
```

Check status/logs:

```bash
ssh root@143.110.148.234 "systemctl status orb-trader --no-pager"
ssh root@143.110.148.234 "journalctl -u orb-trader -n 100 --no-pager"
ssh root@143.110.148.234 "journalctl -u orb-trader -f"
```

## Runtime Notes

- All session/config/log times are US Eastern.
- 5m bars drive signals; 1s bars drive fills/exits where available.
- Each engine allows one trade per session day; independent profiles/legs may overlap.
- Webhook presence determines live vs dry-run behavior.
