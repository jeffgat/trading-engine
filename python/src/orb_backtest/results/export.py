"""Export backtest results as structured JSON for LLM consumption."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np

from ..config import StrategyConfig
from ..engine.simulator import TradeResult, EXIT_NAMES, EXIT_NO_FILL
from .metrics import compute_metrics

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "results"


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


def save_backtest_result(result: dict) -> str:
    """Save a backtest result dict to disk and return its ID.

    ID format: {timestamp}_{instrument}_{sessions}
    """
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    instrument = result.get("config", {}).get("instrument", "UNK")
    sessions = []
    for key in result.get("config", {}):
        if key.endswith("_orb_window"):
            sessions.append(key.split("_")[0].upper())
    session_str = "+".join(sorted(sessions)) or "UNK"

    result_id = f"{ts}_{instrument}_{session_str}"
    filepath = RESULTS_DIR / f"{result_id}.json"
    filepath.write_text(json.dumps(result, indent=2, default=str))
    return result_id


def list_backtest_results() -> list[dict]:
    """List all saved backtest results as metadata dicts, newest first."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for fp in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(fp.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        config = data.get("config", {})
        summary = data.get("summary", {})
        sessions = []
        for key in config:
            if key.endswith("_orb_window"):
                sessions.append(key.split("_")[0].upper())
        # Extract date range from equity curve or trades
        equity = data.get("equity_curve", [])
        trades_list = data.get("trades", [])
        dates_source = equity or trades_list
        date_start = dates_source[0]["date"] if dates_source else ""
        date_end = dates_source[-1]["date"] if dates_source else ""

        items.append({
            "id": fp.stem,
            "timestamp": fp.stem[:17].replace("_", " ", 1),  # "2026-02-14 153045"
            "instrument": config.get("instrument", ""),
            "sessions": sorted(sessions),
            "total_pnl_usd": summary.get("total_pnl_usd", 0),
            "total_trades": summary.get("total_trades", 0),
            "win_rate": summary.get("win_rate", 0),
            "date_start": date_start,
            "date_end": date_end,
        })
    return items


def load_backtest_result(result_id: str) -> dict | None:
    """Load a full backtest result by ID (filename without .json)."""
    fp = RESULTS_DIR / f"{result_id}.json"
    if not fp.exists():
        return None
    return json.loads(fp.read_text())


def delete_backtest_result(result_id: str) -> bool:
    """Delete a saved backtest result. Returns True if deleted."""
    fp = RESULTS_DIR / f"{result_id}.json"
    if not fp.exists():
        return False
    fp.unlink()
    return True


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
