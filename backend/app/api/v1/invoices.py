"""Invoices API (Phase 7.3, #111).

Thin layer over ``app.services.invoices``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role:

* write (create / update / issue / void): owner + bookkeeper + sales
* read (list / get / pdf): owner + bookkeeper + sales + viewer
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.invoice import Invoice, InvoiceItem, InvoiceItemKind
from app.schemas.customers import CustomerAddress
from app.schemas.invoices import (
    InvoiceCreate,
    InvoiceItemResponse,
    InvoiceListResponse,
    InvoiceResponse,
    InvoiceStateTransitionRequest,
    InvoiceUpdate,
    InvoiceWriteOffRequest,
)
from app.services import files as file_storage
from app.services import invoices as invoices_service
from app.services.settings.service import SettingsService

router = APIRouter(prefix="/invoices", tags=["invoices"])

_WRITE_ROLES = ("owner", "bookkeeper", "sales")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")
_PDF_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_item(item: InvoiceItem) -> InvoiceItemResponse:
    return InvoiceItemResponse(
        id=item.id,
        line_number=item.line_number,
        kind=(item.kind.value if isinstance(item.kind, InvoiceItemKind) else item.kind),  # type: ignore[arg-type]
        product_id=item.product_id,
        job_id=item.job_id,
        description=item.description,
        sku_or_job_number=item.sku_or_job_number,
        quantity=item.quantity,
        unit_price=item.unit_price,
        extended_amount=item.extended_amount,
    )


def _to_response(invoice: Invoice) -> InvoiceResponse:
    snapshot = (
        CustomerAddress(**invoice.billing_address_snapshot)
        if invoice.billing_address_snapshot
        else None
    )
    return InvoiceResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        customer_id=invoice.customer_id,
        quote_id=invoice.quote_id,
        sale_id=invoice.sale_id,
        state=invoice.state.value,  # type: ignore[arg-type]
        issued_at=invoice.issued_at,
        due_at=invoice.due_at,
        subtotal=invoice.subtotal,
        discount_amount=invoice.discount_amount,
        tax_amount=invoice.tax_amount,
        total_amount=invoice.total_amount,
        amount_paid=invoice.amount_paid,
        amount_outstanding=invoice.amount_outstanding,
        currency=invoice.currency,
        notes=invoice.notes,
        billing_address_snapshot=snapshot,
        posting_journal_entry_id=invoice.posting_journal_entry_id,
        created_by_user_id=invoice.created_by_user_id,
        created_at=invoice.created_at,
        updated_at=invoice.updated_at,
        items=[_to_item(i) for i in sorted(invoice.items, key=lambda x: x.line_number)],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, invoices_service.InvoiceNotFoundError):
        return HTTPException(status_code=404, detail="invoice not found")
    if isinstance(exc, invoices_service.CustomerNotFoundForInvoiceError):
        return HTTPException(status_code=400, detail=f"customer not found: {exc}")
    if isinstance(exc, invoices_service.MissingArPostingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, invoices_service.InvoiceHasPaymentsError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, invoices_service.InvalidInvoiceItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, invoices_service.InvalidInvoiceStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, invoices_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, invoices_service.InvoiceServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: InvoiceCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> InvoiceResponse:
    try:
        invoice = await invoices_service.create_draft(
            session,
            customer_id=payload.customer_id,
            due_at=payload.due_at,
            discount_amount=payload.discount_amount,
            tax_amount=payload.tax_amount,
            notes=payload.notes,
            items=[item.model_dump() for item in payload.items],
            currency=payload.currency,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    invoice = await invoices_service.get(session, invoice.id)
    return _to_response(invoice)


@router.get("", response_model=InvoiceListResponse)
async def list_invoices(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    customer_id: Annotated[uuid.UUID | None, Query()] = None,
    due_before: Annotated[datetime | None, Query()] = None,
    due_after: Annotated[datetime | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> InvoiceListResponse:
    try:
        page = await invoices_service.list_invoices(
            session,
            state=state,
            customer_id=customer_id,
            due_before=due_before,
            due_after=due_after,
            search=search,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return InvoiceListResponse(
        items=[_to_response(inv) for inv in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
async def get_invoice(
    invoice_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> InvoiceResponse:
    try:
        invoice = await invoices_service.get(session, invoice_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(invoice)


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
async def update_invoice(
    invoice_id: uuid.UUID,
    payload: InvoiceUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> InvoiceResponse:
    patch_dict = payload.model_dump(exclude_unset=True)
    try:
        await invoices_service.update_draft(
            session, invoice_id=invoice_id, patch=patch_dict, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    invoice = await invoices_service.get(session, invoice_id)
    return _to_response(invoice)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


@router.post("/{invoice_id}/issue", response_model=InvoiceResponse)
async def issue_invoice(
    invoice_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: InvoiceStateTransitionRequest | None = None,
) -> InvoiceResponse:
    try:
        await invoices_service.issue(session, invoice_id=invoice_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    invoice = await invoices_service.get(session, invoice_id)
    return _to_response(invoice)


@router.post("/{invoice_id}/void", response_model=InvoiceResponse)
async def void_invoice(
    invoice_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: InvoiceStateTransitionRequest | None = None,
) -> InvoiceResponse:
    try:
        await invoices_service.void(session, invoice_id=invoice_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    invoice = await invoices_service.get(session, invoice_id)
    return _to_response(invoice)


@router.post("/{invoice_id}/write-off", response_model=InvoiceResponse)
async def write_off_invoice(
    invoice_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    # Write-off recognizes bad debt as expense — accounting decision.
    # Sales can issue/void but cannot write off.
    actor: Annotated[User, Depends(require_role("owner", "bookkeeper"))],
    payload: InvoiceWriteOffRequest,
) -> InvoiceResponse:
    """Write off the outstanding balance of an invoice as bad debt
    (Parity #236).

    DR ``bad_debt_account_id`` (defaults to the
    ``ar.default_bad_debt_account_id`` setting) for
    ``amount_outstanding``; CR the customer's AR account. Flips
    invoice state to ``written_off`` and emits
    ``ar.InvoiceWrittenOff``.
    """
    try:
        await invoices_service.write_off(
            session,
            invoice_id=invoice_id,
            actor_user_id=actor.id,
            bad_debt_account_id=payload.bad_debt_account_id,
            posted_at=payload.posted_at,
            reason=payload.reason,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    invoice = await invoices_service.get(session, invoice_id)
    return _to_response(invoice)


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------


def _invoice_pdf_storage_key(invoice_id: uuid.UUID) -> str:
    return f"invoices/{invoice_id}.pdf"


def _address_lines(addr: dict[str, Any] | None) -> list[str]:
    if not addr:
        return ["(address unavailable)"]
    out: list[str] = []
    for key in ("line1", "line2"):
        v = addr.get(key)
        if v:
            out.append(str(v))
    bits = []
    for key in ("city", "region", "postal_code"):
        v = addr.get(key)
        if v:
            bits.append(str(v))
    if bits:
        out.append(", ".join(bits))
    country = addr.get("country")
    if country:
        out.append(str(country))
    if not out:
        out.append("(address unavailable)")
    return out


def _render_invoice_pdf(invoice: Invoice) -> bytes:
    """Render the invoice to a minimal one-page PDF using reportlab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    margin = 0.5 * inch
    y = height - margin

    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, f"INVOICE {invoice.invoice_number}")
    y -= 0.4 * inch

    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"State: {invoice.state.value}")
    y -= 0.2 * inch
    if invoice.issued_at is not None:
        c.drawString(margin, y, f"Issued: {invoice.issued_at.date().isoformat()}")
        y -= 0.2 * inch
    if invoice.due_at is not None:
        c.drawString(margin, y, f"Due: {invoice.due_at.date().isoformat()}")
        y -= 0.2 * inch

    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Bill To:")
    y -= 0.2 * inch
    c.setFont("Helvetica", 10)
    for line in _address_lines(invoice.billing_address_snapshot):
        c.drawString(margin, y, line)
        y -= 0.18 * inch

    y -= 0.3 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Lines:")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    for item in sorted(invoice.items, key=lambda i: i.line_number):
        c.drawString(
            margin,
            y,
            f"{item.line_number}. {item.description[:50]} "
            f"qty={item.quantity} @ {item.unit_price} = {item.extended_amount}",
        )
        y -= 0.18 * inch
        if y < margin + 1.5 * inch:
            c.showPage()
            y = height - margin
            c.setFont("Helvetica", 9)

    y -= 0.3 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, f"Subtotal: {invoice.subtotal}")
    y -= 0.2 * inch
    c.drawString(margin, y, f"Discount: -{invoice.discount_amount}")
    y -= 0.2 * inch
    c.drawString(margin, y, f"Tax: {invoice.tax_amount}")
    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, f"TOTAL: {invoice.total_amount} {invoice.currency}")

    c.showPage()
    c.save()
    return buf.getvalue()


@router.get("/{invoice_id}/pdf")
async def invoice_pdf(
    invoice_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_PDF_ROLES))],
) -> Response:
    try:
        invoice = await invoices_service.get(session, invoice_id)
    except Exception as exc:
        raise _map_error(exc) from None

    storage_key = _invoice_pdf_storage_key(invoice.id)
    raw_root = await SettingsService.get("invoices.pdf_storage_root", session=session)
    root = Path(str(raw_root))

    pdf_bytes = file_storage.read_blob(storage_key, root=root)
    if pdf_bytes is None:
        # Render on demand + cache to disk for next call.
        pdf_bytes = _render_invoice_pdf(invoice)
        file_storage.write_blob(pdf_bytes, root=root, storage_key=storage_key)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{invoice.invoice_number}.pdf"',
        },
    )
