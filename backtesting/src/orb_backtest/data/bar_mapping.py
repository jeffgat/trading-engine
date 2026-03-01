"""Map between bar indices across timeframes for hierarchical bar-magnifier mode."""

from __future__ import annotations

import numpy as np
import pandas as pd

# Timeframe widths in nanoseconds
_5MIN_NS = np.int64(5 * 60 * 1_000_000_000)
_1MIN_NS = np.int64(60 * 1_000_000_000)
_30SEC_NS = np.int64(30 * 1_000_000_000)


def _to_ns(index: pd.DatetimeIndex) -> np.ndarray:
    """Convert a DatetimeIndex to int64 nanoseconds since epoch.

    Parquet files may store timestamps as datetime64[us]; this normalises to
    nanoseconds so the constants (_5MIN_NS etc.) remain correct regardless of
    the source format.
    """
    return index.values.astype("datetime64[ns]").astype(np.int64)


def _make_map(ts_coarse: np.ndarray, ts_fine: np.ndarray) -> np.ndarray:
    """Build a coarse→fine index map using a single searchsorted call.

    For time-aligned bar hierarchies, the end of bar i's sub-bar range equals
    the start of bar i+1's sub-bar range (``ends[i] = starts[i+1]``). This
    eliminates the second searchsorted call, halving map-build time for dense
    arrays (especially critical for 30s→1s with 84M rows).

    Parameters
    ----------
    ts_coarse : np.ndarray
        int64 nanosecond timestamps for the coarser timeframe.
    ts_fine : np.ndarray
        int64 nanosecond timestamps for the finer timeframe.

    Returns
    -------
    np.ndarray
        Shape ``(len(ts_coarse), 2)``.
    """
    starts = np.searchsorted(ts_fine, ts_coarse, side="left")
    ends = np.empty(len(starts), dtype=np.int64)
    if len(starts) > 0:
        ends[:-1] = starts[1:]
        ends[-1] = len(ts_fine)
    return np.column_stack((starts, ends))


def build_5m_to_1m_map(df_5m: pd.DataFrame, df_1m: pd.DataFrame) -> np.ndarray:
    """Build an index map from 5m bars to their constituent 1m bars.

    Parameters
    ----------
    df_5m : pd.DataFrame
        5-minute DataFrame with a DatetimeIndex.
    df_1m : pd.DataFrame
        1-minute DataFrame with a DatetimeIndex.

    Returns
    -------
    np.ndarray
        Shape ``(len(df_5m), 2)``.  For row *i*, ``[i, 0]`` is the first
        1m index (inclusive) and ``[i, 1]`` is one-past-the-last (exclusive).
        An empty range (both values equal) means no 1m bars matched.
    """
    return _make_map(_to_ns(df_5m.index), _to_ns(df_1m.index))


def build_1m_to_30s_map(df_1m: pd.DataFrame, df_30s: pd.DataFrame) -> np.ndarray:
    """Build an index map from 1m bars to their constituent 30s bars.

    Parameters
    ----------
    df_1m : pd.DataFrame
        1-minute DataFrame with a DatetimeIndex.
    df_30s : pd.DataFrame
        30-second DataFrame with a DatetimeIndex.

    Returns
    -------
    np.ndarray
        Shape ``(len(df_1m), 2)``.  For row *j*, ``[j, 0]`` is the first
        30s index (inclusive) and ``[j, 1]`` is one-past-the-last (exclusive).
    """
    return _make_map(_to_ns(df_1m.index), _to_ns(df_30s.index))


def build_30s_to_1s_map(df_30s: pd.DataFrame, df_1s: pd.DataFrame) -> np.ndarray:
    """Build an index map from 30s bars to their constituent 1s bars.

    Parameters
    ----------
    df_30s : pd.DataFrame
        30-second DataFrame with a DatetimeIndex.
    df_1s : pd.DataFrame
        1-second DataFrame with a DatetimeIndex.

    Returns
    -------
    np.ndarray
        Shape ``(len(df_30s), 2)``.  For row *k*, ``[k, 0]`` is the first
        1s index (inclusive) and ``[k, 1]`` is one-past-the-last (exclusive).
    """
    return _make_map(_to_ns(df_30s.index), _to_ns(df_1s.index))


def build_1m_to_1s_map(df_1m: pd.DataFrame, df_1s: pd.DataFrame) -> np.ndarray:
    """Build an index map from 1m bars to their constituent 1s bars.

    Parameters
    ----------
    df_1m : pd.DataFrame
        1-minute DataFrame with a DatetimeIndex.
    df_1s : pd.DataFrame
        1-second DataFrame with a DatetimeIndex.

    Returns
    -------
    np.ndarray
        Shape ``(len(df_1m), 2)``.  For row *j*, ``[j, 0]`` is the first
        1s index (inclusive) and ``[j, 1]`` is one-past-the-last (exclusive).
    """
    return _make_map(_to_ns(df_1m.index), _to_ns(df_1s.index))


def map_1m_to_5m(bar_1m: int, bar_map: np.ndarray) -> int:
    """Find the 5m bar that contains a given 1m bar index.

    Parameters
    ----------
    bar_1m : int
        Index into the 1m DataFrame.
    bar_map : np.ndarray
        The ``(n_5m, 2)`` map returned by :func:`build_5m_to_1m_map`.

    Returns
    -------
    int
        Index of the owning 5m bar, or ``-1`` if *bar_1m* is negative.
    """
    if bar_1m < 0:
        return -1

    # bar_map[:, 0] contains the inclusive start of each 5m bar's 1m range.
    # The 5m bar that owns bar_1m is the last one whose start <= bar_1m.
    idx = int(np.searchsorted(bar_map[:, 0], bar_1m, side="right")) - 1

    if idx < 0:
        return -1
    return idx
