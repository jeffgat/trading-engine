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
    length = int(length)
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

    # Map to 5m bars by date using vectorized merge
    daily_dates = daily.index.normalize()
    bar_dates = df.index.normalize()

    # Use searchsorted for O(n log m) mapping instead of O(n) dict lookups
    daily_dates_arr = daily_dates.values
    bar_dates_arr = bar_dates.values
    indices = np.searchsorted(daily_dates_arr, bar_dates_arr, side="right") - 1

    result = np.full(len(df), np.nan, dtype=np.float64)
    valid = (indices >= 0) & (indices < len(atr_shifted))
    # Only map when the daily date matches exactly
    matching = valid & (daily_dates_arr[np.clip(indices, 0, len(daily_dates_arr) - 1)] == bar_dates_arr)
    result[matching] = atr_shifted[indices[matching]]

    return result


def compute_previous_daily_close(df: pd.DataFrame) -> np.ndarray:
    """Map the previous completed daily close to each intraday bar."""
    daily_close = df["close"].resample("1D").last().dropna()
    daily_dates = daily_close.index.normalize()
    close_vals = daily_close.values.astype(np.float64)

    prev_close = np.roll(close_vals, 1)
    prev_close[0] = np.nan

    daily_dates_arr = daily_dates.values
    bar_dates_arr = df.index.normalize().values
    indices = np.searchsorted(daily_dates_arr, bar_dates_arr, side="right") - 1

    result = np.full(len(df), np.nan, dtype=np.float64)
    valid = (indices >= 0) & (indices < len(daily_dates_arr))
    matching = valid & (
        daily_dates_arr[np.clip(indices, 0, len(daily_dates_arr) - 1)]
        == bar_dates_arr
    )
    result[matching] = prev_close[indices[matching]]
    return result


def compute_previous_daily_rolling_atr_pct(
    df: pd.DataFrame,
    length: int = 14,
) -> np.ndarray:
    """Map previous completed simple rolling daily true-range ATR% to bars.

    This mirrors the research gate workflow: daily true range is computed from
    daily OHLC, averaged with a simple rolling mean, converted to percent of
    that same day's close, then shifted one completed day before intraday use.
    """
    length = int(length)
    daily = (
        df.resample("1D")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        })
        .dropna(subset=["open", "high", "low", "close"])
    )
    prev_close = daily["close"].shift(1)
    true_range = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    rolling_atr = true_range.rolling(length, min_periods=length).mean()
    prior_rolling_atr_pct = (rolling_atr / daily["close"] * 100.0).shift(1)

    daily_dates_arr = daily.index.normalize().values
    bar_dates_arr = df.index.normalize().values
    indices = np.searchsorted(daily_dates_arr, bar_dates_arr, side="right") - 1

    result = np.full(len(df), np.nan, dtype=np.float64)
    valid = (indices >= 0) & (indices < len(daily_dates_arr))
    matching = valid & (
        daily_dates_arr[np.clip(indices, 0, len(daily_dates_arr) - 1)]
        == bar_dates_arr
    )
    values = prior_rolling_atr_pct.values.astype(np.float64)
    result[matching] = values[indices[matching]]
    return result


def compute_daily_sma(
    df: pd.DataFrame,
    length: int = 20,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute daily SMA and previous close, mapped to 5-minute bars.

    Uses the PREVIOUS completed day's values (no lookahead),
    matching Pine Script's ``[1]`` offset with ``lookahead_on``.

    Args:
        df: DataFrame with columns [open, high, low, close] and DatetimeIndex.
        length: SMA period (default 20).

    Returns:
        Tuple of (prev_close_5m, sma_5m) arrays aligned to the 5m bar index.
        NaN for bars where insufficient daily history exists.
    """
    # Resample to daily close
    daily_close = df["close"].resample("1D").last().dropna()
    daily_dates = daily_close.index.normalize()

    close_vals = daily_close.values

    # SMA of daily closes
    sma = np.full_like(close_vals, np.nan)
    if len(close_vals) >= length:
        # Rolling mean
        cumsum = np.cumsum(close_vals)
        sma[length - 1] = cumsum[length - 1] / length
        for i in range(length, len(close_vals)):
            sma[i] = (cumsum[i] - cumsum[i - length]) / length

    # Shift by 1 day: use previous day's values (no lookahead)
    prev_close = np.roll(close_vals, 1)
    prev_close[0] = np.nan
    sma_shifted = np.roll(sma, 1)
    sma_shifted[0] = np.nan

    # Map to 5m bars using searchsorted
    daily_dates_arr = daily_dates.values
    bar_dates_arr = df.index.normalize().values
    indices = np.searchsorted(daily_dates_arr, bar_dates_arr, side="right") - 1

    prev_close_5m = np.full(len(df), np.nan, dtype=np.float64)
    sma_5m = np.full(len(df), np.nan, dtype=np.float64)

    valid = (indices >= 0) & (indices < len(daily_dates_arr))
    matching = valid & (
        daily_dates_arr[np.clip(indices, 0, len(daily_dates_arr) - 1)]
        == bar_dates_arr
    )
    prev_close_5m[matching] = prev_close[indices[matching]]
    sma_5m[matching] = sma_shifted[indices[matching]]

    return prev_close_5m, sma_5m
