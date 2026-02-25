"""Parallel execution of grid sweeps using the qualifying-move engine."""

from __future__ import annotations

import pickle
from multiprocessing import cpu_count
from typing import Callable

import pandas as pd

from ..config import StrategyConfig
from ..engine.qualifying_move import run_backtest_qm
from ..engine.simulator import TradeResult, build_maps
from .parallel import _load_or_build_signal_cache, _warmup_numba, _get_or_create_pool

# ---------------------------------------------------------------------------
# Pickle-bytes cache — mirrors the one in parallel.py for the QM engine.
# Avoids re-serialising large DataFrames/arrays on every run_sweep_qm() call.
# ---------------------------------------------------------------------------
_pickle_cache: dict[int, bytes] = {}


def _cached_pickle(obj: object) -> bytes:
    """Memoize pickle.dumps by object id -- valid while obj is alive."""
    oid = id(obj)
    if oid not in _pickle_cache:
        _pickle_cache[oid] = pickle.dumps(obj)
    return _pickle_cache[oid]


def _run_single_qm(args: tuple) -> tuple[dict, list[TradeResult]]:
    """Worker function for multiprocessing.

    Receives pre-serialised 5m arrays, pre-built maps, and pre-computed signal
    cache so workers skip all map construction, DataFrame unpickling, and signal
    recomputation overhead.
    """
    config, df_bytes, start_date, end_date, df_1m_bytes, maps_bytes, signal_cache_bytes = args
    df = pickle.loads(df_bytes)
    df_1m = pickle.loads(df_1m_bytes) if df_1m_bytes is not None else None
    maps = pickle.loads(maps_bytes) if maps_bytes is not None else None
    signal_cache = pickle.loads(signal_cache_bytes) if signal_cache_bytes is not None else None
    trades = run_backtest_qm(df, config, start_date=start_date, end_date=end_date, df_1m=df_1m,
                             _maps=maps, _signal_cache=signal_cache)
    return config, trades


def run_sweep_qm(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    _prebuilt_signal_cache: object | None = None,
    _prebuilt_maps: object | None = None,
) -> list[tuple[StrategyConfig, list[TradeResult]]]:
    """Run backtests for all configs using the qualifying-move engine.

    Same interface as parallel.run_sweep but routes through run_backtest_qm.

    Bar maps (5m→1m) are built **once** before the sweep and reused across all
    configs. Signal arrays (ATR, session masks, ORB levels, FVG detection) are
    also pre-computed **once** per unique parameter combination and reused.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data).
        configs: List of strategy configurations to test.
        n_workers: Number of parallel workers (None = cpu_count).
        progress_fn: Optional callback(completed, total) for progress reporting.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
        df_1m: Optional 1-minute DataFrame.
        _prebuilt_signal_cache: Optional pre-built signal cache (from a prior
            call to _load_or_build_signal_cache). When supplied, skips cache
            construction entirely.
        _prebuilt_maps: Optional pre-built maps dict (from build_maps). When
            supplied, skips map construction entirely.

    Returns:
        List of (config, trades) tuples (order may differ from input when using
        parallel mode).
    """
    if n_workers is None:
        n_workers = min(cpu_count(), len(configs))

    # Build bar maps and signal cache once — reused across all configs.
    maps = _prebuilt_maps if _prebuilt_maps is not None else build_maps(df, df_1m, None, None)
    signal_cache = (_prebuilt_signal_cache if _prebuilt_signal_cache is not None
                    else _load_or_build_signal_cache(df, configs))

    if n_workers <= 1 or len(configs) <= 1:
        # Sequential execution — pass pre-built caches on every call
        results = []
        for i, config in enumerate(configs):
            trades = run_backtest_qm(df, config, start_date=start_date, end_date=end_date, df_1m=df_1m,
                                     _maps=maps, _signal_cache=signal_cache)
            results.append((config, trades))
            if progress_fn:
                progress_fn(i + 1, len(configs))
        return results

    # Warmup Numba JIT once — skip if pool workers are already warm from a prior sweep.
    # Uses the shared _pool_warmed flag from parallel.py (same worker pool).
    import orb_backtest.optimize.parallel as _par
    if not _par._pool_warmed:
        _warmup_numba(df, configs)

    # Parallel execution — serialise df, maps, and signal_cache once each;
    # all workers share the same bytes without re-pickling per task.
    # Clear cache between sweep calls to prevent id()-aliasing when different
    # DataFrame slices (e.g. per-fold WF) reuse the same memory address.
    _pickle_cache.clear()
    df_bytes           = _cached_pickle(df)
    df_1m_bytes        = _cached_pickle(df_1m) if df_1m is not None else None
    maps_bytes         = _cached_pickle(maps)
    signal_cache_bytes = _cached_pickle(signal_cache)

    args_list = [
        (config, df_bytes, start_date, end_date, df_1m_bytes, maps_bytes, signal_cache_bytes)
        for config in configs
    ]

    # imap_unordered avoids ordering bookkeeping (~5% throughput gain).
    # Chunksize reduces scheduler overhead for large sweeps.
    chunksize = max(1, len(configs) // (n_workers * 4))

    pool = _get_or_create_pool(n_workers)
    results = []
    try:
        for i, result in enumerate(pool.imap_unordered(_run_single_qm, args_list, chunksize=chunksize)):
            results.append(result)
            if progress_fn:
                progress_fn(i + 1, len(configs))
    except Exception:
        # Worker crash — invalidate pool so it's recreated on next call
        _par._pool = None
        _par._pool_n_workers = 0
        _par._pool_warmed = False
        _pickle_cache.clear()
        _par._pickle_cache.clear()
        raise

    _par._pool_warmed = True
    return results
