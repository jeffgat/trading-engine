from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.signals.orb_breakout import detect_orb_breakouts


def test_detect_orb_breakouts_emits_first_touch_per_side() -> None:
    high = np.array([101.0, 102.0, 104.0, 105.0, 103.0], dtype=float)
    low = np.array([99.0, 100.0, 101.0, 100.5, 98.0], dtype=float)
    close = np.array([100.0, 101.0, 102.5, 104.0, 99.0], dtype=float)
    daily_atr = np.full(5, 10.0, dtype=float)
    orb_high = np.array([np.nan, np.nan, 103.0, 103.0, 103.0], dtype=float)
    orb_low = np.array([np.nan, np.nan, 99.0, 99.0, 99.0], dtype=float)
    orb_ready = np.array([False, False, True, True, True], dtype=bool)
    in_entry = np.array([False, False, True, True, True], dtype=bool)
    in_rth = np.ones(5, dtype=bool)
    session_day_id = np.zeros(5, dtype=np.int64)

    result = detect_orb_breakouts(
        high,
        low,
        close,
        daily_atr,
        orb_high,
        orb_low,
        orb_ready,
        in_entry,
        in_rth,
        session_day_id,
        buffer_ticks=0,
        min_tick=0.25,
        trigger="touch",
    )

    assert result["long_breakout"].tolist() == [False, False, True, False, False]
    assert result["short_breakout"].tolist() == [False, False, False, False, True]
    assert result["long_entry_price"][2] == pytest.approx(103.0)
    assert result["short_entry_price"][4] == pytest.approx(99.0)


def test_detect_orb_breakouts_close_confirmation_waits_for_close() -> None:
    high = np.array([101.0, 102.0, 104.0], dtype=float)
    low = np.array([99.0, 100.0, 101.0], dtype=float)
    close = np.array([100.0, 101.0, 102.5], dtype=float)
    daily_atr = np.full(3, 10.0, dtype=float)
    orb_high = np.array([np.nan, np.nan, 103.0], dtype=float)
    orb_low = np.array([np.nan, np.nan, 99.0], dtype=float)
    ready = np.array([False, False, True], dtype=bool)
    session_day_id = np.zeros(3, dtype=np.int64)

    result = detect_orb_breakouts(
        high,
        low,
        close,
        daily_atr,
        orb_high,
        orb_low,
        ready,
        ready,
        np.ones(3, dtype=bool),
        session_day_id,
        trigger="close",
    )

    assert not result["long_breakout"].any()


def test_extract_setup_candidates_orb_breakout_builds_plain_orb_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = pd.date_range(
        "2025-01-03 09:30",
        periods=4,
        freq="5min",
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "open": [100.0, 100.5, 101.0, 102.5],
            "high": [101.0, 101.5, 103.0, 104.0],
            "low": [99.5, 100.0, 101.0, 102.0],
            "close": [100.5, 101.0, 102.5, 103.5],
            "volume": [1.0] * 4,
        },
        index=index,
    )
    n = len(df)
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:40",
        entry_start="09:40",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_orb_pct=100.0,
    )
    masks = {
        "in_orb": np.array([True, True, False, False], dtype=bool),
        "in_entry": np.array([False, False, True, True], dtype=bool),
        "in_flat": np.zeros(n, dtype=bool),
        "in_rth": np.ones(n, dtype=bool),
        "in_sweep": np.ones(n, dtype=bool),
        "after_cutoff": np.zeros(n, dtype=bool),
    }
    monkeypatch.setattr(simulator, "compute_session_masks", lambda *_args, **_kwargs: masks)
    monkeypatch.setattr(
        simulator,
        "compute_session_days",
        lambda *_args, **_kwargs: (
            np.array([True, False, False, False], dtype=bool),
            np.zeros(n, dtype=np.int64),
        ),
    )
    monkeypatch.setattr(simulator, "compute_daily_atr", lambda *_args, **_kwargs: np.full(n, 10.0))
    monkeypatch.setattr(simulator, "compute_previous_daily_close", lambda *_args, **_kwargs: np.full(n, 100.0))
    monkeypatch.setattr(
        simulator,
        "compute_previous_daily_rolling_atr_pct",
        lambda *_args, **_kwargs: np.full(n, 1.0),
    )
    monkeypatch.setattr(
        simulator,
        "compute_orb_levels",
        lambda *_args, **_kwargs: (
            np.array([np.nan, np.nan, 102.0, 102.0], dtype=float),
            np.array([np.nan, np.nan, 99.0, 99.0], dtype=float),
            np.array([False, False, True, True], dtype=bool),
        ),
    )
    monkeypatch.setattr(
        simulator,
        "compute_orb_open",
        lambda *_args, **_kwargs: np.array([np.nan, np.nan, 100.0, 100.0], dtype=float),
    )
    monkeypatch.setattr(simulator, "compute_session_vwap", lambda *_args, **_kwargs: np.full(n, 101.0))
    monkeypatch.setattr(
        simulator,
        "compute_date_strings",
        lambda timestamps: np.array(["20250103"] * len(timestamps)),
    )

    config = StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="orb_breakout",
        direction_filter="long",
        rr=2.0,
        tp1_ratio=0.5,
    )

    candidates = simulator._extract_setup_candidates(df, session, config)

    assert len(candidates) == 1
    assert candidates[0].direction == 1
    assert candidates[0].signal_bar == 1
    assert candidates[0].entry_price == pytest.approx(102.0)
    assert candidates[0].orb_range == pytest.approx(3.0)


def test_strategy_config_rejects_invalid_orb_breakout_params() -> None:
    with pytest.raises(ValueError, match="orb_breakout_trigger"):
        StrategyConfig(strategy="orb_breakout", orb_breakout_trigger="invalid")
    with pytest.raises(ValueError, match="orb_breakout_buffer_ticks"):
        StrategyConfig(strategy="orb_breakout", orb_breakout_buffer_ticks=-1)
    with pytest.raises(ValueError, match="orb_breakout_buffer_atr_pct"):
        StrategyConfig(strategy="orb_breakout", orb_breakout_buffer_atr_pct=-0.1)
