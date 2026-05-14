"""Attachments endpoints (Phase 2.6).

Multipart upload, list, download stream, and soft-delete (archive).
The actual filesystem work lives in ``app.services.attachments``.
"""

from __future__ import annotations

import io
import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.attachment import Attachment
from app.models.auth import User
from app.schemas.attachments import AttachmentListResponse, AttachmentResponse
from app.schemas.notes import ALLOWED_ENTITY_KINDS
from app.services import attachments as attachments_service
from app.services.attachments.service import UploadedFile

router = APIRouter(prefix="/attachments", tags=["attachments"])


def _check_entity_kind(entity_kind: str) -> None:
    if entity_kind not in ALLOWED_ENTITY_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported entity_kind {entity_kind!r}",
        )


def _to_response(a: Attachment) -> AttachmentResponse:
    return AttachmentResponse(
        id=a.id,
        entity_kind=a.entity_kind,
        entity_id=a.entity_id,
        filename=a.filename,
        mime_type=a.mime_type,
        byte_size=a.byte_size,
        uploaded_by_user_id=a.uploaded_by_user_id,
        is_archived=a.is_archived,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


async def _refresh(session: AsyncSession, attachment: Attachment) -> None:
    await session.refresh(attachment, ["created_at", "updated_at"])


@router.post(
    "",
    response_model=AttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[
        User,
        Depends(require_role("owner", "production", "bookkeeper", "sales")),
    ],
    entity_kind: Annotated[str, Form()],
    entity_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File()],
) -> AttachmentResponse:
    _check_entity_kind(entity_kind)
    content = await file.read()
    # Pre-check size before handing off to the service so we can bail
    # without touching disk.
    if len(content) > attachments_service.MAX_BYTE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"file too large (max {attachments_service.MAX_BYTE_SIZE} bytes)",
        )
    try:
        attachment = await attachments_service.upload(
            session,
            entity_kind=entity_kind,
            entity_id=entity_id,
            file=UploadedFile(
                filename=file.filename or "upload.bin",
                mime_type=file.content_type or "application/octet-stream",
                content=content,
            ),
            actor=actor,
        )
    except attachments_service.InvalidMimeTypeError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from None
    except attachments_service.OversizeAttachmentError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from None
    except attachments_service.AttachmentsServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, attachment)
    await session.commit()
    return _to_response(attachment)


@router.get("", response_model=AttachmentListResponse)
async def list_attachments(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_kind: Annotated[str, Query()],
    entity_id: Annotated[uuid.UUID, Query()],
    include_archived: Annotated[bool, Query()] = False,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AttachmentListResponse:
    _check_entity_kind(entity_kind)
    try:
        page = await attachments_service.list_for(
            session,
            entity_kind=entity_kind,
            entity_id=entity_id,
            include_archived=include_archived,
            cursor=cursor,
            limit=limit,
        )
    except attachments_service.InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return AttachmentListResponse(
        items=[_to_response(a) for a in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> StreamingResponse:
    try:
        payload = await attachments_service.download(session, attachment_id)
    except attachments_service.AttachmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found"
        ) from None
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attachment file missing on disk",
        ) from None

    # Quote the filename for safety in headers.
    safe_name = payload.filename.replace('"', "")
    headers = {
        "Content-Disposition": f'attachment; filename="{safe_name}"',
        "Content-Length": str(len(payload.content)),
    }
    return StreamingResponse(
        io.BytesIO(payload.content),
        media_type=payload.mime_type,
        headers=headers,
    )


@router.post("/{attachment_id}/archive", response_model=AttachmentResponse)
async def archive_attachment(
    attachment_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> AttachmentResponse:
    try:
        attachment = await attachments_service.archive(
            session, attachment_id=attachment_id, actor=actor
        )
    except attachments_service.AttachmentNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="attachment not found"
        ) from None
    except attachments_service.AttachmentPermissionError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    await _refresh(session, attachment)
    await session.commit()
    return _to_response(attachment)
