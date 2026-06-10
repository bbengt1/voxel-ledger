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


async def _resolve_je_entity(
    session: AsyncSession, client: Any, entity: dict[str, Any]
) -> dict | None:
    """Resolve a JE line ``Entity`` for an A/R or A/P leg.

    QBO requires a Customer (AR) or Vendor (AP) on a JE line that hits an A/R or
    A/P account (validated 2026-06-10, code 6000). Accepts either a pre-resolved
    ``{type, qbo_id}`` or ``{type, local_id}`` (auto-mapped on demand)."""
    etype = entity.get("type")
    if not etype:
        return None
    qbo_id = entity.get("qbo_id")
    if not qbo_id:
        local_id = entity.get("local_id")
        if not local_id:
            return None
        qbo_id = (
            await _ensure_vendor(session, client, local_id)
            if etype == "Vendor"
            else await _ensure_customer(session, client, local_id)
        )
    return {"Type": etype, "EntityRef": {"value": qbo_id}}


async def _journal_entry_payload(
    session: AsyncSession, client: Any, spec: dict[str, Any]
) -> dict[str, Any]:
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
        if entity:
            resolved = await _resolve_je_entity(session, client, entity)
            if resolved:
                detail["Entity"] = resolved
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
    payload = await _journal_entry_payload(session, client, row.payload)
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


async def _ensure_vendor(session: AsyncSession, client: Any, vendor_id: str) -> str:
    """Return the QBO Vendor id, auto-mapping (upserting) on demand."""
    import uuid as _uuid

    from app.services.quickbooks import master_data

    mapping = await master_data._get_mapping(
        session, master_data.QboLocalKind.VENDOR, _uuid.UUID(str(vendor_id))
    )
    if mapping is not None:
        return mapping.qbo_id
    return (await master_data.upsert_vendor(session, client, _uuid.UUID(str(vendor_id)))).qbo_id


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


async def _synced_post(session: AsyncSession, kind: str, local_id: Any) -> tuple[str | None, str]:
    """Return (qbo_entity_type, qbo_id) of the synced ``post`` row for
    (kind, local_id). Raises :class:`DependencyNotReadyError` if it hasn't
    synced yet (the referencing op should retry, not fail)."""
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.qbo_sync_outbox import QboSyncOutbox as _Outbox
    from app.models.qbo_sync_outbox import QboSyncStatus as _Status

    local_uuid = local_id if isinstance(local_id, _uuid.UUID) else _uuid.UUID(str(local_id))
    row = (
        (
            await session.execute(
                select(_Outbox)
                .where(_Outbox.kind == kind)
                .where(_Outbox.local_id == local_uuid)
                .where(_Outbox.op == "post")
                .where(_Outbox.status == _Status.SYNCED.value)
                .order_by(_Outbox.updated_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if row is None or not row.qbo_id:
        raise DependencyNotReadyError(f"{kind} {local_id} isn't synced to QBO yet")
    return row.qbo_entity_type, row.qbo_id


async def _synced_post_qbo_id(session: AsyncSession, kind: str, local_id: Any) -> str:
    return (await _synced_post(session, kind, local_id))[1]


async def _void_entity(
    session: AsyncSession,
    client: Any,
    *,
    kind: str,
    local_id: Any,
    entity: str | None = None,
    operation: str = "void",
) -> tuple[str, dict[str, Any]]:
    """Reverse the synced doc. ``operation`` is "void" (Invoice/Payment/
    SalesReceipt) or "delete" (Bill/BillPayment/CreditMemo — no void). ``entity``
    overrides the stored type; for sales it's None → the synced row's type."""
    stored_entity, qbo_id = await _synced_post(session, kind, local_id)
    use_entity = entity or stored_entity or "Invoice"
    # Read the live SyncToken (it may have advanced) before reversing.
    current = await client.read(use_entity, qbo_id)
    token = current.get("SyncToken", "0")
    if operation == "delete":
        qbo_obj = await client.delete(use_entity, qbo_id, token)
    else:
        qbo_obj = await client.void(use_entity, qbo_id, token)
    return use_entity, qbo_obj


async def build_invoice(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        return await _void_entity(
            session, client, entity="Invoice", kind="invoice", local_id=row.local_id
        )
    return await _create_invoice(session, client, row)


register_builder("invoice", build_invoice)


# --------------------------------------------------------------------------- #
# Native Payment (#316 Phase 3b-2)
# --------------------------------------------------------------------------- #
async def _create_payment(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    spec = row.payload
    customer_ref = await _ensure_customer(session, client, spec["customer_id"])
    lines: list[dict[str, Any]] = []
    for app in spec.get("applications", []):
        invoice_qbo_id = await _synced_post_qbo_id(session, "invoice", app["invoice_id"])
        lines.append(
            {
                "Amount": float(app["amount"]),
                "LinkedTxn": [{"TxnId": invoice_qbo_id, "TxnType": "Invoice"}],
            }
        )
    payload: dict[str, Any] = {
        "CustomerRef": {"value": customer_ref},
        "TotalAmt": float(spec["amount"]),
    }
    if lines:
        payload["Line"] = lines
    if spec.get("txn_date"):
        payload["TxnDate"] = spec["txn_date"]
    if spec.get("reference"):
        payload["PaymentRefNum"] = str(spec["reference"])[:21]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    # Deposit account: omit → QBO Undeposited Funds; else the mapped bank account.
    if not spec.get("deposit_to_undeposited"):
        bank_id = await account_map.resolve(session, "bank")
        payload["DepositToAccountRef"] = {"value": bank_id}

    qbo_obj = await client.create("Payment", payload, request_id=row.request_id)
    return "Payment", qbo_obj


async def build_payment(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        return await _void_entity(
            session, client, entity="Payment", kind="payment", local_id=row.local_id
        )
    return await _create_payment(session, client, row)


register_builder("payment", build_payment)


# --------------------------------------------------------------------------- #
# Native Sale → Invoice (customer) / SalesReceipt (walk-in) (#316 Phase 3b-3)
# --------------------------------------------------------------------------- #
async def _create_sale_doc(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    spec = row.payload
    has_customer = bool(spec.get("customer_id"))
    entity = "Invoice" if has_customer else "SalesReceipt"

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
    shipping = float(spec.get("shipping_amount") or 0)
    if shipping > 0:
        ship_item = await _ensure_item(session, client, None)  # fallback sales item
        lines.append(
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": shipping,
                "Description": "Shipping",
                "SalesItemLineDetail": {"ItemRef": {"value": ship_item}, "Qty": 1.0},
            }
        )
    discount = float(spec.get("discount_amount") or 0)
    if discount > 0:
        lines.append(
            {
                "DetailType": "DiscountLineDetail",
                "Amount": discount,
                "DiscountLineDetail": {"PercentBased": False},
            }
        )
    if not lines:
        raise BuilderError("sale spec has no lines")

    payload: dict[str, Any] = {"Line": lines}
    if spec.get("doc_number"):
        payload["DocNumber"] = spec["doc_number"]
    if spec.get("txn_date"):
        payload["TxnDate"] = spec["txn_date"]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    tax = float(spec.get("tax_amount") or 0)
    if tax > 0:
        payload["TxnTaxDetail"] = {"TotalTax": tax}

    if has_customer:
        payload["CustomerRef"] = {
            "value": await _ensure_customer(session, client, spec["customer_id"])
        }
    else:
        # Walk-in cash sale → deposit straight to the mapped bank account.
        payload["DepositToAccountRef"] = {"value": await account_map.resolve(session, "bank")}

    qbo_obj = await client.create(entity, payload, request_id=row.request_id)
    return entity, qbo_obj


async def build_sale(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        # entity=None → void whichever doc type (Invoice/SalesReceipt) we pushed.
        return await _void_entity(session, client, kind="sale", local_id=row.local_id)
    return await _create_sale_doc(session, client, row)


register_builder("sale", build_sale)
# The COGS/inventory (+ channel-fee) leg of a sale is a plain JournalEntry.
register_builder("sale_cogs", build_journal_entry)


# --------------------------------------------------------------------------- #
# Native Bill / BillPayment (#316 Phase 3c-1, AP)
# --------------------------------------------------------------------------- #
async def _create_bill(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    spec = row.payload
    vendor_ref = await _ensure_vendor(session, client, spec["vendor_id"])
    expense_acct = await account_map.resolve(session, "expense")
    lines: list[dict[str, Any]] = [
        {
            "DetailType": "AccountBasedExpenseLineDetail",
            "Amount": float(line["amount"]),
            "Description": line.get("description"),
            "AccountBasedExpenseLineDetail": {"AccountRef": {"value": expense_acct}},
        }
        for line in spec.get("lines", [])
    ]
    tax = float(spec.get("tax_amount") or 0)
    if tax > 0:
        tax_acct = await account_map.resolve(session, "tax_expense")
        lines.append(
            {
                "DetailType": "AccountBasedExpenseLineDetail",
                "Amount": tax,
                "Description": "Tax",
                "AccountBasedExpenseLineDetail": {"AccountRef": {"value": tax_acct}},
            }
        )
    if not lines:
        raise BuilderError("bill spec has no lines")

    payload: dict[str, Any] = {"VendorRef": {"value": vendor_ref}, "Line": lines}
    # QBO Bill DocNumber is the vendor's reference number.
    if spec.get("vendor_invoice_number"):
        payload["DocNumber"] = spec["vendor_invoice_number"]
    if spec.get("txn_date"):
        payload["TxnDate"] = spec["txn_date"]
    if spec.get("due_date"):
        payload["DueDate"] = spec["due_date"]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    qbo_obj = await client.create("Bill", payload, request_id=row.request_id)
    return "Bill", qbo_obj


async def build_bill(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        return await _void_entity(
            session, client, entity="Bill", kind="bill", local_id=row.local_id, operation="delete"
        )
    return await _create_bill(session, client, row)


register_builder("bill", build_bill)


async def _create_bill_payment(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    spec = row.payload
    vendor_ref = await _ensure_vendor(session, client, spec["vendor_id"])
    lines: list[dict[str, Any]] = []
    for app in spec.get("applications", []):
        bill_qbo_id = await _synced_post_qbo_id(session, "bill", app["bill_id"])
        lines.append(
            {
                "Amount": float(app["amount"]),
                "LinkedTxn": [{"TxnId": bill_qbo_id, "TxnType": "Bill"}],
            }
        )
    bank_id = await account_map.resolve(session, "bank")
    payload: dict[str, Any] = {
        "VendorRef": {"value": vendor_ref},
        "TotalAmt": float(spec["amount"]),
        # Pay by check from the mapped bank account.
        "PayType": "Check",
        "CheckPayment": {"BankAccountRef": {"value": bank_id}},
    }
    if lines:
        payload["Line"] = lines
    if spec.get("txn_date"):
        payload["TxnDate"] = spec["txn_date"]
    if spec.get("reference"):
        payload["DocNumber"] = str(spec["reference"])[:21]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    qbo_obj = await client.create("BillPayment", payload, request_id=row.request_id)
    return "BillPayment", qbo_obj


async def build_bill_payment(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        return await _void_entity(
            session,
            client,
            entity="BillPayment",
            kind="bill_payment",
            local_id=row.local_id,
            operation="delete",
        )
    return await _create_bill_payment(session, client, row)


register_builder("bill_payment", build_bill_payment)
# A bill-payment withholding leg (Dr AP[Vendor], Cr withholding liability) rides
# as a JournalEntry with a Vendor entity.
register_builder("bill_payment_withholding", build_journal_entry)


# --------------------------------------------------------------------------- #
# Credit notes → CreditMemo; debit notes → JournalEntry (#316 Phase 3c-2)
# --------------------------------------------------------------------------- #
async def _create_credit_memo(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    spec = row.payload
    customer_ref = await _ensure_customer(session, client, spec["customer_id"])
    item_ref = await _ensure_item(session, client, None)  # generic sales item
    amount = float(spec["amount"])
    payload: dict[str, Any] = {
        "CustomerRef": {"value": customer_ref},
        "Line": [
            {
                "DetailType": "SalesItemLineDetail",
                "Amount": amount,
                "Description": spec.get("reason") or "Credit",
                "SalesItemLineDetail": {
                    "ItemRef": {"value": item_ref},
                    "Qty": 1.0,
                    "UnitPrice": amount,
                },
            }
        ],
    }
    if spec.get("doc_number"):
        payload["DocNumber"] = spec["doc_number"]
    if spec.get("txn_date"):
        payload["TxnDate"] = spec["txn_date"]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    qbo_obj = await client.create("CreditMemo", payload, request_id=row.request_id)
    return "CreditMemo", qbo_obj


async def build_credit_note(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    if row.op == "reverse":
        return await _void_entity(
            session,
            client,
            entity="CreditMemo",
            kind="credit_note",
            local_id=row.local_id,
            operation="delete",
        )
    return await _create_credit_memo(session, client, row)


register_builder("credit_note", build_credit_note)


async def build_debit_note(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    # No native QBO customer debit-memo: post a JournalEntry (Dr A/R + Customer
    # Entity, Cr Revenue); reverse by deleting that JE.
    if row.op == "reverse":
        return await _void_entity(
            session,
            client,
            entity="JournalEntry",
            kind="debit_note",
            local_id=row.local_id,
            operation="delete",
        )
    return await build_journal_entry(session, client, row)


register_builder("debit_note", build_debit_note)
