"""Execution fee schedule tests."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from trader.fees import get_fee_schedule
from trader.historical_backtest import ReplayRecorder
from trader.main import INSTRUMENTS, SIGNAL_TO_EXEC


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
    ("symbol", "point_value", "commission"),
    [
        ("MNQ", 2.0, 0.575),
        ("MES", 5.0, 0.575),
        ("MGC", 10.0, 0.825),
        ("MCL", 100.0, 0.775),
    ],
)
def test_execution_instruments_use_fee_schedule(symbol: str, point_value: float, commission: float) -> None:
    instrument = INSTRUMENTS[symbol]
    assert instrument["point_value"] == pytest.approx(point_value)
    assert instrument["commission"] == pytest.approx(commission)


def test_cl_routes_to_micro_crude() -> None:
    assert SIGNAL_TO_EXEC["CL"] == "MCL"


def test_exact_replay_recorder_subtracts_round_turn_commission() -> None:
    recorder = ReplayRecorder("fees")
    engine = SimpleNamespace(
        _levels=SimpleNamespace(
            entry=100.0,
            stop=90.0,
            tp1=110.0,
            tp2=120.0,
            qty=3.0,
            gap_size=1.0,
        ),
        point_value=2.0,
        commission_per_contract=0.575,
        _swept_level=None,
        _fvg_top=None,
        _fvg_bottom=None,
        lsi_variant="",
        _swept_level_time=None,
        _active_htf_level_side="",
        htf_level_tf_minutes=None,
        _fvg_to_inversion_bars=None,
        _sweep_to_inversion_bars=None,
    )
    record = SimpleNamespace(
        r_result=1.0,
        date="20250115",
        session="NQ_NY",
        direction=1,
        exit_type="tp2_direct",
        entry_timestamp="2025-01-15T09:45:00-05:00",
        timestamp="2025-01-15T10:15:00-05:00",
    )

    recorder.make_callback(engine)(record)

    assert recorder.trades[0]["gross_pnl_usd"] == pytest.approx(60.0)
    assert recorder.trades[0]["commission_usd"] == pytest.approx(3.45)
    assert recorder.trades[0]["pnl_usd"] == pytest.approx(56.55)
    assert recorder.trades[0]["net_r_multiple"] == pytest.approx(0.943)
