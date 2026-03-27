"""Shared contract-cap management across engines in one execution config."""

from __future__ import annotations

from dataclasses import dataclass, replace

from .sizing import TradeLevels, _floor_to_step


@dataclass
class Allocation:
    owner_id: str
    qty: float


class ContractCapManager:
    """Track reserved/open contracts across all engines in one config."""

    def __init__(self, max_open_contracts: float = 0.0) -> None:
        self.max_open_contracts = max_open_contracts
        self._allocations: dict[str, Allocation] = {}

    @property
    def enabled(self) -> bool:
        return self.max_open_contracts > 0

    def total_allocated(self) -> float:
        return sum(allocation.qty for allocation in self._allocations.values())

    def allocation_for(self, key: str) -> float:
        allocation = self._allocations.get(key)
        return allocation.qty if allocation is not None else 0.0

    def available_for(self, key: str, *, owner_id: str | None = None) -> float:
        if not self.enabled:
            return float("inf")
        allocation = self._allocations.get(key)
        current = allocation.qty if allocation is not None and (owner_id is None or allocation.owner_id == owner_id) else 0.0
        other_allocations = self.total_allocated() - current
        return max(0.0, self.max_open_contracts - other_allocations)

    def reserve(
        self,
        key: str,
        requested_qty: float,
        *,
        qty_step: float,
        min_qty: float,
        owner_id: str = "",
        exclusive_key: bool = False,
    ) -> float:
        """Reserve contracts for an engine entry/order."""
        if requested_qty <= 0:
            self.release(key, owner_id=owner_id)
            return 0.0
        if not self.enabled:
            self._allocations[key] = Allocation(owner_id=owner_id, qty=requested_qty)
            return requested_qty

        allocation = self._allocations.get(key)
        if exclusive_key and allocation is not None and allocation.qty > 0 and allocation.owner_id != owner_id:
            return 0.0

        approved = _floor_to_step(
            min(requested_qty, self.available_for(key, owner_id=owner_id)),
            qty_step,
        )
        if approved < min_qty:
            self.release(key, owner_id=owner_id)
            return 0.0
        self._allocations[key] = Allocation(owner_id=owner_id, qty=approved)
        return approved

    def adjust(self, key: str, current_qty: float, *, owner_id: str = "") -> None:
        """Update the current reserved/open quantity for an engine."""
        if current_qty <= 0:
            self.release(key, owner_id=owner_id)
            return
        self._allocations[key] = Allocation(owner_id=owner_id, qty=current_qty)

    def release(self, key: str, *, owner_id: str = "") -> None:
        allocation = self._allocations.get(key)
        if allocation is None:
            return
        if owner_id and allocation.owner_id != owner_id:
            return
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
