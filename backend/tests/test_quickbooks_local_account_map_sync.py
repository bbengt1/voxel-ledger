"""QBO sync for the no-role posting sites (#316, epic #312, Phase 3d follow-up).

Inter-account transfers and the bank auto-matcher post to arbitrary local
accounts with no fixed role. When ``quickbooks.enabled`` they enqueue a
JournalEntry whose legs reference local account ids, resolved at drain via the
local-account map. These tests cover:

* a transfer enqueues + builds a balanced QBO JE with the mapped QBO accounts;
* an auto-match enqueues + builds the JE (and matches the tx without a local JE);
* an unmapped local account fails the build clearly.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.bank import BankTransactionState
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services import bank_auto_matcher, bank_match_rules, inter_account_transfers
from app.services.quickbooks import local_account_map, outbox
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import (
    seed_bank_account,
    seed_bank_transaction,
    seed_expense_account,
    seed_open_period,
    seed_user,
)


class FakeQBO:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, Any]]] = []
        self._n = 2200

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


async def _map_local(session: AsyncSession, mapping: dict[uuid.UUID, str]) -> None:
    await local_account_map.set_mappings(
        session,
        {str(k): {"qbo_account_id": v} for k, v in mapping.items()},
        actor_user_id=None,
    )
    await session.commit()


def _refs_by_posting(payload: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in payload["Line"]:
        detail = line["JournalEntryLineDetail"]
        out[detail["PostingType"]] = detail["AccountRef"]["value"]
    return out


@pytest.mark.asyncio
async def test_transfer_enqueues_and_builds_je(app_session: AsyncSession, settings_obj) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    src = await seed_bank_account(app_session, code="1010", name="Checking")
    dst = await seed_bank_account(app_session, code="1011", name="Savings")
    await _enable_qbo(app_session)
    await _map_local(app_session, {src.id: "QBO_SRC", dst.id: "QBO_DST"})

    entry = await inter_account_transfers.post_transfer(
        session=app_session,
        from_account_id=src.id,
        to_account_id=dst.id,
        amount=Decimal("150.00"),
        occurred_at=datetime.now(UTC),
        memo="sweep",
        actor_user_id=user.id,
    )
    await app_session.commit()
    # QBO replace-mode: no local JE.
    assert entry is None

    rows = (
        (
            await app_session.execute(
                select(QboSyncOutbox).where(QboSyncOutbox.kind == "inter_account_transfer")
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1

    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1, res
    entity, payload = fake.created[0]
    assert entity == "JournalEntry"
    refs = _refs_by_posting(payload)
    # Dr to_account (dst), Cr from_account (src).
    assert refs["Debit"] == "QBO_DST"
    assert refs["Credit"] == "QBO_SRC"


@pytest.mark.asyncio
async def test_auto_match_enqueues_and_builds_je(app_session: AsyncSession, settings_obj) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    bank = await seed_bank_account(app_session)
    expense = await seed_expense_account(app_session)
    await _enable_qbo(app_session)
    await _map_local(app_session, {bank.id: "QBO_BANK", expense.id: "QBO_EXP"})

    await bank_match_rules.create(
        session=app_session,
        account_id=bank.id,
        priority=50,
        match_kind="contains",
        match_field="description",
        match_value="RENT",
        action_kind="post_to_account",
        debit_account_id=expense.id,
        credit_account_id=bank.id,
        actor_user_id=user.id,
    )
    await app_session.commit()
    tx = await seed_bank_transaction(
        app_session,
        account_id=bank.id,
        description="RENT MAY",
        amount=Decimal("-1200.00"),
    )

    results = await bank_auto_matcher.run_once(session=app_session, actor_user_id=user.id)
    await app_session.commit()
    assert len(results) == 1
    # QBO replace-mode: matched, but no local JE / journal line.
    assert results[0].journal_entry_id is None
    await app_session.refresh(tx)
    assert tx.state == BankTransactionState.MATCHED
    assert tx.matched_journal_line_id is None

    rows = (
        (await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "bank_match")))
        .scalars()
        .all()
    )
    assert len(rows) == 1

    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1, res
    entity, payload = fake.created[0]
    assert entity == "JournalEntry"
    refs = _refs_by_posting(payload)
    # Outflow: credit bank, debit the expense side.
    assert refs["Credit"] == "QBO_BANK"
    assert refs["Debit"] == "QBO_EXP"


@pytest.mark.asyncio
async def test_unmapped_local_account_fails_build(app_session: AsyncSession, settings_obj) -> None:
    user = await seed_user(app_session)
    await seed_open_period(app_session)
    src = await seed_bank_account(app_session, code="1010", name="Checking")
    dst = await seed_bank_account(app_session, code="1011", name="Savings")
    await _enable_qbo(app_session)
    # Map only one of the two accounts.
    await _map_local(app_session, {src.id: "QBO_SRC"})

    await inter_account_transfers.post_transfer(
        session=app_session,
        from_account_id=src.id,
        to_account_id=dst.id,
        amount=Decimal("10.00"),
        occurred_at=datetime.now(UTC),
        memo=None,
        actor_user_id=user.id,
    )
    await app_session.commit()

    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    # Unmapped account → permanent BuilderError → FAILED, nothing pushed.
    assert res.synced == 0
    assert res.failed == 1
    assert fake.created == []
    row = (
        (
            await app_session.execute(
                select(QboSyncOutbox).where(QboSyncOutbox.kind == "inter_account_transfer")
            )
        )
        .scalars()
        .one()
    )
    assert row.status == QboSyncStatus.FAILED.value
    assert "not mapped" in (row.last_error or "")
