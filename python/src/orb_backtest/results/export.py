"""Export backtest results as structured dicts for DB storage and LLM consumption."""

from __future__ import annotations

import re
import time
from datetime import datetime

import numpy as np

from ..config import StrategyConfig
from ..engine.simulator import TradeResult, EXIT_NAMES, EXIT_NO_FILL
from .metrics import compute_metrics
from ..experiments import (
    log_run,
    log_optimization,
    get_backtest_result,
    delete_backtest_run,
    list_optimization_history,
    get_optimization_result,
    delete_optimization_run,
)


# ---------------------------------------------------------------------------
# ID generation helpers
# ---------------------------------------------------------------------------

# Abbreviations for swept param names in optimization IDs
_PARAM_ABBREV: dict[str, str] = {
    "rr": "rr",
    "tp1_ratio": "tp1",

    "atr_length": "atr",
    "risk_usd": "risk",
    "ny_stop_atr_pct": "ny.stop",
    "ny_min_gap_atr_pct": "ny.gap",
    "ny_max_gap_points": "ny.maxgap",
    "asia_stop_atr_pct": "asia.stop",
    "asia_min_gap_atr_pct": "asia.gap",
    "asia_max_gap_points": "asia.maxgap",
    "ldn_stop_atr_pct": "ldn.stop",
    "ldn_min_gap_atr_pct": "ldn.gap",
    "ldn_max_gap_points": "ldn.maxgap",
}


def _short_hash() -> str:
    """6-char hex from timestamp nanos (16.7M possibilities)."""
    return format(time.time_ns() % (16**6), "06x")


def _slugify(text: str, max_len: int = 40) -> str:
    """Convert text to a lowercase, hyphen-separated ID slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _sessions_from_config(config: dict) -> list[str]:
    """Extract sorted session names from a config dict."""
    return sorted(
        key.split("_")[0].upper()
        for key in config
        if key.endswith("_orb_window")
    )


def generate_backtest_id(result: dict) -> str:
    """Generate a backtest ID: ``bt-{descriptor}-{hash6}``."""
    config = result.get("config", {})
    name = result.get("name", "")

    if name:
        descriptor = _slugify(name)
    else:
        instrument = config.get("instrument", "unk").lower()
        sessions = _sessions_from_config(config)
        sess_str = ".".join(s.lower() for s in sessions) or "unk"
        rr = config.get("rr", "")
        rr_str = f"{rr:g}" if isinstance(rr, (int, float)) else str(rr)
        descriptor = f"{instrument}-{sess_str}-rr{rr_str}"

    return f"bt-{descriptor}-{_short_hash()}"


def generate_optimization_id(result: dict) -> str:
    """Generate an optimization ID: ``opt-{descriptor}-{hash6}``."""
    all_results = result.get("all_results", [])
    swept_params = result.get("swept_params", {})

    instrument = "unk"
    if all_results:
        instrument = all_results[0].get("config", {}).get("instrument", "unk").lower()

    abbrevs = [
        _PARAM_ABBREV.get(p, _slugify(p, max_len=10))
        for p in sorted(swept_params.keys())
    ]

    n_combos = result.get("total_combinations", len(all_results))

    parts = [instrument] + abbrevs + [f"{n_combos}c"]
    descriptor = "-".join(parts)[:40]

    return f"opt-{descriptor}-{_short_hash()}"


def _build_equity_curve(trades: list[TradeResult]) -> list[dict]:
    """Build cumulative equity curve from filled trades.

    Returns list of {date, pnl_cumulative, pnl_per_trade} dicts.
    """
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return []

    cumulative = 0.0
    curve = []
    for t in filled:
        cumulative += t.pnl_usd
        curve.append({
            "date": t.date,
            "pnl_cumulative": round(cumulative, 2),
            "pnl_per_trade": round(t.pnl_usd, 2),
        })
    return curve


def results_to_dict(
    trades: list[TradeResult],
    config: StrategyConfig,
    include_trades: bool = True,
    include_equity_curve: bool = False,
) -> dict:
    """Convert backtest results to a structured dict.

    Args:
        trades: List of TradeResult from the simulator.
        config: Strategy configuration used for this run.
        include_trades: Whether to include the full trade list.

    Returns:
        Dict ready for json.dumps() or LLM consumption.
    """
    metrics = compute_metrics(trades)

    # Config summary (flat, easy for LLMs to parse)
    config_dict = {
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "risk_usd": config.risk_usd,
        "atr_length": config.atr_length,

        "min_qty": config.min_qty,
        "qty_step": config.qty_step,
    }

    if config.strategy:
        config_dict["strategy"] = config.strategy
    if config.direction_filter:
        config_dict["direction_filter"] = config.direction_filter
    if config.use_bar_magnifier:
        config_dict["bar_magnifier"] = "ON"

    # Add per-session params
    for sess in config.sessions:
        prefix = sess.name.lower()
        config_dict[f"{prefix}_stop_atr_pct"] = sess.stop_atr_pct
        config_dict[f"{prefix}_min_gap_atr_pct"] = sess.min_gap_atr_pct
        config_dict[f"{prefix}_max_gap_points"] = sess.max_gap_points
        if sess.qualifying_move_atr_pct > 0:
            config_dict[f"{prefix}_qualifying_move_atr_pct"] = sess.qualifying_move_atr_pct
        config_dict[f"{prefix}_orb_window"] = f"{sess.orb_start}-{sess.orb_end}"
        config_dict[f"{prefix}_entry_window"] = f"{sess.entry_start}-{sess.entry_end}"
        config_dict[f"{prefix}_flat_window"] = f"{sess.flat_start}-{sess.flat_end}"

    if config.instrument:
        config_dict["instrument"] = config.instrument.symbol
        config_dict["point_value"] = config.instrument.point_value

    result = {
        "config": config_dict,
        "summary": metrics,
    }

    if config.name:
        result["name"] = config.name
    if config.notes:
        result["notes"] = config.notes

    if include_equity_curve:
        result["equity_curve"] = _build_equity_curve(trades)

    if include_trades:
        result["trades"] = [
            {
                "date": t.date,
                "session": t.session,
                "direction": "long" if t.direction == 1 else "short",
                "entry_price": round(t.entry_price, 4),
                "stop_price": round(t.stop_price, 4),
                "tp1_price": round(t.tp1_price, 4),
                "tp2_price": round(t.tp2_price, 4),
                "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
                "pnl_usd": round(t.pnl_usd, 2),
                "pnl_points": round(t.pnl_points, 4),
                "r_multiple": round(t.r_multiple, 3),
                "qty": t.qty,
                "gap_size": round(t.gap_size, 4),
                "risk_points": round(t.risk_points, 4),
                "entry_time": t.fill_time,
                "exit_time": t.exit_time,
            }
            for t in trades
        ]

    return result


def save_backtest_result(result: dict) -> str:
    """Save a backtest result to the DB and return its ID.

    ID format: ``bt-{descriptor}-{hash6}``
    """
    result_id = generate_backtest_id(result)
    log_run(result, result_id)
    return result_id


def load_backtest_result(result_id: str) -> dict | None:
    """Load a full backtest result by ID from the DB."""
    return get_backtest_result(result_id)


def delete_backtest_result(result_id: str) -> bool:
    """Delete a saved backtest result from the DB."""
    return delete_backtest_run(result_id)


def grid_results_to_dict(
    all_results: list[tuple[StrategyConfig, list[TradeResult]]],
    swept_params: dict[str, list] | None = None,
) -> dict:
    """Convert grid sweep results to a summary dict.

    Args:
        all_results: List of (config, trades) tuples from grid sweep.
        swept_params: Optional dict mapping param names to swept values.

    Returns:
        Dict with best results and all combination summaries.
    """
    summaries = []
    for config, trades in all_results:
        d = results_to_dict(trades, config, include_trades=False)
        summaries.append(d)

    # Find best by different metrics
    filled_summaries = [s for s in summaries if s["summary"]["total_trades"] > 0]

    best_by_sharpe = max(filled_summaries, key=lambda s: s["summary"]["sharpe_ratio"]) if filled_summaries else None
    best_by_pnl = max(filled_summaries, key=lambda s: s["summary"]["total_pnl_usd"]) if filled_summaries else None
    best_by_pf = max(filled_summaries, key=lambda s: s["summary"]["profit_factor"]) if filled_summaries else None
    best_by_calmar = max(filled_summaries, key=lambda s: s["summary"].get("calmar_ratio", 0)) if filled_summaries else None

    result = {
        "total_combinations": len(summaries),
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "best_by_calmar": best_by_calmar,
        "all_results": summaries,
    }

    if swept_params is not None:
        def _coerce(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return v
        result["swept_params"] = {k: [_coerce(v) for v in vs] for k, vs in swept_params.items()}

    return result


def save_optimization_result(result: dict) -> str:
    """Save an optimization result to the DB and return its ID.

    ID format: ``opt-{descriptor}-{hash6}``
    """
    result_id = generate_optimization_id(result)
    log_optimization(result, result_id)
    return result_id


def list_optimization_results() -> list[dict]:
    """List all saved optimization results as metadata dicts, newest first."""
    return list_optimization_history()


def load_optimization_result(result_id: str) -> dict | None:
    """Load a full optimization result by ID from the DB."""
    return get_optimization_result(result_id)


def delete_optimization_result(result_id: str) -> bool:
    """Delete a saved optimization result from the DB."""
    return delete_optimization_run(result_id)


def _trades_to_minimal(trades: list[TradeResult]) -> list[dict]:
    """Convert trades to minimal dicts (for compact storage in optimization results)."""
    return [
        {
            "date": t.date,
            "session": t.session,
            "direction": "long" if t.direction == 1 else "short",
            "exit_type": EXIT_NAMES.get(t.exit_type, "unknown"),
            "pnl_usd": round(t.pnl_usd, 2),
            "r_multiple": round(t.r_multiple, 3),
        }
        for t in trades
        if t.exit_type != EXIT_NO_FILL
    ]


def get_experiment_history(limit: int = 50, **filters) -> list[dict]:
    """Query experiment history from the SQLite DB.

    Convenience wrapper for API/dashboard use.
    """
    from ..experiments import query_runs
    return query_runs(limit=limit, **filters)
