"""Parallel execution of grid sweeps using multiprocessing."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pickle
import tempfile
import time
from multiprocessing import Pool, cpu_count
from pathlib import Path
from typing import Callable

import pandas as pd

from ..config import StrategyConfig
from ..engine.simulator import run_backtest, build_maps, build_signal_cache, TradeResult


def _run_single(args: tuple) -> tuple[dict, list[TradeResult]]:
    """Worker function for multiprocessing.

    Receives pre-serialised 5m arrays, pre-built maps, and pre-computed signal
    cache so workers skip all map construction, DataFrame unpickling, and signal
    recomputation overhead.
    """
    config, df_bytes, start_date, maps_bytes, signal_cache_bytes = args
    df = pickle.loads(df_bytes)
    maps = pickle.loads(maps_bytes) if maps_bytes is not None else None
    signal_cache = pickle.loads(signal_cache_bytes) if signal_cache_bytes is not None else None
    trades = run_backtest(df, config, start_date=start_date, _maps=maps, _signal_cache=signal_cache)
    return config, trades


def _signal_cache_path(df: pd.DataFrame, configs: list[StrategyConfig]) -> Path:
    """Stable disk cache key for signal cache: hash of data bounds + unique signal params.

    Uses dataclasses.asdict() for content-based config hashing — stable across
    process restarts (unlike Python's built-in hash() which is PYTHONHASHSEED-randomized).
    """
    # Data identity: first timestamp + last timestamp + row count
    data_key = f"{df.index[0]}_{df.index[-1]}_{len(df)}"
    # Content-based key — sorts the full config dict so any param change invalidates cache
    unique_keys = sorted({
        json.dumps(dataclasses.asdict(c), sort_keys=True, default=str)
        for c in configs
    })
    param_key = hashlib.md5(json.dumps(unique_keys).encode()).hexdigest()[:8]
    # Store in data/cache/ — go up from optimize/ -> orb_backtest/ -> src/ -> python/ -> data/cache/
    cache_dir = Path(__file__).parent.parent.parent.parent / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    safe_data_key = str(data_key)[:20].replace(" ", "_").replace(":", "-")
    return cache_dir / f"sigcache_{safe_data_key}_{param_key}.pkl"


def _load_or_build_signal_cache(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
) -> object:
    """Load signal cache from disk if available, otherwise build and save it."""
    cache_path = _signal_cache_path(df, configs)
    if cache_path.exists():
        print(f"[cache] Signal cache loaded from disk: {cache_path.name}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    print("[cache] Building signal cache...")
    t0 = time.time()
    signal_cache = build_signal_cache(df, configs)
    print(f"[cache] Signal cache built in {time.time()-t0:.1f}s — saving to disk")
    # Atomic write: write to temp file then rename so concurrent readers never see a partial file
    tmp_fd, tmp_path = tempfile.mkstemp(dir=cache_path.parent, suffix=".pkl.tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            pickle.dump(signal_cache, f)
        os.replace(tmp_path, cache_path)
    except Exception:
        os.unlink(tmp_path)
        raise
    return signal_cache


def _warmup_numba(df: pd.DataFrame, configs: list[StrategyConfig]) -> None:
    """Trigger Numba JIT compilation before Pool launch so workers start warm.

    Numba caches compiled bytecode to __pycache__ (cache=True). Calling
    run_backtest once here writes the cache; workers then load it without
    recompiling, saving ~0.5-1s per worker on first call.
    """
    if not configs:
        return
    # Use the first config with a small date range — just enough to trigger JIT
    dummy_config = configs[0]
    try:
        run_backtest(df, dummy_config)
    except Exception:
        pass  # warmup is best-effort


def run_sweep(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
    start_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
) -> list[tuple[StrategyConfig, list[TradeResult]]]:
    """Run backtests for all configs, optionally in parallel.

    Bar maps (5m→1m, 1m→30s, 30s→1s) are built **once** before the sweep and
    reused across all configs. For GC with all tiers this saves ~4 s per config
    (~67 minutes per 1000-config sweep).

    Signal arrays (ATR, session masks, ORB levels, FVG detection) are also
    pre-computed **once** per unique parameter combination and reused. For a
    1000-config sweep where only rr/tp1_ratio vary, this saves ~11 minutes.

    Args:
        df: 5-minute OHLCV DataFrame (should include warmup data).
        configs: List of strategy configurations to test.
        n_workers: Number of parallel workers (None = cpu_count).
        progress_fn: Optional callback(completed, total) for progress reporting.
        start_date: Only return trades on or after this date (YYYY-MM-DD).
        df_1m: Optional 1-minute DataFrame.
        df_30s: Optional 30-second DataFrame (GC only for now).
        df_1s: Optional 1-second DataFrame (GC only for now).

    Returns:
        List of (config, trades) tuples (order may differ from input when using
        parallel mode; configs are matched by content via the returned tuples).
    """
    if n_workers is None:
        n_workers = min(cpu_count(), len(configs))

    # Build bar maps and signal cache once — reused across all configs.
    # Maps: saves ~4s/config for GC full-history (~67 min per 1000-config sweep).
    # Signal cache: saves ~650ms/config (~11 min per 1000-config sweep).
    maps = build_maps(df, df_1m, df_30s, df_1s)
    signal_cache = _load_or_build_signal_cache(df, configs)

    if n_workers <= 1 or len(configs) <= 1:
        # Sequential execution — pass pre-built caches on every call
        results = []
        for i, config in enumerate(configs):
            trades = run_backtest(
                df, config, start_date=start_date,
                _maps=maps, _signal_cache=signal_cache,
            )
            results.append((config, trades))
            if progress_fn:
                progress_fn(i + 1, len(configs))
        return results

    # Warmup Numba JIT before workers launch — compiled bytecode is cached and
    # reused by all workers, eliminating per-worker recompilation overhead.
    _warmup_numba(df, configs)

    # Parallel execution — serialise df, maps, and signal_cache once each;
    # all workers share the same bytes without re-pickling per task.
    df_bytes           = pickle.dumps(df)
    maps_bytes         = pickle.dumps(maps)
    signal_cache_bytes = pickle.dumps(signal_cache)

    args_list = [
        (config, df_bytes, start_date, maps_bytes, signal_cache_bytes)
        for config in configs
    ]

    # imap_unordered avoids ordering bookkeeping (~5% throughput gain).
    # Chunksize reduces scheduler overhead for large sweeps.
    chunksize = max(1, len(configs) // (n_workers * 10))

    results = []
    with Pool(n_workers) as pool:
        for i, result in enumerate(pool.imap_unordered(_run_single, args_list, chunksize=chunksize)):
            results.append(result)
            if progress_fn:
                progress_fn(i + 1, len(configs))

    return results


def run_sweep_sequential(
    df: pd.DataFrame,
    configs: list[StrategyConfig],
    progress_fn: Callable[[int, int], None] | None = None,
    start_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
) -> list[tuple[StrategyConfig, list[TradeResult]]]:
    """Run backtests sequentially (useful for debugging or when numba cache is cold)."""
    maps = build_maps(df, df_1m, df_30s, df_1s)
    signal_cache = _load_or_build_signal_cache(df, configs)
    results = []
    for i, config in enumerate(configs):
        trades = run_backtest(
            df, config, start_date=start_date,
            _maps=maps, _signal_cache=signal_cache,
        )
        results.append((config, trades))
        if progress_fn:
            progress_fn(i + 1, len(configs))
    return results
