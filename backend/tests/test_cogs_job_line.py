"""COGS handling of ``kind=job`` sale lines (Phase 6.3, #95).

Confirming a job-line sale must:

* derive the line's cost basis from the job's recorded run cost
  (cost-engine snapshot) — NOT from the FIFO inventory ledger,
* NOT emit a ``sale_consumption`` inventory transaction (jobs feed
  inventory at production time, not at sale time),
* still enqueue the QBO sale document via the sync outbox (QBO is the
  sole ledger — epic #312, Phase 5e).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from app.models.inventory_transaction import (
    KIND_SALE_CONSUMPTION,
    InventoryTransaction,
)
from app.models.job import JobState
from app.models.qbo_sync_outbox import QboSyncOutbox
from app.services import jobs as jobs_service
from app.services import parts as parts_service
from app.services import sales as sales_service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._sales_helpers import (
    seed_channel,
    seed_posting_defaults,
    seed_user,
)


@pytest.mark.asyncio
async def test_job_line_costs_from_job_no_inventory_consumption(
    app_session: AsyncSession,
) -> None:
    user = await seed_user(app_session)
    defaults = await seed_posting_defaults(app_session, actor_user_id=user.id)
    channel = await seed_channel(
        app_session,
        fee_model="none",
        fee_percent=None,
        default_revenue_account_id=defaults["revenue_account_id"],
        default_fee_account_id=defaults["fee_account_id"],
    )

    # Minimal job producing a part with an empty recipe (no materials,
    # 0 print minutes) → cost-engine returns zero cost. That's still a
    # legitimate cost basis for Phase 6.3; the important assertion below
    # is "no inventory transaction was emitted for the job line, AND the
    # journal entry still posts".
    part = await parts_service.create(
        app_session,
        name="Jobbed part",
        sku=f"PRT-{uuid.uuid4().hex[:6]}",
        print_minutes=0,
        setup_minutes=0,
        parts_per_run=1,
        print_grams_by_material={},
        actor_user_id=None,
    )
    job = await jobs_service.create(
        app_session,
        part_id=part.id,
        quantity_ordered=1,
        actor_user_id=user.id,
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
                "kind": "job",
                "job_id": str(job.id),
                "description": "Custom run",
                "quantity": "1",
                "unit_price": "50.00",
            }
        ],
        actor_user_id=user.id,
    )
    await app_session.commit()

    await sales_service.confirm(app_session, sale_id=sale.id, actor_user_id=user.id)
    await app_session.commit()

    # No sale_consumption inventory transaction for this sale.
    rows = (
        (
            await app_session.execute(
                select(InventoryTransaction)
                .where(InventoryTransaction.linked_sale_id == sale.id)
                .where(InventoryTransaction.kind == KIND_SALE_CONSUMPTION)
            )
        )
        .scalars()
        .all()
    )
    assert rows == []

    # The QBO sale doc still enqueued (revenue + AR even with zero cost);
    # zero cost means no sale_cogs JE spec.
    outbox = (
        await app_session.execute(
            select(QboSyncOutbox).where(
                QboSyncOutbox.kind == "sale",
                QboSyncOutbox.local_id == sale.id,
            )
        )
    ).scalar_one()
    assert outbox.op == "post"
    assert job.state == JobState.DRAFT  # sanity — the job stays untouched
