"""Jobs API: role matrix + happy paths (Phase 5.2, #78)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_product, token_for


def _payload(product_id: str) -> dict:
    return {
        "product_id": product_id,
        "quantity_ordered": 10,
        "priority": 0,
        "plates": [
            {
                "name": "Plate A",
                "plate_number": 1,
                "parts_per_set": 2,
                "print_minutes": 30,
                "print_grams_by_material": {},
                "print_hours_setup_minutes": 0,
                "assigned_printer_ids": [],
            }
        ],
    }


@pytest.mark.asyncio
async def test_unauthenticated_list_401(client: AsyncClient) -> None:
    r = await client.get("/api/v1/jobs")
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
    product = await seed_product(app_session)
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/jobs",
        headers=auth_header(token),
        json=_payload(str(product.id)),
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
    r = await client.get("/api/v1/jobs", headers=auth_header(token))
    assert r.status_code == expected, r.text


@pytest.mark.asyncio
async def test_create_get_happy_path(client: AsyncClient, app_session: AsyncSession) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)

    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json=_payload(str(product.id)),
    )
    assert create.status_code == 201, create.text
    body = create.json()
    assert body["state"] == "draft"
    assert body["quantity_ordered"] == 10
    assert body["pieces_produced"] == 0
    assert body["job_number"].startswith("JOB-")
    assert len(body["plates"]) == 1

    job_id = body["id"]
    got = await client.get(f"/api/v1/jobs/{job_id}", headers=auth_header(owner))
    assert got.status_code == 200
    assert got.json()["job_number"] == body["job_number"]


@pytest.mark.asyncio
async def test_create_rejects_zero_plates(client: AsyncClient, app_session: AsyncSession) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    payload = _payload(str(product.id))
    payload["plates"] = []
    r = await client.post("/api/v1/jobs", headers=auth_header(owner), json=payload)
    assert r.status_code in (400, 422)


@pytest.mark.asyncio
async def test_create_rejects_unknown_product(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    payload = _payload("00000000-0000-0000-0000-000000000000")
    r = await client.post("/api/v1/jobs", headers=auth_header(owner), json=payload)
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.get(
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000",
        headers=auth_header(owner),
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_in_openapi(client: AsyncClient) -> None:
    r = await client.get("/api/v1/openapi.json")
    paths = r.json()["paths"]
    assert "/api/v1/jobs" in paths
    assert "/api/v1/jobs/{job_id}" in paths
    assert "/api/v1/jobs/{job_id}/submit" in paths
    assert "/api/v1/jobs/{job_id}/start" in paths
    assert "/api/v1/jobs/{job_id}/complete" in paths
    assert "/api/v1/jobs/{job_id}/cancel" in paths
    assert "/api/v1/jobs/{job_id}/plates" in paths
    assert "/api/v1/jobs/{job_id}/plates/{plate_id}" in paths
    assert "/api/v1/jobs/{job_id}/plates/{plate_id}/assign-printer" in paths
    assert "/api/v1/jobs/{job_id}/plates/{plate_id}/unassign-printer" in paths
    assert "/api/v1/jobs/{job_id}/plates/{plate_id}/record-run" in paths
