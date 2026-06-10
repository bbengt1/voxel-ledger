"""QBO native AP sync — Bills + BillPayments (#316 Phase 3c-1, epic #312).

Native Bill / BillPayment builders (vendor auto-map, AccountBasedExpenseLine,
LinkedTxn[Bill], bank deposit), withholding JE, delete-on-reverse, the JE
Entity-resolution for A/P lines (the 2026-06-10 sandbox finding), and the
bills.issue gating integration.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.bill import Bill, BillItem, BillItemKind, BillState
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.models.vendor import Vendor
from app.services import bills as bills_service
from app.services.auth import create_user
from app.services.quickbooks import account_map, outbox
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FakeQBO:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, dict[str, Any]]] = {}
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.deleted: list[tuple[str, str]] = []
        self._n = 900

    async def query(self, statement: str, entity: str) -> list[dict[str, Any]]:
        field = "Name" if re.search(r"\bName =", statement) else "DisplayName"
        m = re.search(r"= '(.*)'", statement)
        val = m.group(1) if m else None
        return [o for o in self.store.get(entity, {}).values() if o.get(field) == val]

    async def create(self, entity, payload, *, request_id=None):
        self.created.append((entity, payload))
        qid = str(self._n)
        self._n += 1
        obj = {**payload, "Id": qid, "SyncToken": "0"}
        self.store.setdefault(entity, {})[qid] = obj
        return obj

    async def read(self, entity, qbo_id):
        return self.store.get(entity, {}).get(qbo_id, {"Id": qbo_id, "SyncToken": "0"})

    async def void(self, entity, qbo_id, sync_token):
        return {"Id": qbo_id, "SyncToken": "1", "void": True}

    async def delete(self, entity, qbo_id, sync_token):
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
            "expense": {"qbo_account_id": "EXP"},
            "tax_expense": {"qbo_account_id": "TAXEXP"},
            "accounts_payable": {"qbo_account_id": "AP"},
            "bank": {"qbo_account_id": "BANK"},
            "tax_liability": {"qbo_account_id": "TAXLIA"},
            "revenue": {"qbo_account_id": "REV"},
        },
        actor_user_id=None,
    )
    await session.commit()


async def _vendor(session: AsyncSession) -> Vendor:
    v = Vendor(vendor_number=f"V-{uuid.uuid4().hex[:6]}", display_name="Supplier")
    session.add(v)
    await session.flush()
    return v


async def _seed_synced(session, kind, local_id, entity, qbo_id) -> None:
    row = await outbox.enqueue(session, kind=kind, local_id=local_id, payload={}, op="post")
    row.status = QboSyncStatus.SYNCED.value
    row.qbo_entity_type = entity
    row.qbo_id = qbo_id
    await session.commit()


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_bill_builder(client, app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    v = await _vendor(app_session)
    await outbox.enqueue(
        app_session,
        kind="bill",
        local_id=uuid.uuid4(),
        payload={
            "vendor_id": str(v.id),
            "vendor_invoice_number": "INV-X",
            "txn_date": "2026-06-01",
            "tax_amount": "1.50",
            "lines": [{"description": "Parts", "amount": "20"}],
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    entity, payload = fake.created[-1]
    assert entity == "Bill"
    assert payload["VendorRef"]["value"]
    accts = [ln["AccountBasedExpenseLineDetail"]["AccountRef"]["value"] for ln in payload["Line"]]
    assert "EXP" in accts and "TAXEXP" in accts
    assert payload["DocNumber"] == "INV-X"


@pytest.mark.asyncio
async def test_bill_reverse_deletes(client, app_session: AsyncSession, settings_obj) -> None:
    await _enable(app_session)
    lid = uuid.uuid4()
    await _seed_synced(app_session, "bill", lid, "Bill", "QBO-BILL-1")
    await outbox.enqueue(app_session, kind="bill", local_id=lid, payload={}, op="reverse")
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    assert fake.deleted == [("Bill", "QBO-BILL-1")]


@pytest.mark.asyncio
async def test_bill_payment_builder_links_bill(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable(app_session)
    v = await _vendor(app_session)
    bill_local = uuid.uuid4()
    await _seed_synced(app_session, "bill", bill_local, "Bill", "QBO-BILL-9")
    await outbox.enqueue(
        app_session,
        kind="bill_payment",
        local_id=uuid.uuid4(),
        payload={
            "vendor_id": str(v.id),
            "amount": "20",
            "txn_date": "2026-06-02",
            "applications": [{"bill_id": str(bill_local), "amount": "20"}],
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    pay = next(p for e, p in fake.created if e == "BillPayment")
    assert pay["TotalAmt"] == 20.0
    assert pay["Line"][0]["LinkedTxn"][0]["TxnId"] == "QBO-BILL-9"
    assert pay["CheckPayment"]["BankAccountRef"]["value"] == "BANK"


@pytest.mark.asyncio
async def test_bill_payment_retries_until_bill_synced(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable(app_session)
    v = await _vendor(app_session)
    await outbox.enqueue(
        app_session,
        kind="bill_payment",
        local_id=uuid.uuid4(),
        payload={
            "vendor_id": str(v.id),
            "amount": "5",
            "applications": [{"bill_id": str(uuid.uuid4()), "amount": "5"}],
        },
        op="post",
    )
    await app_session.commit()
    res = await outbox.run_pending(app_session, settings_obj, client=FakeQBO())
    assert res.retried == 1 and res.failed == 0


@pytest.mark.asyncio
async def test_je_entity_resolves_vendor_for_ap_line(
    client, app_session: AsyncSession, settings_obj
) -> None:
    # The 2026-06-10 sandbox finding: an A/P JE line needs a Vendor Entity.
    await _enable(app_session)
    v = await _vendor(app_session)
    await outbox.enqueue(
        app_session,
        kind="bill_payment_withholding",
        local_id=uuid.uuid4(),
        payload={
            "lines": [
                {
                    "role": "accounts_payable",
                    "posting": "debit",
                    "amount": "3",
                    "entity": {"type": "Vendor", "local_id": str(v.id)},
                },
                {"role": "tax_liability", "posting": "credit", "amount": "3"},
            ],
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    je = next(p for e, p in fake.created if e == "JournalEntry")
    ap_line = next(
        ln for ln in je["Line"] if ln["JournalEntryLineDetail"]["AccountRef"]["value"] == "AP"
    )
    assert ap_line["JournalEntryLineDetail"]["Entity"]["Type"] == "Vendor"
    assert ap_line["JournalEntryLineDetail"]["Entity"]["EntityRef"]["value"]  # resolved id


# --------------------------------------------------------------------------- #
# gating integration
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_bills_issue_gating_enqueues(client, app_session: AsyncSession) -> None:
    await SettingsService.set("quickbooks.enabled", True, session=app_session, actor_user_id=None)
    user = await create_user(
        app_session,
        email="o@example.com",
        password="pw-correct",
        full_name="o",
        role="owner",
        bcrypt_rounds=4,
    )
    v = await _vendor(app_session)
    bill = Bill(
        bill_number=f"B-{uuid.uuid4().hex[:6]}",
        vendor_id=v.id,
        created_by_user_id=user.id,
        state=BillState.DRAFT,
        subtotal=Decimal("20"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("20"),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal("20"),
        currency="USD",
    )
    app_session.add(bill)
    await app_session.flush()
    app_session.add(
        BillItem(
            bill_id=bill.id,
            line_number=1,
            kind=BillItemKind.MANUAL,
            description="Parts",
            quantity=Decimal("1"),
            unit_price=Decimal("20"),
            extended_amount=Decimal("20"),
        )
    )
    await app_session.commit()

    await bills_service.issue(app_session, bill_id=bill.id, actor_user_id=user.id)
    await app_session.commit()

    await app_session.refresh(bill)
    assert bill.state == BillState.ISSUED
    assert bill.posting_journal_entry_id is None
    row = (
        (await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "bill")))
        .scalars()
        .one()
    )
    assert row.op == "post"
    assert row.payload["vendor_id"] == str(v.id)
