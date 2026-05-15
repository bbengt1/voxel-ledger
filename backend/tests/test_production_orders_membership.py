"""Production-order membership: add/remove/reorder + active-order guard (Phase 5.5, #81)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._jobs_helpers import auth_header, seed_product, token_for


async def _seed_job(client: AsyncClient, token: str, product_id: str) -> str:
    payload = {
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
    r = await client.post("/api/v1/jobs", headers=auth_header(token), json=payload)
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _seed_order(client: AsyncClient, token: str, name: str = "batch") -> str:
    r = await client.post(
        "/api/v1/production-orders",
        headers=auth_header(token),
        json={"name": name, "priority": 0},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_add_remove_job(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    product = await seed_product(app_session)
    job_id = await _seed_job(client, owner, str(product.id))
    order_id = await _seed_order(client, owner)

    add = await client.post(
        f"/api/v1/production-orders/{order_id}/jobs",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert add.status_code == 201, add.text
    assert len(add.json()["jobs"]) == 1
    assert add.json()["jobs"][0]["job_id"] == job_id

    remove = await client.delete(
        f"/api/v1/production-orders/{order_id}/jobs/{job_id}",
        headers=auth_header(owner),
    )
    assert remove.status_code == 200
    assert remove.json()["jobs"] == []


@pytest.mark.asyncio
async def test_reorder_jobs(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    product = await seed_product(app_session)
    jobs = [await _seed_job(client, owner, str(product.id)) for _ in range(3)]
    order_id = await _seed_order(client, owner)

    for j in jobs:
        r = await client.post(
            f"/api/v1/production-orders/{order_id}/jobs",
            headers=auth_header(owner),
            json={"job_id": j},
        )
        assert r.status_code == 201

    # Move last job to position 0.
    r = await client.patch(
        f"/api/v1/production-orders/{order_id}/jobs",
        headers=auth_header(owner),
        json={"job_id": jobs[2], "new_position": 0},
    )
    assert r.status_code == 200
    ordered = sorted(r.json()["jobs"], key=lambda m: m["display_order"])
    assert [m["job_id"] for m in ordered] == [jobs[2], jobs[0], jobs[1]]
    assert [m["display_order"] for m in ordered] == [0, 1, 2]


@pytest.mark.asyncio
async def test_job_in_only_one_active_order(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    product = await seed_product(app_session)
    job_id = await _seed_job(client, owner, str(product.id))

    order_a = await _seed_order(client, owner, name="A")
    order_b = await _seed_order(client, owner, name="B")

    # Add to A, then activate A.
    r = await client.post(
        f"/api/v1/production-orders/{order_a}/jobs",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r.status_code == 201
    r = await client.post(
        f"/api/v1/production-orders/{order_a}/activate",
        headers=auth_header(owner),
    )
    assert r.status_code == 200

    # Adding the same job to B (planning) is allowed... NO! The guard
    # fires whenever there's some *other* active order containing the
    # job. A is active and holds the job, so B is blocked.
    r = await client.post(
        f"/api/v1/production-orders/{order_b}/jobs",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_same_job_in_two_planning_orders_is_allowed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    product = await seed_product(app_session)
    job_id = await _seed_job(client, owner, str(product.id))

    order_a = await _seed_order(client, owner, name="A")
    order_b = await _seed_order(client, owner, name="B")
    for o in (order_a, order_b):
        r = await client.post(
            f"/api/v1/production-orders/{o}/jobs",
            headers=auth_header(owner),
            json={"job_id": job_id},
        )
        assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_add_duplicate_job_same_order_409(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    product = await seed_product(app_session)
    job_id = await _seed_job(client, owner, str(product.id))
    order_id = await _seed_order(client, owner)

    r1 = await client.post(
        f"/api/v1/production-orders/{order_id}/jobs",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r1.status_code == 201
    r2 = await client.post(
        f"/api/v1/production-orders/{order_id}/jobs",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_add_job_to_archived_order_400(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    product = await seed_product(app_session)
    job_id = await _seed_job(client, owner, str(product.id))
    order_id = await _seed_order(client, owner)

    await client.post(
        f"/api/v1/production-orders/{order_id}/archive", headers=auth_header(owner)
    )
    r = await client.post(
        f"/api/v1/production-orders/{order_id}/jobs",
        headers=auth_header(owner),
        json={"job_id": job_id},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_remove_unknown_job_404(client: AsyncClient, app_session: AsyncSession) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    order_id = await _seed_order(client, owner)
    r = await client.delete(
        f"/api/v1/production-orders/{order_id}/jobs/00000000-0000-0000-0000-000000000000",
        headers=auth_header(owner),
    )
    assert r.status_code == 404
