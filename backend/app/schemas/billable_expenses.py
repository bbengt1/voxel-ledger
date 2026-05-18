"""Pydantic schemas for the billable-expenses API surface (Phase 8.8, #135).

The unbilled list returns a tagged union (``source_kind``) across two
shapes:

* ``bill_item`` rows carry ``bill_id`` + ``bill_number``,
* ``expense_claim_line`` rows carry ``claim_id`` + ``claim_number``.

To keep the OpenAPI codegen simple we use a single flattened response
model with both pairs marked optional + a ``source_kind`` discriminator
field. Clients branch on ``source_kind``.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

BillableSourceKindLiteral = Literal["bill_item", "expense_claim_line"]


class BillableSourceRef(BaseModel):
    """Per-line ``billable_source`` reference on an invoice line.

    When set on an ``InvoiceItemCreate``, the invoice composer loads the
    referenced source, validates customer + billable + not-yet-billed,
    applies the markup, and stamps ``billed_invoice_item_id`` on the
    source row in the same transaction.
    """

    kind: BillableSourceKindLiteral
    id: uuid.UUID
    markup_percent_override: Decimal | None = None


class UnbilledRow(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    source_kind: BillableSourceKindLiteral
    source_id: uuid.UUID
    line_number: int
    description: str
    amount: Decimal
    markup_percent: Decimal
    occurred_on: date
    # Present only when ``source_kind == "bill_item"``.
    bill_id: uuid.UUID | None = None
    bill_number: str | None = None
    # Present only when ``source_kind == "expense_claim_line"``.
    claim_id: uuid.UUID | None = None
    claim_number: str | None = None


class BillableExpenseListResponse(BaseModel):
    items: list[UnbilledRow] = Field(default_factory=list)
