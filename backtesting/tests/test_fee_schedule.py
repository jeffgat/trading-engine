"""Execution fee schedule tests."""

from __future__ import annotations

import pytest

from orb_backtest.config import StrategyConfig
from orb_backtest.data.fees import get_fee_schedule
from orb_backtest.data.instruments import get_instrument


@pytest.mark.parametrize(
    ("symbol", "per_side_midpoint", "round_turn_midpoint"),
    [
        ("MNQ", 0.575, 1.15),
        ("MES", 0.575, 1.15),
        ("MGC", 0.825, 1.65),
        ("MCL", 0.775, 1.55),
    ],
)
def test_micro_fee_schedule_midpoints(symbol: str, per_side_midpoint: float, round_turn_midpoint: float) -> None:
    schedule = get_fee_schedule(symbol)
    assert schedule is not None
    assert schedule.per_side_midpoint == pytest.approx(per_side_midpoint)
    assert schedule.round_turn_midpoint == pytest.approx(round_turn_midpoint)


@pytest.mark.parametrize(
    ("symbol", "point_value", "data_file", "commission"),
    [
        ("MNQ", 2.0, "NQ_5m.csv", 0.575),
        ("MES", 5.0, "ES_5m.csv", 0.575),
        ("MGC", 10.0, "GC_5m.csv", 0.825),
        ("MCL", 100.0, "CL_5m.csv", 0.775),
    ],
)
def test_micro_instruments_use_fee_schedule(
    symbol: str,
    point_value: float,
    data_file: str,
    commission: float,
) -> None:
    instrument = get_instrument(symbol)
    assert instrument.point_value == pytest.approx(point_value)
    assert instrument.data_file == data_file
    assert instrument.commission == pytest.approx(commission)
    assert StrategyConfig(instrument=instrument).commission_per_contract == pytest.approx(commission)
