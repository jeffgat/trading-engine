"""VWAP Reversion signals — fully vectorized.

Computes session-resetting VWAP and standard deviation bands, then detects
deviation (price extended away from VWAP) and rejection candle patterns for
mean-reversion entries.

VWAP = cumsum(typical_price * volume) / cumsum(volume), reset each session day.
Standard deviation bands = VWAP +/- N * sqrt(cumsum((tp - vwap)^2 * vol) / cumsum(vol)).

Zero-volume bars (forward-filled gaps) are excluded from the running sums and
carry forward the last computed VWAP / band values.
"""

from __future__ import annotations

import numpy as np


def compute_session_vwap(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    session_day_id: np.ndarray,
) -> np.ndarray:
    """Compute VWAP that resets at the start of each session day.

    Typical price = (H + L + C) / 3.  Zero-volume bars are excluded from
    the cumulative sums and inherit the previous bar's VWAP value.

    Args:
        high: High prices array.
        low: Low prices array.
        close: Close prices array.
        volume: Volume array (zero for forward-filled gaps).
        session_day_id: Integer array from ``compute_session_days()`` assigning
            each bar to a session day index.

    Returns:
        vwap: float64 array.  NaN before the first traded bar of each
            session day.
    """
    n = len(high)
    tp = (high + low + close) / 3.0

    vwap = np.full(n, np.nan, dtype=np.float64)

    cum_tp_vol = 0.0
    cum_vol = 0.0
    current_day = -1
    last_vwap = np.nan

    for i in range(n):
        day = session_day_id[i]

        # Reset accumulators on new session day
        if day != current_day:
            current_day = day
            cum_tp_vol = 0.0
            cum_vol = 0.0
            last_vwap = np.nan

        vol_i = volume[i]
        if vol_i > 0:
            cum_tp_vol += tp[i] * vol_i
            cum_vol += vol_i
            last_vwap = cum_tp_vol / cum_vol

        vwap[i] = last_vwap

    return vwap


def compute_vwap_std_bands(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    session_day_id: np.ndarray,
    num_std: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute VWAP standard deviation bands that reset each session day.

    Standard deviation = sqrt(cumsum((tp - vwap)^2 * vol) / cumsum(vol)),
    where the cumsums reset per session day and zero-volume bars are excluded.

    Args:
        high: High prices array.
        low: Low prices array.
        close: Close prices array.
        volume: Volume array (zero for forward-filled gaps).
        session_day_id: Integer array from ``compute_session_days()``.
        num_std: Number of standard deviations for the bands.

    Returns:
        (upper_band, lower_band): float64 arrays.  NaN before the first
            traded bar of each session day.
    """
    n = len(high)
    tp = (high + low + close) / 3.0

    upper_band = np.full(n, np.nan, dtype=np.float64)
    lower_band = np.full(n, np.nan, dtype=np.float64)

    cum_tp_vol = 0.0
    cum_vol = 0.0
    cum_var_vol = 0.0
    current_day = -1
    last_vwap = np.nan
    last_std = 0.0

    for i in range(n):
        day = session_day_id[i]

        # Reset accumulators on new session day
        if day != current_day:
            current_day = day
            cum_tp_vol = 0.0
            cum_vol = 0.0
            cum_var_vol = 0.0
            last_vwap = np.nan
            last_std = 0.0

        vol_i = volume[i]
        if vol_i > 0:
            cum_tp_vol += tp[i] * vol_i
            cum_vol += vol_i
            last_vwap = cum_tp_vol / cum_vol

            # Accumulate squared deviation weighted by volume
            deviation = tp[i] - last_vwap
            cum_var_vol += deviation * deviation * vol_i
            last_std = np.sqrt(cum_var_vol / cum_vol)

        if np.isnan(last_vwap):
            upper_band[i] = np.nan
            lower_band[i] = np.nan
        else:
            upper_band[i] = last_vwap + num_std * last_std
            lower_band[i] = last_vwap - num_std * last_std

    return upper_band, lower_band


def detect_deviation(
    close: np.ndarray,
    vwap: np.ndarray,
    daily_atr: np.ndarray,
    deviation_atr_pct: float,
    deviation_mode: str,
    upper_band: np.ndarray | None = None,
    lower_band: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Detect bars where price is extended away from VWAP.

    Two modes:
        ``"atr"``: Extended when ``|close - vwap| >= deviation_atr_pct/100 * daily_atr``.
        ``"std"``: Extended when close is beyond the upper/lower std-dev bands.

    Args:
        close: Close prices array.
        vwap: Session VWAP array from ``compute_session_vwap()``.
        daily_atr: Daily ATR mapped to each bar.
        deviation_atr_pct: Minimum distance from VWAP as a percentage of ATR
            (used when ``deviation_mode="atr"``).
        deviation_mode: ``"atr"`` or ``"std"``.
        upper_band: Upper std-dev band (required when ``deviation_mode="std"``).
        lower_band: Lower std-dev band (required when ``deviation_mode="std"``).

    Returns:
        (extended_above, extended_below): bool arrays.
            ``extended_above`` is True where price is significantly above VWAP.
            ``extended_below`` is True where price is significantly below VWAP.
    """
    if deviation_mode == "atr":
        threshold = (deviation_atr_pct / 100.0) * np.where(
            np.isnan(daily_atr), np.inf, daily_atr
        )
        diff = close - vwap
        extended_above = diff >= threshold
        extended_below = (-diff) >= threshold
    elif deviation_mode == "std":
        if upper_band is None or lower_band is None:
            raise ValueError(
                "upper_band and lower_band are required when deviation_mode='std'"
            )
        extended_above = close > upper_band
        extended_below = close < lower_band
    else:
        raise ValueError(f"Unknown deviation_mode: {deviation_mode!r}")

    # Suppress where VWAP is not yet valid
    vwap_nan = np.isnan(vwap)
    extended_above = extended_above & ~vwap_nan
    extended_below = extended_below & ~vwap_nan

    return extended_above, extended_below


def detect_rejection_candles(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    vwap: np.ndarray,
    rejection_mode: str,
    min_wick_atr_pct: float = 0.0,
    max_body_atr_pct: float = 0.0,
    daily_atr: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Detect rejection candles relative to VWAP.

    Two modes:

    ``"close"`` (simple directional close):
        - Bearish rejection (price above VWAP): close < open.
        - Bullish rejection (price below VWAP): close > open.

    ``"pinbar"`` (wick/body ratio filter):
        - Upper wick = high - max(open, close).
        - Lower wick = min(open, close) - low.
        - Body = abs(close - open).
        - Bearish pinbar (above VWAP): upper_wick >= threshold AND body <= threshold.
        - Bullish pinbar (below VWAP): lower_wick >= threshold AND body <= threshold.

    Args:
        open_: Open prices array.
        high: High prices array.
        low: Low prices array.
        close: Close prices array.
        vwap: Session VWAP array from ``compute_session_vwap()``.
        rejection_mode: ``"close"`` or ``"pinbar"``.
        min_wick_atr_pct: Minimum wick length as % of daily ATR (pinbar mode).
        max_body_atr_pct: Maximum body length as % of daily ATR (pinbar mode).
        daily_atr: Daily ATR mapped to each bar (required for pinbar mode).

    Returns:
        Dict with keys:
            ``bearish_rejection``: bool array — rejection candle when price is
                above VWAP (candidate for short/mean-reversion down).
            ``bullish_rejection``: bool array — rejection candle when price is
                below VWAP (candidate for long/mean-reversion up).
            ``long_stop``: float64 array — low of the candle (stop for longs).
            ``short_stop``: float64 array — high of the candle (stop for shorts).
    """
    n = len(high)
    above_vwap = close > vwap
    below_vwap = close < vwap

    if rejection_mode == "close":
        bearish_candle = close < open_  # closed lower
        bullish_candle = close > open_  # closed higher

        bearish_rejection = above_vwap & bearish_candle
        bullish_rejection = below_vwap & bullish_candle

    elif rejection_mode == "pinbar":
        if daily_atr is None:
            raise ValueError("daily_atr is required when rejection_mode='pinbar'")

        atr_safe = np.where(np.isnan(daily_atr), np.inf, daily_atr)
        min_wick = (min_wick_atr_pct / 100.0) * atr_safe
        max_body = (max_body_atr_pct / 100.0) * atr_safe

        upper_wick = high - np.maximum(open_, close)
        lower_wick = np.minimum(open_, close) - low
        body = np.abs(close - open_)

        bearish_pinbar = (upper_wick >= min_wick) & (body <= max_body)
        bullish_pinbar = (lower_wick >= min_wick) & (body <= max_body)

        bearish_rejection = above_vwap & bearish_pinbar
        bullish_rejection = below_vwap & bullish_pinbar

    else:
        raise ValueError(f"Unknown rejection_mode: {rejection_mode!r}")

    # Suppress where VWAP is not yet valid
    vwap_nan = np.isnan(vwap)
    bearish_rejection = bearish_rejection & ~vwap_nan
    bullish_rejection = bullish_rejection & ~vwap_nan

    return {
        "bearish_rejection": bearish_rejection,
        "bullish_rejection": bullish_rejection,
        "long_stop": low.copy(),
        "short_stop": high.copy(),
    }
