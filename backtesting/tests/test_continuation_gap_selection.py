from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ


def _df() -> pd.DataFrame:
    index = pd.date_range(
        "2025-01-03 09:30",
        periods=5,
        freq="5min",
        tz="America/New_York",
    )
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "high": [101.0, 102.0, 103.0, 104.0, 105.0],
            "low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "volume": [1.0] * 5,
        },
        index=index,
    )


def _session() -> SessionConfig:
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
    )


def _patch_common(monkeypatch: pytest.MonkeyPatch, n: int) -> None:
    masks = {
        "in_orb": np.zeros(n, dtype=bool),
        "in_entry": np.ones(n, dtype=bool),
        "in_rth": np.ones(n, dtype=bool),
        "in_sweep": np.ones(n, dtype=bool),
    }
    monkeypatch.setattr(simulator, "compute_session_masks", lambda *_args, **_kwargs: masks)
    monkeypatch.setattr(
        simulator,
        "compute_session_days",
        lambda *_args, **_kwargs: (
            np.array([True] + [False] * (n - 1), dtype=bool),
            np.zeros(n, dtype=np.int64),
        ),
    )
    monkeypatch.setattr(simulator, "compute_daily_atr", lambda *_args, **_kwargs: np.full(n, 10.0))
    monkeypatch.setattr(
        simulator,
        "compute_orb_levels",
        lambda *_args, **_kwargs: (
            np.full(n, 100.0),
            np.full(n, 90.0),
            np.ones(n, dtype=bool),
        ),
    )
    monkeypatch.setattr(simulator, "compute_session_vwap", lambda *_args, **_kwargs: np.full(n, 95.0))
    monkeypatch.setattr(
        simulator,
        "compute_date_strings",
        lambda timestamps: np.array(["20250103"] * len(timestamps)),
    )


def test_extract_setup_candidates_continuation_extreme_selects_highest_long_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df = _df()
    _patch_common(monkeypatch, len(df))

    monkeypatch.setattr(
        simulator,
        "detect_fvg",
        lambda *_args, **_kwargs: {
            "long_fvg": np.array([False, True, False, True, False], dtype=bool),
            "short_fvg": np.zeros(len(df), dtype=bool),
            "long_entry_price": np.array([np.nan, 101.0, np.nan, 104.0, np.nan]),
            "short_entry_price": np.full(len(df), np.nan),
            "long_gap_size": np.array([0.0, 1.0, 0.0, 1.5, 0.0]),
            "short_gap_size": np.zeros(len(df), dtype=float),
        },
    )

    base = StrategyConfig(
        sessions=(_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="long",
        rr=2.0,
        tp1_ratio=0.5,
        continuation_fvg_selection="first",
    )
    chase = StrategyConfig(
        sessions=(_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="long",
        rr=2.0,
        tp1_ratio=0.5,
        continuation_fvg_selection="extreme",
    )

    base_candidates = simulator._extract_setup_candidates(df, _session(), base)
    chase_candidates = simulator._extract_setup_candidates(df, _session(), chase)

    assert len(base_candidates) == 1
    assert base_candidates[0].signal_bar == 1
    assert base_candidates[0].entry_price == pytest.approx(101.0)

    assert len(chase_candidates) == 1
    assert chase_candidates[0].signal_bar == 3
    assert chase_candidates[0].entry_price == pytest.approx(104.0)


def test_extract_setup_candidates_continuation_extreme_selects_lowest_short_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    df = _df()
    _patch_common(monkeypatch, len(df))

    monkeypatch.setattr(
        simulator,
        "detect_fvg",
        lambda *_args, **_kwargs: {
            "long_fvg": np.zeros(len(df), dtype=bool),
            "short_fvg": np.array([False, True, False, True, False], dtype=bool),
            "long_entry_price": np.full(len(df), np.nan),
            "short_entry_price": np.array([np.nan, 99.0, np.nan, 96.0, np.nan]),
            "long_gap_size": np.zeros(len(df), dtype=float),
            "short_gap_size": np.array([0.0, 1.0, 0.0, 1.5, 0.0]),
        },
    )

    base = StrategyConfig(
        sessions=(_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        rr=2.0,
        tp1_ratio=0.5,
        continuation_fvg_selection="first",
    )
    chase = StrategyConfig(
        sessions=(_session(),),
        instrument=NQ,
        strategy="continuation",
        direction_filter="short",
        rr=2.0,
        tp1_ratio=0.5,
        continuation_fvg_selection="extreme",
    )

    base_candidates = simulator._extract_setup_candidates(df, _session(), base)
    chase_candidates = simulator._extract_setup_candidates(df, _session(), chase)

    assert len(base_candidates) == 1
    assert base_candidates[0].signal_bar == 1
    assert base_candidates[0].entry_price == pytest.approx(99.0)

    assert len(chase_candidates) == 1
    assert chase_candidates[0].signal_bar == 3
    assert chase_candidates[0].entry_price == pytest.approx(96.0)


def test_strategy_config_rejects_unknown_continuation_fvg_selection() -> None:
    with pytest.raises(ValueError, match="continuation_fvg_selection"):
        StrategyConfig(
            sessions=(_session(),),
            instrument=NQ,
            strategy="continuation",
            rr=2.0,
            tp1_ratio=0.5,
            continuation_fvg_selection="last",
        )
