"""QBO sync metrics — Phase 4d (#317, epic #312).

Covers the monitoring snapshot (outbox depths, drift count, oldest-pending lag,
worker freshness) and the owner/bookkeeper metrics endpoint.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role
from app.models.qbo_cdc_drift import QboCdcDrift, QboDriftStatus
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.models.worker_run_state import WorkerRunState, WorkerRunStatus
from app.services.auth import create_user
from app.services.quickbooks import monitoring
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

QB = "/api/v1/admin/quickbooks"
NOW = datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


async def _login(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _outbox(status: QboSyncStatus, *, created_at: datetime | None = None) -> QboSyncOutbox:
    row = QboSyncOutbox(
        kind="invoice",
        local_id=uuid.uuid4(),
        op="post",
        payload={},
        request_id=uuid.uuid4().hex,
        status=status.value,
    )
    if created_at is not None:
        row.created_at = created_at
    return row


# --------------------------------------------------------------------------- #
# service
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_metrics_empty(app_session: AsyncSession) -> None:
    m = await monitoring.build_metrics(app_session, now=NOW)
    assert m.outbox["total"] == 0
    assert m.drift_open == 0
    assert m.oldest_pending_age_seconds is None
    assert m.sync_worker.last_status is None
    assert m.cdc_worker.last_status is None


@pytest.mark.asyncio
async def test_metrics_depths_and_lag(app_session: AsyncSession) -> None:
    app_session.add_all(
        [
            _outbox(QboSyncStatus.PENDING, created_at=NOW - timedelta(hours=3)),
            _outbox(QboSyncStatus.PENDING, created_at=NOW - timedelta(hours=1)),
            _outbox(QboSyncStatus.FAILED),
            _outbox(QboSyncStatus.DEAD),
            QboCdcDrift(
                entity_type="Invoice",
                qbo_id="9",
                change_type="updated",
                occurrences=1,
                status=QboDriftStatus.OPEN.value,
                first_detected_at=NOW,
                last_detected_at=NOW,
            ),
        ]
    )
    await app_session.commit()
    m = await monitoring.build_metrics(app_session, now=NOW)
    assert m.outbox["pending"] == 2
    assert m.outbox["failed"] == 1
    assert m.outbox["dead"] == 1
    assert m.drift_open == 1
    # Oldest pending was 3h ago.
    assert m.oldest_pending_age_seconds == 3 * 3600


@pytest.mark.asyncio
async def test_metrics_worker_health(app_session: AsyncSession) -> None:
    app_session.add(
        WorkerRunState(
            job_name="quickbooks_sync",
            last_started_at=NOW - timedelta(minutes=5),
            last_finished_at=NOW - timedelta(minutes=5),
            last_status=WorkerRunStatus.OK,
            last_duration_ms=1200,
            last_processed=7,
        )
    )
    await app_session.commit()
    m = await monitoring.build_metrics(app_session, now=NOW)
    assert m.sync_worker.last_status == "ok"
    assert m.sync_worker.last_processed == 7
    assert m.sync_worker.last_duration_ms == 1200


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [(Role.OWNER, 200), (Role.BOOKKEEPER, 200), (Role.SALES, 403), (Role.VIEWER, 403)],
)
async def test_metrics_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _login(role, client, app_session)
    r = await client.get(f"{QB}/metrics", headers=_auth(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_metrics_endpoint_shape(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _login(Role.OWNER, client, app_session)
    r = await client.get(f"{QB}/metrics", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("enabled", "connected", "outbox", "drift_open", "sync_worker", "cdc_worker"):
        assert key in body
    assert body["sync_worker"]["job_name"] == "quickbooks_sync"
    assert body["cdc_worker"]["job_name"] == "quickbooks_cdc"
