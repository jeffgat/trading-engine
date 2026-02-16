"""SQLite experiment tracking for backtest and optimization runs."""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "results" / "experiments.db"

# ---------------------------------------------------------------------------
# Single source of truth for strategy param columns.
# To add a new param: just add an entry here. The schema DDL, migrations,
# log_run(), list_backtest_history(), and query_runs() all derive from this.
# ---------------------------------------------------------------------------
PARAM_COLUMNS: dict[str, str] = {
    # Global
    "rr": "REAL",
    "tp1_ratio": "REAL",
    "risk_usd": "REAL",
    "atr_length": "INTEGER",
    "be_offset_ticks": "INTEGER",
    "min_qty": "REAL",
    "qty_step": "REAL",
    "point_value": "REAL",
    # NY session
    "ny_stop_atr_pct": "REAL",
    "ny_min_gap_atr_pct": "REAL",
    "ny_max_gap_points": "REAL",
    "ny_orb_window": "TEXT",
    "ny_entry_window": "TEXT",
    "ny_flat_window": "TEXT",
    # Asia session
    "asia_stop_atr_pct": "REAL",
    "asia_min_gap_atr_pct": "REAL",
    "asia_max_gap_points": "REAL",
    "asia_orb_window": "TEXT",
    "asia_entry_window": "TEXT",
    "asia_flat_window": "TEXT",
    # London session
    "ldn_stop_atr_pct": "REAL",
    "ldn_min_gap_atr_pct": "REAL",
    "ldn_max_gap_points": "REAL",
    "ldn_orb_window": "TEXT",
    "ldn_entry_window": "TEXT",
    "ldn_flat_window": "TEXT",
}

# Params that are always present (non-nullable) vs per-session (nullable)
_GLOBAL_PARAMS = {"rr", "tp1_ratio", "risk_usd", "atr_length", "be_offset_ticks",
                  "min_qty", "qty_step", "point_value"}

# ---------------------------------------------------------------------------
# Metric columns promoted from json_extract to dedicated columns.
# Same self-driving pattern: DDL, migration, backfill, INSERT, SELECT all
# derive from this dict.
# ---------------------------------------------------------------------------
METRIC_COLUMNS: dict[str, str] = {
    "total_pnl_usd": "REAL",
    "win_rate": "REAL",
    "sharpe_ratio": "REAL",
    "max_drawdown_usd": "REAL",
    "profit_factor": "REAL",
    "sortino_ratio": "REAL",
    "calmar_ratio": "REAL",
}

_param_ddl = ",\n    ".join(f"{col} {dtype}" for col, dtype in PARAM_COLUMNS.items())
_metric_ddl = ",\n    ".join(f"{col} {dtype}" for col, dtype in METRIC_COLUMNS.items())

_SCHEMA = f"""\
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    run_type TEXT NOT NULL DEFAULT 'backtest',
    experiment_name TEXT,
    notes TEXT,
    git_hash TEXT,
    config_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    total_trades INTEGER NOT NULL,
    result_file TEXT,
    sessions TEXT,
    instrument TEXT,
    date_start TEXT,
    date_end TEXT,
    {_param_ddl},
    {_metric_ddl}
);
"""

_OPTIMIZATIONS_SCHEMA = """\
CREATE TABLE IF NOT EXISTS optimizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    result_id TEXT NOT NULL UNIQUE,
    timestamp TEXT NOT NULL,
    git_hash TEXT,
    instrument TEXT,
    sessions TEXT,
    total_combinations INTEGER NOT NULL,
    swept_params_json TEXT NOT NULL,
    best_by_sharpe_json TEXT,
    best_by_pnl_json TEXT,
    best_by_pf_json TEXT,
    all_results_json TEXT NOT NULL
);
"""

_TESTING_PLAN_SCHEMA = """\
CREATE TABLE IF NOT EXISTS testing_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    notes TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_testing_plan_instrument ON testing_plan(instrument);
"""

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db() -> Path:
    """Create the data directory and tables if they don't exist.

    Returns the path to the SQLite database file.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA)
        conn.executescript(_OPTIMIZATIONS_SCHEMA)
        conn.executescript(_TESTING_PLAN_SCHEMA)

        # Migrate: add columns to optimizations if missing
        opt_existing = {row[1] for row in conn.execute("PRAGMA table_info(optimizations)").fetchall()}
        if "experiment_name" not in opt_existing:
            conn.execute("ALTER TABLE optimizations ADD COLUMN experiment_name TEXT")

        # Migrate: add columns if missing
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        if "trades_json" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN trades_json TEXT")
        if "equity_json" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN equity_json TEXT")
        if "starred" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN starred INTEGER DEFAULT 0")
        if "hidden" not in existing:
            conn.execute("ALTER TABLE runs ADD COLUMN hidden INTEGER DEFAULT 0")

        # Migrate: add dedicated param columns
        new_param_cols: list[str] = []
        for col, dtype in PARAM_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {dtype}")
                new_param_cols.append(col)

        # Backfill newly added param columns from config_json
        if new_param_cols:
            backfill_sets = ", ".join(
                f"{col} = json_extract(config_json, '$.{col}')"
                for col in new_param_cols
            )
            conn.execute(f"UPDATE runs SET {backfill_sets} WHERE {new_param_cols[0]} IS NULL")

        # Migrate: add dedicated metric columns
        new_metric_cols: list[str] = []
        for col, dtype in METRIC_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {dtype}")
                new_metric_cols.append(col)

        # Backfill newly added metric columns from metrics_json
        if new_metric_cols:
            backfill_sets = ", ".join(
                f"{col} = json_extract(metrics_json, '$.{col}')"
                for col in new_metric_cols
            )
            conn.execute(f"UPDATE runs SET {backfill_sets} WHERE {new_metric_cols[0]} IS NULL")

    return DB_PATH


def _get_git_hash() -> str:
    """Return the current HEAD git hash, or 'unknown' on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _json_default(obj):
    """JSON serializer fallback for numpy types and infinity."""
    import math
    if isinstance(obj, float) and (math.isinf(obj) or math.isnan(obj)):
        return None
    # numpy scalar types
    type_name = type(obj).__module__
    if type_name == "numpy":
        return obj.item()
    return str(obj)


def _dumps(obj) -> str:
    """Compact JSON serialization with fallback for special types."""
    return json.dumps(obj, default=_json_default, separators=(",", ":"))


# Whitelist pattern for param filter names (alphanumeric + underscores)
_SAFE_PARAM_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

# Default param values — used to detect non-default params for auto-naming
_DEFAULT_PARAMS: dict[str, object] = {
    "rr": 2.5,
    "tp1_ratio": 0.5,
    "be_offset_ticks": 4,
    "atr_length": 14,
}


def _auto_experiment_name(
    config: dict, date_start: str, date_end: str, sessions_str: str,
) -> str:
    """Generate a human-readable experiment name from config and date range.

    Examples: ``NQ ASIA+NY 2015-2026``, ``ES NY 2024-2025 rr3``
    """
    instrument = config.get("instrument", "UNK")

    start_year = date_start[:4] if date_start and len(date_start) >= 4 else ""
    end_year = date_end[:4] if date_end and len(date_end) >= 4 else ""
    if start_year and end_year and start_year != end_year:
        year_range = f"{start_year}-{end_year}"
    elif start_year:
        year_range = start_year
    else:
        year_range = ""

    parts = [instrument, sessions_str]
    if year_range:
        parts.append(year_range)

    for param, default_val in sorted(_DEFAULT_PARAMS.items()):
        val = config.get(param)
        if val is not None and val != default_val:
            parts.append(f"{param}{val:g}" if isinstance(val, float) else f"{param}{val}")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log_run(
    result_dict: dict,
    result_id: str,
    run_type: str = "backtest",
    *,
    git_hash: str | None = None,
) -> int:
    """Insert a single run into the experiment database.

    Args:
        result_dict: Structured result dict (as produced by results_to_dict).
        result_id: Identifier for the saved result file.
        run_type: 'backtest' or 'optimization'.
        git_hash: Pre-computed git hash (avoids repeated subprocess calls in sweeps).

    Returns:
        The rowid of the newly inserted row.
    """
    init_db()

    config = result_dict["config"]
    summary = result_dict["summary"]

    # Extract session names from config keys like "ny_orb_window"
    sessions: list[str] = []
    for key in config:
        if key.endswith("_orb_window"):
            sessions.append(key.split("_")[0].upper())
    session_str = "+".join(sorted(sessions)) if sessions else ""

    # Extract date range from equity_curve or trades list
    equity_curve = result_dict.get("equity_curve", [])
    trades_list = result_dict.get("trades", [])
    dates_source = equity_curve or trades_list
    date_start = dates_source[0]["date"] if dates_source else ""
    date_end = dates_source[-1]["date"] if dates_source else ""

    # Serialize trades and equity curve
    trades_json = _dumps(trades_list) if trades_list else None
    equity_json = _dumps(equity_curve) if equity_curve else None

    experiment_name = result_dict.get("name")
    if not experiment_name:
        experiment_name = _auto_experiment_name(config, date_start, date_end, session_str)

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_type": run_type,
        "experiment_name": experiment_name,
        "notes": result_dict.get("notes"),
        "git_hash": git_hash if git_hash is not None else _get_git_hash(),
        "config_json": json.dumps(config, default=_json_default),
        "metrics_json": json.dumps(summary, default=_json_default),
        "total_trades": int(summary["total_trades"]),
        "result_file": result_id,
        "sessions": session_str,
        "instrument": config.get("instrument", ""),
        "date_start": date_start,
        "date_end": date_end,
        "trades_json": trades_json,
        "equity_json": equity_json,
        # Dedicated param columns (driven by PARAM_COLUMNS)
        **{col: config.get(col) for col in PARAM_COLUMNS},
        # Dedicated metric columns (driven by METRIC_COLUMNS)
        **{col: summary.get(col) for col in METRIC_COLUMNS},
    }

    columns = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    sql = f"INSERT INTO runs ({columns}) VALUES ({placeholders})"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid  # type: ignore[return-value]


def log_sweep_runs(
    all_results: list[tuple],
    optimization_id: str,
) -> int:
    """Log every combination from a parameter sweep.

    Args:
        all_results: List of (StrategyConfig, list[TradeResult]) tuples.
        optimization_id: Shared identifier for this sweep.

    Returns:
        The number of rows logged.
    """
    # Lazy import to avoid circular dependency
    from .results.export import results_to_dict

    # Compute git hash once for the entire sweep (avoids N subprocess calls)
    git_hash = _get_git_hash()

    count = 0
    for config, trades in all_results:
        result_dict = results_to_dict(trades, config, include_trades=False)
        log_run(result_dict, optimization_id, run_type="optimization", git_hash=git_hash)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Backtest CRUD
# ---------------------------------------------------------------------------

def get_backtest_result(result_id: str) -> dict | None:
    """Load a full backtest result from the DB by result_file ID.

    Returns a BacktestResult-shaped dict with config, summary, trades, equity_curve,
    or None if not found.
    """
    init_db()

    sql = """
        SELECT config_json, metrics_json, trades_json, equity_json,
               experiment_name, notes, result_file
        FROM runs
        WHERE result_file = ? AND run_type = 'backtest'
        ORDER BY id DESC
        LIMIT 1
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, [result_id]).fetchone()

    if row is None:
        return None

    result: dict = {
        "config": json.loads(row["config_json"]),
        "summary": json.loads(row["metrics_json"]),
    }

    if row["trades_json"]:
        result["trades"] = json.loads(row["trades_json"])
    else:
        result["trades"] = []

    if row["equity_json"]:
        result["equity_curve"] = json.loads(row["equity_json"])
    else:
        result["equity_curve"] = []

    if row["experiment_name"]:
        result["name"] = row["experiment_name"]
    if row["notes"]:
        result["notes"] = row["notes"]

    return result


def delete_backtest_run(result_id: str) -> bool:
    """Delete a backtest from the runs table by result_file. Returns True if deleted."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM runs WHERE result_file = ? AND run_type = 'backtest'",
            [result_id],
        )
        return cur.rowcount > 0


def toggle_star(result_id: str) -> bool | None:
    """Toggle the starred flag for a backtest run. Returns the new starred state, or None if not found."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT starred FROM runs WHERE result_file = ? AND run_type = 'backtest' ORDER BY id DESC LIMIT 1",
            [result_id],
        ).fetchone()
        if row is None:
            return None
        new_val = 0 if row[0] else 1
        conn.execute(
            "UPDATE runs SET starred = ? WHERE result_file = ? AND run_type = 'backtest'",
            [new_val, result_id],
        )
        return bool(new_val)


def toggle_hidden(result_id: str) -> bool | None:
    """Toggle the hidden flag for a backtest run. Returns the new hidden state, or None if not found."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT hidden FROM runs WHERE result_file = ? AND run_type = 'backtest' ORDER BY id DESC LIMIT 1",
            [result_id],
        ).fetchone()
        if row is None:
            return None
        new_val = 0 if row[0] else 1
        conn.execute(
            "UPDATE runs SET hidden = ? WHERE result_file = ? AND run_type = 'backtest'",
            [new_val, result_id],
        )
        return bool(new_val)


def list_starred(limit: int = 100) -> list[dict]:
    """Return starred backtest runs, same shape as list_backtest_history()."""
    init_db()

    param_cols = ", ".join(PARAM_COLUMNS.keys())
    metric_cols = ", ".join(METRIC_COLUMNS.keys())
    sql = f"""
        SELECT
            result_file,
            timestamp,
            instrument,
            sessions,
            experiment_name,
            notes,
            total_trades,
            date_start,
            date_end,
            starred,
            hidden,
            {param_cols},
            {metric_cols}
        FROM runs
        WHERE run_type = 'backtest' AND starred = 1
        ORDER BY id DESC
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()

    items: list[dict] = []
    for row in rows:
        sessions_str = row["sessions"] or ""
        item: dict = {
            "id": row["result_file"] or "",
            "timestamp": row["timestamp"] or "",
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "total_trades": row["total_trades"] or 0,
            "date_start": row["date_start"] or "",
            "date_end": row["date_end"] or "",
            "starred": True,
            "hidden": bool(row["hidden"]),
        }
        for col in PARAM_COLUMNS:
            val = row[col]
            if col in _GLOBAL_PARAMS or val is not None:
                item[col] = val
        for col in METRIC_COLUMNS:
            item[col] = row[col] or 0
        if row["experiment_name"]:
            item["name"] = row["experiment_name"]
        if row["notes"]:
            item["notes"] = row["notes"]
        items.append(item)

    return items


# ---------------------------------------------------------------------------
# Optimization CRUD
# ---------------------------------------------------------------------------

def log_optimization(result_dict: dict, result_id: str) -> int:
    """Insert an optimization result into the optimizations table.

    Args:
        result_dict: Grid sweep result dict (from grid_results_to_dict).
        result_id: Unique identifier for this optimization run.

    Returns:
        The rowid of the newly inserted row.
    """
    init_db()

    # Extract instrument and sessions from first result's config
    all_results = result_dict.get("all_results", [])
    instrument = ""
    sessions_set: set[str] = set()
    if all_results:
        config = all_results[0].get("config", {})
        instrument = config.get("instrument", "")
        for key in config:
            if key.endswith("_orb_window"):
                sessions_set.add(key.split("_")[0].upper())
    session_str = "+".join(sorted(sessions_set))

    # Auto-generate experiment name from instrument, sessions, swept params
    swept_params = result_dict.get("swept_params", {})
    swept_names = ", ".join(sorted(swept_params.keys())) if swept_params else ""
    n_combos = result_dict.get("total_combinations", len(all_results))
    name_parts = [instrument or "UNK", session_str or "UNK"]
    if swept_names:
        name_parts.append(swept_names)
    name_parts.append(f"({n_combos}c)")
    experiment_name = " ".join(name_parts)

    row = {
        "result_id": result_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_hash": _get_git_hash(),
        "instrument": instrument,
        "sessions": session_str,
        "experiment_name": experiment_name,
        "total_combinations": result_dict.get("total_combinations", len(all_results)),
        "swept_params_json": _dumps(result_dict.get("swept_params", {})),
        "best_by_sharpe_json": _dumps(result_dict.get("best_by_sharpe")),
        "best_by_pnl_json": _dumps(result_dict.get("best_by_pnl")),
        "best_by_pf_json": _dumps(result_dict.get("best_by_profit_factor")),
        "all_results_json": _dumps(all_results),
    }

    columns = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    sql = f"INSERT OR REPLACE INTO optimizations ({columns}) VALUES ({placeholders})"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, row)
        return cur.lastrowid  # type: ignore[return-value]


def list_optimization_history(limit: int = 100) -> list[dict]:
    """Return optimization runs shaped for the frontend OptimizationHistoryItem."""
    init_db()

    sql = """
        SELECT result_id, timestamp, instrument, sessions,
               total_combinations, swept_params_json,
               best_by_sharpe_json, best_by_pnl_json,
               experiment_name
        FROM optimizations
        ORDER BY id DESC
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()

    items: list[dict] = []
    for row in rows:
        swept_params = json.loads(row["swept_params_json"]) if row["swept_params_json"] else {}
        sessions_str = row["sessions"] or ""

        best_sharpe = 0.0
        best_pnl_usd = 0.0
        risk_usd = 50000

        if row["best_by_sharpe_json"]:
            best = json.loads(row["best_by_sharpe_json"])
            if best:
                best_sharpe = best.get("summary", {}).get("sharpe_ratio", 0)
                risk_usd = best.get("config", {}).get("risk_usd", 50000)

        if row["best_by_pnl_json"]:
            best = json.loads(row["best_by_pnl_json"])
            if best:
                best_pnl_usd = best.get("summary", {}).get("total_pnl_usd", 0)

        item: dict = {
            "id": row["result_id"],
            "timestamp": row["timestamp"],
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "risk_usd": risk_usd,
            "swept_params": list(swept_params.keys()),
            "total_combinations": row["total_combinations"],
            "best_sharpe": best_sharpe,
            "best_pnl_usd": best_pnl_usd,
        }
        if row["experiment_name"]:
            item["name"] = row["experiment_name"]
        items.append(item)

    return items


def get_optimization_result(result_id: str) -> dict | None:
    """Load a full optimization result from the DB by result_id."""
    init_db()

    sql = """
        SELECT result_id, timestamp, instrument, sessions,
               total_combinations, swept_params_json,
               best_by_sharpe_json, best_by_pnl_json, best_by_pf_json,
               all_results_json
        FROM optimizations
        WHERE result_id = ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, [result_id]).fetchone()

    if row is None:
        return None

    result: dict = {
        "total_combinations": row["total_combinations"],
        "all_results": json.loads(row["all_results_json"]),
    }

    if row["swept_params_json"]:
        result["swept_params"] = json.loads(row["swept_params_json"])

    if row["best_by_sharpe_json"]:
        val = json.loads(row["best_by_sharpe_json"])
        if val:
            result["best_by_sharpe"] = val

    if row["best_by_pnl_json"]:
        val = json.loads(row["best_by_pnl_json"])
        if val:
            result["best_by_pnl"] = val

    if row["best_by_pf_json"]:
        val = json.loads(row["best_by_pf_json"])
        if val:
            result["best_by_profit_factor"] = val

    return result


def delete_optimization_run(result_id: str) -> bool:
    """Delete an optimization from the optimizations table. Returns True if deleted."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(
            "DELETE FROM optimizations WHERE result_id = ?",
            [result_id],
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------

def query_runs(**filters) -> list[dict]:
    """Query runs with optional filters.

    Keyword Args:
        date_from: Filter timestamp >= value.
        date_to: Filter timestamp <= value.
        instrument: Exact match on instrument column.
        sessions: Exact match on sessions column (e.g. "NY" or "NY+Asia").
        min_profit_factor: Minimum profit_factor from metrics_json.
        min_sharpe: Minimum sharpe_ratio from metrics_json.
        experiment_name: LIKE match on experiment_name column.
        run_type: Exact match ('backtest' or 'optimization').
        param_filters: Dict mapping param name to (min, max) tuple,
            filtered via json_extract on config_json.
        limit: Max rows returned (default 100).

    Returns:
        List of dicts with all columns plus extracted key metrics.
    """
    init_db()

    clauses: list[str] = []
    params: list = []

    date_from = filters.get("date_from")
    if date_from is not None:
        clauses.append("timestamp >= ?")
        params.append(date_from)

    date_to = filters.get("date_to")
    if date_to is not None:
        clauses.append("timestamp <= ?")
        params.append(date_to)

    instrument = filters.get("instrument")
    if instrument is not None:
        clauses.append("instrument = ?")
        params.append(instrument)

    sessions = filters.get("sessions")
    if sessions is not None:
        clauses.append("sessions = ?")
        params.append(sessions)

    min_profit_factor = filters.get("min_profit_factor")
    if min_profit_factor is not None:
        clauses.append("profit_factor >= ?")
        params.append(min_profit_factor)

    min_sharpe = filters.get("min_sharpe")
    if min_sharpe is not None:
        clauses.append("sharpe_ratio >= ?")
        params.append(min_sharpe)

    experiment_name = filters.get("experiment_name")
    if experiment_name is not None:
        clauses.append("experiment_name LIKE ?")
        params.append(f"%{experiment_name}%")

    run_type = filters.get("run_type")
    if run_type is not None:
        clauses.append("run_type = ?")
        params.append(run_type)

    param_filters: dict[str, tuple[float, float]] | None = filters.get("param_filters")
    if param_filters:
        for param_name, (lo, hi) in param_filters.items():
            if not _SAFE_PARAM_RE.match(param_name):
                raise ValueError(f"Invalid param filter name: {param_name!r}")
            if param_name in PARAM_COLUMNS or param_name in METRIC_COLUMNS:
                clauses.append(f"{param_name} >= ?")
                params.append(lo)
                clauses.append(f"{param_name} <= ?")
                params.append(hi)
            else:
                clauses.append(f"json_extract(config_json, '$.{param_name}') >= ?")
                params.append(lo)
                clauses.append(f"json_extract(config_json, '$.{param_name}') <= ?")
                params.append(hi)

    limit = filters.get("limit", 100)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    metric_cols = ", ".join(METRIC_COLUMNS.keys())
    sql = f"""
        SELECT id, timestamp, run_type, experiment_name, notes, git_hash,
            config_json, metrics_json, total_trades, result_file,
            sessions, instrument, date_start, date_end,
            {metric_cols}
        FROM runs
        {where}
        ORDER BY id DESC
        LIMIT ?
    """
    params.append(limit)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def list_recent_runs(limit: int = 50) -> list[dict]:
    """Return the most recent runs, newest first."""
    return query_runs(limit=limit)


def list_backtest_history(limit: int = 100) -> list[dict]:
    """Return backtest runs shaped for the frontend BacktestHistoryItem.

    Returns list of dicts with: id, timestamp, instrument, sessions,
    risk_usd, total_pnl_usd, total_trades, win_rate, date_start,
    date_end, name, notes.
    """
    init_db()

    param_cols = ", ".join(PARAM_COLUMNS.keys())
    metric_cols = ", ".join(METRIC_COLUMNS.keys())
    sql = f"""
        SELECT
            result_file,
            timestamp,
            instrument,
            sessions,
            experiment_name,
            notes,
            total_trades,
            date_start,
            date_end,
            starred,
            hidden,
            {param_cols},
            {metric_cols}
        FROM runs
        WHERE run_type = 'backtest'
        ORDER BY id DESC
        LIMIT ?
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, [limit]).fetchall()

    items: list[dict] = []
    for row in rows:
        sessions_str = row["sessions"] or ""
        item: dict = {
            "id": row["result_file"] or "",
            "timestamp": row["timestamp"] or "",
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "total_trades": row["total_trades"] or 0,
            "date_start": row["date_start"] or "",
            "date_end": row["date_end"] or "",
            "starred": bool(row["starred"]),
            "hidden": bool(row["hidden"]),
        }
        # Add param columns: globals always, session params only when present
        for col in PARAM_COLUMNS:
            val = row[col]
            if col in _GLOBAL_PARAMS or val is not None:
                item[col] = val
        # Add metric columns (always present)
        for col in METRIC_COLUMNS:
            item[col] = row[col] or 0
        if row["experiment_name"]:
            item["name"] = row["experiment_name"]
        if row["notes"]:
            item["notes"] = row["notes"]
        items.append(item)

    return items


def compare_runs(run_ids: list[int]) -> list[dict]:
    """Load full details for specific run IDs, with parsed JSON fields.

    Args:
        run_ids: List of run IDs to compare.

    Returns:
        List of dicts with config_json and metrics_json parsed into dicts.
    """
    init_db()

    if not run_ids:
        return []

    placeholders = ", ".join("?" for _ in run_ids)
    sql = f"""SELECT id, timestamp, run_type, experiment_name, notes, git_hash,
            config_json, metrics_json, total_trades, result_file,
            sessions, instrument, date_start, date_end
        FROM runs WHERE id IN ({placeholders})"""

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, run_ids).fetchall()

    results: list[dict] = []
    for row in rows:
        d = dict(row)
        d["config_json"] = json.loads(d["config_json"])
        d["metrics_json"] = json.loads(d["metrics_json"])
        results.append(d)

    return results


# ---------------------------------------------------------------------------
# Coverage queries
# ---------------------------------------------------------------------------

def get_instrument_coverage() -> list[dict]:
    """Aggregate coverage stats from the runs table, grouped by instrument."""
    init_db()

    sql = """
        SELECT
            instrument,
            SUM(CASE WHEN run_type = 'backtest' THEN 1 ELSE 0 END) AS backtest_count,
            SUM(CASE WHEN run_type = 'optimization' THEN 1 ELSE 0 END) AS optimization_count,
            MIN(date_start) AS earliest_date,
            MAX(date_end) AS latest_date,
            MAX(timestamp) AS last_run_at,
            GROUP_CONCAT(DISTINCT sessions) AS sessions_raw,
            MAX(sharpe_ratio) AS best_sharpe,
            MAX(total_pnl_usd) AS best_pnl_usd,
            MAX(win_rate) AS best_win_rate,
            MAX(profit_factor) AS best_profit_factor
        FROM runs
        WHERE instrument IS NOT NULL AND instrument != ''
        GROUP BY instrument
        ORDER BY instrument
    """

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql).fetchall()

    results: list[dict] = []
    for row in rows:
        # Parse unique sessions from the concatenated sessions_raw
        sessions_raw = row["sessions_raw"] or ""
        sessions_set: set[str] = set()
        for chunk in sessions_raw.split(","):
            for s in chunk.strip().split("+"):
                s = s.strip()
                if s:
                    sessions_set.add(s)

        results.append({
            "instrument": row["instrument"],
            "backtest_count": row["backtest_count"] or 0,
            "optimization_count": row["optimization_count"] or 0,
            "earliest_date": row["earliest_date"] or "",
            "latest_date": row["latest_date"] or "",
            "last_run_at": row["last_run_at"] or "",
            "sessions_tested": sorted(sessions_set),
            "best_sharpe": row["best_sharpe"],
            "best_pnl_usd": row["best_pnl_usd"],
            "best_win_rate": row["best_win_rate"],
            "best_profit_factor": row["best_profit_factor"],
        })

    return results


def get_param_coverage(instrument: str) -> dict:
    """Return distinct values of key sweep params for an instrument."""
    init_db()

    # Key params we want to show coverage for
    key_params = [
        "rr", "tp1_ratio",
        "ny_stop_atr_pct", "ny_min_gap_atr_pct",
        "asia_stop_atr_pct", "asia_min_gap_atr_pct",
        "ldn_stop_atr_pct", "ldn_min_gap_atr_pct",
    ]

    result: dict = {}
    with sqlite3.connect(DB_PATH) as conn:
        for param in key_params:
            if param not in PARAM_COLUMNS:
                continue
            sql = f"""
                SELECT DISTINCT {param} FROM runs
                WHERE instrument = ? AND {param} IS NOT NULL
                ORDER BY {param}
            """
            rows = conn.execute(sql, [instrument]).fetchall()
            values = [r[0] for r in rows]
            if values:
                result[param] = {
                    "values": values,
                    "min": min(values),
                    "max": max(values),
                    "count": len(values),
                }

    return result


# ---------------------------------------------------------------------------
# Testing plan CRUD
# ---------------------------------------------------------------------------

def list_testing_plan(instrument: str | None = None) -> list[dict]:
    """List testing plan items, optionally filtered by instrument."""
    init_db()

    if instrument:
        sql = """
            SELECT id, instrument, title, status, notes, sort_order, created_at, completed_at
            FROM testing_plan
            WHERE instrument = ?
            ORDER BY status ASC, sort_order ASC, id ASC
        """
        params = [instrument]
    else:
        sql = """
            SELECT id, instrument, title, status, notes, sort_order, created_at, completed_at
            FROM testing_plan
            ORDER BY status ASC, sort_order ASC, id ASC
        """
        params = []

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()

    return [dict(row) for row in rows]


def create_testing_plan_item(instrument: str, title: str, notes: str | None = None) -> dict:
    """Create a new testing plan item. Returns the created item."""
    init_db()

    now = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(DB_PATH) as conn:
        # Auto-set sort_order to max + 1 for this instrument
        row = conn.execute(
            "SELECT COALESCE(MAX(sort_order), -1) + 1 FROM testing_plan WHERE instrument = ?",
            [instrument],
        ).fetchone()
        sort_order = row[0] if row else 0

        cur = conn.execute(
            """INSERT INTO testing_plan (instrument, title, notes, sort_order, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            [instrument, title, notes, sort_order, now],
        )
        item_id = cur.lastrowid

    return {
        "id": item_id,
        "instrument": instrument,
        "title": title,
        "status": "pending",
        "notes": notes,
        "sort_order": sort_order,
        "created_at": now,
        "completed_at": None,
    }


def update_testing_plan_item(item_id: int, **updates) -> dict | None:
    """Update a testing plan item. Returns the updated item, or None if not found."""
    init_db()

    allowed = {"title", "notes", "status", "sort_order"}
    sets: list[str] = []
    params: list = []

    for key, val in updates.items():
        if key not in allowed:
            continue
        sets.append(f"{key} = ?")
        params.append(val)

    # Auto-set completed_at when status changes to completed
    if updates.get("status") == "completed":
        sets.append("completed_at = ?")
        params.append(datetime.now(timezone.utc).isoformat())
    elif updates.get("status") == "pending":
        sets.append("completed_at = ?")
        params.append(None)

    if not sets:
        return None

    params.append(item_id)
    sql = f"UPDATE testing_plan SET {', '.join(sets)} WHERE id = ?"

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute(sql, params)
        if cur.rowcount == 0:
            return None

        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM testing_plan WHERE id = ?", [item_id]).fetchone()
        return dict(row) if row else None


def delete_testing_plan_item(item_id: int) -> bool:
    """Delete a testing plan item. Returns True if deleted."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute("DELETE FROM testing_plan WHERE id = ?", [item_id])
        return cur.rowcount > 0


def reorder_testing_plan(instrument: str, item_ids: list[int]) -> bool:
    """Batch update sort_order from the provided ID sequence."""
    init_db()

    with sqlite3.connect(DB_PATH) as conn:
        for idx, item_id in enumerate(item_ids):
            conn.execute(
                "UPDATE testing_plan SET sort_order = ? WHERE id = ? AND instrument = ?",
                [idx, item_id, instrument],
            )
    return True
