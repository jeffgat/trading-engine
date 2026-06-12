from types import SimpleNamespace

import pytest

from trader.api import (
    DashboardState,
    _broker_cleanup_tickers_from_engine,
    _manual_flatten_engine,
    _public_exec_config_meta,
    _runtime_mode_from_brokers,
    parse_trade_log_line,
)
from trader.auth import authenticate_http_request
from trader.engine import State, TradeRecord
from trader.sizing import TradeLevels
from tests.builders import make_bar


def test_runtime_mode_from_brokers_live_when_any_broker_has_webhook():
    state = DashboardState(
        multi_brokers_by_config={
            "DRY": SimpleNamespace(_brokers=[SimpleNamespace(dry_run=True)]),
            "LIVE": SimpleNamespace(_brokers=[SimpleNamespace(dry_run=False)]),
        }
    )

    assert _runtime_mode_from_brokers(state) == "LIVE"


def test_runtime_mode_from_brokers_dry_run_without_live_brokers():
    state = DashboardState(
        multi_brokers_by_config={
            "DRY": SimpleNamespace(_brokers=[SimpleNamespace(dry_run=True)]),
        }
    )

    assert _runtime_mode_from_brokers(state) == "DRY-RUN"


def test_public_exec_config_meta_keeps_live_count_without_webhook_urls():
    state = DashboardState(
        exec_configs={
            "ALPHA_V1-A": {
                "enabled": True,
                "max_open_contracts": 20,
                "webhooks": [
                    {
                        "url": "https://example.com/secret",
                        "label": "funded",
                        "paused": False,
                        "multiplier": 1.0,
                    }
                ],
                "sessions": ["NQ_NY"],
                "lsi_sessions": ["NQ_NY_LSI"],
            },
            "SHADOW": {
                "enabled": True,
                "max_open_contracts": 0,
                "webhooks": [],
                "sessions": ["ES_NY"],
                "lsi_sessions": [],
            },
        }
    )

    public_meta = _public_exec_config_meta(state)

    assert len(public_meta["ALPHA_V1-A"]["webhooks"]) == 1
    assert public_meta["ALPHA_V1-A"]["webhooks"] == [{}]
    assert public_meta["ALPHA_V1-A"]["sessions"] == ["NQ_NY"]
    assert public_meta["SHADOW"]["webhooks"] == []


def test_broker_cleanup_tickers_include_rollover_neighbors():
    engine = SimpleNamespace(
        exec_ticker="MES",
        broker_ticker="MESU2026",
        _exec_contract="MESU2026",
        _trade_exec_contract="",
        _signal_contract="ESU6",
        _trade_signal_contract="",
    )

    tickers = _broker_cleanup_tickers_from_engine(engine)

    assert tickers[:4] == ["MESU2026", "MESM2026", "MESZ2026", "MES"]


def test_parse_trade_log_line_keeps_full_tick_time_and_resolution():
    line = (
        "2026-03-11 21:46:00 | FAST_V2 | es | ES_Asia | TP1_PARTIAL | "
        "dir=long tp1=6737.75 half_qty=12.0 be=6734.75 tp2=6740.16 "
        "tick_time=2026-03-11 21:45:59-04:00 resolution=1s"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["details"]["tick_time"] == "2026-03-11 21:45:59-04:00"
    assert parsed["details"]["resolution"] == "1s"


def test_parse_trade_log_line_keeps_full_bar_time():
    line = (
        "2026-03-11 21:50:00 | FAST_V2 | es | ES_Asia | TP1_PARTIAL | "
        "dir=long tp1=6737.75 be=6734.75 bar_time=2026-03-11 21:45:00-04:00 resolution=5m"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["details"]["bar_time"] == "2026-03-11 21:45:00-04:00"
    assert parsed["details"]["resolution"] == "5m"


def test_parse_trade_log_line_normalizes_legacy_alpha_v1_config_name():
    line = (
        "2026-04-14 04:05:00 | ALPHA_V1 | nq | NQ_Asia | TP1_PARTIAL | "
        "dir=long tp1=25641.60 half_qty=2.0 be=25590.75 tp2=25760.25"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["config"] == "ALPHA_V1-A"


def test_parse_trade_log_line_recognizes_silver_asset_tag():
    line = (
        "2026-05-04 20:37:00 | TESTING | sil | SI_Asia | REGIME_GATE_BLOCKED | "
        "gate=block_bull_medium_vol date=20260504"
    )

    parsed = parse_trade_log_line(line)

    assert parsed is not None
    assert parsed["config"] == "TESTING"
    assert parsed["asset"] == "sil"
    assert parsed["session"] == "SI_Asia"
    assert parsed["event"] == "REGIME_GATE_BLOCKED"
    assert parsed["details"]["gate"] == "block_bull_medium_vol"


def test_dashboard_state_asia_tp1_hit_for_date_accepts_alpha_v1_alias():
    state = DashboardState()
    state.trade_history = [
        TradeRecord(
            session="NQ_Asia",
            date="20260414",
            direction=1,
            entry_price=1.0,
            stop_price=0.0,
            tp1_price=2.0,
            tp2_price=3.0,
            exit_type="tp1_partial",
            tp1_hit=True,
            timestamp="2026-04-14T04:05:00-04:00",
            config_name="ALPHA_V1",
            r_result=0.9,
            entry_timestamp="2026-04-14T03:40:00-04:00",
        )
    ]

    assert state.asia_tp1_hit_for_date("20260414", config_name="ALPHA_V1-A") is True


@pytest.mark.asyncio
async def test_manual_flatten_route_requires_auth_when_enabled(monkeypatch):
    monkeypatch.setenv("BACKEND_AUTH_ENABLED", "1")
    request = SimpleNamespace(
        method="POST",
        url=SimpleNamespace(path="/api/engines/NQ_NY/flatten"),
        headers={},
    )

    response = await authenticate_http_request(request)

    assert response is not None
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_manual_flatten_engine_flattens_managing_trade(make_orb_engine, mock_broker):
    engine = make_orb_engine(config_name="ALPHA_V1-A")
    engine._state = State.MANAGING
    engine._current_date = "20260529"
    engine._levels = TradeLevels(
        entry=100.0,
        stop=90.0,
        tp1=105.0,
        tp2=120.0,
        be=100.0,
        qty=1.0,
        half_qty=1.0,
        is_single_contract=True,
        risk_pts=10.0,
        direction=1,
        gap_size=2.0,
    )
    engine._bars.append(make_bar("2026-05-29 10:05", 101.0, 104.5, 100.5, 104.0))
    records = []
    engine.on_trade_exit = records.append

    result = await _manual_flatten_engine(engine)

    assert result["action"] == "flattened_position"
    assert result["previous_state"] == "managing"
    assert result["state"] == "flat"
    mock_broker.send_flatten.assert_called_once_with(ticker="MNQ")
    mock_broker.send_cancel.assert_not_called()
    assert engine._state == State.FLAT
    assert records[0].exit_type == "manual_flat"
    assert records[0].r_result == pytest.approx(0.4)


@pytest.mark.asyncio
async def test_manual_flatten_engine_cancels_armed_limit(make_orb_engine, mock_broker):
    engine = make_orb_engine(config_name="ALPHA_V1-A")
    engine._state = State.ARMED_LIMIT
    engine._levels = TradeLevels(
        entry=100.0,
        stop=90.0,
        tp1=105.0,
        tp2=120.0,
        be=100.0,
        qty=1.0,
        half_qty=1.0,
        is_single_contract=True,
        risk_pts=10.0,
        direction=1,
        gap_size=2.0,
    )

    result = await _manual_flatten_engine(engine)

    assert result["action"] == "cancelled_pending_order"
    assert result["previous_state"] == "armed_limit"
    assert result["state"] == "flat"
    mock_broker.send_cancel.assert_called_once_with(ticker="MNQ")
    mock_broker.send_flatten.assert_not_called()
    assert engine._state == State.FLAT
