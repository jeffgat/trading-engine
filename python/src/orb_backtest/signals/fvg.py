"""Fair Value Gap (FVG) detection — fully vectorized.

Replicates Pine Script's FVG logic (HEAD_testing_a.pine lines 629-652):

Bullish FVG (3-candle pattern):
    high[2] < low[0]  AND  high[2] < high[1]  AND  low[2] < low[0]
    Gap = low[0] - high[2]
    Must be above ORB high

Bearish FVG:
    low[2] > high[0]  AND  low[2] > low[1]  AND  high[2] > high[0]
    Gap = low[2] - high[0]
    Must be below ORB low
"""

from __future__ import annotations

import numpy as np


def detect_fvg(
    high: np.ndarray,
    low: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    min_gap_atr_pct: float,
    max_gap_points: float,
) -> dict[str, np.ndarray]:
    """Detect FVG signals with gap size validation.

    Args:
        high: High prices array.
        low: Low prices array.
        daily_atr: Daily ATR values mapped to each bar.
        orb_high: ORB high for each bar (NaN before ready).
        orb_low: ORB low for each bar (NaN before ready).
        min_gap_atr_pct: Minimum gap size as % of daily ATR.
        max_gap_points: Maximum gap size in points (0 = no limit).

    Returns:
        Dict with keys:
            'long_fvg': bool array — bullish FVG detected
            'short_fvg': bool array — bearish FVG detected
            'long_entry_price': float array — FVG top (entry for longs)
            'short_entry_price': float array — FVG bottom (entry for shorts)
            'long_stop_ref': float array — low of bar[2] (not used as stop directly)
            'short_stop_ref': float array — high of bar[2] (not used as stop directly)
            'long_gap_size': float array — gap size for bullish FVGs
            'short_gap_size': float array — gap size for bearish FVGs
    """
    n = len(high)

    # Shifted arrays (bar[1] and bar[2] relative to current bar[0])
    high_1 = np.roll(high, 1)
    high_2 = np.roll(high, 2)
    low_2 = np.roll(low, 2)

    # Invalidate first 2 bars (no lookback data)
    high_1[:1] = np.nan
    high_2[:2] = np.nan
    low_2[:2] = np.nan

    # FVG components
    long_fvg_top = low  # bar[0] low = top of bullish gap
    long_fvg_bottom = high_2  # bar[2] high = bottom of bullish gap
    short_fvg_top = low_2  # bar[2] low = top of bearish gap
    short_fvg_bottom = high  # bar[0] high = bottom of bearish gap

    long_gap_size = long_fvg_top - long_fvg_bottom
    short_gap_size = short_fvg_top - short_fvg_bottom

    # Minimum gap from ATR
    min_gap = (min_gap_atr_pct / 100.0) * np.where(np.isnan(daily_atr), 0.0, daily_atr)

    # Gap validity
    long_gap_valid = long_gap_size >= min_gap
    short_gap_valid = short_gap_size >= min_gap

    if max_gap_points > 0:
        long_gap_valid &= long_gap_size <= max_gap_points
        short_gap_valid &= short_gap_size <= max_gap_points

    # Bullish FVG pattern (Pine: lines 639)
    long_fvg = (
        (high_2 < low)
        & (high_2 < high_1)
        & (low_2 < low)
        & (long_fvg_top > orb_high)
        & long_gap_valid
        & ~np.isnan(orb_high)  # ORB must be ready
    )

    # Bearish FVG pattern (Pine: line 640)
    short_fvg = (
        (low_2 > high)
        & (low_2 > np.roll(low, 1))  # low[2] > low[1]
        & (high_2 > high)
        & (short_fvg_bottom < orb_low)
        & short_gap_valid
        & ~np.isnan(orb_low)  # ORB must be ready
    )

    # Clean up first 2 bars
    long_fvg[:2] = False
    short_fvg[:2] = False

    return {
        "long_fvg": long_fvg,
        "short_fvg": short_fvg,
        "long_entry_price": np.where(long_fvg, long_fvg_top, np.nan),
        "short_entry_price": np.where(short_fvg, short_fvg_bottom, np.nan),
        "long_gap_size": np.where(long_fvg, long_gap_size, np.nan),
        "short_gap_size": np.where(short_fvg, short_gap_size, np.nan),
    }
