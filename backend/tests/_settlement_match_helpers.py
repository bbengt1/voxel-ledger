"""Helpers for the Phase 9.9 settlement matcher + post tests (#161).

These tests bypass the CSV import path and seed
``Settlement`` + ``SettlementLine`` rows directly so each scenario has
precise control over line.amount / occurred_on / external_order_id.
The matcher service is exercised against the seeded rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models.account import Account
from app.models.sale import Sale, SaleItem, SaleItemKind, SaleState
from app.models.sales_channel import SalesChannel
from app.models.settlement import (
    Settlement,
    SettlementLine,
    SettlementLineKind,
    SettlementLineState,
    SettlementState,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def seed_clearing_account(
    session: AsyncSession,
    *,
    channel: SalesChannel,
    code: str = "1200",
    name: str = "Marketplace Clearing",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type="asset")
    session.add(acct)
    await session.flush()
    channel.default_clearing_account_id = acct.id
    await session.flush()
    await session.commit()
    return acct


async def seed_fee_account(
    session: AsyncSession,
    *,
    channel: SalesChannel,
    code: str = "5300",
    name: str = "Channel Fees",
) -> Account:
    acct = Account(id=uuid.uuid4(), code=code, name=name, type="expense")
    session.add(acct)
    await session.flush()
    channel.default_fee_account_id = acct.id
    await session.flush()
    await session.commit()
    return acct


async def seed_sale(
    session: AsyncSession,
    *,
    channel_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    external_order_id: str | None,
    total_amount: Decimal | str = "20.00",
    occurred_at: datetime | None = None,
) -> Sale:
    """Insert a minimal ``Sale`` row directly. Phase 9.9 tests only need
    ``channel_id`` + ``external_order_id`` + ``total_amount`` +
    ``created_at`` for matching; the rest is plumbing.
    """
    amount = Decimal(str(total_amount))
    occurred = occurred_at or datetime.now(UTC)
    sale_id = uuid.uuid4()
    sale = Sale(
        id=sale_id,
        sale_number=f"SALE-TEST-{sale_id.hex[:8]}",
        channel_id=channel_id,
        external_order_id=external_order_id,
        customer_name="Test Customer",
        occurred_at=occurred,
        subtotal=amount,
        discount_amount=Decimal("0"),
        shipping_amount=Decimal("0"),
        tax_amount=Decimal("0"),
        channel_fee_amount=Decimal("0"),
        total_amount=amount,
        state=SaleState.CONFIRMED,
        created_by_user_id=actor_user_id,
        created_at=occurred,
        updated_at=occurred,
    )
    session.add(sale)
    await session.flush()
    item = SaleItem(
        id=uuid.uuid4(),
        sale_id=sale.id,
        line_number=1,
        kind=SaleItemKind.MANUAL,
        description="Test item",
        quantity=Decimal("1"),
        unit_price=amount,
        extended_amount=amount,
    )
    session.add(item)
    await session.flush()
    await session.commit()
    return sale


async def seed_settlement_with_lines(
    session: AsyncSession,
    *,
    channel: SalesChannel,
    payout_account_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    lines: list[dict],
    period_end: date | None = None,
) -> tuple[Settlement, list[SettlementLine]]:
    """Insert a Settlement + the supplied SettlementLine rows directly.

    Each ``lines`` entry is a dict with keys: ``line_kind``,
    ``amount``, ``external_order_id`` (optional), ``occurred_on``
    (optional, defaults to today).
    """
    today = datetime.now(UTC).date()
    pe = period_end or today
    ps = pe - timedelta(days=30)

    # Aggregate totals as the import service would.
    gross = Decimal("0")
    fees = Decimal("0")
    refunds = Decimal("0")
    adjustments = Decimal("0")
    for spec in lines:
        amt = Decimal(str(spec["amount"]))
        kind = spec["line_kind"]
        if kind == "sale" and amt > 0:
            gross += amt
        elif kind == "fee":
            fees += amt
        elif kind == "refund":
            refunds += amt
        elif kind == "adjustment":
            adjustments += amt
    payout = gross - abs(fees) - abs(refunds) + adjustments

    settlement = Settlement(
        id=uuid.uuid4(),
        settlement_number=f"SETT-TEST-{uuid.uuid4().hex[:6]}",
        channel_id=channel.id,
        period_start=ps,
        period_end=pe,
        gross_amount=gross,
        fee_amount=abs(fees),
        refund_amount=abs(refunds),
        adjustment_amount=adjustments,
        payout_amount=payout,
        payout_account_id=payout_account_id,
        filename="seed.csv",
        imported_by_user_id=actor_user_id,
        state=SettlementState.IMPORTED,
    )
    session.add(settlement)
    await session.flush()

    line_rows: list[SettlementLine] = []
    for i, spec in enumerate(lines, start=1):
        occurred_on = spec.get("occurred_on") or today
        line = SettlementLine(
            id=uuid.uuid4(),
            settlement_id=settlement.id,
            line_number=i,
            line_kind=SettlementLineKind(spec["line_kind"]),
            occurred_on=occurred_on,
            description=spec.get("description", ""),
            external_order_id=spec.get("external_order_id"),
            external_txn_id=spec.get("external_txn_id"),
            amount=Decimal(str(spec["amount"])),
            state=SettlementLineState.UNMATCHED,
        )
        session.add(line)
        line_rows.append(line)
    await session.flush()
    await session.commit()
    return settlement, line_rows
