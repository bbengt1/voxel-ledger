"""QBO sync outbox foundation (#316 Phase 3a, epic #312).

Enqueue + worker drain: disabled/not-connected no-ops, journal-entry build+push,
stable request_id across retries, transient backoff, permanent failure, no-builder
failure, and dead-letter past the retry window. Uses an in-memory fake client.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.quickbooks import account_map, outbox
from app.services.quickbooks.client import QuickBooksApiError, QuickBooksThrottleError
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FakeClient:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.error = error
        self._n = 1

    async def create(
        self, entity: str, payload: dict[str, Any], *, request_id: str | None = None
    ) -> dict[str, Any]:
        self.create_calls.append({"entity": entity, "payload": payload, "request_id": request_id})
        if self.error is not None:
            raise self.error
        qid = str(self._n)
        self._n += 1
        return {**payload, "Id": qid, "SyncToken": "0"}


async def _prep(
    session: AsyncSession,
    *,
    enabled: bool = True,
    connected: bool = True,
    roles: tuple[str, ...] = ("revenue", "accounts_receivable"),
) -> None:
    if enabled:
        await SettingsService.set("quickbooks.enabled", True, session=session, actor_user_id=None)
    if connected:
        fut = datetime.now(UTC) + timedelta(days=1)
        session.add(
            OAuthCredential(
                provider=OAuthProvider.QUICKBOOKS.value,
                realm_id="9999",
                access_token="tok",
                refresh_token="ref",
                access_token_expires_at=fut,
                refresh_token_expires_at=fut,
            )
        )
    if roles:
        await account_map.set_mappings(
            session,
            {r: {"qbo_account_id": f"acct-{r}"} for r in roles},
            actor_user_id=None,
        )
    await session.commit()


def _je_payload() -> dict[str, Any]:
    return {
        "lines": [
            {"role": "accounts_receivable", "posting": "debit", "amount": "10.00"},
            {"role": "revenue", "posting": "credit", "amount": "10.00"},
        ],
        "doc_number": "INV-1",
    }


async def _enqueue_je(session: AsyncSession) -> QboSyncOutbox:
    row = await outbox.enqueue(
        session, kind="journal_entry", local_id=uuid.uuid4(), payload=_je_payload()
    )
    await session.commit()
    return row


@pytest.fixture
def settings_obj():
    from app.core.settings import Settings

    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


# --------------------------------------------------------------------------- #
# gating
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_run_pending_skips_when_disabled(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _prep(app_session, enabled=False)
    await _enqueue_je(app_session)
    res = await outbox.run_pending(app_session, settings_obj, client=FakeClient())
    assert res.skipped is True


@pytest.mark.asyncio
async def test_run_pending_skips_when_not_connected(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _prep(app_session, connected=False)
    await _enqueue_je(app_session)
    res = await outbox.run_pending(app_session, settings_obj, client=FakeClient())
    assert res.skipped is True


# --------------------------------------------------------------------------- #
# happy path
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_journal_entry_builds_and_syncs(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _prep(app_session)
    row = await _enqueue_je(app_session)
    fake = FakeClient()

    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1

    await app_session.refresh(row)
    assert row.status == QboSyncStatus.SYNCED.value
    assert row.qbo_entity_type == "JournalEntry"
    assert row.qbo_id == "1"
    # The built JE resolved roles → account refs and carried the row's requestid.
    call = fake.create_calls[0]
    assert call["entity"] == "JournalEntry"
    assert call["request_id"] == row.request_id
    refs = {
        line["JournalEntryLineDetail"]["AccountRef"]["value"] for line in call["payload"]["Line"]
    }
    assert refs == {"acct-revenue", "acct-accounts_receivable"}


@pytest.mark.asyncio
async def test_request_id_stable_across_retry(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _prep(app_session)
    row = await _enqueue_je(app_session)

    # First drain: transient error → row stays pending, scheduled for later.
    failing = FakeClient(error=QuickBooksThrottleError(429, "ThrottleExceeded"))
    res = await outbox.run_pending(app_session, settings_obj, client=failing)
    assert res.retried == 1
    await app_session.refresh(row)
    assert row.status == QboSyncStatus.PENDING.value
    assert row.attempts == 1
    assert outbox._as_utc(row.next_attempt_at) > datetime.now(UTC)

    # Make it due again; second drain succeeds. Same requestid both times.
    row.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    await app_session.commit()
    ok = FakeClient()
    res2 = await outbox.run_pending(app_session, settings_obj, client=ok)
    assert res2.synced == 1
    assert failing.create_calls[0]["request_id"] == ok.create_calls[0]["request_id"]


# --------------------------------------------------------------------------- #
# error classification
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_permanent_4xx_marks_failed(client, app_session: AsyncSession, settings_obj) -> None:
    await _prep(app_session)
    row = await _enqueue_je(app_session)
    fake = FakeClient(error=QuickBooksApiError(400, "bad request"))
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.failed == 1
    await app_session.refresh(row)
    assert row.status == QboSyncStatus.FAILED.value
    assert "400" in (row.last_error or "")


@pytest.mark.asyncio
async def test_unknown_kind_marks_failed(client, app_session: AsyncSession, settings_obj) -> None:
    await _prep(app_session)
    row = await outbox.enqueue(
        app_session, kind="not_a_real_kind", local_id=uuid.uuid4(), payload={"lines": []}
    )
    await app_session.commit()
    res = await outbox.run_pending(app_session, settings_obj, client=FakeClient())
    assert res.failed == 1
    await app_session.refresh(row)
    assert row.status == QboSyncStatus.FAILED.value


@pytest.mark.asyncio
async def test_dead_letter_after_retry_window(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _prep(app_session)
    row = await _enqueue_je(app_session)
    # Pretend this row has been retrying for over a day.
    row.created_at = datetime.now(UTC) - timedelta(hours=25)
    await app_session.commit()
    fake = FakeClient(error=QuickBooksApiError(503, "unavailable"))
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.dead == 1
    await app_session.refresh(row)
    assert row.status == QboSyncStatus.DEAD.value


# --------------------------------------------------------------------------- #
# worker entrypoint no-ops when disabled (builds no client)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_worker_run_noops_when_disabled(client, app_session: AsyncSession) -> None:
    from app.workers import quickbooks_sync

    await _enqueue_je(app_session)  # a row exists but sync is disabled
    await quickbooks_sync.run(app_session)  # must not raise
    row = (await app_session.execute(select(QboSyncOutbox))).scalars().one()
    assert row.status == QboSyncStatus.PENDING.value
