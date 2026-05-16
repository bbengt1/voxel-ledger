"""Vendors endpoint tests (Phase 8.1, #128).

Role matrix, CRUD round-trip, archive/unarchive, and ``?search=``
case-insensitive partial match.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._vendors_helpers import auth_header, token_for


def _sample_body(**overrides):
    body = {
        "display_name": "Acme Supplies",
        "legal_name": "Acme Supplies, LLC",
        "primary_email": "ar@acmesupp.example",
        "phone": "+1 555 0100",
        "payment_terms_days": 30,
        "tax_id": "12-3456789",
        "is_1099_vendor": False,
        "billing_address": {
            "line1": "1 Main St",
            "city": "Springfield",
            "region": "IL",
            "postal_code": "62701",
            "country": "US",
        },
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_create_and_get_round_trip(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post("/api/v1/vendors", json=_sample_body(), headers=auth_header(token))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["display_name"] == "Acme Supplies"
    assert created["vendor_number"].startswith("VEND-")
    assert created["state"] == "active"
    assert created["payment_terms_days"] == 30
    assert created["billing_address"]["city"] == "Springfield"
    assert created["tax_id"] == "12-3456789"
    assert created["is_1099_vendor"] is False

    vid = created["id"]
    r2 = await client.get(f"/api/v1/vendors/{vid}", headers=auth_header(token))
    assert r2.status_code == 200
    assert r2.json()["id"] == vid


@pytest.mark.asyncio
async def test_update_and_archive_unarchive(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post("/api/v1/vendors", json=_sample_body(), headers=auth_header(token))
    vid = r.json()["id"]

    r2 = await client.patch(
        f"/api/v1/vendors/{vid}",
        json={"display_name": "Acme (renamed)", "payment_terms_days": 60, "is_1099_vendor": True},
        headers=auth_header(token),
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["display_name"] == "Acme (renamed)"
    assert body["payment_terms_days"] == 60
    assert body["is_1099_vendor"] is True

    r3 = await client.post(f"/api/v1/vendors/{vid}/archive", headers=auth_header(token))
    assert r3.status_code == 200
    assert r3.json()["state"] == "archived"

    r4 = await client.post(f"/api/v1/vendors/{vid}/unarchive", headers=auth_header(token))
    assert r4.status_code == 200
    assert r4.json()["state"] == "active"


@pytest.mark.asyncio
async def test_search_partial_case_insensitive(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    for name in ["Acme Supplies", "Beta Industries", "ACME Northern"]:
        await client.post(
            "/api/v1/vendors",
            json=_sample_body(display_name=name),
            headers=auth_header(token),
        )

    r = await client.get("/api/v1/vendors?search=acm", headers=auth_header(token))
    assert r.status_code == 200
    names = sorted(v["display_name"] for v in r.json()["items"])
    assert names == ["ACME Northern", "Acme Supplies"]

    r2 = await client.get("/api/v1/vendors?search=Beta", headers=auth_header(token))
    assert [v["display_name"] for v in r2.json()["items"]] == ["Beta Industries"]


@pytest.mark.asyncio
async def test_list_filters_by_state(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/vendors",
        json=_sample_body(display_name="Active One"),
        headers=auth_header(token),
    )
    a_id = r.json()["id"]
    r = await client.post(
        "/api/v1/vendors",
        json=_sample_body(display_name="To Archive"),
        headers=auth_header(token),
    )
    b_id = r.json()["id"]
    await client.post(f"/api/v1/vendors/{b_id}/archive", headers=auth_header(token))

    r = await client.get("/api/v1/vendors?state=active", headers=auth_header(token))
    assert {v["id"] for v in r.json()["items"]} == {a_id}

    r = await client.get("/api/v1/vendors?state=archived", headers=auth_header(token))
    assert {v["id"] for v in r.json()["items"]} == {b_id}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected_create",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 201),
        (Role.SALES, 403),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected_create: int,
):
    token = await token_for(role, client, app_session)
    r = await client.post("/api/v1/vendors", json=_sample_body(), headers=auth_header(token))
    assert r.status_code == expected_create, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected_read",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.SALES, 200),
        (Role.VIEWER, 200),
        (Role.PRODUCTION, 403),
    ],
)
async def test_list_role_matrix(
    client: AsyncClient,
    app_session: AsyncSession,
    role: Role,
    expected_read: int,
):
    token = await token_for(role, client, app_session)
    r = await client.get("/api/v1/vendors", headers=auth_header(token))
    assert r.status_code == expected_read
