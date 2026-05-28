"""v1 migration tests (Phase 12.4, #206)."""

from __future__ import annotations

import pytest
from app.models.customer import Customer, CustomerState
from app.models.event import Event
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from scripts.v1_migration import framework
from scripts.v1_migration.contexts import customers as customers_ctx


@pytest.fixture(autouse=True)
def _registry_clean():
    """Each test gets the production registry restored after running.

    Pytest's module collection imports every context once; we
    snapshot/restore so tests that mutate the registry don't bleed.
    """
    snapshot = list(framework._REGISTRY)
    yield
    framework._REGISTRY[:] = snapshot


@pytest.mark.asyncio
async def test_customers_migrates_and_emits_backfill_event(
    client, app_session: AsyncSession
) -> None:
    v1_payload = {
        "customers": [
            {
                "customer_number": "C-V1-1",
                "display_name": "Acme",
                "primary_email": "ops@acme.test",
                "payment_terms_days": 45,
                "state": "active",
                "created_at": "2025-04-01T00:00:00Z",
            },
            {
                "customer_number": "C-V1-2",
                "display_name": "Beta",
                "state": "archived",
            },
        ]
    }
    ctx = framework.MigrationContext(v1_session=v1_payload, v2_session=app_session, dry_run=False)
    result = await customers_ctx.migrate(ctx)
    await app_session.commit()

    assert result.rows_in == 2
    assert result.rows_out == 2
    assert result.events_emitted == 2
    assert result.ok

    rows = (
        (await app_session.execute(select(Customer).order_by(Customer.customer_number)))
        .scalars()
        .all()
    )
    assert [c.customer_number for c in rows] == ["C-V1-1", "C-V1-2"]
    assert rows[0].payment_terms_days == 45
    assert rows[1].state == CustomerState.ARCHIVED

    events = (
        (await app_session.execute(select(Event).where(Event.type == "ar.CustomerCreated")))
        .scalars()
        .all()
    )
    assert len(events) == 2
    assert all(e.schema_version == 0 for e in events)
    # occurred_at uses the v1 row timestamp when available.
    for e in events:
        if e.payload["customer_number"] == "C-V1-1":
            assert e.occurred_at.isoformat().startswith("2025-04-01")


@pytest.mark.asyncio
async def test_customers_is_idempotent(client, app_session: AsyncSession) -> None:
    v1_payload = {"customers": [{"customer_number": "C-V1-IDEM", "display_name": "Same"}]}
    ctx = framework.MigrationContext(v1_session=v1_payload, v2_session=app_session, dry_run=False)
    r1 = await customers_ctx.migrate(ctx)
    await app_session.commit()
    r2 = await customers_ctx.migrate(ctx)
    await app_session.commit()

    assert r1.rows_out == 1
    assert r2.rows_out == 0
    assert r2.rows_skipped == 1
    rows = (
        (await app_session.execute(select(Customer).where(Customer.customer_number == "C-V1-IDEM")))
        .scalars()
        .all()
    )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_orchestrator_runs_every_registered_context(
    client, app_session: AsyncSession
) -> None:
    v1_payload = {
        "customers": [{"customer_number": "C-ORC", "display_name": "OrcCo"}],
    }
    result = await framework.run_all(
        v1_session=v1_payload,
        v2_session=app_session,
        dry_run=False,
    )
    assert result.ok
    # 15 contexts total (per scripts/v1_migration/contexts/__init__.py).
    assert len(result.results) >= 1
    by_name = {r.context: r for r in result.results}
    assert by_name["customers"].rows_out == 1
    # Stubs return zero rows but no errors.
    for name, r in by_name.items():
        assert r.ok, f"{name} had errors: {r.errors}"


@pytest.mark.asyncio
async def test_dry_run_rolls_back(client, app_session: AsyncSession) -> None:
    v1_payload = {"customers": [{"customer_number": "C-DRY", "display_name": "Dry"}]}
    await framework.run_all(
        v1_session=v1_payload,
        v2_session=app_session,
        dry_run=True,
    )
    # Roll the test session back so it sees a fresh transaction state.
    await app_session.rollback()
    rows = (
        (await app_session.execute(select(Customer).where(Customer.customer_number == "C-DRY")))
        .scalars()
        .all()
    )
    assert rows == []


@pytest.mark.asyncio
async def test_preconditions_refuse_non_empty_event_log(client, app_session: AsyncSession) -> None:
    # Seed one event by running a real append.
    v1_payload = {"customers": [{"customer_number": "C-PRE", "display_name": "Pre"}]}
    ctx = framework.MigrationContext(v1_session=v1_payload, v2_session=app_session, dry_run=False)
    await customers_ctx.migrate(ctx)
    await app_session.commit()

    with pytest.raises(framework.MigrationError):
        await framework.check_preconditions(v2_session=app_session)
