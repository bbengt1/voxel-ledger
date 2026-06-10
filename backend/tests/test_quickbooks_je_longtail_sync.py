"""QBO JE long-tail sync — Phase 3d-1 asset lifecycle (#316, epic #312).

The depreciation / fixed-asset-acquisition / disposal postings are role-tagged
JournalEntries. These tests confirm each registered kind builds a balanced QBO
JournalEntry with the right account refs (the gating at each site follows the
surgical-gate pattern already validated in 3b/3c and is covered by the local-mode
regression suite).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.services.quickbooks import account_map, outbox
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession


class FakeQBO:
    def __init__(self) -> None:
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[tuple[str, str]] = []
        self._n = 1100

    async def create(self, entity, payload, *, request_id=None):
        self.created.append((entity, payload))
        self._n += 1
        return {**payload, "Id": str(self._n), "SyncToken": "0"}

    async def read(self, entity, qbo_id):
        return {"Id": qbo_id, "SyncToken": "0"}

    async def delete(self, entity, qbo_id, token):
        self.deleted.append((entity, qbo_id))
        return {"Id": qbo_id, "status": "Deleted"}


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


async def _enable(session: AsyncSession) -> None:
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
    await account_map.set_mappings(
        session,
        {
            "depreciation_expense": {"qbo_account_id": "DEPEXP"},
            "accumulated_depreciation": {"qbo_account_id": "ACCDEP"},
            "fixed_asset": {"qbo_account_id": "FA"},
            "bank": {"qbo_account_id": "BANK"},
            "gain_loss_on_disposal": {"qbo_account_id": "GL"},
            # Phase 3d-2 long-tail roles.
            "tax_liability": {"qbo_account_id": "TAXLIAB"},
            "expense": {"qbo_account_id": "EXP"},
            "employee_reimbursable": {"qbo_account_id": "EMPREIMB"},
            "undeposited_funds": {"qbo_account_id": "UNDEP"},
            "payout": {"qbo_account_id": "PAYOUT"},
            "marketplace_fee": {"qbo_account_id": "MKTFEE"},
            "settlement_adjustment": {"qbo_account_id": "SETADJ"},
            "marketplace_clearing": {"qbo_account_id": "MKTCLR"},
        },
        actor_user_id=None,
    )
    await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,lines,expected_refs",
    [
        (
            "depreciation",
            [
                {"role": "depreciation_expense", "posting": "debit", "amount": "5"},
                {"role": "accumulated_depreciation", "posting": "credit", "amount": "5"},
            ],
            {"DEPEXP", "ACCDEP"},
        ),
        (
            "fixed_asset_acquisition",
            [
                {"role": "fixed_asset", "posting": "debit", "amount": "100"},
                {"role": "bank", "posting": "credit", "amount": "100"},
            ],
            {"FA", "BANK"},
        ),
        (
            "fixed_asset_disposal",
            [
                {"role": "accumulated_depreciation", "posting": "debit", "amount": "40"},
                {"role": "bank", "posting": "debit", "amount": "70"},
                {"role": "fixed_asset", "posting": "credit", "amount": "100"},
                {"role": "gain_loss_on_disposal", "posting": "credit", "amount": "10"},
            ],
            {"ACCDEP", "BANK", "FA", "GL"},
        ),
        # --- Phase 3d-2 long-tail role-JE sites ---
        (
            "tax_remittance",
            [
                {"role": "tax_liability", "posting": "debit", "amount": "30"},
                {"role": "bank", "posting": "credit", "amount": "30"},
            ],
            {"TAXLIAB", "BANK"},
        ),
        (
            "expense_claim",
            [
                {"role": "expense", "posting": "debit", "amount": "12"},
                {"role": "employee_reimbursable", "posting": "credit", "amount": "12"},
            ],
            {"EXP", "EMPREIMB"},
        ),
        (
            "deposit_slip",
            [
                {"role": "bank", "posting": "debit", "amount": "200"},
                {"role": "undeposited_funds", "posting": "credit", "amount": "200"},
            ],
            {"BANK", "UNDEP"},
        ),
        (
            "settlement",
            [
                {"role": "payout", "posting": "debit", "amount": "90"},
                {"role": "marketplace_fee", "posting": "debit", "amount": "10"},
                {"role": "settlement_adjustment", "posting": "credit", "amount": "5"},
                {"role": "marketplace_clearing", "posting": "credit", "amount": "95"},
            ],
            {"PAYOUT", "MKTFEE", "SETADJ", "MKTCLR"},
        ),
    ],
)
async def test_longtail_je_kinds_build(
    client, app_session: AsyncSession, settings_obj, kind, lines, expected_refs
) -> None:
    await _enable(app_session)
    await outbox.enqueue(
        app_session,
        kind=kind,
        local_id=uuid.uuid4(),
        payload={"lines": lines, "private_note": f"{kind} test"},
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1, res
    entity, payload = fake.created[0]
    assert entity == "JournalEntry"
    refs = {ln["JournalEntryLineDetail"]["AccountRef"]["value"] for ln in payload["Line"]}
    assert refs == expected_refs


@pytest.mark.asyncio
async def test_tax_remittance_reverse_deletes_journal_entry(
    client, app_session: AsyncSession, settings_obj
) -> None:
    """Cancelling a remittance deletes the synced QBO JournalEntry."""
    await _enable(app_session)
    local_id = uuid.uuid4()
    await outbox.enqueue(
        app_session,
        kind="tax_remittance",
        local_id=local_id,
        payload={
            "lines": [
                {"role": "tax_liability", "posting": "debit", "amount": "30"},
                {"role": "bank", "posting": "credit", "amount": "30"},
            ],
            "private_note": "remit",
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1, res

    # Now reverse it.
    await outbox.enqueue(
        app_session,
        kind="tax_remittance",
        local_id=local_id,
        payload={"tax_remittance_id": str(local_id)},
        op="reverse",
    )
    await app_session.commit()
    res2 = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res2.synced == 1, res2
    assert fake.deleted, "expected a JournalEntry delete on reverse"
    assert fake.deleted[0][0] == "JournalEntry"
