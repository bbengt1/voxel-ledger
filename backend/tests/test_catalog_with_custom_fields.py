"""Catalog round-trip: define a custom field, POST/PATCH entity, archive
the field, and confirm stored value persists."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _owner_token(client: AsyncClient, session: AsyncSession) -> str:
    email = "owner@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="owner",
        role=Role.OWNER,
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
async def test_material_round_trip_with_custom_field(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _owner_token(client, app_session)
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
    assert cf.status_code == 201, cf.text
    cf_id = cf.json()["id"]

    # Create material with the custom_field set.
    mat = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={
            "name": "PLA Bright Red",
            "material_type": "PLA",
            "custom_fields": {"supplier_code": "ACME-123"},
        },
    )
    assert mat.status_code == 201, mat.text
    body = mat.json()
    assert body["custom_fields"] == {"supplier_code": "ACME-123"}
    mat_id = body["id"]

    # GET it back; value present.
    got = await client.get(f"/api/v1/materials/{mat_id}", headers=_h(owner))
    assert got.status_code == 200
    assert got.json()["custom_fields"] == {"supplier_code": "ACME-123"}

    # Archive the field; the row value still persists.
    arch = await client.post(f"/api/v1/custom-fields/{cf_id}/archive", headers=_h(owner))
    assert arch.status_code == 200

    again = await client.get(f"/api/v1/materials/{mat_id}", headers=_h(owner))
    assert again.json()["custom_fields"] == {"supplier_code": "ACME-123"}

    # Active definitions list no longer includes the archived field.
    listed = await client.get("/api/v1/custom-fields?entity_type=material", headers=_h(owner))
    keys = [row["key"] for row in listed.json()["items"]]
    assert "supplier_code" not in keys


@pytest.mark.asyncio
async def test_required_missing_returns_400(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await _owner_token(client, app_session)
    await client.post(
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

    mat = await client.post(
        "/api/v1/materials",
        headers=_h(owner),
        json={"name": "PLA Sand", "material_type": "PLA"},
    )
    assert mat.status_code == 400, mat.text


@pytest.mark.asyncio
async def test_select_invalid_value_returns_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _owner_token(client, app_session)
    await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "product",
            "key": "grade",
            "label": "Grade",
            "field_type": "select",
            "options": [
                {"value": "a", "label": "A"},
                {"value": "b", "label": "B"},
            ],
        },
    )

    bad = await client.post(
        "/api/v1/products",
        headers=_h(owner),
        json={
            "name": "Widget",
            "unit_price": "10.00",
            "custom_fields": {"grade": "z"},
        },
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_supply_and_rate_carry_custom_fields(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _owner_token(client, app_session)
    await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "supply",
            "key": "msds_url",
            "label": "MSDS URL",
            "field_type": "string",
        },
    )
    await client.post(
        "/api/v1/custom-fields",
        headers=_h(owner),
        json={
            "entity_type": "rate",
            "key": "notes",
            "label": "Notes",
            "field_type": "string",
        },
    )

    s = await client.post(
        "/api/v1/supplies",
        headers=_h(owner),
        json={
            "name": "Cleaner",
            "unit": "ml",
            "unit_cost": "0.05",
            "custom_fields": {"msds_url": "https://example.com/msds"},
        },
    )
    assert s.status_code == 201, s.text
    assert s.json()["custom_fields"]["msds_url"] == "https://example.com/msds"

    r = await client.post(
        "/api/v1/rates",
        headers=_h(owner),
        json={
            "name": "Labor",
            "kind": "labor",
            "value": "25.00",
            "custom_fields": {"notes": "second shift only"},
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["custom_fields"]["notes"] == "second shift only"
