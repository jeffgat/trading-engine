"""Tests for the Hunter/classic ORB execution leg."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.engine import State
from trader.hunter_orb_engine import HunterORBEngine
from tests.builders import make_bar


@pytest.fixture
def broker():
    b = MagicMock(spec=TradersPostClient)
    b.send_entry = AsyncMock(return_value=[
        WebhookResult(payload={"action": "buy"}, status=None, latency_ms=0, dry_run=True),
    ])
    b.send_cancel = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    b.send_flatten = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    b.paused = False
    b.multiplier = 1.0
    return b


def _make_hunter_engine(broker, **overrides) -> HunterORBEngine:
    defaults = dict(
        name="H_ORB",
        broker=broker,
        exec_ticker="MNQ",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="11:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=0.0,
        min_gap_atr_pct=0.0,
        max_gap_atr_pct=0.0,
        rr=2.0,
        tp1_ratio=1.0,
        risk_usd=350.0,
        point_value=2.0,
        min_qty=1.0,
        qty_step=1.0,
        be_offset_ticks=0,
        min_tick=0.25,
        stop_basis="hunter",
        gap_filter_basis="hunter",
        long_only=False,
        short_only=False,
        excluded_dow=[1],
        post_exit_cleanup_delay_s=0.0,
        post_exit_cancel_settle_delay_s=0.0,
    )
    defaults.update(overrides)
    return HunterORBEngine(**defaults)


async def _seed_ema_and_orb(engine: HunterORBEngine) -> None:
    for bar in [
        make_bar("2025-01-15 09:00", 95, 96, 94, 95),
        make_bar("2025-01-15 09:05", 95, 96, 94, 95),
        make_bar("2025-01-15 09:10", 95, 96, 94, 95),
        make_bar("2025-01-15 09:15", 96, 97, 95, 96),
        make_bar("2025-01-15 09:20", 96, 97, 95, 96),
        make_bar("2025-01-15 09:25", 96, 97, 95, 96),
        make_bar("2025-01-15 09:30", 95, 100, 90, 94),
        make_bar("2025-01-15 09:35", 94, 101, 92, 94),
        make_bar("2025-01-15 09:40", 94, 102, 93, 94),
    ]:
        await engine.on_bar(bar, 300.0)


class TestHunterORBEngine:
    async def test_breakout_body_and_ema_filters_trigger_market_style_bracket(self, broker):
        engine = _make_hunter_engine(broker)
        await _seed_ema_and_orb(engine)

        await engine.on_bar(make_bar("2025-01-15 09:45", 100, 116, 99, 115), 300.0)

        assert engine._state == State.MANAGING
        assert engine._levels is not None
        assert engine._levels.entry == pytest.approx(115.0)
        assert engine._levels.stop == pytest.approx(98.0)
        assert engine._levels.tp2 == pytest.approx(149.0)
        assert engine._levels.qty == pytest.approx(10.0)
        broker.send_entry.assert_called_once()
        assert broker.send_entry.call_args.kwargs["action"] == "buy"
        assert broker.send_entry.call_args.kwargs["ticker"] == "MNQ"

    async def test_weak_body_breakout_is_rejected(self, broker):
        engine = _make_hunter_engine(broker)
        await _seed_ema_and_orb(engine)

        await engine.on_bar(make_bar("2025-01-15 09:45", 105, 116, 99, 106), 300.0)

        assert engine._state == State.WAITING_FOR_GAP
        broker.send_entry.assert_not_called()

    async def test_target_exit_records_trade_and_returns_to_scanning_window(self, broker):
        engine = _make_hunter_engine(broker)
        records = []
        engine.on_trade_exit = records.append
        await _seed_ema_and_orb(engine)
        await engine.on_bar(make_bar("2025-01-15 09:45", 100, 116, 99, 115), 300.0)

        await engine.on_tick(make_bar("2025-01-15 09:50", 115, 149, 114, 149), 300.0)
        await asyncio.sleep(0)

        assert engine._state == State.WAITING_FOR_GAP
        assert len(records) == 1
        assert records[0].session == "H_ORB"
        assert records[0].exit_type == "tp2_direct"
        assert records[0].r_result == pytest.approx(2.0)
