"""IFVG experiment tracking — delegates to shared orb_backtest experiments DB.

Adds IFVG-specific columns (strategy_type, sweep params, etc.) via migration,
then re-exports the shared log/query functions.  Also provides IFVG-specific
helpers for sweep logging, optimization CRUD, and auto-naming.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3

from orb_backtest.experiments import (
    init_db,
    DB_PATH,
    METRIC_COLUMNS,
    log_run,
    get_backtest_result,
    delete_backtest_run,
    list_backtest_history,
    toggle_star,
    toggle_hidden,
    list_starred,
    query_runs,
    compare_runs,
    log_optimization,
    list_optimization_history,
    get_optimization_result,
    delete_optimization_run,
    get_instrument_coverage,
    get_param_coverage,
    list_testing_plan,
    create_testing_plan_item,
    update_testing_plan_item,
    delete_testing_plan_item,
    reorder_testing_plan,
    _get_git_hash,
    _json_default,
)

# Optional imports — these exist in newer orb_backtest versions
try:
    from orb_backtest.experiments import backup_db
except ImportError:
    def backup_db():
        return None

try:
    from orb_backtest.experiments import rename_backtest
except ImportError:
    def rename_backtest(result_id: str, new_name: str) -> str | None:
        init_db()
        import sqlite3 as _sqlite3
        with _sqlite3.connect(DB_PATH) as conn:
            row = conn.execute(
                "SELECT id FROM runs WHERE result_file = ? AND run_type = 'backtest' ORDER BY id DESC LIMIT 1",
                [result_id],
            ).fetchone()
            if row is None:
                return None
            conn.execute(
                "UPDATE runs SET experiment_name = ? WHERE result_file = ? AND run_type = 'backtest'",
                [new_name, result_id],
            )
            return new_name


# IFVG-specific columns to add to the shared runs table
IFVG_COLUMNS: dict[str, str] = {
    "strategy_type": "TEXT",
    "max_bars_after_sweep": "INTEGER",
    "min_gap_atr_pct": "REAL",
    "gap_window_bars": "INTEGER",
    "be_offset_ticks": "INTEGER",
    "use_pdh_sweeps": "INTEGER",  # 0/1 bool
    "use_pdl_sweeps": "INTEGER",
    "asia_use_high_sweeps": "INTEGER",
    "asia_use_low_sweeps": "INTEGER",
    "london_use_high_sweeps": "INTEGER",
    "london_use_low_sweeps": "INTEGER",
    "entry_start": "TEXT",
    "entry_end": "TEXT",
    "candle_tf": "TEXT",
    "direction_filter": "TEXT",
    "entry_type": "TEXT",
    "bpr_filter": "TEXT",
    "max_inversion_bars": "INTEGER",
    "min_stop_atr_pct": "REAL",
    "require_singular_gap": "INTEGER",
    "use_swing_high_sweeps": "INTEGER",
    "use_swing_low_sweeps": "INTEGER",
    "swing_length": "INTEGER",
}

# IFVG param abbreviations for optimization IDs
_PARAM_ABBREV: dict[str, str] = {
    "rr": "rr",
    "tp1_ratio": "tp1",
    "min_gap_atr_pct": "gap",
    "gap_window_bars": "gwin",
    "max_bars_after_sweep": "sweep",
    "be_offset_ticks": "be",
    "min_stop_atr_pct": "minstop",
    "max_inversion_bars": "inv",
    "candle_tf": "tf",
    "bpr_filter": "bpr",
    "bpr_tight_max_bars": "bprbars",
    "direction_filter": "dir",
    "entry_type": "entry",
}


def migrate_ifvg_columns() -> None:
    """Add IFVG-specific columns to the shared experiments DB if missing."""
    init_db()  # Ensure base schema exists first

    with sqlite3.connect(DB_PATH) as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runs)").fetchall()}
        for col, dtype in IFVG_COLUMNS.items():
            if col not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {dtype}")


# Run migration on import so columns exist when log_run is called
migrate_ifvg_columns()


def log_ifvg_sweep_runs(
    all_results: list[tuple],
    optimization_id: str,
) -> int:
    """Log every combination from an IFVG parameter sweep.

    Args:
        all_results: List of (IFVGConfig, trades, metrics) tuples.
        optimization_id: Shared identifier for this sweep.

    Returns:
        The number of rows logged.
    """
    from .results.export import results_to_dict

    git_hash = _get_git_hash()

    count = 0
    for config, trades, _metrics in all_results:
        result_dict = results_to_dict(trades, config, include_trades=False)
        log_run(result_dict, optimization_id, run_type="optimization", git_hash=git_hash)
        count += 1
    return count


# Re-export everything the IFVG module needs
__all__ = [
    "DB_PATH",
    "METRIC_COLUMNS",
    "backup_db",
    "log_run",
    "get_backtest_result",
    "delete_backtest_run",
    "rename_backtest",
    "list_backtest_history",
    "toggle_star",
    "toggle_hidden",
    "list_starred",
    "query_runs",
    "compare_runs",
    "log_optimization",
    "list_optimization_history",
    "get_optimization_result",
    "delete_optimization_run",
    "get_instrument_coverage",
    "get_param_coverage",
    "list_testing_plan",
    "create_testing_plan_item",
    "update_testing_plan_item",
    "delete_testing_plan_item",
    "reorder_testing_plan",
    "migrate_ifvg_columns",
    "log_ifvg_sweep_runs",
    "_PARAM_ABBREV",
    "_get_git_hash",
]
