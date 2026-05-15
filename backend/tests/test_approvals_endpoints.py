"""Approvals API: role matrix + list scoping (Phase 4.4)."""

from __future__ import annotations

import uuid

import pytest
from app.models.auth import Role
from app.services.approvals import ApprovalsService
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_user(session: AsyncSession, role: Role, email: str | None = None):
    email = email or f"{role.value}@example.com"
    return await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_list_admin_sees_all_others_see_own(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    owner = await _seed_user(app_session, Role.OWNER)
    sales = await _seed_user(app_session, Role.SALES)
    bk = await _seed_user(app_session, Role.BOOKKEEPER)
    await app_session.commit()

    await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload={"x": 1},
        session=app_session,
        actor_user_id=owner.id,
    )
    await ApprovalsService.create(
        request_type="sales.refund_above_threshold",
        subject_kind="refund",
        subject_id=uuid.uuid4(),
        payload={"x": 2},
        session=app_session,
        actor_user_id=sales.id,
    )
    await app_session.commit()

    owner_token = await _login(client, owner.email)
    sales_token = await _login(client, sales.email)
    bk_token = await _login(client, bk.email)

    # Admin sees both.
    r = await client.get("/api/v1/approvals", headers=_h(owner_token))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2

    r = await client.get("/api/v1/approvals", headers=_h(bk_token))
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2

    # Sales sees only their own.
    r = await client.get("/api/v1/approvals", headers=_h(sales_token))
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["requested_by_user_id"] == str(sales.id)


@pytest.mark.asyncio
async def test_approve_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    requester = await _seed_user(app_session, Role.SALES, "req@x.com")
    owner = await _seed_user(app_session, Role.OWNER)
    bk = await _seed_user(app_session, Role.BOOKKEEPER)
    prod = await _seed_user(app_session, Role.PRODUCTION)
    await app_session.commit()

    req = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload={},
        session=app_session,
        actor_user_id=requester.id,
    )
    await app_session.commit()

    prod_token = await _login(client, prod.email)
    r = await client.post(
        f"/api/v1/approvals/{req.id}/approve",
        headers=_h(prod_token),
        json={},
    )
    assert r.status_code == 403

    bk_token = await _login(client, bk.email)
    r = await client.post(
        f"/api/v1/approvals/{req.id}/approve",
        headers=_h(bk_token),
        json={"decision_note": "ok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["state"] == "approved"
    assert body["decision_note"] == "ok"

    # Already decided.
    owner_token = await _login(client, owner.email)
    r = await client.post(
        f"/api/v1/approvals/{req.id}/approve",
        headers=_h(owner_token),
        json={},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cancel_by_requester_and_owner(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    requester = await _seed_user(app_session, Role.SALES, "rs@x.com")
    owner = await _seed_user(app_session, Role.OWNER)
    other = await _seed_user(app_session, Role.PRODUCTION, "p2@x.com")
    await app_session.commit()

    # Requester cancels own.
    req = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload={},
        session=app_session,
        actor_user_id=requester.id,
    )
    await app_session.commit()
    t = await _login(client, requester.email)
    r = await client.post(
        f"/api/v1/approvals/{req.id}/cancel",
        headers=_h(t),
        json={"reason": "mistake"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "cancelled"

    # Owner cancels someone else's.
    req2 = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload={},
        session=app_session,
        actor_user_id=requester.id,
    )
    await app_session.commit()
    owner_token = await _login(client, owner.email)
    r = await client.post(
        f"/api/v1/approvals/{req2.id}/cancel",
        headers=_h(owner_token),
        json={},
    )
    assert r.status_code == 200

    # Non-owner third party cannot cancel.
    req3 = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload={},
        session=app_session,
        actor_user_id=requester.id,
    )
    await app_session.commit()
    other_token = await _login(client, other.email)
    r = await client.post(
        f"/api/v1/approvals/{req3.id}/cancel",
        headers=_h(other_token),
        json={},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_get_visibility(client: AsyncClient, app_session: AsyncSession) -> None:
    requester = await _seed_user(app_session, Role.SALES, "vis-r@x.com")
    other = await _seed_user(app_session, Role.SALES, "vis-o@x.com")
    bk = await _seed_user(app_session, Role.BOOKKEEPER)
    await app_session.commit()

    req = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        payload={},
        session=app_session,
        actor_user_id=requester.id,
    )
    await app_session.commit()

    requester_t = await _login(client, requester.email)
    other_t = await _login(client, other.email)
    bk_t = await _login(client, bk.email)

    assert (
        await client.get(f"/api/v1/approvals/{req.id}", headers=_h(requester_t))
    ).status_code == 200
    assert (await client.get(f"/api/v1/approvals/{req.id}", headers=_h(bk_t))).status_code == 200
    # Other sales user cannot see foreign request.
    assert (await client.get(f"/api/v1/approvals/{req.id}", headers=_h(other_t))).status_code == 403
