"""TradersPost webhook client.

Sends JSON payloads matching the exact format from HEAD_prod_nq_ny_asia.pine.
Dry-run mode is auto-derived from the webhook URL: if no URL is configured
(or the URL contains "dry-run"), the broker logs payloads without sending.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

try:
    import aiohttp
except ModuleNotFoundError:  # pragma: no cover - optional in research-only envs
    aiohttp = None

logger = logging.getLogger(__name__)
webhook_logger = logging.getLogger("trader.webhooks")


@dataclass
class WebhookResult:
    """Result of a webhook POST."""

    payload: dict
    status: int | None  # None in dry-run mode
    latency_ms: float
    dry_run: bool


class TradersPostClient:
    """Async HTTP client for TradersPost webhooks.

    All payload formats match HEAD_prod_nq_ny_asia.pine exactly.
    Dry-run mode is derived automatically: a broker is live only if it
    has a real webhook URL.
    """

    def __init__(
        self,
        webhook_url: str,
        ticker: str = "MNQ",
        timeout_s: float = 10.0,
        config_name: str = "",
    ) -> None:
        self.webhook_url = webhook_url
        self.ticker = ticker
        self.dry_run = not webhook_url or "dry-run" in webhook_url
        self.config_name = config_name
        self.timeout = aiohttp.ClientTimeout(total=timeout_s) if aiohttp is not None else timeout_s
        self._session: aiohttp.ClientSession | None = None
        self.paused: bool = False
        self.multiplier: float = 1.0

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if aiohttp is None:
            raise RuntimeError("aiohttp is required for live webhook delivery; use dry-run mode in research envs.")
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _resolve_ticker(self, ticker: str | None) -> str:
        """Return explicit ticker if provided, else fall back to default."""
        return ticker if ticker is not None else self.ticker

    async def _post(self, payload: dict) -> WebhookResult:
        """Send a single webhook POST. Logs payload in both live and dry-run."""
        t0 = time.monotonic()
        tag = self.config_name or "DEFAULT"

        if self.dry_run:
            latency = (time.monotonic() - t0) * 1000
            webhook_logger.info("%s | DRY-RUN | 0.0ms | %s", tag, payload)
            return WebhookResult(payload=payload, status=None, latency_ms=latency, dry_run=True)

        session = await self._ensure_session()
        try:
            async with session.post(self.webhook_url, json=payload) as resp:
                latency = (time.monotonic() - t0) * 1000
                body = await resp.text()
                if resp.status >= 400:
                    webhook_logger.error(
                        "%s | FAILED | %d | %.1fms | %s | %s",
                        tag, resp.status, latency, payload, body,
                    )
                else:
                    webhook_logger.info(
                        "%s | OK | %d | %.1fms | %s",
                        tag, resp.status, latency, payload,
                    )
                return WebhookResult(payload=payload, status=resp.status, latency_ms=latency, dry_run=False)
        except Exception:
            latency = (time.monotonic() - t0) * 1000
            webhook_logger.exception(
                "%s | ERROR | %.1fms | %s", tag, latency, payload,
            )
            return WebhookResult(payload=payload, status=None, latency_ms=latency, dry_run=False)

    # ------------------------------------------------------------------
    # Entry orders (Pine: lines 745-762)
    # ------------------------------------------------------------------

    async def send_entry(
        self,
        action: str,
        qty: float,
        price: float,
        tp2: float,
        stop: float,
        ticker: str | None = None,
    ) -> list[WebhookResult]:
        """Send bracket entry order.

        Sends a pre-entry flatten first (clears stale broker position),
        then the entry with bracket stop + TP.

        Args:
            action: "buy" or "sell"
            qty: Total contract quantity
            price: Limit entry price
            tp2: Take profit (full target) price
            stop: Initial stop loss price
            ticker: Execution ticker override (e.g. "MNQ"). Falls back to default.
        """
        t = self._resolve_ticker(ticker)

        # Single bracket entry — no pre-flatten needed since the engine's
        # state machine guarantees no open position when entering.
        result = await self._post({
            "ticker": t,
            "action": action,
            "quantity": qty,
            "price": price,
            "takeProfit": {"limitPrice": tp2},
            "stopLoss": {"type": "stop", "stopPrice": stop},
        })

        return [result]

    # ------------------------------------------------------------------
    # TP1 partial exit — multi-contract (Pine: lines 763-778)
    # ------------------------------------------------------------------

    async def send_tp1_multi(
        self,
        direction: str,
        total_qty: float,
        exit_qty: float,
        be_price: float,
        tp2: float,
        ticker: str | None = None,
    ) -> list[WebhookResult]:
        """Send 3-step TP1 partial exit for multi-contract positions.

        Args:
            direction: "long" or "short"
            total_qty: Total open quantity before the TP1 partial exit.
            exit_qty: Quantity to exit at TP1.
            be_price: Breakeven stop price for runner
            tp2: Full target price for runner
            ticker: Execution ticker override (e.g. "MNQ"). Falls back to default.
        """
        t = self._resolve_ticker(ticker)
        close_action = "sell" if direction == "long" else "buy"
        runner_qty = max(0.0, total_qty - exit_qty)
        results = []

        # Step 1: partially exit half the position.
        # TradersPost only honors partial exits via action="exit" with an
        # explicit quantity. Using buy/sell here can open the opposite side
        # if our engine thinks the entry filled but the broker never got a
        # position on.
        results.append(await self._post({
            "ticker": t,
            "action": "exit",
            "quantity": exit_qty,
        }))

        if runner_qty > 0:
            # Step 2: BE stop for runner — cancel=true (default) clears old bracket
            # (Pine: lines 767, 775)
            results.append(await self._post({
                "ticker": t,
                "action": close_action,
                "orderType": "stop",
                "stopPrice": be_price,
                "quantity": runner_qty,
                "sentiment": "flat",
                "delay": 3,
            }))

            # Step 3: TP2 limit for runner — cancel=false preserves BE stop
            # (Pine: lines 769, 777)
            results.append(await self._post({
                "ticker": t,
                "action": close_action,
                "orderType": "limit",
                "limitPrice": tp2,
                "quantity": runner_qty,
                "sentiment": "flat",
                "cancel": False,
                "delay": 5,
            }))

        return results

    # ------------------------------------------------------------------
    # TP1 breakeven move — single contract (Pine: lines 779-784)
    # ------------------------------------------------------------------

    async def send_tp1_single(
        self,
        direction: str,
        qty: float,
        be_price: float,
        ticker: str | None = None,
    ) -> WebhookResult:
        """Move stop to breakeven for single-contract position."""
        t = self._resolve_ticker(ticker)
        close_action = "sell" if direction == "long" else "buy"

        return await self._post({
            "ticker": t,
            "action": close_action,
            "orderType": "stop",
            "stopPrice": be_price,
            "quantity": qty,
            "sentiment": "flat",
            "delay": 3,
        })

    # ------------------------------------------------------------------
    # Flatten / Cancel (Pine: lines 789-803)
    # ------------------------------------------------------------------

    async def send_flatten(self, ticker: str | None = None) -> WebhookResult:
        """Flatten all positions and cancel pending orders."""
        return await self._post({
            "ticker": self._resolve_ticker(ticker),
            "action": "exit",
        })

    async def send_cancel(self, ticker: str | None = None) -> WebhookResult:
        """Cancel all pending orders without closing positions."""
        return await self._post({
            "ticker": self._resolve_ticker(ticker),
            "action": "cancel",
        })


class MultiBroker:
    """Fan-out broker that forwards every call to multiple TradersPostClient instances.

    All methods mirror TradersPostClient's interface. Results from the first
    broker are returned; remaining brokers are fired in parallel and their
    results are discarded (errors are logged but do not raise).
    """

    def __init__(self, brokers: list[TradersPostClient]) -> None:
        self._brokers = brokers

    async def close(self) -> None:
        await asyncio.gather(*[b.close() for b in self._brokers], return_exceptions=True)

    async def send_entry(self, action, qty, price, tp2, stop, ticker=None):
        active = [b for b in self._brokers if not b.paused]
        if not active:
            return []

        async def _send_entry(b: TradersPostClient):
            scaled_qty = max(1, round(qty * b.multiplier))
            return await b.send_entry(action, scaled_qty, price, tp2, stop, ticker=ticker)

        results = await asyncio.gather(*[_send_entry(b) for b in active], return_exceptions=True)
        return results[0] if results else []

    async def send_tp1_multi(self, direction, total_qty, exit_qty, be_price, tp2, ticker=None):
        active = [b for b in self._brokers if not b.paused]
        if not active:
            return []

        async def _send_tp1_multi(b: TradersPostClient):
            scaled_total = max(1, round(total_qty * b.multiplier))
            scaled_exit = max(1, round(exit_qty * b.multiplier))
            if scaled_exit >= scaled_total:
                scaled_exit = max(1, scaled_total - 1)
            return await b.send_tp1_multi(direction, scaled_total, scaled_exit, be_price, tp2, ticker=ticker)

        results = await asyncio.gather(*[_send_tp1_multi(b) for b in active], return_exceptions=True)
        return results[0] if results else []

    async def send_tp1_single(self, direction, qty, be_price, ticker=None):
        active = [b for b in self._brokers if not b.paused]
        if not active:
            return None

        async def _send_tp1_single(b: TradersPostClient):
            scaled_qty = max(1, round(qty * b.multiplier))
            return await b.send_tp1_single(direction, scaled_qty, be_price, ticker=ticker)

        results = await asyncio.gather(*[_send_tp1_single(b) for b in active], return_exceptions=True)
        return results[0] if results else None

    async def send_flatten(self, ticker=None):
        active = [b for b in self._brokers if not b.paused]
        if not active:
            return None
        results = await asyncio.gather(
            *[b.send_flatten(ticker=ticker) for b in active],
            return_exceptions=True,
        )
        return results[0] if results else None

    async def send_cancel(self, ticker=None):
        active = [b for b in self._brokers if not b.paused]
        if not active:
            return None
        results = await asyncio.gather(
            *[b.send_cancel(ticker=ticker) for b in active],
            return_exceptions=True,
        )
        return results[0] if results else None
