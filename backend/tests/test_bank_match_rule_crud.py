"""Bank match-rule CRUD smoke tests (Phase 8.10, #137)."""

from __future__ import annotations

import pytest
from app.models.auth import Role
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    auth_header,
    seed_bank_account,
    seed_expense_account,
    token_for,
)


@pytest.mark.asyncio
async def test_create_get_patch_deactivate(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)

    r = await client.post(
        "/api/v1/bank-match-rules",
        json={
            "account_id": str(bank.id),
            "priority": 50,
            "match_kind": "contains",
            "match_field": "description",
            "match_value": "COFFEE",
            "action_kind": "post_to_account",
            "debit_account_id": str(expense.id),
            "credit_account_id": str(bank.id),
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text
    rid = r.json()["id"]

    r2 = await client.get(f"/api/v1/bank-match-rules/{rid}", headers=auth_header(token))
    assert r2.status_code == 200

    r3 = await client.patch(
        f"/api/v1/bank-match-rules/{rid}",
        json={"priority": 10, "notes": "high-priority coffee match"},
        headers=auth_header(token),
    )
    assert r3.status_code == 200, r3.text
    assert r3.json()["priority"] == 10

    r4 = await client.post(
        f"/api/v1/bank-match-rules/{rid}/deactivate",
        headers=auth_header(token),
    )
    assert r4.status_code == 200
    assert r4.json()["is_active"] is False


@pytest.mark.asyncio
async def test_post_to_account_requires_both_accounts(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)

    r = await client.post(
        "/api/v1/bank-match-rules",
        json={
            "account_id": str(bank.id),
            "priority": 50,
            "match_kind": "contains",
            "match_field": "description",
            "match_value": "COFFEE",
            "action_kind": "post_to_account",
            # missing debit/credit
        },
        headers=auth_header(token),
    )
    assert r.status_code == 400, r.text
    assert "debit_account_id" in r.text


@pytest.mark.asyncio
async def test_regex_validated_at_create(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)

    r = await client.post(
        "/api/v1/bank-match-rules",
        json={
            "account_id": str(bank.id),
            "priority": 50,
            "match_kind": "regex",
            "match_field": "description",
            "match_value": "[unclosed",
            "action_kind": "ignore",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 400
    assert "regex" in r.text.lower()


@pytest.mark.asyncio
async def test_ignore_action_does_not_require_accounts(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    bank = await seed_bank_account(app_session)
    r = await client.post(
        "/api/v1/bank-match-rules",
        json={
            "account_id": str(bank.id),
            "priority": 50,
            "match_kind": "contains",
            "match_field": "description",
            "match_value": "TRANSFER",
            "action_kind": "ignore",
        },
        headers=auth_header(token),
    )
    assert r.status_code == 201, r.text


@pytest.mark.asyncio
async def test_viewer_cannot_create_rule(client: AsyncClient, app_session: AsyncSession) -> None:
    viewer = await token_for(Role.VIEWER, client, app_session)
    bank = await seed_bank_account(app_session)
    r = await client.post(
        "/api/v1/bank-match-rules",
        json={
            "account_id": str(bank.id),
            "priority": 50,
            "match_kind": "contains",
            "match_field": "description",
            "match_value": "x",
            "action_kind": "ignore",
        },
        headers=auth_header(viewer),
    )
    assert r.status_code == 403
