"""TradersPost webhook client.

Sends JSON payloads matching the exact format from HEAD_prod_nq_ny_asia.pine.
Supports dry-run mode for testing without hitting the real endpoint.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)


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
    """

    def __init__(
        self,
        webhook_url: str,
        ticker: str = "MNQ",
        dry_run: bool = True,
        timeout_s: float = 10.0,
    ) -> None:
        self.webhook_url = webhook_url
        self.ticker = ticker
        self.dry_run = dry_run
        self.timeout = aiohttp.ClientTimeout(total=timeout_s)
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
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

        if self.dry_run:
            latency = (time.monotonic() - t0) * 1000
            logger.info("[DRY-RUN] webhook: %s", payload)
            return WebhookResult(payload=payload, status=None, latency_ms=latency, dry_run=True)

        session = await self._ensure_session()
        try:
            async with session.post(self.webhook_url, json=payload) as resp:
                latency = (time.monotonic() - t0) * 1000
                body = await resp.text()
                if resp.status >= 400:
                    logger.error(
                        "Webhook FAILED (%d) %.1fms: %s → %s",
                        resp.status, latency, payload, body,
                    )
                else:
                    logger.info(
                        "Webhook OK (%d) %.1fms: %s",
                        resp.status, latency, payload,
                    )
                return WebhookResult(payload=payload, status=resp.status, latency_ms=latency, dry_run=False)
        except Exception:
            latency = (time.monotonic() - t0) * 1000
            logger.exception("Webhook ERROR %.1fms: %s", latency, payload)
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
        results = []

        # Step 1: flatten stale position (Pine: lines 747, 756)
        results.append(await self._post({
            "ticker": t,
            "action": "exit",
        }))

        # Step 2: entry with bracket (Pine: lines 750-753, 759-762)
        results.append(await self._post({
            "ticker": t,
            "action": action,
            "quantity": qty,
            "price": price,
            "takeProfit": {"limitPrice": tp2},
            "stopLoss": {"type": "stop", "stopPrice": stop},
            "delay": 3,
        }))

        return results

    # ------------------------------------------------------------------
    # TP1 partial exit — multi-contract (Pine: lines 763-778)
    # ------------------------------------------------------------------

    async def send_tp1_multi(
        self,
        direction: str,
        half_qty: float,
        be_price: float,
        tp2: float,
        ticker: str | None = None,
    ) -> list[WebhookResult]:
        """Send 3-step TP1 partial exit for multi-contract positions.

        Args:
            direction: "long" or "short"
            half_qty: Quantity to exit at TP1 (also quantity for runner)
            be_price: Breakeven stop price for runner
            tp2: Full target price for runner
            ticker: Execution ticker override (e.g. "MNQ"). Falls back to default.
        """
        t = self._resolve_ticker(ticker)
        close_action = "sell" if direction == "long" else "buy"
        results = []

        # Step 1: market exit half qty (Pine: lines 765, 773)
        results.append(await self._post({
            "ticker": t,
            "action": "exit",
            "quantity": half_qty,
        }))

        # Step 2: BE stop for runner — cancel=true (default) clears old bracket
        # (Pine: lines 767, 775)
        results.append(await self._post({
            "ticker": t,
            "action": close_action,
            "orderType": "stop",
            "stopPrice": be_price,
            "quantity": half_qty,
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
            "quantity": half_qty,
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
