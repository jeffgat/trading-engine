"""Shared pytest fixtures for the execution engine test suite."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.engine import Bar, ORBEngine

ET = ZoneInfo("America/New_York")

# Re-export make_bar so it's available via conftest import in all test files
from tests.builders import make_bar  # noqa: E402  (conftest-level import)


@pytest.fixture
def mock_broker():
    """TradersPostClient with all send_* methods as AsyncMock.

    Use broker.send_entry.call_args etc. to inspect what was sent.
    """
    broker = MagicMock(spec=TradersPostClient)
    broker.send_entry = AsyncMock(return_value=[
        WebhookResult(payload={"action": "exit"}, status=None, latency_ms=0, dry_run=True),
        WebhookResult(payload={"action": "buy"}, status=None, latency_ms=0, dry_run=True),
    ])
    broker.send_tp1_multi = AsyncMock(return_value=[])
    broker.send_tp1_single = AsyncMock(
        return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True)
    )
    broker.send_flatten = AsyncMock(
        return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True)
    )
    broker.send_cancel = AsyncMock(
        return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True)
    )
    broker.paused = False
    broker.multiplier = 1.0
    return broker


def _make_orb_engine(broker, **overrides) -> ORBEngine:
    """Build an ORBEngine with NQ_NY-style defaults. Override any field via kwargs."""
    defaults = dict(
        name="NQ_NY",
        broker=broker,
        exec_ticker="MNQ",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="12:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=11.0,
        min_gap_atr_pct=0.5,
        max_gap_atr_pct=0.0,
        rr=11.0,
        tp1_ratio=0.5,
        risk_usd=250.0,
        point_value=2.0,
        min_qty=1.0,
        qty_step=1.0,
        be_offset_ticks=4,
        min_tick=0.25,
        long_only=True,
    )
    defaults.update(overrides)
    return ORBEngine(**defaults)


@pytest.fixture
def make_orb_engine(mock_broker):
    """Fixture that returns a factory for ORBEngine instances."""
    def _factory(**overrides):
        return _make_orb_engine(mock_broker, **overrides)
    return _factory


async def advance_to_scanning(
    engine: ORBEngine,
    atr: float = 300.0,
    date: str = "2025-01-15",
    orb_high: float = 19530.0,
) -> ORBEngine:
    """Drive engine from IDLE to WAITING_FOR_GAP by feeding ORB bars + transition bar.

    The transition bar is at 09:45 with a high *above* orb_high + 5 so it
    cannot accidentally serve as the ``bar2`` (before-candle) of the FVG
    pattern formed by subsequent bars.
    """
    from tests.builders import build_orb_sequence, make_bar
    for bar in build_orb_sequence(date, orb_high=orb_high):
        await engine.on_bar(bar, atr)
    # High must exceed (orb_high + 5) to block false FVG with next bars
    t_high = orb_high + 8
    transition = make_bar(f"{date} 09:45", orb_high + 1, t_high, orb_high - 5, orb_high + 5)
    await engine.on_bar(transition, atr)
    return engine


async def advance_to_armed(
    engine: ORBEngine,
    atr: float = 300.0,
    date: str = "2025-01-15",
    orb_high: float = 19530.0,
) -> ORBEngine:
    """Drive engine from IDLE to ARMED_LIMIT by feeding ORB + FVG bars."""
    from tests.builders import build_bullish_fvg_bars
    await advance_to_scanning(engine, atr, date, orb_high=orb_high)
    for bar in build_bullish_fvg_bars(date, orb_high=orb_high, gap=10.0):
        await engine.on_bar(bar, atr)
    return engine


async def advance_to_managing(
    engine: ORBEngine,
    atr: float = 300.0,
    date: str = "2025-01-15",
    orb_high: float = 19530.0,
) -> tuple[ORBEngine, float]:
    """Drive engine from IDLE to MANAGING (filled) and return (engine, entry_price).

    Uses the engine's actual _levels.entry to construct the fill bar so that
    bar.low ≤ entry regardless of which FVG the engine detected.
    """
    from tests.builders import make_bar
    await advance_to_armed(engine, atr, date, orb_high)
    assert engine._levels is not None, "advance_to_armed did not reach ARMED_LIMIT"
    entry_price = engine._levels.entry
    # Feed a fill bar at 10:05: low ≤ entry
    fill_bar = make_bar(
        f"{date} 10:05",
        entry_price + 5,
        entry_price + 20,
        entry_price - 5,  # low below entry → fills
        entry_price + 15,
    )
    await engine.on_bar(fill_bar, atr)
    return engine, entry_price
