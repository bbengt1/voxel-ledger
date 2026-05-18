"""Bank auto-matcher service (Phase 8.10, #137).

Walks all ``state=unmatched`` ``bank_transaction`` rows, finds the first
matching ``bank_match_rule`` in priority order, and applies the rule's
action atomically inside the supplied session.

Same-transaction invariant
--------------------------
``run_once`` never calls ``session.commit()``. The caller (the worker or
the operator-triggered API endpoint) commits at the end. Per-transaction
exceptions are caught and logged so a single bad rule never blocks the
rest.

Sign convention
---------------
``bank_transaction.amount`` is **signed**: positive = inflow (money
arriving into the bank-asset account → debit the bank-asset; credit the
other side). Negative = outflow → credit the bank-asset, debit the
other side. Magnitude is ``abs(amount)``.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import banking as banking_events
from app.models.bank import BankTransaction, BankTransactionState
from app.models.bank_match_rule import (
    BankMatchAction,
    BankMatchRule,
)
from app.models.journal_entry import JournalEntry
from app.models.journal_line import JournalLine
from app.schemas.events import EventCreate
from app.services import bank_match_rules as rules_service
from app.services import event_store
from app.services import journal_entries as journal_service

log = logging.getLogger(__name__)


_ZERO = Decimal("0")


@dataclass(frozen=True)
class AutoMatchResult:
    transaction_id: uuid.UUID
    rule_id: uuid.UUID | None
    action_kind: str
    journal_entry_id: uuid.UUID | None


def _render_memo(rule: BankMatchRule, tx: BankTransaction) -> str:
    if rule.description_template:
        try:
            return rule.description_template.format_map(
                {
                    "description": tx.description or "",
                    "amount": str(tx.amount),
                    "occurred_on": tx.occurred_on.isoformat(),
                }
            )
        except (KeyError, IndexError) as exc:
            log.warning(
                "bank_auto_matcher.template_render_failed",
                extra={"rule_id": str(rule.id), "error": str(exc)},
            )
    return f"Auto-matched: {tx.description}".strip()


def _posted_at_for(tx: BankTransaction) -> datetime:
    """Combine the transaction's ``occurred_on`` with UTC midnight."""
    return datetime.combine(tx.occurred_on, time(0, 0, 0), tzinfo=UTC)


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


async def _post_journal_for_match(
    *,
    session: AsyncSession,
    tx: BankTransaction,
    rule: BankMatchRule,
    actor_user_id: uuid.UUID | None,
) -> JournalEntry:
    """Build + post a balanced 2-line JE for a ``post_to_account`` match.

    Positive ``tx.amount`` → debit bank (asset goes up); negative → credit
    bank. The other side is rule.debit_account_id or rule.credit_account_id
    depending on which side the bank account ends up on.
    """
    magnitude = abs(tx.amount)
    memo = _render_memo(rule, tx)
    posted_at = _posted_at_for(tx)

    if tx.amount >= _ZERO:
        # inflow: debit bank, credit the rule's credit_account_id side.
        bank_line = journal_service.JournalLineInput(
            account_id=tx.account_id,
            debit=magnitude,
            credit=_ZERO,
            line_number=1,
            memo=memo,
        )
        other_line = journal_service.JournalLineInput(
            account_id=rule.credit_account_id,  # type: ignore[arg-type]
            debit=_ZERO,
            credit=magnitude,
            line_number=2,
            memo=memo,
        )
    else:
        # outflow: credit bank, debit the rule's debit_account_id side.
        bank_line = journal_service.JournalLineInput(
            account_id=tx.account_id,
            debit=_ZERO,
            credit=magnitude,
            line_number=1,
            memo=memo,
        )
        other_line = journal_service.JournalLineInput(
            account_id=rule.debit_account_id,  # type: ignore[arg-type]
            debit=magnitude,
            credit=_ZERO,
            line_number=2,
            memo=memo,
        )

    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=memo,
            posted_at=posted_at,
            lines=[bank_line, other_line],
        ),
        session=session,
        actor_user_id=actor_user_id or uuid.UUID(int=0),
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    return entry


async def _link_match(
    *,
    session: AsyncSession,
    tx: BankTransaction,
    entry: JournalEntry,
) -> uuid.UUID:
    """Find the JE's line whose ``account_id == tx.account_id`` and
    stamp ``tx.matched_journal_line_id``. Returns the linked line id."""
    line_row = (
        await session.execute(
            select(JournalLine).where(
                JournalLine.entry_id == entry.id,
                JournalLine.account_id == tx.account_id,
            )
        )
    ).scalar_one_or_none()
    if line_row is None:
        # Defensive — caller has constructed the JE such that this row
        # must exist. Surface clearly rather than silently mis-linking.
        raise RuntimeError(
            f"no journal line on entry {entry.id} references bank account {tx.account_id}"
        )
    tx.matched_journal_line_id = line_row.id
    tx.state = BankTransactionState.MATCHED
    return line_row.id


async def run_once(
    *,
    session: AsyncSession,
    now: datetime | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> list[AutoMatchResult]:
    """Walk all unmatched bank transactions and apply the first matching
    rule in priority order.

    Priority semantics
    ------------------
    * lower ``priority`` runs first
    * per-account rules (NOT NULL ``account_id``) win over global rules at
      the same priority
    * ``id`` is the final tiebreaker for determinism

    Per-tx exceptions are caught + logged so one bad rule doesn't block
    the rest. Never commits — the caller commits.
    """
    _ = now  # currently unused; kept for parity with worker entrypoints.
    rules = await rules_service.list_rules(session=session, include_inactive=False, limit=10_000)
    matchers_all = rules_service.compile_matchers(rules)

    # Bucket matchers by account_id (None == global) so we can slice
    # quickly per transaction.
    by_account: dict[uuid.UUID | None, list[rules_service.CompiledMatcher]] = {}
    for matcher in matchers_all:
        by_account.setdefault(matcher.rule.account_id, []).append(matcher)

    stmt = (
        select(BankTransaction)
        .where(BankTransaction.state == BankTransactionState.UNMATCHED)
        .order_by(BankTransaction.occurred_on.asc(), BankTransaction.id.asc())
    )
    rows: list[BankTransaction] = list((await session.execute(stmt)).scalars().all())

    results: list[AutoMatchResult] = []
    for tx in rows:
        try:
            # Per-account rules first, then global, in priority order.
            # ``list_rules`` already returned in (priority asc, per-account
            # before global) ordering, so iterate the combined list once.
            scoped = by_account.get(tx.account_id, []) + by_account.get(None, [])
            scoped.sort(
                key=lambda m: (
                    m.rule.priority,
                    0 if m.rule.account_id is not None else 1,
                    str(m.rule.id),
                )
            )

            picked = None
            for matcher in scoped:
                if matcher.matches(
                    description=tx.description,
                    memo=tx.memo,
                    amount=tx.amount,
                ):
                    picked = matcher
                    break

            if picked is None:
                continue

            rule = picked.rule
            if rule.action_kind == BankMatchAction.IGNORE:
                tx.state = BankTransactionState.IGNORED
                await _emit(
                    session,
                    event_type=banking_events.TYPE_BANK_TRANSACTION_IGNORED,
                    aggregate_type=banking_events.AGGREGATE_TYPE_BANK_TRANSACTION,
                    aggregate_id=tx.id,
                    payload={
                        "transaction_id": str(tx.id),
                        "rule_id": str(rule.id),
                    },
                    actor_user_id=actor_user_id,
                )
                results.append(
                    AutoMatchResult(
                        transaction_id=tx.id,
                        rule_id=rule.id,
                        action_kind=rule.action_kind.value,
                        journal_entry_id=None,
                    )
                )
                continue

            if rule.action_kind == BankMatchAction.FLAG_FOR_REVIEW:
                # State stays ``unmatched``; the event is the signal.
                await _emit(
                    session,
                    event_type=banking_events.TYPE_BANK_TRANSACTION_FLAGGED_FOR_REVIEW,
                    aggregate_type=banking_events.AGGREGATE_TYPE_BANK_TRANSACTION,
                    aggregate_id=tx.id,
                    payload={
                        "transaction_id": str(tx.id),
                        "rule_id": str(rule.id),
                    },
                    actor_user_id=actor_user_id,
                )
                results.append(
                    AutoMatchResult(
                        transaction_id=tx.id,
                        rule_id=rule.id,
                        action_kind=rule.action_kind.value,
                        journal_entry_id=None,
                    )
                )
                continue

            # action_kind == post_to_account
            entry = await _post_journal_for_match(
                session=session,
                tx=tx,
                rule=rule,
                actor_user_id=actor_user_id,
            )
            await _link_match(session=session, tx=tx, entry=entry)
            await _emit(
                session,
                event_type=banking_events.TYPE_BANK_TRANSACTION_AUTO_MATCHED,
                aggregate_type=banking_events.AGGREGATE_TYPE_BANK_TRANSACTION,
                aggregate_id=tx.id,
                payload={
                    "transaction_id": str(tx.id),
                    "rule_id": str(rule.id),
                    "journal_entry_id": str(entry.id),
                    "amount": str(tx.amount),
                },
                actor_user_id=actor_user_id,
            )
            results.append(
                AutoMatchResult(
                    transaction_id=tx.id,
                    rule_id=rule.id,
                    action_kind=rule.action_kind.value,
                    journal_entry_id=entry.id,
                )
            )
        except Exception as exc:  # pragma: no cover - defensive log path
            log.exception(
                "bank_auto_matcher.tx_failed",
                extra={"transaction_id": str(tx.id), "error": str(exc)},
            )
            continue

    await session.flush()
    return results


__all__ = [
    "AutoMatchResult",
    "run_once",
]
