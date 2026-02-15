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

RESULTS_DIR = Path(__file__).resolve().parents[2] / "data" / "results"
OPTIMIZATIONS_DIR = Path(__file__).resolve().parents[2] / "data" / "optimizations"

_init_in_progress = False


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db() -> Path:
    """Create the data directory and tables if they don't exist.

    Also runs schema migrations for new columns and backfills from JSON files.
    Returns the path to the SQLite database file.
    """
    global _init_in_progress
    if _init_in_progress:
        return DB_PATH

    _init_in_progress = True
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(DB_PATH) as conn:
            conn.executescript(_SCHEMA)
            conn.executescript(_OPTIMIZATIONS_SCHEMA)

            # Migrate: add trades_json and equity_json columns if missing
            existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
            if "trades_json" not in existing:
                conn.execute("ALTER TABLE runs ADD COLUMN trades_json TEXT")
            if "equity_json" not in existing:
                conn.execute("ALTER TABLE runs ADD COLUMN equity_json TEXT")

        # One-time backfill from JSON files
        if _needs_backfill():
            backfill_from_json()
    finally:
        _init_in_progress = False

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
        "trades_json": trades_json,
        "equity_json": equity_json,
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

    row = {
        "result_id": result_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "git_hash": _get_git_hash(),
        "instrument": instrument,
        "sessions": session_str,
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
               best_by_sharpe_json, best_by_pnl_json
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

        items.append({
            "id": row["result_id"],
            "timestamp": row["timestamp"],
            "instrument": row["instrument"] or "",
            "sessions": sessions_str.split("+") if sessions_str else [],
            "risk_usd": risk_usd,
            "swept_params": list(swept_params.keys()),
            "total_combinations": row["total_combinations"],
            "best_sharpe": best_sharpe,
            "best_pnl_usd": best_pnl_usd,
        })

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
# Backfill from JSON files
# ---------------------------------------------------------------------------

def _needs_backfill() -> bool:
    """Check if there are JSON files that haven't been backfilled into the DB.

    Returns True if any backtest JSON files exist with no corresponding
    trades_json in the DB, or if optimization JSONs exist with no DB rows.
    """
    # Check backtest results
    if RESULTS_DIR.exists():
        json_files = list(RESULTS_DIR.glob("*.json"))
        if json_files:
            with sqlite3.connect(DB_PATH) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM runs WHERE run_type = 'backtest' AND trades_json IS NOT NULL"
                ).fetchone()[0]
                if count < len(json_files):
                    return True

    # Check optimization results
    if OPTIMIZATIONS_DIR.exists():
        opt_files = list(OPTIMIZATIONS_DIR.glob("*.json"))
        if opt_files:
            with sqlite3.connect(DB_PATH) as conn:
                count = conn.execute(
                    "SELECT COUNT(*) FROM optimizations"
                ).fetchone()[0]
                if count < len(opt_files):
                    return True

    return False


def backfill_from_json() -> dict[str, int]:
    """One-time migration: scan JSON files and insert/update DB rows.

    Returns dict with counts of backfilled backtests and optimizations.
    """
    counts = {"backtests": 0, "optimizations": 0}

    # Get existing result_file values with trades_json populated
    with sqlite3.connect(DB_PATH) as conn:
        existing_backtests = {
            row[0] for row in conn.execute(
                "SELECT result_file FROM runs WHERE run_type = 'backtest' AND trades_json IS NOT NULL"
            ).fetchall()
        }
        existing_optimizations = {
            row[0] for row in conn.execute(
                "SELECT result_id FROM optimizations"
            ).fetchall()
        }

    # Backfill backtest results
    if RESULTS_DIR.exists():
        for fp in sorted(RESULTS_DIR.glob("*.json")):
            result_id = fp.stem
            if result_id in existing_backtests:
                continue
            try:
                data = json.loads(fp.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            # Skip non-backtest files
            if "config" not in data or "summary" not in data:
                continue

            # Check if this result_file already exists in DB (without trades_json)
            with sqlite3.connect(DB_PATH) as conn:
                row = conn.execute(
                    "SELECT id FROM runs WHERE result_file = ? AND run_type = 'backtest'",
                    [result_id],
                ).fetchone()

            if row:
                # Update existing row with trades/equity
                trades_json = _dumps(data.get("trades", [])) if data.get("trades") else None
                equity_json = _dumps(data.get("equity_curve", [])) if data.get("equity_curve") else None
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "UPDATE runs SET trades_json = ?, equity_json = ? WHERE id = ?",
                        [trades_json, equity_json, row[0]],
                    )
            else:
                # Insert new row from JSON file
                _backfill_single_backtest(data, result_id, fp)

            counts["backtests"] += 1

    # Backfill optimization results
    if OPTIMIZATIONS_DIR.exists():
        for fp in sorted(OPTIMIZATIONS_DIR.glob("*.json")):
            result_id = fp.stem
            if result_id in existing_optimizations:
                continue
            try:
                data = json.loads(fp.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if "all_results" not in data:
                continue

            log_optimization(data, result_id)
            counts["optimizations"] += 1

    return counts


def _backfill_single_backtest(data: dict, result_id: str, fp: Path) -> None:
    """Insert a backtest JSON file into the runs table."""
    config = data.get("config", {})
    summary = data.get("summary", {})

    sessions: list[str] = []
    for key in config:
        if key.endswith("_orb_window"):
            sessions.append(key.split("_")[0].upper())
    session_str = "+".join(sorted(sessions)) if sessions else ""

    equity_curve = data.get("equity_curve", [])
    trades_list = data.get("trades", [])
    dates_source = equity_curve or trades_list
    date_start = dates_source[0]["date"] if dates_source else ""
    date_end = dates_source[-1]["date"] if dates_source else ""

    # Derive timestamp from filename: "2026-02-14_153045_..."
    stem = fp.stem
    try:
        ts_str = stem[:17]  # "2026-02-14_153045"
        ts = datetime.strptime(ts_str, "%Y-%m-%d_%H%M%S").replace(tzinfo=timezone.utc)
        timestamp = ts.isoformat()
    except (ValueError, IndexError):
        timestamp = datetime.now(timezone.utc).isoformat()

    trades_json = _dumps(trades_list) if trades_list else None
    equity_json = _dumps(equity_curve) if equity_curve else None

    row = {
        "timestamp": timestamp,
        "run_type": "backtest",
        "experiment_name": data.get("name"),
        "notes": data.get("notes"),
        "git_hash": "backfill",
        "config_json": json.dumps(config, default=_json_default),
        "metrics_json": json.dumps(summary, default=_json_default),
        "total_trades": int(summary.get("total_trades", 0)),
        "result_file": result_id,
        "sessions": session_str,
        "instrument": config.get("instrument", ""),
        "date_start": date_start,
        "date_end": date_end,
        "trades_json": trades_json,
        "equity_json": equity_json,
    }

    columns = ", ".join(row.keys())
    placeholders = ", ".join(f":{k}" for k in row.keys())
    sql = f"INSERT INTO runs ({columns}) VALUES ({placeholders})"

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(sql, row)


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
        SELECT id, timestamp, run_type, experiment_name, notes, git_hash,
            config_json, metrics_json, total_trades, result_file,
            sessions, instrument, date_start, date_end,
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


def list_backtest_history(limit: int = 100) -> list[dict]:
    """Return backtest runs shaped for the frontend BacktestHistoryItem.

    Returns list of dicts with: id, timestamp, instrument, sessions,
    risk_usd, total_pnl_usd, total_trades, win_rate, date_start,
    date_end, name, notes.
    """
    init_db()

    sql = """
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
            json_extract(config_json, '$.risk_usd')           AS risk_usd,
            json_extract(metrics_json, '$.total_pnl_usd')      AS total_pnl_usd,
            json_extract(metrics_json, '$.win_rate')            AS win_rate,
            json_extract(metrics_json, '$.sharpe_ratio')        AS sharpe_ratio,
            json_extract(metrics_json, '$.max_drawdown_usd')    AS max_drawdown_usd,
            json_extract(metrics_json, '$.profit_factor')       AS profit_factor,
            json_extract(metrics_json, '$.sortino_ratio')       AS sortino_ratio
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
            "risk_usd": row["risk_usd"] or 5000,
            "total_pnl_usd": row["total_pnl_usd"] or 0,
            "total_trades": row["total_trades"] or 0,
            "win_rate": row["win_rate"] or 0,
            "sharpe_ratio": row["sharpe_ratio"] or 0,
            "max_drawdown_usd": row["max_drawdown_usd"] or 0,
            "profit_factor": row["profit_factor"] or 0,
            "sortino_ratio": row["sortino_ratio"] or 0,
            "date_start": row["date_start"] or "",
            "date_end": row["date_end"] or "",
        }
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
