"""Idempotency guard on (kind, subject_kind, subject_id) (Phase 7.7, #115)."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from app.models import Base
from app.models.email_message import EmailKind, EmailMessage
from app.services import email as email_service
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest_asyncio.fixture
async def storage_root(session: AsyncSession, schema: None, tmp_path: Path) -> Path:
    await SettingsService.set(
        "email.storage_root", str(tmp_path), session=session, actor_user_id=None
    )
    await session.commit()
    return tmp_path


@pytest.mark.asyncio
async def test_replaying_invoice_issued_does_not_double_queue(
    session: AsyncSession, storage_root: Path
) -> None:
    invoice_id = uuid.uuid4()
    first = await email_service.enqueue_email(
        EmailKind.INVOICE,
        subject_kind="invoice",
        subject_id=invoice_id,
        to_address="to@example.com",
        subject="Invoice 1",
        body_html="<p>1</p>",
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert first is not None

    # Second call for the same (kind, subject_kind, subject_id) is a no-op.
    second = await email_service.enqueue_email(
        EmailKind.INVOICE,
        subject_kind="invoice",
        subject_id=invoice_id,
        to_address="to@example.com",
        subject="Invoice 1 (replay)",
        body_html="<p>1 replay</p>",
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert second is None

    rows = list(
        (
            await session.execute(select(EmailMessage).where(EmailMessage.subject_id == invoice_id))
        ).scalars()
    )
    assert len(rows) == 1
    # The original subject (not the replay's) is what stuck.
    assert rows[0].subject == "Invoice 1"
