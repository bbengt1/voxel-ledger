"""Pure tests for declining-balance depreciation (Phase 9.2, #154)."""

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
    cost: str,
    salvage: str,
    life: int,
    method: DepreciationMethod,
) -> FixedAsset:
    return FixedAsset(
        id=uuid.uuid4(),
        asset_number="ASSET-2026-0001",
        name="Test",
        asset_kind=FixedAssetKind.TANGIBLE,
        asset_class=FixedAssetClass.COMPUTER,
        acquired_on=date(2026, 1, 15),
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
    "method",
    [DepreciationMethod.DECLINING_BALANCE_200, DepreciationMethod.DECLINING_BALANCE_150],
)
def test_declining_balance_sum_equals_basis(method: DepreciationMethod) -> None:
    asset = _build_asset(cost="10000.00", salvage="1000.00", life=36, method=method)
    rows = compute_entries(asset=asset)
    assert len(rows) == 36
    basis = Decimal("10000.00") - Decimal("1000.00")
    total = sum((r.depreciation_amount for r in rows), Decimal("0"))
    assert total == basis


@pytest.mark.parametrize(
    "method",
    [DepreciationMethod.DECLINING_BALANCE_200, DepreciationMethod.DECLINING_BALANCE_150],
)
def test_declining_balance_final_closing_is_salvage(method: DepreciationMethod) -> None:
    asset = _build_asset(cost="5000.00", salvage="500.00", life=24, method=method)
    rows = compute_entries(asset=asset)
    assert rows[-1].closing_book_value == Decimal("500.00")


def test_declining_balance_200_zero_tail_when_salvage_hits_early() -> None:
    """When salvage is high relative to cost, 200% DB drives book to
    salvage long before useful_life expires; subsequent months emit
    zero-amount ``planned`` entries so the schedule length stays equal
    to useful_life_months."""
    # 200% DB on a 12-month life: rate = 0.1667/mo. Starting at 1000
    # with salvage 800 means the first month's raw dep would be ~166.67
    # but the clamp limits it to (1000-800)=200, hitting salvage in
    # month 1. The remaining 11 months must be zero-amount.
    asset = _build_asset(
        cost="1000.00",
        salvage="800.00",
        life=12,
        method=DepreciationMethod.DECLINING_BALANCE_200,
    )
    rows = compute_entries(asset=asset)
    assert len(rows) == 12
    tail_zero = [r for r in rows if r.depreciation_amount == Decimal("0.00")]
    assert tail_zero, "expected at least one zero-amount tail row"
    assert rows[-1].closing_book_value == Decimal("800.00")


def test_declining_balance_opening_chains() -> None:
    asset = _build_asset(
        cost="5000.00",
        salvage="100.00",
        life=24,
        method=DepreciationMethod.DECLINING_BALANCE_150,
    )
    rows = compute_entries(asset=asset)
    for i in range(1, len(rows)):
        assert rows[i].opening_book_value == rows[i - 1].closing_book_value
