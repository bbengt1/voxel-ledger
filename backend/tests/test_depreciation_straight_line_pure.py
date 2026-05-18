"""Pure tests for straight-line depreciation (Phase 9.2, #154)."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from app.models.fixed_asset import (
    DepreciationMethod,
    FixedAsset,
    FixedAssetClass,
    FixedAssetKind,
    FixedAssetState,
)
from app.services.depreciation_schedule import compute_entries


def _build_asset(
    *,
    cost: str = "1200.00",
    salvage: str = "0.00",
    life: int = 36,
    method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE,
    acquired_on: date = date(2026, 1, 15),
) -> FixedAsset:
    return FixedAsset(
        id=uuid.uuid4(),
        asset_number="ASSET-2026-0001",
        name="Test",
        asset_kind=FixedAssetKind.TANGIBLE,
        asset_class=FixedAssetClass.COMPUTER,
        acquired_on=acquired_on,
        acquisition_cost=Decimal(cost),
        salvage_value=Decimal(salvage),
        useful_life_months=life,
        depreciation_method=method,
        asset_account_id=uuid.uuid4(),
        accumulated_depreciation_account_id=uuid.uuid4(),
        depreciation_expense_account_id=uuid.uuid4(),
        state=FixedAssetState.ACTIVE,
        created_by_user_id=uuid.uuid4(),
    )


@pytest.mark.parametrize(
    "cost,salvage,life",
    [
        ("1200.00", "0.00", 36),
        ("10000.00", "1000.00", 60),
        ("999.99", "0.01", 12),
        ("1000.00", "100.00", 7),  # non-divisible → last month picks remainder
    ],
)
def test_straight_line_sum_equals_basis(cost: str, salvage: str, life: int) -> None:
    asset = _build_asset(cost=cost, salvage=salvage, life=life)
    rows = compute_entries(asset=asset)
    assert len(rows) == life
    basis = Decimal(cost) - Decimal(salvage)
    total = sum((r.depreciation_amount for r in rows), Decimal("0"))
    assert total == basis.quantize(Decimal("0.01"))


def test_straight_line_final_closing_is_salvage() -> None:
    asset = _build_asset(cost="1200.00", salvage="120.00", life=36)
    rows = compute_entries(asset=asset)
    assert rows[-1].closing_book_value == Decimal("120.00")


def test_straight_line_opening_equals_previous_closing() -> None:
    asset = _build_asset(cost="5000.00", salvage="500.00", life=24)
    rows = compute_entries(asset=asset)
    for i in range(1, len(rows)):
        assert rows[i].opening_book_value == rows[i - 1].closing_book_value


def test_straight_line_period_indexes_are_dense() -> None:
    asset = _build_asset(life=12)
    rows = compute_entries(asset=asset)
    assert [r.period_index for r in rows] == list(range(12))
