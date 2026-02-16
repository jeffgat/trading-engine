"""Monte Carlo simulation for strategy robustness analysis."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..engine.simulator import TradeResult, EXIT_NO_FILL


@dataclass
class MonteCarloConfig:
    """Configuration for Monte Carlo simulation."""
    n_simulations: int = 1000
    method: str = "bootstrap"  # "bootstrap" or "shuffle"
    seed: int | None = None


@dataclass
class MonteCarloResult:
    """Results of Monte Carlo simulation."""
    method: str
    n_simulations: int
    n_trades: int
    actual_final_pnl: float  # in R
    actual_max_drawdown: float  # in R
    actual_sharpe: float
    final_pnl_percentiles: dict[str, float]
    max_dd_percentiles: dict[str, float]
    sharpe_percentiles: dict[str, float]
    ruin_probability: float
    ruin_threshold: float
    equity_curves: np.ndarray  # (n_sims, n_trades) cumulative R


def _percentiles(arr: np.ndarray) -> dict[str, float]:
    """Compute standard percentiles."""
    return {
        "p5": round(float(np.percentile(arr, 5)), 4),
        "p25": round(float(np.percentile(arr, 25)), 4),
        "p50": round(float(np.percentile(arr, 50)), 4),
        "p75": round(float(np.percentile(arr, 75)), 4),
        "p95": round(float(np.percentile(arr, 95)), 4),
    }


def run_monte_carlo(
    trades: list[TradeResult],
    config: MonteCarloConfig,
    ruin_threshold: float = -8.0,
) -> MonteCarloResult:
    """Run Monte Carlo simulation on trade results.

    Bootstrap: Resample trades with replacement (tests luck variance).
    Shuffle: Randomly reorder trades (tests path dependency).

    Args:
        trades: List of TradeResult from a backtest.
        config: MC configuration.
        ruin_threshold: Max drawdown in R for ruin probability calculation.

    Returns:
        MonteCarloResult with percentile distributions.
    """
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        raise ValueError("No filled trades for Monte Carlo simulation")

    r_multiples = np.array([t.r_multiple for t in filled])
    n_trades = len(r_multiples)
    n_sims = config.n_simulations

    rng = np.random.default_rng(config.seed)

    # Generate all simulated equity curves
    equity_curves = np.zeros((n_sims, n_trades))

    for i in range(n_sims):
        if config.method == "bootstrap":
            # Resample with replacement
            idx = rng.integers(0, n_trades, size=n_trades)
            sim_r = r_multiples[idx]
        else:
            # Shuffle order
            sim_r = rng.permutation(r_multiples)

        equity_curves[i] = np.cumsum(sim_r)

    # Final PnL (in R)
    final_pnls = equity_curves[:, -1]

    # Max drawdown per simulation (in R)
    peaks = np.maximum.accumulate(equity_curves, axis=1)
    drawdowns = equity_curves - peaks
    max_dds = np.min(drawdowns, axis=1)

    # Sharpe per simulation
    daily_returns = np.diff(equity_curves, axis=1, prepend=0)
    means = np.mean(daily_returns, axis=1)
    stds = np.std(daily_returns, axis=1, ddof=1)
    stds = np.where(stds > 0, stds, 1.0)
    sharpes = means / stds * np.sqrt(252)

    # Ruin probability
    ruin_count = np.sum(max_dds < ruin_threshold)
    ruin_prob = float(ruin_count / n_sims)

    # Actual (observed) stats
    actual_equity = np.cumsum(r_multiples)
    actual_peak = np.maximum.accumulate(actual_equity)
    actual_dd = actual_equity - actual_peak
    actual_max_dd = float(np.min(actual_dd))
    actual_final = float(actual_equity[-1])

    avg_r = float(np.mean(r_multiples))
    std_r = float(np.std(r_multiples, ddof=1)) if n_trades > 1 else 1.0
    actual_sharpe = (avg_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0

    return MonteCarloResult(
        method=config.method,
        n_simulations=n_sims,
        n_trades=n_trades,
        actual_final_pnl=round(actual_final, 4),
        actual_max_drawdown=round(actual_max_dd, 4),
        actual_sharpe=round(actual_sharpe, 4),
        final_pnl_percentiles=_percentiles(final_pnls),
        max_dd_percentiles=_percentiles(max_dds),
        sharpe_percentiles=_percentiles(sharpes),
        ruin_probability=ruin_prob,
        ruin_threshold=ruin_threshold,
        equity_curves=equity_curves,
    )


def mc_result_to_dict(result: MonteCarloResult) -> dict:
    """Convert MonteCarloResult to a JSON-serializable dict."""
    return {
        "method": result.method,
        "n_simulations": result.n_simulations,
        "n_trades": result.n_trades,
        "actual_final_pnl": result.actual_final_pnl,
        "actual_max_drawdown": result.actual_max_drawdown,
        "actual_sharpe": result.actual_sharpe,
        "final_pnl_percentiles": result.final_pnl_percentiles,
        "max_dd_percentiles": result.max_dd_percentiles,
        "sharpe_percentiles": result.sharpe_percentiles,
        "ruin_probability": result.ruin_probability,
        "ruin_threshold": result.ruin_threshold,
    }
