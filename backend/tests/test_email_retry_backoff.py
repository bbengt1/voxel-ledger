"""Retry backoff curve + max-attempts termination (Phase 7.7, #115)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import pytest_asyncio
from app.models import Base
from app.models.email_message import EmailKind, EmailState
from app.services import email as email_service
from app.services.email.providers import ProviderResult
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


class _FailingProvider:
    async def send(self, **kwargs):
        raise RuntimeError("smtp boom")


class _OkProvider:
    async def send(self, **kwargs):
        return ProviderResult(provider_message_id="ok-1", status="sent")


def test_backoff_curve() -> None:
    assert email_service.backoff_seconds(1) == 60
    assert email_service.backoff_seconds(2) == 300
    assert email_service.backoff_seconds(3) == 900
    assert email_service.backoff_seconds(4) == 3600
    assert email_service.backoff_seconds(5) == 21600
    assert email_service.max_attempts() == 6


@pytest.mark.asyncio
async def test_failed_attempt_reschedules_until_max(
    session: AsyncSession, storage_root: Path
) -> None:
    email = await email_service.enqueue_email(
        EmailKind.GENERIC,
        subject_kind=None,
        subject_id=None,
        to_address="to@example.com",
        subject="Subj",
        body_html="<p>b</p>",
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert email is not None

    provider = _FailingProvider()
    for expected_attempt in range(1, email_service.max_attempts()):
        before = datetime.now(UTC)
        updated = await email_service.attempt_send(email.id, session=session, provider=provider)
        await session.commit()
        assert updated.attempts == expected_attempt
        assert updated.state == EmailState.QUEUED
        assert updated.next_retry_at is not None
        # Backoff is at least the curve value (allow tiny clock drift).
        wait = (updated.next_retry_at - before).total_seconds()
        expected_wait = email_service.backoff_seconds(expected_attempt)
        assert wait >= expected_wait - 1
        assert updated.last_error == "smtp boom"

    # One more failing attempt tips it into terminal failed state.
    updated = await email_service.attempt_send(email.id, session=session, provider=provider)
    await session.commit()
    assert updated.state == EmailState.FAILED
    assert updated.attempts == email_service.max_attempts()
    assert updated.next_retry_at is None


@pytest.mark.asyncio
async def test_recovery_after_failure(session: AsyncSession, storage_root: Path) -> None:
    email = await email_service.enqueue_email(
        EmailKind.GENERIC,
        subject_kind=None,
        subject_id=None,
        to_address="to@example.com",
        subject="Subj",
        body_html="<p>b</p>",
        session=session,
        from_address="from@example.com",
    )
    await session.commit()
    assert email is not None
    await email_service.attempt_send(email.id, session=session, provider=_FailingProvider())
    await session.commit()
    updated = await email_service.attempt_send(email.id, session=session, provider=_OkProvider())
    await session.commit()
    assert updated.state == EmailState.SENT
    assert updated.provider_message_id == "ok-1"
    assert updated.last_error is None
