"""Objective function mapping for optimization."""

from __future__ import annotations


# Map short names -> metric dict keys
OBJECTIVE_MAP: dict[str, str] = {
    "sharpe": "sharpe_ratio",
    "sortino": "sortino_ratio",
    "calmar": "calmar_ratio",
    "pnl": "total_pnl_usd",
    "profit_factor": "profit_factor",
    "avg_r": "avg_r",
    "win_rate": "win_rate",
}

VALID_OBJECTIVES: list[str] = list(OBJECTIVE_MAP.keys())


def get_objective_value(
    metrics: dict,
    objective: str,
    risk_usd: float = 5000.0,
) -> float:
    """Extract the objective value from a metrics dict.

    Args:
        metrics: Dict from compute_metrics().
        objective: One of VALID_OBJECTIVES.
        risk_usd: Risk per trade in USD (unused, reserved for future R-normalized objectives).

    Returns:
        The objective value (higher is better).
    """
    key = OBJECTIVE_MAP[objective]
    return float(metrics.get(key, 0.0))
