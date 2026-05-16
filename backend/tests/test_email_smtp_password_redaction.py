"""SMTP password redaction in event payloads (Phase 7.7, #115).

Regression test: writing ``email.smtp_password_secret`` must not leak
the real secret value into the emitted ``settings.SettingChanged``
event. Both ``old_value`` and ``new_value`` should be ``"***"``.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from app.events.types.settings import TYPE_SETTING_CHANGED
from app.models import Base
from app.models.event import Event
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def schema(engine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


@pytest.mark.asyncio
async def test_smtp_password_is_redacted_in_event(session: AsyncSession, schema: None) -> None:
    secret = "super-secret-pw-xyz"
    await SettingsService.set(
        "email.smtp_password_secret",
        secret,
        session=session,
        actor_user_id=None,
    )
    await session.commit()

    rows = list(
        (await session.execute(select(Event).where(Event.type == TYPE_SETTING_CHANGED))).scalars()
    )
    assert rows, "no SettingChanged events recorded"
    matching = [e for e in rows if (e.payload or {}).get("key") == "email.smtp_password_secret"]
    assert len(matching) == 1
    payload = matching[0].payload
    assert payload["old_value"] == "***"
    assert payload["new_value"] == "***"
    assert secret not in str(payload)


@pytest.mark.asyncio
async def test_non_secret_setting_is_not_redacted(session: AsyncSession, schema: None) -> None:
    await SettingsService.set(
        "email.from_address",
        "billing@example.com",
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    rows = list(
        (await session.execute(select(Event).where(Event.type == TYPE_SETTING_CHANGED))).scalars()
    )
    payload = next(e.payload for e in rows if (e.payload or {}).get("key") == "email.from_address")
    assert payload["new_value"] == "billing@example.com"
