"""Session time window masks (fully vectorized).

Replicates Pine Script's `not na(time(timeframe.period, session, tz))` logic.
All times are in America/New_York timezone.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SessionConfig


def _parse_time(t: str) -> tuple[int, int]:
    """Parse 'HH:MM' to (hour, minute)."""
    parts = t.split(":")
    return int(parts[0]), int(parts[1])


def _time_in_range(
    hour: np.ndarray,
    minute: np.ndarray,
    start: str,
    end: str,
) -> np.ndarray:
    """Check if each bar's time falls within [start, end).

    Handles cross-midnight ranges (e.g., '18:00' to '07:00').
    Uses bar open time — a bar at 09:30 represents the 09:30-09:35 candle.
    """
    sh, sm = _parse_time(start)
    eh, em = _parse_time(end)

    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    bar_minutes = hour * 60 + minute

    if start_minutes <= end_minutes:
        # Normal range (e.g., 09:30-13:00)
        return (bar_minutes >= start_minutes) & (bar_minutes < end_minutes)
    else:
        # Cross-midnight range (e.g., 18:00-07:00)
        return (bar_minutes >= start_minutes) | (bar_minutes < end_minutes)


def compute_session_masks(
    timestamps: pd.DatetimeIndex,
    session: SessionConfig,
) -> dict[str, np.ndarray]:
    """Compute boolean masks for a session's time windows.

    Args:
        timestamps: DatetimeIndex in America/New_York timezone.
        session: Session configuration with time windows.

    Returns:
        Dict with keys:
            'in_orb': True during ORB building window
            'in_entry': True during entry window
            'in_flat': True during flat/EOD window
            'in_rth': True during regular trading hours
            'after_cutoff': True after entry window closes but still in RTH
    """
    hour = timestamps.hour.values
    minute = timestamps.minute.values

    # RTH start: use rth_start when set (LSI), otherwise orb_start (ORB strategies)
    rth_start = session.rth_start or session.orb_start

    # ORB mask — only meaningful when orb_start and orb_end are both set
    if session.orb_start and session.orb_end:
        in_orb = _time_in_range(hour, minute, session.orb_start, session.orb_end)
    else:
        in_orb = np.zeros(len(hour), dtype=bool)

    in_entry = _time_in_range(hour, minute, session.entry_start, session.entry_end)
    in_flat = _time_in_range(hour, minute, session.flat_start, session.flat_end)

    # RTH spans from rth_start (or orb_start) to flat end
    in_rth = _time_in_range(hour, minute, rth_start, session.flat_end)

    after_cutoff = in_rth & ~in_entry & ~in_orb

    return {
        "in_orb": in_orb,
        "in_entry": in_entry,
        "in_flat": in_flat,
        "in_rth": in_rth,
        "after_cutoff": after_cutoff,
    }


def compute_trading_days(timestamps: pd.DatetimeIndex) -> np.ndarray:
    """Detect new trading day boundaries.

    Returns boolean array where True = first bar of a new calendar day.
    Matches Pine Script's `ta.change(time("D")) != 0`.
    """
    dates = timestamps.date
    new_day = np.empty(len(dates), dtype=bool)
    new_day[0] = True
    new_day[1:] = dates[1:] != dates[:-1]
    return new_day


def compute_date_strings(timestamps: pd.DatetimeIndex) -> np.ndarray:
    """Convert timestamps to YYYYMMDD strings for half-day/excluded date matching."""
    return timestamps.strftime("%Y%m%d").values


def compute_session_days(
    timestamps: pd.DatetimeIndex,
    session: SessionConfig,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute session-aware day boundaries.

    For sessions that cross midnight (e.g. Asia RTH 18:00-07:00), the "session day"
    starts at the RTH open, not at calendar midnight. This prevents the ORB state
    from being reset mid-session.

    For sessions within a single calendar day (e.g. NY 09:30-16:00), this is
    equivalent to compute_trading_days().

    Args:
        timestamps: DatetimeIndex in America/New_York timezone.
        session: Session configuration with time windows.

    Returns:
        new_session_day: Boolean array where True = first bar of a new session day.
            For cross-midnight sessions, fires at RTH start (e.g. 18:00).
            For same-day sessions, fires at calendar midnight.
        session_day_id: Integer array assigning each bar to a session day index.
            Bars within the same session day share the same index.
    """
    rth_start = session.rth_start or session.orb_start
    rth_sh, rth_sm = _parse_time(rth_start)
    flat_eh, flat_em = _parse_time(session.flat_end)

    orb_start_minutes = rth_sh * 60 + rth_sm
    flat_end_minutes = flat_eh * 60 + flat_em

    # Detect if this is a cross-midnight session
    crosses_midnight = orb_start_minutes > flat_end_minutes

    if not crosses_midnight:
        # Same-day session (e.g. NY): calendar day boundaries are fine
        new_day = compute_trading_days(timestamps)
        day_id = np.cumsum(new_day) - 1
        return new_day, day_id

    # Cross-midnight session: new session day starts at RTH start time
    # We shift timestamps back so that the session start aligns with the
    # beginning of a calendar day, then use date changes.
    # E.g., Asia RTH at 18:00 → shift back 1080 min so 18:00 becomes 00:00,
    # and 07:00 next day becomes -660 → wraps to same calendar day.

    hour = timestamps.hour.values
    minute = timestamps.minute.values
    bar_minutes = hour * 60 + minute

    # Shift bars so that rth_start maps to minute 0
    shifted = bar_minutes - orb_start_minutes
    # Bars before rth_start (negative shift) belong to the previous session day
    # We can detect session day changes by looking at the shifted date
    shifted_ts = timestamps - pd.Timedelta(minutes=orb_start_minutes)
    shifted_dates = shifted_ts.date

    new_session_day = np.empty(len(timestamps), dtype=bool)
    new_session_day[0] = True
    new_session_day[1:] = shifted_dates[1:] != shifted_dates[:-1]

    day_id = np.cumsum(new_session_day) - 1

    return new_session_day, day_id
