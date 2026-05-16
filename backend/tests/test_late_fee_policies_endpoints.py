"""Late-fee-policies CRUD + apply-now endpoint smoke (Phase 7.6, #114)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from app.models.auth import Role, User
from app.models.invoice import InvoiceState
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._late_fees_helpers import (
    get_invoice,
    seed_customer,
    seed_full_ar_stack,
    seed_issued_invoice,
)
from tests._payments_helpers import auth_header, token_for


@pytest.mark.asyncio
async def test_create_and_get_global_policy(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    r = await client.post(
        "/api/v1/late-fee-policies",
        headers=auth_header(owner),
        json={
            "kind": "percent_of_outstanding",
            "amount": "0.015",
            "apply_after_days": 30,
        },
    )
    assert r.status_code == 201, r.text
    policy = r.json()
    assert policy["customer_id"] is None
    assert policy["is_active"] is True

    pid = policy["id"]
    g = await client.get(f"/api/v1/late-fee-policies/{pid}", headers=auth_header(owner))
    assert g.status_code == 200
    assert g.json()["kind"] == "percent_of_outstanding"


@pytest.mark.asyncio
async def test_duplicate_active_policy_rejected(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    body = {
        "kind": "flat",
        "amount": "10.00",
        "apply_after_days": 30,
    }
    r1 = await client.post(
        "/api/v1/late-fee-policies", headers=auth_header(owner), json=body
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/late-fee-policies", headers=auth_header(owner), json=body
    )
    assert r2.status_code == 400


@pytest.mark.asyncio
async def test_deactivate_then_create_new(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    body = {"kind": "flat", "amount": "10.00", "apply_after_days": 30}
    r1 = await client.post(
        "/api/v1/late-fee-policies", headers=auth_header(owner), json=body
    )
    pid = r1.json()["id"]
    r2 = await client.post(
        f"/api/v1/late-fee-policies/{pid}/deactivate", headers=auth_header(owner)
    )
    assert r2.status_code == 200
    assert r2.json()["is_active"] is False
    r3 = await client.post(
        "/api/v1/late-fee-policies", headers=auth_header(owner), json=body
    )
    assert r3.status_code == 201


@pytest.mark.asyncio
async def test_apply_now_creates_debit_note(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await token_for(Role.OWNER, client, app_session)
    await seed_full_ar_stack(app_session)
    customer = await seed_customer(app_session)
    user = (
        await app_session.execute(select(User).where(User.email == "owner@example.com"))
    ).scalar_one()
    invoice = await seed_issued_invoice(
        app_session, customer=customer, actor_user_id=user.id, unit_price="200.00"
    )
    fresh = await get_invoice(app_session, invoice.id)
    fresh.due_at = datetime.now(UTC) - timedelta(days=45)
    fresh.state = InvoiceState.OVERDUE
    await app_session.commit()

    await client.post(
        "/api/v1/late-fee-policies",
        headers=auth_header(owner),
        json={"kind": "flat", "amount": "15.00", "apply_after_days": 30},
    )

    r = await client.post(
        "/api/v1/late-fee-policies/apply-now", headers=auth_header(owner)
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    assert len(payload["applied"]) == 1
    assert payload["applied"][0]["amount"] == "15.00"

    refreshed = await get_invoice(app_session, invoice.id)
    await app_session.refresh(refreshed)
    assert refreshed.amount_outstanding == Decimal("215.000000")


@pytest.mark.asyncio
async def test_viewer_cannot_create_policy(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    viewer = await token_for(Role.VIEWER, client, app_session)
    r = await client.post(
        "/api/v1/late-fee-policies",
        headers=auth_header(viewer),
        json={"kind": "flat", "amount": "10.00", "apply_after_days": 30},
    )
    assert r.status_code == 403
