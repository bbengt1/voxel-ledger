"""Self-approval guard: requester cannot approve or reject their own.

The endpoint surface returns 400 (not 403) because the underlying
SelfApprovalError is mapped to a bad-request response.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, email: str, password: str = "pw-correct") -> str:
    r = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return r.json()["access_token"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_requester_cannot_self_approve_via_api(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # Owner is both an admin (can approve in general) AND the requester.
    await create_user(
        app_session,
        email="owner@example.com",
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()

    token = await _login(client, "owner@example.com")

    # Seed a pending approval whose requester is the owner via the
    # service directly (the journal-entry threshold flow does this in
    # the real world).
    from app.services.approvals import ApprovalsService

    owner_id = (
        (
            await app_session.execute(
                __import__("sqlalchemy").select(
                    __import__("app.models.auth", fromlist=["User"]).User
                )
            )
        )
        .scalar_one()
        .id
    )
    req = await ApprovalsService.create(
        request_type="accounting.large_journal_entry",
        subject_kind="journal_entry",
        subject_id=__import__("uuid").uuid4(),
        payload={"k": "v"},
        threshold_amount=None,
        session=app_session,
        actor_user_id=owner_id,
    )
    await app_session.commit()

    r = await client.post(
        f"/api/v1/approvals/{req.id}/approve",
        headers=_h(token),
        json={},
    )
    assert r.status_code == 400, r.text
    assert "approve" in r.json()["detail"].lower()

    r = await client.post(
        f"/api/v1/approvals/{req.id}/reject",
        headers=_h(token),
        json={},
    )
    assert r.status_code == 400, r.text
