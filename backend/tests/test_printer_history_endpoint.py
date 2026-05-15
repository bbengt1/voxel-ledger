"""Endpoint tests for GET /api/v1/printers/{id}/history (Phase 5.4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.models.auth import Role
from app.models.printer_history_event import PrinterEventKind, PrinterHistoryEvent
from app.services import printers as printers_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_history_requires_auth(client: AsyncClient, app_session: AsyncSession) -> None:
    p = await printers_service.create(
        app_session,
        name="H1",
        slug="h1",
        printer_type="prusa_mk4",
        actor_user_id=None,
    )
    await app_session.commit()
    r = await client.get(f"/api/v1/printers/{p.id}/history")
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_history_list_filter_and_pagination(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    p = await printers_service.create(
        app_session,
        name="H2",
        slug="h2",
        printer_type="prusa_mk4",
        actor_user_id=None,
    )
    await app_session.commit()

    # Seed 5 history rows across a 10-minute window.
    now = datetime.now(UTC)
    kinds = [
        PrinterEventKind.CONNECTED,
        PrinterEventKind.PRINT_STARTED,
        PrinterEventKind.PRINT_PAUSED,
        PrinterEventKind.PRINT_RESUMED,
        PrinterEventKind.PRINT_COMPLETED,
    ]
    for i, kind in enumerate(kinds):
        app_session.add(
            PrinterHistoryEvent(
                id=uuid.uuid4(),
                printer_id=p.id,
                event_kind=kind,
                occurred_at=now - timedelta(minutes=10 - i * 2),
                details={"i": i},
            )
        )
    await app_session.commit()

    token = await _token_for(Role.VIEWER, client, app_session)
    headers = {"Authorization": f"Bearer {token}"}

    # Full list, descending.
    r = await client.get(f"/api/v1/printers/{p.id}/history", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["items"]) == 5
    assert body["items"][0]["event_kind"] == "print_completed"
    assert body["items"][-1]["event_kind"] == "connected"

    # Range filter: only the first 3 minutes' worth.
    cutoff = (now - timedelta(minutes=5)).isoformat()
    r = await client.get(
        f"/api/v1/printers/{p.id}/history",
        headers=headers,
        params={"from_at": cutoff},
    )
    assert r.status_code == 200
    assert len(r.json()["items"]) == 2

    # Pagination — page size 2.
    r = await client.get(
        f"/api/v1/printers/{p.id}/history",
        headers=headers,
        params={"limit": 2},
    )
    page1 = r.json()
    assert len(page1["items"]) == 2
    assert page1["next_cursor"] is not None

    r = await client.get(
        f"/api/v1/printers/{p.id}/history",
        headers=headers,
        params={"limit": 2, "cursor": page1["next_cursor"]},
    )
    page2 = r.json()
    assert len(page2["items"]) == 2
    # No overlap.
    ids1 = {item["id"] for item in page1["items"]}
    ids2 = {item["id"] for item in page2["items"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_history_404_for_unknown_printer(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _token_for(Role.OWNER, client, app_session)
    r = await client.get(
        f"/api/v1/printers/{uuid.uuid4()}/history",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
