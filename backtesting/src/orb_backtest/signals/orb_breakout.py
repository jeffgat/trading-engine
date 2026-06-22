"""Plain opening-range breakout detection.

This module intentionally contains only signal logic. It does not size, fill,
or exit trades; the simulator consumes the returned masks and applies the
canonical execution/cost ledger.
"""

from __future__ import annotations

import numba as nb
import numpy as np


@nb.njit(cache=True)
def _detect_orb_breakouts_numba(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    orb_ready: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    session_day_id: np.ndarray,
    buffer_ticks: int,
    min_tick: float,
    buffer_atr_pct: float,
    close_confirm: bool,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    n = len(high)
    long_breakout = np.zeros(n, dtype=nb.boolean)
    short_breakout = np.zeros(n, dtype=nb.boolean)
    long_entry_price = np.full(n, np.nan)
    short_entry_price = np.full(n, np.nan)

    current_day = -1
    long_seen = False
    short_seen = False

    for i in range(n):
        day = int(session_day_id[i])
        if day != current_day:
            current_day = day
            long_seen = False
            short_seen = False

        if not in_entry[i] or not in_rth[i] or not orb_ready[i]:
            continue
        if np.isnan(orb_high[i]) or np.isnan(orb_low[i]):
            continue

        buffer_points = float(buffer_ticks) * min_tick
        if buffer_atr_pct > 0.0:
            if np.isnan(daily_atr[i]) or daily_atr[i] <= 0.0:
                continue
            buffer_points += (buffer_atr_pct / 100.0) * daily_atr[i]

        long_level = orb_high[i] + buffer_points
        short_level = orb_low[i] - buffer_points

        if not long_seen:
            touched = close[i] >= long_level if close_confirm else high[i] >= long_level
            if touched:
                long_breakout[i] = True
                long_entry_price[i] = long_level
                long_seen = True

        if not short_seen:
            touched = close[i] <= short_level if close_confirm else low[i] <= short_level
            if touched:
                short_breakout[i] = True
                short_entry_price[i] = short_level
                short_seen = True

    return long_breakout, short_breakout, long_entry_price, short_entry_price


def detect_orb_breakouts(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    orb_ready: np.ndarray,
    in_entry: np.ndarray,
    in_rth: np.ndarray,
    session_day_id: np.ndarray,
    *,
    buffer_ticks: int = 0,
    min_tick: float = 0.25,
    buffer_atr_pct: float = 0.0,
    trigger: str = "touch",
) -> dict[str, np.ndarray]:
    """Detect first long/short ORB breakouts per session day.

    ``trigger="touch"`` models stop-market breakout arming on an intrabar touch
    of the OR level plus buffer. ``trigger="close"`` requires the bar close to
    finish beyond the same level. Fills/exits remain simulator-owned.
    """
    if trigger not in {"touch", "close"}:
        raise ValueError("trigger must be 'touch' or 'close'")
    if buffer_ticks < 0:
        raise ValueError("buffer_ticks must be >= 0")
    if buffer_atr_pct < 0.0:
        raise ValueError("buffer_atr_pct must be >= 0")

    long_breakout, short_breakout, long_entry_price, short_entry_price = (
        _detect_orb_breakouts_numba(
            np.asarray(high, dtype=np.float64),
            np.asarray(low, dtype=np.float64),
            np.asarray(close, dtype=np.float64),
            np.asarray(daily_atr, dtype=np.float64),
            np.asarray(orb_high, dtype=np.float64),
            np.asarray(orb_low, dtype=np.float64),
            np.asarray(orb_ready, dtype=np.bool_),
            np.asarray(in_entry, dtype=np.bool_),
            np.asarray(in_rth, dtype=np.bool_),
            np.asarray(session_day_id, dtype=np.int64),
            int(buffer_ticks),
            float(min_tick),
            float(buffer_atr_pct),
            trigger == "close",
        )
    )
    return {
        "long_breakout": long_breakout,
        "short_breakout": short_breakout,
        "long_entry_price": long_entry_price,
        "short_entry_price": short_entry_price,
    }
