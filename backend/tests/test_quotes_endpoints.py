"""Quotes API: role matrix + CRUD + state transitions (Phase 7.2, #110)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._quotes_helpers import (
    auth_header,
    sample_quote_body,
    seed_customer,
    token_for,
)


@pytest.mark.asyncio
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/quotes")
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 201),
        (Role.BOOKKEEPER, 201),
        (Role.SALES, 201),
        (Role.PRODUCTION, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_create_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    customer = await seed_customer(app_session)
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/quotes",
        headers=auth_header(token),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.BOOKKEEPER, 200),
        (Role.SALES, 200),
        (Role.VIEWER, 200),
        (Role.PRODUCTION, 403),
    ],
)
async def test_list_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await token_for(role, client, app_session)
    r = await client.get("/api/v1/quotes", headers=auth_header(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_get_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(
        app_session,
        billing_address={"line1": "123 Foo", "city": "Bar"},
    )
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["state"] == "draft"
    assert body["quote_number"].startswith("QT-")
    assert len(body["items"]) == 1
    assert body["items"][0]["line_number"] == 1
    # Billing address snapshot persisted from customer.
    assert body["billing_address_snapshot"]["line1"] == "123 Foo"

    got = await client.get(f"/api/v1/quotes/{body['id']}", headers=auth_header(owner))
    assert got.status_code == 200
    assert got.json()["quote_number"] == body["quote_number"]


@pytest.mark.asyncio
async def test_update_draft_replaces_items_and_replays_totals(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]

    patched = await client.patch(
        f"/api/v1/quotes/{quote_id}",
        headers=auth_header(owner),
        json={
            "items": [
                {"kind": "manual", "description": "A", "quantity": "1", "unit_price": "50"},
                {"kind": "manual", "description": "B", "quantity": "3", "unit_price": "25"},
            ],
            "discount_amount": "10",
            "tax_amount": "5",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    # subtotal = 50 + 75 = 125; total = 125 - 10 + 5 = 120
    assert body["subtotal"].rstrip("0").rstrip(".") in ("125", "125.")
    assert body["total_amount"].rstrip("0").rstrip(".") in ("120", "120.")
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_update_after_send_is_blocked(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    send_r = await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    assert send_r.status_code == 200, send_r.text

    patched = await client.patch(
        f"/api/v1/quotes/{quote_id}",
        headers=auth_header(owner),
        json={"notes": "tweak"},
    )
    assert patched.status_code == 400


@pytest.mark.asyncio
async def test_update_after_accept_is_blocked(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))

    patched = await client.patch(
        f"/api/v1/quotes/{quote_id}",
        headers=auth_header(owner),
        json={"notes": "tweak"},
    )
    assert patched.status_code == 400


@pytest.mark.asyncio
async def test_state_machine_draft_sent_accepted(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]

    r1 = await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    assert r1.status_code == 200 and r1.json()["state"] == "sent"
    assert r1.json()["issued_at"] is not None

    r2 = await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))
    assert r2.status_code == 200 and r2.json()["state"] == "accepted"

    # accept again -> 400 (already accepted)
    r3 = await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_state_machine_illegal_transition_draft_to_accepted(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    r = await client.post(f"/api/v1/quotes/{quote_id}/accept", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_decline_from_sent(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    await client.post(f"/api/v1/quotes/{quote_id}/send", headers=auth_header(owner))
    r = await client.post(f"/api/v1/quotes/{quote_id}/decline", headers=auth_header(owner))
    assert r.status_code == 200 and r.json()["state"] == "declined"


@pytest.mark.asyncio
async def test_cancel_from_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    r = await client.post(f"/api/v1/quotes/{quote_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200 and r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    customer = await seed_customer(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(customer.id)),
    )
    quote_id = create.json()["id"]
    viewer = await token_for(Role.VIEWER, client, app_session)
    r = await client.post(f"/api/v1/quotes/{quote_id}/cancel", headers=auth_header(viewer))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/quotes/00000000-0000-0000-0000-000000000000",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_unknown_customer_400(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id="00000000-0000-0000-0000-000000000000"),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_filter_by_state_and_customer(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    c1 = await seed_customer(app_session, display_name="Acme")
    c2 = await seed_customer(app_session, display_name="Beta")
    owner = await token_for(Role.OWNER, client, app_session)

    a = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(c1.id)),
    )
    b = await client.post(
        "/api/v1/quotes",
        headers=auth_header(owner),
        json=sample_quote_body(customer_id=str(c2.id)),
    )
    assert a.status_code == 201 and b.status_code == 201
    await client.post(f"/api/v1/quotes/{b.json()['id']}/send", headers=auth_header(owner))

    r = await client.get(f"/api/v1/quotes?customer_id={c1.id}", headers=auth_header(owner))
    ids = {item["id"] for item in r.json()["items"]}
    assert ids == {a.json()["id"]}

    r = await client.get("/api/v1/quotes?state=sent", headers=auth_header(owner))
    ids = {item["id"] for item in r.json()["items"]}
    assert ids == {b.json()["id"]}


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/quotes" in paths
    assert "/api/v1/quotes/{quote_id}" in paths
    assert "/api/v1/quotes/{quote_id}/send" in paths
    assert "/api/v1/quotes/{quote_id}/accept" in paths
    assert "/api/v1/quotes/{quote_id}/decline" in paths
    assert "/api/v1/quotes/{quote_id}/expire" in paths
    assert "/api/v1/quotes/{quote_id}/cancel" in paths
    assert "/api/v1/quotes/{quote_id}/convert-to-invoice" in paths
