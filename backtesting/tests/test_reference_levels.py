from __future__ import annotations

import math

import pandas as pd

from orb_backtest.config import ASIA_SESSION, LDN_SESSION
from orb_backtest.signals.reference_levels import (
    compute_completed_session_levels,
    compute_previous_day_levels,
    compute_reference_levels,
)


def test_previous_day_levels_publish_on_first_bar_of_new_day() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-02 09:30",
            "2025-01-02 09:35",
            "2025-01-03 09:30",
            "2025-01-03 09:35",
        ],
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "high": [101.0, 105.0, 103.0, 104.0],
            "low": [99.0, 98.0, 100.0, 101.0],
        },
        index=idx,
    )

    prev_day_high, prev_day_low = compute_previous_day_levels(df)

    assert math.isnan(prev_day_high[0])
    assert math.isnan(prev_day_low[0])
    assert prev_day_high[2] == 105.0
    assert prev_day_low[2] == 98.0
    assert prev_day_high[3] == 105.0
    assert prev_day_low[3] == 98.0


def test_asia_levels_publish_only_after_session_close() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-02 19:55",
            "2025-01-02 20:00",
            "2025-01-02 20:05",
            "2025-01-03 06:55",
            "2025-01-03 07:00",
            "2025-01-03 12:00",
            "2025-01-03 20:00",
            "2025-01-03 20:05",
        ],
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "high": [99.0, 101.0, 104.0, 103.0, 100.0, 100.0, 102.0, 101.0],
            "low": [98.0, 97.0, 99.0, 96.0, 99.0, 99.0, 100.0, 98.0],
        },
        index=idx,
    )

    asia_high, asia_low = compute_completed_session_levels(df, ASIA_SESSION)

    assert math.isnan(asia_high[1])
    assert math.isnan(asia_low[1])
    assert asia_high[4] == 104.0
    assert asia_low[4] == 96.0
    assert asia_high[5] == 104.0
    assert asia_low[5] == 96.0
    assert asia_high[6] == 104.0
    assert asia_low[6] == 96.0


def test_london_levels_publish_after_ldn_close() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-03 02:55",
            "2025-01-03 03:00",
            "2025-01-03 08:20",
            "2025-01-03 08:25",
            "2025-01-03 09:30",
        ],
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "high": [100.0, 101.0, 103.0, 99.0, 104.0],
            "low": [99.0, 98.0, 97.0, 98.0, 100.0],
        },
        index=idx,
    )

    london_high, london_low = compute_completed_session_levels(df, LDN_SESSION)

    assert math.isnan(london_high[1])
    assert math.isnan(london_low[1])
    assert london_high[3] == 103.0
    assert london_low[3] == 97.0
    assert london_high[4] == 103.0
    assert london_low[4] == 97.0


def test_reference_levels_wrapper_exposes_expected_keys() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-02 20:00",
            "2025-01-03 07:00",
            "2025-01-03 08:25",
            "2025-01-03 09:30",
        ],
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 98.0, 97.0, 96.0],
        },
        index=idx,
    )

    levels = compute_reference_levels(df)

    assert set(levels) == {
        "previous_day_high",
        "previous_day_low",
        "asia_high",
        "asia_low",
        "london_high",
        "london_low",
    }
    assert len(levels["asia_high"]) == len(df)
