"""POST /accounting/entries/from-approval dispatcher (Phase 4.4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": "pw-correct"})
    return r.json()["access_token"]


def _h(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


@pytest.mark.asyncio
async def test_dispatch_posts_entry_and_marks_consumed(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # Two different bookkeepers — requester != approver/dispatcher.
    await create_user(
        app_session,
        email="r@x.com",
        password="pw-correct",
        full_name="R",
        role=Role.BOOKKEEPER,
        bcrypt_rounds=4,
    )
    await create_user(
        app_session,
        email="a@x.com",
        password="pw-correct",
        full_name="A",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    r_token = await _login(client, "r@x.com")
    a_token = await _login(client, "a@x.com")

    cash = await client.post(
        "/api/v1/accounts",
        headers=_h(a_token),
        json={"code": "1000", "name": "Cash", "type": "asset"},
    )
    rev = await client.post(
        "/api/v1/accounts",
        headers=_h(a_token),
        json={"code": "4000", "name": "Revenue", "type": "revenue"},
    )

    # Requester (bookkeeper) submits an over-threshold entry.
    body = {
        "description": "big sale",
        "posted_at": datetime.now(UTC).isoformat(),
        "lines": [
            {
                "account_id": cash.json()["id"],
                "debit": "2500.00",
                "credit": "0",
                "line_number": 1,
            },
            {
                "account_id": rev.json()["id"],
                "debit": "0",
                "credit": "2500.00",
                "line_number": 2,
            },
        ],
    }
    submit = await client.post("/api/v1/accounting/entries", headers=_h(r_token), json=body)
    assert submit.status_code == 202, submit.text
    approval_id = submit.json()["approval_request_id"]

    # Approver approves it.
    approve = await client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=_h(a_token),
        json={"decision_note": "ok"},
    )
    assert approve.status_code == 200, approve.text

    # Approver (or any bookkeeper/owner) dispatches the post.
    dispatch = await client.post(
        f"/api/v1/accounting/entries/from-approval/{approval_id}",
        headers=_h(a_token),
    )
    assert dispatch.status_code == 201, dispatch.text
    posted = dispatch.json()
    # Author preserved.
    # The original requester is r@x.com — actor_user_id on the entry
    # should match.
    me_r = await client.get("/api/v1/auth/me", headers=_h(r_token))
    assert posted["actor_user_id"] == me_r.json()["id"]

    # A second dispatch attempt fails.
    again = await client.post(
        f"/api/v1/accounting/entries/from-approval/{approval_id}",
        headers=_h(a_token),
    )
    assert again.status_code == 400


@pytest.mark.asyncio
async def test_dispatch_rejects_non_approved(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await create_user(
        app_session,
        email="owner@x.com",
        password="pw-correct",
        full_name="O",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    t = await _login(client, "owner@x.com")
    # Fabricate an approval that's still pending and try to dispatch.
    import uuid as _uuid

    from app.services.approvals import ApprovalsService

    req = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=_uuid.uuid4(),
        payload={"description": "x", "posted_at": "2026-05-14T00:00:00+00:00", "lines": []},
        session=app_session,
        actor_user_id=(
            await app_session.execute(
                __import__("sqlalchemy").select(
                    __import__("app.models.auth", fromlist=["User"]).User
                )
            )
        )
        .scalar_one()
        .id,
    )
    await app_session.commit()
    r = await client.post(f"/api/v1/accounting/entries/from-approval/{req.id}", headers=_h(t))
    assert r.status_code == 400
