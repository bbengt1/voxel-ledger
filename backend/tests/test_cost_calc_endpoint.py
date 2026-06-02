"""POST /api/v1/jobs/calculate role matrix + happy paths (Phase 5.3, #79)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_part, token_for


def _inputs_payload() -> dict:
    return {
        "inputs": {
            "plates": [
                {
                    "parts_per_set": 1,
                    "print_minutes": 60,
                    "print_grams_by_material": {},
                    "setup_minutes": 0,
                    "assigned_printer_ids": [],
                }
            ],
            "quantity_ordered": 1,
        }
    }


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client: AsyncClient) -> None:
    r = await client.post("/api/v1/jobs/calculate", json=_inputs_payload())
    assert r.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role",
    [Role.OWNER, Role.PRODUCTION, Role.SALES, Role.BOOKKEEPER, Role.VIEWER],
)
async def test_every_authenticated_role_can_calculate(
    client: AsyncClient, app_session: AsyncSession, role: Role
) -> None:
    token = await token_for(role, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(token),
        json=_inputs_payload(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pieces_per_set"] == 1
    assert body["sets_required"] == 1


@pytest.mark.asyncio
async def test_calculate_for_existing_job(
    client: AsyncClient, app_session: AsyncSession, workshop_location
) -> None:
    # Part with parts_per_run=2; order 4 → 2 sets required, 2 pieces/set.
    part = await seed_part(app_session, parts_per_run=2)
    owner = await token_for(Role.OWNER, client, app_session)
    create = await client.post(
        "/api/v1/jobs",
        headers=auth_header(owner),
        json={
            "part_id": str(part.id),
            "quantity_ordered": 4,
        },
    )
    assert create.status_code == 201, create.text
    job_id = create.json()["id"]

    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # 4 pieces ordered / 2 per set = 2 sets.
    assert body["sets_required"] == 2
    assert body["pieces_per_set"] == 2


@pytest.mark.asyncio
async def test_calculate_rejects_neither_job_nor_inputs(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(token),
        json={},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_calculate_rejects_both_job_and_inputs(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(token),
        json={"job_id": str(uuid.uuid4()), **_inputs_payload()},
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_unknown_job_id_returns_404(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(token),
        json={"job_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_inputs_response_shape_has_decimal_strings(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """All cost fields should serialize as strings preserving precision."""
    token = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs/calculate",
        headers=auth_header(token),
        json=_inputs_payload(),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # Pydantic's default Decimal JSON encoding emits strings.
    assert isinstance(body["total_cost"], str)
    # Round-trips through Decimal cleanly.
    Decimal(body["total_cost"])
    Decimal(body["cost_per_piece"])
    Decimal(body["suggested_unit_price"])
