"""Pydantic schemas for the fixed-assets API surface (Phase 9.1, #153).

The acquire request is the single create entrypoint — there is no
draft lifecycle. ``update`` allows the metadata-only subset
(``name``, ``notes``, ``serial_number``, ``vendor_id``).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FixedAssetKindLiteral = Literal["tangible", "intangible"]
FixedAssetClassLiteral = Literal[
    "machine",
    "printer",
    "computer",
    "furniture",
    "vehicle",
    "software",
    "intellectual_property",
    "other",
]
DepreciationMethodLiteral = Literal[
    "straight_line",
    "declining_balance_200",
    "declining_balance_150",
    "none",
]
FixedAssetStateLiteral = Literal["active", "disposed", "written_off"]


class FixedAssetAcquireRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: FixedAssetKindLiteral
    asset_class: FixedAssetClassLiteral
    acquired_on: date
    acquisition_cost: Decimal
    salvage_value: Decimal = Field(default=Decimal("0"))
    useful_life_months: int = Field(ge=1)
    depreciation_method: DepreciationMethodLiteral

    asset_account_id: uuid.UUID
    accumulated_depreciation_account_id: uuid.UUID
    depreciation_expense_account_id: uuid.UUID

    # Cr side at acquisition (Bank/cash or AP). Required when there's no
    # ``acquisition_bill_id``; ignored otherwise.
    contra_account_id: uuid.UUID | None = None

    serial_number: str | None = Field(default=None, max_length=128)
    vendor_id: uuid.UUID | None = None
    acquisition_bill_id: uuid.UUID | None = None
    notes: str | None = None


class FixedAssetUpdate(BaseModel):
    """Metadata-only patch.

    Cost/life/depreciation method changes are blocked at the service
    layer once any depreciation has been posted (relevant once Phase
    9.3 lands).
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    notes: str | None = None
    serial_number: str | None = Field(default=None, max_length=128)
    vendor_id: uuid.UUID | None = None


class FixedAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_number: str
    name: str
    kind: FixedAssetKindLiteral
    asset_class: FixedAssetClassLiteral
    acquired_on: date
    acquisition_cost: Decimal
    salvage_value: Decimal
    useful_life_months: int
    depreciation_method: DepreciationMethodLiteral
    asset_account_id: uuid.UUID
    accumulated_depreciation_account_id: uuid.UUID
    depreciation_expense_account_id: uuid.UUID
    serial_number: str | None = None
    vendor_id: uuid.UUID | None = None
    acquisition_bill_id: uuid.UUID | None = None
    state: FixedAssetStateLiteral
    last_depreciated_on: date | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    notes: str | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class FixedAssetListResponse(BaseModel):
    items: list[FixedAssetResponse]
    next_cursor: str | None = None
