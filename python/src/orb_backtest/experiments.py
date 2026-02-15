"""SQLite experiment tracking for backtest and optimization runs."""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "results" / "experiments.db"

_SCHEMA = """\
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
    date_end TEXT
);
"""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db() -> Path:
    """Create the data directory and runs table if they don't exist.

    Returns the path to the SQLite database file.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(_SCHEMA)
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


# Whitelist pattern for param filter names (alphanumeric + underscores)
_SAFE_PARAM_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


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

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_type": run_type,
        "experiment_name": result_dict.get("name"),
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
        clauses.append("json_extract(metrics_json, '$.profit_factor') >= ?")
        params.append(min_profit_factor)

    min_sharpe = filters.get("min_sharpe")
    if min_sharpe is not None:
        clauses.append("json_extract(metrics_json, '$.sharpe_ratio') >= ?")
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
            clauses.append(f"json_extract(config_json, '$.{param_name}') >= ?")
            params.append(lo)
            clauses.append(f"json_extract(config_json, '$.{param_name}') <= ?")
            params.append(hi)

    limit = filters.get("limit", 100)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses)

    sql = f"""
        SELECT *,
            json_extract(metrics_json, '$.win_rate')       AS win_rate,
            json_extract(metrics_json, '$.total_pnl_usd')  AS total_pnl_usd,
            json_extract(metrics_json, '$.profit_factor')   AS profit_factor,
            json_extract(metrics_json, '$.sharpe_ratio')    AS sharpe_ratio
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
    sql = f"SELECT * FROM runs WHERE id IN ({placeholders})"

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
