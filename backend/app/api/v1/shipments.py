"""Shipments API (Phase 6.6, #98).

Thin layer over ``app.services.shipping``. Two routers ship in this
module so the URL surface can split cleanly:

* ``sales_shipments_router`` — mounts the nested
  ``/sales/{sale_id}/shipments`` create endpoint.
* ``router`` — mounts the flat ``/shipments/{id}/*`` endpoints
  (state transitions, label download).

Both are included by ``app.api.v1.router``.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.shipment import Shipment, ShipmentState
from app.schemas.shipments import (
    ShipmentCreate,
    ShipmentResponse,
    ShipmentTransitionRequest,
)
from app.services import shipping as shipping_service

router = APIRouter(prefix="/shipments", tags=["shipments"])
sales_shipments_router = APIRouter(prefix="/sales", tags=["shipments"])


def _to_response(shipment: Shipment) -> ShipmentResponse:
    state_value = (
        shipment.state.value if isinstance(shipment.state, ShipmentState) else shipment.state
    )
    return ShipmentResponse(
        id=shipment.id,
        sale_id=shipment.sale_id,
        state=state_value,  # type: ignore[arg-type]
        carrier=shipment.carrier,
        service_level=shipment.service_level,
        tracking_number=shipment.tracking_number,
        tracking_url=shipment.tracking_url,
        label_pdf_storage_key=shipment.label_pdf_storage_key,
        cost_amount=shipment.cost_amount,
        weight_grams=shipment.weight_grams,
        dimensions_cm=shipment.dimensions_cm,
        ship_from=shipment.ship_from,
        ship_to=shipment.ship_to,
        created_at=shipment.created_at,
        updated_at=shipment.updated_at,
    )


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, shipping_service.ShipmentNotFoundError):
        return HTTPException(status_code=404, detail="shipment not found")
    if isinstance(exc, shipping_service.LabelNotAvailableError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, shipping_service.InvalidShipmentStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, shipping_service.ShippingServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Create (nested under /sales/{sale_id}/shipments)
# ---------------------------------------------------------------------------


@sales_shipments_router.post(
    "/{sale_id}/shipments",
    response_model=ShipmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shipment(
    sale_id: uuid.UUID,
    payload: ShipmentCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
) -> ShipmentResponse:
    try:
        shipment = await shipping_service.create_shipment(
            sale_id,
            ship_to=payload.ship_to,
            weight_grams=payload.weight_grams,
            dimensions_cm=payload.dimensions_cm,
            service_level=payload.service_level,
            carrier_hint=payload.carrier_hint,
            session=session,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(shipment)


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


@router.get("/{shipment_id}", response_model=ShipmentResponse)
async def get_shipment(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper", "viewer"))],
) -> ShipmentResponse:
    try:
        shipment = await shipping_service.get(session, shipment_id)
    except Exception as exc:
        raise _map_error(exc) from None
    return _to_response(shipment)


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


@router.post("/{shipment_id}/purchase-label", response_model=ShipmentResponse)
async def purchase_label(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
    _payload: ShipmentTransitionRequest | None = None,
) -> ShipmentResponse:
    try:
        shipment = await shipping_service.purchase_label(
            shipment_id, session=session, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(shipment)


@router.post("/{shipment_id}/mark-shipped", response_model=ShipmentResponse)
async def mark_shipped(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
    _payload: ShipmentTransitionRequest | None = None,
) -> ShipmentResponse:
    try:
        shipment = await shipping_service.mark_shipped(
            shipment_id, session=session, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(shipment)


@router.post("/{shipment_id}/mark-delivered", response_model=ShipmentResponse)
async def mark_delivered(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
    _payload: ShipmentTransitionRequest | None = None,
) -> ShipmentResponse:
    try:
        shipment = await shipping_service.mark_delivered(
            shipment_id, session=session, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(shipment)


@router.post("/{shipment_id}/cancel", response_model=ShipmentResponse)
async def cancel_shipment(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
    _payload: ShipmentTransitionRequest | None = None,
) -> ShipmentResponse:
    try:
        shipment = await shipping_service.cancel(
            shipment_id, session=session, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_error(exc) from None
    await session.commit()
    return _to_response(shipment)


# ---------------------------------------------------------------------------
# Label PDF stream
# ---------------------------------------------------------------------------


@router.get("/{shipment_id}/label.pdf")
async def download_label(
    shipment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "sales", "bookkeeper"))],
) -> Response:
    """Stream the rendered label PDF.

    Local-FS backend today returns the bytes directly. Once the S3
    backend lands, this handler will issue a signed URL redirect
    instead — the caller-facing contract stays a single GET that
    delivers the PDF.
    """
    try:
        pdf_bytes = await shipping_service.load_label_pdf(shipment_id, session=session)
    except Exception as exc:
        raise _map_error(exc) from None
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="label-{shipment_id}.pdf"',
        },
    )


__all__ = ["router", "sales_shipments_router"]
