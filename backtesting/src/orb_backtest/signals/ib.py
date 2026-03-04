"""Initial Balance (IB) range computation and direction signal.

IB range = high/low of 9:30-10:30 ET (reuses orb_start/orb_end session fields).
Direction: if the IB low formed first (earlier bar) → LONG at midpoint.
           if the IB high formed first → SHORT at midpoint.
           if tied → skip (no trade).
"""

from __future__ import annotations

import numpy as np
import numba as nb
import pandas as pd


@nb.njit(cache=True)
def _compute_ib_levels_numba(
    high: np.ndarray,
    low: np.ndarray,
    in_ib: np.ndarray,
    in_rth: np.ndarray,
    new_day: np.ndarray,
) -> tuple:
    """Compute IB high, low, midpoint, direction, ready flag, and broken flag.

    Returns:
        ib_high: float array (NaN before IB complete)
        ib_low: float array
        ib_mid: float array (midpoint)
        ib_direction: int array (1=LONG, -1=SHORT, 0=skip)
        ib_ready: bool array (True after IB window closes)
        ib_broken: bool array (True if IB has been broken after ready)
    """
    n = len(high)
    ib_high = np.full(n, np.nan)
    ib_low = np.full(n, np.nan)
    ib_mid = np.full(n, np.nan)
    ib_direction = np.zeros(n, dtype=np.int64)
    ib_ready = np.zeros(n, dtype=nb.boolean)
    ib_broken = np.zeros(n, dtype=nb.boolean)

    cur_high = np.nan
    cur_low = np.nan
    high_bar = -1
    low_bar = -1
    ready = False
    broken = False
    direction = 0
    mid = np.nan
    frozen_high = np.nan
    frozen_low = np.nan

    for i in range(n):
        if new_day[i]:
            cur_high = np.nan
            cur_low = np.nan
            high_bar = -1
            low_bar = -1
            ready = False
            broken = False
            direction = 0
            mid = np.nan
            frozen_high = np.nan
            frozen_low = np.nan

        if in_ib[i]:
            if np.isnan(cur_high):
                cur_high = high[i]
                cur_low = low[i]
                high_bar = i
                low_bar = i
            else:
                if high[i] > cur_high:
                    cur_high = high[i]
                    high_bar = i
                if low[i] < cur_low:
                    cur_low = low[i]
                    low_bar = i
        elif not ready and not np.isnan(cur_high) and in_rth[i]:
            ready = True
            mid = (cur_high + cur_low) / 2.0
            frozen_high = cur_high
            frozen_low = cur_low
            if low_bar < high_bar:
                direction = 1   # low formed first → LONG
            elif high_bar < low_bar:
                direction = -1  # high formed first → SHORT
            else:
                direction = 0   # tie → skip

        if ready and not broken:
            if high[i] > frozen_high or low[i] < frozen_low:
                broken = True

        if ready:
            ib_high[i] = frozen_high
            ib_low[i] = frozen_low
            ib_mid[i] = mid
            ib_direction[i] = direction
            ib_ready[i] = True
            ib_broken[i] = broken

    return ib_high, ib_low, ib_mid, ib_direction, ib_ready, ib_broken


def compute_ib_levels(
    df: pd.DataFrame,
    in_ib: np.ndarray,
    in_rth: np.ndarray,
    new_day: np.ndarray,
) -> tuple:
    """Compute IB levels for each bar.

    Args:
        df: DataFrame with columns [high, low].
        in_ib: Boolean mask for bars within the IB window (orb_start to orb_end).
        in_rth: Boolean mask for bars within RTH.
        new_day: Boolean mask for first bar of each session day.

    Returns:
        Tuple of (ib_high, ib_low, ib_mid, ib_direction, ib_ready, ib_broken).
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    return _compute_ib_levels_numba(high, low, in_ib, in_rth, new_day)
