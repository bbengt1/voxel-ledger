"""Notes API: role matrix, author-vs-owner gating, pin/unpin."""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-{uuid.uuid4().hex[:6]}@example.com"
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


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _entity() -> tuple[str, str]:
    return "material", str(uuid.uuid4())


@pytest.mark.asyncio
async def test_unauthenticated_get_401(client: AsyncClient) -> None:
    kind, ent = _entity()
    r = await client.get(f"/api/v1/notes?entity_kind={kind}&entity_id={ent}")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.BOOKKEEPER, 201),
        (Role.SALES, 201),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected: int,
) -> None:
    token = await _token_for(role, client, app_session)
    kind, ent = _entity()
    r = await client.post(
        "/api/v1/notes",
        headers=_h(token),
        json={"entity_kind": kind, "entity_id": ent, "body": "hello"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_visible_to_every_authenticated_role(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    kind, ent = _entity()
    await client.post(
        "/api/v1/notes",
        headers=_h(owner),
        json={"entity_kind": kind, "entity_id": ent, "body": "first"},
    )
    for role in [
        Role.OWNER,
        Role.BOOKKEEPER,
        Role.PRODUCTION,
        Role.SALES,
        Role.VIEWER,
    ]:
        tok = await _token_for(role, client, app_session)
        r = await client.get(
            f"/api/v1/notes?entity_kind={kind}&entity_id={ent}",
            headers=_h(tok),
        )
        assert r.status_code == 200, r.text
        assert any(n["body"] == "first" for n in r.json()["items"])


@pytest.mark.asyncio
async def test_unsupported_entity_kind_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/notes",
        headers=_h(owner),
        json={"entity_kind": "alien", "entity_id": str(uuid.uuid4()), "body": "x"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_author_can_update_and_delete_own_note(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    prod = await _token_for(Role.PRODUCTION, client, app_session)
    kind, ent = _entity()
    create = await client.post(
        "/api/v1/notes",
        headers=_h(prod),
        json={"entity_kind": kind, "entity_id": ent, "body": "original"},
    )
    nid = create.json()["id"]

    upd = await client.patch(
        f"/api/v1/notes/{nid}",
        headers=_h(prod),
        json={"body": "edited"},
    )
    assert upd.status_code == 200
    assert upd.json()["body"] == "edited"

    dele = await client.delete(f"/api/v1/notes/{nid}", headers=_h(prod))
    assert dele.status_code == 204


@pytest.mark.asyncio
async def test_non_author_non_owner_cannot_update_or_delete(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    author = await _token_for(Role.PRODUCTION, client, app_session)
    other = await _token_for(Role.SALES, client, app_session)
    kind, ent = _entity()
    nid = (
        await client.post(
            "/api/v1/notes",
            headers=_h(author),
            json={"entity_kind": kind, "entity_id": ent, "body": "yours"},
        )
    ).json()["id"]

    upd = await client.patch(
        f"/api/v1/notes/{nid}",
        headers=_h(other),
        json={"body": "hijack"},
    )
    assert upd.status_code == 403

    dele = await client.delete(f"/api/v1/notes/{nid}", headers=_h(other))
    assert dele.status_code == 403


@pytest.mark.asyncio
async def test_owner_can_update_and_delete_any_note(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    author = await _token_for(Role.PRODUCTION, client, app_session)
    owner = await _token_for(Role.OWNER, client, app_session)
    kind, ent = _entity()
    nid = (
        await client.post(
            "/api/v1/notes",
            headers=_h(author),
            json={"entity_kind": kind, "entity_id": ent, "body": "draft"},
        )
    ).json()["id"]

    upd = await client.patch(
        f"/api/v1/notes/{nid}",
        headers=_h(owner),
        json={"body": "owner edit"},
    )
    assert upd.status_code == 200

    dele = await client.delete(f"/api/v1/notes/{nid}", headers=_h(owner))
    assert dele.status_code == 204


@pytest.mark.asyncio
async def test_only_owner_can_pin_and_unpin(client: AsyncClient, app_session: AsyncSession) -> None:
    author = await _token_for(Role.PRODUCTION, client, app_session)
    owner = await _token_for(Role.OWNER, client, app_session)
    kind, ent = _entity()
    nid = (
        await client.post(
            "/api/v1/notes",
            headers=_h(author),
            json={"entity_kind": kind, "entity_id": ent, "body": "pinme"},
        )
    ).json()["id"]

    # Author (non-owner) cannot pin.
    nope = await client.post(f"/api/v1/notes/{nid}/pin", headers=_h(author))
    assert nope.status_code == 403

    pin = await client.post(f"/api/v1/notes/{nid}/pin", headers=_h(owner))
    assert pin.status_code == 200
    assert pin.json()["is_pinned"] is True

    unp = await client.post(f"/api/v1/notes/{nid}/unpin", headers=_h(owner))
    assert unp.status_code == 200
    assert unp.json()["is_pinned"] is False


@pytest.mark.asyncio
async def test_list_orders_pinned_first(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    kind, ent = _entity()
    # Create three notes; pin the middle one.
    ids: list[str] = []
    for body in ("alpha", "beta", "gamma"):
        r = await client.post(
            "/api/v1/notes",
            headers=_h(owner),
            json={"entity_kind": kind, "entity_id": ent, "body": body},
        )
        ids.append(r.json()["id"])
    await client.post(f"/api/v1/notes/{ids[1]}/pin", headers=_h(owner))

    listing = await client.get(
        f"/api/v1/notes?entity_kind={kind}&entity_id={ent}",
        headers=_h(owner),
    )
    rows = listing.json()["items"]
    assert rows[0]["body"] == "beta"
    assert rows[0]["is_pinned"] is True
    assert all(r["is_pinned"] is False for r in rows[1:])
