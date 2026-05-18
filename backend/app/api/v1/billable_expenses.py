"""Billable expenses API (Phase 8.8, #135).

Read-only endpoint that surfaces ``bill_item`` + ``expense_claim_line``
rows flagged ``is_billable`` for a target customer that haven't yet been
linked to an invoice line. The invoice composer (``POST /invoices`` /
``PATCH /invoices/{id}``) is the write path — it accepts a per-line
``billable_source`` reference, applies the markup, and stamps the
source's ``billed_invoice_item_id`` in the same transaction.

Roles: read = owner + bookkeeper + sales + viewer.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.schemas.billable_expenses import (
    BillableExpenseListResponse,
    UnbilledRow,
)
from app.services import billable_expenses as billable_service

router = APIRouter(prefix="/billable-expenses", tags=["billable-expenses"])

_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")


@router.get("", response_model=BillableExpenseListResponse)
async def list_billable_expenses(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    customer_id: Annotated[uuid.UUID, Query(...)],
) -> BillableExpenseListResponse:
    rows = await billable_service.list_unbilled(session, customer_id=customer_id)
    items: list[UnbilledRow] = []
    for row in rows:
        if isinstance(row, billable_service.UnbilledBillItem):
            items.append(
                UnbilledRow(
                    source_kind=row.source_kind,  # type: ignore[arg-type]
                    source_id=row.source_id,
                    line_number=row.line_number,
                    description=row.description,
                    amount=row.amount,
                    markup_percent=row.markup_percent,
                    occurred_on=row.occurred_on,
                    bill_id=row.bill_id,
                    bill_number=row.bill_number,
                )
            )
        else:
            items.append(
                UnbilledRow(
                    source_kind=row.source_kind,  # type: ignore[arg-type]
                    source_id=row.source_id,
                    line_number=row.line_number,
                    description=row.description,
                    amount=row.amount,
                    markup_percent=row.markup_percent,
                    occurred_on=row.occurred_on,
                    claim_id=row.claim_id,
                    claim_number=row.claim_number,
                )
            )
    return BillableExpenseListResponse(items=items)
