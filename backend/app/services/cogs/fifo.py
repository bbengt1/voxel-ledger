"""Pure FIFO calculator for cost-of-goods-sold (Phase 6.3, #95).

Deterministic, no I/O. Given an ordered (oldest-first) list of remaining
inventory layers (:class:`InventoryLot`) and a requested quantity,
:func:`compute_cogs` walks lots in order and consumes them until the
quantity is satisfied — partial-lot consumption is fine, multi-lot
consumption is fine, fractional quantities are fine. All math runs in
``Decimal`` quantized to 6 decimal places interior. If the lots can't
cover the request, :class:`InsufficientInventory` is raised with the
deficit so callers can build a precise error message.

The data shape (``InventoryLot`` / ``CogsConsumption`` / ``CogsResult``)
is intentionally trivial: dataclasses with ``Decimal`` fields. The
service layer (:mod:`app.services.cogs.service`) is responsible for
hydrating lots from the inventory transaction ledger; this module never
touches a session.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

_QUANTUM = Decimal("0.000001")  # 6dp interior precision; matches Numeric(18, 6).
_ZERO = Decimal("0")


def _q(value: Decimal | str | int | float) -> Decimal:
    """Quantize to 6 places via HALF_UP."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class InventoryLot:
    """One layer of remaining stock.

    ``lot_id`` is the originating inventory_transaction id (the positive
    movement that arrived in the location). ``remaining_quantity`` is
    what hasn't yet been consumed by prior outbound rows. ``unit_cost``
    is the snapshot cost recorded when the lot arrived; preserved
    through every consumption so per-period COGS is exact.
    """

    lot_id: uuid.UUID
    remaining_quantity: Decimal
    unit_cost: Decimal


@dataclass(frozen=True)
class CogsConsumption:
    """One slice taken out of a single lot."""

    lot_id: uuid.UUID
    quantity: Decimal
    unit_cost: Decimal

    @property
    def line_cost(self) -> Decimal:
        return _q(self.quantity * self.unit_cost)


@dataclass(frozen=True)
class CogsResult:
    """Result of one ``compute_cogs`` call."""

    total_cost: Decimal
    consumption: list[CogsConsumption] = field(default_factory=list)


class InsufficientInventory(Exception):
    """Raised when the supplied lots can't cover the requested quantity.

    Carries the ``product_id``, the requested quantity, and the total
    available (``requested - available = deficit``) so the caller can
    surface a precise 400 message without re-walking the lots.
    """

    def __init__(self, *, product_id: uuid.UUID, requested: Decimal, available: Decimal) -> None:
        self.product_id = product_id
        self.requested = _q(requested)
        self.available = _q(available)
        self.deficit = _q(self.requested - self.available)
        super().__init__(
            f"insufficient inventory for product {product_id}: "
            f"requested {self.requested}, available {self.available}, "
            f"deficit {self.deficit}"
        )


def compute_cogs(
    *,
    product_id: uuid.UUID,
    quantity: Decimal | str | int | float,
    lots: Iterable[InventoryLot],
) -> CogsResult:
    """Walk lots oldest-first, consuming until ``quantity`` is satisfied.

    Args:
        product_id: passed through to :class:`InsufficientInventory` if
            the lots can't cover the request. The pure calc otherwise
            ignores it; the service uses it to scope its lot query.
        quantity: positive requested quantity. Coerced to Decimal at the
            boundary, quantized to 6 places.
        lots: oldest-first iterable of remaining inventory layers. Lots
            with ``remaining_quantity <= 0`` are skipped (they were
            already drained).

    Returns:
        :class:`CogsResult` with ``total_cost`` (sum over slices) and a
        ``consumption`` list of ``(lot_id, qty, unit_cost)`` triples.

    Raises:
        InsufficientInventory: with the deficit if the lots can't cover.
    """
    requested = _q(quantity)
    if requested <= _ZERO:
        # Defensive — callers should pre-validate; but a zero-qty line
        # legitimately means "no cost", not "raise".
        return CogsResult(total_cost=_ZERO, consumption=[])

    remaining_needed = requested
    consumption: list[CogsConsumption] = []
    total_cost = _ZERO
    total_available = _ZERO

    for lot in lots:
        lot_remaining = _q(lot.remaining_quantity)
        if lot_remaining <= _ZERO:
            continue
        total_available += lot_remaining
        if remaining_needed <= _ZERO:
            # Already satisfied — keep accumulating ``total_available``
            # only if we need to raise InsufficientInventory below
            # (we won't if remaining_needed is zero, so we can break).
            break
        take = lot_remaining if lot_remaining < remaining_needed else remaining_needed
        take = _q(take)
        consumption.append(
            CogsConsumption(
                lot_id=lot.lot_id,
                quantity=take,
                unit_cost=_q(lot.unit_cost),
            )
        )
        total_cost = _q(total_cost + take * _q(lot.unit_cost))
        remaining_needed = _q(remaining_needed - take)

    if remaining_needed > _ZERO:
        # Walk the rest of the iterable to compute the true available
        # for the error message (the loop above broke early if
        # remaining_needed was already satisfied, but here it wasn't).
        # The loop already consumed everything it had; tally is in
        # ``total_available``. No further iteration needed because we
        # only broke early when remaining_needed == 0.
        raise InsufficientInventory(
            product_id=product_id,
            requested=requested,
            available=total_available,
        )

    return CogsResult(total_cost=total_cost, consumption=consumption)


__all__ = [
    "CogsConsumption",
    "CogsResult",
    "InsufficientInventory",
    "InventoryLot",
    "compute_cogs",
]
