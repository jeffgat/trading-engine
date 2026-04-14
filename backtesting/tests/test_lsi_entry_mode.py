from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig


TEST_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    sweep_start="09:30",
    sweep_end="15:00",
    entry_start="09:35",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=0.0,
)


def _bars(start: str, n: int, *, freq: str = "5min", day: str = "2025-01-03") -> pd.DatetimeIndex:
    return pd.date_range(
        f"{day} {start}",
        periods=n,
        freq=freq,
        tz="America/New_York",
    )


def _df(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    start: str = "09:35",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1.0] * len(open_),
        },
        index=_bars(start, len(open_)),
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


def _extract_classic_long_candidates(
    monkeypatch: pytest.MonkeyPatch,
    *,
    entry_mode: str,
    close_on_sweep_to_inversion_minutes: int = 0,
) -> list[simulator._SetupCandidate]:
    df = _df(
        open_=[101.0, 102.0, 100.5, 100.0, 101.5],
        high=[102.0, 103.0, 101.0, 101.0, 103.0],
        low=[100.0, 101.0, 99.0, 98.5, 98.0],
        close=[101.0, 102.0, 100.0, 100.5, 102.5],
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][3] = True
    fvg["short_fvg_top"][3] = 101.0
    fvg["short_entry_price"][3] = 99.0
    fvg["short_gap_size"][3] = 2.0

    monkeypatch.setattr(
        simulator,
        "detect_swing_highs",
        lambda high, n_left, n_right: np.zeros(len(df), dtype=bool),
    )
    monkeypatch.setattr(
        simulator,
        "detect_swing_lows",
        lambda low, n_left, n_right: np.array([False, True, False, False, False], dtype=bool),
    )

    candidates = simulator._extract_lsi_candidates(
        df,
        fvg,
        valid_long=np.zeros(len(df), dtype=bool),
        valid_short=fvg["short_fvg"].copy(),
        session_day_id=np.zeros(len(df), dtype=np.int64),
        in_entry=np.ones(len(df), dtype=bool),
        in_rth=np.ones(len(df), dtype=bool),
        in_sweep=np.ones(len(df), dtype=bool),
        dates=df.index.date,
        close=df["close"].to_numpy(dtype=float),
        daily_atr=np.full(len(df), 10.0, dtype=float),
        orb_high=np.full(len(df), 110.0, dtype=float),
        orb_low=np.full(len(df), 100.0, dtype=float),
        session=TEST_SESSION,
        n_left=1,
        n_right=1,
        fvg_window_left=10,
        fvg_window_right=10,
        direction_filter="long",
        stop_mode="absolute",
        entry_mode=entry_mode,
        close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
        rr=2.0,
        tp1_ratio=0.5,
    )
    return candidates


def test_extract_lsi_candidates_close_mode_computes_tp1_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    candidates = _extract_classic_long_candidates(monkeypatch, entry_mode="close")

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.direction == 1
    assert candidate.signal_bar == 3
    assert candidate.entry_price == pytest.approx(102.5)


def test_extract_lsi_candidates_timed_hybrid_uses_fvg_limit_when_inversion_is_too_slow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = _extract_classic_long_candidates(
        monkeypatch,
        entry_mode="timed_hybrid",
        close_on_sweep_to_inversion_minutes=5,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.signal_bar == 4
    assert candidate.entry_price == pytest.approx(101.0)


def test_extract_lsi_candidates_timed_hybrid_uses_close_when_inversion_is_fast_enough(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = _extract_classic_long_candidates(
        monkeypatch,
        entry_mode="timed_hybrid",
        close_on_sweep_to_inversion_minutes=15,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.signal_bar == 3
    assert candidate.entry_price == pytest.approx(102.5)
