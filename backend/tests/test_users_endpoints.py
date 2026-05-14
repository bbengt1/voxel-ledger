"""Users-admin endpoint role matrix + happy paths (Phase 1.6)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
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
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/users",
        headers=_headers(token),
        json={
            "email": "newbie@example.com",
            "full_name": "Newbie",
            "role": "sales",
        },
    )
    assert r.status_code == expected, r.text


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
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/users", headers=_headers(token))
    assert r.status_code == expected, r.text


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
async def test_get_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    # find their own id via /me
    me = await client.get("/api/v1/auth/me", headers=_headers(token))
    assert me.status_code == 200
    user_id = me.json()["id"]
    r = await client.get(f"/api/v1/users/{user_id}", headers=_headers(token))
    assert r.status_code == expected, r.text


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
async def test_patch_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    # Need a target. Seed a separate target user so the actor isn't editing themselves.
    await create_user(
        app_session,
        email="target@example.com",
        password="pw",
        full_name="Target",
        role=Role.SALES,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    token = await _token_for(role, client, app_session)
    owner_token = await _token_for_or_existing(Role.OWNER, client, app_session, token)
    listing = await client.get("/api/v1/users", headers=_headers(owner_token))
    target = next(u for u in listing.json()["items"] if u["email"] == "target@example.com")

    r = await client.patch(
        f"/api/v1/users/{target['id']}",
        headers=_headers(token),
        json={"full_name": "Renamed"},
    )
    assert r.status_code == expected, r.text


async def _token_for_or_existing(
    role: Role, client: AsyncClient, app_session: AsyncSession, fallback_token: str
) -> str:
    """If we already minted a token for ``role`` in this test, return it;
    otherwise create a fresh user + token. Used by combo tests."""
    email = f"{role.value}@example.com"
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    if r.status_code == 200:
        return r.json()["access_token"]
    return await _token_for(role, client, app_session)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "endpoint",
    ["deactivate", "reactivate", "reset-password"],
)
@pytest.mark.parametrize(
    "role,expected_when_owner",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 403),
        (Role.PRODUCTION, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_action_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    endpoint: str,
    role: Role,
    expected_when_owner: int,
) -> None:
    await create_user(
        app_session,
        email="target@example.com",
        password="pw",
        full_name="Target",
        role=Role.SALES,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    token = await _token_for(role, client, app_session)
    owner_token = await _token_for_or_existing(Role.OWNER, client, app_session, token)
    listing = await client.get("/api/v1/users", headers=_headers(owner_token))
    target = next(u for u in listing.json()["items"] if u["email"] == "target@example.com")
    r = await client.post(f"/api/v1/users/{target['id']}/{endpoint}", headers=_headers(token))
    assert r.status_code == expected_when_owner, r.text


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/users")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_create_returns_password_once(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/users",
        headers=_headers(token),
        json={
            "email": "FreshUser@Example.COM",
            "full_name": "Fresh User",
            "role": "bookkeeper",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["email"] == "freshuser@example.com"  # lowercased
    assert body["user"]["role"] == "bookkeeper"
    assert body["user"]["is_active"] is True
    pwd = body["generated_password"]
    assert isinstance(pwd, str)
    assert len(pwd) == 20

    # New user can log in with that password right away.
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "freshuser@example.com", "password": pwd},
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_create_duplicate_email_400(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r1 = await client.post(
        "/api/v1/users",
        headers=_headers(token),
        json={"email": "dup@example.com", "full_name": "Dup", "role": "sales"},
    )
    assert r1.status_code == 201, r1.text
    r2 = await client.post(
        "/api/v1/users",
        headers=_headers(token),
        json={"email": "dup@example.com", "full_name": "Dup", "role": "sales"},
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_list_filters_and_search(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    for email, name, role in [
        ("alice@example.com", "Alice Apple", "sales"),
        ("bob@example.com", "Bob Banana", "production"),
        ("carol@example.com", "Carol Cherry", "sales"),
    ]:
        await client.post(
            "/api/v1/users",
            headers=_headers(token),
            json={"email": email, "full_name": name, "role": role},
        )

    # search by substring of name
    r = await client.get("/api/v1/users?search=banana", headers=_headers(token))
    assert r.status_code == 200
    emails = [u["email"] for u in r.json()["items"]]
    assert emails == ["bob@example.com"]

    # filter by role
    r = await client.get("/api/v1/users?role=sales", headers=_headers(token))
    emails = sorted(u["email"] for u in r.json()["items"])
    assert emails == ["alice@example.com", "carol@example.com"]

    # filter by is_active
    r = await client.get("/api/v1/users?is_active=true", headers=_headers(token))
    assert all(u["is_active"] is True for u in r.json()["items"])


@pytest.mark.asyncio
async def test_patch_updates_fields(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/users",
        headers=_headers(token),
        json={"email": "user@example.com", "full_name": "Original", "role": "sales"},
    )
    uid = create.json()["user"]["id"]
    r = await client.patch(
        f"/api/v1/users/{uid}",
        headers=_headers(token),
        json={"full_name": "Renamed", "role": "production"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["full_name"] == "Renamed"
    assert body["role"] == "production"


@pytest.mark.asyncio
async def test_reset_password_returns_new_password_once(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/users",
        headers=_headers(token),
        json={"email": "rp@example.com", "full_name": "Reset Me", "role": "sales"},
    )
    uid = create.json()["user"]["id"]

    r = await client.post(f"/api/v1/users/{uid}/reset-password", headers=_headers(token))
    assert r.status_code == 200, r.text
    new_pwd = r.json()["generated_password"]
    assert len(new_pwd) == 20

    # Login with the new password works; old one rejected.
    ok = await client.post(
        "/api/v1/auth/login",
        json={"email": "rp@example.com", "password": new_pwd},
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/users" in paths
    assert "/api/v1/users/{user_id}" in paths
    assert "/api/v1/users/{user_id}/deactivate" in paths
    assert "/api/v1/users/{user_id}/reactivate" in paths
    assert "/api/v1/users/{user_id}/reset-password" in paths
