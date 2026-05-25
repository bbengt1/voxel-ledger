"""Worker run-state tests (Issue #220)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.worker_run_state import WorkerRunState, WorkerRunStatus
from app.workers.registry import _REGISTRY, register_job, run_job
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _registry_clean():
    """Snapshot+restore so synthetic jobs in this module don't bleed
    into other suites."""
    snapshot = dict(_REGISTRY)
    yield
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


@pytest.fixture(autouse=True)
async def _clear_state(app_session: AsyncSession):
    """Reset the run-state table per-test."""
    await app_session.execute(delete(WorkerRunState))
    await app_session.commit()
    yield


@pytest.mark.asyncio
async def test_successful_run_records_ok_state(
    client, app_session: AsyncSession
) -> None:
    async def job(_session: AsyncSession) -> None:
        return

    register_job("test-ok-job", cron="* * * * *", fn=job)

    await run_job("test-ok-job", session=app_session)

    row = (
        await app_session.execute(
            select(WorkerRunState).where(WorkerRunState.job_name == "test-ok-job")
        )
    ).scalar_one()
    assert row.last_status == WorkerRunStatus.OK
    assert row.last_error is None
    assert row.last_finished_at is not None
    assert row.last_started_at is not None
    assert row.last_duration_ms is not None
    assert row.last_duration_ms >= 0


@pytest.mark.asyncio
async def test_failing_run_records_failed_state(
    client, app_session: AsyncSession
) -> None:
    async def job(_session: AsyncSession) -> None:
        raise RuntimeError("kaboom")

    register_job("test-fail-job", cron="* * * * *", fn=job)

    with pytest.raises(RuntimeError):
        await run_job("test-fail-job", session=app_session)

    row = (
        await app_session.execute(
            select(WorkerRunState).where(WorkerRunState.job_name == "test-fail-job")
        )
    ).scalar_one()
    assert row.last_status == WorkerRunStatus.FAILED
    assert row.last_error == "kaboom"
    assert row.last_finished_at is not None


@pytest.mark.asyncio
async def test_subsequent_success_clears_error(
    client, app_session: AsyncSession
) -> None:
    state = {"raise": True}

    async def job(_session: AsyncSession) -> None:
        if state["raise"]:
            raise RuntimeError("transient")

    register_job("test-flip-job", cron="* * * * *", fn=job)

    with pytest.raises(RuntimeError):
        await run_job("test-flip-job", session=app_session)
    state["raise"] = False
    await run_job("test-flip-job", session=app_session)

    row = (
        await app_session.execute(
            select(WorkerRunState).where(WorkerRunState.job_name == "test-flip-job")
        )
    ).scalar_one()
    assert row.last_status == WorkerRunStatus.OK
    assert row.last_error is None


@pytest.mark.asyncio
async def test_admin_endpoint_lists_all_registered_jobs(
    client, app_session: AsyncSession
) -> None:
    """Endpoint should list every registered job, including those that
    have never run (state row absent)."""
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    token = await token_for(Role.OWNER, client, app_session)

    # Pre-existing jobs (ai_insights_runner, etc.) are already in the
    # registry — just hit the endpoint and assert the shape.
    resp = await client.get(
        "/api/v1/admin/workers", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) > 0
    job_names = {row["job_name"] for row in body}
    # ai_insights_runner is registered in ai_insights_runner.py via
    # register_job at import time.
    assert "ai_insights_runner" in job_names


@pytest.mark.asyncio
async def test_admin_endpoint_role_matrix(
    client, app_session: AsyncSession
) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    sales_token = await token_for(Role.SALES, client, app_session)
    resp = await client.get(
        "/api/v1/admin/workers",
        headers={"Authorization": f"Bearer {sales_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_control_center_failed_jobs_reads_run_state(
    client, app_session: AsyncSession
) -> None:
    """A fresh failure inside the 24h window shows up in the Control
    Center's ``failed_jobs`` tile."""
    from app.services import control_center as cc_service

    app_session.add(
        WorkerRunState(
            job_name="test-cc-failed",
            last_status=WorkerRunStatus.FAILED,
            last_finished_at=datetime.now(UTC) - timedelta(minutes=5),
            last_error="boom from CC test",
        )
    )
    app_session.add(
        WorkerRunState(
            job_name="test-cc-old",
            last_status=WorkerRunStatus.FAILED,
            # Outside the 24h window — should NOT count.
            last_finished_at=datetime.now(UTC) - timedelta(hours=48),
            last_error="ancient",
        )
    )
    app_session.add(
        WorkerRunState(
            job_name="test-cc-ok",
            last_status=WorkerRunStatus.OK,
            last_finished_at=datetime.now(UTC),
        )
    )
    await app_session.commit()

    result = await cc_service.build(app_session)
    assert result.failed_jobs.count == 1
    assert result.failed_jobs.sample[0]["job_name"] == "test-cc-failed"
