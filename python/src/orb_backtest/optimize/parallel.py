"""Parallel execution of grid sweeps using multiprocessing."""

from __future__ import annotations

import time
from multiprocessing import Pool, cpu_count
from typing import Callable

import pandas as pd

from ..config import StrategyConfig
from ..engine.simulator import run_backtest, TradeResult


def _run_single(args: tuple) -> tuple[dict, list[TradeResult]]:
    """Worker function for multiprocessing. Takes (config_dict, df_bytes) tuple."""
    import pickle
    config, df_bytes = args
    df = pickle.loads(df_bytes)
    trades = run_backtest(df, config)
    return config, trades


def run_sweep(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
) -> list[tuple[StrategyConfig, list[TradeResult]]]:
    """Run backtests for all configs, optionally in parallel.

    Args:
        df: 5-minute OHLCV DataFrame.
        configs: List of strategy configurations to test.
        n_workers: Number of parallel workers (None = cpu_count).
        progress_fn: Optional callback(completed, total) for progress reporting.

    Returns:
        List of (config, trades) tuples in the same order as configs.
    """
    if n_workers is None:
        n_workers = min(cpu_count(), len(configs))

    if n_workers <= 1 or len(configs) <= 1:
        # Sequential execution (simpler, no overhead)
        results = []
        for i, config in enumerate(configs):
            trades = run_backtest(df, config)
            results.append((config, trades))
            if progress_fn:
                progress_fn(i + 1, len(configs))
        return results

    # Parallel execution
    import pickle
    df_bytes = pickle.dumps(df)

    args_list = [(config, df_bytes) for config in configs]

    results = []
    with Pool(n_workers) as pool:
        for i, result in enumerate(pool.imap(_run_single, args_list)):
            results.append(result)
            if progress_fn:
                progress_fn(i + 1, len(configs))

    return results


def run_sweep_sequential(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
    progress_fn: Callable[[int, int], None] | None = None,
) -> list[tuple[StrategyConfig, list[TradeResult]]]:
    """Run backtests sequentially (useful for debugging or when numba cache is cold)."""
    results = []
    for i, config in enumerate(configs):
        trades = run_backtest(df, config)
        results.append((config, trades))
        if progress_fn:
            progress_fn(i + 1, len(configs))
    return results
