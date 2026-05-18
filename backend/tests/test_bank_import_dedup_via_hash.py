"""Re-importing the same file must dedupe via the canonical hash
(Phase 8.9, #136).

The first import inserts N rows. The second import (same file, same
mapping) inserts 0 rows and counts N duplicates.
"""

from __future__ import annotations

import pytest
from app.models.auth import Role
from app.models.bank import BankTransaction
from app.services import bank_imports as service
from app.services.auth import create_user
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._banking_helpers import sample_csv_signed_amount, seed_bank_account


@pytest.mark.asyncio
async def test_dedup_via_external_hash(client: AsyncClient, app_session: AsyncSession) -> None:
    session = app_session
    # Set up: a user (to satisfy created_by_user_id), a bank account, a CSV mapping.
    user = await create_user(
        session,
        email="bk@example.com",
        password="x",
        full_name="bk",
        role=Role.BOOKKEEPER,
        bcrypt_rounds=4,
    )
    await session.commit()
    acct = await seed_bank_account(session)

    mapping = await service.create_mapping(
        session,
        name="wells-signed",
        account_id=acct.id,
        file_kind="csv",
        column_map={
            "date": "Date",
            "description": "Description",
            "amount": "Amount",
            "balance": "Balance",
        },
        date_format="%Y-%m-%d",
        amount_sign="signed_amount",
        actor_user_id=user.id,
    )
    await session.commit()

    csv = sample_csv_signed_amount()

    run1 = await service.import_file(
        session,
        account_id=acct.id,
        filename="april.csv",
        file_bytes=csv,
        mapping_id=mapping.id,
        actor_user_id=user.id,
    )
    await session.commit()
    assert run1.row_count == 4
    assert run1.inserted_count == 4
    assert run1.duplicate_count == 0

    run2 = await service.import_file(
        session,
        account_id=acct.id,
        filename="april-again.csv",
        file_bytes=csv,
        mapping_id=mapping.id,
        actor_user_id=user.id,
    )
    await session.commit()
    assert run2.row_count == 4
    assert run2.inserted_count == 0
    assert run2.duplicate_count == 4

    # And only 4 rows in the table.
    rows = (
        (
            await session.execute(
                select(BankTransaction).where(BankTransaction.account_id == acct.id)
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 4
