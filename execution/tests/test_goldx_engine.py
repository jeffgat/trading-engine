"""Tests for the Gold-X reverse-engineered execution leg."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.checkpoint import restore_orb_engine, serialize_orb_engine
from trader.engine import State
from trader.goldx_engine import GoldXEngine
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


def _make_goldx_engine(broker, **overrides) -> GoldXEngine:
    defaults = dict(
        name="GOLD_X",
        broker=broker,
        exec_ticker="MGC",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:05",
        flat_start="16:55",
        flat_end="17:00",
        stop_atr_pct=0.0,
        min_gap_atr_pct=0.0,
        max_gap_atr_pct=0.0,
        rr=2.0,
        tp1_ratio=1.0,
        risk_usd=400.0,
        point_value=10.0,
        min_qty=1.0,
        qty_step=1.0,
        be_offset_ticks=0,
        min_tick=0.10,
        stop_basis="gold_x",
        gap_filter_basis="gold_x",
        long_only=False,
        short_only=False,
        goldx_enable_classic_proxy_filters=False,
        goldx_enable_fvg_ut_filter=False,
        post_exit_cleanup_delay_s=0.0,
        post_exit_cancel_settle_delay_s=0.0,
    )
    defaults.update(overrides)
    return GoldXEngine(**defaults)


async def _seed_goldx_orb(engine: GoldXEngine) -> None:
    for bar in [
        make_bar("2025-01-13 09:30", 96, 100, 90, 95),
        make_bar("2025-01-13 09:35", 95, 101, 91, 96),
        make_bar("2025-01-13 09:40", 96, 102, 92, 100),
    ]:
        await engine.on_bar(bar, 20.0)


class TestGoldXEngine:
    async def test_classic_breakout_enters_market_style_bracket(self, broker):
        engine = _make_goldx_engine(broker, goldx_mode="classic_only")
        await _seed_goldx_orb(engine)

        await engine.on_bar(make_bar("2025-01-13 09:45", 101, 110, 100, 108), 20.0)

        assert engine._state == State.MANAGING
        assert engine._levels is not None
        assert engine._levels.entry == pytest.approx(108.0)
        assert engine._levels.stop == pytest.approx(89.0)
        assert engine._levels.tp2 == pytest.approx(114.0)
        assert engine._levels.qty == pytest.approx(2.0)
        broker.send_entry.assert_called_once()
        assert broker.send_entry.call_args.kwargs["ticker"] == "MGC"

    async def test_classic_target_exit_records_full_target(self, broker):
        engine = _make_goldx_engine(broker, goldx_mode="classic_only")
        records = []
        engine.on_trade_exit = records.append
        await _seed_goldx_orb(engine)
        await engine.on_bar(make_bar("2025-01-13 09:45", 101, 110, 100, 108), 20.0)

        await engine.on_tick(make_bar("2025-01-13 09:51", 108, 114, 107, 114), 20.0)
        await asyncio.sleep(0)

        assert records
        assert records[0].session == "GOLD_X"
        assert records[0].exit_type == "tp2_direct"
        assert records[0].r_result == pytest.approx((114.0 - 108.0) / (108.0 - 89.0))

    async def test_fvg_only_arms_and_fills_retest_limit(self, broker):
        engine = _make_goldx_engine(broker, name="GOLD_X_SAFE", goldx_mode="fvg_only")
        await _seed_goldx_orb(engine)

        await engine.on_bar(make_bar("2025-01-13 09:45", 101, 109, 101, 108), 20.0)
        await engine.on_bar(make_bar("2025-01-13 09:50", 114, 120, 112, 118), 20.0)

        assert engine._state == State.ARMED_LIMIT
        assert engine._levels is not None
        assert engine._levels.entry == pytest.approx(112.0)
        assert engine._levels.stop == pytest.approx(101.0)
        assert engine._levels.tp2 == pytest.approx(134.0)

        await engine.on_bar(make_bar("2025-01-13 09:55", 118, 119, 111, 113), 20.0)

        assert engine._state == State.MANAGING
        assert engine._fill_timestamp is not None

    async def test_checkpoint_preserves_goldx_active_trade_fields(self, broker):
        engine = _make_goldx_engine(broker, goldx_mode="classic_only")
        await _seed_goldx_orb(engine)
        await engine.on_bar(make_bar("2025-01-13 09:45", 101, 110, 100, 108), 20.0)

        data = serialize_orb_engine(engine)
        assert data["engine_type"] == "gold_x"
        assert data["goldx_active_family"] == "classic"
        assert data["goldx_max_hold_at"]
        assert data["goldx_quartile_stop"] == pytest.approx(99.0)

        restored = _make_goldx_engine(broker, goldx_mode="classic_only")
        assert restore_orb_engine(restored, data) is True
        assert restored._state == State.MANAGING
        assert restored._goldx_active_family == "classic"
        assert restored._goldx_max_hold_at == engine._goldx_max_hold_at
        assert restored._goldx_quartile_stop == pytest.approx(99.0)
