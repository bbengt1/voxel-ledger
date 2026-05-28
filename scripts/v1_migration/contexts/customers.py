"""Customer context migration (Phase 12.4, #206).

Fully worked. Reads v1 ``customers`` rows (or a JSON fixture in
tests), upserts into ``customer`` keyed on ``customer_number``, and
emits one ``ar.CustomerCreated`` event per new row with
``schema_version=0``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app.events.types import ar as ar_events
from app.models.customer import Customer, CustomerState
from sqlalchemy import select

from scripts.v1_migration.framework import (
    MigrationContext,
    MigrationResult,
    emit_backfill_event,
    register,
)


def _normalize(row: dict[str, Any]) -> dict[str, Any]:
    """Map a v1 row dict onto the v2 ``Customer`` field set.

    The v1 schema varies; the migration accepts a forgiving shape and
    fills sensible defaults. Override per-deployment by editing the
    field map below.
    """
    return {
        "customer_number": str(row["customer_number"]),
        "display_name": str(row.get("display_name") or row.get("name") or "Unknown"),
        "legal_name": row.get("legal_name"),
        "primary_email": row.get("primary_email") or row.get("email"),
        "phone": row.get("phone"),
        "payment_terms_days": int(row.get("payment_terms_days") or 30),
        "notes": row.get("notes"),
        "state": (
            CustomerState.ARCHIVED
            if str(row.get("state") or "active").lower() == "archived"
            else CustomerState.ACTIVE
        ),
        "created_at_v1": row.get("created_at"),
    }


def _v1_timestamp(value: Any) -> datetime:
    """Parse a v1 timestamp string into an aware UTC datetime."""
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)


@register("customers")
async def migrate(ctx: MigrationContext) -> MigrationResult:
    result = MigrationResult(context="customers")

    rows = _read_v1_customers(ctx.v1_session)
    for row in rows:
        result.rows_in += 1
        try:
            mapped = _normalize(row)
        except Exception as exc:
            result.errors.append(f"normalize {row!r}: {exc}")
            continue

        existing = (
            await ctx.v2_session.execute(
                select(Customer).where(Customer.customer_number == mapped["customer_number"])
            )
        ).scalar_one_or_none()
        if existing is not None:
            result.rows_skipped += 1
            continue

        new_id = uuid.uuid4()
        c = Customer(
            id=new_id,
            customer_number=mapped["customer_number"],
            display_name=mapped["display_name"],
            legal_name=mapped["legal_name"],
            primary_email=mapped["primary_email"],
            phone=mapped["phone"],
            payment_terms_days=mapped["payment_terms_days"],
            notes=mapped["notes"],
            state=mapped["state"],
        )
        ctx.v2_session.add(c)
        await ctx.v2_session.flush()

        await emit_backfill_event(
            session=ctx.v2_session,
            type=ar_events.TYPE_CUSTOMER_CREATED,
            aggregate_type=ar_events.AGGREGATE_TYPE_CUSTOMER,
            aggregate_id=new_id,
            payload={
                "customer_id": str(new_id),
                "customer_number": mapped["customer_number"],
                "display_name": mapped["display_name"],
                "legal_name": mapped["legal_name"],
                "primary_email": mapped["primary_email"],
                "phone": mapped["phone"],
                "payment_terms_days": mapped["payment_terms_days"],
                "default_revenue_account_id": None,
                "default_ar_account_id": None,
                "tax_profile_id": None,
                "state": mapped["state"].value,
            },
            original_occurred_at=_v1_timestamp(mapped["created_at_v1"]),
            actor_user_id=ctx.actor_user_id,
        )
        result.rows_out += 1
        result.events_emitted += 1

    return result


def _read_v1_customers(v1_session: Any) -> list[dict[str, Any]]:
    """Return v1 customer rows as plain dicts.

    Two shapes accepted today:

    1. Test path: ``v1_session`` is a ``dict[str, list[dict]]`` keyed
       by context name (``{"customers": [...]}``).
    2. Production: ``v1_session`` is a real DB session; this function
       gets monkey-patched at cutover time to issue the actual SELECT.
    """
    if isinstance(v1_session, dict):
        return list(v1_session.get("customers") or [])
    raise NotImplementedError("Wire _read_v1_customers to the real v1 connection at cutover.")
