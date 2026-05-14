"""Custom-fields API: role matrix on CRUD + archive."""

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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.PRODUCTION, 403),
        (Role.BOOKKEEPER, 403),
        (Role.SALES, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix_owner_only(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await _token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/custom-fields",
        headers=_h(token),
        json={
            "entity_type": "material",
            "key": f"supplier_code_{role.value}",
            "label": "Supplier Code",
            "field_type": "string",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_list_visible_to_all_authenticated(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    viewer = await _token_for(Role.VIEWER, client, app_session)
    r = await client.get("/api/v1/custom-fields?entity_type=material", headers=_h(viewer))
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_create_get_patch_archive_unarchive_happy_path(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "supplier_code",
            "label": "Supplier Code",
            "field_type": "string",
            "required": True,
        },
    )
    assert create.status_code == 201, create.text
    cf_id = create.json()["id"]

    got = await client.get(f"/api/v1/custom-fields/{cf_id}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["key"] == "supplier_code"

    patched = await client.patch(
        f"/api/v1/custom-fields/{cf_id}",
        headers=_h(owner),
        json={"label": "Supplier code (vendor)"},
    )
    assert patched.status_code == 200
    assert patched.json()["label"] == "Supplier code (vendor)"

    arch = await client.post(f"/api/v1/custom-fields/{cf_id}/archive", headers=_h(owner))
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    un = await client.post(f"/api/v1/custom-fields/{cf_id}/unarchive", headers=_h(owner))
    assert un.status_code == 200
    assert un.json()["is_archived"] is False


@pytest.mark.asyncio
async def test_invalid_entity_type_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "horse",
            "key": "weight_kg",
            "label": "Weight",
            "field_type": "number",
        },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_invalid_key_pattern_rejected(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "BadKey",
            "label": "x",
            "field_type": "string",
        },
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_select_requires_options(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "grade",
            "label": "Grade",
            "field_type": "select",
        },
    )
    assert r.status_code == 400

    r2 = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "grade",
            "label": "Grade",
            "field_type": "select",
            "options": [
                {"value": "a", "label": "A"},
                {"value": "b", "label": "B"},
            ],
        },
    )
    assert r2.status_code == 201, r2.text


@pytest.mark.asyncio
async def test_duplicate_active_key_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    first = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "supplier_code",
            "label": "Supplier Code",
            "field_type": "string",
        },
    )
    assert first.status_code == 201
    second = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "supplier_code",
            "label": "Another",
            "field_type": "string",
        },
    )
    assert second.status_code == 400


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/custom-fields" in paths
    assert "/api/v1/custom-fields/{custom_field_id}" in paths
    assert "/api/v1/custom-fields/{custom_field_id}/archive" in paths
    assert "/api/v1/custom-fields/{custom_field_id}/unarchive" in paths
