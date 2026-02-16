"""Post-trade gates for filtering trades by external signals.

Gates are applied after trade simulation to filter out trades that don't
meet additional criteria (e.g., trend alignment). This is computationally
cheaper than re-running the full simulation with signal-level filtering.
"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from ..engine.simulator import TradeResult, EXIT_NO_FILL
from ..signals.daily_atr import compute_daily_sma


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
