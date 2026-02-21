---
name: new-variable
description: >
  Add a new tracked strategy parameter to the experiment database and frontend.
  This skill should be used when adding a new variable, param, or column to the
  runs table, or when the user says "track X in the DB", "add param X", or
  "new variable X". Handles backend (SQLite schema, migration, queries) and
  frontend (TypeScript types, history table) in a single workflow.
---

# New Variable

Add a new strategy parameter as a first-class column in `experiments.db`, with automatic migration, backfill, and frontend surfacing.

## When to Use

- User asks to add, track, or store a new strategy parameter
- User says "add param", "new variable", "track X in the database"
- A new config field needs to appear in the history API and dashboard

## Do NOT Use When

- Adding a new metric (those live in `metrics_json`, not param columns)
- Adding a new instrument or session (different workflow)
- Modifying the backtest engine logic itself

## Workflow

### Step 1: Gather Requirements

Determine from the user:

1. **Parameter name** — snake_case (e.g. `commission_usd`, `ny_min_orb_range`)
2. **SQLite type** — `REAL` (float), `INTEGER` (int), or `TEXT` (string)
3. **Scope** — global (always present) or per-session (nullable, prefixed with `ny_`/`asia_`/`ldn_`)
4. **Show in history table?** — whether to add a visible column in `BacktestHistoryPanel.tsx`

Load `references/architecture.md` for naming conventions and column categories.

### Step 2: Backend — Add to PARAM_COLUMNS

Edit `python/src/orb_backtest/experiments.py`:

1. Add an entry to the `PARAM_COLUMNS` dict at the top of the file. Place it in the correct section (Global, NY, Asia, or LDN).

```python
PARAM_COLUMNS: dict[str, str] = {
    # Global
    "rr": "REAL",
    ...
    "new_param": "REAL",  # <-- add here
}
```

2. If the param is **global** (always present), also add it to the `_GLOBAL_PARAMS` set:

```python
_GLOBAL_PARAMS = {"rr", "tp1_ratio", "risk_usd", "atr_length", "new_param"}
```

No other backend changes needed — the migration, INSERT, SELECT, and query filter logic all derive from `PARAM_COLUMNS` automatically.

### Step 3: Verify Config Produces the Value

Confirm the param key exists in the config dict produced by `results_to_dict()` in `python/src/orb_backtest/results/export.py`. The key in the config dict must match the `PARAM_COLUMNS` key exactly.

If the param is new to `StrategyConfig`, also add it to:
- `python/src/orb_backtest/config.py` — the `StrategyConfig` dataclass
- `python/src/orb_backtest/results/export.py` — the `config_dict` in `results_to_dict()`

### Step 4: Frontend — Add TypeScript Type

Edit `frontend/src/lib/types.ts`:

Add the field to the `BacktestHistoryItem` interface. Use `?` for optional (session params) or required (global params):

```typescript
export interface BacktestHistoryItem {
  ...
  new_param?: number;  // <-- add here
}
```

### Step 5: Frontend — Add Table Column (Optional)

If the param should be visible in the history table, edit `frontend/src/components/BacktestHistoryPanel.tsx`:

1. Add a `<th>` header in the `<thead>` section (use `SortHeader` for sortable, plain `<th>` otherwise)
2. Add a matching `<td>` cell in the row mapping
3. If using `SortHeader`, add the key to the `SortKey` type union

### Step 6: Verify

1. Run syntax check: `cd python && uv run python -c "from orb_backtest.experiments import PARAM_COLUMNS; print(PARAM_COLUMNS)"`
2. Run frontend type check: `cd frontend && npx tsc --noEmit`
3. If an existing DB exists, restart the API to trigger migration: `cd python && uv run uvicorn orb_backtest.api:app`
4. Query to confirm: `sqlite3 python/data/results/experiments.db "PRAGMA table_info(runs)" | grep new_param`

## Error Handling

| Error | Recovery |
|-------|----------|
| Migration fails on existing DB | Check column name doesn't conflict with existing columns. Run `PRAGMA table_info(runs)` to inspect. |
| Param always NULL after backfill | The key in `PARAM_COLUMNS` doesn't match the key in `config_json`. Check `results_to_dict()` output. |
| Frontend type error | Ensure the field name in `BacktestHistoryItem` exactly matches the API response key. |
| Per-session param showing for wrong session | Session params must be prefixed with `ny_`, `asia_`, or `ldn_`. Do not add to `_GLOBAL_PARAMS`. |
