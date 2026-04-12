from __future__ import annotations

import math

import numpy as np
import pandas as pd

from orb_backtest.config import ASIA_SESSION, LDN_SESSION, NY_SESSION
from orb_backtest.signals.reference_levels import (
    compute_completed_session_levels,
    compute_data_sweep_levels,
    compute_previous_day_levels,
    compute_previous_week_levels,
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


def test_new_york_levels_publish_after_session_close() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-03 09:30",
            "2025-01-03 12:00",
            "2025-01-03 15:55",
            "2025-01-03 20:00",
            "2025-01-06 09:30",
        ],
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "high": [101.0, 105.0, 103.0, 100.0, 104.0],
            "low": [99.0, 98.0, 100.0, 99.0, 101.0],
        },
        index=idx,
    )

    new_york_high, new_york_low = compute_completed_session_levels(df, NY_SESSION)

    assert math.isnan(new_york_high[1])
    assert math.isnan(new_york_low[1])
    assert new_york_high[3] == 105.0
    assert new_york_low[3] == 98.0
    assert new_york_high[4] == 105.0
    assert new_york_low[4] == 98.0


def test_previous_week_levels_publish_on_first_bar_of_new_week() -> None:
    idx = pd.DatetimeIndex(
        [
            "2025-01-03 09:30",
            "2025-01-03 15:55",
            "2025-01-06 09:30",
            "2025-01-06 09:35",
        ],
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "high": [101.0, 106.0, 103.0, 104.0],
            "low": [99.0, 98.0, 100.0, 101.0],
        },
        index=idx,
    )

    prev_week_high, prev_week_low = compute_previous_week_levels(df)

    assert math.isnan(prev_week_high[0])
    assert math.isnan(prev_week_low[0])
    assert prev_week_high[2] == 106.0
    assert prev_week_low[2] == 98.0
    assert prev_week_high[3] == 106.0
    assert prev_week_low[3] == 98.0


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
        "previous_week_high",
        "previous_week_low",
        "asia_high",
        "asia_low",
        "london_high",
        "london_low",
        "new_york_high",
        "new_york_low",
    }
    assert len(levels["asia_high"]) == len(df)


def test_data_sweep_levels_publish_on_first_eligible_base_bar_and_reset_next_day() -> None:
    base_idx = pd.DatetimeIndex(
        [
            "2025-01-22 09:30",
            "2025-01-22 09:32",
            "2025-01-22 09:34",
            "2025-01-23 09:30",
            "2025-01-23 09:32",
        ],
        tz="America/New_York",
    )
    base = pd.DataFrame(
        {
            "high": [101.0, 102.0, 103.0, 100.0, 101.0],
            "low": [99.0, 98.0, 97.0, 99.0, 98.0],
        },
        index=base_idx,
    )

    raw_idx = pd.date_range("2025-01-01 09:30", "2025-01-23 09:34", freq="1min", tz="America/New_York")
    raw = pd.DataFrame(
        {
            "open": np.full(len(raw_idx), 100.0, dtype=float),
            "high": np.full(len(raw_idx), 101.0, dtype=float),
            "low": np.full(len(raw_idx), 100.0, dtype=float),
            "close": np.full(len(raw_idx), 100.5, dtype=float),
            "volume": np.ones(len(raw_idx), dtype=float),
        },
        index=raw_idx,
    )
    raw.loc["2025-01-22 09:31", ["high", "low"]] = [120.0, 80.0]

    levels, instance_ids = compute_data_sweep_levels(
        base,
        raw,
        atr_length=14,
        min_daily_atr_pct=200.0,
    )

    assert math.isnan(levels["data_high"][0])
    assert levels["data_high"][1] == 120.0
    assert levels["data_low"][1] == 80.0
    assert levels["data_high"][2] == 120.0
    assert levels["data_low"][2] == 80.0
    assert math.isnan(levels["data_high"][3])
    assert math.isnan(levels["data_low"][3])
    assert instance_ids[1] == 0
    assert instance_ids[2] == 0
    assert instance_ids[3] == -1


def test_data_sweep_levels_keep_latest_same_day_qualifying_candle() -> None:
    base_idx = pd.DatetimeIndex(
        [
            "2025-01-22 09:30",
            "2025-01-22 09:32",
            "2025-01-22 09:34",
            "2025-01-22 09:36",
        ],
        tz="America/New_York",
    )
    base = pd.DataFrame(
        {
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 98.0, 97.0, 96.0],
        },
        index=base_idx,
    )

    raw_idx = pd.date_range("2025-01-01 09:30", "2025-01-22 09:36", freq="1min", tz="America/New_York")
    raw = pd.DataFrame(
        {
            "open": np.full(len(raw_idx), 100.0, dtype=float),
            "high": np.full(len(raw_idx), 101.0, dtype=float),
            "low": np.full(len(raw_idx), 100.0, dtype=float),
            "close": np.full(len(raw_idx), 100.5, dtype=float),
            "volume": np.ones(len(raw_idx), dtype=float),
        },
        index=raw_idx,
    )
    raw.loc["2025-01-22 09:31", ["high", "low"]] = [120.0, 80.0]
    raw.loc["2025-01-22 09:34", ["high", "low"]] = [118.0, 82.0]

    levels, instance_ids = compute_data_sweep_levels(
        base,
        raw,
        atr_length=14,
        min_daily_atr_pct=200.0,
    )

    assert levels["data_high"][1] == 120.0
    assert levels["data_low"][1] == 80.0
    assert levels["data_high"][3] == 118.0
    assert levels["data_low"][3] == 82.0
    assert instance_ids[1] == 0
    assert instance_ids[3] == 1
