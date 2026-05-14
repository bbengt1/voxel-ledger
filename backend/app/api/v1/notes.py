"""Notes endpoints (Phase 2.6).

Polymorphic notes attached to catalog entities. All authenticated users
can read; non-viewer can write; pin/unpin is owner-only; update/delete
is author OR owner (enforced at the service layer).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.note import Note
from app.schemas.notes import (
    ALLOWED_ENTITY_KINDS,
    NoteCreateRequest,
    NoteListResponse,
    NoteResponse,
    NoteUpdateRequest,
)
from app.services import notes as notes_service

router = APIRouter(prefix="/notes", tags=["notes"])


def _check_entity_kind(entity_kind: str) -> None:
    if entity_kind not in ALLOWED_ENTITY_KINDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported entity_kind {entity_kind!r}",
        )


def _to_response(note: Note) -> NoteResponse:
    return NoteResponse(
        id=note.id,
        entity_kind=note.entity_kind,
        entity_id=note.entity_id,
        body=note.body,
        author_user_id=note.author_user_id,
        is_pinned=note.is_pinned,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


async def _refresh(session: AsyncSession, note: Note) -> None:
    await session.refresh(note, ["created_at", "updated_at"])


@router.get("", response_model=NoteListResponse)
async def list_notes(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
    entity_kind: Annotated[str, Query()],
    entity_id: Annotated[uuid.UUID, Query()],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> NoteListResponse:
    _check_entity_kind(entity_kind)
    try:
        page = await notes_service.list_for(
            session,
            entity_kind=entity_kind,
            entity_id=entity_id,
            cursor=cursor,
            limit=limit,
        )
    except notes_service.InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    return NoteListResponse(
        items=[_to_response(n) for n in page.items],
        next_cursor=page.next_cursor,
    )


@router.post("", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
async def create_note(
    payload: NoteCreateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[
        User,
        Depends(require_role("owner", "production", "bookkeeper", "sales")),
    ],
) -> NoteResponse:
    _check_entity_kind(payload.entity_kind)
    try:
        note = await notes_service.create(
            session,
            entity_kind=payload.entity_kind,
            entity_id=payload.entity_id,
            body=payload.body,
            author=actor,
        )
    except notes_service.NotesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, note)
    await session.commit()
    return _to_response(note)


@router.patch("/{note_id}", response_model=NoteResponse)
async def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> NoteResponse:
    try:
        note = await notes_service.update(session, note_id=note_id, body=payload.body, actor=actor)
    except notes_service.NoteNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from None
    except notes_service.NotePermissionError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    except notes_service.NotesServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    await _refresh(session, note)
    await session.commit()
    return _to_response(note)


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_note(
    note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(get_current_user)],
) -> None:
    try:
        await notes_service.delete(session, note_id=note_id, actor=actor)
    except notes_service.NoteNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from None
    except notes_service.NotePermissionError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    await session.commit()


@router.post("/{note_id}/pin", response_model=NoteResponse)
async def pin_note(
    note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> NoteResponse:
    try:
        note = await notes_service.pin(session, note_id=note_id, actor=actor)
    except notes_service.NoteNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from None
    except notes_service.NotePermissionError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    await _refresh(session, note)
    await session.commit()
    return _to_response(note)


@router.post("/{note_id}/unpin", response_model=NoteResponse)
async def unpin_note(
    note_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner"))],
) -> NoteResponse:
    try:
        note = await notes_service.unpin(session, note_id=note_id, actor=actor)
    except notes_service.NoteNotFoundError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="note not found"
        ) from None
    except notes_service.NotePermissionError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from None
    await _refresh(session, note)
    await session.commit()
    return _to_response(note)
