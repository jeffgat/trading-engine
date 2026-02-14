"""Export backtest results as structured JSON for LLM consumption."""

from __future__ import annotations

import json
from dataclasses import asdict

from ..config import StrategyConfig
from ..engine.simulator import TradeResult, EXIT_NAMES, EXIT_NO_FILL
from .metrics import compute_metrics


def results_to_dict(
    trades: list[TradeResult],
    config: StrategyConfig,
    include_trades: bool = True,
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
        "be_offset_ticks": config.be_offset_ticks,
        "min_qty": config.min_qty,
        "qty_step": config.qty_step,
    }

    # Add per-session params
    for sess in config.sessions:
        prefix = sess.name.lower()
        config_dict[f"{prefix}_stop_atr_pct"] = sess.stop_atr_pct
        config_dict[f"{prefix}_min_gap_atr_pct"] = sess.min_gap_atr_pct
        config_dict[f"{prefix}_max_gap_points"] = sess.max_gap_points
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
            }
            for t in trades
        ]

    return result


def results_to_json(
    trades: list[TradeResult],
    config: StrategyConfig,
    include_trades: bool = True,
    indent: int = 2,
) -> str:
    """Serialize backtest results to a JSON string."""
    d = results_to_dict(trades, config, include_trades)
    return json.dumps(d, indent=indent, default=str)


def save_results(
    trades: list[TradeResult],
    config: StrategyConfig,
    filepath: str,
    include_trades: bool = True,
) -> None:
    """Save backtest results to a JSON file."""
    text = results_to_json(trades, config, include_trades)
    with open(filepath, "w") as f:
        f.write(text)


def grid_results_to_dict(
    all_results: list[tuple[StrategyConfig, list[TradeResult]]],
) -> dict:
    """Convert grid sweep results to a summary dict.

    Args:
        all_results: List of (config, trades) tuples from grid sweep.

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

    return {
        "total_combinations": len(summaries),
        "best_by_sharpe": best_by_sharpe,
        "best_by_pnl": best_by_pnl,
        "best_by_profit_factor": best_by_pf,
        "all_results": summaries,
    }
