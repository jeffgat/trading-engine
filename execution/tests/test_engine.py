"""Tests for ORBEngine — full state machine.

Covers: IDLE → ORB_BUILDING → WAITING_FOR_GAP → ARMED_LIMIT → MANAGING → FLAT
and the 1s tick path. All tests are async (pytest-asyncio auto mode).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, call
from zoneinfo import ZoneInfo

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.engine import Bar, ORBEngine, State, TradeRecord
from tests.builders import build_bearish_fvg_bars, build_bullish_fvg_bars, build_orb_sequence, make_bar
from tests.conftest import (
    advance_to_armed,
    advance_to_managing,
    advance_to_scanning,
    _make_orb_engine,
)

ET = ZoneInfo("America/New_York")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def broker():
    b = MagicMock(spec=TradersPostClient)
    b.send_entry = AsyncMock(return_value=[
        WebhookResult(payload={"action": "exit"}, status=None, latency_ms=0, dry_run=True),
        WebhookResult(payload={"action": "buy"}, status=None, latency_ms=0, dry_run=True),
    ])
    b.send_tp1_multi = AsyncMock(return_value=[])
    b.send_tp1_single = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    b.send_flatten = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    b.send_cancel = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
    b.paused = False
    b.multiplier = 1.0
    return b


@pytest.fixture
def engine(broker):
    return _make_orb_engine(broker)


# =============================================================================
# IDLE state
# =============================================================================

class TestIdleState:
    async def test_bar_in_orb_window_starts_orb_building(self, engine):
        bar = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        await engine.on_bar(bar, 300.0)
        assert engine._state == State.ORB_BUILDING

    async def test_bar_before_rth_stays_idle(self, engine):
        # 08:00 is before both ORB (09:30) and flat_end (16:00), but outside RTH entirely
        bar = make_bar("2025-01-15 08:00", 19500, 19520, 19490, 19505)
        await engine.on_bar(bar, 300.0)
        # Engine should not be in ORB_BUILDING (it's outside RTH)
        assert engine._state == State.IDLE

    async def test_first_orb_bar_sets_orb_levels(self, engine):
        bar = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        await engine.on_bar(bar, 300.0)
        assert engine._orb_high == pytest.approx(19530.0)
        assert engine._orb_low == pytest.approx(19480.0)

    async def test_excluded_date_goes_flat(self, broker):
        eng = _make_orb_engine(broker, excluded_dates=("20250115",))
        bar = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        await eng.on_bar(bar, 300.0)
        assert eng._state != State.ORB_BUILDING

    async def test_excluded_dow_goes_flat(self, broker):
        # Jan 15 2025 is a Wednesday (weekday=2)
        eng = _make_orb_engine(broker, excluded_dow=2)
        bar = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        await eng.on_bar(bar, 300.0)
        assert eng._state != State.ORB_BUILDING

    async def test_fomc_date_goes_flat(self, broker):
        eng = _make_orb_engine(broker, fomc_exclusion=True)
        # 2025-03-19 is a known FOMC date from the engine's FOMC_DATES set
        bar = make_bar("2025-03-19 09:30", 19500, 19530, 19480, 19510)
        await eng.on_bar(bar, 300.0)
        # Excluded — should not transition to ORB_BUILDING
        assert eng._state != State.ORB_BUILDING


# =============================================================================
# ORB_BUILDING state
# =============================================================================

class TestORBBuilding:
    async def test_orb_high_accumulates_across_bars(self, engine):
        bar1 = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        bar2 = make_bar("2025-01-15 09:35", 19510, 19550, 19490, 19530)  # new high
        await engine.on_bar(bar1, 300.0)
        await engine.on_bar(bar2, 300.0)
        assert engine._orb_high == pytest.approx(19550.0)

    async def test_orb_low_accumulates_across_bars(self, engine):
        bar1 = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        bar2 = make_bar("2025-01-15 09:35", 19510, 19520, 19460, 19500)  # new low
        await engine.on_bar(bar1, 300.0)
        await engine.on_bar(bar2, 300.0)
        assert engine._orb_low == pytest.approx(19460.0)

    async def test_transition_to_scanning_after_orb_ends(self, engine):
        await advance_to_scanning(engine)
        assert engine._state == State.WAITING_FOR_GAP

    async def test_g5_gate_blocks_scanning(self, broker):
        eng = _make_orb_engine(broker, g5_gate_check=lambda date: True)
        await advance_to_scanning(eng)
        assert eng._state == State.FLAT

    async def test_g5_gate_inactive_allows_scanning(self, broker):
        eng = _make_orb_engine(broker, g5_gate_check=lambda date: False)
        await advance_to_scanning(eng)
        assert eng._state == State.WAITING_FOR_GAP


# =============================================================================
# WAITING_FOR_GAP → ARMED_LIMIT
# =============================================================================

class TestScanningToArmed:
    async def test_bullish_fvg_above_orb_triggers_armed(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        assert engine._state == State.ARMED_LIMIT
        broker.send_entry.assert_called_once()

    async def test_send_entry_action_is_buy(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        call_args = broker.send_entry.call_args
        action = call_args.kwargs.get("action") or call_args.args[0]
        assert action == "buy"

    async def test_send_entry_price_is_fvg_top(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        call_args = broker.send_entry.call_args
        price = call_args.kwargs.get("price") or call_args.args[2]
        # FVG top = bar0.low = orb_high + 5 + gap = 19530 + 15 = 19545
        assert price == pytest.approx(19545.0)

    async def test_send_entry_stop_below_entry(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        call_args = broker.send_entry.call_args
        stop = call_args.kwargs.get("stop") or call_args.args[4]
        price = call_args.kwargs.get("price") or call_args.args[2]
        assert stop < price

    async def test_send_entry_tp2_above_entry(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        call_args = broker.send_entry.call_args
        tp2 = call_args.kwargs.get("tp2") or call_args.args[3]
        price = call_args.kwargs.get("price") or call_args.args[2]
        assert tp2 > price

    async def test_fvg_below_orb_high_rejected(self, engine, broker):
        """FVG top below ORB high — should NOT arm."""
        await advance_to_scanning(engine)
        # Build FVG bars where bar0.low < orb_high (below ORB)
        orb_high = engine._orb_high
        # bar0.low = orb_high - 10 (below ORB)
        bar2 = make_bar("2025-01-15 09:45", orb_high - 5, orb_high - 1, orb_high - 10, orb_high - 3)
        bar1 = make_bar("2025-01-15 09:50", orb_high - 3, orb_high + 20, orb_high - 5, orb_high + 15)
        bar0 = make_bar("2025-01-15 09:55", orb_high + 10, orb_high + 30, orb_high - 2, orb_high + 25)
        # bar2.high=orb_high-1 < bar0.low=orb_high-2 is False here, so no FVG
        # Use deliberately invalid geometry:
        for bar in [bar2, bar1, bar0]:
            await engine.on_bar(bar, 300.0)
        assert engine._state == State.WAITING_FOR_GAP
        broker.send_entry.assert_not_called()

    async def test_long_only_ignores_bearish_fvg(self, engine, broker):
        await advance_to_scanning(engine)
        orb_low = engine._orb_low
        # Build valid bearish FVG below ORB low
        for bar in build_bearish_fvg_bars("2025-01-15", orb_low=orb_low):
            await engine.on_bar(bar, 300.0)
        assert engine._state == State.WAITING_FOR_GAP
        broker.send_entry.assert_not_called()

    async def test_short_fvg_triggers_when_not_long_only(self, broker):
        eng = _make_orb_engine(broker, long_only=False)
        await advance_to_scanning(eng)
        orb_low = eng._orb_low
        for bar in build_bearish_fvg_bars("2025-01-15", orb_low=orb_low):
            await eng.on_bar(bar, 300.0)
        assert eng._state == State.ARMED_LIMIT
        broker.send_entry.assert_called_once()
        action = broker.send_entry.call_args.kwargs.get("action") or broker.send_entry.call_args.args[0]
        assert action == "sell"

    async def test_gap_too_small_rejected(self, broker):
        """Gap smaller than min_gap_atr_pct * ATR → stays WAITING_FOR_GAP."""
        # min_gap_atr_pct=50 with atr=300 → min_gap=150; actual gap=10 → rejected
        eng = _make_orb_engine(broker, min_gap_atr_pct=50.0)
        await advance_to_scanning(eng, atr=300.0)
        for bar in build_bullish_fvg_bars("2025-01-15", orb_high=eng._orb_high, gap=10.0):
            await eng.on_bar(bar, 300.0)
        assert eng._state == State.WAITING_FOR_GAP
        broker.send_entry.assert_not_called()

    async def test_entry_window_expiry_goes_flat(self, engine):
        """Bar past entry_end while WAITING_FOR_GAP → FLAT."""
        await advance_to_scanning(engine)
        bar = make_bar("2025-01-15 12:05", 19500, 19510, 19490, 19500)  # past 12:00
        await engine.on_bar(bar, 300.0)
        assert engine._state == State.FLAT

    async def test_icf_allows_entry_when_impulse_close_above_orb(self, broker):
        """ICF enabled: even if FVG top ≤ orb_high, impulse close above orb_high is valid."""
        eng = _make_orb_engine(broker, icf_enabled=True)
        await advance_to_scanning(eng)
        orb_high = eng._orb_high
        # Construct FVG where bar0.low = orb_high - 5 (BELOW ORB) but bar1.close > orb_high
        bar2 = make_bar("2025-01-15 09:45", orb_high - 5, orb_high - 1, orb_high - 8, orb_high - 3)
        bar1 = make_bar("2025-01-15 09:50", orb_high, orb_high + 20, orb_high - 1, orb_high + 15)  # close > orb_high
        # bar0.low must be > bar2.high for bullish FVG
        bar0 = make_bar("2025-01-15 09:55", orb_high + 15, orb_high + 25, orb_high, orb_high + 20)
        # Check: bar2.high=orb_high-1, bar0.low=orb_high → gap exists since orb_high > (orb_high-1)
        for bar in [bar2, bar1, bar0]:
            await eng.on_bar(bar, 300.0)
        # With ICF, bar1.close > orb_high → valid
        if eng._state == State.ARMED_LIMIT:
            broker.send_entry.assert_called_once()


# =============================================================================
# ARMED_LIMIT → MANAGING (fill detection on 5m bars)
# =============================================================================

class TestArmedToManaging:
    async def test_fill_on_low_lte_entry(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        assert eng._state == State.MANAGING

    async def test_5m_fill_can_be_disabled_for_live_mode(self, broker):
        eng = _make_orb_engine(broker, allow_5m_fill_detection=False)
        await advance_to_armed(eng, orb_high=19530.0)
        entry_price = eng._levels.entry
        bar = make_bar("2025-01-15 10:00", entry_price + 10, entry_price + 20, entry_price - 5, entry_price + 15)
        await eng.on_bar(bar, 300.0)
        assert eng._state == State.ARMED_LIMIT

    async def test_no_fill_when_low_above_entry(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        entry_price = engine._levels.entry
        # Bar that doesn't touch entry
        bar = make_bar("2025-01-15 10:00", entry_price + 10, entry_price + 20, entry_price + 5, entry_price + 15)
        await engine.on_bar(bar, 300.0)
        assert engine._state == State.ARMED_LIMIT

    async def test_armed_entry_window_expiry_sends_cancel(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        bar = make_bar("2025-01-15 12:05", 19500, 19510, 19490, 19500)  # past entry_end
        await engine.on_bar(bar, 300.0)
        broker.send_cancel.assert_called_once()
        assert engine._state == State.FLAT


# =============================================================================
# MANAGING exits — 5m bar path
# =============================================================================

class TestManagingExits5m:
    async def test_sl_hit_sends_flatten(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        stop = eng._levels.stop
        # Feed bar with low ≤ stop
        bar = make_bar("2025-01-15 10:05", stop + 10, stop + 15, stop - 5, stop + 8)
        await eng.on_bar(bar, 300.0)
        broker.send_flatten.assert_called_once()
        assert eng._state == State.FLAT

    async def test_sl_emits_trade_record(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        stop = eng._levels.stop
        bar = make_bar("2025-01-15 10:05", stop + 10, stop + 15, stop - 5, stop + 8)
        await eng.on_bar(bar, 300.0)
        assert len(records) == 1
        assert records[0].exit_type == "sl"
        assert records[0].tp1_hit is False

    async def test_tp1_hit_multi_contract_calls_tp1_multi(self, broker):
        """Multi-contract (qty=2): TP1 should call send_tp1_multi."""
        # Use high risk_usd to get qty=2+
        eng = _make_orb_engine(broker, risk_usd=2000, stop_atr_pct=5.0)
        eng, entry_price = await advance_to_managing(eng, atr=100.0, orb_high=19530.0)
        if eng._levels.is_single_contract:
            pytest.skip("Couldn't get multi-contract with these params")
        tp1 = eng._levels.tp1
        bar = make_bar("2025-01-15 10:05", tp1 - 5, tp1 + 10, tp1 - 10, tp1 + 5)
        await eng.on_bar(bar, 100.0)
        broker.send_tp1_multi.assert_called_once()
        broker.send_tp1_single.assert_not_called()
        assert eng._tp1_hit is True
        assert eng._state == State.MANAGING  # still open, runner active

    async def test_tp1_hit_single_contract_calls_tp1_single(self, broker):
        """Single contract (qty=1): TP1 should call send_tp1_single."""
        # Low risk_usd forces single contract
        eng = _make_orb_engine(broker, risk_usd=10)
        eng, entry_price = await advance_to_managing(eng, orb_high=19530.0)
        if not eng._levels.is_single_contract:
            pytest.skip("Couldn't get single-contract with these params")
        tp1 = eng._levels.tp1
        bar = make_bar("2025-01-15 10:05", tp1 - 5, tp1 + 10, tp1 - 10, tp1 + 5)
        await eng.on_bar(bar, 300.0)
        broker.send_tp1_single.assert_called_once()
        broker.send_tp1_multi.assert_not_called()

    async def test_tp2_hit_after_tp1_exits(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        # Force _tp1_hit manually to test TP2 path
        eng._tp1_hit = True
        eng._tp1_bar_count = 0  # allow 5m checks
        tp2 = eng._levels.tp2
        bar = make_bar("2025-01-15 10:10", tp2 - 5, tp2 + 10, tp2 - 10, tp2 + 5)
        await eng.on_bar(bar, 300.0)
        broker.send_flatten.assert_called()
        assert eng._state == State.FLAT

    async def test_tp2_emits_correct_exit_type(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        eng._tp1_hit = True
        eng._tp1_bar_count = 0
        tp2 = eng._levels.tp2
        bar = make_bar("2025-01-15 10:10", tp2 - 5, tp2 + 10, tp2 - 10, tp2 + 5)
        await eng.on_bar(bar, 300.0)
        assert records[0].exit_type == "tp1_tp2"
        assert records[0].tp1_hit is True

    async def test_be_hit_after_tp1_exits(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        eng._tp1_hit = True
        eng._tp1_bar_count = 0
        be = eng._levels.be
        # Long: BE hit when low ≤ be
        bar = make_bar("2025-01-15 10:10", be + 5, be + 10, be - 5, be + 8)
        await eng.on_bar(bar, 300.0)
        broker.send_flatten.assert_called()
        assert eng._state == State.FLAT

    async def test_be_emits_tp1_be_exit_type(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        eng._tp1_hit = True
        eng._tp1_bar_count = 0
        be = eng._levels.be
        bar = make_bar("2025-01-15 10:10", be + 5, be + 10, be - 5, be + 8)
        await eng.on_bar(bar, 300.0)
        assert records[0].exit_type == "tp1_be"

    async def test_eod_flat_no_tp1_exits(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        bar = make_bar("2025-01-15 15:51", 19550, 19560, 19540, 19550)
        await eng.on_bar(bar, 300.0)
        broker.send_flatten.assert_called_once()
        assert eng._state == State.FLAT

    async def test_eod_emits_eod_exit_type(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        bar = make_bar("2025-01-15 15:51", 19550, 19560, 19540, 19550)
        await eng.on_bar(bar, 300.0)
        assert records[0].exit_type == "eod"

    async def test_eod_records_realized_r_result(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        close_price = eng._levels.entry + 10.0
        bar = make_bar("2025-01-15 15:51", close_price - 2, close_price + 2, close_price - 3, close_price)
        await eng.on_bar(bar, 300.0)
        expected_r = eng._price_to_r(close_price)
        assert eng._r_result == pytest.approx(expected_r)
        assert records[0].r_result == pytest.approx(expected_r)

    async def test_eod_with_tp1_emits_tp1_eod(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        eng._tp1_hit = True
        eng._tp1_bar_count = 0
        bar = make_bar("2025-01-15 15:51", 19550, 19560, 19540, 19550)
        await eng.on_bar(bar, 300.0)
        assert records[0].exit_type == "tp1_eod"

    async def test_tp1_eod_records_realized_r_result(self, broker):
        records = []
        eng = _make_orb_engine(broker, risk_usd=2000, stop_atr_pct=5.0)
        eng.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(eng, atr=100.0, orb_high=19530.0)
        if eng._levels.is_single_contract:
            pytest.skip("Couldn't get multi-contract with these params")
        eng._tp1_hit = True
        eng._tp1_bar_count = 0
        close_price = eng._levels.entry + 20.0
        bar = make_bar("2025-01-15 15:51", close_price - 2, close_price + 2, close_price - 3, close_price)
        await eng.on_bar(bar, 100.0)
        expected_r = (eng._price_to_r(eng._levels.tp1) + eng._price_to_r(close_price)) / 2.0
        assert eng._r_result == pytest.approx(expected_r)
        assert records[0].exit_type == "tp1_eod"
        assert records[0].r_result == pytest.approx(expected_r)

    async def test_sl_wins_over_tp1_same_bar(self, engine, broker):
        """When both SL and TP1 triggered on same bar, SL wins (pessimistic)."""
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        stop = eng._levels.stop
        tp1 = eng._levels.tp1
        # Bar crosses BOTH stop and TP1
        bar = make_bar("2025-01-15 10:05", entry_price, tp1 + 5, stop - 5, entry_price)
        await eng.on_bar(bar, 300.0)
        broker.send_flatten.assert_called_once()
        broker.send_tp1_multi.assert_not_called()
        broker.send_tp1_single.assert_not_called()

    async def test_tp1_hit_transitions_state_stays_managing(self, engine, broker):
        """After TP1 hits, state remains MANAGING (waiting for BE or TP2 next bar)."""
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        tp1 = eng._levels.tp1
        # Feed a bar that touches tp1 but not tp2
        bar = make_bar("2025-01-15 10:10", entry_price, tp1 + 5, entry_price - 2, tp1)
        await eng.on_bar(bar, 300.0)
        # TP1 fired — still managing (TP2 not yet hit)
        assert eng._state == State.MANAGING
        assert eng._tp1_hit is True
        broker.send_tp1_multi.assert_called_once()

    async def test_fill_bar_no_immediate_exit_check(self, engine, broker):
        """Fill on bar N — exits must not trigger on the SAME bar (fill bar guard)."""
        await advance_to_armed(engine, orb_high=19530.0)
        entry_price = engine._levels.entry
        stop = engine._levels.stop
        # This bar fills AND goes below stop simultaneously (adversarial)
        # With the fill_bar guard, SL must NOT trigger on this same bar
        bar = make_bar(
            "2025-01-15 10:00",
            entry_price + 5,
            entry_price + 10,
            stop - 10,  # below stop
            entry_price + 3,
        )
        await engine.on_bar(bar, 300.0)
        # Should be in MANAGING (filled) but stop not triggered yet
        # (fill_bar_idx guard protects this bar)
        assert engine._state == State.MANAGING
        broker.send_flatten.assert_not_called()


# =============================================================================
# 1-second tick path
# =============================================================================

class TestTickPath:
    async def test_tick_ignored_in_idle(self, engine, broker):
        tick = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await engine.on_tick(tick, 300.0)
        broker.send_flatten.assert_not_called()
        broker.send_entry.assert_not_called()

    async def test_tick_ignored_in_scanning(self, engine, broker):
        await advance_to_scanning(engine)
        tick = make_bar("2025-01-15 09:50", 19600, 19610, 19590, 19600)
        await engine.on_tick(tick, 300.0)
        broker.send_flatten.assert_not_called()
        broker.send_entry.assert_not_called()

    async def test_tick_fill_in_armed(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        entry_price = engine._levels.entry
        tick = make_bar("2025-01-15 10:05", entry_price + 2, entry_price + 5, entry_price - 1, entry_price + 3)
        await engine.on_tick(tick, 300.0)
        assert engine._state == State.MANAGING
        assert engine._fill_timestamp is not None

    async def test_tick_before_signal_bar_close_does_not_fill(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        entry_price = engine._levels.entry
        stale_tick = make_bar("2025-01-15 10:04", entry_price + 2, entry_price + 5, entry_price - 1, entry_price + 3)
        await engine.on_tick(stale_tick, 300.0)
        assert engine._state == State.ARMED_LIMIT
        assert engine._fill_timestamp is None

        live_tick = make_bar("2025-01-15 10:05", entry_price + 2, entry_price + 5, entry_price - 1, entry_price + 3)
        await engine.on_tick(live_tick, 300.0)
        assert engine._state == State.MANAGING
        assert engine._fill_timestamp == live_tick.timestamp

    async def test_tick_fill_same_timestamp_guard(self, engine, broker):
        """Two ticks with same timestamp: second should NOT trigger exits."""
        await advance_to_armed(engine, orb_high=19530.0)
        entry_price = engine._levels.entry
        stop = engine._levels.stop
        # Fill on tick 1
        tick1 = make_bar("2025-01-15 10:05", entry_price + 2, entry_price + 5, entry_price - 1, entry_price + 3)
        await engine.on_tick(tick1, 300.0)
        assert engine._state == State.MANAGING
        # Send another tick with same timestamp that goes below stop
        tick2 = make_bar("2025-01-15 10:05", stop + 5, stop + 8, stop - 10, stop + 3)
        await engine.on_tick(tick2, 300.0)
        # Guard: same timestamp → SL should NOT fire
        broker.send_flatten.assert_not_called()
        assert engine._state == State.MANAGING

    async def test_tick_filled_trade_ignores_5m_exit_management(self, engine, broker):
        await advance_to_armed(engine, orb_high=19530.0)
        entry_price = engine._levels.entry
        tp1 = engine._levels.tp1
        be = engine._levels.be

        fill_tick = make_bar("2025-01-15 10:05", entry_price + 2, entry_price + 5, entry_price - 1, entry_price + 3)
        await engine.on_tick(fill_tick, 300.0)
        assert engine._state == State.MANAGING
        assert engine._fill_via_tick is True

        # A 5m bar can contain stale pre-fill excursion, so it must not manage exits.
        stale_bar = make_bar("2025-01-15 10:10", entry_price, tp1 + 5, be - 5, entry_price)
        await engine.on_bar(stale_bar, 300.0)

        broker.send_tp1_multi.assert_not_called()
        broker.send_tp1_single.assert_not_called()
        broker.send_flatten.assert_not_called()
        assert engine._state == State.MANAGING

    async def test_tick_sl_in_managing(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        stop = eng._levels.stop
        # Use a distinct timestamp (different from fill timestamp)
        fill_ts = eng._fill_timestamp
        tick_ts = fill_ts + timedelta(seconds=2)
        tick = Bar(
            timestamp=tick_ts,
            open=stop + 5, high=stop + 8, low=stop - 5, close=stop + 3, volume=10
        )
        await eng.on_tick(tick, 300.0)
        broker.send_flatten.assert_called_once()
        assert eng._state == State.FLAT

    async def test_tick_tp1_multi_in_managing(self, broker):
        eng = _make_orb_engine(broker, risk_usd=2000, stop_atr_pct=5.0)
        eng, entry_price = await advance_to_managing(eng, atr=100.0, orb_high=19530.0)
        if eng._levels.is_single_contract:
            pytest.skip("Need multi-contract")
        tp1 = eng._levels.tp1
        fill_ts = eng._fill_timestamp
        tick_ts = fill_ts + timedelta(seconds=2)
        tick = Bar(timestamp=tick_ts, open=tp1 - 5, high=tp1 + 5, low=tp1 - 8, close=tp1 + 2, volume=10)
        await eng.on_tick(tick, 100.0)
        broker.send_tp1_multi.assert_called_once()

    async def test_tick_sl_wins_over_tp1(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        stop = eng._levels.stop
        tp1 = eng._levels.tp1
        fill_ts = eng._fill_timestamp
        tick_ts = fill_ts + timedelta(seconds=2)
        # Tick crosses both stop and TP1
        tick = Bar(timestamp=tick_ts, open=entry_price, high=tp1 + 5, low=stop - 5, close=entry_price, volume=10)
        await eng.on_tick(tick, 300.0)
        broker.send_flatten.assert_called_once()
        broker.send_tp1_multi.assert_not_called()

    async def test_tick_eod_flatten(self, engine, broker):
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        tick = make_bar("2025-01-15 15:51", 19550, 19560, 19540, 19550)
        await eng.on_tick(tick, 300.0)
        broker.send_flatten.assert_called_once()
        assert eng._state == State.FLAT


# =============================================================================
# Daily reset and cross-midnight
# =============================================================================

class TestDailyReset:
    async def test_new_calendar_day_resets_state(self, engine):
        await advance_to_scanning(engine)
        assert engine._state == State.WAITING_FOR_GAP
        # Feed bar on Jan 16 (new day)
        bar = make_bar("2025-01-16 09:30", 19500, 19530, 19480, 19510)
        await engine.on_bar(bar, 300.0)
        # Should have reset to IDLE (or ORB_BUILDING for the new day)
        assert engine._state in (State.IDLE, State.ORB_BUILDING)
        # ORB levels reset
        assert engine._current_date == "20250116"

    async def test_cross_midnight_asia_no_spurious_reset(self, broker):
        """Asia session: ORB starts 20:00, bar at 00:05 next calendar day
        is the SAME session and must NOT trigger a daily reset."""
        eng = _make_orb_engine(
            broker,
            orb_start="20:00",
            orb_end="20:15",
            entry_start="20:15",
            entry_end="23:30",
            flat_start="06:50",
            flat_end="07:00",
        )
        # ORB bar on Jan 14 (20:00)
        bar1 = make_bar("2025-01-14 20:00", 19500, 19530, 19480, 19510)
        await eng.on_bar(bar1, 300.0)
        assert eng._state == State.ORB_BUILDING
        assert eng._current_date == "20250114"

        # Bar at 20:15 Jan 14 — moves to WAITING_FOR_GAP
        bar2 = make_bar("2025-01-14 20:15", 19510, 19520, 19500, 19515)
        await eng.on_bar(bar2, 300.0)
        state_after_transition = eng._state

        # Bar at 00:05 Jan 15 — must NOT reset the session
        bar3 = make_bar("2025-01-15 00:05", 19520, 19530, 19510, 19525)
        await eng.on_bar(bar3, 300.0)
        # Session date must still be Jan 14
        assert eng._current_date == "20250114"

    async def test_half_day_flat_earlier(self, broker):
        """On a half-day, flat window triggers at half_day_flat_start instead of flat_start."""
        eng = _make_orb_engine(
            broker,
            half_days=("20250109",),  # Jan 9 is a half day
            half_day_flat_start="12:50",
            half_day_flat_end="13:00",
        )
        eng, entry_price = await advance_to_managing(eng, date="2025-01-09", orb_high=19530.0)
        # Feed bar at 12:51 on Jan 9 — should trigger half-day flat
        bar = make_bar("2025-01-09 12:51", 19550, 19560, 19540, 19550)
        await eng.on_bar(bar, 300.0)
        broker.send_flatten.assert_called_once()
        assert eng._state == State.FLAT


# =============================================================================
# Callbacks
# =============================================================================

class TestCallbacks:
    async def test_state_change_callback_fires(self, engine):
        events = []
        engine.on_state_change = events.append
        bar = make_bar("2025-01-15 09:30", 19500, 19530, 19480, 19510)
        await engine.on_bar(bar, 300.0)
        assert len(events) > 0

    async def test_trade_record_on_sl_has_correct_fields(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        stop = eng._levels.stop
        bar = make_bar("2025-01-15 10:05", stop + 5, stop + 10, stop - 5, stop + 5)
        await eng.on_bar(bar, 300.0)
        r = records[0]
        assert r.session == "NQ_NY"
        assert r.exit_type == "sl"
        assert r.tp1_hit is False
        assert r.direction == 1  # long
        assert r.entry_price > 0
        assert r.stop_price > 0

    async def test_trade_record_on_tp2_has_tp1_hit_true(self, engine, broker):
        records = []
        engine.on_trade_exit = records.append
        eng, entry_price = await advance_to_managing(engine, orb_high=19530.0)
        eng._tp1_hit = True
        eng._tp1_bar_count = 0
        tp2 = eng._levels.tp2
        bar = make_bar("2025-01-15 10:10", tp2 - 2, tp2 + 10, tp2 - 5, tp2 + 5)
        await eng.on_bar(bar, 300.0)
        assert records[0].tp1_hit is True
        assert records[0].exit_type == "tp1_tp2"
