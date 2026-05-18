"""Expense-claim lines support an attachment_id receipt FK (Phase 8.7, #134)."""

from __future__ import annotations

import uuid

import pytest
from app.models.attachment import Attachment
from app.services import expense_claims as claims_service
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_claims_helpers import (
    sample_claim_lines,
    seed_full_expense_claim_stack,
    seed_user,
)


@pytest.mark.asyncio
async def test_attachment_id_stored_on_line(app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    submitter = await seed_user(app_session, email="att-sub@example.com")

    # Seed a receipt attachment.
    att = Attachment(
        id=uuid.uuid4(),
        entity_kind="expense_claim_line",
        entity_id=uuid.uuid4(),
        filename="receipt.png",
        mime_type="image/png",
        byte_size=1234,
        storage_path="receipts/test/receipt.png",
        uploaded_by_user_id=submitter.id,
    )
    app_session.add(att)
    await app_session.commit()

    lines = sample_claim_lines(expense_category_id=stack["expense_category_id"])
    lines[0]["attachment_id"] = str(att.id)

    claim = await claims_service.create_draft(
        app_session,
        submitter_user_id=submitter.id,
        lines=lines,
        actor_user_id=submitter.id,
    )
    await app_session.commit()
    assert claim.lines[0].attachment_id == att.id
