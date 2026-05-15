"""Cameras endpoints (Phase 5.1).

Cameras are 1:1 children of a printer; the surface lives under
``/printers/{id}/cameras``. POST is idempotent set-or-replace.

The snapshot proxy returns ``image/jpeg`` with a short cache window
that matches the in-process cache TTL (``max-age=2, must-revalidate``).
Only ``go2rtc`` is implemented in v1; other kinds return 501.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.camera import Camera
from app.schemas.cameras import CameraConfigRequest, CameraResponse
from app.services import cameras as cameras_service

router = APIRouter(prefix="/printers", tags=["cameras"])


def _to_response(camera: Camera) -> CameraResponse:
    return CameraResponse(
        id=camera.id,
        printer_id=camera.printer_id,
        kind=camera.kind.value,  # type: ignore[arg-type]
        snapshot_url=camera.snapshot_url,
        username=camera.username,
        password_secret_set=camera.password_secret is not None,
        is_active=camera.is_active,
        created_at=camera.created_at,
        updated_at=camera.updated_at,
    )


@router.post(
    "/{printer_id}/cameras",
    response_model=CameraResponse,
    status_code=status.HTTP_200_OK,
)
async def upsert_camera(
    printer_id: uuid.UUID,
    payload: CameraConfigRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> CameraResponse:
    try:
        camera = await cameras_service.upsert(
            session,
            printer_id=printer_id,
            kind=payload.kind,
            snapshot_url=payload.snapshot_url,
            username=payload.username,
            password_secret=payload.password_secret,
            is_active=payload.is_active,
            actor_user_id=actor.id,
        )
    except cameras_service.PrinterNotFoundForCameraError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="printer not found") from None
    except cameras_service.CamerasServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await session.refresh(camera, ["created_at", "updated_at"])
    await session.commit()
    return _to_response(camera)


@router.get("/{printer_id}/cameras", response_model=CameraResponse)
async def get_camera(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> CameraResponse:
    try:
        camera = await cameras_service.get_for_printer(session, printer_id)
    except cameras_service.CameraNotFoundError:
        raise HTTPException(status_code=404, detail="camera not configured") from None
    return _to_response(camera)


@router.delete("/{printer_id}/cameras", status_code=status.HTTP_204_NO_CONTENT)
async def delete_camera(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> Response:
    try:
        await cameras_service.delete_for_printer(
            session, printer_id=printer_id, actor_user_id=actor.id
        )
    except cameras_service.CameraNotFoundError:
        await session.rollback()
        raise HTTPException(status_code=404, detail="camera not configured") from None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{printer_id}/cameras/snapshot.jpg",
    responses={
        200: {"content": {"image/jpeg": {}}},
        501: {"description": "snapshot kind not implemented"},
        502: {"description": "upstream snapshot fetch failed"},
    },
    response_class=Response,
)
async def get_camera_snapshot(
    printer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> Response:
    try:
        camera = await cameras_service.get_for_printer(session, printer_id)
    except cameras_service.CameraNotFoundError:
        raise HTTPException(status_code=404, detail="camera not configured") from None
    try:
        body = await cameras_service.fetch_snapshot(camera.id, session=session)
    except cameras_service.UnsupportedCameraKindError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from None
    except cameras_service.CameraUpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from None
    return Response(
        content=body,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=2, must-revalidate"},
    )
