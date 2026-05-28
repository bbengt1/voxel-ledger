"""Global search endpoint (#251)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services import products as products_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
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


@pytest.mark.asyncio
async def test_search_finds_a_product_by_name(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await products_service.create(
        app_session,
        name="Round Light Stand",
        description=None,
        unit_price=Decimal("12.50"),
        actor_user_id=None,
    )
    await app_session.commit()
    token = await _token(Role.OWNER, client, app_session)

    r = await client.get(
        "/api/v1/search?q=round",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert any(i["kind"] == "product" and "Round" in i["label"] for i in items), items


@pytest.mark.asyncio
async def test_search_empty_query_returns_no_items(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/search?q=  ",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == {"items": []}


@pytest.mark.asyncio
async def test_search_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/search?q=anything")
    assert r.status_code == 401
