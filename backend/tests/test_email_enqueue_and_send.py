"""Full enqueue → send loop with the StaticFileProvider (Phase 7.7, #115)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from app.models import Base
from app.models.email_message import EmailKind, EmailState
from app.services import email as email_service
from app.services.email.providers import Attachment, StaticFileProvider
from app.services.settings.service import SettingsService
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
async def test_enqueue_persists_row_and_body(session: AsyncSession, storage_root: Path) -> None:
    email = await email_service.enqueue_email(
        EmailKind.GENERIC,
        subject_kind=None,
        subject_id=None,
        to_address="to@example.com",
        subject="Subj",
        body_html="<p>hello</p>",
        body_text="hello",
        attachments=[Attachment(filename="r.txt", content=b"data")],
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert email is not None
    assert email.state == EmailState.QUEUED
    body_path = storage_root / email.body_html_storage_key
    assert body_path.read_text(encoding="utf-8") == "<p>hello</p>"
    assert email.attachments_json
    att_key = email.attachments_json[0]["storage_key"]
    assert (storage_root / att_key).read_bytes() == b"data"


@pytest.mark.asyncio
async def test_attempt_send_marks_sent(session: AsyncSession, storage_root: Path) -> None:
    email = await email_service.enqueue_email(
        EmailKind.GENERIC,
        subject_kind=None,
        subject_id=None,
        to_address="to@example.com",
        subject="Subj",
        body_html="<p>hi</p>",
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert email is not None

    provider = StaticFileProvider(root=storage_root)
    updated = await email_service.attempt_send(email.id, session=session, provider=provider)
    await session.commit()
    assert updated.state == EmailState.SENT
    assert updated.provider_message_id is not None
    assert updated.sent_at is not None
    assert updated.attempts == 1


@pytest.mark.asyncio
async def test_worker_picks_up_due_rows(session: AsyncSession, storage_root: Path) -> None:
    for i in range(3):
        await email_service.enqueue_email(
            EmailKind.GENERIC,
            subject_kind=None,
            subject_id=None,
            to_address=f"to-{i}@example.com",
            subject=f"S{i}",
            body_html="<p>b</p>",
            session=session,
            from_address="from@example.com",
        )
    await session.commit()
    provider = StaticFileProvider(root=storage_root)
    touched = await email_service.run_worker_once(session=session, provider=provider)
    await session.commit()
    assert len(touched) == 3
    assert all(t.state == EmailState.SENT for t in touched)


@pytest.mark.asyncio
async def test_cancel_only_from_queued(session: AsyncSession, storage_root: Path) -> None:
    email = await email_service.enqueue_email(
        EmailKind.GENERIC,
        subject_kind=None,
        subject_id=None,
        to_address="to@example.com",
        subject="Subj",
        body_html="<p>hi</p>",
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert email is not None
    cancelled = await email_service.cancel(email.id, session=session)
    await session.commit()
    assert cancelled.state == EmailState.FAILED
    assert cancelled.last_error == "cancelled by operator"
    # Second cancel fails since state is no longer queued.
    with pytest.raises(email_service.InvalidEmailStateError):
        await email_service.cancel(email.id, session=session)
