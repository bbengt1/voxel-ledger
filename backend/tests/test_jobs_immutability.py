"""Jobs immutability rules (Phase 5.2, #78).

- ``product_id`` / ``quantity_ordered`` are rejected in PATCH (400).
- Plate mutations are rejected once a job leaves ``draft`` (400).
"""

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
        "plates": [
            {
                "name": "P1",
                "plate_number": 1,
                "parts_per_set": 2,
                "print_minutes": 30,
            }
        ],
    }


@pytest.mark.asyncio
async def test_patch_rejects_immutable_fields(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    job_id = r.json()["id"]

    bad = await client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(owner),
        json={"quantity_ordered": 999},
    )
    assert bad.status_code == 400

    bad = await client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(owner),
        json={"product_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_patch_allows_priority_due_notes(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    job_id = r.json()["id"]

    good = await client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(owner),
        json={"priority": 5, "notes": "rush"},
    )
    assert good.status_code == 200
    assert good.json()["priority"] == 5
    assert good.json()["notes"] == "rush"


@pytest.mark.asyncio
async def test_plate_mutation_blocked_after_leaving_draft(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    job_id = r.json()["id"]
    plate_id = r.json()["plates"][0]["id"]

    sub = await client.post(f"/api/v1/jobs/{job_id}/submit", headers=auth_header(owner))
    assert sub.status_code == 200
    assert sub.json()["state"] == "queued"

    bad = await client.patch(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}",
        headers=auth_header(owner),
        json={"parts_per_set": 99},
    )
    assert bad.status_code == 400

    bad = await client.delete(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}", headers=auth_header(owner)
    )
    assert bad.status_code == 400

    bad = await client.post(
        f"/api/v1/jobs/{job_id}/plates",
        headers=auth_header(owner),
        json={"name": "X", "plate_number": 2, "parts_per_set": 1, "print_minutes": 0},
    )
    assert bad.status_code == 400
