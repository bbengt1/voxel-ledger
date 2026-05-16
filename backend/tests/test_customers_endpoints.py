"""Customers endpoint tests (Phase 7.1, #109).

Role matrix, CRUD round-trip, archive/unarchive, and ``?search=``
case-insensitive partial match.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._customers_helpers import auth_header, token_for


def _sample_body(**overrides):
    body = {
        "display_name": "Acme Co.",
        "legal_name": "Acme Holdings, LLC",
        "primary_email": "ap@acme.example",
        "phone": "+1 555 0100",
        "payment_terms_days": 30,
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
    r = await client.post("/api/v1/customers", json=_sample_body(), headers=auth_header(token))
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["display_name"] == "Acme Co."
    assert created["customer_number"].startswith("CUST-")
    assert created["state"] == "active"
    assert created["payment_terms_days"] == 30
    assert created["billing_address"]["city"] == "Springfield"

    cid = created["id"]
    r2 = await client.get(f"/api/v1/customers/{cid}", headers=auth_header(token))
    assert r2.status_code == 200
    assert r2.json()["id"] == cid


@pytest.mark.asyncio
async def test_update_and_archive_unarchive(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post("/api/v1/customers", json=_sample_body(), headers=auth_header(token))
    cid = r.json()["id"]

    r2 = await client.patch(
        f"/api/v1/customers/{cid}",
        json={"display_name": "Acme (renamed)", "payment_terms_days": 60},
        headers=auth_header(token),
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["display_name"] == "Acme (renamed)"
    assert body["payment_terms_days"] == 60

    r3 = await client.post(f"/api/v1/customers/{cid}/archive", headers=auth_header(token))
    assert r3.status_code == 200
    assert r3.json()["state"] == "archived"

    r4 = await client.post(f"/api/v1/customers/{cid}/unarchive", headers=auth_header(token))
    assert r4.status_code == 200
    assert r4.json()["state"] == "active"


@pytest.mark.asyncio
async def test_search_partial_case_insensitive(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    for name in ["Acme Co.", "Beta Industries", "ACME Northern"]:
        await client.post(
            "/api/v1/customers",
            json=_sample_body(display_name=name),
            headers=auth_header(token),
        )

    r = await client.get("/api/v1/customers?search=acm", headers=auth_header(token))
    assert r.status_code == 200
    names = sorted(c["display_name"] for c in r.json()["items"])
    assert names == ["ACME Northern", "Acme Co."]

    r2 = await client.get("/api/v1/customers?search=Beta", headers=auth_header(token))
    assert [c["display_name"] for c in r2.json()["items"]] == ["Beta Industries"]


@pytest.mark.asyncio
async def test_list_filters_by_state(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/customers",
        json=_sample_body(display_name="Active One"),
        headers=auth_header(token),
    )
    a_id = r.json()["id"]
    r = await client.post(
        "/api/v1/customers",
        json=_sample_body(display_name="To Archive"),
        headers=auth_header(token),
    )
    b_id = r.json()["id"]
    await client.post(f"/api/v1/customers/{b_id}/archive", headers=auth_header(token))

    r = await client.get("/api/v1/customers?state=active", headers=auth_header(token))
    assert {c["id"] for c in r.json()["items"]} == {a_id}

    r = await client.get("/api/v1/customers?state=archived", headers=auth_header(token))
    assert {c["id"] for c in r.json()["items"]} == {b_id}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected_create",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 201),
        (Role.SALES, 201),
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
    r = await client.post("/api/v1/customers", json=_sample_body(), headers=auth_header(token))
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
    r = await client.get("/api/v1/customers", headers=auth_header(token))
    assert r.status_code == expected_read
