"""HTTP-level tests for the operational settings endpoints.

Covers role matrix, unknown-key 400s, bulk atomic rollback, and
response shape — including verifying that endpoints land in the OpenAPI
schema so the frontend codegen picks them up.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
import pytest_asyncio
from app.models.auth import Role
from app.models.setting import Setting
from app.services.auth import create_user
from app.services.settings.cache import get_cache
from httpx import AsyncClient
from sqlalchemy import select
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
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


@pytest_asyncio.fixture(autouse=True)
async def _clear_cache() -> None:
    get_cache().clear()


@pytest.mark.asyncio
async def test_list_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/settings")
    assert r.status_code == 401


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
async def test_list_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected: int,
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_get_single_returns_default(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.BOOKKEEPER, client, app_session)
    r = await client.get(
        "/api/v1/settings/cost_engine.labor_rate_per_hour",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["key"] == "cost_engine.labor_rate_per_hour"
    assert body["value"] == "25.00"
    assert body["default"] == "25.00"
    assert body["updated_at"] is None
    assert body["updated_by_user_id"] is None


@pytest.mark.asyncio
async def test_get_unknown_key_400(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/settings/nope.not.real",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 400, r.text


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
async def test_put_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected: int,
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.put(
        "/api/v1/settings/cost_engine.labor_rate_per_hour",
        headers={"Authorization": f"Bearer {token}"},
        json={"value": "33.33"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_put_persists_and_returns_updated_record(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.put(
        "/api/v1/settings/cost_engine.labor_rate_per_hour",
        headers={"Authorization": f"Bearer {token}"},
        json={"value": "99.99"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value"] == "99.99"
    assert body["updated_at"] is not None
    assert body["updated_by_user_id"] is not None

    # Row really exists in the DB.
    row = (
        await app_session.execute(
            select(Setting).where(Setting.key == "cost_engine.labor_rate_per_hour")
        )
    ).scalar_one()
    assert row.value == "99.99"


@pytest.mark.asyncio
async def test_put_unknown_key_400(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.put(
        "/api/v1/settings/nope.not.real",
        headers={"Authorization": f"Bearer {token}"},
        json={"value": "1"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_put_invalid_value_400(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.put(
        "/api/v1/settings/cost_engine.overhead_percent",
        headers={"Authorization": f"Bearer {token}"},
        json={"value": "9999"},  # > 100
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_bulk_owner_only(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.BOOKKEEPER, client, app_session)
    r = await client.post(
        "/api/v1/settings:bulk",
        headers={"Authorization": f"Bearer {token}"},
        json={"updates": {"cost_engine.labor_rate_per_hour": "10"}},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_bulk_atomic_rollback_on_invalid_value(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/settings:bulk",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "updates": {
                "cost_engine.labor_rate_per_hour": "50.00",
                "cost_engine.overhead_percent": "9999",  # invalid
            }
        },
    )
    assert r.status_code == 400, r.text
    # Nothing written — both keys must still be at their defaults.
    rows = (await app_session.execute(select(Setting))).scalars().all()
    assert rows == []


@pytest.mark.asyncio
async def test_bulk_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/settings:bulk",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "updates": {
                "cost_engine.labor_rate_per_hour": "50.00",
                "cost_engine.overhead_percent": "10",
            }
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["updated"]["cost_engine.labor_rate_per_hour"] == "50.00"
    assert body["updated"]["cost_engine.overhead_percent"] == "10"


@pytest.mark.asyncio
async def test_list_response_shape(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/settings",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    keys = {entry["key"] for entry in body}
    # Cost-engine keys all appear.
    assert "cost_engine.labor_rate_per_hour" in keys
    assert "cost_engine.overhead_percent" in keys
    # Every entry has the documented shape.
    sample = body[0]
    assert {
        "key",
        "value",
        "default",
        "schema_type",
        "updated_at",
        "updated_by_user_id",
    }.issubset(sample.keys())


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/settings" in paths
    assert "/api/v1/settings/{key}" in paths
    assert "/api/v1/settings:bulk" in paths


@pytest.mark.asyncio
async def test_put_decimal_round_trip_via_http(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Decimal precision survives the HTTP round-trip."""
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.put(
        "/api/v1/settings/cost_engine.power_cost_per_kwh",
        headers={"Authorization": f"Bearer {token}"},
        json={"value": "0.123456789012345"},
    )
    assert r.status_code == 200
    assert r.json()["value"] == "0.123456789012345"
    assert Decimal(r.json()["value"]) == Decimal("0.123456789012345")
