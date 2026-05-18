"""Settlement-line dedup via partial-unique on external_txn_id (Phase 9.8, #160).

The unique index protects against the same external_txn_id appearing
twice within the same settlement. Re-importing the same file produces a
*new* settlement (each import is its own aggregate) — but a single
upload that contains duplicate rows must drop the second occurrence.
"""

from __future__ import annotations

import io

import pytest
from app.models.settlement import SettlementLine
from app.services import settlement_imports as service
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests._settlement_helpers import sample_etsy_csv_bytes, seed_settlement_stack, seed_user


@pytest.mark.asyncio
async def test_duplicate_external_txn_id_within_upload_is_skipped(
    client, app_session: AsyncSession
) -> None:
    _ = client
    stack = await seed_settlement_stack(app_session)
    user = await seed_user(app_session)

    # Two rows share the same TransactionID — the second should drop.
    rows = [
        {
            "Type": "Sale",
            "OrderID": "O-1",
            "TransactionID": "TX-DUP",
            "Title": "first",
            "Date": "2026-03-01",
            "Amount": "10.00",
        },
        {
            "Type": "Sale",
            "OrderID": "O-1",
            "TransactionID": "TX-DUP",
            "Title": "second (dup)",
            "Date": "2026-03-01",
            "Amount": "10.00",
        },
        {
            "Type": "Sale",
            "OrderID": "O-2",
            "TransactionID": "TX-UNIQUE",
            "Title": "ok",
            "Date": "2026-03-02",
            "Amount": "15.00",
        },
    ]
    csv_bytes = sample_etsy_csv_bytes(rows=rows)
    from datetime import date

    settlement = await service.import_file(
        session=app_session,
        channel_id=stack["channel_id"],
        file_bytes=csv_bytes,
        filename="dup.csv",
        format_kind="etsy",
        period_start=date(2026, 3, 1),
        period_end=date(2026, 3, 31),
        payout_account_id=stack["payout_account_id"],
        actor_user_id=user.id,
    )
    await app_session.commit()

    lines = list(
        (
            await app_session.execute(
                select(SettlementLine).where(SettlementLine.settlement_id == settlement.id)
            )
        )
        .scalars()
        .all()
    )
    # Only two unique TransactionIDs survive.
    assert len(lines) == 2
    txn_ids = {line.external_txn_id for line in lines}
    assert txn_ids == {"TX-DUP", "TX-UNIQUE"}


@pytest.mark.asyncio
async def test_parser_handles_csv_without_dupes() -> None:
    raw = sample_etsy_csv_bytes()
    rows = service.parse_etsy_csv(stream=io.StringIO(raw.decode("utf-8")))
    txn_ids = {r.external_txn_id for r in rows}
    # All five fixture rows have distinct TransactionIDs.
    assert len(txn_ids) == 5
