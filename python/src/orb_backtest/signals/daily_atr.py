"""Daily ATR computation mapped to 5-minute bars.

Replicates Pine Script's:
    dailyATR = request.security(syminfo.tickerid, "D", ta.atr(atrLength)[1],
                                lookahead=barmerge.lookahead_on)
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_daily_atr(
    df: pd.DataFrame,
    length: int = 14,
) -> np.ndarray:
    """Compute daily ATR and map to each 5-minute bar.

    Uses the PREVIOUS completed day's ATR value (no lookahead),
    matching Pine Script's `[1]` offset with `lookahead_on`.

    Args:
        df: DataFrame with columns [open, high, low, close] and DatetimeIndex.
        length: ATR period (default 14).

    Returns:
        Array of ATR values aligned to the 5m bar index.
        NaN for bars where insufficient daily history exists.
    """
    # Resample to daily OHLC
    daily = df.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()

    # True Range
    high = daily["high"].values
    low = daily["low"].values
    prev_close = np.roll(daily["close"].values, 1)
    prev_close[0] = np.nan

    tr = np.maximum(
        high - low,
        np.maximum(
            np.abs(high - prev_close),
            np.abs(low - prev_close),
        ),
    )

    # ATR as simple moving average of TR (matching Pine's ta.atr default)
    atr = np.full_like(tr, np.nan)
    # Initial ATR = mean of first `length` TRs
    if len(tr) >= length + 1:
        atr[length] = np.nanmean(tr[1 : length + 1])  # skip first NaN from prev_close
        # Subsequent: EMA-style (Wilder's smoothing)
        for i in range(length + 1, len(tr)):
            atr[i] = (atr[i - 1] * (length - 1) + tr[i]) / length

    # Shift by 1 day: use previous day's ATR (matches Pine's [1] offset)
    atr_shifted = np.roll(atr, 1)
    atr_shifted[0] = np.nan

    # Build a series indexed by date for mapping
    daily_atr_series = pd.Series(atr_shifted, index=daily.index.date)

    # Map to 5m bars by date
    bar_dates = df.index.date
    result = np.array([
        daily_atr_series.get(d, np.nan) for d in bar_dates
    ], dtype=np.float64)

    return result
