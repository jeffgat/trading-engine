# Agent Instructions

This `AGENTS.md` file is the canonical instruction file for execution work. `CLAUDE.md` is only a compatibility pointer for Anthropic tooling.

Live/dry execution service: DataBento 1m/1s -> feed -> ORB/LSI/specialist engines -> TradersPost, with FastAPI REST/WebSocket for the dashboard.

Commands:

```bash
uv sync
uv run pytest
uv run orb-trader
uv run orb-trader --config config/live.toml
uv run orb-trader --replay /path/to/NQ_5m.csv --start 2025-01-01
bash deploy/deploy.sh
```

Core map: `main.py` loads `config/live.toml` and `config/exec_configs.json`, builds engines, wires DataBento/API/checkpoints; `feed.py` aggregates 1m to 5m, forwards 1s ticks, computes ATR, and can stream optional MBP-10 order-book samples; `engine.py` is `ORBEngine`; `lsi_engine.py` is `LSIEngine`; `goldx_engine.py` and `hunter_orb_engine.py` are specialists; `broker.py` is TradersPost plus `MultiBroker`; `sizing.py` computes levels/qty; `api.py` serves dashboard controls; `checkpoint.py` persists restart state; `historical_backtest.py` replays live engines exactly.

Runtime invariants:

- All session/config/log times are US Eastern.
- 5m bars drive signals; 1s bars are authoritative for fills/exits when available. Preserve cross-midnight session handling.
- Signal data uses full-size futures while execution usually maps to micros via `SIGNAL_TO_EXEC` in `main.py`.
- `exec_configs.json` defines enabled profiles, sessions, LSI sessions, max contract caps, and webhooks. Missing/empty webhooks mean dry-run; configured webhooks can send live orders.
- Checkpoint and trade-history files live under `config/`; state changes should request checkpoints so restarts do not duplicate stale entries/exits.
- Keep order-book MBP-10 disabled unless intentionally validating cost-bearing live order-book features (`[orderbook]` in `live.toml`).

Historical profile validation:

```bash
PYTHONUNBUFFERED=1 .venv/bin/python scripts/save_exact_exec_backtests.py --profiles FAST_V1.1 FAST_V2.1 GENERAL_V1 --years 5
```

Use this exact replay for saved execution-profile history. `uv run orb-trader --replay ...` is only for narrow single-symbol engine debugging.

Deployment target is `/opt/orb-trader/` on `143.110.148.234` via `orb-trader.service`; deploy from repo root with `bash execution/deploy/deploy.sh` or from this directory with `bash deploy/deploy.sh`.
