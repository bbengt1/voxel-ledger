"""Control Center tests (Phase 11.4, #196)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from app.models.approval_request import ApprovalRequest, ApprovalState
from app.models.auth import Role
from app.models.invoice import Invoice, InvoiceState
from app.models.webhook import (
    WebhookDelivery,
    WebhookDeliveryStatus,
    WebhookSubscription,
)
from app.services import control_center
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import seed_user, token_for


@pytest.mark.asyncio
async def test_empty_install_zeros(client, app_session: AsyncSession) -> None:
    cc = await control_center.build(app_session)
    assert cc.pending_approvals.count == 0
    assert cc.low_stock_alerts.count == 0
    assert cc.overdue_invoices.count == 0
    assert cc.overdue_invoices.amount_total == Decimal("0")
    assert cc.overdue_bills.count == 0
    assert cc.failed_jobs.count == 0
    assert cc.webhook_dlq.count == 0
    assert cc.ws_health.moonraker_ws_connected is False
    assert cc.ws_health.last_event_at is None


@pytest.mark.asyncio
async def test_aggregates_each_section(client, app_session: AsyncSession) -> None:
    from app.models.customer import Customer, CustomerState

    user = await seed_user(app_session, email="cc@example.com")

    # Pending approval.
    appr = ApprovalRequest(
        id=uuid.uuid4(),
        request_type="journal_entry.high_amount",
        subject_kind="journal_entry",
        subject_id=uuid.uuid4(),
        state=ApprovalState.PENDING.value,
        requested_by_user_id=user.id,
        threshold_amount=Decimal("1000.00"),
        payload={},
    )
    app_session.add(appr)

    # Overdue invoice.
    customer = Customer(
        id=uuid.uuid4(),
        customer_number="CC-CUST",
        display_name="Overdue Co",
        state=CustomerState.ACTIVE,
    )
    app_session.add(customer)
    await app_session.flush()
    inv = Invoice(
        id=uuid.uuid4(),
        invoice_number="INV-OVERDUE-1",
        customer_id=customer.id,
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("100.00"),
        amount_paid=Decimal("0"),
        amount_outstanding=Decimal("100.00"),
        state=InvoiceState.OVERDUE,
        created_by_user_id=user.id,
    )
    app_session.add(inv)

    # Dead-letter delivery.
    sub = WebhookSubscription(
        id=uuid.uuid4(),
        name="dlq-hook",
        target_url="https://example.test/x",
        secret="x" * 64,
        event_types=["test.TestEvent"],
        is_active=True,
    )
    app_session.add(sub)
    await app_session.flush()
    dlq = WebhookDelivery(
        id=uuid.uuid4(),
        subscription_id=sub.id,
        event_id=None,
        event_type="test.TestEvent",
        payload={},
        attempt_count=5,
        last_status=WebhookDeliveryStatus.DEAD_LETTER,
        last_response_code=500,
        next_attempt_at=datetime.now(UTC),
    )
    app_session.add(dlq)
    await app_session.commit()

    cc = await control_center.build(app_session)
    assert cc.pending_approvals.count == 1
    assert cc.overdue_invoices.count == 1
    assert cc.overdue_invoices.amount_total == Decimal("100.00")
    assert cc.webhook_dlq.count == 1
    assert cc.webhook_dlq.sample[0]["event_type"] == "test.TestEvent"


@pytest.mark.asyncio
async def test_ws_health_reads_monitor_when_present(client, app_session: AsyncSession) -> None:
    """When the printer monitor is alive and has a fresh state, the
    Control Center should reflect ``connected=True`` with the
    monitor's most-recent ``last_seen_at``.
    """
    from datetime import UTC, datetime

    from app.services.printer_monitor import PrinterMonitor, PrinterState
    from app.services.printer_monitor import monitor as monitor_module

    fake = PrinterMonitor.__new__(PrinterMonitor)
    fake._states = {}  # type: ignore[attr-defined]
    now = datetime.now(UTC)
    pid = uuid.uuid4()
    fake._states[pid] = PrinterState(  # type: ignore[attr-defined]
        printer_id=pid, state="idle", last_seen_at=now
    )
    monitor_module._monitor = fake
    try:
        cc = await control_center.build(app_session)
        assert cc.ws_health.moonraker_ws_connected is True
        assert cc.ws_health.last_event_at is not None
    finally:
        monitor_module._monitor = None


@pytest.mark.asyncio
async def test_endpoint_role_matrix(client: AsyncClient, app_session: AsyncSession) -> None:
    sales_token = await token_for(Role.SALES, client, app_session)
    resp = await client.get(
        "/api/v1/control-center",
        headers={"Authorization": f"Bearer {sales_token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_endpoint_shape(client: AsyncClient, app_session: AsyncSession) -> None:
    token = await token_for(Role.OWNER, client, app_session)
    resp = await client.get(
        "/api/v1/control-center",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in (
        "as_of",
        "pending_approvals",
        "low_stock_alerts",
        "overdue_invoices",
        "overdue_bills",
        "failed_jobs",
        "webhook_dlq",
        "ws_health",
    ):
        assert key in body
    assert body["ws_health"]["moonraker_ws_connected"] is False
