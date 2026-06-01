"""Jobs edit rules (Phase 5.2, #78; revised #254).

- ``product_id`` is rejected in PATCH (400); ``quantity_ordered`` is now
  editable on non-terminal jobs.
- Plate mutations are allowed while the job is non-terminal (draft /
  queued / in_progress) and rejected once the job is completed/cancelled.
- A plate with recorded runs cannot be deleted.
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
async def test_patch_rejects_product_id_but_allows_quantity(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    job_id = r.json()["id"]

    # product_id stays immutable.
    bad = await client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(owner),
        json={"product_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert bad.status_code == 400

    # quantity_ordered is now editable on a non-terminal job.
    good = await client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(owner),
        json={"quantity_ordered": 25},
    )
    assert good.status_code == 200, good.text
    assert good.json()["quantity_ordered"] == 25


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
async def test_plate_mutation_allowed_while_queued(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Queued (non-terminal) jobs remain editable — #254."""
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

    # Edit a plate on a queued job — now allowed.
    ok = await client.patch(
        f"/api/v1/jobs/{job_id}/plates/{plate_id}",
        headers=auth_header(owner),
        json={"parts_per_set": 99},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["parts_per_set"] == 99

    # Add a new plate on a queued job — allowed.
    add = await client.post(
        f"/api/v1/jobs/{job_id}/plates",
        headers=auth_header(owner),
        json={"name": "X", "plate_number": 2, "parts_per_set": 1, "print_minutes": 0},
    )
    assert add.status_code == 201, add.text


@pytest.mark.asyncio
async def test_plate_mutation_blocked_when_cancelled(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    """Terminal (cancelled) jobs are read-only — plates locked, edits 400."""
    product = await seed_product(app_session)
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/jobs", headers=auth_header(owner), json=_payload(str(product.id))
    )
    job_id = r.json()["id"]
    plate_id = r.json()["plates"][0]["id"]

    cancel = await client.post(f"/api/v1/jobs/{job_id}/cancel", headers=auth_header(owner))
    assert cancel.status_code == 200
    assert cancel.json()["state"] == "cancelled"

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

    # Job-level edits are also rejected on a terminal job.
    bad = await client.patch(
        f"/api/v1/jobs/{job_id}",
        headers=auth_header(owner),
        json={"priority": 3},
    )
    assert bad.status_code == 400
