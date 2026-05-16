"""Vendor contacts tests (Phase 8.1, #128).

Add / update / remove contacts, multiple contacts on one vendor, and
the ``is_primary`` uniqueness invariant.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._vendors_helpers import auth_header, token_for


async def _create_vendor(client: AsyncClient, token: str) -> str:
    r = await client.post(
        "/api/v1/vendors",
        json={"display_name": "Acme Supplies", "payment_terms_days": 30},
        headers=auth_header(token),
    )
    assert r.status_code == 201
    return r.json()["id"]


@pytest.mark.asyncio
async def test_add_update_remove_contact(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    vid = await _create_vendor(client, token)

    r = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "Pat AR", "email": "pat@acmesupp.example", "role_label": "AR clerk"},
        headers=auth_header(token),
    )
    assert r.status_code == 201
    contact_id = r.json()["id"]
    assert r.json()["is_primary"] is False

    r = await client.patch(
        f"/api/v1/vendors/{vid}/contacts/{contact_id}",
        json={"role_label": "Owner"},
        headers=auth_header(token),
    )
    assert r.status_code == 200
    assert r.json()["role_label"] == "Owner"

    r = await client.delete(
        f"/api/v1/vendors/{vid}/contacts/{contact_id}",
        headers=auth_header(token),
    )
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_multiple_contacts_one_vendor(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    vid = await _create_vendor(client, token)

    for name in ["Alice", "Bob", "Carol"]:
        r = await client.post(
            f"/api/v1/vendors/{vid}/contacts",
            json={"name": name},
            headers=auth_header(token),
        )
        assert r.status_code == 201

    r = await client.get(f"/api/v1/vendors/{vid}", headers=auth_header(token))
    assert {c["name"] for c in r.json()["contacts"]} == {"Alice", "Bob", "Carol"}


@pytest.mark.asyncio
async def test_is_primary_uniqueness_on_add(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    vid = await _create_vendor(client, token)

    r = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "First", "is_primary": True},
        headers=auth_header(token),
    )
    assert r.status_code == 201

    r2 = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "Second", "is_primary": True},
        headers=auth_header(token),
    )
    assert r2.status_code == 400
    assert "primary" in r2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_is_primary_uniqueness_on_update(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    vid = await _create_vendor(client, token)

    r1 = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "First", "is_primary": True},
        headers=auth_header(token),
    )
    assert r1.status_code == 201

    r2 = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "Second"},
        headers=auth_header(token),
    )
    second_id = r2.json()["id"]

    r3 = await client.patch(
        f"/api/v1/vendors/{vid}/contacts/{second_id}",
        json={"is_primary": True},
        headers=auth_header(token),
    )
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_is_primary_can_be_set_after_demoting(client: AsyncClient, app_session: AsyncSession):
    token = await token_for(Role.OWNER, client, app_session)
    vid = await _create_vendor(client, token)

    r1 = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "First", "is_primary": True},
        headers=auth_header(token),
    )
    first_id = r1.json()["id"]

    r2 = await client.post(
        f"/api/v1/vendors/{vid}/contacts",
        json={"name": "Second"},
        headers=auth_header(token),
    )
    second_id = r2.json()["id"]

    r3 = await client.patch(
        f"/api/v1/vendors/{vid}/contacts/{first_id}",
        json={"is_primary": False},
        headers=auth_header(token),
    )
    assert r3.status_code == 200

    r4 = await client.patch(
        f"/api/v1/vendors/{vid}/contacts/{second_id}",
        json={"is_primary": True},
        headers=auth_header(token),
    )
    assert r4.status_code == 200
    assert r4.json()["is_primary"] is True
