"""Sales API: role matrix + CRUD + state transitions (Phase 6.2, #94)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import auth_header, sample_sale_body, seed_channel, token_for


@pytest.mark.asyncio
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/sales")
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
    channel = await seed_channel(app_session)
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/sales",
        headers=auth_header(token),
        json=sample_sale_body(channel_id=str(channel.id)),
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
    r = await client.get("/api/v1/sales", headers=auth_header(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_get_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["state"] == "draft"
    assert body["sale_number"].startswith("SO-")
    assert len(body["items"]) == 1
    assert body["items"][0]["line_number"] == 1

    got = await client.get(f"/api/v1/sales/{body['id']}", headers=auth_header(owner))
    assert got.status_code == 200
    assert got.json()["sale_number"] == body["sale_number"]


@pytest.mark.asyncio
async def test_update_draft_replaces_items_and_replays_totals(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    sale_id = create.json()["id"]

    patched = await client.patch(
        f"/api/v1/sales/{sale_id}",
        headers=auth_header(owner),
        json={
            "items": [
                {
                    "kind": "manual",
                    "description": "Widget A",
                    "quantity": "1",
                    "unit_price": "50",
                },
                {
                    "kind": "manual",
                    "description": "Widget B",
                    "quantity": "3",
                    "unit_price": "25",
                },
            ],
            "shipping_amount": "10",
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    # subtotal = 50 + 75 = 125
    assert body["subtotal"].rstrip("0").rstrip(".") in ("125", "125.")
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_update_after_confirm_is_blocked(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    sale_id = create.json()["id"]
    confirm = await client.post(f"/api/v1/sales/{sale_id}/confirm", headers=auth_header(owner))
    assert confirm.status_code == 200

    patched = await client.patch(
        f"/api/v1/sales/{sale_id}",
        headers=auth_header(owner),
        json={"customer_name": "Other"},
    )
    assert patched.status_code == 400


@pytest.mark.asyncio
async def test_state_machine_draft_confirmed_fulfilled(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    sale_id = create.json()["id"]

    r1 = await client.post(f"/api/v1/sales/{sale_id}/confirm", headers=auth_header(owner))
    assert r1.status_code == 200 and r1.json()["state"] == "confirmed"

    r2 = await client.post(f"/api/v1/sales/{sale_id}/fulfill", headers=auth_header(owner))
    assert r2.status_code == 200 and r2.json()["state"] == "fulfilled"

    # fulfill again -> 400 (terminal)
    r3 = await client.post(f"/api/v1/sales/{sale_id}/fulfill", headers=auth_header(owner))
    assert r3.status_code == 400


@pytest.mark.asyncio
async def test_state_machine_illegal_transition_draft_to_fulfilled(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    sale_id = create.json()["id"]
    # draft -> fulfilled is not allowed.
    r = await client.post(f"/api/v1/sales/{sale_id}/fulfill", headers=auth_header(owner))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cancel_from_draft(client: AsyncClient, app_session: AsyncSession) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    sale_id = create.json()["id"]
    r = await client.post(f"/api/v1/sales/{sale_id}/cancel", headers=auth_header(owner))
    assert r.status_code == 200 and r.json()["state"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    channel = await seed_channel(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(channel.id)),
    )
    sale_id = create.json()["id"]
    viewer = await token_for(Role.VIEWER, client, app_session)
    r = await client.post(f"/api/v1/sales/{sale_id}/cancel", headers=auth_header(viewer))
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/sales/00000000-0000-0000-0000-000000000000",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_create_unknown_channel_400(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id="00000000-0000-0000-0000-000000000000"),
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_filter_by_state_and_channel(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    ch1 = await seed_channel(app_session, name="Etsy", slug="etsy")
    ch2 = await seed_channel(app_session, name="Shopify", slug="shopify", fee_percent="0.029")
    owner = await token_for(Role.OWNER, client, app_session)

    a = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(ch1.id)),
    )
    b = await client.post(
        "/api/v1/sales",
        headers=auth_header(owner),
        json=sample_sale_body(channel_id=str(ch2.id)),
    )
    assert a.status_code == 201 and b.status_code == 201
    await client.post(f"/api/v1/sales/{b.json()['id']}/confirm", headers=auth_header(owner))

    r = await client.get(f"/api/v1/sales?channel_id={ch1.id}", headers=auth_header(owner))
    ids = {item["id"] for item in r.json()["items"]}
    assert ids == {a.json()["id"]}

    r = await client.get("/api/v1/sales?state=confirmed", headers=auth_header(owner))
    ids = {item["id"] for item in r.json()["items"]}
    assert ids == {b.json()["id"]}


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/sales" in paths
    assert "/api/v1/sales/{sale_id}" in paths
    assert "/api/v1/sales/{sale_id}/confirm" in paths
    assert "/api/v1/sales/{sale_id}/fulfill" in paths
    assert "/api/v1/sales/{sale_id}/cancel" in paths
