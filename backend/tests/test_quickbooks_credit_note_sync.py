"""QBO credit/debit-note sync (#316 Phase 3c-2, epic #312).

Credit notes → native CreditMemo; debit notes → JournalEntry with the customer
Entity on the A/R line (QBO has no native customer debit-memo). Delete on
reverse, plus the issue gating integration.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.credit_note import CreditNote, CreditNoteState, DebitNote, DebitNoteState
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceState
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services import credit_notes as cn_service
from app.services import debit_notes as dn_service
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
        self._n = 1000

    async def query(self, statement, entity):
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

    async def delete(self, entity, qbo_id, sync_token):
        self.deleted.append((entity, qbo_id))
        return {"Id": qbo_id, "status": "Deleted"}

    async def void(self, entity, qbo_id, sync_token):
        return {"Id": qbo_id, "SyncToken": "1"}


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


async def _enable(session: AsyncSession) -> None:
    await SettingsService.set("quickbooks.enabled", True, session=session, actor_user_id=None)
    await SettingsService.set(
        "quickbooks.default_sales_item_id", "ITEM-G", session=session, actor_user_id=None
    )
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
            "revenue": {"qbo_account_id": "REV"},
            "accounts_receivable": {"qbo_account_id": "AR"},
        },
        actor_user_id=None,
    )
    await session.commit()


async def _customer(session: AsyncSession) -> Customer:
    c = Customer(customer_number=f"C-{uuid.uuid4().hex[:6]}", display_name="Acme")
    session.add(c)
    await session.flush()
    return c


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
async def test_credit_note_builds_credit_memo(client, app_session: AsyncSession, settings_obj):
    await _enable(app_session)
    cust = await _customer(app_session)
    await outbox.enqueue(
        app_session,
        kind="credit_note",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": str(cust.id),
            "doc_number": "CN-1",
            "reason": "Return",
            "amount": "7.50",
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    entity, payload = next((e, p) for e, p in fake.created if e == "CreditMemo")
    assert payload["CustomerRef"]["value"]
    assert payload["Line"][0]["Amount"] == 7.5
    assert payload["DocNumber"] == "CN-1"


@pytest.mark.asyncio
async def test_credit_note_reverse_deletes(client, app_session: AsyncSession, settings_obj):
    await _enable(app_session)
    lid = uuid.uuid4()
    await _seed_synced(app_session, "credit_note", lid, "CreditMemo", "QBO-CM-1")
    await outbox.enqueue(app_session, kind="credit_note", local_id=lid, payload={}, op="reverse")
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    assert fake.deleted == [("CreditMemo", "QBO-CM-1")]


@pytest.mark.asyncio
async def test_debit_note_builds_je_with_customer_entity(
    client, app_session: AsyncSession, settings_obj
):
    await _enable(app_session)
    cust = await _customer(app_session)
    await outbox.enqueue(
        app_session,
        kind="debit_note",
        local_id=uuid.uuid4(),
        payload={
            "lines": [
                {
                    "role": "accounts_receivable",
                    "posting": "debit",
                    "amount": "3",
                    "entity": {"type": "Customer", "local_id": str(cust.id)},
                },
                {"role": "revenue", "posting": "credit", "amount": "3"},
            ],
            "doc_number": "DN-1",
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    je = next(p for e, p in fake.created if e == "JournalEntry")
    ar = next(
        ln for ln in je["Line"] if ln["JournalEntryLineDetail"]["AccountRef"]["value"] == "AR"
    )
    assert ar["JournalEntryLineDetail"]["Entity"]["Type"] == "Customer"
    assert ar["JournalEntryLineDetail"]["Entity"]["EntityRef"]["value"]


@pytest.mark.asyncio
async def test_debit_note_reverse_deletes_je(client, app_session: AsyncSession, settings_obj):
    await _enable(app_session)
    lid = uuid.uuid4()
    await _seed_synced(app_session, "debit_note", lid, "JournalEntry", "QBO-JE-1")
    await outbox.enqueue(app_session, kind="debit_note", local_id=lid, payload={}, op="reverse")
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    assert fake.deleted == [("JournalEntry", "QBO-JE-1")]


# --------------------------------------------------------------------------- #
# gating integration
# --------------------------------------------------------------------------- #
async def _customer_invoice(session, user_id):
    cust = await _customer(session)
    inv = Invoice(
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        created_by_user_id=user_id,
        state=InvoiceState.ISSUED,
        subtotal=Decimal("10"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("10"),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal("10"),
        currency="USD",
    )
    session.add(inv)
    await session.flush()
    return cust, inv


@pytest.mark.asyncio
async def test_credit_note_issue_gating(client, app_session: AsyncSession):
    await SettingsService.set("quickbooks.enabled", True, session=app_session, actor_user_id=None)
    user = await create_user(
        app_session,
        email="o@example.com",
        password="pw-correct",
        full_name="o",
        role="owner",
        bcrypt_rounds=4,
    )
    cust, inv = await _customer_invoice(app_session, user.id)
    note = CreditNote(
        credit_note_number=f"CN-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        invoice_id=inv.id,
        created_by_user_id=user.id,
        reason="Return",
        total_amount=Decimal("4"),
        state=CreditNoteState.DRAFT,
    )
    app_session.add(note)
    await app_session.commit()

    await cn_service.issue(app_session, credit_note_id=note.id, actor_user_id=user.id)
    await app_session.commit()
    await app_session.refresh(note)
    assert note.state == CreditNoteState.ISSUED
    assert note.posting_journal_entry_id is None
    row = (
        (
            await app_session.execute(
                select(QboSyncOutbox).where(QboSyncOutbox.kind == "credit_note")
            )
        )
        .scalars()
        .one()
    )
    assert row.payload["amount"] == "4.000000"


@pytest.mark.asyncio
async def test_debit_note_issue_gating(client, app_session: AsyncSession):
    await SettingsService.set("quickbooks.enabled", True, session=app_session, actor_user_id=None)
    user = await create_user(
        app_session,
        email="o2@example.com",
        password="pw-correct",
        full_name="o",
        role="owner",
        bcrypt_rounds=4,
    )
    cust, inv = await _customer_invoice(app_session, user.id)
    note = DebitNote(
        debit_note_number=f"DN-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        invoice_id=inv.id,
        created_by_user_id=user.id,
        reason="Surcharge",
        total_amount=Decimal("2"),
        state=DebitNoteState.DRAFT,
    )
    app_session.add(note)
    await app_session.commit()

    await dn_service.issue(app_session, debit_note_id=note.id, actor_user_id=user.id)
    await app_session.commit()
    await app_session.refresh(note)
    assert note.state == DebitNoteState.ISSUED
    assert note.posting_journal_entry_id is None
    row = (
        (await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "debit_note")))
        .scalars()
        .one()
    )
    assert row.payload["lines"][0]["entity"]["type"] == "Customer"
