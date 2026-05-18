"""Inter-account transfer service (Phase 8.11, #138).

A "transfer" is just the operator's mental model — under the hood it's a
single balanced journal entry posting:

    Dr  to_account    amount
    Cr  from_account  amount

There is no transfer aggregate. The JE itself is the record. The
``banking.InterAccountTransferPosted`` event carries the JE id plus the
two account ids and amount so reports can recover the transfer view
without joining JL twice.

Both accounts MUST be of ``type='asset'`` (you only "transfer" between
asset accounts — moving from a liability to an asset is just a payment
or a draw, which has its own service). The two account ids must differ.
The amount must be strictly positive.

Same-TX: this service NEVER commits. The caller (the endpoint layer)
owns the commit boundary.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import banking as banking_events
from app.models.account import Account
from app.models.journal_entry import JournalEntry
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service


class InterAccountTransfersServiceError(Exception):
    """Base. Routers map to 400 unless noted."""


class InvalidInterAccountTransferError(InterAccountTransfersServiceError):
    """Validation failure (same account, non-asset, non-positive amount, ...)."""


async def _load_asset_account(session: AsyncSession, account_id: uuid.UUID) -> Account:
    row = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if row is None:
        raise InvalidInterAccountTransferError(f"account {account_id} does not exist")
    # Account.type is stored as a string via the SAEnum; compare as str.
    if str(row.type) != "asset":
        raise InvalidInterAccountTransferError(
            f"account {account_id} must be type=asset (got {row.type!r})"
        )
    if row.is_archived:
        raise InvalidInterAccountTransferError(f"account {account_id} is archived")
    return row


async def post_transfer(
    *,
    session: AsyncSession,
    from_account_id: uuid.UUID,
    to_account_id: uuid.UUID,
    amount: Decimal,
    occurred_at: datetime,
    memo: str | None,
    actor_user_id: uuid.UUID,
) -> JournalEntry:
    """Validate and post a balanced inter-account transfer JE.

    Returns the persisted :class:`JournalEntry`. Same-TX — the caller
    must commit. Emits ``banking.InterAccountTransferPosted`` inside the
    same transaction.
    """
    if from_account_id == to_account_id:
        raise InvalidInterAccountTransferError("from_account_id and to_account_id must differ")
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))
    if amount <= Decimal("0"):
        raise InvalidInterAccountTransferError("amount must be > 0")

    await _load_asset_account(session, from_account_id)
    await _load_asset_account(session, to_account_id)

    description = (memo or "").strip() or f"Transfer {from_account_id} -> {to_account_id}"

    lines = [
        journal_service.JournalLineInput(
            account_id=to_account_id,
            debit=amount,
            credit=Decimal("0"),
            line_number=1,
            memo=memo,
        ),
        journal_service.JournalLineInput(
            account_id=from_account_id,
            debit=Decimal("0"),
            credit=amount,
            line_number=2,
            memo=memo,
        ),
    ]
    try:
        entry = await journal_service.post(
            journal_service.JournalEntryInput(
                description=description,
                posted_at=occurred_at,
                lines=lines,
            ),
            session=session,
            actor_user_id=actor_user_id,
            _internal_skip_approval_check=True,
        )
    except journal_service.JournalEntriesServiceError as exc:
        raise InvalidInterAccountTransferError(str(exc)) from exc

    if not isinstance(entry, JournalEntry):
        # With _internal_skip_approval_check=True the approval branch is
        # unreachable; surface as a service error if it ever fires.
        raise InvalidInterAccountTransferError("journal entry not posted")

    await event_store.append(
        EventCreate(
            type=banking_events.TYPE_INTER_ACCOUNT_TRANSFER_POSTED,
            aggregate_type=banking_events.AGGREGATE_TYPE_JOURNAL_ENTRY,
            aggregate_id=entry.id,
            payload={
                "journal_entry_id": str(entry.id),
                "from_account_id": str(from_account_id),
                "to_account_id": str(to_account_id),
                "amount": str(amount),
                "occurred_at": occurred_at.isoformat(),
                "memo": memo,
            },
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )

    return entry


__all__ = [
    "InterAccountTransfersServiceError",
    "InvalidInterAccountTransferError",
    "post_transfer",
]
