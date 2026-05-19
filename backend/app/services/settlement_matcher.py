"""Settlement matcher + payout JE service (Phase 9.9, #161).

Two responsibilities split across this module:

1. **Auto-match** + manual match/unmatch/ignore of ``settlement_line``
   rows against in-app ``sale`` / ``refund`` rows.
2. **Post** the settlement once every non-ignored line is matched:
   atomically writes a balanced JE that nets out the marketplace
   clearing balance, flips ``settlement.state`` to ``posted``, and
   stamps ``posting_journal_entry_id``.

Refunds: we follow the **"trust the existing refund JE"** approach.
Refunds posted by the in-app Refund flow already Cr the marketplace
clearing account when they happened. The settlement payout JE
therefore does NOT re-debit refund lines; it only Cr's the residual
clearing balance which equals ``gross - refund_amount`` (and that
matches what the marketplace actually netted before fees).

JE shape
--------
The payout JE for one settlement::

    Dr settlement.payout_account_id      payout_amount
    Dr sales_channel.default_fee_account_id   fee_amount     (only if > 0)
    [Dr settlements.default_adjustment_account_id  -adjustment]
        or
    [Cr settlements.default_adjustment_account_id  +adjustment]
    Cr sales_channel.default_clearing_account_id   gross - refund_amount

The Cr clearing total balances the entry; you can verify by
substituting:

    Dr_sum  = payout + fee + max(-adj, 0)
            = (gross - fee - refund + adj) + fee + max(-adj, 0)
    Cr_sum  = (gross - refund) + max(adj, 0)

For positive adj: Dr_sum = gross - refund + adj; Cr_sum = gross - refund + adj. OK
For negative adj: Dr_sum = gross - refund + adj + (-adj) = gross - refund;
Cr_sum = gross - refund. OK
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import settlements as settlements_events
from app.models.journal_entry import JournalEntry
from app.models.refund import Refund
from app.models.sale import Sale
from app.models.sales_channel import SalesChannel
from app.models.settlement import (
    Settlement,
    SettlementLine,
    SettlementLineKind,
    SettlementLineState,
    SettlementState,
)
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import journal_entries as journal_service
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SettlementMatcherError(Exception):
    """Base. Routers map to 400 unless noted."""


class SettlementNotFoundError(SettlementMatcherError):
    """Mapped to 404."""


class SettlementLineNotFoundError(SettlementMatcherError):
    """Mapped to 404."""


class InvalidSettlementStateError(SettlementMatcherError):
    """Wrong state for the requested transition (e.g. posting twice)."""


class IncompleteMatchError(SettlementMatcherError):
    """``post`` requires every non-ignored line to be matched."""


class MissingSettlementAccountError(SettlementMatcherError):
    """A required account is unconfigured on the channel or settings."""


class InvalidMatchTargetError(SettlementMatcherError):
    """The supplied ``sale_id`` / ``refund_id`` is missing / mismatched."""


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")
_FUZZY_AMOUNT_TOLERANCE = Decimal("0.50")
_FUZZY_DATE_DAYS = 3


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Event helper
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=settlements_events.AGGREGATE_TYPE_SETTLEMENT,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


async def _load_settlement(session: AsyncSession, settlement_id: uuid.UUID) -> Settlement:
    row = (
        await session.execute(select(Settlement).where(Settlement.id == settlement_id))
    ).scalar_one_or_none()
    if row is None:
        raise SettlementNotFoundError(str(settlement_id))
    return row


async def _load_line(session: AsyncSession, line_id: uuid.UUID) -> SettlementLine:
    row = (
        await session.execute(select(SettlementLine).where(SettlementLine.id == line_id))
    ).scalar_one_or_none()
    if row is None:
        raise SettlementLineNotFoundError(str(line_id))
    return row


# ---------------------------------------------------------------------------
# Auto-match
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatchResult:
    line_id: uuid.UUID
    matched: bool
    matched_sale_id: uuid.UUID | None = None
    matched_refund_id: uuid.UUID | None = None
    strategy: str | None = None


async def _find_sale_match(
    session: AsyncSession, *, line: SettlementLine, channel_id: uuid.UUID
) -> tuple[Sale | None, str | None]:
    """Resolve a sale line to a Sale row.

    Order: exact ``external_order_id`` → fuzzy on (channel_id, |amount
    diff| <= $0.50, created_at within ±3 days of ``occurred_on``).
    """
    if line.external_order_id:
        sale = (
            await session.execute(
                select(Sale).where(
                    Sale.channel_id == channel_id,
                    Sale.external_order_id == line.external_order_id,
                )
            )
        ).scalar_one_or_none()
        if sale is not None:
            return sale, "external_order_id"

    target_amount = _q(line.amount)
    low = target_amount - _FUZZY_AMOUNT_TOLERANCE
    high = target_amount + _FUZZY_AMOUNT_TOLERANCE
    day_start = datetime.combine(
        line.occurred_on - timedelta(days=_FUZZY_DATE_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    day_end = datetime.combine(
        line.occurred_on + timedelta(days=_FUZZY_DATE_DAYS),
        datetime.max.time(),
        tzinfo=UTC,
    )
    candidates = list(
        (
            await session.execute(
                select(Sale)
                .where(Sale.channel_id == channel_id)
                .where(Sale.total_amount >= low)
                .where(Sale.total_amount <= high)
                .where(Sale.created_at >= day_start)
                .where(Sale.created_at <= day_end)
            )
        )
        .scalars()
        .all()
    )
    # Take the single best candidate iff exactly one. Ambiguous matches
    # stay unmatched — the operator picks manually.
    if len(candidates) == 1:
        return candidates[0], "fuzzy_amount_date"
    return None, None


async def _find_refund_match(
    session: AsyncSession, *, line: SettlementLine, channel_id: uuid.UUID
) -> tuple[Refund | None, str | None]:
    if line.external_order_id:
        # join refund -> sale by sale.external_order_id
        stmt = (
            select(Refund)
            .join(Sale, Sale.id == Refund.sale_id)
            .where(Sale.channel_id == channel_id)
            .where(Sale.external_order_id == line.external_order_id)
        )
        refund = (await session.execute(stmt)).scalar_one_or_none()
        if refund is not None:
            return refund, "external_order_id"

    # Fuzzy on |amount| (refund line.amount may be negative).
    target_amount = abs(_q(line.amount))
    low = target_amount - _FUZZY_AMOUNT_TOLERANCE
    high = target_amount + _FUZZY_AMOUNT_TOLERANCE
    day_start = datetime.combine(
        line.occurred_on - timedelta(days=_FUZZY_DATE_DAYS),
        datetime.min.time(),
        tzinfo=UTC,
    )
    day_end = datetime.combine(
        line.occurred_on + timedelta(days=_FUZZY_DATE_DAYS),
        datetime.max.time(),
        tzinfo=UTC,
    )
    stmt = (
        select(Refund)
        .join(Sale, Sale.id == Refund.sale_id)
        .where(Sale.channel_id == channel_id)
        .where(Refund.total_amount >= low)
        .where(Refund.total_amount <= high)
        .where(Refund.created_at >= day_start)
        .where(Refund.created_at <= day_end)
    )
    candidates = list((await session.execute(stmt)).scalars().all())
    if len(candidates) == 1:
        return candidates[0], "fuzzy_amount_date"
    return None, None


async def run_match(
    *,
    session: AsyncSession,
    settlement_id: uuid.UUID,
    dry_run: bool = False,
    actor_user_id: uuid.UUID | None = None,
) -> list[MatchResult]:
    """Sweep every ``unmatched`` line on the settlement.

    Sale + refund lines are matched against in-app rows; fee /
    adjustment / payout / tax lines are left untouched (they post to
    fixed accounts in :func:`post`). Returns one :class:`MatchResult`
    per line considered.
    """
    settlement = await _load_settlement(session, settlement_id)
    if settlement.state == SettlementState.POSTED:
        raise InvalidSettlementStateError(
            f"settlement {settlement.settlement_number} is already posted"
        )

    lines = list(
        (
            await session.execute(
                select(SettlementLine)
                .where(SettlementLine.settlement_id == settlement_id)
                .where(SettlementLine.state == SettlementLineState.UNMATCHED)
                .order_by(SettlementLine.line_number)
            )
        )
        .scalars()
        .all()
    )

    results: list[MatchResult] = []
    matched_count = 0
    for line in lines:
        if line.line_kind == SettlementLineKind.SALE:
            sale, strategy = await _find_sale_match(
                session, line=line, channel_id=settlement.channel_id
            )
            if sale is not None:
                results.append(
                    MatchResult(
                        line_id=line.id,
                        matched=True,
                        matched_sale_id=sale.id,
                        strategy=strategy,
                    )
                )
                if not dry_run:
                    line.matched_sale_id = sale.id
                    line.state = SettlementLineState.MATCHED
                    matched_count += 1
                    await _emit(
                        session,
                        event_type=settlements_events.TYPE_SETTLEMENT_LINE_MATCHED,
                        aggregate_id=settlement.id,
                        payload={
                            "settlement_id": str(settlement.id),
                            "line_id": str(line.id),
                            "line_kind": line.line_kind.value,
                            "matched_sale_id": str(sale.id),
                            "matched_refund_id": None,
                            "match_strategy": strategy or "exact",
                        },
                        actor_user_id=actor_user_id,
                    )
                continue
        elif line.line_kind == SettlementLineKind.REFUND:
            refund, strategy = await _find_refund_match(
                session, line=line, channel_id=settlement.channel_id
            )
            if refund is not None:
                results.append(
                    MatchResult(
                        line_id=line.id,
                        matched=True,
                        matched_refund_id=refund.id,
                        strategy=strategy,
                    )
                )
                if not dry_run:
                    line.matched_refund_id = refund.id
                    line.state = SettlementLineState.MATCHED
                    matched_count += 1
                    await _emit(
                        session,
                        event_type=settlements_events.TYPE_SETTLEMENT_LINE_MATCHED,
                        aggregate_id=settlement.id,
                        payload={
                            "settlement_id": str(settlement.id),
                            "line_id": str(line.id),
                            "line_kind": line.line_kind.value,
                            "matched_sale_id": None,
                            "matched_refund_id": str(refund.id),
                            "match_strategy": strategy or "exact",
                        },
                        actor_user_id=actor_user_id,
                    )
                continue
        # fee / adjustment / payout / tax: not auto-matchable.
        results.append(MatchResult(line_id=line.id, matched=False))

    if not dry_run:
        await session.flush()
        # Flip settlement state to ``matched`` if every non-ignored line is matched.
        remaining = list(
            (
                await session.execute(
                    select(SettlementLine).where(SettlementLine.settlement_id == settlement_id)
                )
            )
            .scalars()
            .all()
        )
        matchable_kinds = {SettlementLineKind.SALE, SettlementLineKind.REFUND}
        unmatched_relevant = [
            r
            for r in remaining
            if r.line_kind in matchable_kinds and r.state == SettlementLineState.UNMATCHED
        ]
        if not unmatched_relevant and settlement.state == SettlementState.IMPORTED:
            settlement.state = SettlementState.MATCHED
            await session.flush()
        await _emit(
            session,
            event_type=settlements_events.TYPE_SETTLEMENT_MATCHED,
            aggregate_id=settlement.id,
            payload={
                "settlement_id": str(settlement.id),
                "settlement_number": settlement.settlement_number,
                "matched_count": matched_count,
                "unmatched_count": sum(
                    1 for r in remaining if r.state == SettlementLineState.UNMATCHED
                ),
                "ignored_count": sum(
                    1 for r in remaining if r.state == SettlementLineState.IGNORED
                ),
            },
            actor_user_id=actor_user_id,
        )
    return results


# ---------------------------------------------------------------------------
# Manual match / unmatch / ignore
# ---------------------------------------------------------------------------


async def manual_match(
    *,
    session: AsyncSession,
    settlement_id: uuid.UUID,
    line_id: uuid.UUID,
    sale_id: uuid.UUID | None = None,
    refund_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> SettlementLine:
    if sale_id is None and refund_id is None:
        raise InvalidMatchTargetError("supply one of sale_id or refund_id")
    if sale_id is not None and refund_id is not None:
        raise InvalidMatchTargetError("only one of sale_id or refund_id may be set")

    settlement = await _load_settlement(session, settlement_id)
    if settlement.state == SettlementState.POSTED:
        raise InvalidSettlementStateError(
            f"settlement {settlement.settlement_number} is already posted"
        )
    line = await _load_line(session, line_id)
    if line.settlement_id != settlement_id:
        raise SettlementLineNotFoundError("line does not belong to this settlement")

    if sale_id is not None:
        sale = (await session.execute(select(Sale).where(Sale.id == sale_id))).scalar_one_or_none()
        if sale is None:
            raise InvalidMatchTargetError(f"sale not found: {sale_id}")
        if sale.channel_id != settlement.channel_id:
            raise InvalidMatchTargetError(
                f"sale {sale_id} belongs to a different channel than the settlement"
            )
        line.matched_sale_id = sale_id
        line.matched_refund_id = None
    else:
        refund = (
            await session.execute(select(Refund).where(Refund.id == refund_id))
        ).scalar_one_or_none()
        if refund is None:
            raise InvalidMatchTargetError(f"refund not found: {refund_id}")
        line.matched_sale_id = None
        line.matched_refund_id = refund_id

    line.state = SettlementLineState.MATCHED
    await session.flush()
    await _emit(
        session,
        event_type=settlements_events.TYPE_SETTLEMENT_LINE_MATCHED,
        aggregate_id=settlement.id,
        payload={
            "settlement_id": str(settlement.id),
            "line_id": str(line.id),
            "line_kind": line.line_kind.value,
            "matched_sale_id": str(line.matched_sale_id) if line.matched_sale_id else None,
            "matched_refund_id": str(line.matched_refund_id) if line.matched_refund_id else None,
            "match_strategy": "manual",
        },
        actor_user_id=actor_user_id,
    )
    return line


async def manual_unmatch(
    *,
    session: AsyncSession,
    settlement_id: uuid.UUID,
    line_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> SettlementLine:
    settlement = await _load_settlement(session, settlement_id)
    if settlement.state == SettlementState.POSTED:
        raise InvalidSettlementStateError(
            f"settlement {settlement.settlement_number} is already posted"
        )
    line = await _load_line(session, line_id)
    if line.settlement_id != settlement_id:
        raise SettlementLineNotFoundError("line does not belong to this settlement")
    line.matched_sale_id = None
    line.matched_refund_id = None
    line.state = SettlementLineState.UNMATCHED
    # If the settlement had progressed to MATCHED, drop back to IMPORTED.
    if settlement.state == SettlementState.MATCHED:
        settlement.state = SettlementState.IMPORTED
    await session.flush()
    await _emit(
        session,
        event_type=settlements_events.TYPE_SETTLEMENT_LINE_UNMATCHED,
        aggregate_id=settlement.id,
        payload={"settlement_id": str(settlement.id), "line_id": str(line.id)},
        actor_user_id=actor_user_id,
    )
    return line


async def ignore_line(
    *,
    session: AsyncSession,
    settlement_id: uuid.UUID,
    line_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> SettlementLine:
    settlement = await _load_settlement(session, settlement_id)
    if settlement.state == SettlementState.POSTED:
        raise InvalidSettlementStateError(
            f"settlement {settlement.settlement_number} is already posted"
        )
    line = await _load_line(session, line_id)
    if line.settlement_id != settlement_id:
        raise SettlementLineNotFoundError("line does not belong to this settlement")
    line.state = SettlementLineState.IGNORED
    await session.flush()
    await _emit(
        session,
        event_type=settlements_events.TYPE_SETTLEMENT_LINE_IGNORED,
        aggregate_id=settlement.id,
        payload={"settlement_id": str(settlement.id), "line_id": str(line.id)},
        actor_user_id=actor_user_id,
    )
    return line


# ---------------------------------------------------------------------------
# Post the payout JE
# ---------------------------------------------------------------------------


async def post(
    *,
    session: AsyncSession,
    settlement_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Settlement:
    """Atomically post the settlement payout JE.

    Requires every ``sale`` / ``refund`` line on the settlement to be
    either ``matched`` or ``ignored``. Same-TX: the row state flip + JE
    post + event emission all roll back together if anything raises.
    The router commits.
    """
    settlement = await _load_settlement(session, settlement_id)
    if settlement.state == SettlementState.POSTED:
        raise InvalidSettlementStateError(
            f"settlement {settlement.settlement_number} is already posted"
        )
    if settlement.state == SettlementState.CANCELLED:
        raise InvalidSettlementStateError(f"settlement {settlement.settlement_number} is cancelled")

    lines = list(
        (
            await session.execute(
                select(SettlementLine)
                .where(SettlementLine.settlement_id == settlement_id)
                .order_by(SettlementLine.line_number)
            )
        )
        .scalars()
        .all()
    )
    matchable_kinds = {SettlementLineKind.SALE, SettlementLineKind.REFUND}
    incomplete = [
        line
        for line in lines
        if line.line_kind in matchable_kinds and line.state == SettlementLineState.UNMATCHED
    ]
    if incomplete:
        raise IncompleteMatchError(
            f"{len(incomplete)} sale/refund lines on settlement "
            f"{settlement.settlement_number} are unmatched; resolve them before posting"
        )

    channel = (
        await session.execute(select(SalesChannel).where(SalesChannel.id == settlement.channel_id))
    ).scalar_one_or_none()
    if channel is None:
        raise MissingSettlementAccountError(f"settlement channel {settlement.channel_id} not found")
    if channel.default_clearing_account_id is None:
        raise MissingSettlementAccountError(
            f"sales channel {channel.slug!r} has no default_clearing_account_id; "
            "set it before posting"
        )

    payout_amount = _q(settlement.payout_amount)
    fee_amount = _q(settlement.fee_amount)
    refund_amount = _q(settlement.refund_amount)
    gross_amount = _q(settlement.gross_amount)
    adjustment_amount = _q(settlement.adjustment_amount)

    if fee_amount > _ZERO and channel.default_fee_account_id is None:
        raise MissingSettlementAccountError(
            f"sales channel {channel.slug!r} has fees of {fee_amount} but no "
            "default_fee_account_id; set it before posting"
        )

    adjustment_account_id: uuid.UUID | None = None
    if adjustment_amount != _ZERO:
        raw = await SettingsService.get(
            "settlements.default_adjustment_account_id", session=session
        )
        if raw is None:
            raise MissingSettlementAccountError(
                "settlement has a non-zero adjustment but "
                "settings.settlements.default_adjustment_account_id is unset"
            )
        adjustment_account_id = raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))

    clearing_credit = _q(gross_amount - refund_amount)

    # Build JE.
    lines_in: list[journal_service.JournalLineInput] = []
    line_no = 1
    lines_in.append(
        journal_service.JournalLineInput(
            account_id=settlement.payout_account_id,
            debit=payout_amount,
            credit=_ZERO,
            line_number=line_no,
            memo=f"Settlement payout {settlement.settlement_number}",
        )
    )
    line_no += 1
    if fee_amount > _ZERO:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=channel.default_fee_account_id,  # type: ignore[arg-type]
                debit=fee_amount,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Settlement fees {settlement.settlement_number}",
            )
        )
        line_no += 1
    if adjustment_amount > _ZERO and adjustment_account_id is not None:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=adjustment_account_id,
                debit=_ZERO,
                credit=adjustment_amount,
                line_number=line_no,
                memo=f"Settlement adjustment {settlement.settlement_number}",
            )
        )
        line_no += 1
    elif adjustment_amount < _ZERO and adjustment_account_id is not None:
        lines_in.append(
            journal_service.JournalLineInput(
                account_id=adjustment_account_id,
                debit=-adjustment_amount,
                credit=_ZERO,
                line_number=line_no,
                memo=f"Settlement adjustment {settlement.settlement_number}",
            )
        )
        line_no += 1
    lines_in.append(
        journal_service.JournalLineInput(
            account_id=channel.default_clearing_account_id,  # type: ignore[arg-type]
            debit=_ZERO,
            credit=clearing_credit,
            line_number=line_no,
            memo=f"Settlement clearing {settlement.settlement_number}",
        )
    )

    posted_at = datetime.combine(settlement.period_end, datetime.min.time(), tzinfo=UTC)
    entry = await journal_service.post(
        journal_service.JournalEntryInput(
            description=f"Settlement payout {settlement.settlement_number}",
            posted_at=posted_at,
            lines=lines_in,
        ),
        session=session,
        actor_user_id=actor_user_id,
        _internal_skip_approval_check=True,
    )
    assert isinstance(entry, JournalEntry)
    settlement.posting_journal_entry_id = entry.id
    settlement.state = SettlementState.POSTED
    await session.flush()

    await _emit(
        session,
        event_type=settlements_events.TYPE_SETTLEMENT_POSTED,
        aggregate_id=settlement.id,
        payload={
            "settlement_id": str(settlement.id),
            "settlement_number": settlement.settlement_number,
            "channel_id": str(settlement.channel_id),
            "journal_entry_id": str(entry.id),
            "payout_amount": str(payout_amount),
            "fee_amount": str(fee_amount),
            "adjustment_amount": str(adjustment_amount),
            "clearing_credit": str(clearing_credit),
        },
        actor_user_id=actor_user_id,
    )
    return settlement


__all__ = [
    "IncompleteMatchError",
    "InvalidMatchTargetError",
    "InvalidSettlementStateError",
    "MatchResult",
    "MissingSettlementAccountError",
    "SettlementLineNotFoundError",
    "SettlementMatcherError",
    "SettlementNotFoundError",
    "ignore_line",
    "manual_match",
    "manual_unmatch",
    "post",
    "run_match",
]
