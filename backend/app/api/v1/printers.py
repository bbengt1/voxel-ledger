"""Printers endpoints (Phase 5.1).

Thin layer over ``app.services.printers``. Routers commit the
transaction, map service-layer errors to HTTP, and gate each route on
role. Responses NEVER include ``moonraker_api_key``; the surface uses
``moonraker_api_key_set: bool`` instead.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.printer import Printer
from app.schemas.printers import (
    PrinterCreateRequest,
    PrinterListResponse,
    PrinterResponse,
    PrinterUpdateRequest,
)
from app.services import printers as printers_service

router = APIRouter(prefix="/printers", tags=["printers"])


async def _refresh_for_response(session: AsyncSession, printer: Printer) -> None:
    await session.refresh(printer, ["created_at", "updated_at"])


def _to_response(printer: Printer) -> PrinterResponse:
    return PrinterResponse(
        id=printer.id,
        name=printer.name,
        slug=printer.slug,
        printer_type=printer.printer_type.value,  # type: ignore[arg-type]
        moonraker_url=printer.moonraker_url,
        moonraker_api_key_set=printer.moonraker_api_key is not None,
        power_draw_watts=printer.power_draw_watts,
        purchase_price=printer.purchase_price,
        salvage_value=printer.salvage_value,
        lifespan_years=printer.lifespan_years,
        annual_print_hours=printer.annual_print_hours,
        preheat_minutes=printer.preheat_minutes,
        preheat_power_watts=printer.preheat_power_watts,
        notes=printer.notes,
        is_archived=printer.is_archived,
        created_at=printer.created_at,
        updated_at=printer.updated_at,
    )


@router.post("", response_model=PrinterResponse, status_code=status.HTTP_201_CREATED)
async def create_printer(
    payload: PrinterCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PrinterResponse:
    try:
        printer = await printers_service.create(
            session,
            name=payload.name,
            slug=payload.slug,
            printer_type=payload.printer_type,
            moonraker_url=payload.moonraker_url,
            moonraker_api_key=payload.moonraker_api_key,
            power_draw_watts=payload.power_draw_watts,
            purchase_price=payload.purchase_price,
            salvage_value=payload.salvage_value,
            lifespan_years=payload.lifespan_years,
            annual_print_hours=payload.annual_print_hours,
            preheat_minutes=payload.preheat_minutes,
            preheat_power_watts=payload.preheat_power_watts,
            notes=payload.notes,
            actor_user_id=actor.id,
        )
    except printers_service.DuplicatePrinterError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except printers_service.PrintersServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await _refresh_for_response(session, printer)
    await session.commit()
    return _to_response(printer)


@router.get("", response_model=PrinterListResponse)
async def list_printers(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    is_archived: Annotated[bool | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PrinterListResponse:
    try:
        page = await printers_service.list_printers(
            session, is_archived=is_archived, cursor=cursor, limit=limit
        )
    except printers_service.InvalidCursorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return PrinterListResponse(
        items=[_to_response(p) for p in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{printer_id}", response_model=PrinterResponse)
async def get_printer(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> PrinterResponse:
    try:
        printer = await printers_service.get(session, printer_id)
    except printers_service.PrinterNotFoundError:
        raise HTTPException(status_code=404, detail="printer not found") from None
    return _to_response(printer)


@router.patch("/{printer_id}", response_model=PrinterResponse)
async def update_printer(
    printer_id: uuid.UUID,
    payload: PrinterUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PrinterResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        printer = await printers_service.update(
            session, printer_id=printer_id, patch=patch, actor_user_id=actor.id
        )
    except printers_service.PrinterNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="printer not found") from None
    except printers_service.DuplicatePrinterError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except printers_service.PrintersServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await _refresh_for_response(session, printer)
    await session.commit()
    return _to_response(printer)


@router.post("/{printer_id}/archive", response_model=PrinterResponse)
async def archive_printer(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> PrinterResponse:
    try:
        printer = await printers_service.archive(
            session, printer_id=printer_id, actor_user_id=actor.id
        )
    except printers_service.PrinterNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="printer not found") from None
    await _refresh_for_response(session, printer)
    await session.commit()
    return _to_response(printer)


@router.post("/{printer_id}/unarchive", response_model=PrinterResponse)
async def unarchive_printer(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> PrinterResponse:
    try:
        printer = await printers_service.unarchive(
            session, printer_id=printer_id, actor_user_id=actor.id
        )
    except printers_service.PrinterNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="printer not found") from None
    except printers_service.DuplicatePrinterError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await _refresh_for_response(session, printer)
    await session.commit()
    return _to_response(printer)
