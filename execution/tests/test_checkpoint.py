"""Tests for checkpoint persistence — serialization, restore, and crash recovery.

Covers: atomic writes, Bar/TradeLevels/SweepEvent/GapInfo round-trips,
ORBEngine and LSIEngine checkpoint/restore, trade history persistence,
staleness checks, and G5 gate recovery.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.engine import Bar, ORBEngine, State, TradeRecord
from trader.lsi_engine import GapInfo, LSIEngine, LSIState
from trader.sizing import TradeLevels
from trader.swing import SweepEvent
from trader.checkpoint import (
    _atomic_write,
    _deserialize_bar,
    _deserialize_gap,
    _deserialize_levels,
    _deserialize_sweep,
    _serialize_bar,
    _serialize_gap,
    _serialize_levels,
    _serialize_sweep,
    load_checkpoint,
    load_trade_history,
    restore_engines,
    restore_lsi_engine,
    restore_orb_engine,
    save_checkpoint,
    save_trade_history,
    serialize_lsi_engine,
    serialize_orb_engine,
    CHECKPOINT_VERSION,
)
from tests.builders import make_bar
from tests.conftest import (
    _make_orb_engine,
    advance_to_armed,
    advance_to_managing,
    advance_to_scanning,
)

ET = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_broker():
    b = MagicMock(spec=TradersPostClient)
    b.send_entry = AsyncMock(return_value=[
        WebhookResult(payload={"action": "exit"}, status=None, latency_ms=0, dry_run=True),
        WebhookResult(payload={"action": "buy"}, status=None, latency_ms=0, dry_run=True),
    ])
    b.send_tp1_multi = AsyncMock(return_value=[])
    b.send_tp1_single = AsyncMock(
        return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True)
    )
    b.send_flatten = AsyncMock(
        return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True)
    )
    b.send_cancel = AsyncMock(
        return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True)
    )
    b.paused = False
    b.multiplier = 1.0
    return b


def _make_lsi_engine(broker, **overrides) -> LSIEngine:
    defaults = dict(
        name="NQ_NY_LSI",
        broker=broker,
        exec_ticker="MNQ",
        entry_start="09:45",
        entry_end="12:00",
        flat_start="15:50",
        flat_end="16:00",
        rr=3.0,
        tp1_ratio=0.3,
        min_gap_atr_pct=5.0,
        risk_usd=250.0,
        point_value=2.0,
        min_qty=1.0,
        qty_step=1.0,
        min_tick=0.25,
    )
    defaults.update(overrides)
    return LSIEngine(**defaults)


def _sample_trade_levels() -> TradeLevels:
    return TradeLevels(
        entry=19540.0,
        stop=19508.25,
        tp1=19591.38,
        tp2=19651.12,
        be=19541.0,
        qty=3.0,
        half_qty=1.0,
        is_single_contract=False,
        risk_pts=31.75,
        direction=1,
        gap_size=12.5,
    )


def _sample_bar() -> Bar:
    return Bar(
        timestamp=datetime(2026, 3, 2, 10, 30, tzinfo=ET),
        open=19560.0,
        high=19575.0,
        low=19555.0,
        close=19570.0,
        volume=1234,
    )


# =============================================================================
# Serialization round-trip tests
# =============================================================================


class TestBarSerialization:
    def test_round_trip(self):
        bar = _sample_bar()
        data = _serialize_bar(bar)
        restored = _deserialize_bar(data)
        assert restored.open == bar.open
        assert restored.high == bar.high
        assert restored.low == bar.low
        assert restored.close == bar.close
        assert restored.volume == bar.volume
        assert restored.timestamp == bar.timestamp

    def test_json_safe(self):
        bar = _sample_bar()
        data = _serialize_bar(bar)
        json_str = json.dumps(data)
        assert isinstance(json_str, str)


class TestTradeLevelsSerialization:
    def test_round_trip(self):
        levels = _sample_trade_levels()
        data = _serialize_levels(levels)
        restored = _deserialize_levels(data)
        assert restored.entry == levels.entry
        assert restored.stop == levels.stop
        assert restored.tp1 == levels.tp1
        assert restored.tp2 == levels.tp2
        assert restored.be == levels.be
        assert restored.qty == levels.qty
        assert restored.half_qty == levels.half_qty
        assert restored.is_single_contract == levels.is_single_contract
        assert restored.direction == levels.direction

    def test_none_levels(self):
        assert _serialize_levels(None) is None
        assert _deserialize_levels(None) is None


class TestSweepEventSerialization:
    def test_round_trip(self):
        sweep = SweepEvent(source="kz_low", level=19420.0, direction=1, bar_index=12)
        data = _serialize_sweep(sweep)
        restored = _deserialize_sweep(data)
        assert restored.source == sweep.source
        assert restored.level == sweep.level
        assert restored.direction == sweep.direction
        assert restored.bar_index == sweep.bar_index

    def test_none(self):
        assert _serialize_sweep(None) is None
        assert _deserialize_sweep(None) is None


class TestGapInfoSerialization:
    def test_round_trip(self):
        gap = GapInfo(top=19450.0, bottom=19435.0, is_bullish=False,
                      impulse_high=19460.0, impulse_low=19430.0, bar_index=16)
        data = _serialize_gap(gap)
        restored = _deserialize_gap(data)
        assert restored.top == gap.top
        assert restored.bottom == gap.bottom
        assert restored.is_bullish == gap.is_bullish
        assert restored.impulse_high == gap.impulse_high
        assert restored.impulse_low == gap.impulse_low
        assert restored.bar_index == gap.bar_index

    def test_none(self):
        assert _serialize_gap(None) is None
        assert _deserialize_gap(None) is None


# =============================================================================
# Atomic write tests
# =============================================================================


class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "test.json"
        _atomic_write(p, {"key": "value"})
        assert p.exists()
        data = json.loads(p.read_text())
        assert data["key"] == "value"

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "test.json"
        _atomic_write(p, {"version": 1})
        _atomic_write(p, {"version": 2})
        data = json.loads(p.read_text())
        assert data["version"] == 2

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "nested" / "dir" / "test.json"
        _atomic_write(p, {"ok": True})
        assert p.exists()


# =============================================================================
# ORBEngine checkpoint tests
# =============================================================================


class TestORBEngineCheckpoint:
    async def test_serialize_armed(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        await advance_to_armed(engine)
        assert engine._state == State.ARMED_LIMIT

        data = serialize_orb_engine(engine)
        assert data["engine_type"] == "orb"
        assert data["state"] == "armed_limit"
        assert data["levels"] is not None
        assert data["levels"]["direction"] == 1

    async def test_restore_armed(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        await advance_to_armed(engine)

        data = serialize_orb_engine(engine)
        original_entry = engine._levels.entry

        # Create fresh engine and restore
        new_engine = _make_orb_engine(_mock_broker())
        assert new_engine._state == State.IDLE

        result = restore_orb_engine(new_engine, data)
        assert result is True
        assert new_engine._state == State.ARMED_LIMIT
        assert new_engine._levels is not None
        assert new_engine._levels.entry == original_entry
        assert new_engine._orb_high == engine._orb_high
        assert new_engine._orb_low == engine._orb_low

    async def test_restore_managing(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        engine, entry = await advance_to_managing(engine)
        assert engine._state == State.MANAGING

        data = serialize_orb_engine(engine)

        new_engine = _make_orb_engine(_mock_broker())
        result = restore_orb_engine(new_engine, data)
        assert result is True
        assert new_engine._state == State.MANAGING
        assert new_engine._levels.entry == entry
        assert new_engine._fill_bar_idx == engine._fill_bar_idx

    async def test_restore_managing_tp1_hit(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        engine, _ = await advance_to_managing(engine)

        # Simulate TP1 hit
        engine._tp1_hit = True
        engine._tp1_bar_count = engine._bar_count

        data = serialize_orb_engine(engine)
        new_engine = _make_orb_engine(_mock_broker())
        restore_orb_engine(new_engine, data)

        assert new_engine._tp1_hit is True
        assert new_engine._tp1_bar_count == engine._tp1_bar_count

    def test_idle_not_restored(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        data = serialize_orb_engine(engine)

        new_engine = _make_orb_engine(_mock_broker())
        result = restore_orb_engine(new_engine, data)
        assert result is False
        assert new_engine._state == State.IDLE

    async def test_scanning_not_restored_outside_entry(self):
        """WAITING_FOR_GAP is downgraded to FLAT when entry window is closed."""
        from unittest.mock import patch
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        await advance_to_scanning(engine)
        assert engine._state == State.WAITING_FOR_GAP

        data = serialize_orb_engine(engine)
        new_engine = _make_orb_engine(_mock_broker())
        # Mock time to be outside entry window (e.g. 23:00 ET)
        fake_now = datetime(2026, 3, 3, 23, 0, tzinfo=ET)
        with patch("trader.checkpoint.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = restore_orb_engine(new_engine, data)
        assert result is True  # restore succeeds (state is FLAT, not IDLE)
        assert new_engine._state == State.FLAT

    def test_unknown_state_not_restored(self):
        data = {"state": "nonexistent_state"}
        engine = _make_orb_engine(_mock_broker())
        result = restore_orb_engine(engine, data)
        assert result is False


# =============================================================================
# LSIEngine checkpoint tests
# =============================================================================


class TestLSIEngineCheckpoint:
    def test_serialize_idle(self):
        broker = _mock_broker()
        engine = _make_lsi_engine(broker)
        data = serialize_lsi_engine(engine)
        assert data["engine_type"] == "lsi"
        assert data["state"] == "idle"

    def test_restore_armed_limit(self):
        broker = _mock_broker()
        engine = _make_lsi_engine(broker)

        # Manually set state to ARMED_LIMIT (legacy state, kept for checkpoint compat)
        engine._state = LSIState.ARMED_LIMIT
        engine._current_date = "20260302"
        engine._daily_atr = 300.0
        engine._entry_price = 19450.0
        engine._entry_direction = 1
        engine._entry_stop = 19430.0
        engine._active_sweep = SweepEvent("swing_low", 19420.0, 1, 12)
        engine._active_gap = GapInfo(19450.0, 19435.0, False, 19460.0, 19430.0, 16)

        data = serialize_lsi_engine(engine)
        new_engine = _make_lsi_engine(_mock_broker())
        result = restore_lsi_engine(new_engine, data)

        assert result is True
        assert new_engine._state == LSIState.ARMED_LIMIT
        assert new_engine._entry_price == 19450.0
        assert new_engine._active_sweep is not None
        assert new_engine._active_sweep.source == "swing_low"
        assert new_engine._active_gap is not None
        assert new_engine._active_gap.top == 19450.0

    def test_restore_managing(self):
        broker = _mock_broker()
        engine = _make_lsi_engine(broker)

        engine._state = LSIState.MANAGING
        engine._current_date = "20260302"
        engine._levels = _sample_trade_levels()
        engine._tp1_hit = True
        engine._tp1_bar_count = 20
        engine._fill_bar_count = 15
        engine._fill_timestamp = datetime(2026, 3, 2, 10, 15, tzinfo=ET)

        data = serialize_lsi_engine(engine)
        new_engine = _make_lsi_engine(_mock_broker())
        result = restore_lsi_engine(new_engine, data)

        assert result is True
        assert new_engine._state == LSIState.MANAGING
        assert new_engine._tp1_hit is True
        assert new_engine._levels.entry == 19540.0
        assert new_engine._fill_bar_count == 15

    def test_waiting_for_sweep_not_restored_outside_entry(self):
        """WAITING_FOR_SWEEP is downgraded to FLAT when entry window is closed."""
        from unittest.mock import patch
        broker = _mock_broker()
        engine = _make_lsi_engine(broker)
        engine._state = LSIState.WAITING_FOR_SWEEP

        data = serialize_lsi_engine(engine)
        new_engine = _make_lsi_engine(_mock_broker())
        # Mock time to be outside entry window (e.g. 23:00 ET)
        fake_now = datetime(2026, 3, 3, 23, 0, tzinfo=ET)
        with patch("trader.checkpoint.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            mock_dt.fromisoformat = datetime.fromisoformat
            result = restore_lsi_engine(new_engine, data)
        assert result is True  # restore succeeds (state is FLAT, not IDLE)
        assert new_engine._state == LSIState.FLAT


# =============================================================================
# Full checkpoint save/load/restore cycle
# =============================================================================


class TestCheckpointCycle:
    async def test_save_and_load(self, tmp_path):
        broker = _mock_broker()
        engine = _make_orb_engine(broker, name="NQ_NY")
        await advance_to_armed(engine)

        engines_by_config = {"DEFAULT": [engine]}
        ckpt_path = tmp_path / "checkpoint.json"
        save_checkpoint(engines_by_config, path=ckpt_path)

        data = load_checkpoint(ckpt_path)
        assert data is not None
        assert data["version"] == CHECKPOINT_VERSION
        assert "DEFAULT" in data["configs"]
        assert "NQ_NY" in data["configs"]["DEFAULT"]

    def test_load_missing_returns_none(self, tmp_path):
        result = load_checkpoint(tmp_path / "nonexistent.json")
        assert result is None

    def test_load_corrupt_returns_none(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{invalid json")
        result = load_checkpoint(p)
        assert result is None

    def test_load_wrong_version_returns_none(self, tmp_path):
        p = tmp_path / "old.json"
        p.write_text(json.dumps({"version": 999}))
        result = load_checkpoint(p)
        assert result is None

    async def test_stale_checkpoint_ignored(self, tmp_path):
        broker = _mock_broker()
        engine = _make_orb_engine(broker, name="NQ_NY")
        await advance_to_armed(engine)

        # Set checkpoint date to 5 days ago
        engine._current_date = (datetime.now(tz=ET) - timedelta(days=5)).strftime("%Y%m%d")

        engines_by_config = {"DEFAULT": [engine]}
        ckpt_path = tmp_path / "checkpoint.json"
        save_checkpoint(engines_by_config, path=ckpt_path)

        new_engine = _make_orb_engine(_mock_broker(), name="NQ_NY")
        new_configs = {"DEFAULT": [new_engine]}
        restored = restore_engines(new_configs, path=ckpt_path)
        assert restored == 0
        assert new_engine._state == State.IDLE

    async def test_today_checkpoint_restored(self, tmp_path):
        broker = _mock_broker()
        engine = _make_orb_engine(broker, name="NQ_NY")
        await advance_to_armed(engine)

        # Set checkpoint date to today
        engine._current_date = datetime.now(tz=ET).strftime("%Y%m%d")

        engines_by_config = {"DEFAULT": [engine]}
        ckpt_path = tmp_path / "checkpoint.json"
        save_checkpoint(engines_by_config, path=ckpt_path)

        new_engine = _make_orb_engine(_mock_broker(), name="NQ_NY")
        new_configs = {"DEFAULT": [new_engine]}
        restored = restore_engines(new_configs, path=ckpt_path)
        assert restored == 1
        assert new_engine._state == State.ARMED_LIMIT

    async def test_yesterday_checkpoint_restored(self, tmp_path):
        """Yesterday's checkpoint is valid (cross-midnight sessions)."""
        broker = _mock_broker()
        engine = _make_orb_engine(broker, name="NQ_Asia")
        await advance_to_armed(engine, date="2025-01-15")

        engine._current_date = (datetime.now(tz=ET) - timedelta(days=1)).strftime("%Y%m%d")

        engines_by_config = {"DEFAULT": [engine]}
        ckpt_path = tmp_path / "checkpoint.json"
        save_checkpoint(engines_by_config, path=ckpt_path)

        new_engine = _make_orb_engine(_mock_broker(), name="NQ_Asia")
        new_configs = {"DEFAULT": [new_engine]}
        restored = restore_engines(new_configs, path=ckpt_path)
        assert restored == 1

    async def test_mixed_engines(self, tmp_path):
        """ORB + LSI engines in the same config."""
        orb_broker = _mock_broker()
        orb_engine = _make_orb_engine(orb_broker, name="NQ_NY")
        await advance_to_armed(orb_engine)
        orb_engine._current_date = datetime.now(tz=ET).strftime("%Y%m%d")

        lsi_broker = _mock_broker()
        lsi_engine = _make_lsi_engine(lsi_broker, name="NQ_NY_LSI")
        lsi_engine._state = LSIState.MANAGING
        lsi_engine._current_date = datetime.now(tz=ET).strftime("%Y%m%d")
        lsi_engine._levels = _sample_trade_levels()
        lsi_engine._fill_bar_count = 10

        engines_by_config = {"DEFAULT": [orb_engine, lsi_engine]}
        ckpt_path = tmp_path / "checkpoint.json"
        save_checkpoint(engines_by_config, path=ckpt_path)

        new_orb = _make_orb_engine(_mock_broker(), name="NQ_NY")
        new_lsi = _make_lsi_engine(_mock_broker(), name="NQ_NY_LSI")
        new_configs = {"DEFAULT": [new_orb, new_lsi]}
        restored = restore_engines(new_configs, path=ckpt_path)
        assert restored == 2
        assert new_orb._state == State.ARMED_LIMIT
        assert new_lsi._state == LSIState.MANAGING


# =============================================================================
# Trade history persistence tests
# =============================================================================


class TestTradeHistory:
    def test_save_and_load_round_trip(self, tmp_path):
        recent_date_1 = (datetime.now(tz=ET) - timedelta(days=1)).strftime("%Y%m%d")
        recent_date_2 = datetime.now(tz=ET).strftime("%Y%m%d")
        trades = [
            TradeRecord(
                session="NQ_Asia", date=recent_date_1, direction=1,
                entry_price=19500.0, stop_price=19468.25,
                tp1_price=19545.0, tp2_price=19612.0,
                exit_type="tp1_be", tp1_hit=True,
                timestamp=f"{recent_date_1[:4]}-{recent_date_1[4:6]}-{recent_date_1[6:]}T04:15:23.456789",
                config_name="FAST",
            ),
            TradeRecord(
                session="NQ_NY", date=recent_date_2, direction=1,
                entry_price=19600.0, stop_price=19570.0,
                tp1_price=19660.0, tp2_price=19750.0,
                exit_type="sl", tp1_hit=False,
                timestamp=f"{recent_date_2[:4]}-{recent_date_2[4:6]}-{recent_date_2[6:]}T11:30:00",
                config_name="FAST",
            ),
        ]
        path = tmp_path / "trade_history.json"
        save_trade_history(trades, path=path)

        loaded = load_trade_history(path=path)
        assert len(loaded) == 2
        assert loaded[0].session == "NQ_Asia"
        assert loaded[0].tp1_hit is True
        assert loaded[1].exit_type == "sl"

    def test_retention_prunes_old_trades(self, tmp_path):
        old_date = (datetime.now(tz=ET) - timedelta(days=30)).strftime("%Y%m%d")
        recent_date = datetime.now(tz=ET).strftime("%Y%m%d")

        trades = [
            TradeRecord("NQ_Asia", old_date, 1, 19500, 19468, 19545, 19612,
                        "tp1_be", True, "2026-01-01T10:00:00", "FAST"),
            TradeRecord("NQ_NY", recent_date, 1, 19600, 19570, 19660, 19750,
                        "sl", False, "2026-03-02T10:00:00", "FAST"),
        ]
        path = tmp_path / "trade_history.json"
        save_trade_history(trades, path=path)

        loaded = load_trade_history(path=path)
        assert len(loaded) == 1
        assert loaded[0].date == recent_date

    def test_missing_file_returns_empty(self, tmp_path):
        loaded = load_trade_history(path=tmp_path / "missing.json")
        assert loaded == []

    def test_corrupt_file_returns_empty(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not json at all")
        loaded = load_trade_history(path=p)
        assert loaded == []

    def test_g5_gate_works_after_restore(self, tmp_path):
        """asia_tp1_hit_for_date() returns True after trade history restore."""
        from trader.api import DashboardState

        recent_date = datetime.now(tz=ET).strftime("%Y%m%d")
        trades = [
            TradeRecord(
                "NQ_Asia",
                recent_date,
                1,
                19500,
                19468,
                19545,
                19612,
                "tp1_be",
                True,
                f"{recent_date[:4]}-{recent_date[4:6]}-{recent_date[6:]}T04:15:00",
                "FAST",
            ),
        ]
        path = tmp_path / "trade_history.json"
        save_trade_history(trades, path=path)

        dashboard = DashboardState()
        dashboard.trade_history = load_trade_history(path=path)

        assert dashboard.asia_tp1_hit_for_date(recent_date, config_name="FAST") is True
        next_date = (datetime.now(tz=ET) + timedelta(days=1)).strftime("%Y%m%d")
        assert dashboard.asia_tp1_hit_for_date(next_date, config_name="FAST") is False


# =============================================================================
# Checkpoint callback integration
# =============================================================================


class TestCheckpointCallback:
    async def test_callback_fired_on_armed(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        checkpoint_count = 0

        def _on_checkpoint():
            nonlocal checkpoint_count
            checkpoint_count += 1

        engine.on_checkpoint = _on_checkpoint
        await advance_to_armed(engine)
        # Should fire at least for: ORB_BUILDING, WAITING_FOR_GAP, ARMED_LIMIT
        assert checkpoint_count >= 3

    async def test_callback_fired_on_managing(self):
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        checkpoint_count = 0

        def _on_checkpoint():
            nonlocal checkpoint_count
            checkpoint_count += 1

        engine.on_checkpoint = _on_checkpoint
        await advance_to_managing(engine)
        # Should fire for: ORB_BUILDING, WAITING_FOR_GAP, ARMED_LIMIT, MANAGING
        assert checkpoint_count >= 4

    def test_lsi_callback_wired(self):
        broker = _mock_broker()
        engine = _make_lsi_engine(broker)
        called = False

        def _on_checkpoint():
            nonlocal called
            called = True

        engine.on_checkpoint = _on_checkpoint
        engine._request_checkpoint()
        assert called is True

    def test_no_callback_no_error(self):
        """_request_checkpoint() is a no-op when callback is None."""
        broker = _mock_broker()
        engine = _make_orb_engine(broker)
        assert engine.on_checkpoint is None
        engine._request_checkpoint()  # should not raise
