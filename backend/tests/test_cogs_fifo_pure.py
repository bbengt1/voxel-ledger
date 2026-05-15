"""Pure FIFO calculator tests (Phase 6.3, #95).

Exercises :func:`app.services.cogs.fifo.compute_cogs` without touching
the database: single-lot exact, multi-lot split, fractional quantities,
and the insufficient-inventory deficit path.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.services.cogs.fifo import (
    InsufficientInventory,
    InventoryLot,
    compute_cogs,
)


def _lot(qty: str, cost: str) -> InventoryLot:
    return InventoryLot(
        lot_id=uuid.uuid4(),
        remaining_quantity=Decimal(qty),
        unit_cost=Decimal(cost),
    )


def test_single_lot_exact_consumption():
    lot = _lot("10", "2.50")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("10"), lots=[lot])
    assert result.total_cost == Decimal("25.000000")
    assert len(result.consumption) == 1
    assert result.consumption[0].quantity == Decimal("10.000000")
    assert result.consumption[0].unit_cost == Decimal("2.500000")
    assert result.consumption[0].lot_id == lot.lot_id


def test_single_lot_partial_consumption():
    lot = _lot("10", "2.50")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("3"), lots=[lot])
    assert result.total_cost == Decimal("7.500000")
    assert result.consumption[0].quantity == Decimal("3.000000")


def test_multi_lot_split():
    lot1 = _lot("5", "1.00")
    lot2 = _lot("5", "2.00")
    lot3 = _lot("5", "3.00")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("8"), lots=[lot1, lot2, lot3])
    # 5 @ 1.00 + 3 @ 2.00 = 11.00
    assert result.total_cost == Decimal("11.000000")
    assert [c.lot_id for c in result.consumption] == [lot1.lot_id, lot2.lot_id]
    assert result.consumption[0].quantity == Decimal("5.000000")
    assert result.consumption[1].quantity == Decimal("3.000000")


def test_multi_lot_full_drain():
    lot1 = _lot("5", "1.00")
    lot2 = _lot("5", "2.00")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("10"), lots=[lot1, lot2])
    assert result.total_cost == Decimal("15.000000")
    assert len(result.consumption) == 2


def test_fractional_quantity():
    lot = _lot("2.5", "4.20")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("1.25"), lots=[lot])
    assert result.total_cost == Decimal("5.250000")
    assert result.consumption[0].quantity == Decimal("1.250000")


def test_skips_drained_lots():
    drained = InventoryLot(uuid.uuid4(), Decimal("0"), Decimal("99"))
    live = _lot("5", "1.00")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("3"), lots=[drained, live])
    assert len(result.consumption) == 1
    assert result.consumption[0].lot_id == live.lot_id


def test_zero_quantity_returns_empty():
    lot = _lot("5", "1.00")
    result = compute_cogs(product_id=uuid.uuid4(), quantity=Decimal("0"), lots=[lot])
    assert result.total_cost == Decimal("0")
    assert result.consumption == []


def test_insufficient_inventory_raises_with_deficit():
    lot1 = _lot("2", "1.00")
    lot2 = _lot("3", "2.00")
    product_id = uuid.uuid4()
    with pytest.raises(InsufficientInventory) as exc_info:
        compute_cogs(product_id=product_id, quantity=Decimal("10"), lots=[lot1, lot2])
    err = exc_info.value
    assert err.product_id == product_id
    assert err.requested == Decimal("10.000000")
    assert err.available == Decimal("5.000000")
    assert err.deficit == Decimal("5.000000")


def test_insufficient_inventory_when_no_lots():
    product_id = uuid.uuid4()
    with pytest.raises(InsufficientInventory) as exc_info:
        compute_cogs(product_id=product_id, quantity=Decimal("1"), lots=[])
    assert exc_info.value.available == Decimal("0.000000")
    assert exc_info.value.deficit == Decimal("1.000000")
