"""Materials API: role matrix + happy paths."""

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


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _seed_receiving_location(client: AsyncClient, owner_token: str) -> None:
    """Phase 3.2: receipts need a default receiving location to land in."""
    await client.post(
        "/api/v1/inventory/locations",
        headers=_h(owner_token),
        json={"name": "Receiving", "code": "RX", "kind": "workshop"},
    )


@pytest.mark.asyncio
async def test_unauthenticated_get_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/materials")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/materials",
        headers=_h(token),
        json={
            "name": f"PLA {role.value}",
            "material_type": "PLA",
            "spool_weight_grams": 1000,
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.BOOKKEEPER, Role.PRODUCTION, Role.SALES, Role.VIEWER],
)
async def test_list_visible_to_every_authenticated_role(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.get("/api/v1/materials", headers=_h(token))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={
            "name": "Standard PLA",
            "brand": "Polymaker",
            "material_type": "PLA",
            "spool_weight_grams": 1000,
            "color": "red",
            "density_g_per_cm3": "1.24",
        },
    )
    assert create.status_code == 201, create.text
    mid = create.json()["id"]
    assert create.json()["current_cost_per_gram"] == "0.00"
    assert create.json()["total_on_hand"] == "0.00"
    assert create.json()["per_location_on_hand"] == {}

    # GET
    got = await client.get(f"/api/v1/materials/{mid}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["recent_receipts"] == []

    # PATCH
    patched = await client.patch(
        f"/api/v1/materials/{mid}",
        headers=_h(owner),
        json={"name": "Standard PLA Pro"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Standard PLA Pro"

    # Archive (owner-only)
    arch = await client.post(f"/api/v1/materials/{mid}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    # Unarchive
    un = await client.post(f"/api/v1/materials/{mid}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_archived"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.PRODUCTION, 403),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_archive_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    mid = create.json()["id"]

    if role == Role.OWNER:
        token = owner
    else:
        token = await _token_for(role, client, app_session)
    r = await client.post(f"/api/v1/materials/{mid}/archive", headers=_h(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 201),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_record_receipt_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    await _seed_receiving_location(client, owner)
    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": f"PLA-{role.value}", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    mid = create.json()["id"]
    token = owner if role == Role.OWNER else await _token_for(role, client, app_session)
    r = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(token),
        json={"spools": 1, "extra_grams": "0", "price_per_spool": "20.00"},
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_record_receipt_updates_cost_in_response(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    await _seed_receiving_location(client, owner)
    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    mid = create.json()["id"]
    r = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(owner),
        json={"spools": 1, "extra_grams": "0", "price_per_spool": "20000.00"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["current_cost_per_gram"] == "20.00"
    assert body["total_on_hand"] == "1000.00"


@pytest.mark.asyncio
async def test_record_receipt_validation_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    mid = create.json()["id"]
    # zero quantity → 422 (model validator)
    r = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(owner),
        json={"spools": 0, "extra_grams": "0", "price_per_spool": "1.00"},
    )
    assert r.status_code in (400, 422), r.text
    # negative price → 422 (Pydantic Field(ge=0))
    r = await client.post(
        f"/api/v1/materials/{mid}/receipts",
        headers=_h(owner),
        json={"spools": 1, "extra_grams": "0", "price_per_spool": "-1.00"},
    )
    assert r.status_code in (400, 422), r.text


@pytest.mark.asyncio
async def test_list_receipts_pagination(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    await _seed_receiving_location(client, owner)
    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA", "material_type": "PLA", "spool_weight_grams": 1000},
    )
    mid = create.json()["id"]
    for _ in range(3):
        await client.post(
            f"/api/v1/materials/{mid}/receipts",
            headers=_h(owner),
            json={"spools": 1, "extra_grams": "0", "price_per_spool": "5.00"},
        )

    page = await client.get(f"/api/v1/materials/{mid}/receipts?limit=2", headers=_h(owner))
    assert page.status_code == 200
    body = page.json()
    assert len(body["items"]) == 2
    assert body["next_cursor"]


@pytest.mark.asyncio
async def test_list_search_and_archived_filter(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    for name, color in [("Red Material", "red"), ("Blue Material", "blue")]:
        await client.post(
            "/api/v1/materials",
            headers=_h(owner),
            json={
                "name": name,
                "material_type": "PLA",
                "color": color,
                "spool_weight_grams": 1000,
            },
        )
    r = await client.get("/api/v1/materials?search=red", headers=_h(owner))
    assert r.status_code == 200
    names = [m["name"] for m in r.json()["items"]]
    assert names == ["Red Material"]

    # Archive one and filter.
    create = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "Ghost", "material_type": "PETG", "spool_weight_grams": 1000},
    )
    mid = create.json()["id"]
    await client.post(f"/api/v1/materials/{mid}/archive", headers=_h(owner))
    r = await client.get("/api/v1/materials?is_archived=true", headers=_h(owner))
    assert [m["name"] for m in r.json()["items"]] == ["Ghost"]


@pytest.mark.asyncio
async def test_create_duplicate_active_triple_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    body = {
        "name": "PLA",
        "brand": "X",
        "material_type": "PLA",
        "spool_weight_grams": 1000,
        "color": "red",
    }
    r1 = await client.post("/api/v1/materials", headers=_h(owner), json=body)
    assert r1.status_code == 201, r1.text
    r2 = await client.post("/api/v1/materials", headers=_h(owner), json=body)
    assert r2.status_code == 400, r2.text


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/materials" in paths
    assert "/api/v1/materials/{material_id}" in paths
    assert "/api/v1/materials/{material_id}/archive" in paths
    assert "/api/v1/materials/{material_id}/unarchive" in paths
    assert "/api/v1/materials/{material_id}/receipts" in paths
