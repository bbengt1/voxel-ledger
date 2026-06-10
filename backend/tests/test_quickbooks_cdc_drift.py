"""QBO CDC drift polling — Phase 4a (#317, epic #312).

Covers CDC response parsing, drift detection vs synced outbox rows, the
self-echo skip (our own push isn't drift), delete-always-drift, cursor
advance, upsert/occurrence bump, and acknowledged→reopen on a newer change.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_cdc_drift import QboCdcDrift, QboDriftStatus
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.quickbooks import cdc
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


class FakeQBO:
    """Stand-in QuickBooksClient exposing only ``_request`` for the cdc poll."""

    def __init__(self, body: dict[str, Any]) -> None:
        self.body = body
        self.calls: list[dict[str, str]] = []

    async def _request(self, method, path, *, params=None, json=None):
        self.calls.append(params or {})
        return self.body


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


async def _enable(session: AsyncSession) -> None:
    await SettingsService.set("quickbooks.enabled", True, session=session, actor_user_id=None)
    fut = NOW + timedelta(days=1)
    session.add(
        OAuthCredential(
            provider=OAuthProvider.QUICKBOOKS.value,
            realm_id="1",
            access_token="t",
            refresh_token="r",
            access_token_expires_at=fut,
            refresh_token_expires_at=fut,
        )
    )
    await session.commit()


async def _synced(session: AsyncSession, *, entity: str, qbo_id: str, synced_at: datetime) -> None:
    session.add(
        QboSyncOutbox(
            kind="invoice",
            local_id=uuid.uuid4(),
            op="post",
            payload={"lines": []},
            request_id=uuid.uuid4().hex,
            status=QboSyncStatus.SYNCED.value,
            qbo_entity_type=entity,
            qbo_id=qbo_id,
            updated_at=synced_at,
        )
    )
    await session.commit()


def _cdc(entity: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"CDCResponse": [{"QueryResponse": [{entity: items, "startPosition": 1}]}]}


def _obj(qbo_id: str, *, last_updated: datetime, deleted: bool = False) -> dict[str, Any]:
    obj: dict[str, Any] = {
        "Id": qbo_id,
        "Metadata": {"LastUpdatedTime": last_updated.isoformat()},
    }
    if deleted:
        obj["status"] = "Deleted"
    return obj


# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_poll_skips_when_disabled(app_session: AsyncSession, settings_obj) -> None:
    res = await cdc.poll(app_session, settings_obj, client=FakeQBO({}), now=NOW)
    assert res.skipped is True


@pytest.mark.asyncio
async def test_external_update_is_drift(app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    await _synced(app_session, entity="Invoice", qbo_id="101", synced_at=NOW - timedelta(hours=2))
    # QBO edited the invoice 1h ago — well after our sync.
    body = _cdc("Invoice", [_obj("101", last_updated=NOW - timedelta(hours=1))])
    res = await cdc.poll(app_session, settings_obj, client=FakeQBO(body), now=NOW)
    assert (res.matched, res.drift_new, res.drift_updated) == (1, 1, 0)
    row = (await app_session.execute(select(QboCdcDrift))).scalar_one()
    assert row.entity_type == "Invoice"
    assert row.qbo_id == "101"
    assert row.change_type == "updated"
    assert row.status == QboDriftStatus.OPEN.value
    assert row.local_kind == "invoice"


@pytest.mark.asyncio
async def test_self_echo_is_not_drift(app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    synced_at = NOW - timedelta(minutes=10)
    await _synced(app_session, entity="Invoice", qbo_id="102", synced_at=synced_at)
    # QBO's LastUpdatedTime == our sync time (our own write echoing back).
    body = _cdc("Invoice", [_obj("102", last_updated=synced_at)])
    res = await cdc.poll(app_session, settings_obj, client=FakeQBO(body), now=NOW)
    assert (res.matched, res.drift_new) == (1, 0)
    assert (await app_session.execute(select(QboCdcDrift))).first() is None


@pytest.mark.asyncio
async def test_delete_is_always_drift(app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    await _synced(app_session, entity="Payment", qbo_id="201", synced_at=NOW)
    body = _cdc("Payment", [_obj("201", last_updated=NOW, deleted=True)])
    res = await cdc.poll(app_session, settings_obj, client=FakeQBO(body), now=NOW)
    assert res.drift_new == 1
    row = (await app_session.execute(select(QboCdcDrift))).scalar_one()
    assert row.change_type == "deleted"


@pytest.mark.asyncio
async def test_unsynced_entity_ignored(app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    # No synced outbox row for this qbo_id.
    body = _cdc("Invoice", [_obj("999", last_updated=NOW)])
    res = await cdc.poll(app_session, settings_obj, client=FakeQBO(body), now=NOW)
    assert (res.scanned, res.matched, res.drift_new) == (1, 0, 0)


@pytest.mark.asyncio
async def test_cursor_advances(app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    fake = FakeQBO(_cdc("Invoice", []))
    # First poll: no cursor → 30-day lookback used as changedSince.
    await cdc.poll(app_session, settings_obj, client=fake, now=NOW)
    cursor = await SettingsService.get("quickbooks.cdc_cursor", session=app_session)
    assert cursor is not None and cursor.startswith("2026-06-10T12:00:00")
    # Second poll passes the stored cursor as changedSince.
    await cdc.poll(app_session, settings_obj, client=fake, now=NOW + timedelta(hours=1))
    assert fake.calls[1]["changedSince"].startswith("2026-06-10T12:00:00")


@pytest.mark.asyncio
async def test_redetect_bumps_occurrences_and_reopens(
    app_session: AsyncSession, settings_obj
) -> None:
    await _enable(app_session)
    await _synced(app_session, entity="Invoice", qbo_id="301", synced_at=NOW - timedelta(hours=3))
    body = _cdc("Invoice", [_obj("301", last_updated=NOW - timedelta(hours=1))])
    await cdc.poll(app_session, settings_obj, client=FakeQBO(body), now=NOW)

    # Operator acknowledges it.
    row = (await app_session.execute(select(QboCdcDrift))).scalar_one()
    row.status = QboDriftStatus.ACKNOWLEDGED.value
    await app_session.commit()

    # A newer external change re-detected → reopened, occurrences bumped.
    body2 = _cdc("Invoice", [_obj("301", last_updated=NOW + timedelta(minutes=30))])
    res = await cdc.poll(
        app_session, settings_obj, client=FakeQBO(body2), now=NOW + timedelta(hours=1)
    )
    assert res.drift_updated == 1
    await app_session.refresh(row)
    assert row.occurrences == 2
    assert row.status == QboDriftStatus.OPEN.value


@pytest.mark.asyncio
async def test_open_drift_count(app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    await _synced(app_session, entity="Invoice", qbo_id="401", synced_at=NOW - timedelta(hours=2))
    body = _cdc("Invoice", [_obj("401", last_updated=NOW - timedelta(hours=1))])
    await cdc.poll(app_session, settings_obj, client=FakeQBO(body), now=NOW)
    assert await cdc.open_drift_count(app_session) == 1
