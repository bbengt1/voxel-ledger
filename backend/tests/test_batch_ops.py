"""Batch operations tests (Phase 11.3, #195)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from app.models.audit import AuditLog
from app.models.bill import Bill, BillState
from app.models.customer import Customer, CustomerState
from app.models.invoice import Invoice, InvoiceState
from app.models.product import Product
from app.models.vendor import Vendor, VendorState
from app.services import batch_ops as service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_user


async def _seed_customer(
    session: AsyncSession, *, name: str = "Cust", number: str = "C-1"
) -> Customer:
    c = Customer(
        id=uuid.uuid4(),
        customer_number=number,
        display_name=name,
        state=CustomerState.ACTIVE,
    )
    session.add(c)
    await session.flush()
    return c


async def _seed_vendor(
    session: AsyncSession, *, name: str = "Vend", number: str = "V-1"
) -> Vendor:
    v = Vendor(
        id=uuid.uuid4(),
        vendor_number=number,
        display_name=name,
        payment_terms_days=30,
        state=VendorState.ACTIVE,
    )
    session.add(v)
    await session.flush()
    return v


async def _seed_product(session: AsyncSession, *, sku: str = "S-1") -> Product:
    p = Product(
        id=uuid.uuid4(),
        sku=sku,
        name=f"product {sku}",
        unit_price=Decimal("9.99"),
        category="old",
    )
    session.add(p)
    await session.flush()
    return p


async def _seed_open_invoice(
    session: AsyncSession, *, customer_id: uuid.UUID, user_id: uuid.UUID
) -> Invoice:
    inv = Invoice(
        id=uuid.uuid4(),
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        customer_id=customer_id,
        subtotal=Decimal("10.00"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("10.00"),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal("10.00"),
        state=InvoiceState.ISSUED,
        created_by_user_id=user_id,
    )
    session.add(inv)
    await session.flush()
    return inv


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_archive_preview_surfaces_blocker(
    client, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    c_clean = await _seed_customer(app_session, name="Clean", number="C-CLEAN")
    c_blocked = await _seed_customer(app_session, name="Blocked", number="C-BLOCKED")
    await _seed_open_invoice(
        app_session, customer_id=c_blocked.id, user_id=user.id
    )
    await app_session.commit()

    result = await service.preview(
        session=app_session,
        entity="customer",
        ids=[c_clean.id, c_blocked.id],
        action="archive",
    )
    assert result.matched_count == 2
    blocked_ids = {b.id for b in result.blockers}
    assert c_blocked.id in blocked_ids
    assert c_clean.id not in blocked_ids


@pytest.mark.asyncio
async def test_customer_archive_commit_applies_and_skips(
    client, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    c_clean = await _seed_customer(app_session, name="Clean", number="C-CLEAN")
    c_blocked = await _seed_customer(app_session, name="Blocked", number="C-BLOCKED")
    await _seed_open_invoice(
        app_session, customer_id=c_blocked.id, user_id=user.id
    )
    await app_session.commit()

    result = await service.commit(
        session=app_session,
        entity="customer",
        ids=[c_clean.id, c_blocked.id],
        action="archive",
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.applied == 1
    assert result.skipped == 1
    assert {b.id for b in result.blockers} == {c_blocked.id}

    assert c_clean.state == CustomerState.ARCHIVED
    assert c_blocked.state == CustomerState.ACTIVE


@pytest.mark.asyncio
async def test_product_set_category_requires_param(
    client, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    p = await _seed_product(app_session)
    await app_session.commit()

    with pytest.raises(service.InvalidActionParamsError):
        await service.commit(
            session=app_session,
            entity="product",
            ids=[p.id],
            action="set_category",
            actor_user_id=user.id,
            params={},
        )


@pytest.mark.asyncio
async def test_product_set_category_applies(
    client, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    p1 = await _seed_product(app_session, sku="A")
    p2 = await _seed_product(app_session, sku="B")
    await app_session.commit()

    result = await service.commit(
        session=app_session,
        entity="product",
        ids=[p1.id, p2.id],
        action="set_category",
        actor_user_id=user.id,
        params={"category": "fresh"},
    )
    await app_session.commit()
    assert result.applied == 2
    assert p1.category == "fresh"
    assert p2.category == "fresh"


@pytest.mark.asyncio
async def test_unknown_entity_raises(client, app_session: AsyncSession) -> None:
    with pytest.raises(service.UnknownEntityError):
        await service.preview(
            session=app_session, entity="nope", ids=[uuid.uuid4()], action="archive"
        )


@pytest.mark.asyncio
async def test_unknown_action_raises(client, app_session: AsyncSession) -> None:
    c = await _seed_customer(app_session)
    await app_session.commit()
    with pytest.raises(service.UnknownActionError):
        await service.preview(
            session=app_session, entity="customer", ids=[c.id], action="set_category"
        )


@pytest.mark.asyncio
async def test_audit_row_records_ids_not_pii(
    client, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    c = await _seed_customer(app_session, name="PII-SENSITIVE", number="C-PII")
    await app_session.commit()

    await service.commit(
        session=app_session,
        entity="customer",
        ids=[c.id],
        action="archive",
        actor_user_id=user.id,
    )
    await app_session.commit()

    audit = (
        await app_session.execute(
            select(AuditLog).where(AuditLog.event_type == "batch_ops.BatchCommitted")
        )
    ).scalar_one()
    assert audit.payload_excerpt is not None
    assert str(c.id) in audit.payload_excerpt.get("applied_ids", [])
    # Customer display name is PII — must NOT appear in excerpt.
    blob = repr(audit.payload_excerpt)
    assert "PII-SENSITIVE" not in blob


@pytest.mark.asyncio
async def test_bill_mark_void_blocks_non_draft(
    client, app_session: AsyncSession
) -> None:
    user = await seed_user(app_session)
    vendor = await _seed_vendor(app_session)
    draft = Bill(
        id=uuid.uuid4(),
        bill_number="B-DRAFT",
        vendor_id=vendor.id,
        subtotal=Decimal("0"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("0"),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal("0"),
        state=BillState.DRAFT,
        created_by_user_id=user.id,
    )
    issued = Bill(
        id=uuid.uuid4(),
        bill_number="B-ISSUED",
        vendor_id=vendor.id,
        subtotal=Decimal("10"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("10"),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal("10"),
        state=BillState.ISSUED,
        created_by_user_id=user.id,
    )
    app_session.add_all([draft, issued])
    await app_session.commit()

    result = await service.commit(
        session=app_session,
        entity="bill",
        ids=[draft.id, issued.id],
        action="mark_void",
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.applied == 1
    assert result.skipped == 1
    assert draft.state == BillState.VOID
    assert issued.state == BillState.ISSUED


# ---------------------------------------------------------------------------
# Endpoint smoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_endpoint_role_matrix(client, app_session: AsyncSession) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    sales_token = await token_for(Role.SALES, client, app_session)
    resp = await client.post(
        "/api/v1/batch/preview",
        headers={"Authorization": f"Bearer {sales_token}"},
        json={"entity": "customer", "ids": [], "action": "archive"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_endpoint_preview_and_commit(client, app_session: AsyncSession) -> None:
    from app.models.auth import Role

    from tests._sales_helpers import token_for

    token = await token_for(Role.OWNER, client, app_session)
    c1 = await _seed_customer(app_session, name="A", number="C-A")
    c2 = await _seed_customer(app_session, name="B", number="C-B")
    await app_session.commit()

    preview_resp = await client.post(
        "/api/v1/batch/preview",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "entity": "customer",
            "ids": [str(c1.id), str(c2.id)],
            "action": "archive",
        },
    )
    assert preview_resp.status_code == 200, preview_resp.text
    assert preview_resp.json()["matched_count"] == 2

    commit_resp = await client.post(
        "/api/v1/batch/commit",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "entity": "customer",
            "ids": [str(c1.id), str(c2.id)],
            "action": "archive",
        },
    )
    assert commit_resp.status_code == 200, commit_resp.text
    body = commit_resp.json()
    assert body["applied"] == 2
    assert body["skipped"] == 0
    assert body["audit_id"]
