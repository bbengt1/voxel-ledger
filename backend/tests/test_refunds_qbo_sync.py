"""Refund QBO sync — Phase 3f (#316, epic #312).

When ``quickbooks.enabled``, a posted refund enqueues a role-tagged reversing
JournalEntry (Dr revenue/sales_tax, Cr bank, plus Dr inventory / Cr cogs for
restock) instead of posting the local GL — closing the refund hole and making
refunds visible to the reconciliation gate.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from app.models.oauth_credential import OAuthCredential, OAuthProvider
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.models.refund import RefundState
from app.services import refunds as refunds_service
from app.services.quickbooks import reconcile
from app.services.settings.service import SettingsService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._refunds_helpers import create_confirmed_sale, seed_product_with_stock
from tests._sales_helpers import seed_channel, seed_posting_defaults, seed_user


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


def _lines(payload: dict) -> dict[str, tuple[str, str]]:
    """role -> (posting, amount)."""
    return {ln["role"]: (ln["posting"], ln["amount"]) for ln in payload["lines"]}


@pytest.mark.asyncio
async def test_posted_refund_enqueues_role_je(app_session: AsyncSession) -> None:
    await _enable_qbo(app_session)
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await seed_product_with_stock(app_session, qty="10", unit_cost="3.00")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="4",
        unit_price="10.00",
    )
    sale_item = sale.items[0]

    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="full",
        reason_code="damaged",
        notes=None,
        restock_inventory=True,
        items=[{"sale_item_id": str(sale_item.id), "quantity": "4", "unit_amount": "10.00"}],
        actor_user_id=user.id,
    )
    await app_session.commit()
    assert result.refund.state == RefundState.APPROVED

    await refunds_service.post(result.refund.id, session=app_session, actor_user_id=user.id)
    await app_session.commit()

    refund = await refunds_service.get(result.refund.id, session=app_session)
    assert refund.state == RefundState.POSTED
    # QBO replace-mode: no local GL entry.
    assert refund.posting_journal_entry_id is None

    rows = (
        (await app_session.execute(select(QboSyncOutbox).where(QboSyncOutbox.kind == "refund")))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    lines = _lines(rows[0].payload)
    # 4 units @ $10 = $40 revenue reversed, no tax; cash refunded $40.
    assert lines["revenue"] == ("debit", "40.000000")
    assert lines["bank"] == ("credit", "40.000000")
    # Restock 4 @ $3 cost = $12 inventory back, cogs reversed.
    assert lines["inventory"] == ("debit", "12.000000")
    assert lines["cogs"] == ("credit", "12.000000")
    # Balanced: debits (40 + 12) == credits (40 + 12).
    debits = sum(float(a) for p, a in lines.values() if p == "debit")
    credits = sum(float(a) for p, a in lines.values() if p == "credit")
    assert debits == credits


@pytest.mark.asyncio
async def test_posted_refund_is_reconciliation_gap_until_synced(
    app_session: AsyncSession,
) -> None:
    await _enable_qbo(app_session)
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )
    product, _ = await seed_product_with_stock(app_session, qty="10", unit_cost="3.00")
    sale = await create_confirmed_sale(
        app_session,
        channel=channel,
        user=user,
        product=product,
        quantity="2",
        unit_price="10.00",
    )
    result = await refunds_service.create(
        session=app_session,
        sale_id=sale.id,
        kind="full",
        reason_code="damaged",
        notes=None,
        restock_inventory=False,
        items=[{"sale_item_id": str(sale.items[0].id), "quantity": "2", "unit_amount": "10.00"}],
        actor_user_id=user.id,
    )
    await app_session.commit()
    await refunds_service.post(result.refund.id, session=app_session, actor_user_id=user.id)
    await app_session.commit()

    today = datetime.now(UTC).date()
    report = await reconcile.build(app_session, date_from=today, date_to=today)
    # The posted refund's enqueued row is still pending (worker hasn't run),
    # so it surfaces as a gap (no *synced* row yet).
    assert any(g.kind == "refund" for g in report.gaps)
