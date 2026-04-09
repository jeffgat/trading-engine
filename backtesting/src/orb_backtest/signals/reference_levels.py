"""Reusable previous-day and completed-session reference levels.

This module provides lookahead-safe, bar-aligned levels that are commonly
used as intraday context:

- previous day high / low
- latest completed Asia session high / low
- latest completed London session high / low

Session levels are published only after that session has completed, then
forward-filled until a newer completed session replaces them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ASIA_SESSION, LDN_SESSION, SessionConfig
from .session import compute_session_days, compute_session_masks, compute_trading_days


def compute_previous_day_levels(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Compute previous calendar day high/low aligned to each bar.

    The current day's developing range is never exposed. Bars on the first
    detected day return NaN because there is no prior completed day yet.
    """
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    new_day = compute_trading_days(df.index)

    prev_day_high = np.full(len(df), np.nan, dtype=np.float64)
    prev_day_low = np.full(len(df), np.nan, dtype=np.float64)

    current_high = np.nan
    current_low = np.nan
    last_completed_high = np.nan
    last_completed_low = np.nan

    for i in range(len(df)):
        if i > 0 and new_day[i]:
            last_completed_high = current_high
            last_completed_low = current_low
            current_high = np.nan
            current_low = np.nan

        prev_day_high[i] = last_completed_high
        prev_day_low[i] = last_completed_low

        if np.isnan(current_high):
            current_high = high[i]
            current_low = low[i]
        else:
            if high[i] > current_high:
                current_high = high[i]
            if low[i] < current_low:
                current_low = low[i]

    return prev_day_high, prev_day_low


def compute_completed_session_levels(
    df: pd.DataFrame,
    session: SessionConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the most recently completed session high/low aligned to each bar.

    During an active session, this returns the *prior* completed session's
    levels. Once the session closes, the freshly completed levels become
    available on the next bar and remain in force until a newer session closes.
    """
    timestamps = df.index
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)

    masks = compute_session_masks(timestamps, session)
    in_rth = masks["in_rth"]
    new_session_day, _ = compute_session_days(timestamps, session)

    session_high = np.full(len(df), np.nan, dtype=np.float64)
    session_low = np.full(len(df), np.nan, dtype=np.float64)

    current_high = np.nan
    current_low = np.nan
    last_completed_high = np.nan
    last_completed_low = np.nan

    for i in range(len(df)):
        if i > 0 and in_rth[i - 1] and not in_rth[i]:
            last_completed_high = current_high
            last_completed_low = current_low

        if i > 0 and new_session_day[i]:
            current_high = np.nan
            current_low = np.nan

        session_high[i] = last_completed_high
        session_low[i] = last_completed_low

        if in_rth[i]:
            if np.isnan(current_high):
                current_high = high[i]
                current_low = low[i]
            else:
                if high[i] > current_high:
                    current_high = high[i]
                if low[i] < current_low:
                    current_low = low[i]

    return session_high, session_low


def compute_reference_levels(
    df: pd.DataFrame,
    *,
    asia_session: SessionConfig = ASIA_SESSION,
    london_session: SessionConfig = LDN_SESSION,
) -> dict[str, np.ndarray]:
    """Compute commonly used day/session reference levels.

    Returns a dict with bar-aligned arrays:
    ``previous_day_high``, ``previous_day_low``,
    ``asia_high``, ``asia_low``,
    ``london_high``, ``london_low``.
    """
    previous_day_high, previous_day_low = compute_previous_day_levels(df)
    asia_high, asia_low = compute_completed_session_levels(df, asia_session)
    london_high, london_low = compute_completed_session_levels(df, london_session)

    return {
        "previous_day_high": previous_day_high,
        "previous_day_low": previous_day_low,
        "asia_high": asia_high,
        "asia_low": asia_low,
        "london_high": london_high,
        "london_low": london_low,
    }
