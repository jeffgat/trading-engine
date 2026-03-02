"""Liquidity sweep detection — fully vectorized, no look-ahead bias.

A **liquidity sweep** occurs when price trades *through* a prior confirmed
swing level:
  - High sweep: current bar's high reaches or exceeds a previous confirmed swing high
  - Low sweep:  current bar's low reaches or undercuts a previous confirmed swing low

**Swing pivot definition** (matches Pine Script's ``ta.pivothigh(n, n)``):
  A bar is a swing high if its ``high`` is strictly greater than all ``n``
  bars to its left AND all ``n`` bars to its right.  Symmetrically for
  swing lows using ``low``.  Pivot detection delegates to
  :mod:`orb_backtest.signals.swing` (``detect_swing_highs`` / ``detect_swing_lows``).

**Look-ahead avoidance**:
  Because a pivot at bar ``i`` can only be confirmed after ``n_bars`` more
  bars have closed, all confirmation signals are *emitted at bar i + n_bars*,
  never at bar ``i`` itself.

**Typical usage**::

    pivots = detect_swing_pivots(high, low, n_bars=10)
    swing  = track_latest_swing(**pivots)
    sweeps = detect_liquidity_sweeps(high, low, **swing)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .swing import detect_swing_highs, detect_swing_lows


# ---------------------------------------------------------------------------
# 1. Swing pivot detection
# ---------------------------------------------------------------------------

def detect_swing_pivots(
    high: np.ndarray,
    low: np.ndarray,
    n_bars: int = 10,
) -> dict[str, np.ndarray]:
    """Detect swing-high and swing-low pivot confirmations.

    Delegates to :func:`detect_swing_highs` and :func:`detect_swing_lows`
    (``n_left = n_right = n_bars``) and adds level arrays for downstream use.

    A pivot at bar ``c`` is confirmed at bar ``c + n_bars`` once ``n_bars``
    bars to its right have all closed with lower highs (or higher lows).
    This replicates ``ta.pivothigh(n_bars, n_bars)`` in Pine Script with no
    future information used at runtime.

    Args:
        high:   High prices array, length N.
        low:    Low prices array, length N.
        n_bars: Number of bars on each side that must be exceeded.
                Must be >= 1.  Default 10.

    Returns:
        Dict with keys:

        ``pivot_high``
            bool array — True at confirmation bar when a swing high is confirmed.
        ``pivot_low``
            bool array — True at confirmation bar when a swing low is confirmed.
        ``pivot_high_level``
            float array — ``high`` value of the pivot bar (NaN where no pivot).
        ``pivot_low_level``
            float array — ``low`` value of the pivot bar (NaN where no pivot).

    Raises:
        ValueError: If ``n_bars < 1``.
    """
    if n_bars < 1:
        raise ValueError(f"n_bars must be >= 1, got {n_bars}")

    pivot_high = detect_swing_highs(high, n_left=n_bars, n_right=n_bars)
    pivot_low = detect_swing_lows(low, n_left=n_bars, n_right=n_bars)

    # Level at pivot bar = value n_bars before the confirmation bar
    pivot_candidate_high = pd.Series(high, dtype=float).shift(n_bars).values
    pivot_candidate_low = pd.Series(low, dtype=float).shift(n_bars).values

    pivot_high_level = np.where(pivot_high, pivot_candidate_high, np.nan)
    pivot_low_level = np.where(pivot_low, pivot_candidate_low, np.nan)

    return {
        "pivot_high": pivot_high,
        "pivot_low": pivot_low,
        "pivot_high_level": pivot_high_level,
        "pivot_low_level": pivot_low_level,
    }


# ---------------------------------------------------------------------------
# 2. Forward-fill latest confirmed swing levels
# ---------------------------------------------------------------------------

def track_latest_swing(
    pivot_high: np.ndarray,
    pivot_low: np.ndarray,
    pivot_high_level: np.ndarray,
    pivot_low_level: np.ndarray,
) -> dict[str, np.ndarray]:
    """Forward-fill the most recently confirmed swing high and swing low.

    After a pivot is confirmed at bar ``t``, its level is carried forward into
    every subsequent bar until a newer pivot of the same type replaces it.
    Bars before the first confirmed pivot remain NaN.

    Args:
        pivot_high:       bool array — output of :func:`detect_swing_pivots`.
        pivot_low:        bool array — output of :func:`detect_swing_pivots`.
        pivot_high_level: float array — swing high levels (NaN where no pivot).
        pivot_low_level:  float array — swing low levels (NaN where no pivot).

    Returns:
        Dict with keys:

        ``latest_swing_high``
            float array — most recent confirmed swing high level (NaN if none
            yet confirmed).
        ``latest_swing_low``
            float array — most recent confirmed swing low level (NaN if none
            yet confirmed).
    """
    latest_swing_high = (
        pd.Series(np.where(pivot_high, pivot_high_level, np.nan))
        .ffill()
        .values
    )
    latest_swing_low = (
        pd.Series(np.where(pivot_low, pivot_low_level, np.nan))
        .ffill()
        .values
    )

    return {
        "latest_swing_high": latest_swing_high,
        "latest_swing_low": latest_swing_low,
    }


# ---------------------------------------------------------------------------
# 3. Liquidity sweep detection
# ---------------------------------------------------------------------------

def detect_liquidity_sweeps(
    high: np.ndarray,
    low: np.ndarray,
    latest_swing_high: np.ndarray,
    latest_swing_low: np.ndarray,
) -> dict[str, np.ndarray]:
    """Detect bars where price trades through the most recent confirmed swing.

    Comparisons are made against the *previous* bar's latest swing level (a
    1-bar shift) to avoid same-bar triggering: a bar that simultaneously
    confirms a pivot and trades through it would be a false signal.

    Args:
        high:              High prices array.
        low:               Low prices array.
        latest_swing_high: float array — output of :func:`track_latest_swing`.
        latest_swing_low:  float array — output of :func:`track_latest_swing`.

    Returns:
        Dict with keys:

        ``high_swept``
            bool array — True when current bar's high exceeds the prior bar's
            latest confirmed swing high.
        ``low_swept``
            bool array — True when current bar's low undercuts the prior bar's
            latest confirmed swing low.
        ``swept_high_level``
            float array — swing high level that was swept (NaN where not swept).
        ``swept_low_level``
            float array — swing low level that was swept (NaN where not swept).
    """
    # Shift swing levels by 1 bar so bar[t] compares against bar[t-1]'s level
    prev_swing_high = np.roll(latest_swing_high, 1).astype(float)
    prev_swing_high[0] = np.nan

    prev_swing_low = np.roll(latest_swing_low, 1).astype(float)
    prev_swing_low[0] = np.nan

    # A sweep requires a valid (non-NaN) prior swing level.
    # Use >= / <= (not strict) so tick-perfect touches are captured — consistent
    # with how the Numba simulator fills stop orders (>= for longs, <= for shorts).
    high_swept = ~np.isnan(prev_swing_high) & (high >= prev_swing_high)
    low_swept = ~np.isnan(prev_swing_low) & (low <= prev_swing_low)

    swept_high_level = np.where(high_swept, prev_swing_high, np.nan)
    swept_low_level = np.where(low_swept, prev_swing_low, np.nan)

    return {
        "high_swept": high_swept,
        "low_swept": low_swept,
        "swept_high_level": swept_high_level,
        "swept_low_level": swept_low_level,
    }
