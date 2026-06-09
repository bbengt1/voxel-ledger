"""QBO native Payment sync (#316 Phase 3b-2, epic #312).

Gating at payments.apply_payment/unapply_payment + the native Payment builder:
LinkedTxn to the synced invoice, deposit-account handling, dependency-retry when
the invoice isn't synced yet, and void on unapply.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.customer import Customer
from app.models.invoice import Invoice, InvoiceState
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.payment import Payment, PaymentMethod, PaymentState
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services import payments
from app.services.auth import create_user
from app.services.quickbooks import account_map, outbox
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class FakeQBO:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, dict[str, Any]]] = {}
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.voided: list[tuple[str, str]] = []
        self._n = 700

    async def query(self, statement: str, entity: str) -> list[dict[str, Any]]:
        field = "Name" if re.search(r"\bName =", statement) else "DisplayName"
        m = re.search(r"= '(.*)'", statement)
        val = m.group(1) if m else None
        return [o for o in self.store.get(entity, {}).values() if o.get(field) == val]

    async def create(
        self, entity: str, payload: dict[str, Any], *, request_id: str | None = None
    ) -> dict[str, Any]:
        self.created.append((entity, payload))
        qid = str(self._n)
        self._n += 1
        obj = {**payload, "Id": qid, "SyncToken": "0"}
        self.store.setdefault(entity, {})[qid] = obj
        return obj

    async def read(self, entity: str, qbo_id: str) -> dict[str, Any]:
        return self.store.get(entity, {}).get(qbo_id, {"Id": qbo_id, "SyncToken": "0"})

    async def void(self, entity: str, qbo_id: str, sync_token: str) -> dict[str, Any]:
        self.voided.append((entity, qbo_id))
        return {"Id": qbo_id, "SyncToken": str(int(sync_token) + 1), "void": True}


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


async def _enable_qbo(session: AsyncSession, *, bank: bool = True) -> None:
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
    mapping = {"revenue": {"qbo_account_id": "RV"}}
    if bank:
        mapping["bank"] = {"qbo_account_id": "BANK1"}
    await account_map.set_mappings(session, mapping, actor_user_id=None)
    await session.commit()


async def _seed_synced_invoice(
    session: AsyncSession, invoice_local_id: uuid.UUID, qbo_id: str
) -> None:
    """Insert a SYNCED invoice post row so a payment can link to it."""
    row = await outbox.enqueue(
        session, kind="invoice", local_id=invoice_local_id, payload={}, op="post"
    )
    row.status = QboSyncStatus.SYNCED.value
    row.qbo_id = qbo_id
    await session.commit()


async def _customer(session: AsyncSession) -> Customer:
    c = Customer(customer_number=f"C-{uuid.uuid4().hex[:6]}", display_name="Acme")
    session.add(c)
    await session.flush()
    return c


async def _issued_invoice(session: AsyncSession, customer: Customer, user_id: uuid.UUID) -> Invoice:
    inv = Invoice(
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        customer_id=customer.id,
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
    return inv


# --------------------------------------------------------------------------- #
# gating at the posting site
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_apply_enqueues_and_skips_local_gl(client, app_session: AsyncSession) -> None:
    await _enable_qbo(app_session)
    user = await create_user(
        app_session,
        email="o@example.com",
        password="pw-correct",
        full_name="o",
        role="owner",
        bcrypt_rounds=4,
    )
    cust = await _customer(app_session)
    inv = await _issued_invoice(app_session, cust, user.id)
    pmt = Payment(
        payment_number=f"PMT-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        created_by_user_id=user.id,
        amount=Decimal("10"),
        method=PaymentMethod.CHECK,
        state=PaymentState.PENDING,
    )
    app_session.add(pmt)
    await app_session.commit()

    await payments.apply_payment(
        app_session, payment_id=pmt.id, applications=[(inv.id, "10")], actor_user_id=user.id
    )
    await app_session.commit()

    await app_session.refresh(pmt)
    await app_session.refresh(inv)
    assert pmt.state == PaymentState.APPLIED
    assert pmt.posting_journal_entry_id is None
    assert inv.amount_outstanding == Decimal("10.000000") - Decimal("10")  # 0
    row = (
        (await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "payment")))
        .scalars()
        .one()
    )
    assert row.op == "post"
    assert row.payload["applications"][0]["invoice_id"] == str(inv.id)


# --------------------------------------------------------------------------- #
# native Payment builder
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_builder_creates_payment_linked_to_invoice(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    cust = await _customer(app_session)
    inv_local = uuid.uuid4()
    await _seed_synced_invoice(app_session, inv_local, "QBO-INV-9")
    await outbox.enqueue(
        app_session,
        kind="payment",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": str(cust.id),
            "amount": "10",
            "txn_date": "2026-06-01",
            "deposit_to_undeposited": False,
            "applications": [{"invoice_id": str(inv_local), "amount": "10"}],
        },
        op="post",
    )
    await app_session.commit()

    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    pay = next(p for e, p in fake.created if e == "Payment")
    assert pay["TotalAmt"] == 10.0
    assert pay["Line"][0]["LinkedTxn"][0]["TxnId"] == "QBO-INV-9"
    assert pay["DepositToAccountRef"]["value"] == "BANK1"


@pytest.mark.asyncio
async def test_payment_to_undeposited_omits_deposit_ref(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session, bank=False)  # no bank role mapped
    cust = await _customer(app_session)
    inv_local = uuid.uuid4()
    await _seed_synced_invoice(app_session, inv_local, "QBO-INV-1")
    await outbox.enqueue(
        app_session,
        kind="payment",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": str(cust.id),
            "amount": "5",
            "deposit_to_undeposited": True,
            "applications": [{"invoice_id": str(inv_local), "amount": "5"}],
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    pay = next(p for e, p in fake.created if e == "Payment")
    assert "DepositToAccountRef" not in pay


@pytest.mark.asyncio
async def test_payment_retries_until_invoice_synced(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    cust = await _customer(app_session)
    # Invoice referenced but NOT synced → dependency not ready → retry.
    await outbox.enqueue(
        app_session,
        kind="payment",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": str(cust.id),
            "amount": "10",
            "deposit_to_undeposited": True,
            "applications": [{"invoice_id": str(uuid.uuid4()), "amount": "10"}],
        },
        op="post",
    )
    await app_session.commit()
    res = await outbox.run_pending(app_session, settings_obj, client=FakeQBO())
    assert res.retried == 1 and res.failed == 0
    row = (await app_session.execute(select(QboSyncOutbox))).scalars().one()
    assert row.status == QboSyncStatus.PENDING.value


# --------------------------------------------------------------------------- #
# unapply → void
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_unapply_enqueues_reverse_and_voids(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    user = await create_user(
        app_session,
        email="o2@example.com",
        password="pw-correct",
        full_name="o",
        role="owner",
        bcrypt_rounds=4,
    )
    cust = await _customer(app_session)
    inv = await _issued_invoice(app_session, cust, user.id)
    await _seed_synced_invoice(app_session, inv.id, "QBO-INV-77")
    pmt = Payment(
        payment_number=f"PMT-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        created_by_user_id=user.id,
        amount=Decimal("10"),
        method=PaymentMethod.CHECK,
        state=PaymentState.PENDING,
    )
    app_session.add(pmt)
    await app_session.commit()
    await payments.apply_payment(
        app_session, payment_id=pmt.id, applications=[(inv.id, "10")], actor_user_id=user.id
    )
    await app_session.commit()
    fake = FakeQBO()
    await outbox.run_pending(app_session, settings_obj, client=fake)  # sync the payment

    await payments.unapply_payment(app_session, payment_id=pmt.id, actor_user_id=user.id)
    await app_session.commit()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    assert fake.voided and fake.voided[0][0] == "Payment"
