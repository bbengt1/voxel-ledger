"""POS endpoint role matrix (Phase 6.4, #96).

Write (open, scan, line edits, checkout, void): owner + sales.
Read (GET cart): owner + sales + bookkeeper.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._pos_helpers import seed_pos_channel
from tests._sales_helpers import auth_header, token_for


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.SALES, 201),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_open_cart_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    channel = await seed_pos_channel(app_session)
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(token),
        json={"channel_id": str(channel.id)},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.SALES, 200),
        (Role.BOOKKEEPER, 200),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_get_cart_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    from app.services.auth import create_user

    # Seed an extra non-conflicting "creator" user so the OWNER token below
    # can be (re)issued without colliding with the parametrized OWNER case.
    await create_user(
        app_session,
        email="cart-creator@example.com",
        password="pw-correct",
        full_name="Creator",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "cart-creator@example.com", "password": "pw-correct"},
    )
    creator = login.json()["access_token"]
    channel = await seed_pos_channel(app_session)
    r = await client.post(
        "/api/v1/pos/carts",
        headers=auth_header(creator),
        json={"channel_id": str(channel.id)},
    )
    cart_id = r.json()["id"]
    token = await token_for(role, client, app_session)
    r = await client.get(f"/api/v1/pos/carts/{cart_id}", headers=auth_header(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_unauthenticated_open_401(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/pos/carts",
        json={"channel_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 401
