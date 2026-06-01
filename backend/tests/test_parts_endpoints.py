"""Parts API: role matrix, CRUD, validation, list/search (epic #267 Phase 1)."""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token(role: Role, client: AsyncClient, session: AsyncSession) -> str:
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
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_unauthenticated_401(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/parts")).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.SALES, 201),
        (Role.BOOKKEEPER, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token(role, client, app_session)
    r = await client.post(
        "/api/v1/parts",
        headers=_h(token),
        json={"name": f"Widget {role.value}", "print_minutes": 60, "parts_per_run": 2},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_autoallocates_sku_and_roundtrips_recipe(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    material_id = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/parts",
        headers=_h(owner),
        json={
            "name": "Bracket",
            "description": "left bracket",
            "print_minutes": 90,
            "setup_minutes": 5,
            "parts_per_run": 4,
            "print_grams_by_material": {material_id: "12.5"},
            "assigned_printer_ids": [],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["sku"].startswith("PART-")
    assert body["parts_per_run"] == 4
    assert body["print_minutes"] == 90
    assert body["print_grams_by_material"][material_id] == "12.5"
    # Phase 2a: the part_cost projection computes the cost on create (here
    # from print/labor/machine since the random material has no priced
    # receipt). With default rate config it resolves to a value.
    assert body["unit_cost_cached"] is not None

    # Fetch round-trip.
    got = await client.get(f"/api/v1/parts/{body['id']}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["name"] == "Bracket"


@pytest.mark.asyncio
async def test_duplicate_manual_sku_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    first = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "A", "sku": "PART-CUSTOM-1"}
    )
    assert first.status_code == 201
    dup = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "B", "sku": "PART-CUSTOM-1"}
    )
    assert dup.status_code == 400, dup.text


@pytest.mark.asyncio
async def test_parts_per_run_must_be_positive(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "Bad", "parts_per_run": 0}
    )
    # Schema enforces gt=0 → 422.
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_update_and_archive_cycle(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/parts", headers=_h(owner), json={"name": "Editable", "print_minutes": 10}
    )
    pid = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/parts/{pid}",
        headers=_h(owner),
        json={"name": "Renamed", "print_minutes": 20},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Renamed"
    assert patched.json()["print_minutes"] == 20

    arch = await client.post(f"/api/v1/parts/{pid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    unarch = await client.post(f"/api/v1/parts/{pid}/unarchive", headers=_h(owner))
    assert unarch.status_code == 200
    assert unarch.json()["is_archived"] is False


@pytest.mark.asyncio
async def test_list_search_and_archived_filter(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Alpha gear"})
    b = await client.post("/api/v1/parts", headers=_h(owner), json={"name": "Beta gear"})
    await client.post(f"/api/v1/parts/{b.json()['id']}/archive", headers=_h(owner))

    found = await client.get("/api/v1/parts", headers=_h(owner), params={"search": "alpha"})
    names = [p["name"] for p in found.json()["items"]]
    assert "Alpha gear" in names and "Beta gear" not in names

    active = await client.get("/api/v1/parts", headers=_h(owner), params={"is_archived": "false"})
    active_names = [p["name"] for p in active.json()["items"]]
    assert "Beta gear" not in active_names


@pytest.mark.asyncio
async def test_get_unknown_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token(Role.OWNER, client, app_session)
    r = await client.get(f"/api/v1/parts/{uuid.uuid4()}", headers=_h(owner))
    assert r.status_code == 404
