"""AI insights worker + service tests (Phase 10.7, #182)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from app.models.ai_insight_summary import AiInsightStatus, AiInsightSummary
from app.models.auth import Role
from app.services import ai_insights as service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _seed_user(app_session: AsyncSession, *, email: str):
    user = await create_user(
        app_session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    return user


@pytest.mark.asyncio
async def test_deterministic_summary(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await _seed_user(app_session, email="det@example.com")
    today = date.today()
    await service.request(
        session=app_session,
        scope="sales_trend",
        period_start=today - timedelta(days=30),
        period_end=today,
        actor_user_id=user.id,
    )
    await app_session.commit()

    result = await service.run_pending(session=app_session, now=datetime.now(UTC))
    assert result.processed == 1
    assert result.failed == 0

    row = (await app_session.execute(select(AiInsightSummary))).scalars().one()
    assert row.status == AiInsightStatus.READY
    assert "sales_trend" in row.narrative
    # Deterministic provider tag.
    assert row.model and row.model.startswith("deterministic:")


@pytest.mark.asyncio
async def test_worker_picks_oldest_queued(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await _seed_user(app_session, email="oldest@example.com")
    today = date.today()

    first = await service.request(
        session=app_session,
        scope="sales_trend",
        period_start=today - timedelta(days=60),
        period_end=today - timedelta(days=31),
        actor_user_id=user.id,
    )
    await app_session.commit()
    # Force the second row's created_at to be later.
    second = await service.request(
        session=app_session,
        scope="sales_trend",
        period_start=today - timedelta(days=30),
        period_end=today,
        actor_user_id=user.id,
    )
    await app_session.commit()

    # max_per_run=1 → only the oldest processed.
    result = await service.run_pending(session=app_session, now=datetime.now(UTC), max_per_run=1)
    assert result.processed == 1

    fresh_first_id = first.id
    fresh_second_id = second.id
    fresh_first = (
        await app_session.execute(
            select(AiInsightSummary).where(AiInsightSummary.id == fresh_first_id)
        )
    ).scalar_one()
    fresh_second = (
        await app_session.execute(
            select(AiInsightSummary).where(AiInsightSummary.id == fresh_second_id)
        )
    ).scalar_one()
    assert fresh_first.status == AiInsightStatus.READY
    assert fresh_second.status == AiInsightStatus.QUEUED


@pytest.mark.asyncio
async def test_failure_records_error(client: AsyncClient, app_session: AsyncSession) -> None:
    user = await _seed_user(app_session, email="fail@example.com")
    today = date.today()
    await service.request(
        session=app_session,
        scope="sales_trend",
        period_start=today - timedelta(days=30),
        period_end=today,
        actor_user_id=user.id,
    )
    await app_session.commit()

    # Force the payload-computation step to blow up so we exercise the
    # failed-path on a row already in state RUNNING.
    with patch.object(
        service,
        "_payload_for_scope",
        side_effect=RuntimeError("kaboom"),
    ):
        result = await service.run_pending(session=app_session, now=datetime.now(UTC))
    assert result.processed == 0
    assert result.failed == 1

    row = (await app_session.execute(select(AiInsightSummary))).scalars().one()
    assert row.status == AiInsightStatus.FAILED
    assert "kaboom" in (row.error or "")


@pytest.mark.asyncio
async def test_endpoints_request_then_latest(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    await _seed_user(app_session, email="ep@example.com")
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "ep@example.com", "password": "pw-correct"},
    )
    token = login.json()["access_token"]
    hdrs = {"Authorization": f"Bearer {token}"}

    today = date.today()
    create = await client.post(
        "/api/v1/dashboard/ai-insights/requests",
        headers=hdrs,
        json={
            "scope": "sales_trend",
            "period_start": (today - timedelta(days=7)).isoformat(),
            "period_end": today.isoformat(),
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["status"] == "queued"

    # Latest with no ready row yet → 200 + null body.
    empty = await client.get("/api/v1/dashboard/ai-insights/latest?scope=sales_trend", headers=hdrs)
    assert empty.status_code == 200
    assert empty.json() is None

    # Drain the worker.
    await service.run_pending(session=app_session, now=datetime.now(UTC))

    latest = await client.get(
        "/api/v1/dashboard/ai-insights/latest?scope=sales_trend", headers=hdrs
    )
    assert latest.status_code == 200
    body = latest.json()
    assert body is not None
    assert body["scope"] == "sales_trend"
    assert body["status"] == "ready"
    assert "sales_trend" in body["narrative"]
