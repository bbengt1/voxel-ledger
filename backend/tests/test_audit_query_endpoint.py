"""Admin audit-log query endpoint: role gate, filters, pagination."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@audit-query.example.com"
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


async def _emit(session: AsyncSession, etype: str = "test.TestEvent") -> None:
    await event_store.append(
        EventCreate(
            type=etype,
            aggregate_type="test",
            aggregate_id=uuid.uuid4(),
            payload={"value": "x"},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
        ),
        session=session,
    )
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/audit-log")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_response_shape_and_default_descending(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    for _ in range(3):
        await _emit(app_session)
    r = await client.get(
        "/api/v1/admin/audit-log",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "next_cursor" in body
    positions = [item["event_position"] for item in body["items"]]
    assert positions == sorted(positions, reverse=True)


@pytest.mark.asyncio
async def test_filter_by_event_type(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    await _emit(app_session, etype="test.TestEvent")
    r = await client.get(
        "/api/v1/admin/audit-log",
        params={"event_type": "test.TestEvent"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert all(item["event_type"] == "test.TestEvent" for item in body["items"])
    assert len(body["items"]) >= 1


@pytest.mark.asyncio
async def test_filter_by_aggregate_type(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    await _emit(app_session)
    r = await client.get(
        "/api/v1/admin/audit-log",
        params={"aggregate_type": "test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    for item in body["items"]:
        assert item["aggregate_type"] == "test"


@pytest.mark.asyncio
async def test_filter_by_aggregate_id_returns_only_matches(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    target = uuid.uuid4()
    await event_store.append(
        EventCreate(
            type="test.TestEvent",
            aggregate_type="test",
            aggregate_id=target,
            payload={"value": "x"},
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
        ),
        session=app_session,
    )
    await _emit(app_session)  # decoy
    await app_session.commit()
    r = await client.get(
        "/api/v1/admin/audit-log",
        params={"aggregate_id": str(target)},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["aggregate_id"] == str(target)


@pytest.mark.asyncio
async def test_filter_by_time_window(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    await _emit(app_session)
    # Use a future from-timestamp; should match nothing.
    future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    r = await client.get(
        "/api/v1/admin/audit-log",
        params={"from": future},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = r.json()
    assert body["items"] == []


@pytest.mark.asyncio
async def test_cursor_pagination_stable(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    for _ in range(5):
        await _emit(app_session)
    # limit=2 to force pagination across the 5 + login event(s).
    r1 = await client.get(
        "/api/v1/admin/audit-log",
        params={"limit": 2},
        headers={"Authorization": f"Bearer {token}"},
    )
    body1 = r1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None

    r2 = await client.get(
        "/api/v1/admin/audit-log",
        params={"limit": 2, "cursor": body1["next_cursor"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    body2 = r2.json()
    assert len(body2["items"]) == 2
    # Pages are disjoint and continue descending.
    page1_positions = [i["event_position"] for i in body1["items"]]
    page2_positions = [i["event_position"] for i in body2["items"]]
    assert min(page1_positions) > max(page2_positions)


@pytest.mark.asyncio
async def test_invalid_cursor_400s(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/admin/audit-log",
        params={"cursor": "not-a-real-cursor"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
