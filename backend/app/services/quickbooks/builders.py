"""Document builders: turn an outbox row into a pushed QBO entity (#316).

A builder is registered per outbox ``kind``. It receives the session, a QBO
client, and the outbox row, builds the QBO document from ``row.payload`` (the
role-tagged spec), pushes it via the client (using ``row.request_id`` for
idempotency), and returns ``(qbo_entity_type, qbo_object)``.

Phase 3a ships the **generic JournalEntry** builder — the fallback for any
posting with no native QBO document. Native builders (Invoice/Bill/Payment/…)
register themselves in Phases 3b-3d. Reversals: the enqueuing site encodes the
reversing direction in ``payload`` (swapped debit/credit) for JE-based postings;
native builders branch on ``row.op`` (void/delete) when those land.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.quickbooks import account_map

if TYPE_CHECKING:
    from app.models.qbo_sync_outbox import QboSyncOutbox

# (entity_type, qbo_object)
BuilderFn = Callable[[AsyncSession, Any, "QboSyncOutbox"], Awaitable[tuple[str, dict[str, Any]]]]

_REGISTRY: dict[str, BuilderFn] = {}


class BuilderError(RuntimeError):
    """A permanent build problem (no builder for the kind, malformed spec)."""


class DependencyNotReadyError(RuntimeError):
    """A prerequisite isn't synced yet (e.g. an invoice a payment links to).

    Treated as transient by the worker — retried with backoff, dead-lettered
    only past the retry window."""


def register_builder(kind: str, fn: BuilderFn) -> None:
    _REGISTRY[kind] = fn


def get_builder(kind: str) -> BuilderFn | None:
    return _REGISTRY.get(kind)


async def build_and_push(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    """Dispatch to the registered builder for ``row.kind`` and push to QBO."""
    builder = get_builder(row.kind)
    if builder is None:
        raise BuilderError(f"no QBO document builder registered for kind {row.kind!r}")
    return await builder(session, client, row)


async def _journal_entry_payload(session: AsyncSession, spec: dict[str, Any]) -> dict[str, Any]:
    """Build a balanced QBO JournalEntry payload from a role-tagged spec."""
    lines = spec.get("lines") or []
    if not lines:
        raise BuilderError("journal_entry spec has no lines")
    qbo_lines: list[dict[str, Any]] = []
    for leg in lines:
        try:
            account_id = await account_map.resolve(session, leg["role"])
        except KeyError as exc:
            raise BuilderError(f"journal_entry line missing 'role': {leg}") from exc
        posting = "Debit" if leg.get("posting") == "debit" else "Credit"
        detail: dict[str, Any] = {
            "PostingType": posting,
            "AccountRef": {"value": account_id},
        }
        entity = leg.get("entity")
        if entity and entity.get("type") and entity.get("qbo_id"):
            detail["Entity"] = {
                "Type": entity["type"],
                "EntityRef": {"value": entity["qbo_id"]},
            }
        line: dict[str, Any] = {
            "DetailType": "JournalEntryLineDetail",
            "Amount": float(leg["amount"]),
            "JournalEntryLineDetail": detail,
        }
        if leg.get("description"):
            line["Description"] = leg["description"]
        qbo_lines.append(line)

    payload: dict[str, Any] = {"Line": qbo_lines}
    if spec.get("doc_number"):
        payload["DocNumber"] = spec["doc_number"]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    return payload


async def build_journal_entry(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    payload = await _journal_entry_payload(session, row.payload)
    qbo_obj = await client.create("JournalEntry", payload, request_id=row.request_id)
    return "JournalEntry", qbo_obj


register_builder("journal_entry", build_journal_entry)


# --------------------------------------------------------------------------- #
# Native Invoice (#316 Phase 3b)
# --------------------------------------------------------------------------- #
async def _ensure_customer(session: AsyncSession, client: Any, customer_id: str) -> str:
    """Return the QBO Customer id, auto-mapping (upserting) on demand."""
    import uuid as _uuid

    from app.services.quickbooks import master_data

    mapping = await master_data._get_mapping(
        session, master_data.QboLocalKind.CUSTOMER, _uuid.UUID(customer_id)
    )
    if mapping is not None:
        return mapping.qbo_id
    return (await master_data.upsert_customer(session, client, _uuid.UUID(customer_id))).qbo_id


async def _ensure_item(session: AsyncSession, client: Any, product_id: str | None) -> str:
    """Return the QBO Item id for a line: the mapped product, else the
    configured fallback sales item for job/manual (product-less) lines."""
    import uuid as _uuid

    from app.services.quickbooks import master_data

    if product_id:
        mapping = await master_data._get_mapping(
            session, master_data.QboLocalKind.PRODUCT, _uuid.UUID(product_id)
        )
        if mapping is not None:
            return mapping.qbo_id
        return (await master_data.upsert_product(session, client, _uuid.UUID(product_id))).qbo_id

    from app.services.settings.service import SettingsService

    fallback = await SettingsService.get("quickbooks.default_sales_item_id", session=session)
    if not fallback:
        raise BuilderError(
            "invoice line has no product; set quickbooks.default_sales_item_id "
            "(a QBO Item) to sync job/manual lines"
        )
    return str(fallback)


async def _create_invoice(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    spec = row.payload
    customer_ref = await _ensure_customer(session, client, spec["customer_id"])
    lines: list[dict[str, Any]] = []
    for line in spec.get("lines", []):
        item_ref = await _ensure_item(session, client, line.get("product_id"))
        lines.append(
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": float(line["amount"]),
                "Description": line.get("description"),
                "SalesItemLineDetail": {
                    "ItemRef": {"value": item_ref},
                    "Qty": float(line["qty"]),
                    "UnitPrice": float(line["unit_price"]),
                },
            }
        )
    if not lines:
        raise BuilderError("invoice spec has no lines")

    payload: dict[str, Any] = {"CustomerRef": {"value": customer_ref}, "Line": lines}
    if spec.get("doc_number"):
        payload["DocNumber"] = spec["doc_number"]
    if spec.get("txn_date"):
        payload["TxnDate"] = spec["txn_date"]
    if spec.get("due_date"):
        payload["DueDate"] = spec["due_date"]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    # Best-effort manual tax (validate against the live company in sandbox —
    # Automated-Sales-Tax companies may compute their own; #316 3b note).
    tax = float(spec.get("tax_amount") or 0)
    if tax > 0:
        payload["TxnTaxDetail"] = {"TotalTax": tax}

    qbo_obj = await client.create("Invoice", payload, request_id=row.request_id)
    return "Invoice", qbo_obj


async def _void_invoice(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    from sqlalchemy import select

    from app.models.qbo_sync_outbox import QboSyncOutbox as _Outbox
    from app.models.qbo_sync_outbox import QboSyncStatus as _Status

    orig = (
        (
            await session.execute(
                select(_Outbox)
                .where(_Outbox.kind == "invoice")
                .where(_Outbox.local_id == row.local_id)
                .where(_Outbox.op == "post")
                .where(_Outbox.status == _Status.SYNCED.value)
                .order_by(_Outbox.updated_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if orig is None or not orig.qbo_id:
        raise DependencyNotReadyError(
            f"cannot void invoice {row.local_id}: its QBO Invoice isn't synced yet"
        )
    # Read the live SyncToken (it may have advanced) before voiding.
    current = await client.read("Invoice", orig.qbo_id)
    qbo_obj = await client.void("Invoice", orig.qbo_id, current.get("SyncToken", "0"))
    return "Invoice", qbo_obj


async def build_invoice(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        return await _void_invoice(session, client, row)
    return await _create_invoice(session, client, row)


register_builder("invoice", build_invoice)
