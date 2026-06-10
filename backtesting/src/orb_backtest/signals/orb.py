"""ORB (Opening Range Breakout) high/low computation.

Replicates Pine Script's ORB building logic:
    if inORB and is5m:
        orbHigh = max(orbHigh, high)
        orbLow  = min(orbLow, low)
    if not inORB and not orbReady and orbHigh exists:
        orbReady = true
"""

from __future__ import annotations

import numpy as np
import numba as nb
import pandas as pd


@nb.njit(cache=True)
def _compute_orb_levels_numba(
    high: np.ndarray,
    low: np.ndarray,
    in_orb: np.ndarray,
    in_rth: np.ndarray,
    new_day: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Numba-compiled ORB level computation."""
    n = len(high)
    orb_high = np.full(n, np.nan)
    orb_low = np.full(n, np.nan)
    orb_ready = np.zeros(n, dtype=nb.boolean)

    current_high = np.nan
    current_low = np.nan
    ready = False

    for i in range(n):
        if new_day[i]:
            current_high = np.nan
            current_low = np.nan
            ready = False

        if in_orb[i]:
            if np.isnan(current_high):
                current_high = high[i]
                current_low = low[i]
            else:
                if high[i] > current_high:
                    current_high = high[i]
                if low[i] < current_low:
                    current_low = low[i]
        elif not ready and not np.isnan(current_high) and in_rth[i]:
            ready = True

        if ready:
            orb_high[i] = current_high
            orb_low[i] = current_low
            orb_ready[i] = True

    return orb_high, orb_low, orb_ready


def compute_orb_levels(
    df: pd.DataFrame,
    in_orb: np.ndarray,
    in_rth: np.ndarray,
    new_day: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute ORB high/low levels for each bar.

    Args:
        df: DataFrame with columns [high, low].
        in_orb: Boolean mask for bars within the ORB window.
        in_rth: Boolean mask for bars within RTH.
        new_day: Boolean mask for first bar of each trading day.

    Returns:
        orb_high: ORB high for each bar (NaN before ORB completes, forward-filled after).
        orb_low: ORB low for each bar (NaN before ORB completes, forward-filled after).
        orb_ready: Boolean array, True after ORB window closes for that session day.
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    return _compute_orb_levels_numba(high, low, in_orb, in_rth, new_day)


@nb.njit(cache=True)
def _compute_orb_open_numba(
    open_: np.ndarray,
    in_orb: np.ndarray,
    in_rth: np.ndarray,
    new_day: np.ndarray,
) -> np.ndarray:
    """Numba-compiled completed ORB open computation."""
    n = len(open_)
    orb_open = np.full(n, np.nan)

    current_open = np.nan
    saw_orb = False
    ready = False

    for i in range(n):
        if new_day[i]:
            current_open = np.nan
            saw_orb = False
            ready = False

        if in_orb[i]:
            if not saw_orb:
                current_open = open_[i]
                saw_orb = True
        elif not ready and saw_orb and in_rth[i]:
            ready = True

        if ready:
            orb_open[i] = current_open

    return orb_open


def compute_orb_open(
    df: pd.DataFrame,
    in_orb: np.ndarray,
    in_rth: np.ndarray,
    new_day: np.ndarray,
) -> np.ndarray:
    """Compute the first ORB-window open, forward-filled after ORB completion."""
    open_ = df["open"].values.astype(np.float64)
    return _compute_orb_open_numba(open_, in_orb, in_rth, new_day)
