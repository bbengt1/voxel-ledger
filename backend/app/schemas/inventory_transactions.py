"""Pydantic schemas for the inventory-transactions API (Phase 3.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Kinds the operator may post via the create endpoint. ``transfer_in``
# / ``transfer_out`` are written by the dedicated transfer endpoint and
# ``production_consumption`` / ``sale_consumption`` are only written by
# services (record-plate-run, sale fulfilment) — never accepted on the
# raw create surface, so they're absent here.
InventoryTransactionKindLiteral = Literal[
    "production_in",
    "sale_out",
    "adjustment",
    "return_in",
    "waste",
    "receipt",
    "transfer_in",
    "transfer_out",
]
# Kinds the response may carry. Strict superset of the create literal —
# the read surface has to round-trip every row the service might write,
# including the consumption rows.
InventoryTransactionResponseKindLiteral = Literal[
    "production_in",
    "sale_out",
    "adjustment",
    "return_in",
    "waste",
    "receipt",
    "transfer_in",
    "transfer_out",
    "production_consumption",
    "sale_consumption",
]
InventoryEntityKindLiteral = Literal["material", "supply", "product"]


class InventoryTransactionCreate(BaseModel):
    """Body for ``POST /api/v1/inventory/transactions``.

    ``quantity`` is the positive magnitude for every kind except
    ``adjustment``, where the caller supplies a signed delta.
    """

    kind: InventoryTransactionKindLiteral
    entity_kind: InventoryEntityKindLiteral
    entity_id: uuid.UUID
    location_id: uuid.UUID
    quantity: Decimal
    occurred_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=4096)
    unit_cost: Decimal | None = None
    linked_job_id: uuid.UUID | None = None
    linked_sale_id: uuid.UUID | None = None


class InventoryTransferCreate(BaseModel):
    """Body for ``POST /api/v1/inventory/transactions/transfer``."""

    entity_kind: InventoryEntityKindLiteral
    entity_id: uuid.UUID
    from_location_id: uuid.UUID
    to_location_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    occurred_at: datetime | None = None
    reason: str | None = Field(default=None, max_length=4096)


class InventoryTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    created_at: datetime
    kind: InventoryTransactionResponseKindLiteral
    entity_kind: InventoryEntityKindLiteral
    entity_id: uuid.UUID
    location_id: uuid.UUID
    # Signed magnitude — the service has already applied direction.
    quantity: Decimal
    unit_cost_at_transaction: Decimal | None = None
    total_cost_at_transaction: Decimal | None = None
    transfer_pair_id: uuid.UUID | None = None
    linked_job_id: uuid.UUID | None = None
    linked_sale_id: uuid.UUID | None = None
    actor_user_id: uuid.UUID | None = None
    reason: str | None = None


class InventoryTransferResponse(BaseModel):
    """Response from the transfer endpoint — returns both halves."""

    transfer_pair_id: uuid.UUID
    out_transaction: InventoryTransactionResponse
    in_transaction: InventoryTransactionResponse


class InventoryTransactionListResponse(BaseModel):
    items: list[InventoryTransactionResponse]
    next_cursor: str | None = None
