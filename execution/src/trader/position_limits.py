"""Shared contract-cap management across engines in one execution config."""

from __future__ import annotations

from dataclasses import replace

from .sizing import TradeLevels, _floor_to_step


class ContractCapManager:
    """Track reserved/open contracts across all engines in one config."""

    def __init__(self, max_open_contracts: float = 0.0) -> None:
        self.max_open_contracts = max_open_contracts
        self._allocations: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return self.max_open_contracts > 0

    def total_allocated(self) -> float:
        return sum(self._allocations.values())

    def allocation_for(self, key: str) -> float:
        return self._allocations.get(key, 0.0)

    def available_for(self, key: str) -> float:
        if not self.enabled:
            return float("inf")
        current = self._allocations.get(key, 0.0)
        other_allocations = self.total_allocated() - current
        return max(0.0, self.max_open_contracts - other_allocations)

    def reserve(self, key: str, requested_qty: float, *, qty_step: float, min_qty: float) -> float:
        """Reserve contracts for an engine entry/order."""
        if requested_qty <= 0:
            self.release(key)
            return 0.0
        if not self.enabled:
            self._allocations[key] = requested_qty
            return requested_qty

        approved = _floor_to_step(min(requested_qty, self.available_for(key)), qty_step)
        if approved < min_qty:
            self.release(key)
            return 0.0
        self._allocations[key] = approved
        return approved

    def adjust(self, key: str, current_qty: float) -> None:
        """Update the current reserved/open quantity for an engine."""
        if current_qty <= 0:
            self.release(key)
            return
        self._allocations[key] = current_qty

    def release(self, key: str) -> None:
        self._allocations.pop(key, None)


def resize_trade_levels(levels: TradeLevels, approved_qty: float, *, min_qty: float, qty_step: float) -> TradeLevels:
    """Return a copy of levels resized to the approved quantity."""
    if approved_qty >= levels.qty:
        return levels

    is_single = approved_qty <= min_qty
    if is_single:
        half_qty = approved_qty
    else:
        half_qty = _floor_to_step(approved_qty / 2, qty_step)
        half_qty = max(half_qty, min_qty)

    return replace(
        levels,
        qty=approved_qty,
        half_qty=half_qty,
        is_single_contract=is_single,
    )
