"""Post-trade gates for filtering trades by external signals.

Gates are applied after trade simulation to filter out trades that don't
meet additional criteria (e.g., trend alignment). This is computationally
cheaper than re-running the full simulation with signal-level filtering.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import numpy as np
import pandas as pd

from ..engine.simulator import TradeResult, EXIT_NO_FILL
from ..signals.daily_atr import compute_daily_atr, compute_daily_sma


def apply_sma_trend_gate(
    trades: list[TradeResult],
    df: pd.DataFrame,
    sma_period: int = 20,
) -> list[TradeResult]:
    """Filter trades by SMA trend alignment at signal bar.

    With-trend gate:
    - Long trades: keep only when prev_close > SMA (bullish trend)
    - Short trades: keep only when prev_close < SMA (bearish trend)

    Args:
        trades: Trade results from the simulator.
        df: The same 5m DataFrame used for backtesting (needed for SMA lookup).
        sma_period: SMA period for trend detection.

    Returns:
        Filtered list of trades passing the trend gate.
    """
    if not trades:
        return trades

    prev_close_5m, sma_5m = compute_daily_sma(df, length=sma_period)

    filtered = []
    n_bars = len(df)
    for t in trades:
        # Keep no-fill trades as-is (they don't affect metrics)
        if t.exit_type == EXIT_NO_FILL:
            filtered.append(t)
            continue

        bar_idx = t.signal_bar
        if bar_idx < 0 or bar_idx >= n_bars:
            continue

        prev_close = prev_close_5m[bar_idx]
        sma_val = sma_5m[bar_idx]

        # Skip if SMA data not available yet (insufficient history)
        if pd.isna(prev_close) or pd.isna(sma_val):
            continue

        # With-trend: long when above SMA, short when below
        if t.direction == 1 and prev_close > sma_val:
            filtered.append(t)
        elif t.direction == -1 and prev_close < sma_val:
            filtered.append(t)

    return filtered


def create_sma_gate_fn(
    df: pd.DataFrame,
    sma_period: int = 20,
) -> Callable[[list[TradeResult]], list[TradeResult]]:
    """Factory that returns an SMA trend gate function for walk-forward use.

    Pre-computes the SMA arrays once, then returns a closure that filters
    trades without recomputing. This is efficient when the gate is called
    many times on different trade lists from the same DataFrame.

    Args:
        df: The 5m DataFrame to compute SMA on.
        sma_period: SMA period for trend detection.

    Returns:
        A callable with signature (trades) -> filtered_trades.
    """
    prev_close_5m, sma_5m = compute_daily_sma(df, length=sma_period)
    n_bars = len(df)

    def gate_fn(trades: list[TradeResult]) -> list[TradeResult]:
        filtered = []
        for t in trades:
            if t.exit_type == EXIT_NO_FILL:
                filtered.append(t)
                continue

            bar_idx = t.signal_bar
            if bar_idx < 0 or bar_idx >= n_bars:
                continue

            prev_close = prev_close_5m[bar_idx]
            sma_val = sma_5m[bar_idx]

            if pd.isna(prev_close) or pd.isna(sma_val):
                continue

            if t.direction == 1 and prev_close > sma_val:
                filtered.append(t)
            elif t.direction == -1 and prev_close < sma_val:
                filtered.append(t)

        return filtered

    return gate_fn


def apply_atr_volatility_gate(
    trades: list[TradeResult],
    df: pd.DataFrame,
    atr_length: int = 14,
    atr_sma_length: int = 20,
    threshold: float = 1.25,
) -> list[TradeResult]:
    """Filter trades when daily ATR is elevated relative to its own SMA.

    Skips trades on days where daily_atr > atr_sma * threshold.
    High-ATR environments produce wider stops and larger losses.

    Both the ATR and its SMA use the PREVIOUS day's data (no lookahead):
    compute_daily_atr already shifts by 1 day, so resampling it to daily
    gives a series where index D has the ATR of bars ending on D-1.

    Args:
        trades: Trade results from the simulator.
        df: The 5m DataFrame used for backtesting.
        atr_length: Wilder ATR period (default 14).
        atr_sma_length: SMA period applied to the daily ATR (default 20).
        threshold: Skip when ATR > ATR_SMA * threshold (default 1.25).

    Returns:
        Filtered list of trades with elevated-volatility days removed.
    """
    if not trades:
        return trades

    # daily ATR already uses prev-day value (no lookahead)
    atr_5m = compute_daily_atr(df, length=atr_length)

    # Resample back to one value per day for rolling SMA computation
    atr_series = pd.Series(atr_5m, index=df.index)
    daily_atr = atr_series.resample("1D").first().dropna()

    # Rolling SMA of daily ATR — no extra shift needed since atr already lags 1 day
    atr_sma = daily_atr.rolling(atr_sma_length).mean()

    # Map both back to 5m bars by date
    daily_dates_arr = daily_atr.index.normalize().values
    bar_dates_arr = df.index.normalize().values
    n_daily = len(daily_dates_arr)

    indices = np.searchsorted(daily_dates_arr, bar_dates_arr, side="right") - 1
    atr_5m_mapped = np.full(len(df), np.nan)
    atr_sma_5m_mapped = np.full(len(df), np.nan)
    valid = (indices >= 0) & (indices < n_daily)
    matching = valid & (daily_dates_arr[np.clip(indices, 0, n_daily - 1)] == bar_dates_arr)
    atr_5m_mapped[matching] = daily_atr.values[indices[matching]]
    atr_sma_5m_mapped[matching] = atr_sma.values[indices[matching]]

    filtered = []
    n_bars = len(df)
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            filtered.append(t)
            continue

        bar_idx = t.signal_bar
        if bar_idx < 0 or bar_idx >= n_bars:
            continue

        atr_val = atr_5m_mapped[bar_idx]
        sma_val = atr_sma_5m_mapped[bar_idx]

        # Keep when gate unavailable (insufficient history)
        if np.isnan(atr_val) or np.isnan(sma_val) or sma_val == 0:
            filtered.append(t)
            continue

        # Only trade when volatility is normal
        if atr_val <= sma_val * threshold:
            filtered.append(t)

    return filtered


# Day-of-week constants
MON, TUE, WED, THU, FRI = 0, 1, 2, 3, 4
DOW_NAMES = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}


def apply_dow_filter(
    trades: list[TradeResult],
    excluded_days: set[int],
) -> list[TradeResult]:
    """Filter trades by day of week.

    Args:
        trades: Trade results from the simulator.
        excluded_days: Set of weekday integers to skip (0=Mon ... 4=Fri).

    Returns:
        Filtered list with trades on excluded days removed.
    """
    if not trades or not excluded_days:
        return trades

    filtered = []
    for t in trades:
        if t.exit_type == EXIT_NO_FILL:
            filtered.append(t)
            continue
        dow = datetime.strptime(t.date, "%Y-%m-%d").weekday()
        if dow not in excluded_days:
            filtered.append(t)

    return filtered


def apply_monthly_loss_cap(
    trades: list[TradeResult],
    cap_r: float,
) -> list[TradeResult]:
    """Stop trading for the rest of a month once cumulative loss hits cap_r.

    Processes trades in date order. When the running monthly R drops below
    -cap_r, all remaining trades that month are skipped (converted to no-fill).

    Args:
        trades: Trade results from the simulator (need not be sorted).
        cap_r: Maximum loss per month in R (positive value, e.g. 5.0 = stop at -5R).

    Returns:
        Filtered list with trades skipped after monthly cap is breached.
    """
    if not trades or cap_r <= 0:
        return trades

    # Sort by date to process in order
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    no_fills = [t for t in trades if t.exit_type == EXIT_NO_FILL]

    filled_sorted = sorted(filled, key=lambda t: t.date)

    monthly_r: dict[str, float] = {}   # YYYY-MM -> cumulative R
    monthly_halted: set[str] = set()   # months where cap was breached

    kept = []
    for t in filled_sorted:
        month = t.date[:7]  # YYYY-MM

        if month in monthly_halted:
            # Month already halted — skip this trade
            continue

        # Take the trade and update running monthly R
        kept.append(t)
        monthly_r[month] = monthly_r.get(month, 0.0) + t.r_multiple

        if monthly_r[month] <= -cap_r:
            monthly_halted.add(month)

    return no_fills + kept


def create_sma_gate_factory(
    sma_period: int = 20,
) -> Callable[[pd.DataFrame], Callable[[list[TradeResult]], list[TradeResult]]]:
    """Factory that returns a gate builder for walk-forward use.

    Unlike create_sma_gate_fn which pre-computes on a fixed DataFrame,
    this returns a factory that creates a fresh gate for each DataFrame slice.
    This is necessary for walk-forward optimization where each fold uses a
    different slice of the data (and signal_bar indices are relative to that slice).

    Args:
        sma_period: SMA period for trend detection.

    Returns:
        A callable with signature (df: DataFrame) -> gate_fn.
    """
    def factory(df: pd.DataFrame) -> Callable[[list[TradeResult]], list[TradeResult]]:
        return create_sma_gate_fn(df, sma_period=sma_period)
    return factory
