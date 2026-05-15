"""Production orders API: role matrix + CRUD + state transitions (Phase 5.5, #81)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, token_for


def _payload(**overrides) -> dict:
    body = {"name": "March holiday batch", "priority": 5, "notes": "rush"}
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/production-orders")
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
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/production-orders", headers=auth_header(token), json=_payload()
    )
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,expected",
    [
        (Role.OWNER, 200),
        (Role.PRODUCTION, 200),
        (Role.SALES, 200),
        (Role.BOOKKEEPER, 403),
        (Role.VIEWER, 403),
    ],
)
async def test_list_role_matrix(
    client: AsyncClient, app_session: AsyncSession, role: Role, expected: int
) -> None:
    token = await token_for(role, client, app_session)
    r = await client.get("/api/v1/production-orders", headers=auth_header(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_get_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/production-orders", headers=auth_header(owner), json=_payload()
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["state"] == "planning"
    assert body["order_number"].startswith("PO-")
    assert body["jobs"] == []

    got = await client.get(
        f"/api/v1/production-orders/{body['id']}", headers=auth_header(owner)
    )
    assert got.status_code == 200
    assert got.json()["order_number"] == body["order_number"]


@pytest.mark.asyncio
async def test_update_changes_name(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/production-orders", headers=auth_header(owner), json=_payload()
    )
    order_id = created.json()["id"]

    r = await client.patch(
        f"/api/v1/production-orders/{order_id}",
        headers=auth_header(owner),
        json={"name": "April rush"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "April rush"


@pytest.mark.asyncio
async def test_state_machine_planning_active_completed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/production-orders", headers=auth_header(owner), json=_payload()
    )
    order_id = created.json()["id"]

    r1 = await client.post(
        f"/api/v1/production-orders/{order_id}/activate", headers=auth_header(owner)
    )
    assert r1.status_code == 200 and r1.json()["state"] == "active"

    r2 = await client.post(
        f"/api/v1/production-orders/{order_id}/complete", headers=auth_header(owner)
    )
    assert r2.status_code == 200 and r2.json()["state"] == "completed"

    r3 = await client.post(
        f"/api/v1/production-orders/{order_id}/archive", headers=auth_header(owner)
    )
    assert r3.status_code == 200 and r3.json()["state"] == "archived"


@pytest.mark.asyncio
async def test_state_machine_illegal_transition(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    created = await client.post(
        "/api/v1/production-orders", headers=auth_header(owner), json=_payload()
    )
    order_id = created.json()["id"]
    # planning -> completed is not allowed.
    r = await client.post(
        f"/api/v1/production-orders/{order_id}/complete", headers=auth_header(owner)
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/production-orders/00000000-0000-0000-0000-000000000000",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/production-orders" in paths
    assert "/api/v1/production-orders/{order_id}" in paths
    assert "/api/v1/production-orders/{order_id}/activate" in paths
    assert "/api/v1/production-orders/{order_id}/complete" in paths
    assert "/api/v1/production-orders/{order_id}/archive" in paths
    assert "/api/v1/production-orders/{order_id}/jobs" in paths
    assert "/api/v1/production-orders/{order_id}/jobs/{job_id}" in paths
    assert "/api/v1/jobs/discover" in paths


@pytest.mark.asyncio
async def test_discover_endpoint_accepts_any_auth_role(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    viewer = await token_for(Role.VIEWER, client, app_session)
    from pathlib import Path

    sample = (
        Path(__file__).parent / "fixtures" / "prusaslicer_sample.gcode.json"
    ).read_bytes()
    r = await client.post(
        "/api/v1/jobs/discover",
        headers=auth_header(viewer),
        files={"file": ("p.gcode.json", sample, "application/json")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_format"] == "prusaslicer"
    assert body["print_minutes"] > 0


@pytest.mark.asyncio
async def test_discover_endpoint_rejects_unknown(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    from pathlib import Path

    sample = (Path(__file__).parent / "fixtures" / "unknown_sample.gcode.json").read_bytes()
    r = await client.post(
        "/api/v1/jobs/discover",
        headers=auth_header(owner),
        files={"file": ("x.gcode.json", sample, "application/json")},
    )
    assert r.status_code == 415


@pytest.mark.asyncio
async def test_discover_endpoint_requires_auth(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/jobs/discover",
        files={"file": ("x.gcode.json", b"{}", "application/json")},
    )
    assert r.status_code == 401
