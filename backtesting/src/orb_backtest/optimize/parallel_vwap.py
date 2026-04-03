"""Parallel execution of VWAP grid sweeps using multiprocessing."""

from __future__ import annotations

import atexit
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

from ..vwap_config import VWAPStrategyConfig
from ..engine.vwap_simulator import run_vwap_backtest, build_vwap_signal_cache
from ..engine.simulator import TradeResult, build_maps

# Reuse the persistent pool from the ORB parallel module
from .parallel import (
    _get_or_create_pool,
    _cached_pickle,
    _dataframe_cache_fingerprint,
    _pickle_cache,
)


def _run_single_vwap(args: tuple) -> tuple[dict, list[TradeResult]]:
    """Worker function for VWAP multiprocessing."""
    config, df_bytes, start_date, end_date, maps_bytes, signal_cache_bytes = args
    df = pickle.loads(df_bytes)
    maps = pickle.loads(maps_bytes) if maps_bytes is not None else None
    signal_cache = pickle.loads(signal_cache_bytes) if signal_cache_bytes is not None else None
    trades = run_vwap_backtest(
        df, config, start_date=start_date, end_date=end_date,
        _maps=maps, _signal_cache=signal_cache,
    )
    return config, trades


def _vwap_signal_cache_path(df: pd.DataFrame, configs: list[VWAPStrategyConfig]) -> Path:
    """Stable disk cache key for VWAP signal cache."""
    data_hash = _dataframe_cache_fingerprint(df)[:12]
    unique_keys = sorted({
        json.dumps(dataclasses.asdict(c), sort_keys=True, default=str)
        for c in configs
    })
    param_key = hashlib.md5(json.dumps(unique_keys).encode()).hexdigest()[:8]
    cache_dir = Path(__file__).parent.parent.parent.parent / "data" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"vwap_sigcache_{data_hash}_{param_key}.pkl"


def _load_or_build_vwap_signal_cache(
    df: pd.DataFrame,
    configs: list[VWAPStrategyConfig],
) -> object:
    """Load VWAP signal cache from disk if available, otherwise build and save it."""
    cache_path = _vwap_signal_cache_path(df, configs)
    if cache_path.exists():
        print(f"[cache] VWAP signal cache loaded from disk: {cache_path.name}")
        with open(cache_path, "rb") as f:
            return pickle.load(f)
    print("[cache] Building VWAP signal cache...")
    t0 = time.time()
    signal_cache = build_vwap_signal_cache(df, configs)
    print(f"[cache] VWAP signal cache built in {time.time()-t0:.1f}s — saving to disk")
    tmp_fd, tmp_path = tempfile.mkstemp(dir=cache_path.parent, suffix=".pkl.tmp")
    try:
        with os.fdopen(tmp_fd, "wb") as f:
            pickle.dump(signal_cache, f)
        os.replace(tmp_path, cache_path)
    except Exception:
        os.unlink(tmp_path)
        raise
    return signal_cache


def run_vwap_sweep(
    df: pd.DataFrame,
    configs: list[VWAPStrategyConfig],
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
    _prebuilt_signal_cache: object | None = None,
    _prebuilt_maps: object | None = None,
) -> list[tuple[VWAPStrategyConfig, list[TradeResult]]]:
    """Run VWAP backtests for all configs, optionally in parallel.

    Same interface as run_sweep() but for VWAP configs.
    """
    if not configs:
        return []

    if n_workers is None:
        n_workers = min(cpu_count(), len(configs))

    maps = _prebuilt_maps if _prebuilt_maps is not None else build_maps(df, df_1m)
    signal_cache = _prebuilt_signal_cache if _prebuilt_signal_cache is not None else _load_or_build_vwap_signal_cache(df, configs)

    if n_workers <= 1 or len(configs) <= 1:
        results = []
        for i, config in enumerate(configs):
            trades = run_vwap_backtest(
                df, config, start_date=start_date, end_date=end_date,
                _maps=maps, _signal_cache=signal_cache,
            )
            results.append((config, trades))
            if progress_fn:
                progress_fn(i + 1, len(configs))
        return results

    # Warmup: run one backtest to trigger Numba JIT (reuse pre-built caches)
    if configs:
        try:
            run_vwap_backtest(
                df, configs[0],
                start_date=start_date, end_date=end_date,
                _maps=maps, _signal_cache=signal_cache,
            )
        except Exception:
            pass

    _pickle_cache.clear()
    df_bytes = _cached_pickle(df)
    maps_bytes = _cached_pickle(maps)
    signal_cache_bytes = _cached_pickle(signal_cache)

    args_list = [
        (config, df_bytes, start_date, end_date, maps_bytes, signal_cache_bytes)
        for config in configs
    ]

    chunksize = max(1, len(configs) // (n_workers * 4))
    pool = _get_or_create_pool(n_workers)
    results = []
    try:
        for i, result in enumerate(pool.imap_unordered(_run_single_vwap, args_list, chunksize=chunksize)):
            results.append(result)
            if progress_fn:
                progress_fn(i + 1, len(configs))
    except Exception:
        raise

    return results
