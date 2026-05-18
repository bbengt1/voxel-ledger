"""Shared helpers for settlement-imports tests (Phase 9.8, #160)."""

from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.account import Account
from app.models.accounting_period import AccountingPeriod, AccountingPeriodState
from app.models.auth import Role
from app.services import sales_channels as channels_service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}-settle@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_user(session: AsyncSession, *, email: str = "owner-settle@example.com"):
    user = await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name="Owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    return user


async def seed_settlement_stack(session: AsyncSession) -> dict[str, uuid.UUID]:
    """Seed an open period + payout (bank) account + a marketplace channel.

    Returns a dict with ``payout_account_id`` and ``channel_id``.
    """
    today = datetime.now(UTC).date()
    session.add(
        AccountingPeriod(
            id=uuid.uuid4(),
            name="settlement-test-period",
            start_date=today - timedelta(days=60),
            end_date=today + timedelta(days=30),
            state=AccountingPeriodState.OPEN.value,
        )
    )

    payout = Account(id=uuid.uuid4(), code="1015", name="Marketplace Clearing", type="asset")
    session.add(payout)
    await session.flush()

    channel = await channels_service.create(
        session,
        name="Etsy Test",
        slug="etsy-test",
        kind="marketplace",
        fee_model="percent",
        fee_percent=Decimal("0.065"),
        fee_flat=None,
        default_revenue_account_id=None,
        default_fee_account_id=None,
        actor_user_id=None,
    )
    await session.commit()
    return {"payout_account_id": payout.id, "channel_id": channel.id}


def sample_etsy_csv_bytes(rows: Iterable[dict[str, str]] | None = None) -> bytes:
    """Build a tiny Etsy-shaped CSV.

    Default schema is ``Type,OrderID,TransactionID,Title,Date,Amount`` to
    match the ``ETSY_COLUMN_MAP`` preset in
    ``app.services.settlement_imports``.
    """
    header = ["Type", "OrderID", "TransactionID", "Title", "Date", "Amount"]
    if rows is None:
        rows = [
            {
                "Type": "Sale",
                "OrderID": "ETSY-1001",
                "TransactionID": "TX-1001",
                "Title": "Tiny Voxel Print",
                "Date": "2026-03-15",
                "Amount": "20.00",
            },
            {
                "Type": "Fee",
                "OrderID": "ETSY-1001",
                "TransactionID": "TX-1001-FEE",
                "Title": "Listing fee",
                "Date": "2026-03-15",
                "Amount": "-1.30",
            },
            {
                "Type": "Refund",
                "OrderID": "ETSY-1002",
                "TransactionID": "TX-1002-RF",
                "Title": "Customer refund",
                "Date": "2026-03-18",
                "Amount": "-5.00",
            },
            {
                "Type": "Adjustment",
                "OrderID": "",
                "TransactionID": "TX-ADJ-001",
                "Title": "Promo credit",
                "Date": "2026-03-20",
                "Amount": "0.50",
            },
            {
                "Type": "Deposit",
                "OrderID": "",
                "TransactionID": "TX-DEPOSIT-001",
                "Title": "Bank payout",
                "Date": "2026-03-31",
                "Amount": "14.20",
            },
        ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")


def sample_generic_csv_bytes(rows: list[dict[str, str]], header: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8")
