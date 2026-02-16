# New Variable Architecture

## Single Source of Truth

All strategy param columns are defined in one place:

```
python/src/orb_backtest/experiments.py → PARAM_COLUMNS dict
```

This dict drives:
- **Schema DDL**: Column definitions in `_SCHEMA` are generated from `PARAM_COLUMNS`
- **Migration**: `init_db()` auto-adds missing columns via `ALTER TABLE` and backfills from `config_json`
- **INSERT**: `log_run()` extracts `config.get(col)` for every key in `PARAM_COLUMNS`
- **SELECT**: `list_backtest_history()` selects all `PARAM_COLUMNS` keys
- **Query filters**: `query_runs()` uses direct column filters for keys in `PARAM_COLUMNS`

## File Locations

| File | Purpose |
|------|---------|
| `python/src/orb_backtest/experiments.py` | `PARAM_COLUMNS` dict + `_GLOBAL_PARAMS` set |
| `frontend/src/lib/types.ts` | `BacktestHistoryItem` interface |
| `frontend/src/components/BacktestHistoryPanel.tsx` | History table columns |

## Column Categories

- **Global params** (`_GLOBAL_PARAMS` set): Always included in API response (e.g. `rr`, `tp1_ratio`, `risk_usd`)
- **Session params**: Only included when non-null (e.g. `ny_stop_atr_pct`, `asia_min_gap_atr_pct`)

## Naming Convention

- Global params: snake_case matching `StrategyConfig` field name (e.g. `rr`, `atr_length`)
- Session params: `{session_prefix}_{param_name}` (e.g. `ny_stop_atr_pct`, `ldn_max_gap_points`)
- Session prefixes: `ny`, `asia`, `ldn`

## SQLite Types

| Python type | SQLite type |
|-------------|-------------|
| `float`     | `REAL`      |
| `int`       | `INTEGER`   |
| `str`       | `TEXT`      |
