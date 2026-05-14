"""Admin audit-log CSV export: streaming, role-gated, filtered."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@audit-csv.example.com"
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


@pytest.mark.asyncio
async def test_csv_role_gate(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.VIEWER, client, app_session)
    r = await client.get(
        "/api/v1/admin/audit-log/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_csv_shape_and_content_type(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    for _ in range(3):
        await event_store.append(
            EventCreate(
                type="test.TestEvent",
                aggregate_type="test",
                aggregate_id=uuid.uuid4(),
                payload={"value": "x"},
                occurred_at=datetime.now(UTC),
                correlation_id=uuid.uuid4(),
            ),
            session=app_session,
        )
    await app_session.commit()

    r = await client.get(
        "/api/v1/admin/audit-log/export.csv",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    # Header + at least the three rows we added (plus the login event).
    assert lines[0].startswith("event_position,")
    assert len(lines) >= 4


@pytest.mark.asyncio
async def test_csv_respects_event_type_filter(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    await event_store.append(
        EventCreate(
            type="test.TestEvent",
            aggregate_type="test",
            aggregate_id=uuid.uuid4(),
            payload={"value": "x"},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
        ),
        session=app_session,
    )
    await app_session.commit()

    r = await client.get(
        "/api/v1/admin/audit-log/export.csv",
        params={"event_type": "no.such.Type"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    lines = r.text.strip().splitlines()
    # Only the header.
    assert len(lines) == 1
