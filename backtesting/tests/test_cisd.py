from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.signals.cisd import detect_internal_cisd


TEST_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    sweep_start="09:30",
    sweep_end="15:00",
    entry_start="09:30",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=0.0,
)


def _bars(n: int, *, day: str = "2025-01-03") -> pd.DatetimeIndex:
    return pd.date_range(f"{day} 09:30", periods=n, freq="5min", tz="America/New_York")


def _df(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    day: str = "2025-01-03",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1.0] * len(open_),
        },
        index=_bars(len(open_), day=day),
    )


def _empty_lsi_fvg(n: int) -> dict[str, np.ndarray]:
    return {
        "long_fvg": np.zeros(n, dtype=bool),
        "long_fvg_bottom": np.full(n, np.nan, dtype=float),
        "long_entry_price": np.full(n, np.nan, dtype=float),
        "long_gap_size": np.zeros(n, dtype=float),
        "short_fvg": np.zeros(n, dtype=bool),
        "short_fvg_top": np.full(n, np.nan, dtype=float),
        "short_entry_price": np.full(n, np.nan, dtype=float),
        "short_gap_size": np.zeros(n, dtype=float),
    }


def test_detect_internal_cisd_uses_body_level_not_wick() -> None:
    open_ = np.array([10.2, 10.0, 9.8, 9.5, 9.3, 9.6], dtype=float)
    close = np.array([10.0, 9.8, 9.5, 9.3, 9.6, 10.2], dtype=float)
    daily_atr = np.full(len(open_), 10.0, dtype=float)

    cisd = detect_internal_cisd(
        open_,
        close,
        daily_atr=daily_atr,
        min_leg_bars=2,
        min_leg_atr_pct=5.0,
        max_leg_bars=20,
    )

    assert cisd["bullish_cisd"].tolist() == [False, False, False, False, False, True]
    assert cisd["bullish_level"][5] == pytest.approx(10.0)
    assert cisd["bullish_level_bar"][5] == 1
    assert cisd["bullish_leg_bars"][5] >= 2
    assert cisd["bullish_leg_move"][5] == pytest.approx(0.7)


def test_detect_internal_cisd_requires_min_leg_atr_travel() -> None:
    open_ = np.array([10.2, 10.0, 9.8, 9.5, 9.3, 9.6], dtype=float)
    close = np.array([10.0, 9.8, 9.5, 9.3, 9.6, 10.2], dtype=float)
    daily_atr = np.full(len(open_), 20.0, dtype=float)

    cisd = detect_internal_cisd(
        open_,
        close,
        daily_atr=daily_atr,
        min_leg_bars=2,
        min_leg_atr_pct=5.0,
        max_leg_bars=20,
    )

    assert not cisd["bullish_cisd"].any()


def test_detect_internal_cisd_bearish_mirror() -> None:
    open_ = np.array([9.8, 10.0, 10.2, 10.5, 10.7, 10.4], dtype=float)
    close = np.array([10.0, 10.2, 10.5, 10.7, 10.4, 9.8], dtype=float)
    daily_atr = np.full(len(open_), 10.0, dtype=float)

    cisd = detect_internal_cisd(
        open_,
        close,
        daily_atr=daily_atr,
        min_leg_bars=2,
        min_leg_atr_pct=5.0,
        max_leg_bars=20,
    )

    assert cisd["bearish_cisd"].tolist() == [False, False, False, False, False, True]
    assert cisd["bearish_level"][5] == pytest.approx(10.0)
    assert cisd["bearish_level_bar"][5] == 1
    assert cisd["bearish_leg_bars"][5] >= 2
    assert cisd["bearish_leg_move"][5] == pytest.approx(0.7)


def test_lsi_cisd_replacement_arms_after_sweep_without_fvg(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        open_=[10.2, 10.0, 9.8, 9.5, 9.3, 9.6],
        high=[10.4, 10.2, 10.0, 9.7, 9.8, 10.3],
        low=[9.0, 9.7, 8.8, 9.1, 9.2, 9.5],
        close=[10.0, 9.8, 9.5, 9.3, 9.6, 10.2],
    )
    n = len(df)
    fvg = _empty_lsi_fvg(n)

    monkeypatch.setattr(
        simulator,
        "detect_swing_highs",
        lambda high, n_left, n_right: np.zeros(n, dtype=bool),
    )
    monkeypatch.setattr(
        simulator,
        "detect_swing_lows",
        lambda low, n_left, n_right: np.array([False, True, False, False, False, False], dtype=bool),
    )

    candidates = simulator._extract_lsi_candidates(
        df,
        fvg,
        valid_long=np.zeros(n, dtype=bool),
        valid_short=np.zeros(n, dtype=bool),
        session_day_id=np.zeros(n, dtype=np.int64),
        in_entry=np.ones(n, dtype=bool),
        in_rth=np.ones(n, dtype=bool),
        in_sweep=np.ones(n, dtype=bool),
        dates=df.index.date,
        close=df["close"].to_numpy(dtype=float),
        daily_atr=np.full(n, 10.0, dtype=float),
        orb_high=np.full(n, np.nan, dtype=float),
        orb_low=np.full(n, np.nan, dtype=float),
        session=TEST_SESSION,
        n_left=1,
        n_right=1,
        fvg_window_left=10,
        fvg_window_right=10,
        direction_filter="long",
        confirmation_mode="cisd",
        entry_mode="close",
        rr=2.0,
        tp1_ratio=0.5,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == 1
    assert candidate.entry_price == pytest.approx(10.2)
    assert candidate.signal_bar == 4
    assert candidate.lsi_sweep_bar == 2
    assert candidate.lsi_swept_level == pytest.approx(9.0)
    assert candidate.lsi_confirmation_type == "cisd"
    assert candidate.lsi_cisd_level == pytest.approx(10.0)


def test_lsi_cisd_level_limit_waits_for_broken_body_level(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        open_=[10.2, 10.0, 9.8, 9.5, 9.3, 9.6],
        high=[10.4, 10.2, 10.0, 9.7, 9.8, 10.3],
        low=[9.0, 9.7, 8.8, 9.1, 9.2, 9.5],
        close=[10.0, 9.8, 9.5, 9.3, 9.6, 10.2],
    )
    n = len(df)
    fvg = _empty_lsi_fvg(n)

    monkeypatch.setattr(
        simulator,
        "detect_swing_highs",
        lambda high, n_left, n_right: np.zeros(n, dtype=bool),
    )
    monkeypatch.setattr(
        simulator,
        "detect_swing_lows",
        lambda low, n_left, n_right: np.array([False, True, False, False, False, False], dtype=bool),
    )

    candidates = simulator._extract_lsi_candidates(
        df,
        fvg,
        valid_long=np.zeros(n, dtype=bool),
        valid_short=np.zeros(n, dtype=bool),
        session_day_id=np.zeros(n, dtype=np.int64),
        in_entry=np.ones(n, dtype=bool),
        in_rth=np.ones(n, dtype=bool),
        in_sweep=np.ones(n, dtype=bool),
        dates=df.index.date,
        close=df["close"].to_numpy(dtype=float),
        daily_atr=np.full(n, 10.0, dtype=float),
        orb_high=np.full(n, np.nan, dtype=float),
        orb_low=np.full(n, np.nan, dtype=float),
        session=TEST_SESSION,
        n_left=1,
        n_right=1,
        fvg_window_left=10,
        fvg_window_right=10,
        direction_filter="long",
        confirmation_mode="cisd",
        entry_mode="level_limit",
        rr=2.0,
        tp1_ratio=0.5,
    )

    assert len(candidates) == 1
    assert candidates[0].entry_price == pytest.approx(10.0)
    assert candidates[0].signal_bar == 5


def test_lsi_cisd_excluded_day_blocks_sweep_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Thursday, 2025-01-02. This catches the engine-level path where
    # excluded_days must gate CISD sweeps, not just FVG candidate arrays.
    df = _df(
        open_=[10.2, 10.0, 9.8, 9.5, 9.3, 9.6],
        high=[10.4, 10.2, 10.0, 9.7, 9.8, 10.3],
        low=[9.0, 9.7, 8.8, 9.1, 9.2, 9.5],
        close=[10.0, 9.8, 9.5, 9.3, 9.6, 10.2],
        day="2025-01-02",
    )
    n = len(df)

    monkeypatch.setattr(
        simulator,
        "compute_daily_atr",
        lambda _df, _length: np.full(n, 10.0, dtype=float),
    )
    monkeypatch.setattr(
        simulator,
        "detect_swing_highs",
        lambda high, n_left, n_right: np.zeros(n, dtype=bool),
    )
    monkeypatch.setattr(
        simulator,
        "detect_swing_lows",
        lambda low, n_left, n_right: np.array([False, True, False, False, False, False], dtype=bool),
    )

    base_config = StrategyConfig(
        strategy="lsi",
        sessions=(TEST_SESSION,),
        atr_length=1,
        rr=2.0,
        tp1_ratio=0.5,
        direction_filter="long",
        lsi_n_left=1,
        lsi_n_right=1,
        lsi_confirmation_mode="cisd",
        lsi_entry_mode="close",
    )

    baseline = simulator._extract_setup_candidates(df, TEST_SESSION, base_config)
    excluded = simulator._extract_setup_candidates(
        df,
        TEST_SESSION,
        StrategyConfig(
            strategy="lsi",
            sessions=(TEST_SESSION,),
            atr_length=1,
            rr=2.0,
            tp1_ratio=0.5,
            direction_filter="long",
            lsi_n_left=1,
            lsi_n_right=1,
            lsi_confirmation_mode="cisd",
            lsi_entry_mode="close",
            excluded_days=(3,),
        ),
    )

    assert len(baseline) == 1
    assert excluded == []
