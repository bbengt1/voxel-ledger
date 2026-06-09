"""QBO native Sale sync (#316 Phase 3b-3, epic #312).

The sale builder: Invoice (customer) / SalesReceipt (walk-in) with item +
shipping + discount lines and manual tax, the COGS/fee JournalEntry, and void on
reverse (using the stored doc type). Builder-focused (the issue/void gating
mirrors the already-tested invoice/payment pattern).
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from app.core.settings import Settings
from app.models.customer import Customer
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.quickbooks import account_map, outbox
from app.services.settings.service import SettingsService
from sqlalchemy.ext.asyncio import AsyncSession


class FakeQBO:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, dict[str, Any]]] = {}
        self.created: list[tuple[str, dict[str, Any]]] = []
        self.voided: list[tuple[str, str]] = []
        self._n = 800

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
        return {"Id": qbo_id, "SyncToken": "1", "void": True}


@pytest.fixture
def settings_obj() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        jwt_secret_key="test-secret-key-not-a-real-secret-xx",
    )


async def _enable(session: AsyncSession) -> None:
    await SettingsService.set("quickbooks.enabled", True, session=session, actor_user_id=None)
    await SettingsService.set(
        "quickbooks.default_sales_item_id", "ITEM-GEN", session=session, actor_user_id=None
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
            "bank": {"qbo_account_id": "BANK"},
            "cogs": {"qbo_account_id": "COGS"},
            "inventory": {"qbo_account_id": "INV"},
            "marketplace_fee": {"qbo_account_id": "FEE"},
            "marketplace_clearing": {"qbo_account_id": "CLR"},
        },
        actor_user_id=None,
    )
    await session.commit()


async def _seed_synced_sale(
    session: AsyncSession, local_id: uuid.UUID, entity: str, qbo_id: str
) -> None:
    row = await outbox.enqueue(session, kind="sale", local_id=local_id, payload={}, op="post")
    row.status = QboSyncStatus.SYNCED.value
    row.qbo_entity_type = entity
    row.qbo_id = qbo_id
    await session.commit()


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_sale_with_customer_builds_invoice(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable(app_session)
    cust = Customer(customer_number=f"C-{uuid.uuid4().hex[:6]}", display_name="Acme")
    app_session.add(cust)
    await app_session.flush()
    await outbox.enqueue(
        app_session,
        kind="sale",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": str(cust.id),
            "doc_number": "S-1",
            "txn_date": "2026-06-01",
            "discount_amount": "1",
            "shipping_amount": "2",
            "tax_amount": "0.50",
            "lines": [
                {
                    "product_id": None,
                    "description": "Item",
                    "qty": "1",
                    "unit_price": "10",
                    "amount": "10",
                }
            ],
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    entity, payload = next((e, p) for e, p in fake.created if e in ("Invoice", "SalesReceipt"))
    assert entity == "Invoice"
    assert payload["CustomerRef"]["value"]
    detail_types = [line["DetailType"] for line in payload["Line"]]
    assert detail_types.count("SalesItemLineDetail") == 2  # item + shipping
    assert "DiscountLineDetail" in detail_types
    assert payload["TxnTaxDetail"]["TotalTax"] == 0.5


@pytest.mark.asyncio
async def test_walkin_sale_builds_salesreceipt(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable(app_session)
    await outbox.enqueue(
        app_session,
        kind="sale",
        local_id=uuid.uuid4(),
        payload={
            "customer_id": None,
            "doc_number": "S-2",
            "txn_date": "2026-06-01",
            "lines": [
                {
                    "product_id": None,
                    "description": "Item",
                    "qty": "1",
                    "unit_price": "5",
                    "amount": "5",
                }
            ],
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    entity, payload = fake.created[0]
    assert entity == "SalesReceipt"
    assert "CustomerRef" not in payload
    assert payload["DepositToAccountRef"]["value"] == "BANK"


@pytest.mark.asyncio
async def test_sale_cogs_builds_journal_entry(
    client, app_session: AsyncSession, settings_obj
) -> None:
    await _enable(app_session)
    await outbox.enqueue(
        app_session,
        kind="sale_cogs",
        local_id=uuid.uuid4(),
        payload={
            "lines": [
                {"role": "cogs", "posting": "debit", "amount": "4"},
                {"role": "inventory", "posting": "credit", "amount": "4"},
                {"role": "marketplace_fee", "posting": "debit", "amount": "1"},
                {"role": "marketplace_clearing", "posting": "credit", "amount": "1"},
            ]
        },
        op="post",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    entity, payload = fake.created[0]
    assert entity == "JournalEntry"
    refs = {line["JournalEntryLineDetail"]["AccountRef"]["value"] for line in payload["Line"]}
    assert refs == {"COGS", "INV", "FEE", "CLR"}


@pytest.mark.asyncio
@pytest.mark.parametrize("doc_entity", ["Invoice", "SalesReceipt"])
async def test_sale_reverse_voids_stored_doc_type(
    client, app_session: AsyncSession, settings_obj, doc_entity: str
) -> None:
    await _enable(app_session)
    local_id = uuid.uuid4()
    await _seed_synced_sale(app_session, local_id, doc_entity, "QBO-DOC-1")
    await outbox.enqueue(
        app_session,
        kind="sale",
        local_id=local_id,
        payload={"sale_id": str(local_id)},
        op="reverse",
    )
    await app_session.commit()
    fake = FakeQBO()
    res = await outbox.run_pending(app_session, settings_obj, client=fake)
    assert res.synced == 1
    assert fake.voided == [(doc_entity, "QBO-DOC-1")]


# --------------------------------------------------------------------------- #
# integration: the post_for_sale gate enqueues instead of posting local GL
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_post_for_sale_gating_enqueues(client, app_session: AsyncSession) -> None:
    from decimal import Decimal

    from app.models.inventory_transaction import KIND_PRODUCTION_IN
    from app.services import cogs as cogs_pkg
    from app.services import inventory_locations as locations_service
    from app.services import inventory_transactions as inventory_tx_service
    from app.services import products as products_service
    from app.services import sales as sales_service
    from sqlalchemy import select

    from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user

    await SettingsService.set("quickbooks.enabled", True, session=app_session, actor_user_id=None)
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    loc = await locations_service.create(
        app_session, name="WS", code="WS", kind="workshop", actor_user_id=None
    )
    prod = await products_service.create(
        app_session,
        name="W",
        description=None,
        unit_price=Decimal("20.00"),
        sku=f"PRD-{uuid.uuid4().hex[:6]}",
        actor_user_id=None,
    )
    await app_session.commit()
    await inventory_tx_service.record(
        app_session,
        kind=KIND_PRODUCTION_IN,
        entity_kind="product",
        entity_id=prod.id,
        location_id=loc.id,
        quantity=Decimal("10"),
        unit_cost=Decimal("2.00"),
        actor_user_id=None,
    )
    await app_session.commit()
    sale = await sales_service.create_draft(
        app_session,
        channel_id=channel.id,
        external_order_id=None,
        customer_name="C",
        customer_email=None,
        occurred_at=datetime.now(UTC),
        items=[
            {
                "kind": "product",
                "product_id": str(prod.id),
                "description": "W",
                "quantity": "2",
                "unit_price": "20.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()

    # QBO mode: no local JE; a sale doc + a COGS JE were enqueued.
    await app_session.refresh(sale)
    assert sale.posting_journal_entry_id is None
    kinds = {
        r.kind
        for r in (
            await app_session.execute(
                select(QboSyncOutbox).where(QboSyncOutbox.local_id == sale.id)
            )
        ).scalars()
    }
    assert kinds == {"sale", "sale_cogs"}
    assert cogs_pkg is not None  # import smoke
