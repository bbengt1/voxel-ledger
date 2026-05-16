"""Bills API (Phase 8.2, #129).

Thin layer over ``app.services.bills`` — the AP mirror of the Phase 7.3
invoices router. Routers commit the transaction, map service-layer
errors to HTTP, and gate each route on role:

* write (create / update / issue / void): owner + bookkeeper
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
from app.models.bill import Bill, BillItem, BillItemKind
from app.schemas.bills import (
    BillCreate,
    BillItemResponse,
    BillListResponse,
    BillResponse,
    BillStateTransitionRequest,
    BillUpdate,
)
from app.schemas.vendors import VendorAddress
from app.services import bills as bills_service
from app.services import files as file_storage
from app.services.settings.service import SettingsService

router = APIRouter(prefix="/bills", tags=["bills"])

_WRITE_ROLES = ("owner", "bookkeeper")
_READ_ROLES = ("owner", "bookkeeper", "sales", "viewer")
_PDF_ROLES = ("owner", "bookkeeper", "sales", "viewer")


def _to_item(item: BillItem) -> BillItemResponse:
    return BillItemResponse(
        id=item.id,
        line_number=item.line_number,
        kind=(item.kind.value if isinstance(item.kind, BillItemKind) else item.kind),  # type: ignore[arg-type]
        expense_category_id=item.expense_category_id,
        description=item.description,
        vendor_sku=item.vendor_sku,
        quantity=item.quantity,
        unit_price=item.unit_price,
        extended_amount=item.extended_amount,
        expense_account_id_override=item.expense_account_id_override,
    )


def _to_response(bill: Bill) -> BillResponse:
    snapshot = (
        VendorAddress(**bill.billing_address_snapshot) if bill.billing_address_snapshot else None
    )
    return BillResponse(
        id=bill.id,
        bill_number=bill.bill_number,
        vendor_id=bill.vendor_id,
        state=bill.state.value,  # type: ignore[arg-type]
        issued_at=bill.issued_at,
        due_at=bill.due_at,
        vendor_invoice_number=bill.vendor_invoice_number,
        subtotal=bill.subtotal,
        discount_amount=bill.discount_amount,
        tax_amount=bill.tax_amount,
        total_amount=bill.total_amount,
        amount_paid=bill.amount_paid,
        amount_outstanding=bill.amount_outstanding,
        currency=bill.currency,
        notes=bill.notes,
        billing_address_snapshot=snapshot,
        posting_journal_entry_id=bill.posting_journal_entry_id,
        created_by_user_id=bill.created_by_user_id,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
        items=[_to_item(i) for i in sorted(bill.items, key=lambda x: x.line_number)],
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, bills_service.BillNotFoundError):
        return HTTPException(status_code=404, detail="bill not found")
    if isinstance(exc, bills_service.VendorNotFoundForBillError):
        return HTTPException(status_code=400, detail=f"vendor not found: {exc}")
    if isinstance(exc, bills_service.MissingApPostingAccountError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bills_service.BillHasPaymentsError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bills_service.InvalidBillItemError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bills_service.InvalidBillStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bills_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, bills_service.BillServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=BillResponse, status_code=status.HTTP_201_CREATED)
async def create_bill(
    payload: BillCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> BillResponse:
    try:
        bill = await bills_service.create_draft(
            session,
            vendor_id=payload.vendor_id,
            due_at=payload.due_at,
            vendor_invoice_number=payload.vendor_invoice_number,
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
    bill = await bills_service.get(session, bill.id)
    return _to_response(bill)


@router.get("", response_model=BillListResponse)
async def list_bills(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    state: Annotated[str | None, Query()] = None,
    vendor_id: Annotated[uuid.UUID | None, Query()] = None,
    due_from: Annotated[datetime | None, Query()] = None,
    due_to: Annotated[datetime | None, Query()] = None,
    overdue: Annotated[bool | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> BillListResponse:
    try:
        page = await bills_service.list_bills(
            session,
            state=state,
            vendor_id=vendor_id,
            due_from=due_from,
            due_to=due_to,
            overdue=overdue,
            search=search,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_error(exc) from None
    return BillListResponse(
        items=[_to_response(b) for b in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{bill_id}", response_model=BillResponse)
async def get_bill(
    bill_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> BillResponse:
    try:
        bill = await bills_service.get(session, bill_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(bill)


@router.patch("/{bill_id}", response_model=BillResponse)
async def update_bill(
    bill_id: uuid.UUID,
    payload: BillUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> BillResponse:
    patch_dict = payload.model_dump(exclude_unset=True)
    try:
        await bills_service.update_draft(
            session, bill_id=bill_id, patch=patch_dict, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    bill = await bills_service.get(session, bill_id)
    return _to_response(bill)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


@router.post("/{bill_id}/issue", response_model=BillResponse)
async def issue_bill(
    bill_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: BillStateTransitionRequest | None = None,
) -> BillResponse:
    try:
        await bills_service.issue(session, bill_id=bill_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    bill = await bills_service.get(session, bill_id)
    return _to_response(bill)


@router.post("/{bill_id}/void", response_model=BillResponse)
async def void_bill(
    bill_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
    _payload: BillStateTransitionRequest | None = None,
) -> BillResponse:
    try:
        await bills_service.void(session, bill_id=bill_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    bill = await bills_service.get(session, bill_id)
    return _to_response(bill)


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------


def _bill_pdf_storage_key(bill_id: uuid.UUID) -> str:
    return f"bills/{bill_id}.pdf"


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


def _render_bill_pdf(bill: Bill) -> bytes:
    """Render the bill to a minimal one-page PDF using reportlab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.units import inch
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER
    margin = 0.5 * inch
    y = height - margin

    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, y, f"BILL {bill.bill_number}")
    y -= 0.4 * inch

    c.setFont("Helvetica", 10)
    c.drawString(margin, y, f"State: {bill.state.value}")
    y -= 0.2 * inch
    if bill.vendor_invoice_number:
        c.drawString(margin, y, f"Vendor invoice #: {bill.vendor_invoice_number}")
        y -= 0.2 * inch
    if bill.issued_at is not None:
        c.drawString(margin, y, f"Issued: {bill.issued_at.date().isoformat()}")
        y -= 0.2 * inch
    if bill.due_at is not None:
        c.drawString(margin, y, f"Due: {bill.due_at.date().isoformat()}")
        y -= 0.2 * inch

    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Bill From:")
    y -= 0.2 * inch
    c.setFont("Helvetica", 10)
    for line in _address_lines(bill.billing_address_snapshot):
        c.drawString(margin, y, line)
        y -= 0.18 * inch

    y -= 0.3 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin, y, "Lines:")
    y -= 0.2 * inch
    c.setFont("Helvetica", 9)
    for item in sorted(bill.items, key=lambda i: i.line_number):
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
    c.drawString(margin, y, f"Subtotal: {bill.subtotal}")
    y -= 0.2 * inch
    c.drawString(margin, y, f"Discount: -{bill.discount_amount}")
    y -= 0.2 * inch
    c.drawString(margin, y, f"Tax: {bill.tax_amount}")
    y -= 0.2 * inch
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, y, f"TOTAL: {bill.total_amount} {bill.currency}")

    c.showPage()
    c.save()
    return buf.getvalue()


@router.get("/{bill_id}/pdf")
async def bill_pdf(
    bill_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_PDF_ROLES))],
) -> Response:
    try:
        bill = await bills_service.get(session, bill_id)
    except Exception as exc:
        raise _map_error(exc) from None

    storage_key = _bill_pdf_storage_key(bill.id)
    raw_root = await SettingsService.get("bills.pdf_storage_root", session=session)
    root = Path(str(raw_root))

    pdf_bytes = file_storage.read_blob(storage_key, root=root)
    if pdf_bytes is None:
        pdf_bytes = _render_bill_pdf(bill)
        file_storage.write_blob(pdf_bytes, root=root, storage_key=storage_key)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{bill.bill_number}.pdf"',
        },
    )
