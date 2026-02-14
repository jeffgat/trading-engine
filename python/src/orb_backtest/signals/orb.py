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
import pandas as pd


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
    n = len(df)
    high = df["high"].values
    low = df["low"].values

    orb_high = np.full(n, np.nan)
    orb_low = np.full(n, np.nan)
    orb_ready = np.zeros(n, dtype=bool)

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
                current_high = max(current_high, high[i])
                current_low = min(current_low, low[i])
        elif not ready and not np.isnan(current_high) and in_rth[i]:
            ready = True

        if ready:
            orb_high[i] = current_high
            orb_low[i] = current_low
            orb_ready[i] = True

    return orb_high, orb_low, orb_ready
