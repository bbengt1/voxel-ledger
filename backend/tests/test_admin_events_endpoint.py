"""Admin event endpoints: role-gated, window-bounded, response shape."""

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


def _evt() -> EventCreate:
    return EventCreate(
        type="test.TestEvent",
        aggregate_type="test",
        aggregate_id=uuid.uuid4(),
        payload={"value": "x"},
        occurred_at=datetime.now(UTC),
        correlation_id=uuid.uuid4(),
    )


@pytest.mark.asyncio
async def test_verify_chain_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/admin/events/verify-chain")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_verify_chain_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected: int,
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get(
        "/api/v1/admin/events/verify-chain",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_verify_chain_ok_response_shape(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    # _token_for() logs in, which now emits one auth.LoginSucceeded event
    # (Phase 1.4). Account for it in the expected counts.
    for _ in range(3):
        await event_store.append(_evt(), session=app_session)
    await app_session.commit()
    r = await client.get(
        "/api/v1/admin/events/verify-chain",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["last_position"] == 4
    assert body["broken_at_position"] is None
    assert body["events_checked"] == 4


@pytest.mark.asyncio
async def test_verify_chain_window_too_large(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/admin/events/verify-chain" "?from_position=0&to_position=2000000",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400
    assert "window" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verify_chain_inverted_range(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/admin/events/verify-chain?from_position=10&to_position=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_verify_chain_appears_in_openapi(client: AsyncClient) -> None:
    """Sanity check: the new path is on the OpenAPI surface so the
    frontend codegen will pick it up."""
    r = await client.get("/api/v1/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    assert "/api/v1/admin/events/verify-chain" in paths
