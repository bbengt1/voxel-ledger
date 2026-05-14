"""Form-templates API: role matrix, set-default flow, add/remove fields."""

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
        "/api/v1/form-templates",
        headers=_h(token),
        json={
            "entity_type": "material",
            "name": f"Template {role.value}",
        },
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_set_default_flips_previous_default(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    a = await client.post(
        "/api/v1/form-templates",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "name": "Default A",
            "is_default_for_entity_type": True,
        },
    )
    b = await client.post(
        "/api/v1/form-templates",
        headers=_h(owner),
        json={"entity_type": "material", "name": "Template B"},
    )
    aid = a.json()["id"]
    bid = b.json()["id"]

    r = await client.post(f"/api/v1/form-templates/{bid}/set-default", headers=_h(owner))
    assert r.status_code == 200, r.text
    assert r.json()["is_default_for_entity_type"] is True

    # Re-fetch A and confirm previous-default-cleared assertion.
    list_a = await client.get("/api/v1/form-templates?entity_type=material", headers=_h(owner))
    rows = {row["id"]: row for row in list_a.json()["items"]}
    assert rows[aid]["is_default_for_entity_type"] is False
    assert rows[bid]["is_default_for_entity_type"] is True


@pytest.mark.asyncio
async def test_add_and_remove_field(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _token_for(Role.OWNER, client, app_session)
    cf = await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "material",
            "key": "supplier_code",
            "label": "Supplier Code",
            "field_type": "string",
        },
    )
    cf_id = cf.json()["id"]

    t = await client.post(
        "/api/v1/form-templates",
        headers=_h(owner),
        json={"entity_type": "material", "name": "T"},
    )
    tid = t.json()["id"]

    add = await client.post(
        f"/api/v1/form-templates/{tid}/fields",
        headers=_h(owner),
        json={"custom_field_id": cf_id, "display_order": 0},
    )
    assert add.status_code == 201, add.text
    body = add.json()
    assert len(body["fields"]) == 1

    rm = await client.delete(f"/api/v1/form-templates/{tid}/fields/{cf_id}", headers=_h(owner))
    assert rm.status_code == 200
    assert len(rm.json()["fields"]) == 0


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/form-templates" in paths
    assert "/api/v1/form-templates/{template_id}" in paths
    assert "/api/v1/form-templates/{template_id}/set-default" in paths
    assert "/api/v1/form-templates/{template_id}/fields" in paths
    assert "/api/v1/form-templates/{template_id}/fields/{custom_field_id}" in paths
