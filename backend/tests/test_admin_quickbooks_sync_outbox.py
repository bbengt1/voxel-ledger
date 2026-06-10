"""Admin QBO sync-outbox surface — Phase 3e (#316, epic #312).

Covers the owner-only outbox observability + recovery endpoints (stats, list,
single retry, bulk retry) and the underlying ``outbox`` service helpers:
status counts, keyset paging, retry eligibility, and idempotent requeue.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.auth import Role, User
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.auth import create_user
from app.services.quickbooks import outbox
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

QB = "/api/v1/admin/quickbooks"


async def _seed(role: Role, client: AsyncClient, session: AsyncSession) -> tuple[str, User]:
    email = f"{role.value}@example.com"
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"], user


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _row(*, kind: str, status: QboSyncStatus, **overrides) -> QboSyncOutbox:
    row = QboSyncOutbox(
        kind=kind,
        local_id=uuid.uuid4(),
        op="post",
        payload={"lines": []},
        request_id=uuid.uuid4().hex,
        status=status.value,
        next_attempt_at=datetime.now(UTC),
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


async def _seed_rows(session: AsyncSession) -> None:
    session.add_all(
        [
            _row(kind="invoice", status=QboSyncStatus.PENDING),
            _row(kind="payment", status=QboSyncStatus.SYNCED, qbo_id="42"),
            _row(kind="bill", status=QboSyncStatus.FAILED, last_error="boom", attempts=3),
            _row(kind="sale", status=QboSyncStatus.DEAD, last_error="gave up", attempts=9),
        ]
    )
    await session.commit()


# --------------------------------------------------------------------------- #
# service layer
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_stats_zero_filled_and_total(app_session: AsyncSession) -> None:
    await _seed_rows(app_session)
    counts = await outbox.stats(app_session)
    assert counts == {"pending": 1, "synced": 1, "failed": 1, "dead": 1, "total": 4}


@pytest.mark.asyncio
async def test_list_rows_filter_and_order(app_session: AsyncSession) -> None:
    await _seed_rows(app_session)
    failed = await outbox.list_rows(app_session, status="failed")
    assert [r.kind for r in failed] == ["bill"]
    all_rows = await outbox.list_rows(app_session)
    assert len(all_rows) == 4
    # newest first
    times = [r.created_at for r in all_rows]
    assert times == sorted(times, reverse=True)


@pytest.mark.asyncio
async def test_retry_row_requeues_failed(app_session: AsyncSession) -> None:
    row = _row(kind="bill", status=QboSyncStatus.FAILED, last_error="boom", attempts=3)
    app_session.add(row)
    await app_session.commit()
    out = await outbox.retry_row(app_session, row.id)
    assert out.status == QboSyncStatus.PENDING.value
    assert out.last_error is None
    assert out.attempts == 3  # history preserved


@pytest.mark.asyncio
async def test_retry_row_rejects_pending(app_session: AsyncSession) -> None:
    row = _row(kind="invoice", status=QboSyncStatus.PENDING)
    app_session.add(row)
    await app_session.commit()
    with pytest.raises(outbox.OutboxNotRetryableError):
        await outbox.retry_row(app_session, row.id)


@pytest.mark.asyncio
async def test_retry_row_missing(app_session: AsyncSession) -> None:
    with pytest.raises(outbox.OutboxRowNotFoundError):
        await outbox.retry_row(app_session, uuid.uuid4())


@pytest.mark.asyncio
async def test_retry_all_only_target_status(app_session: AsyncSession) -> None:
    await _seed_rows(app_session)
    n = await outbox.retry_all(app_session, status="dead")
    await app_session.commit()
    assert n == 1
    counts = await outbox.stats(app_session)
    assert counts["dead"] == 0
    assert counts["pending"] == 2  # original pending + requeued dead
    assert counts["failed"] == 1  # untouched


@pytest.mark.asyncio
async def test_retry_all_rejects_bad_status(app_session: AsyncSession) -> None:
    with pytest.raises(outbox.OutboxNotRetryableError):
        await outbox.retry_all(app_session, status="pending")


# --------------------------------------------------------------------------- #
# API — auth matrix
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_stats_requires_auth(client: AsyncClient) -> None:
    r = await client.get(f"{QB}/outbox/stats")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.BOOKKEEPER, 403), (Role.SALES, 403), (Role.VIEWER, 403)],
)
async def test_stats_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token, _ = await _seed(role, client, app_session)
    r = await client.get(f"{QB}/outbox/stats", headers=_auth(token))
    assert r.status_code == expected, r.text


# --------------------------------------------------------------------------- #
# API — behavior
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_api_stats_and_list(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    await _seed_rows(app_session)

    r = await client.get(f"{QB}/outbox/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"pending": 1, "synced": 1, "failed": 1, "dead": 1, "total": 4}

    r = await client.get(f"{QB}/outbox", params={"status": "failed"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert [it["kind"] for it in body["items"]] == ["bill"]
    assert body["items"][0]["last_error"] == "boom"
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_api_list_bad_status(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    r = await client.get(f"{QB}/outbox", params={"status": "nope"}, headers=_auth(token))
    assert r.status_code == 400, r.text


@pytest.mark.asyncio
async def test_api_list_paging_cursor(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    await _seed_rows(app_session)
    r = await client.get(f"{QB}/outbox", params={"limit": 2}, headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"] is not None
    r2 = await client.get(
        f"{QB}/outbox", params={"limit": 2, "cursor": body["next_cursor"]}, headers=_auth(token)
    )
    assert r2.status_code == 200, r2.text
    assert len(r2.json()["items"]) == 2


@pytest.mark.asyncio
async def test_api_retry_single_row(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    row = _row(kind="bill", status=QboSyncStatus.FAILED, last_error="boom")
    app_session.add(row)
    await app_session.commit()

    r = await client.post(f"{QB}/outbox/{row.id}/retry", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "pending"

    refreshed = (
        await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.id == row.id))
    ).scalar_one()
    await app_session.refresh(refreshed)
    assert refreshed.status == QboSyncStatus.PENDING.value


@pytest.mark.asyncio
async def test_api_retry_conflict_on_pending(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    row = _row(kind="invoice", status=QboSyncStatus.PENDING)
    app_session.add(row)
    await app_session.commit()
    r = await client.post(f"{QB}/outbox/{row.id}/retry", headers=_auth(token))
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_api_retry_404(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    r = await client.post(f"{QB}/outbox/{uuid.uuid4()}/retry", headers=_auth(token))
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_api_retry_all(client: AsyncClient, app_session: AsyncSession) -> None:
    token, _ = await _seed(Role.OWNER, client, app_session)
    await _seed_rows(app_session)
    r = await client.post(f"{QB}/outbox/retry", json={"status": "failed"}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["requeued"] == 1
    # bad status rejected
    r = await client.post(f"{QB}/outbox/retry", json={"status": "synced"}, headers=_auth(token))
    assert r.status_code == 400, r.text
