"""Export IFVG backtest results as structured dicts for DB storage."""

from __future__ import annotations

import re
import time

from orb_backtest.engine.simulator import TradeResult, EXIT_NAMES, EXIT_NO_FILL
from .metrics import compute_metrics
from ..config import IFVGConfig
from ..experiments import (
    log_run,
    get_backtest_result,
    delete_backtest_run,
    rename_backtest,
    log_optimization,
    list_optimization_history,
    get_optimization_result,
    delete_optimization_run,
    _PARAM_ABBREV,
)


# ---------------------------------------------------------------------------
# ID generation helpers
# ---------------------------------------------------------------------------

def _short_hash() -> str:
    """6-char hex from timestamp nanos."""
    return format(time.time_ns() % (16**6), "06x")


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def generate_backtest_id(result: dict) -> str:
    """Generate ID: ``ifvg-{descriptor}-{hash6}``."""
    name = result.get("name", "")
    config = result.get("config", {})

    if name:
        descriptor = _slugify(name)
    else:
        instrument = config.get("instrument", "unk").lower()
        rr = config.get("rr", "")
        rr_str = f"{rr:g}" if isinstance(rr, (int, float)) else str(rr)
        descriptor = f"{instrument}-rr{rr_str}"

    return f"ifvg-{descriptor}-{_short_hash()}"


def generate_optimization_id(result: dict) -> str:
    """Generate an optimization ID: ``ifvg-opt-{descriptor}-{hash6}``."""
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

    return f"ifvg-opt-{descriptor}-{_short_hash()}"


def _build_equity_curve(trades: list[TradeResult]) -> list[dict]:
    """Build cumulative equity curve from filled trades."""
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
    config: IFVGConfig,
    include_trades: bool = True,
    include_equity_curve: bool = False,
) -> dict:
    """Convert IFVG backtest results to a structured dict."""
    metrics = compute_metrics(trades)

    config_dict = {
        "strategy_type": "ifvg",
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "risk_usd": config.risk_usd,
        "atr_length": config.atr_length,
        "min_qty": config.min_qty,
        "qty_step": config.qty_step,
        "be_offset_ticks": config.be_offset_ticks,
        "entry_window": f"{config.entry_start}-{config.entry_end}",
        "flat_window": f"{config.flat_start}-{config.flat_end}",
        "entry_start": config.entry_start,
        "entry_end": config.entry_end,
        "max_bars_after_sweep": config.max_bars_after_sweep,
        "min_gap_atr_pct": config.min_gap_atr_pct,
        "gap_window_bars": config.gap_window_bars,
        "max_inversion_bars": config.max_inversion_bars,
        "min_stop_atr_pct": config.min_stop_atr_pct,
        "direction_filter": config.direction_filter,
        "entry_type": config.entry_type,
        "bpr_filter": config.bpr_filter,
        "bpr_tight_max_bars": config.bpr_tight_max_bars,
        "candle_tf": config.candle_tf,
        "require_singular_gap": config.require_singular_gap,
        "use_pdh_sweeps": config.use_pdh_sweeps,
        "use_pdl_sweeps": config.use_pdl_sweeps,
        "use_swing_high_sweeps": config.use_swing_high_sweeps,
        "use_swing_low_sweeps": config.use_swing_low_sweeps,
        "swing_length": config.swing_length,
    }

    # KZ configs
    for kz in config.killzones:
        prefix = kz.name.lower()
        config_dict[f"{prefix}_session"] = f"{kz.start}-{kz.end}"
        config_dict[f"{prefix}_use_high_sweeps"] = kz.use_high_sweeps
        config_dict[f"{prefix}_use_low_sweeps"] = kz.use_low_sweeps

    if config.instrument:
        config_dict["instrument"] = config.instrument.symbol
        config_dict["point_value"] = config.instrument.point_value

    if config.use_bar_magnifier:
        config_dict["bar_magnifier"] = "ON"

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
    """Save an IFVG backtest result to the shared DB."""
    result_id = generate_backtest_id(result)
    log_run(result, result_id)
    return result_id


def load_backtest_result(result_id: str) -> dict | None:
    """Load a full backtest result by ID."""
    return get_backtest_result(result_id)


def delete_backtest_result(result_id: str) -> bool:
    """Delete a saved backtest result."""
    return delete_backtest_run(result_id)


def save_optimization_result(result: dict) -> str:
    """Save an optimization result to the DB and return its ID."""
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


def grid_results_to_dict(
    all_results: list[tuple[IFVGConfig, list[TradeResult]]],
    swept_params: dict[str, list] | None = None,
) -> dict:
    """Convert grid sweep results to a summary dict."""
    summaries = []
    for config, trades in all_results:
        d = results_to_dict(trades, config, include_trades=False)
        summaries.append(d)

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


def get_experiment_history(limit: int = 50, **filters) -> list[dict]:
    """Query experiment history from the SQLite DB."""
    from ..experiments import query_runs
    return query_runs(limit=limit, **filters)
