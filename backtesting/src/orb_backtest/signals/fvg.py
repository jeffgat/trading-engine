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
    close: np.ndarray | None = None,
    impulse_close_filter: bool = False,
    min_gap_orb_pct: float = 0.0,
) -> dict[str, np.ndarray]:
    """Detect FVG signals with gap size validation.

    Args:
        high: High prices array.
        low: Low prices array.
        daily_atr: Daily ATR values mapped to each bar.
        orb_high: ORB high for each bar (NaN before ready).
        orb_low: ORB low for each bar (NaN before ready).
        min_gap_atr_pct: Minimum gap size as % of daily ATR.
        close: Close prices array (needed when impulse_close_filter is True).
        impulse_close_filter: When True, also accept FVGs where bar[1]'s close
            is outside the ORB range, even if the gap zone itself is inside.
        min_gap_orb_pct: Minimum gap size as % of ORB range (0 = use ATR-based).

    Returns:
        Dict with keys:
            'long_fvg': bool array — bullish FVG detected
            'short_fvg': bool array — bearish FVG detected
            'long_entry_price': float array — FVG top (entry for longs)
            'short_entry_price': float array — FVG bottom (entry for shorts)
            'long_gap_size': float array — gap size for bullish FVGs
            'short_gap_size': float array — gap size for bearish FVGs
    """
    n = len(high)

    # Shifted arrays (bar[1] and bar[2] relative to current bar[0])
    high_1 = np.roll(high, 1)
    low_1 = np.roll(low, 1)
    high_2 = np.roll(high, 2)
    low_2 = np.roll(low, 2)

    # Invalidate first 2 bars (no lookback data)
    high_1[:1] = np.nan
    low_1[:1] = np.nan
    high_2[:2] = np.nan
    low_2[:2] = np.nan

    # FVG components
    long_fvg_top = low  # bar[0] low = top of bullish gap
    long_fvg_bottom = high_2  # bar[2] high = bottom of bullish gap
    short_fvg_top = low_2  # bar[2] low = top of bearish gap
    short_fvg_bottom = high  # bar[0] high = bottom of bearish gap

    long_gap_size = long_fvg_top - long_fvg_bottom
    short_gap_size = short_fvg_top - short_fvg_bottom

    # Minimum gap threshold — ORB-based or ATR-based
    if min_gap_orb_pct > 0:
        orb_range = orb_high - orb_low
        min_gap = (min_gap_orb_pct / 100.0) * np.where(orb_range > 0, orb_range, np.inf)
    else:
        min_gap = (min_gap_atr_pct / 100.0) * np.where(np.isnan(daily_atr), 0.0, daily_atr)

    # Gap validity
    long_gap_valid = long_gap_size >= min_gap
    short_gap_valid = short_gap_size >= min_gap

    # ORB directional filter — optionally relaxed by impulse candle close
    if impulse_close_filter and close is not None:
        close_1 = np.roll(close, 1)
        close_1[:1] = np.nan
        long_orb_ok = (long_fvg_top > orb_high) | (close_1 > orb_high)
        short_orb_ok = (short_fvg_bottom < orb_low) | (close_1 < orb_low)
    else:
        long_orb_ok = long_fvg_top > orb_high
        short_orb_ok = short_fvg_bottom < orb_low

    # Bullish FVG pattern (Pine: lines 639)
    long_fvg = (
        (high_2 < low)
        & (high_2 < high_1)
        & (low_2 < low)
        & long_orb_ok
        & long_gap_valid
        & ~np.isnan(orb_high)  # ORB must be ready
    )

    # Bearish FVG pattern (Pine: line 640)
    short_fvg = (
        (low_2 > high)
        & (low_2 > low_1)  # low[2] > low[1]
        & (high_2 > high)
        & short_orb_ok
        & short_gap_valid
        & ~np.isnan(orb_low)  # ORB must be ready
    )

    # Clean up first 2 bars
    long_fvg[:2] = False
    short_fvg[:2] = False

    return {
        "long_fvg": long_fvg,
        "short_fvg": short_fvg,
        "long_entry_price": long_fvg_top,
        "short_entry_price": short_fvg_bottom,
        "long_gap_size": long_gap_size,
        "short_gap_size": short_gap_size,
        # Zone boundaries for inversion detection
        "long_fvg_bottom": long_fvg_bottom,  # high[2]
        "short_fvg_top": short_fvg_top,      # low[2]
    }


def detect_fvg_no_orb(
    high: np.ndarray,
    low: np.ndarray,
    daily_atr: np.ndarray,
    min_gap_atr_pct: float,
) -> dict[str, np.ndarray]:
    """Detect FVGs without any ORB directional filter.

    Same as detect_fvg() but removes the requirement that bullish FVGs sit
    above the ORB high and bearish FVGs sit below the ORB low. Any valid
    3-candle FVG pattern in the session qualifies, regardless of direction
    relative to the opening range. Used for no-ORB liquidity sweep inversions.
    """
    n = len(high)

    high_1 = np.roll(high, 1)
    low_1 = np.roll(low, 1)
    high_2 = np.roll(high, 2)
    low_2 = np.roll(low, 2)

    high_1[:1] = np.nan
    low_1[:1] = np.nan
    high_2[:2] = np.nan
    low_2[:2] = np.nan

    long_fvg_top = low
    long_fvg_bottom = high_2
    short_fvg_top = low_2
    short_fvg_bottom = high

    long_gap_size = long_fvg_top - long_fvg_bottom
    short_gap_size = short_fvg_top - short_fvg_bottom

    min_gap = (min_gap_atr_pct / 100.0) * np.where(np.isnan(daily_atr), 0.0, daily_atr)

    long_gap_valid = long_gap_size >= min_gap
    short_gap_valid = short_gap_size >= min_gap

    # No ORB directional filter — any valid FVG pattern qualifies
    long_fvg = (
        (high_2 < low)
        & (high_2 < high_1)
        & (low_2 < low)
        & long_gap_valid
    )

    short_fvg = (
        (low_2 > high)
        & (low_2 > low_1)
        & (high_2 > high)
        & short_gap_valid
    )

    long_fvg[:2] = False
    short_fvg[:2] = False

    return {
        "long_fvg": long_fvg,
        "short_fvg": short_fvg,
        "long_entry_price": long_fvg_top,
        "short_entry_price": short_fvg_bottom,
        "long_gap_size": long_gap_size,
        "short_gap_size": short_gap_size,
        "long_fvg_bottom": long_fvg_bottom,
        "short_fvg_top": short_fvg_top,
    }
