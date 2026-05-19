"""Pydantic schemas for the fixed-asset disposal API (Phase 9.4, #156)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

AssetDisposalKindLiteral = Literal["sale", "scrap", "writeoff", "donation"]


class FixedAssetDisposalRequest(BaseModel):
    disposed_on: date
    kind: AssetDisposalKindLiteral
    proceeds_amount: Decimal = Decimal("0")
    proceeds_account_id: uuid.UUID | None = None
    gain_loss_account_id: uuid.UUID
    notes: str | None = None


class FixedAssetDisposalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    disposed_on: date
    disposal_kind: AssetDisposalKindLiteral
    proceeds_amount: Decimal
    proceeds_account_id: uuid.UUID | None = None
    gain_loss_account_id: uuid.UUID
    book_value_at_disposal: Decimal
    accumulated_depreciation_at_disposal: Decimal
    gain_loss_amount: Decimal
    notes: str | None = None
    posting_journal_entry_id: uuid.UUID | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
