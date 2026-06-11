"""Cutover opening-balance seed → QBO (#318, epic #312, Phase 5b).

Phase 5 makes QBO the sole ledger. Rather than replaying years of local
transactions (costly, error-prone — phase-0 findings §11), QBO is seeded with a
single **cutover JournalEntry**: one line per local account with a non-zero
balance as of the cutover date, so QBO's balance sheet starts correct.

The lines hit arbitrary chart-of-accounts accounts, so — like inter-account
transfers and the bank auto-matcher — they resolve through the **local-account
map** at drain time (``builders.build_journal_entry_local``, kind
``opening_balance``). :func:`build_preview` is the operator's dry-run: it shows
every line, flags unmapped accounts, and checks the debit/credit totals;
:func:`enqueue_opening_balance` refuses to enqueue until the preview is clean
(complete map, balanced books, no prior seed pending/synced).

The synced outbox row (kind ``opening_balance``) doubles as the Phase-5c gate's
"opening balances are in QBO" evidence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.quickbooks import local_account_map
from app.services.quickbooks import outbox as qbo_outbox
from app.services.reports import trial_balance

_ZERO = Decimal("0")

# Account types whose normal balance is a debit; the rest are credit-normal.
# (Mirrors the trial-balance sign convention.)
_DR_NORMAL: frozenset[str] = frozenset({"asset", "expense"})

KIND = "opening_balance"


class OpeningBalanceError(RuntimeError):
    """Base. Routers map to 400/409."""


class UnmappedAccountsError(OpeningBalanceError):
    """Accounts with non-zero balances lack a local-account→QBO mapping."""

    def __init__(self, codes: list[str]) -> None:
        self.codes = codes
        super().__init__(
            "opening-balance seed blocked: no QBO account mapped for local "
            f"account(s) {', '.join(codes)}; set them in the QuickBooks admin "
            "panel (local-account-map) first"
        )


class UnbalancedLedgerError(OpeningBalanceError):
    """The trial balance doesn't balance — must be investigated before cutover."""


class AlreadySeededError(OpeningBalanceError):
    """An opening-balance JE is already pending or synced."""


@dataclass(frozen=True)
class OpeningBalanceLine:
    account_id: uuid.UUID
    code: str
    name: str
    type: str
    balance: Decimal  # signed, per the account type's normal balance
    posting: str  # "debit" | "credit"
    amount: Decimal  # abs(balance)
    qbo_account_id: str | None  # None == unmapped


@dataclass(frozen=True)
class OpeningBalancePreview:
    cutover_date: date
    lines: list[OpeningBalanceLine]
    total_debits: Decimal
    total_credits: Decimal
    balanced: bool
    unmapped_codes: list[str]
    existing_status: str | None  # latest opening_balance outbox row status, if any


def _posting_for(account_type: str, balance: Decimal) -> str:
    if account_type in _DR_NORMAL:
        return "debit" if balance >= _ZERO else "credit"
    return "credit" if balance >= _ZERO else "debit"


async def _latest_row(session: AsyncSession) -> QboSyncOutbox | None:
    return (
        (
            await session.execute(
                select(QboSyncOutbox)
                .where(QboSyncOutbox.kind == KIND)
                .order_by(QboSyncOutbox.created_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )


async def build_preview(session: AsyncSession, *, cutover_date: date) -> OpeningBalancePreview:
    """Compute the cutover JE lines without enqueuing anything."""
    report = await trial_balance.build(
        session, date_from=date(1970, 1, 1), date_to=cutover_date, include_zero=False
    )
    mapped = await local_account_map.get_map(session)

    lines: list[OpeningBalanceLine] = []
    total_dr = _ZERO
    total_cr = _ZERO
    unmapped: list[str] = []
    for row in report.rows:
        if row.closing_balance == _ZERO:
            continue
        posting = _posting_for(row.type, row.closing_balance)
        amount = abs(row.closing_balance)
        qbo_id = (mapped.get(row.account_id) or {}).get("qbo_account_id")
        if qbo_id is None:
            unmapped.append(row.code)
        if posting == "debit":
            total_dr += amount
        else:
            total_cr += amount
        lines.append(
            OpeningBalanceLine(
                account_id=uuid.UUID(row.account_id),
                code=row.code,
                name=row.name,
                type=row.type,
                balance=row.closing_balance,
                posting=posting,
                amount=amount,
                qbo_account_id=qbo_id,
            )
        )

    existing = await _latest_row(session)
    return OpeningBalancePreview(
        cutover_date=cutover_date,
        lines=lines,
        total_debits=total_dr,
        total_credits=total_cr,
        balanced=total_dr == total_cr,
        unmapped_codes=unmapped,
        existing_status=existing.status if existing is not None else None,
    )


async def enqueue_opening_balance(
    session: AsyncSession,
    *,
    cutover_date: date,
    actor_user_id: uuid.UUID | None,
) -> QboSyncOutbox:
    """Validate the preview and enqueue the cutover JE. Caller commits.

    Refuses when: an opening-balance row is already pending/synced; any
    non-zero account is unmapped; the books don't balance; there is nothing
    to seed."""
    existing = await _latest_row(session)
    if existing is not None and existing.status in (
        QboSyncStatus.PENDING.value,
        QboSyncStatus.SYNCED.value,
    ):
        raise AlreadySeededError(
            f"an opening-balance JE already exists with status {existing.status!r}; "
            "void it in QBO and mark the outbox row failed before re-seeding"
        )

    preview = await build_preview(session, cutover_date=cutover_date)
    if not preview.lines:
        raise OpeningBalanceError("nothing to seed: every account balance is zero")
    if preview.unmapped_codes:
        raise UnmappedAccountsError(preview.unmapped_codes)
    if not preview.balanced:
        raise UnbalancedLedgerError(
            f"trial balance does not balance as of {cutover_date.isoformat()} "
            f"(Dr {preview.total_debits} != Cr {preview.total_credits}); "
            "investigate before cutover"
        )

    return await qbo_outbox.enqueue(
        session,
        kind=KIND,
        local_id=uuid.uuid4(),
        payload={
            "lines": [
                {
                    "local_account_id": str(line.account_id),
                    "posting": line.posting,
                    "amount": str(line.amount),
                    "description": f"{line.code} {line.name}",
                }
                for line in preview.lines
            ],
            "doc_number": f"OB-{cutover_date.isoformat()}",
            "txn_date": cutover_date.isoformat(),
            "private_note": (
                f"Opening balances as of {cutover_date.isoformat()} (local-GL cutover, #318)"
            ),
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
        },
        op="post",
    )


async def seed_status(session: AsyncSession) -> QboSyncOutbox | None:
    """Latest opening-balance outbox row — the Phase-5c gate's evidence."""
    return await _latest_row(session)
