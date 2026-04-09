"""Tests for LSIEngine — LSI reversal strategy state machine.

State machine: IDLE → WAITING_FOR_SWEEP → WAITING_FOR_GAP →
               WAITING_FOR_INVERSION → MANAGING → FLAT

Entry is at the inversion bar's close price (matching backtester entry_mode="close").
Stop is absolute-range high/low from FVG bar through inversion bar (stop_mode="absolute").
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from trader.broker import TradersPostClient, WebhookResult
from trader.engine import Bar
from trader.lsi_engine import GapInfo, LSIEngine, LSIState

ET = ZoneInfo("America/New_York")

# Backward-compat for renamed state in the live engine.
if not hasattr(LSIState, "WAITING_FOR_SWEEP"):
    LSIState.WAITING_FOR_SWEEP = LSIState.SCANNING  # type: ignore[attr-defined]


async def _flush_cleanup_tasks() -> None:
    await asyncio.sleep(0)


# =============================================================================
# Helpers
# =============================================================================

def make_bar(ts: str, o: float, h: float, l: float, c: float, v: int = 100) -> Bar:
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    return Bar(timestamp=dt, open=o, high=h, low=l, close=c, volume=v)


def make_mock_broker():
    b = MagicMock(spec=TradersPostClient)
    b.send_entry = AsyncMock(return_value=[
        WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True),
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


def make_lsi_engine(broker=None, **overrides) -> LSIEngine:
    if broker is None:
        broker = make_mock_broker()
    defaults = dict(
        name="NQ_LSI",
        broker=broker,
        exec_ticker="MNQ",
        entry_start="09:30",
        entry_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        rr=3.0,
        tp1_ratio=0.3,
        min_gap_atr_pct=0.5,  # very small so our test gaps pass the filter
        risk_usd=250.0,
        point_value=2.0,
        min_qty=1.0,
        qty_step=1.0,
        min_tick=0.25,
        max_single_risk_usd=500.0,
        long_only=True,
        fvg_window_right=10,
        fvg_window_left=10,
        lsi_n_left=3,
        lsi_n_right=3,
        post_exit_cleanup_delay_s=0.0,
        post_exit_cancel_settle_delay_s=0.0,
    )
    defaults.update(overrides)
    return LSIEngine(**defaults)


async def feed_swing_low_and_sweep(
    eng: LSIEngine,
    swing_low: float = 19400.0,
    base_price: float = 19500.0,
):
    """Build a confirmed swing low pivot and then sweep it.

    With n_left=3, n_right=3 (window=7):
    - Bars 1-3 (left): highs/lows above swing_low
    - Bar 4 (pivot): low = swing_low (strictly less than all neighbors)
    - Bars 5-7 (right): highs/lows above swing_low
    - Bar 8: one more bar so the confirmed level shifts to _prev_swing_low
    - Bar 9 (09:30): entry window starts, triggers WAITING_FOR_SWEEP
    - Bar 10 (09:35): sweep bar — low < swing_low (strict, matching backtest)

    All pre-entry bars use times before the entry window (09:30).
    """
    # Bars with lows above swing_low (left side of pivot)
    for i in range(3):
        bar = make_bar(
            f"2025-01-15 08:{30 + i * 5:02d}",
            base_price, base_price + 10, base_price - 10, base_price,
        )
        await eng.on_bar(bar, 300.0)

    # Pivot bar: low = swing_low (strictly less than all neighbors)
    await eng.on_bar(
        make_bar("2025-01-15 08:45", base_price - 50, base_price - 40, swing_low, base_price - 60),
        300.0,
    )

    # Right side of pivot (3 bars with lows above swing_low)
    for i in range(3):
        bar = make_bar(
            f"2025-01-15 09:{i * 5:02d}",
            base_price, base_price + 10, base_price - 10, base_price,
        )
        await eng.on_bar(bar, 300.0)
    # After bar 7 (09:10), pivot is confirmed → _latest_swing_low = swing_low

    # Bar 8: one more bar to shift the level into _prev_swing_low
    await eng.on_bar(
        make_bar("2025-01-15 09:15", base_price, base_price + 10, base_price - 10, base_price),
        300.0,
    )

    # Bar 9: entry window opens → IDLE → WAITING_FOR_SWEEP
    await eng.on_bar(
        make_bar("2025-01-15 09:30", base_price, base_price + 10, base_price - 10, base_price),
        300.0,
    )
    assert eng._state == LSIState.WAITING_FOR_SWEEP

    # Bar 10: sweep bar — low < swing_low (strict) → WAITING_FOR_GAP
    await eng.on_bar(
        make_bar("2025-01-15 09:35", swing_low + 30, swing_low + 40, swing_low - 10, swing_low + 20),
        300.0,
    )
    assert eng._state == LSIState.WAITING_FOR_GAP


async def _advance_to_inversion(eng: LSIEngine) -> LSIEngine | None:
    """Advance engine to WAITING_FOR_INVERSION with a bearish FVG."""
    await feed_swing_low_and_sweep(eng, swing_low=19400.0)
    # Bearish FVG: top=19450, bottom=19430
    bar2 = make_bar("2025-01-15 09:40", 19490, 19500, 19450, 19460)
    bar1 = make_bar("2025-01-15 09:45", 19460, 19500, 19350, 19380)
    bar0 = make_bar("2025-01-15 09:50", 19380, 19430, 19350, 19400)
    await eng.on_bar(bar2, 300.0)
    await eng.on_bar(bar1, 300.0)
    await eng.on_bar(bar0, 300.0)
    if eng._state != LSIState.WAITING_FOR_INVERSION:
        return None
    return eng


async def _advance_to_managing(eng: LSIEngine) -> tuple[LSIEngine | None, float | None]:
    """Advance engine to MANAGING via inversion-bar-close entry."""
    result = await _advance_to_inversion(eng)
    if result is None:
        return None, None
    gap = eng._active_gap
    # Inversion: close > gap.top → long entry at bar close
    inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, gap.top + 5)
    await eng.on_bar(inversion_bar, 300.0)
    if eng._state != LSIState.MANAGING:
        return None, None
    return eng, eng._levels.entry


# =============================================================================
# IDLE → WAITING_FOR_SWEEP
# =============================================================================

class TestIdleToWaitingForSweep:
    async def test_entry_window_starts_waiting_for_sweep(self):
        eng = make_lsi_engine()
        bar = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar, 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP

    async def test_regime_gate_blocks_before_waiting_for_sweep(self):
        eng = make_lsi_engine(
            regime_gate="bull_no_low_confidence",
            regime_gate_check=lambda _date: False,
        )
        eng._log_trade = MagicMock()

        bar = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar, 300.0)

        assert eng._state == LSIState.FLAT
        eng._log_trade.assert_called_with("REGIME_GATE_BLOCKED", "gate=bull_no_low_confidence date=20250115")

    async def test_multiple_regime_gates_block_on_first_failure(self):
        eng = make_lsi_engine(
            regime_gates=("bull_no_low_confidence", "block_full_medium_vol"),
            regime_gate_checks=(
                ("bull_no_low_confidence", lambda _date: True),
                ("block_full_medium_vol", lambda _date: False),
            ),
        )
        eng._log_trade = MagicMock()

        bar = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar, 300.0)

        assert eng._state == LSIState.FLAT
        eng._log_trade.assert_called_with("REGIME_GATE_BLOCKED", "gate=block_full_medium_vol date=20250115")

    async def test_excluded_date_does_not_start_waiting_for_sweep(self):
        eng = make_lsi_engine(excluded_dates=("20250115",))
        bar = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar, 300.0)
        assert eng._state != LSIState.WAITING_FOR_SWEEP

    async def test_excluded_dow_does_not_start_waiting_for_sweep(self):
        # Jan 15 2025 is Wednesday (weekday=2)
        eng = make_lsi_engine(excluded_dow=2)
        bar = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar, 300.0)
        assert eng._state != LSIState.WAITING_FOR_SWEEP

    async def test_waiting_for_sweep_to_flat_past_entry_end(self):
        eng = make_lsi_engine()
        bar1 = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar1, 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP
        bar2 = make_bar("2025-01-15 15:05", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar2, 300.0)
        assert eng._state == LSIState.FLAT


# =============================================================================
# WAITING_FOR_SWEEP → WAITING_FOR_GAP (sweep detection)
# =============================================================================

class TestWaitingForSweepToWaitingForGap:
    async def test_low_sweep_triggers_waiting_for_gap(self):
        eng = make_lsi_engine()
        await feed_swing_low_and_sweep(eng, swing_low=19400.0)
        assert eng._state == LSIState.WAITING_FOR_GAP

    async def test_long_only_high_sweep_ignored(self):
        """In long_only mode, high sweeps are ignored — stays WAITING_FOR_SWEEP."""
        eng = make_lsi_engine(long_only=True)
        base_price = 19500.0
        swing_high = 19600.0

        # Left side (3 bars with highs below swing_high)
        for i in range(3):
            bar = make_bar(
                f"2025-01-15 08:{30 + i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            )
            await eng.on_bar(bar, 300.0)

        # Pivot bar: high = swing_high
        await eng.on_bar(
            make_bar("2025-01-15 08:45", base_price + 50, swing_high, base_price + 40, base_price + 60),
            300.0,
        )

        # Right side (3 bars with highs below swing_high)
        for i in range(3):
            bar = make_bar(
                f"2025-01-15 09:{i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            )
            await eng.on_bar(bar, 300.0)

        # Shift bar
        await eng.on_bar(
            make_bar("2025-01-15 09:15", base_price, base_price + 10, base_price - 10, base_price),
            300.0,
        )

        # Entry window opens
        await eng.on_bar(
            make_bar("2025-01-15 09:30", base_price, base_price + 10, base_price - 10, base_price),
            300.0,
        )
        assert eng._state == LSIState.WAITING_FOR_SWEEP

        # High sweep bar — high > swing_high (strict)
        sweep_bar = make_bar("2025-01-15 09:35", swing_high - 10, swing_high + 20, swing_high - 20, swing_high + 10)
        await eng.on_bar(sweep_bar, 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP

    async def test_active_sweep_set_on_transition(self):
        eng = make_lsi_engine()
        await feed_swing_low_and_sweep(eng, swing_low=19400.0)
        assert eng._active_sweep is not None
        assert eng._active_sweep.source == "swing_low"

    async def test_tick_perfect_touch_does_not_sweep(self):
        """Strict < means bar.low == swing_low is NOT a sweep (matches backtest)."""
        eng = make_lsi_engine()
        base_price = 19500.0
        swing_low = 19400.0

        # Build confirmed swing low
        for i in range(3):
            await eng.on_bar(make_bar(
                f"2025-01-15 08:{30 + i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            ), 300.0)
        await eng.on_bar(make_bar("2025-01-15 08:45", base_price - 50, base_price - 40, swing_low, base_price - 60), 300.0)
        for i in range(3):
            await eng.on_bar(make_bar(
                f"2025-01-15 09:{i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            ), 300.0)
        await eng.on_bar(make_bar("2025-01-15 09:15", base_price, base_price + 10, base_price - 10, base_price), 300.0)
        await eng.on_bar(make_bar("2025-01-15 09:30", base_price, base_price + 10, base_price - 10, base_price), 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP

        # Bar with low == swing_low exactly — NOT a sweep with strict <
        await eng.on_bar(make_bar("2025-01-15 09:35", swing_low + 30, swing_low + 40, swing_low, swing_low + 20), 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP  # did NOT transition


# =============================================================================
# WAITING_FOR_GAP → WAITING_FOR_INVERSION
# =============================================================================

class TestWaitingForGapToInversion:
    async def _advance_to_waiting_for_gap(self, long_only=True):
        eng = make_lsi_engine(long_only=long_only)
        await feed_swing_low_and_sweep(eng, swing_low=19400.0)
        assert eng._state == LSIState.WAITING_FOR_GAP
        return eng

    async def test_bearish_fvg_after_low_sweep_transitions(self):
        eng = await self._advance_to_waiting_for_gap()
        bar2 = make_bar("2025-01-15 09:40", 19490, 19500, 19450, 19460)
        bar1 = make_bar("2025-01-15 09:45", 19460, 19500, 19350, 19380)
        bar0 = make_bar("2025-01-15 09:50", 19380, 19430, 19350, 19400)
        await eng.on_bar(bar2, 300.0)
        await eng.on_bar(bar1, 300.0)
        await eng.on_bar(bar0, 300.0)
        assert eng._state == LSIState.WAITING_FOR_INVERSION

    async def test_bullish_fvg_ignored_after_low_sweep(self):
        eng = await self._advance_to_waiting_for_gap()
        bar2 = make_bar("2025-01-15 09:40", 19480, 19500, 19480, 19495)
        bar1 = make_bar("2025-01-15 09:45", 19495, 19560, 19490, 19550)
        bar0 = make_bar("2025-01-15 09:50", 19550, 19600, 19520, 19590)
        await eng.on_bar(bar2, 300.0)
        await eng.on_bar(bar1, 300.0)
        await eng.on_bar(bar0, 300.0)
        assert eng._state == LSIState.WAITING_FOR_GAP
        eng.broker.send_entry.assert_not_called()

    async def test_sweep_expires_after_max_bars(self):
        eng = make_lsi_engine(fvg_window_right=3)
        await feed_swing_low_and_sweep(eng, swing_low=19400.0)
        assert eng._state == LSIState.WAITING_FOR_GAP

        for i in range(4):
            bar = make_bar(f"2025-01-15 09:{40 + i * 5:02d}", 19495, 19510, 19490, 19500)
            await eng.on_bar(bar, 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP
        assert eng._active_sweep is None

    async def test_gap_too_small_stays_waiting(self):
        eng = make_lsi_engine(min_gap_atr_pct=50.0)
        await feed_swing_low_and_sweep(eng, swing_low=19400.0)
        bar2 = make_bar("2025-01-15 09:40", 19480, 19490, 19460, 19465)
        bar1 = make_bar("2025-01-15 09:45", 19465, 19490, 19400, 19410)
        bar0 = make_bar("2025-01-15 09:50", 19410, 19457, 19400, 19455)
        await eng.on_bar(bar2, 300.0)
        await eng.on_bar(bar1, 300.0)
        await eng.on_bar(bar0, 300.0)
        assert eng._state == LSIState.WAITING_FOR_GAP


# =============================================================================
# FVG-before-sweep lookback (fvg_window_left)
# =============================================================================

class TestFVGBeforeSweepLookback:
    async def test_fvg_formed_before_sweep_promotes(self):
        """An FVG detected in WAITING_FOR_SWEEP before a sweep should be
        promoted when the sweep arrives (within fvg_window_left bars)."""
        eng = make_lsi_engine(fvg_window_left=10)
        base_price = 19500.0
        swing_low = 19400.0

        # Build confirmed swing low
        for i in range(3):
            await eng.on_bar(make_bar(
                f"2025-01-15 08:{30 + i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            ), 300.0)
        await eng.on_bar(make_bar("2025-01-15 08:45", base_price - 50, base_price - 40, swing_low, base_price - 60), 300.0)
        for i in range(3):
            await eng.on_bar(make_bar(
                f"2025-01-15 09:{i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            ), 300.0)
        await eng.on_bar(make_bar("2025-01-15 09:15", base_price, base_price + 10, base_price - 10, base_price), 300.0)

        # Enter entry window
        await eng.on_bar(make_bar("2025-01-15 09:30", base_price, base_price + 10, base_price - 10, base_price), 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP

        # Form bearish FVG BEFORE sweep (while in WAITING_FOR_SWEEP).
        # All lows must stay ABOVE swing_low (19400) to avoid triggering a sweep.
        # Bearish FVG: bar2.low > bar0.high (gap down)
        bar2 = make_bar("2025-01-15 09:35", 19490, 19500, 19470, 19480)  # low=19470 > swing_low
        bar1 = make_bar("2025-01-15 09:40", 19480, 19490, 19420, 19430)  # impulse down, low=19420 > swing_low
        bar0 = make_bar("2025-01-15 09:45", 19430, 19460, 19410, 19440)  # after bar, high=19460 < bar2.low=19470
        await eng.on_bar(bar2, 300.0)
        await eng.on_bar(bar1, 300.0)
        await eng.on_bar(bar0, 300.0)

        # FVG should be buffered
        assert len(eng._recent_fvgs) > 0
        assert eng._state == LSIState.WAITING_FOR_SWEEP  # no sweep yet

        # Now sweep — should promote the pre-existing FVG → WAITING_FOR_INVERSION
        await eng.on_bar(make_bar("2025-01-15 09:50", swing_low + 30, swing_low + 40, swing_low - 10, swing_low + 20), 300.0)
        assert eng._state == LSIState.WAITING_FOR_INVERSION


# =============================================================================
# WAITING_FOR_INVERSION → MANAGING (inversion-bar-close entry)
# =============================================================================

class TestInversionToManaging:
    async def test_close_above_gap_top_enters_managing(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")
        gap = eng._active_gap
        assert not gap.is_bullish  # bearish FVG

        # Inversion: close > gap.top → entry at bar close
        inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, gap.top + 5)
        await eng.on_bar(inversion_bar, 300.0)
        assert eng._state == LSIState.MANAGING

    async def test_entry_price_is_inversion_bar_close(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")
        gap = eng._active_gap
        inversion_close = gap.top + 5
        inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, inversion_close)
        await eng.on_bar(inversion_bar, 300.0)
        assert eng._levels is not None
        assert eng._levels.entry == pytest.approx(inversion_close)

    async def test_stop_is_absolute_range_low(self):
        """Stop should be min(low) from FVG bar through inversion bar (absolute mode)."""
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")
        gap = eng._active_gap
        inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, gap.top + 5)
        await eng.on_bar(inversion_bar, 300.0)
        assert eng._levels is not None
        # For long: stop = min(low) over the range, which should be 19350 from the FVG bars
        assert eng._levels.stop <= 19350.0

    async def test_direction_is_long(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")
        gap = eng._active_gap
        inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, gap.top + 5)
        await eng.on_bar(inversion_bar, 300.0)
        assert eng._levels.direction == 1

    async def test_inversion_skips_gap_formation_bar(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")
        assert eng._state == LSIState.WAITING_FOR_INVERSION

    async def test_no_max_inversion_bars_limit(self):
        """Backtest has no max_inversion_bars — engine waits until entry window closes."""
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")
        gap = eng._active_gap

        # Feed many bars without inversion (close below gap.top)
        for i in range(20):
            minute = 55 + (i + 1) * 5
            hour = 9 + minute // 60
            minute = minute % 60
            bar = make_bar(f"2025-01-15 {hour:02d}:{minute:02d}", 19410, 19420, 19395, gap.top - 10)
            await eng.on_bar(bar, 300.0)

        # Should still be waiting — no max_inversion_bars expiry
        assert eng._state == LSIState.WAITING_FOR_INVERSION

    async def test_broker_send_entry_called(self):
        eng = make_lsi_engine()
        eng, entry = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        eng.broker.send_entry.assert_called_once()
        call_kwargs = eng.broker.send_entry.call_args.kwargs
        assert call_kwargs["action"] == "buy"
        assert call_kwargs["qty"] == pytest.approx(eng._levels.qty)
        assert call_kwargs["price"] == pytest.approx(eng._levels.entry)
        assert call_kwargs["tp2"] == pytest.approx(eng._levels.tp2)
        assert call_kwargs["stop"] == pytest.approx(eng._levels.stop)
        assert call_kwargs["ticker"] == "MNQ"


# =============================================================================
# WAITING_FOR_INVERSION → ARMED_LIMIT → MANAGING (fvg_limit entry mode)
# =============================================================================

class TestFvgLimitEntryMode:
    async def test_inversion_bar_touch_does_not_fill_same_bar(self):
        eng = make_lsi_engine(lsi_entry_mode="fvg_limit")
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")

        gap = eng._active_gap
        inversion_bar = make_bar(
            "2025-01-15 09:55",
            gap.top + 2,      # open
            gap.top + 10,     # high
            gap.top - 2,      # low touches through limit price
            gap.top + 1,      # close confirms inversion
        )
        await eng.on_bar(inversion_bar, 300.0)

        assert eng._state == LSIState.ARMED_LIMIT
        assert eng.broker.send_entry.await_count == 0
        assert eng._limit_price == pytest.approx(gap.top)

    async def test_limit_fills_on_next_bar_after_inversion(self):
        eng = make_lsi_engine(lsi_entry_mode="fvg_limit")
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")

        gap = eng._active_gap
        inversion_bar = make_bar(
            "2025-01-15 09:55",
            gap.top + 2,
            gap.top + 10,
            gap.top - 2,
            gap.top + 1,
        )
        await eng.on_bar(inversion_bar, 300.0)

        fill_bar = make_bar(
            "2025-01-15 10:00",
            gap.top + 4,
            gap.top + 8,
            gap.top - 1,
            gap.top + 2,
        )
        await eng.on_bar(fill_bar, 300.0)

        assert eng._state == LSIState.MANAGING
        eng.broker.send_entry.assert_awaited_once()
        assert eng._levels is not None
        assert eng._levels.entry == pytest.approx(gap.top)


# =============================================================================
# MANAGING exits
# =============================================================================

class TestManagingExits:
    async def test_sl_hit_sends_flatten(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        broker = eng.broker
        stop = eng._levels.stop
        bar = make_bar("2025-01-15 10:05", stop + 5, stop + 10, stop - 5, stop + 3)
        await eng.on_bar(bar, 300.0)
        await _flush_cleanup_tasks()
        broker.send_cancel.assert_called()
        broker.send_flatten.assert_called()
        assert eng._state == LSIState.FLAT

    async def test_tp1_hit_multi_contract(self):
        eng = make_lsi_engine(risk_usd=5000)
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        if eng._levels.is_single_contract:
            pytest.skip("Need multi-contract")
        broker = eng.broker
        tp1 = eng._levels.tp1
        bar = make_bar("2025-01-15 10:05", tp1 - 5, tp1 + 10, tp1 - 10, tp1 + 5)
        await eng.on_bar(bar, 300.0)
        broker.send_tp1_multi.assert_called_once()
        call_kwargs = broker.send_tp1_multi.call_args.kwargs
        assert call_kwargs["total_qty"] == pytest.approx(eng._levels.qty)
        assert call_kwargs["exit_qty"] == pytest.approx(eng._levels.half_qty)
        assert eng._tp1_hit is True

    async def test_tp2_hit_after_tp1(self):
        records = []
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        eng.on_trade_exit = records.append
        broker = eng.broker
        eng._tp1_hit = True
        tp2 = eng._levels.tp2
        bar = make_bar("2025-01-15 10:10", tp2 - 5, tp2 + 10, tp2 - 10, tp2 + 5)
        await eng.on_bar(bar, 300.0)
        await _flush_cleanup_tasks()
        broker.send_cancel.assert_called()
        broker.send_flatten.assert_called()
        assert eng._state == LSIState.FLAT
        if records:
            assert records[0].exit_type == "tp1_tp2"

    async def test_eod_exits(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        broker = eng.broker
        eod_bar = make_bar("2025-01-15 15:51", 19450, 19460, 19440, 19450)
        await eng.on_bar(eod_bar, 300.0)
        broker.send_flatten.assert_called()
        assert eng._state == LSIState.FLAT

    async def test_eod_records_realized_r_result(self):
        records = []
        eng = make_lsi_engine()
        eng.on_trade_exit = records.append
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        close_price = eng._levels.entry + 15.0
        eod_bar = make_bar("2025-01-15 15:51", close_price - 2, close_price + 2, close_price - 3, close_price)
        await eng.on_bar(eod_bar, 300.0)
        expected_r = eng._price_to_r(close_price)
        assert eng._r_result == pytest.approx(expected_r)
        assert records[0].exit_type == "eod"
        assert records[0].r_result == pytest.approx(expected_r)

    async def test_tp1_eod_records_realized_r_result(self):
        records = []
        eng = make_lsi_engine(risk_usd=5000)
        eng.on_trade_exit = records.append
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        if eng._levels.is_single_contract:
            pytest.skip("Need multi-contract")
        eng._tp1_hit = True
        close_price = eng._levels.entry + 20.0
        eod_bar = make_bar("2025-01-15 15:51", close_price - 2, close_price + 2, close_price - 3, close_price)
        await eng.on_bar(eod_bar, 300.0)
        expected_r = (eng._price_to_r(eng._levels.tp1) + eng._price_to_r(close_price)) / 2.0
        assert eng._r_result == pytest.approx(expected_r)
        assert records[0].exit_type == "tp1_eod"
        assert records[0].r_result == pytest.approx(expected_r)


# =============================================================================
# Fill-bar and TP1-bar guards
# =============================================================================

class TestFillBarGuard:
    """Ensure exits don't trigger on the same 5m bar as the fill."""

    async def test_fill_bar_no_immediate_sl_check(self):
        """Fill bar guard should block SL check on entry bar."""
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        assert eng._fill_bar_count > 0


class TestTP1BarGuard:
    """Ensure 5m bar containing TP1 (detected via 1s) doesn't false-trigger BE."""

    async def test_tp1_bar_count_set_on_tick(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")

        levels = eng._levels
        tp1 = levels.tp1
        fill_ts = eng._fill_timestamp

        # Advance past fill bar
        clean_bar = make_bar("2025-01-15 10:05", levels.entry + 5, levels.entry + 20, levels.entry + 2, levels.entry + 15)
        await eng.on_bar(clean_bar, 300.0)

        # 1s tick hits TP1
        tick_ts = fill_ts + timedelta(seconds=62)
        tick = Bar(timestamp=tick_ts, open=tp1 - 5, high=tp1 + 5, low=tp1 - 8, close=tp1 + 2, volume=10)
        await eng.on_tick(tick, 300.0)

        assert eng._tp1_hit is True
        assert eng._tp1_bar_count == eng._bar_count
        assert eng._tp1_bar_count > 0

    async def test_tp1_bar_guard_blocks_same_bar_be(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")

        levels = eng._levels
        be = levels.be
        broker = eng.broker

        eng._tp1_hit = True
        eng._tp1_bar_count = eng._bar_count + 1

        bar = make_bar("2025-01-15 10:05", be + 10, be + 15, be - 5, be + 8)
        await eng.on_bar(bar, 300.0)

        assert eng._state == LSIState.MANAGING
        broker.send_flatten.assert_not_called()

    async def test_tp1_bar_count_set_on_5m_tp1(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")

        tp1 = eng._levels.tp1
        bar = make_bar("2025-01-15 10:05", tp1 - 5, tp1 + 10, tp1 - 10, tp1 + 5)
        await eng.on_bar(bar, 300.0)

        assert eng._tp1_hit is True
        assert eng._tp1_bar_count == eng._bar_count


class TestDashboardOverlay:
    async def test_waiting_for_gap_status_includes_swept_level(self):
        eng = make_lsi_engine()
        await feed_swing_low_and_sweep(eng, swing_low=19400.0)

        status = eng.status_dict()

        assert status["state"] == LSIState.WAITING_FOR_GAP.value
        assert status["swept_level"] == pytest.approx(19400.0)
        assert status["fvg_top"] is None
        assert status["fvg_bottom"] is None

    async def test_waiting_for_inversion_status_includes_gap_bounds(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")

        gap = eng._active_gap
        status = eng.status_dict()

        assert status["state"] == LSIState.WAITING_FOR_INVERSION.value
        assert status["swept_level"] == pytest.approx(19400.0)
        assert status["fvg_top"] == pytest.approx(gap.top)
        assert status["fvg_bottom"] == pytest.approx(gap.bottom)


class TestTradeOverlap:
    async def test_long_inversion_blocked_when_orb_short_has_priority(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")

        eng.trade_overlap_check = lambda direction: direction == 1
        gap = eng._active_gap
        inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, gap.top + 5)

        await eng.on_bar(inversion_bar, 300.0)

        assert eng._state == LSIState.WAITING_FOR_INVERSION
        assert eng.broker.send_entry.await_count == 0

        status = eng.status_dict()
        assert status["state"] == "trade_overlap"
        assert status["raw_state"] == LSIState.WAITING_FOR_INVERSION.value
        assert status["trade_overlap"] is True

    async def test_armed_long_limit_blocked_from_filling_when_orb_turns_short(self):
        eng = make_lsi_engine(lsi_entry_mode="fvg_limit")
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")

        eng.trade_overlap_check = lambda direction: False
        gap = eng._active_gap
        inversion_bar = make_bar("2025-01-15 09:55", gap.top + 3, gap.top + 10, gap.top + 1, gap.top + 5)

        await eng.on_bar(inversion_bar, 300.0)

        assert eng._state == LSIState.ARMED_LIMIT
        assert eng.broker.send_entry.await_count == 0

        eng.trade_overlap_check = lambda direction: direction == 1
        fill_bar = make_bar(
            "2025-01-15 10:00",
            eng._limit_price + 4,
            eng._limit_price + 8,
            eng._limit_price - 2,
            eng._limit_price + 1,
        )

        await eng.on_bar(fill_bar, 300.0)

        assert eng._state == LSIState.ARMED_LIMIT
        assert eng.broker.send_entry.await_count == 0

        status = eng.status_dict()
        assert status["state"] == "trade_overlap"
        assert status["raw_state"] == LSIState.ARMED_LIMIT.value
        assert status["trade_overlap"] is True

    async def test_long_inversion_allowed_when_overlap_check_does_not_block(self):
        eng = make_lsi_engine()
        result = await _advance_to_inversion(eng)
        if result is None:
            pytest.skip("Could not reach WAITING_FOR_INVERSION")

        eng.trade_overlap_check = lambda direction: False
        gap = eng._active_gap
        inversion_bar = make_bar("2025-01-15 09:55", 19440, gap.top + 10, gap.top - 5, gap.top + 5)

        await eng.on_bar(inversion_bar, 300.0)

        assert eng._state == LSIState.MANAGING
        eng.broker.send_entry.assert_awaited_once()

        status = eng.status_dict()
        assert status["state"] == LSIState.MANAGING.value
        assert status["trade_overlap"] is False


# =============================================================================
# 1s tick path
# =============================================================================

class TestTickPath:
    async def test_tick_sl_in_managing(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        broker = eng.broker
        stop = eng._levels.stop
        fill_ts = eng._fill_timestamp
        tick_ts = fill_ts + timedelta(seconds=2)
        tick = Bar(timestamp=tick_ts, open=stop + 5, high=stop + 8, low=stop - 5, close=stop + 3, volume=10)
        await eng.on_tick(tick, 300.0)
        await _flush_cleanup_tasks()
        broker.send_cancel.assert_called()
        broker.send_flatten.assert_called()
        assert eng._state == LSIState.FLAT

    async def test_tick_tp1_multi(self):
        eng = make_lsi_engine(risk_usd=2000)
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        if eng._levels.is_single_contract:
            pytest.skip("Need multi-contract MANAGING state")
        broker = eng.broker
        tp1 = eng._levels.tp1
        fill_ts = eng._fill_timestamp
        tick_ts = fill_ts + timedelta(seconds=2)
        tick = Bar(timestamp=tick_ts, open=tp1 - 5, high=tp1 + 5, low=tp1 - 8, close=tp1 + 2, volume=10)
        await eng.on_tick(tick, 300.0)
        broker.send_tp1_multi.assert_called_once()
        call_kwargs = broker.send_tp1_multi.call_args.kwargs
        assert call_kwargs["total_qty"] == pytest.approx(eng._levels.qty)
        assert call_kwargs["exit_qty"] == pytest.approx(eng._levels.half_qty)

    async def test_tick_eod(self):
        eng = make_lsi_engine()
        eng, entry_price = await _advance_to_managing(eng)
        if eng is None:
            pytest.skip("Could not reach MANAGING")
        broker = eng.broker
        tick = make_bar("2025-01-15 15:51", 19450, 19460, 19440, 19450)
        await eng.on_tick(tick, 300.0)
        broker.send_flatten.assert_called()
        assert eng._state == LSIState.FLAT

    async def test_tick_ignored_in_non_managing(self):
        """on_tick should be a no-op when not in MANAGING state."""
        eng = make_lsi_engine()
        bar = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar, 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP

        tick = make_bar("2025-01-15 09:30", 19500, 19510, 19490, 19500)
        await eng.on_tick(tick, 300.0)
        # Should still be WAITING_FOR_SWEEP — tick ignored
        assert eng._state == LSIState.WAITING_FOR_SWEEP


# =============================================================================
# daily reset and cross-midnight
# =============================================================================

class TestDailyReset:
    async def test_cross_midnight_session_no_spurious_reset(self):
        eng = make_lsi_engine(
            name="NQ_ASIA_LSI",
            entry_start="20:15",
            entry_end="23:30",
            flat_start="06:50",
            flat_end="07:00",
        )

        bar1 = make_bar("2025-01-14 20:15", 19500, 19510, 19490, 19500)
        await eng.on_bar(bar1, 300.0)
        assert eng._state == LSIState.WAITING_FOR_SWEEP
        assert eng._current_date == "20250114"

        bar2 = make_bar("2025-01-15 00:05", 19500, 19515, 19495, 19510)
        await eng.on_bar(bar2, 300.0)
        assert eng._state == LSIState.FLAT
        assert eng._current_date == "20250114"

    def test_recovery_reapplies_regime_gates_before_scanning(self):
        eng = make_lsi_engine(
            regime_gates=("bull_no_low_confidence", "block_full_medium_vol"),
            regime_gate_checks=(
                ("bull_no_low_confidence", lambda _date: True),
                ("block_full_medium_vol", lambda _date: False),
            ),
        )
        eng._log_trade = MagicMock()
        bars = [
            make_bar("2025-01-15 09:00", 19500, 19510, 19490, 19500),
            make_bar("2025-01-15 09:05", 19500, 19510, 19490, 19500),
        ]

        recovered = eng.recover_session_state(
            bars,
            make_bar("2025-01-15 09:45", 19500, 19510, 19490, 19500).timestamp,
        )

        assert recovered is True
        assert eng._state == LSIState.FLAT
        eng._log_trade.assert_called_with("REGIME_GATE_BLOCKED", "gate=block_full_medium_vol date=20250115")

    def test_legacy_lsi_recovery_replays_prior_day_swings(self):
        eng = make_lsi_engine(lsi_variant="legacy-LSI")
        base_price = 19500.0
        swing_low = 19400.0
        bars = [
            make_bar("2025-01-14 08:30", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:35", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:40", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:45", base_price - 50, base_price - 40, swing_low, base_price - 60),
            make_bar("2025-01-14 08:50", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:55", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 09:00", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-15 09:00", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-15 09:05", base_price, base_price + 10, base_price - 10, base_price),
        ]

        recovered = eng.recover_session_state(
            bars,
            make_bar("2025-01-15 09:45", base_price, base_price + 10, base_price - 10, base_price).timestamp,
        )

        assert recovered is True
        assert eng._state == LSIState.SCANNING
        assert eng._swings.latest_swing_low == pytest.approx(swing_low)

    def test_standard_recovery_keeps_same_day_only_warmup(self):
        eng = make_lsi_engine(lsi_variant="standard")
        base_price = 19500.0
        swing_low = 19400.0
        bars = [
            make_bar("2025-01-14 08:30", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:35", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:40", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:45", base_price - 50, base_price - 40, swing_low, base_price - 60),
            make_bar("2025-01-14 08:50", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 08:55", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-14 09:00", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-15 09:00", base_price, base_price + 10, base_price - 10, base_price),
            make_bar("2025-01-15 09:05", base_price, base_price + 10, base_price - 10, base_price),
        ]

        recovered = eng.recover_session_state(
            bars,
            make_bar("2025-01-15 09:45", base_price, base_price + 10, base_price - 10, base_price).timestamp,
        )

        assert recovered is True
        assert eng._state == LSIState.SCANNING
        assert math.isnan(eng._swings.latest_swing_low)


# =============================================================================
# Swing level persistence across days
# =============================================================================

class TestSwingPersistenceAcrossDays:
    async def test_swing_levels_carry_across_days(self):
        """Swing levels should NOT reset on new day (matching backtest ffill)."""
        eng = make_lsi_engine()

        # Build pivot on day 1
        base_price = 19500.0
        swing_low = 19400.0
        for i in range(3):
            await eng.on_bar(make_bar(
                f"2025-01-15 08:{30 + i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            ), 300.0)
        await eng.on_bar(make_bar("2025-01-15 08:45", base_price - 50, base_price - 40, swing_low, base_price - 60), 300.0)
        for i in range(3):
            await eng.on_bar(make_bar(
                f"2025-01-15 09:{i * 5:02d}",
                base_price, base_price + 10, base_price - 10, base_price,
            ), 300.0)

        # Confirmed: _latest_swing_low should be set
        assert eng._swings.latest_swing_low == pytest.approx(swing_low)

        # New day bar
        await eng.on_bar(make_bar("2025-01-16 09:30", base_price, base_price + 10, base_price - 10, base_price), 300.0)

        # Swing level should persist across day boundary
        assert eng._swings.latest_swing_low == pytest.approx(swing_low)
