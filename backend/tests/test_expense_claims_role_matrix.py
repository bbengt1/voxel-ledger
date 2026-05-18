"""Role matrix for expense claims endpoints (Phase 8.7, #134).

* submitter cannot approve their own claim (self-approval guard).
* viewer cannot create.
* submitter (non-privileged) only sees their own claims.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._expense_claims_helpers import (
    auth_header,
    sample_claim_lines,
    seed_full_expense_claim_stack,
    token_for,
)


async def _create_login(
    client: AsyncClient, session: AsyncSession, *, email: str, role: Role
) -> str:
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=email,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_viewer_cannot_create_claim(client: AsyncClient, app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    viewer = await token_for(Role.VIEWER, client, app_session)
    r = await client.post(
        "/api/v1/expense-claims",
        headers=auth_header(viewer),
        json={
            "lines": sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        },
    )
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_submitter_cannot_approve_own_claim(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    # Submitter is BOOKKEEPER so they have approve role generally, but
    # self-approval must still be blocked.
    submitter_token = await _create_login(
        client, app_session, email="self-app@example.com", role=Role.BOOKKEEPER
    )
    r = await client.post(
        "/api/v1/expense-claims",
        headers=auth_header(submitter_token),
        json={
            "lines": sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        },
    )
    assert r.status_code == 201, r.text
    claim_id = r.json()["id"]

    r2 = await client.post(
        f"/api/v1/expense-claims/{claim_id}/submit",
        headers=auth_header(submitter_token),
    )
    assert r2.status_code in (200, 202), r2.text

    r3 = await client.post(
        f"/api/v1/expense-claims/{claim_id}/approve",
        headers=auth_header(submitter_token),
    )
    assert r3.status_code == 403, r3.text


@pytest.mark.asyncio
async def test_non_submitter_cannot_see_others_claim(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    alice = await _create_login(client, app_session, email="alice@example.com", role=Role.SALES)
    bob = await _create_login(client, app_session, email="bob@example.com", role=Role.SALES)
    r = await client.post(
        "/api/v1/expense-claims",
        headers=auth_header(alice),
        json={
            "lines": sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        },
    )
    assert r.status_code == 201, r.text
    claim_id = r.json()["id"]

    # Bob can't see Alice's claim.
    r_get = await client.get(f"/api/v1/expense-claims/{claim_id}", headers=auth_header(bob))
    assert r_get.status_code == 404

    # Bob's list excludes Alice's claim.
    r_list = await client.get("/api/v1/expense-claims", headers=auth_header(bob))
    assert r_list.status_code == 200
    items = r_list.json()["items"]
    assert all(item["id"] != claim_id for item in items)


@pytest.mark.asyncio
async def test_owner_sees_all_claims(client: AsyncClient, app_session: AsyncSession) -> None:
    stack = await seed_full_expense_claim_stack(app_session)
    alice = await _create_login(client, app_session, email="alice2@example.com", role=Role.SALES)
    owner = await _create_login(client, app_session, email="owner2@example.com", role=Role.OWNER)
    r = await client.post(
        "/api/v1/expense-claims",
        headers=auth_header(alice),
        json={
            "lines": sample_claim_lines(expense_category_id=stack["expense_category_id"]),
        },
    )
    assert r.status_code == 201
    claim_id = r.json()["id"]

    r_owner = await client.get(f"/api/v1/expense-claims/{claim_id}", headers=auth_header(owner))
    assert r_owner.status_code == 200


@pytest.mark.asyncio
async def test_submit_returns_202_when_approval_required(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    stack = await seed_full_expense_claim_stack(app_session, threshold=Decimal("10.00"))
    submitter_token = await _create_login(
        client, app_session, email="hi@example.com", role=Role.SALES
    )
    r = await client.post(
        "/api/v1/expense-claims",
        headers=auth_header(submitter_token),
        json={
            "lines": sample_claim_lines(
                expense_category_id=stack["expense_category_id"], amount="100.00"
            ),
        },
    )
    assert r.status_code == 201
    claim_id = r.json()["id"]
    r2 = await client.post(
        f"/api/v1/expense-claims/{claim_id}/submit",
        headers=auth_header(submitter_token),
    )
    assert r2.status_code == 202, r2.text
    assert r2.json()["approval_request_id"] is not None
