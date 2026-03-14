"""Tests for TradersPost webhook payload format.

Strategy: patch client._post() to capture payloads without making real HTTP calls.
This gives exact field-level assertions on every webhook sent.

Critical correctness requirements verified here:
  - Entry bracket order payload
  - TP1 multi: 3 steps with exact fields
  - cancel=False MUST be explicit on TP2 limit (regression guard)
  - Direction-aware close_action (sell for long, buy for short)
  - Flatten and cancel exact minimal payloads
  - Ticker override / fallback
  - MultiBroker fan-out and multiplier scaling
  - HTTP error handling (no raises)
"""

from __future__ import annotations

import pytest
from aioresponses import aioresponses
from unittest.mock import AsyncMock

from trader.broker import MultiBroker, TradersPostClient, WebhookResult


# =============================================================================
# Fixture: client with _post patched to capture payloads
# =============================================================================

@pytest.fixture
def client_and_captured():
    """Returns (client, captured_list).

    Each _post() call appends the payload to captured_list.
    No real HTTP is made.
    """
    c = TradersPostClient("http://fake-webhook.test/hook", ticker="MNQ")
    captured: list[dict] = []

    async def capture(payload: dict) -> WebhookResult:
        captured.append(payload)
        return WebhookResult(payload=payload, status=None, latency_ms=0, dry_run=True)

    c._post = capture  # type: ignore[method-assign]
    return c, captured


# =============================================================================
# send_entry — long
# =============================================================================

class TestSendEntryLong:
    async def test_sends_single_bracket_webhook(self, client_and_captured):
        client, captured = client_and_captured
        results = await client.send_entry("buy", 2.0, 19500.0, 19700.0, 19400.0)
        assert len(results) == 1
        assert len(captured) == 1

    async def test_entry_payload_fields(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_entry("buy", 2.0, 19500.0, 19700.0, 19400.0)
        entry = captured[0]
        assert entry["ticker"] == "MNQ"
        assert entry["action"] == "buy"
        assert entry["quantity"] == 2.0
        assert entry["price"] == 19500.0
        assert entry["takeProfit"]["limitPrice"] == 19700.0
        assert entry["stopLoss"]["type"] == "stop"
        assert entry["stopLoss"]["stopPrice"] == 19400.0

    async def test_entry_no_extra_fields(self, client_and_captured):
        """Entry payload must NOT have orderType/sentiment/cancel at top level."""
        client, captured = client_and_captured
        await client.send_entry("buy", 2.0, 19500.0, 19700.0, 19400.0)
        entry = captured[0]
        assert "orderType" not in entry
        assert "sentiment" not in entry
        assert "cancel" not in entry
        assert "delay" not in entry


# =============================================================================
# send_entry — short
# =============================================================================

class TestSendEntryShort:
    async def test_short_action_is_sell(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_entry("sell", 1.0, 19500.0, 19300.0, 19600.0)
        assert captured[0]["action"] == "sell"

    async def test_short_stop_above_entry(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_entry("sell", 1.0, 19500.0, 19300.0, 19600.0)
        assert captured[0]["stopLoss"]["stopPrice"] > captured[0]["price"]

    async def test_short_tp_below_entry(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_entry("sell", 1.0, 19500.0, 19300.0, 19600.0)
        assert captured[0]["takeProfit"]["limitPrice"] < captured[0]["price"]


# =============================================================================
# send_tp1_multi — long
# =============================================================================

class TestSendTp1MultiLong:
    async def test_sends_three_webhooks(self, client_and_captured):
        client, captured = client_and_captured
        results = await client.send_tp1_multi("long", 1.0, 19500.0, 19700.0)
        assert len(results) == 3
        assert len(captured) == 3

    async def test_first_webhook_market_exit_half(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_multi("long", 1.0, 19500.0, 19700.0)
        assert captured[0]["ticker"] == "MNQ"
        assert captured[0]["action"] == "exit"
        assert captured[0]["quantity"] == 1.0

    async def test_be_stop_fields(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_multi("long", 1.0, 19500.0, 19700.0)
        be = captured[1]
        assert be["ticker"] == "MNQ"
        assert be["action"] == "sell"
        assert be["orderType"] == "stop"
        assert be["stopPrice"] == 19500.0
        assert be["quantity"] == 1.0
        assert be["sentiment"] == "flat"
        assert be["delay"] == 3
        # BE stop should NOT have explicit cancel=False (it uses default cancel=true behaviour)
        assert "cancel" not in be

    async def test_tp2_limit_fields(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_multi("long", 1.0, 19500.0, 19700.0)
        tp2 = captured[2]
        assert tp2["ticker"] == "MNQ"
        assert tp2["action"] == "sell"
        assert tp2["orderType"] == "limit"
        assert tp2["limitPrice"] == 19700.0
        assert tp2["quantity"] == 1.0
        assert tp2["sentiment"] == "flat"
        assert tp2["delay"] == 5

    async def test_tp2_cancel_false_is_explicit(self, client_and_captured):
        """CRITICAL regression guard: cancel=False MUST be present and exactly False.

        Without it, TradersPost defaults to cancelling prior orders (including
        the BE stop), leaving the runner completely unprotected.
        """
        client, captured = client_and_captured
        await client.send_tp1_multi("long", 1.0, 19500.0, 19700.0)
        tp2 = captured[2]
        assert "cancel" in tp2, "cancel key must be explicitly present in TP2 payload"
        assert tp2["cancel"] is False, "cancel must be exactly False (not just falsy)"


# =============================================================================
# send_tp1_multi — short (close action is buy)
# =============================================================================

class TestSendTp1MultiShort:
    async def test_short_close_action_is_buy(self, client_and_captured):
        """Critical: closing a short requires action='buy'. Hardcoded 'sell' opens new position."""
        client, captured = client_and_captured
        await client.send_tp1_multi("short", 1.0, 19500.0, 19300.0)
        assert captured[1]["action"] == "buy"
        assert captured[2]["action"] == "buy"

    async def test_short_tp2_cancel_false(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_multi("short", 1.0, 19500.0, 19300.0)
        assert captured[2]["cancel"] is False


# =============================================================================
# send_tp1_single
# =============================================================================

class TestSendTp1Single:
    async def test_long_payload(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_single("long", 1.0, 19501.0)
        assert len(captured) == 1
        p = captured[0]
        assert p["ticker"] == "MNQ"
        assert p["action"] == "sell"
        assert p["orderType"] == "stop"
        assert p["stopPrice"] == 19501.0
        assert p["quantity"] == 1.0
        assert p["sentiment"] == "flat"
        assert p["delay"] == 3

    async def test_long_no_cancel_key(self, client_and_captured):
        """Single-contract TP1 must NOT include cancel field."""
        client, captured = client_and_captured
        await client.send_tp1_single("long", 1.0, 19501.0)
        assert "cancel" not in captured[0]

    async def test_long_no_limit_price(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_single("long", 1.0, 19501.0)
        assert "limitPrice" not in captured[0]

    async def test_short_action_is_buy(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_tp1_single("short", 1.0, 19499.0)
        assert captured[0]["action"] == "buy"


# =============================================================================
# send_flatten and send_cancel
# =============================================================================

class TestFlattenAndCancel:
    async def test_flatten_exact_payload(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_flatten()
        assert captured[0] == {"ticker": "MNQ", "action": "exit"}

    async def test_flatten_no_quantity_field(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_flatten()
        assert "quantity" not in captured[0]

    async def test_cancel_exact_payload(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_cancel()
        assert captured[0] == {"ticker": "MNQ", "action": "cancel"}


# =============================================================================
# Ticker resolution
# =============================================================================

class TestTickerResolution:
    async def test_override_ticker_wins(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_entry("buy", 1.0, 19500.0, 19700.0, 19400.0, ticker="NQ")
        assert captured[0]["ticker"] == "NQ"

    async def test_none_ticker_uses_default(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_entry("buy", 1.0, 19500.0, 19700.0, 19400.0, ticker=None)
        assert captured[0]["ticker"] == "MNQ"

    async def test_ticker_in_flatten(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_flatten(ticker="MGC")
        assert captured[0]["ticker"] == "MGC"

    async def test_ticker_in_cancel(self, client_and_captured):
        client, captured = client_and_captured
        await client.send_cancel(ticker="MES")
        assert captured[0]["ticker"] == "MES"


# =============================================================================
# Dry-run mode
# =============================================================================

class TestDryRun:
    async def test_dry_run_returns_status_none(self):
        client = TradersPostClient("", ticker="MNQ")
        result = await client._post({"ticker": "MNQ", "action": "exit"})
        assert result.status is None
        assert result.dry_run is True

    async def test_dry_run_no_http(self):
        """Confirm no real HTTP connection is attempted when URL is empty."""
        client = TradersPostClient("", ticker="MNQ")
        result = await client.send_flatten()
        assert result.status is None

    async def test_dry_run_auto_derived_from_empty_url(self):
        """Empty URL auto-derives dry_run=True."""
        client = TradersPostClient("", ticker="MNQ")
        assert client.dry_run is True

    async def test_live_auto_derived_from_real_url(self):
        """Real URL auto-derives dry_run=False."""
        client = TradersPostClient("http://real.test/hook", ticker="MNQ")
        assert client.dry_run is False


# =============================================================================
# Live mode HTTP (using aioresponses to mock)
# =============================================================================

class TestLiveMode:
    async def test_live_200_returns_status(self):
        client = TradersPostClient("http://fake/hook", ticker="MNQ")
        with aioresponses() as m:
            m.post("http://fake/hook", status=200, payload={"ok": True})
            result = await client._post({"ticker": "MNQ", "action": "exit"})
        assert result.status == 200
        assert result.dry_run is False
        await client.close()

    async def test_http_error_no_raise(self):
        """400 response must NOT raise — return result with status=400."""
        client = TradersPostClient("http://fake/hook", ticker="MNQ")
        with aioresponses() as m:
            m.post("http://fake/hook", status=400, payload={"error": "bad"})
            result = await client._post({"action": "exit"})
        assert result.status == 400
        await client.close()

    async def test_connection_error_no_raise(self):
        """Network exception must NOT raise — return result with status=None."""
        import aiohttp
        client = TradersPostClient("http://fake/hook", ticker="MNQ")
        with aioresponses() as m:
            m.post("http://fake/hook", exception=aiohttp.ClientConnectionError())
            result = await client._post({"action": "exit"})
        assert result.status is None
        assert result.dry_run is False
        await client.close()


# =============================================================================
# MultiBroker fan-out and multiplier
# =============================================================================

class TestMultiBroker:
    def _make_mock_client(self, paused=False, multiplier=1.0):
        from unittest.mock import AsyncMock, MagicMock
        b = MagicMock(spec=TradersPostClient)
        b.paused = paused
        b.multiplier = multiplier
        b.send_entry = AsyncMock(return_value=[
            WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True),
            WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True),
        ])
        b.send_tp1_multi = AsyncMock(return_value=[])
        b.send_tp1_single = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
        b.send_flatten = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
        b.send_cancel = AsyncMock(return_value=WebhookResult(payload={}, status=None, latency_ms=0, dry_run=True))
        return b

    async def test_fan_out_sends_to_all_active(self):
        b1 = self._make_mock_client()
        b2 = self._make_mock_client()
        multi = MultiBroker([b1, b2])
        await multi.send_entry("buy", 2.0, 19500.0, 19700.0, 19400.0)
        b1.send_entry.assert_called_once()
        b2.send_entry.assert_called_once()

    async def test_paused_broker_skipped(self):
        b1 = self._make_mock_client(paused=True)
        b2 = self._make_mock_client(paused=False)
        multi = MultiBroker([b1, b2])
        await multi.send_entry("buy", 2.0, 19500.0, 19700.0, 19400.0)
        b1.send_entry.assert_not_called()
        b2.send_entry.assert_called_once()

    async def test_multiplier_scales_qty(self):
        b1 = self._make_mock_client(multiplier=2.0)
        multi = MultiBroker([b1])
        await multi.send_entry("buy", 3.0, 19500.0, 19700.0, 19400.0)
        # Scaled qty = max(1, round(3 * 2.0)) = 6
        call_kwargs = b1.send_entry.call_args
        called_qty = call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("qty")
        assert called_qty == 6

    async def test_tp1_multi_multiplier_scales_half_qty(self):
        b1 = self._make_mock_client(multiplier=2.0)
        multi = MultiBroker([b1])
        await multi.send_tp1_multi("long", 1.0, 19500.0, 19700.0)
        call_kwargs = b1.send_tp1_multi.call_args
        called_half_qty = call_kwargs.args[1] if call_kwargs.args else call_kwargs.kwargs.get("half_qty")
        assert called_half_qty == 2

    async def test_all_paused_returns_empty(self):
        b1 = self._make_mock_client(paused=True)
        b2 = self._make_mock_client(paused=True)
        multi = MultiBroker([b1, b2])
        result = await multi.send_entry("buy", 1.0, 19500.0, 19700.0, 19400.0)
        assert result == []

    async def test_returns_first_broker_result(self):
        b1 = self._make_mock_client()
        b2 = self._make_mock_client()
        expected = [
            WebhookResult(payload={"action": "exit"}, status=200, latency_ms=1, dry_run=False),
            WebhookResult(payload={"action": "buy"}, status=200, latency_ms=2, dry_run=False),
        ]
        b1.send_entry = AsyncMock(return_value=expected)
        multi = MultiBroker([b1, b2])
        result = await multi.send_entry("buy", 1.0, 19500.0, 19700.0, 19400.0)
        assert result == expected
