from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orb_backtest.config import SessionConfig, default_config, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import _compute_session_context_gate_mask
from orb_backtest.results.export import results_to_dict
from orb_backtest.signals.daily_atr import compute_previous_daily_rolling_atr_pct


def test_session_context_gate_mask_applies_prior_atr_and_orb_caps() -> None:
    session = SessionConfig(
        name="NY",
        max_prior_atr_pct=1.5,
        max_prior_rolling_atr_pct=1.5,
        max_orb_range_pct=0.5,
    )
    daily_atr = np.array([10.0, 16.0, 10.0, np.nan])
    previous_daily_close = np.array([1000.0, 1000.0, 1000.0, 1000.0])
    prior_rolling_atr_pct = np.array([1.0, 1.0, 1.6, 1.0])
    orb_high = np.array([104.0, 104.0, 106.0, 104.0])
    orb_low = np.array([100.0, 100.0, 100.0, 100.0])
    orb_open = np.array([1000.0, 1000.0, 1000.0, 1000.0])

    mask = _compute_session_context_gate_mask(
        session,
        daily_atr,
        previous_daily_close,
        prior_rolling_atr_pct,
        orb_high,
        orb_low,
        orb_open,
    )

    assert mask.tolist() == [True, False, False, False]


def test_previous_daily_rolling_atr_pct_matches_research_gate_definition() -> None:
    index = pd.date_range(
        "2025-01-01 09:30",
        periods=4,
        freq="1D",
        tz="America/New_York",
    )
    df = pd.DataFrame(
        {
            "open": [100.0, 100.0, 110.0, 120.0],
            "high": [110.0, 120.0, 140.0, 140.0],
            "low": [90.0, 100.0, 110.0, 120.0],
            "close": [100.0, 110.0, 120.0, 130.0],
            "volume": [1.0, 1.0, 1.0, 1.0],
        },
        index=index,
    )

    rolling_atr_pct = compute_previous_daily_rolling_atr_pct(df, length=2)

    assert np.isnan(rolling_atr_pct[0])
    assert np.isnan(rolling_atr_pct[1])
    assert rolling_atr_pct[2] == pytest.approx(20.0 / 110.0 * 100.0)
    assert rolling_atr_pct[3] == pytest.approx(25.0 / 120.0 * 100.0)


def test_native_context_gate_fields_round_trip_through_overrides_and_export() -> None:
    config = with_overrides(
        default_config(NQ),
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
            ),
        ),
        ny_max_prior_atr_pct=1.6228,
        ny_max_prior_rolling_atr_pct=1.6228,
        ny_max_orb_range_pct=0.4658,
    )

    assert config.sessions[0].max_prior_atr_pct == 1.6228
    assert config.sessions[0].max_prior_rolling_atr_pct == 1.6228
    assert config.sessions[0].max_orb_range_pct == 0.4658

    payload = results_to_dict([], config, include_trades=False)

    assert payload["config"]["ny_max_prior_atr_pct"] == 1.6228
    assert payload["config"]["ny_max_prior_rolling_atr_pct"] == 1.6228
    assert payload["config"]["ny_max_orb_range_pct"] == 0.4658
