from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.engine import Bar, State
from trader.position_limits import ContractCapManager
from tests.builders import make_bar
from tests.conftest import _make_orb_engine, advance_to_armed, advance_to_managing


def _mock_broker():
    broker = MagicMock(spec=TradersPostClient)
    broker.send_entry = AsyncMock(return_value=[
        WebhookResult(payload={"action": "buy"}, status=None, latency_ms=0, dry_run=True),
    ])
    broker.send_tp1_multi = AsyncMock(return_value=[])
    broker.send_tp1_single = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    broker.send_flatten = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    broker.send_cancel = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    broker.paused = False
    broker.multiplier = 1.0
    return broker


@pytest.mark.asyncio
async def test_contract_cap_resizes_entry_qty_before_order_send():
    broker = _mock_broker()
    manager = ContractCapManager(max_open_contracts=20)
    engine = _make_orb_engine(
        broker,
        risk_usd=2000.0,
        position_manager=manager,
        position_limit_key="FAST_V2:NQ",
    )

    await advance_to_armed(engine)

    assert engine._state == State.ARMED_LIMIT
    assert engine._levels is not None
    assert engine._levels.qty == 20.0
    assert manager.total_allocated() == 20.0
    assert broker.send_entry.call_args.kwargs["qty"] == 20.0


@pytest.mark.asyncio
async def test_second_entry_is_blocked_when_contract_cap_is_fully_used():
    manager = ContractCapManager(max_open_contracts=20)
    first_broker = _mock_broker()
    second_broker = _mock_broker()

    first = _make_orb_engine(
        first_broker,
        name="ES_Asia",
        risk_usd=2000.0,
        position_manager=manager,
        position_limit_key="FAST_V2:ES",
    )
    second = _make_orb_engine(
        second_broker,
        name="NQ_NY",
        risk_usd=2000.0,
        position_manager=manager,
        position_limit_key="FAST_V2:NQ",
    )

    await advance_to_armed(first)
    assert manager.total_allocated() == 20.0

    await advance_to_armed(second)

    assert second._state == State.WAITING_FOR_GAP
    assert second._levels is None
    second_broker.send_entry.assert_not_called()
    assert manager.total_allocated() == 20.0


@pytest.mark.asyncio
async def test_tp1_partial_releases_capacity_for_later_entry():
    manager = ContractCapManager(max_open_contracts=20)
    first_broker = _mock_broker()
    second_broker = _mock_broker()

    first, _ = await advance_to_managing(
        _make_orb_engine(
            first_broker,
            name="ES_Asia",
            risk_usd=2000.0,
            position_manager=manager,
            position_limit_key="FAST_V2:ES",
        )
    )
    assert first._levels is not None
    assert first._levels.qty == 20.0
    assert manager.total_allocated() == 20.0

    fill_ts = first._fill_timestamp
    assert fill_ts is not None
    tp1_tick = Bar(
        timestamp=fill_ts + timedelta(seconds=2),
        open=first._levels.tp1 - 1,
        high=first._levels.tp1 + 2,
        low=first._levels.entry,
        close=first._levels.tp1 + 1,
        volume=10,
    )
    await first.on_tick(tp1_tick, 300.0)

    assert first._tp1_hit is True
    assert manager.total_allocated() == 10.0

    second = _make_orb_engine(
        second_broker,
        name="NQ_NY",
        risk_usd=2000.0,
        position_manager=manager,
        position_limit_key="FAST_V2:NQ",
    )
    await advance_to_armed(second)

    assert second._levels is not None
    assert second._levels.qty == 10.0
    assert second_broker.send_entry.call_args.kwargs["qty"] == 10.0
    assert manager.total_allocated() == 20.0


@pytest.mark.asyncio
async def test_second_same_asset_entry_is_blocked_even_with_remaining_contract_headroom():
    manager = ContractCapManager(max_open_contracts=40)
    first_broker = _mock_broker()
    second_broker = _mock_broker()

    first = _make_orb_engine(
        first_broker,
        name="ES_Asia",
        risk_usd=2000.0,
        position_manager=manager,
        position_limit_key="FAST_V2:ES",
    )
    second = _make_orb_engine(
        second_broker,
        name="ES_NY",
        risk_usd=2000.0,
        position_manager=manager,
        position_limit_key="FAST_V2:ES",
    )

    await advance_to_armed(first)
    assert first._state == State.ARMED_LIMIT
    assert first._levels is not None
    assert manager.total_allocated() == first._levels.qty

    await advance_to_armed(second)

    assert second._state == State.WAITING_FOR_GAP
    assert second._levels is None
    second_broker.send_entry.assert_not_called()
    assert manager.total_allocated() == first._levels.qty
