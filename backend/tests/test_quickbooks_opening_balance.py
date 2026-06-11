"""Cutover opening-balance seed → QBO (#318, epic #312, Phase 5b).

Covers:

* preview classifies each non-zero account onto the right posting side and
  flags unmapped accounts;
* enqueue produces an outbox row that drains into a balanced, cutover-dated
  QBO JournalEntry with the mapped account refs;
* enqueue refuses on unmapped accounts and on a duplicate seed.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.services import journal_entries as journal_service
from app.services.quickbooks import local_account_map, opening_balance, outbox
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession

from tests._je_helpers import d, seed_account, seed_owner


class FakeQBO:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, Any]]] = []
        self._n = 3300

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


async def _post_je(session: AsyncSession, *, actor_user_id, lines) -> None:
    journal_lines = [
        journal_service.JournalLineInput(
            account_id=acct_id, debit=d(dr), credit=d(cr), line_number=i
        )
        for i, (acct_id, dr, cr) in enumerate(lines, start=1)
    ]
    await journal_service.post(
        journal_service.JournalEntryInput(
            description="seed",
            posted_at=datetime.now(UTC),
            lines=journal_lines,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    await session.flush()


async def _seed_books(session: AsyncSession):
    """Bank 130 Dr / Loan 30 Cr / Revenue 100 Cr — balanced across types."""
    user = await seed_owner(session)
    bank = await seed_account(session, code="1000", name="Bank", type="asset")
    loan = await seed_account(session, code="2000", name="Loan", type="liability")
    revenue = await seed_account(session, code="4000", name="Sales", type="revenue")
    await _post_je(
        session,
        actor_user_id=user.id,
        lines=[(bank.id, "100.00", "0"), (revenue.id, "0", "100.00")],
    )
    await _post_je(
        session,
        actor_user_id=user.id,
        lines=[(bank.id, "30.00", "0"), (loan.id, "0", "30.00")],
    )
    await session.commit()
    return user, bank, loan, revenue


async def _map_all(session: AsyncSession, mapping: dict[uuid.UUID, str]) -> None:
    await local_account_map.set_mappings(
        session,
        {str(k): {"qbo_account_id": v} for k, v in mapping.items()},
        actor_user_id=None,
    )
    await session.commit()


@pytest.mark.asyncio
async def test_preview_classifies_postings_and_flags_unmapped(
    app_session: AsyncSession,
) -> None:
    _, bank, loan, revenue = await _seed_books(app_session)
    # Map only the bank; loan + revenue stay unmapped.
    await _map_all(app_session, {bank.id: "QBO_BANK"})

    preview = await opening_balance.build_preview(
        app_session, cutover_date=datetime.now(UTC).date()
    )
    by_code = {line.code: line for line in preview.lines}
    assert by_code["1000"].posting == "debit"
    assert by_code["1000"].amount == Decimal("130.00")
    assert by_code["1000"].qbo_account_id == "QBO_BANK"
    assert by_code["2000"].posting == "credit"
    assert by_code["2000"].amount == Decimal("30.00")
    assert by_code["4000"].posting == "credit"
    assert by_code["4000"].amount == Decimal("100.00")
    assert preview.total_debits == preview.total_credits == Decimal("130.00")
    assert preview.balanced is True
    assert preview.unmapped_codes == ["2000", "4000"]
    assert preview.existing_status is None


@pytest.mark.asyncio
async def test_enqueue_builds_cutover_dated_je(app_session: AsyncSession, settings_obj) -> None:
    user, bank, loan, revenue = await _seed_books(app_session)
    await _enable_qbo(app_session)
    await _map_all(app_session, {bank.id: "QBO_BANK", loan.id: "QBO_LOAN", revenue.id: "QBO_REV"})

    cutover = datetime.now(UTC).date()
    row = await opening_balance.enqueue_opening_balance(
        app_session, cutover_date=cutover, actor_user_id=user.id
    )
    await app_session.commit()
    assert row.kind == "opening_balance"

    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1, res
    entity, payload = fake.created[0]
    assert entity == "JournalEntry"
    assert payload["TxnDate"] == cutover.isoformat()
    assert payload["DocNumber"] == f"OB-{cutover.isoformat()}"
    debits = {
        ln["JournalEntryLineDetail"]["AccountRef"]["value"]: ln["Amount"]
        for ln in payload["Line"]
        if ln["JournalEntryLineDetail"]["PostingType"] == "Debit"
    }
    credits = {
        ln["JournalEntryLineDetail"]["AccountRef"]["value"]: ln["Amount"]
        for ln in payload["Line"]
        if ln["JournalEntryLineDetail"]["PostingType"] == "Credit"
    }
    assert debits == {"QBO_BANK": 130.0}
    assert credits == {"QBO_LOAN": 30.0, "QBO_REV": 100.0}

    # The synced row is the 5c gate's evidence.
    status_row = await opening_balance.seed_status(app_session)
    assert status_row is not None and status_row.status == "synced"


@pytest.mark.asyncio
async def test_enqueue_refuses_unmapped_and_duplicate(
    app_session: AsyncSession,
) -> None:
    user, bank, loan, revenue = await _seed_books(app_session)
    await _enable_qbo(app_session)
    await _map_all(app_session, {bank.id: "QBO_BANK"})

    cutover = datetime.now(UTC).date()
    with pytest.raises(opening_balance.UnmappedAccountsError) as exc_info:
        await opening_balance.enqueue_opening_balance(
            app_session, cutover_date=cutover, actor_user_id=user.id
        )
    assert exc_info.value.codes == ["2000", "4000"]

    await _map_all(app_session, {loan.id: "QBO_LOAN", revenue.id: "QBO_REV"})
    await opening_balance.enqueue_opening_balance(
        app_session, cutover_date=cutover, actor_user_id=user.id
    )
    await app_session.commit()

    with pytest.raises(opening_balance.AlreadySeededError):
        await opening_balance.enqueue_opening_balance(
            app_session, cutover_date=cutover, actor_user_id=user.id
        )
