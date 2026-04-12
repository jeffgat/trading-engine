"""Reusable previous-period and completed-session reference levels.

This module provides lookahead-safe, bar-aligned levels that are commonly
used as intraday context:

- previous day high / low
- previous week high / low
- latest completed Asia session high / low
- latest completed London session high / low
- latest completed New York session high / low

Session levels are published only after that session has completed, then
forward-filled until a newer completed session replaces them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import ASIA_SESSION, LDN_SESSION, NY_SESSION, SessionConfig
from .daily_atr import compute_daily_atr
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


def compute_previous_week_levels(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Compute previous calendar week high/low aligned to each bar.

    The current week's developing range is never exposed. Bars in the first
    detected week return NaN because there is no prior completed week yet.
    """
    timestamps = df.index
    localized = timestamps.tz_convert("America/New_York") if timestamps.tz is not None else timestamps.tz_localize("America/New_York")
    week_periods = localized.tz_localize(None).to_period("W-SUN")

    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)

    new_week = np.empty(len(df), dtype=bool)
    new_week[0] = True
    new_week[1:] = week_periods[1:] != week_periods[:-1]

    prev_week_high = np.full(len(df), np.nan, dtype=np.float64)
    prev_week_low = np.full(len(df), np.nan, dtype=np.float64)

    current_high = np.nan
    current_low = np.nan
    last_completed_high = np.nan
    last_completed_low = np.nan

    for i in range(len(df)):
        if i > 0 and new_week[i]:
            last_completed_high = current_high
            last_completed_low = current_low
            current_high = np.nan
            current_low = np.nan

        prev_week_high[i] = last_completed_high
        prev_week_low[i] = last_completed_low

        if np.isnan(current_high):
            current_high = high[i]
            current_low = low[i]
        else:
            if high[i] > current_high:
                current_high = high[i]
            if low[i] < current_low:
                current_low = low[i]

    return prev_week_high, prev_week_low


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


def compute_data_sweep_levels(
    df: pd.DataFrame,
    signal_df_1m: pd.DataFrame,
    *,
    atr_length: int = 14,
    min_daily_atr_pct: float = 15.0,
) -> tuple[dict[str, np.ndarray], np.ndarray]:
    """Compute same-day data-spike highs/lows aligned to each base bar.

    A qualifying data candle is any completed 1m bar whose range is at least
    ``min_daily_atr_pct`` of the previous completed day's ATR. Its high and low
    become eligible liquidity levels as soon as that 1m bar closes. For
    coarser base frames, the earliest causal bar is the first base bar whose
    timestamp is at or after the 1m candle close.

    The latest published qualifying candle for the current day is exposed as
    ``data_high`` / ``data_low``. Levels reset when the trading day changes.
    """
    if signal_df_1m is None or signal_df_1m.empty:
        raise ValueError("signal_df_1m is required to compute data sweep levels.")

    base_index = df.index
    active_high = np.full(len(base_index), np.nan, dtype=np.float64)
    active_low = np.full(len(base_index), np.nan, dtype=np.float64)
    active_ids = np.full(len(base_index), -1, dtype=np.int64)

    if len(base_index) == 0:
        return {"data_high": active_high, "data_low": active_low}, active_ids

    raw = signal_df_1m[["open", "high", "low", "close"]].copy().sort_index()
    raw_high = raw["high"].to_numpy(dtype=np.float64)
    raw_low = raw["low"].to_numpy(dtype=np.float64)
    raw_ts = raw.index.values.astype("datetime64[ns]")
    base_ts = base_index.values.astype("datetime64[ns]")

    raw_local = raw.index.tz_convert("America/New_York") if raw.index.tz is not None else raw.index.tz_localize("America/New_York")
    base_local = base_index.tz_convert("America/New_York") if base_index.tz is not None else base_index.tz_localize("America/New_York")
    raw_days = raw_local.normalize().values.astype("datetime64[ns]")
    base_days = base_local.normalize().values.astype("datetime64[ns]")

    daily_atr = compute_daily_atr(raw, length=atr_length)
    min_range = daily_atr * (float(min_daily_atr_pct) / 100.0)
    qualifying = np.isfinite(min_range) & ((raw_high - raw_low) >= min_range)

    if not np.any(qualifying):
        return {"data_high": active_high, "data_low": active_low}, active_ids

    event_publish = raw_ts[qualifying] + np.timedelta64(1, "m")
    event_days = raw_days[qualifying]
    event_high = raw_high[qualifying]
    event_low = raw_low[qualifying]
    event_ids = np.arange(np.count_nonzero(qualifying), dtype=np.int64)

    pos = np.searchsorted(event_publish, base_ts, side="right") - 1
    valid = pos >= 0
    if np.any(valid):
        event_pos = pos[valid]
        same_day = event_days[event_pos] == base_days[valid]
        if np.any(same_day):
            valid_idx = np.flatnonzero(valid)[same_day]
            matched_pos = event_pos[same_day]
            active_high[valid_idx] = event_high[matched_pos]
            active_low[valid_idx] = event_low[matched_pos]
            active_ids[valid_idx] = event_ids[matched_pos]

    return {"data_high": active_high, "data_low": active_low}, active_ids


def compute_reference_levels(
    df: pd.DataFrame,
    *,
    asia_session: SessionConfig = ASIA_SESSION,
    london_session: SessionConfig = LDN_SESSION,
    new_york_session: SessionConfig = NY_SESSION,
) -> dict[str, np.ndarray]:
    """Compute commonly used day/session reference levels.

    Returns a dict with bar-aligned arrays:
    ``previous_day_high``, ``previous_day_low``,
    ``previous_week_high``, ``previous_week_low``,
    ``asia_high``, ``asia_low``,
    ``london_high``, ``london_low``,
    ``new_york_high``, ``new_york_low``.
    """
    previous_day_high, previous_day_low = compute_previous_day_levels(df)
    previous_week_high, previous_week_low = compute_previous_week_levels(df)
    asia_high, asia_low = compute_completed_session_levels(df, asia_session)
    london_high, london_low = compute_completed_session_levels(df, london_session)
    new_york_high, new_york_low = compute_completed_session_levels(df, new_york_session)

    return {
        "previous_day_high": previous_day_high,
        "previous_day_low": previous_day_low,
        "previous_week_high": previous_week_high,
        "previous_week_low": previous_week_low,
        "asia_high": asia_high,
        "asia_low": asia_low,
        "london_high": london_high,
        "london_low": london_low,
        "new_york_high": new_york_high,
        "new_york_low": new_york_low,
    }
