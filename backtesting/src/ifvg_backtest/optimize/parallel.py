"""Parallel sweep runner for IFVG strategy optimization.

Uses a persistent worker pool (like orb_backtest) to avoid per-sweep
Pool() creation overhead and keep Numba bytecode warm across sweeps.
"""

from __future__ import annotations

import atexit
import pickle
from multiprocessing import Pool, cpu_count
from typing import Callable

import pandas as pd

from ..config import IFVGConfig
from ..engine.simulator import run_backtest, TradeResult
from ..results.metrics import compute_metrics

# ---------------------------------------------------------------------------
# Persistent worker pool — avoids per-sweep Pool() creation overhead (~300ms)
# and keeps Numba bytecode warm in worker processes across sweeps.
# ---------------------------------------------------------------------------

_pool: Pool | None = None
_pool_n_workers: int = 0
_pool_warmed: bool = False

# ---------------------------------------------------------------------------
# Pickle-bytes cache — avoids re-serialising large DataFrames on every
# run_sweep() call when the same objects are reused across consecutive sweeps.
# Keyed by id(obj), valid while the object is alive.  Cleared when the worker
# pool is recreated (which is the point where new data might be loaded).
# ---------------------------------------------------------------------------
_pickle_cache: dict[int, bytes] = {}


def _cached_pickle(obj: object) -> bytes:
    """Memoize pickle.dumps by object id — valid while obj is alive."""
    oid = id(obj)
    if oid not in _pickle_cache:
        _pickle_cache[oid] = pickle.dumps(obj)
    return _pickle_cache[oid]


def _get_or_create_pool(n_workers: int) -> Pool:
    """Return the module-level Pool, creating or replacing it if needed."""
    global _pool, _pool_n_workers, _pool_warmed
    if _pool is None or _pool_n_workers != n_workers:
        if _pool is not None:
            _pool.terminate()
            _pool.join()
        _pickle_cache.clear()
        _pool = Pool(n_workers)
        _pool_n_workers = n_workers
        _pool_warmed = False
    return _pool


def _shutdown_pool():
    global _pool
    if _pool is not None:
        _pool.terminate()
        _pool.join()
        _pool = None
    _pickle_cache.clear()

atexit.register(_shutdown_pool)


def _warmup_numba(df: pd.DataFrame, configs: list[IFVGConfig]) -> None:
    """Trigger Numba JIT compilation before Pool launch so workers start warm.

    Numba caches compiled bytecode to __pycache__ (cache=True). Calling
    run_backtest once here writes the cache; workers then load it without
    recompiling, saving ~0.5-1s per worker on first call.
    """
    if not configs:
        return
    try:
        run_backtest(df, configs[0])
    except Exception:
        pass  # warmup is best-effort


def _run_single(args: tuple) -> tuple[dict, list[TradeResult], dict]:
    """Worker function: run one backtest and return (config_dict, trades, metrics).

    Receives pre-serialised DataFrames to avoid per-worker pickle overhead.
    """
    config, df_bytes, start_date, end_date, df_1m_bytes = args
    df = pickle.loads(df_bytes)
    df_1m = pickle.loads(df_1m_bytes) if df_1m_bytes is not None else None

    trades = run_backtest(df, config, start_date=start_date, end_date=end_date, df_1m=df_1m)
    metrics = compute_metrics(trades)

    # Config as dict for serialization
    config_dict = {
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "risk_usd": config.risk_usd,
        "min_gap_atr_pct": config.min_gap_atr_pct,
        "gap_window_bars": config.gap_window_bars,
        "max_bars_after_sweep": config.max_bars_after_sweep,
        "be_offset_ticks": config.be_offset_ticks,
        "min_stop_atr_pct": config.min_stop_atr_pct,
        "candle_tf": config.candle_tf,
        "direction_filter": config.direction_filter,
        "entry_type": config.entry_type,
        "bpr_filter": config.bpr_filter,
        "bpr_tight_max_bars": config.bpr_tight_max_bars,
        "use_pdh_sweeps": config.use_pdh_sweeps,
        "use_pdl_sweeps": config.use_pdl_sweeps,
        "max_inversion_bars": config.max_inversion_bars,
        "use_swing_high_sweeps": config.use_swing_high_sweeps,
        "use_swing_low_sweeps": config.use_swing_low_sweeps,
        "swing_length": config.swing_length,
    }
    if config.instrument:
        config_dict["instrument"] = config.instrument.symbol

    return config_dict, trades, metrics


def run_sweep(
    df: pd.DataFrame,
    configs: list[IFVGConfig],
    n_workers: int | None = None,
    progress_fn: Callable[[int, int], None] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
) -> list[tuple[IFVGConfig, list[TradeResult], dict]]:
    """Run parallel parameter sweep.

    Args:
        df: 5-minute OHLCV DataFrame.
        configs: List of IFVGConfig to evaluate.
        n_workers: Number of parallel processes (default: CPU count - 1).
        progress_fn: Optional callback(completed, total) for progress reporting.
        start_date: Only return trades on or after this date.
        end_date: Exclude trades on or after this date.
        df_1m: Optional 1-minute data for non-5m candle timeframes.

    Returns:
        List of (config, trades, metrics) tuples, one per config.
    """
    if n_workers is None:
        n_workers = min(max(1, cpu_count() - 1), len(configs))

    if n_workers <= 1 or len(configs) <= 1:
        # Sequential execution
        results = []
        for i, config in enumerate(configs):
            trades = run_backtest(df, config, start_date=start_date, end_date=end_date, df_1m=df_1m)
            metrics = compute_metrics(trades)
            results.append((config, trades, metrics))
            if progress_fn:
                progress_fn(i + 1, len(configs))
        return results

    # Warmup Numba JIT once — skip if pool workers are already warm from a prior sweep.
    global _pool_warmed
    if not _pool_warmed:
        _warmup_numba(df, configs)

    # Parallel execution — serialise df and df_1m once each;
    # all workers share the same bytes without re-pickling per task.
    # Clear cache between sweep calls to prevent id()-aliasing when different
    # DataFrame slices (e.g. per-fold WF) reuse the same memory address.
    _pickle_cache.clear()
    df_bytes = _cached_pickle(df)
    df_1m_bytes = _cached_pickle(df_1m) if df_1m is not None else None

    args_list = [
        (config, df_bytes, start_date, end_date, df_1m_bytes)
        for config in configs
    ]

    # imap_unordered avoids ordering bookkeeping (~5% throughput gain).
    # Chunksize reduces scheduler overhead for large sweeps.
    chunksize = max(1, len(configs) // (n_workers * 4))

    pool = _get_or_create_pool(n_workers)
    results = []
    try:
        for i, (config_dict, trades, metrics) in enumerate(
            pool.imap_unordered(_run_single, args_list, chunksize=chunksize)
        ):
            # Match config_dict back to the original IFVGConfig
            # by finding the config whose key params match
            matched_config = _match_config(config_dict, configs)
            results.append((matched_config, trades, metrics))
            if progress_fn:
                progress_fn(i + 1, len(configs))
    except Exception:
        # Worker crash — invalidate pool so it's recreated on next call
        global _pool, _pool_n_workers
        _pool = None
        _pool_n_workers = 0
        _pool_warmed = False
        _pickle_cache.clear()
        raise

    _pool_warmed = True
    return results


def _match_config(config_dict: dict, configs: list[IFVGConfig]) -> IFVGConfig:
    """Find the IFVGConfig that matches a serialized config dict."""
    for c in configs:
        if (c.rr == config_dict.get("rr") and
            c.min_gap_atr_pct == config_dict.get("min_gap_atr_pct") and
            c.gap_window_bars == config_dict.get("gap_window_bars") and
            c.max_bars_after_sweep == config_dict.get("max_bars_after_sweep") and
            c.be_offset_ticks == config_dict.get("be_offset_ticks") and
            c.candle_tf == config_dict.get("candle_tf") and
            c.direction_filter == config_dict.get("direction_filter") and
            c.entry_type == config_dict.get("entry_type") and
            c.bpr_filter == config_dict.get("bpr_filter") and
            c.tp1_ratio == config_dict.get("tp1_ratio") and
            c.min_stop_atr_pct == config_dict.get("min_stop_atr_pct") and
            c.max_inversion_bars == config_dict.get("max_inversion_bars") and
            c.bpr_tight_max_bars == config_dict.get("bpr_tight_max_bars")):
            return c
    # Fallback: return first config (shouldn't happen in practice)
    return configs[0]


def run_sweep_sequential(
    df: pd.DataFrame,
    configs: list[IFVGConfig],
    progress_fn: Callable[[int, int], None] | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    df_1m: pd.DataFrame | None = None,
) -> list[tuple[IFVGConfig, list[TradeResult], dict]]:
    """Run backtests sequentially (useful for debugging or when numba cache is cold)."""
    results = []
    for i, config in enumerate(configs):
        trades = run_backtest(df, config, start_date=start_date, end_date=end_date, df_1m=df_1m)
        metrics = compute_metrics(trades)
        results.append((config, trades, metrics))
        if progress_fn:
            progress_fn(i + 1, len(configs))
    return results
