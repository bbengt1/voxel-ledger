"""Customer-credit-balance projection handlers (Phase 7.4, #112).

Two events drive the balance:

* ``ar.CustomerCreditAccrued`` -> increment available_amount
* ``ar.CustomerCreditApplied`` -> decrement available_amount

Both use the same dialect-aware ``INSERT ... ON CONFLICT DO UPDATE``
pattern as ``inventory_on_hand`` so replay against a truncated read
model reproduces the same totals.
"""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types.ar import (
    TYPE_CUSTOMER_CREDIT_ACCRUED,
    TYPE_CUSTOMER_CREDIT_APPLIED,
)
from app.models.customer_credit import CustomerCreditBalance
from app.models.event import Event
from app.projections.registry import projection

HANDLER_NAME_ACCRUAL = "customer_credit_balance_accrual"
HANDLER_NAME_APPLICATION = "customer_credit_balance_application"
READ_MODEL_TABLES: tuple[str, ...] = ("customer_credit_balance",)

_QUANTUM = Decimal("0.000001")


def _to_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _to_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


async def _apply_delta(session: AsyncSession, *, customer_id: uuid.UUID, delta: Decimal) -> None:
    delta_q = delta.quantize(_QUANTUM, rounding=ROUND_HALF_UP)
    dialect = session.bind.dialect.name if session.bind is not None else "sqlite"
    insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
    values = {
        "id": uuid.uuid4(),
        "customer_id": customer_id,
        "available_amount": delta_q,
    }
    stmt = insert_fn(CustomerCreditBalance).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["customer_id"],
        set_={
            "available_amount": (
                CustomerCreditBalance.available_amount + stmt.excluded.available_amount
            ),
        },
    )
    await session.execute(stmt)
    await session.flush()


@projection(
    event_type=TYPE_CUSTOMER_CREDIT_ACCRUED,
    name=HANDLER_NAME_ACCRUAL,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_customer_credit_accrued(event: Event, session: AsyncSession) -> None:
    payload = event.payload or {}
    await _apply_delta(
        session,
        customer_id=_to_uuid(payload["customer_id"]),
        delta=_to_decimal(payload["amount"]),
    )


@projection(
    event_type=TYPE_CUSTOMER_CREDIT_APPLIED,
    name=HANDLER_NAME_APPLICATION,
    read_model_tables=READ_MODEL_TABLES,
)
async def project_customer_credit_applied(event: Event, session: AsyncSession) -> None:
    payload = event.payload or {}
    await _apply_delta(
        session,
        customer_id=_to_uuid(payload["customer_id"]),
        delta=-_to_decimal(payload["amount"]),
    )
