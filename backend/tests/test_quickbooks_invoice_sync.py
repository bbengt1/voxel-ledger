"""QBO native Invoice sync (#316 Phase 3b-1, epic #312).

Gating at invoices.issue/void (enqueue vs local GL) + the native Invoice builder:
drain-time customer/item auto-mapping, fallback item for product-less lines,
manual tax, and void (with dependency-retry when the invoice isn't synced yet).
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
from app.models.invoice import Invoice, InvoiceItem, InvoiceItemKind, InvoiceState
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.product import Product
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services import invoices
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
        self._n = 500

    def seed(self, entity: str, obj: dict[str, Any]) -> None:
        self.store.setdefault(entity, {})[obj["Id"]] = obj

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


async def _enable_qbo(session: AsyncSession, *, revenue: bool = True) -> None:
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
    if revenue:
        await account_map.set_mappings(
            session, {"revenue": {"qbo_account_id": "RV"}}, actor_user_id=None
        )
    await session.commit()


async def _draft_invoice(
    session: AsyncSession, *, manual_line: bool = False
) -> tuple[Invoice, uuid.UUID]:
    user = await create_user(
        session,
        email=f"o{uuid.uuid4().hex[:6]}@example.com",
        password="pw-correct",
        full_name="owner",
        role="owner",
        bcrypt_rounds=4,
    )
    cust = Customer(
        customer_number=f"C-{uuid.uuid4().hex[:6]}", display_name="Acme", payment_terms_days=30
    )
    session.add(cust)
    await session.flush()
    inv = Invoice(
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        customer_id=cust.id,
        created_by_user_id=user.id,
        state=InvoiceState.DRAFT,
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
    if manual_line:
        line = InvoiceItem(
            invoice_id=inv.id,
            line_number=1,
            kind=InvoiceItemKind.MANUAL,
            description="Consulting",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
            extended_amount=Decimal("10"),
        )
    else:
        prod = Product(sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Widget", unit_price=Decimal("10"))
        session.add(prod)
        await session.flush()
        line = InvoiceItem(
            invoice_id=inv.id,
            line_number=1,
            kind=InvoiceItemKind.PRODUCT,
            product_id=prod.id,
            description="Widget",
            quantity=Decimal("1"),
            unit_price=Decimal("10"),
            extended_amount=Decimal("10"),
        )
    session.add(line)
    await session.commit()
    return inv, user.id


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


# --------------------------------------------------------------------------- #
# gating at the posting site
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_issue_enqueues_and_skips_local_gl(client, app_session: AsyncSession) -> None:
    await _enable_qbo(app_session)
    inv, actor = await _draft_invoice(app_session)

    issued = await invoices.issue(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()

    assert issued.state == InvoiceState.ISSUED
    assert issued.posting_journal_entry_id is None  # no local GL in QBO mode
    row = (
        (await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "invoice")))
        .scalars()
        .one()
    )
    assert row.op == "post"
    assert row.payload["doc_number"] == inv.invoice_number
    assert row.status == QboSyncStatus.PENDING.value


@pytest.mark.asyncio
async def test_void_enqueues_reverse(client, app_session: AsyncSession) -> None:
    await _enable_qbo(app_session)
    inv, actor = await _draft_invoice(app_session)
    await invoices.issue(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()

    await invoices.void(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()

    ops = {
        r.op
        for r in (
            await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "invoice"))
        ).scalars()
    }
    assert ops == {"post", "reverse"}


# --------------------------------------------------------------------------- #
# native Invoice builder
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_builder_creates_invoice_with_auto_mapped_refs(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    inv, actor = await _draft_invoice(app_session)
    await invoices.issue(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()

    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1

    entities = [e for e, _ in fake.created]
    assert "Customer" in entities  # auto-mapped
    assert "Item" in entities  # product auto-mapped
    assert "Invoice" in entities
    invoice_payload = next(p for e, p in fake.created if e == "Invoice")
    assert invoice_payload["CustomerRef"]["value"]
    assert invoice_payload["Line"][0]["SalesItemLineDetail"]["ItemRef"]["value"]


@pytest.mark.asyncio
async def test_manual_line_requires_fallback_item(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    inv, actor = await _draft_invoice(app_session, manual_line=True)
    await invoices.issue(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()

    # No fallback item configured → permanent failure.
    res = await outbox.run_pending(app_session, settings_obj, client=FakeQBO())
    assert res.failed == 1
    row = (await app_session.execute(select(QboSyncOutbox))).scalars().one()
    assert row.status == QboSyncStatus.FAILED.value
    assert "default_sales_item_id" in (row.last_error or "")

    # Configure it → re-enqueue + drain succeeds using the fallback item.
    await SettingsService.set(
        "quickbooks.default_sales_item_id", "ITEM-99", session=app_session, actor_user_id=None
    )
    row.status = QboSyncStatus.PENDING.value
    await app_session.commit()
    fake = FakeQBO()
    res2 = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res2.synced == 1
    inv_payload = next(p for e, p in fake.created if e == "Invoice")
    assert inv_payload["Line"][0]["SalesItemLineDetail"]["ItemRef"]["value"] == "ITEM-99"


@pytest.mark.asyncio
async def test_manual_tax_is_attached(client, app_session: AsyncSession, settings_obj) -> None:
    await _enable_qbo(app_session)
    cust = Customer(customer_number=f"C-{uuid.uuid4().hex[:6]}", display_name="TaxCo")
    app_session.add(cust)
    await app_session.flush()
    await outbox.enqueue(
        app_session,
        kind="invoice",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": str(cust.id),
            "doc_number": "INV-T",
            "tax_amount": "2.50",
            "lines": [
                {
                    "product_id": None,
                    "description": "x",
                    "qty": "1",
                    "unit_price": "10",
                    "amount": "10",
                }
            ],
        },
        op="post",
    )
    await SettingsService.set(
        "quickbooks.default_sales_item_id", "ITEM-1", session=app_session, actor_user_id=None
    )
    await app_session.commit()
    fake = FakeQBO()
    await outbox.run_pending(app_session, settings_obj, client=fake)
    inv_payload = next(p for e, p in fake.created if e == "Invoice")
    assert inv_payload["TxnTaxDetail"]["TotalTax"] == 2.5


# --------------------------------------------------------------------------- #
# void builder
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_void_builder_voids_synced_invoice(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    inv, actor = await _draft_invoice(app_session)
    await invoices.issue(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()
    fake = FakeQBO()
    await outbox.run_pending(app_session, settings_obj, client=fake)  # sync the invoice

    await invoices.void(app_session, invoice_id=inv.id, actor_user_id=actor)
    await app_session.commit()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    assert fake.voided and fake.voided[0][0] == "Invoice"


@pytest.mark.asyncio
async def test_void_retries_when_invoice_not_yet_synced(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable_qbo(app_session)
    # A reverse row with no synced post row → dependency not ready → retry.
    await outbox.enqueue(
        app_session,
        kind="invoice",
        local_id=uuid.uuid4(),
        payload={"invoice_id": str(uuid.uuid4())},
        op="reverse",
    )
    await app_session.commit()
    res = await outbox.run_pending(app_session, settings_obj, client=FakeQBO())
    assert res.retried == 1
    assert res.failed == 0
    row = (await app_session.execute(select(QboSyncOutbox))).scalars().one()
    assert row.status == QboSyncStatus.PENDING.value
