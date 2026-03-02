"""Vectorized swing high/low detection — no lookahead.

A confirmed swing high at bar j requires:
  - n_left bars before j all have lower highs
  - n_right bars after j all have lower highs

Because we need n_right bars after j, the confirmation is known at bar
i = j + n_right. So is_swing_high[i] is True when bar i - n_right was
a confirmed swing high, using only data up to bar i.

Symmetric logic applies for swing lows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def detect_swing_highs(
    high: np.ndarray,
    n_left: int,
    n_right: int,
) -> np.ndarray:
    """Return bool array marking confirmed swing highs.

    is_swing_high[i] is True when bar i - n_right was a confirmed swing high:
      - high[i - n_right] > max(high[i - n_right - n_left : i - n_right])
      - high[i - n_right] > max(high[i - n_right + 1 : i + 1])

    All required bars are in the past at bar i — no lookahead.

    Args:
        high: Array of bar high prices.
        n_left: Number of bars to the LEFT of the pivot that must have lower highs.
        n_right: Number of bars to the RIGHT of the pivot that must have lower highs.

    Returns:
        Boolean array of length len(high). True at bar i when the pivot at
        i - n_right is a confirmed swing high.
    """
    s = pd.Series(high, dtype=float)

    # Pivot value: high at bar (i - n_right)
    pivot = s.shift(n_right)

    # Max of n_left bars strictly BEFORE the pivot.
    # s.shift(1).rolling(n_left).max() at position i gives max(high[i-n_left:i]).
    # Shifting that by n_right gives max(high[i-n_right-n_left : i-n_right]).
    left_max = s.shift(1).rolling(n_left).max().shift(n_right)

    # Max of n_right bars strictly AFTER the pivot.
    # s.rolling(n_right).max() at position i gives max(high[i-n_right+1 : i+1]).
    # This window covers exactly the n_right bars after the pivot (excluding pivot itself).
    right_max = s.rolling(n_right).max()

    swing = (pivot > left_max) & (pivot > right_max)

    result = swing.to_numpy(dtype=bool, na_value=False)
    return result


def detect_swing_lows(
    low: np.ndarray,
    n_left: int,
    n_right: int,
) -> np.ndarray:
    """Return bool array marking confirmed swing lows.

    is_swing_low[i] is True when bar i - n_right was a confirmed swing low:
      - low[i - n_right] < min(low[i - n_right - n_left : i - n_right])
      - low[i - n_right] < min(low[i - n_right + 1 : i + 1])

    All required bars are in the past at bar i — no lookahead.

    Args:
        low: Array of bar low prices.
        n_left: Number of bars to the LEFT of the pivot that must have higher lows.
        n_right: Number of bars to the RIGHT of the pivot that must have higher lows.

    Returns:
        Boolean array of length len(low). True at bar i when the pivot at
        i - n_right is a confirmed swing low.
    """
    s = pd.Series(low, dtype=float)

    # Pivot value: low at bar (i - n_right)
    pivot = s.shift(n_right)

    # Min of n_left bars strictly BEFORE the pivot.
    left_min = s.shift(1).rolling(n_left).min().shift(n_right)

    # Min of n_right bars strictly AFTER the pivot.
    right_min = s.rolling(n_right).min()

    swing = (pivot < left_min) & (pivot < right_min)

    result = swing.to_numpy(dtype=bool, na_value=False)
    return result
