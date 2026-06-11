"""Decommission cutover readiness + declaration — Phase-5c hard gate (#318).

Covers:

* readiness reports every failing precondition with a reason (QBO off, no
  archive, no opening balance);
* a fully-green pipeline (archive + synced opening balance + clean
  reconciliation) is ready, and declare_cutover records the declaration;
* date mismatches between archive/opening-balance and the declared cutover
  block the declaration;
* a second declaration is refused.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.services import journal_entries as journal_service
from app.services.quickbooks import (
    archive,
    decommission,
    local_account_map,
    opening_balance,
    outbox,
)
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, seed_account, seed_owner


class FakeQBO:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, Any]]] = []
        self._n = 4400

    async def create(self, entity, payload, *, request_id=None):
        self.created.append((entity, payload))
        self._n += 1
        return {**payload, "Id": str(self._n), "SyncToken": "0"}


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


async def _enable_qbo(session: AsyncSession) -> None:
    await SettingsService.set("quickbooks.enabled", True, session=session, actor_user_id=None)
    fut = datetime.now(UTC) + timedelta(days=1)
    session.add(
        OAuthCredential(
            provider=OAuthProvider.QUICKBOOKS.value,
            realm_id="1",
            access_token="t",
            refresh_token="r",
            access_token_expires_at=fut,
            refresh_token_expires_at=fut,
        )
    )
    await session.commit()


async def _seed_books(session: AsyncSession):
    user = await seed_owner(session)
    bank = await seed_account(session, code="1000", name="Bank", type="asset")
    revenue = await seed_account(session, code="4000", name="Sales", type="revenue")
    await journal_service.post(
        journal_service.JournalEntryInput(
            description="seed",
            posted_at=datetime.now(UTC),
            lines=[
                journal_service.JournalLineInput(
                    account_id=bank.id, debit=d("100.00"), credit=d("0"), line_number=1
                ),
                journal_service.JournalLineInput(
                    account_id=revenue.id, debit=d("0"), credit=d("100.00"), line_number=2
                ),
            ],
        ),
        session=session,
        actor_user_id=user.id,
        _internal_skip_approval_check=True,
    )
    await session.commit()
    return user, bank, revenue


async def _run_full_prep(
    session: AsyncSession, settings_obj: Settings, tmp_path: Path, user, bank, revenue
):
    """Archive (5a) + seed and drain opening balances (5b) for today."""
    cutover = datetime.now(UTC).date()
    await local_account_map.set_mappings(
        session,
        {str(bank.id): {"qbo_account_id": "B"}, str(revenue.id): {"qbo_account_id": "R"}},
        actor_user_id=None,
    )
    await archive.build_archive(
        session, cutover_date=cutover, out_dir=tmp_path / "arch", actor_user_id=user.id
    )
    await opening_balance.enqueue_opening_balance(
        session, cutover_date=cutover, actor_user_id=user.id
    )
    await session.commit()
    res = await outbox.run_pending(session, settings_obj, client=FakeQBO())
    assert res.synced == 1, res
    return cutover


@pytest.mark.asyncio
async def test_readiness_lists_every_failing_precondition(app_session: AsyncSession) -> None:
    await _seed_books(app_session)
    cutover = datetime.now(UTC).date()

    readiness = await decommission.build_readiness(app_session, cutover_date=cutover)
    assert readiness.ready is False
    joined = " | ".join(readiness.reasons)
    assert "quickbooks.enabled is off" in joined
    assert "no GL archive" in joined
    assert "never seeded" in joined
    assert readiness.declared is False

    with pytest.raises(decommission.NotReadyError):
        await decommission.declare_cutover(app_session, cutover_date=cutover, actor_user_id=None)


@pytest.mark.asyncio
async def test_green_pipeline_declares_cutover(
    app_session: AsyncSession, settings_obj, tmp_path: Path
) -> None:
    user, bank, revenue = await _seed_books(app_session)
    await _enable_qbo(app_session)
    cutover = await _run_full_prep(app_session, settings_obj, tmp_path, user, bank, revenue)

    readiness = await decommission.build_readiness(app_session, cutover_date=cutover)
    assert readiness.reasons == []
    assert readiness.ready is True
    assert readiness.archive_balanced is True
    assert readiness.opening_balance_status == "synced"

    row = await decommission.declare_cutover(
        app_session, cutover_date=cutover, actor_user_id=user.id
    )
    await app_session.commit()
    assert row.archive_manifest_id == readiness.archive_manifest_id
    assert row.opening_balance_outbox_id == readiness.opening_balance_outbox_id
    assert row.readiness_snapshot["ready"] is True
    assert await decommission.is_cutover_declared(app_session) is True

    with pytest.raises(decommission.AlreadyDeclaredError):
        await decommission.declare_cutover(app_session, cutover_date=cutover, actor_user_id=user.id)


@pytest.mark.asyncio
async def test_date_mismatch_blocks_declaration(
    app_session: AsyncSession, settings_obj, tmp_path: Path
) -> None:
    user, bank, revenue = await _seed_books(app_session)
    await _enable_qbo(app_session)
    cutover = await _run_full_prep(app_session, settings_obj, tmp_path, user, bank, revenue)

    wrong_date = cutover + timedelta(days=7)
    readiness = await decommission.build_readiness(app_session, cutover_date=wrong_date)
    assert readiness.ready is False
    joined = " | ".join(readiness.reasons)
    assert "re-archive" in joined
    assert "opening-balance JE is dated" in joined

    with pytest.raises(decommission.NotReadyError):
        await decommission.declare_cutover(
            app_session, cutover_date=wrong_date, actor_user_id=user.id
        )
    assert await decommission.is_cutover_declared(app_session) is False
