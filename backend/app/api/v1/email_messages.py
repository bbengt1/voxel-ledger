"""Email-messages API (Phase 7.7, #115).

Read endpoints plus operator retry / cancel and the manual statement
send. Auth: owner + bookkeeper only.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.email_message import EmailKind, EmailMessage, EmailState
from app.schemas.email_messages import (
    EmailMessageListResponse,
    EmailMessageResponse,
    SendStatementRequest,
)
from app.services import email as email_service
from app.services import files as file_storage
from app.services.email.renderers import statement as statement_renderer
from app.services.settings.service import SettingsService

router = APIRouter(prefix="/email-messages", tags=["email-messages"])
statements_router = APIRouter(prefix="/customers", tags=["customers", "statements"])

_READ_ROLES = ("owner", "bookkeeper")
_WRITE_ROLES = ("owner", "bookkeeper")
_STATEMENT_ROLES = ("owner", "bookkeeper", "sales")


def _to_response(row: EmailMessage) -> EmailMessageResponse:
    return EmailMessageResponse(
        id=row.id,
        kind=row.kind.value if hasattr(row.kind, "value") else str(row.kind),  # type: ignore[arg-type]
        subject_kind=row.subject_kind,
        subject_id=row.subject_id,
        to_address=row.to_address,
        from_address=row.from_address,
        subject=row.subject,
        body_html_storage_key=row.body_html_storage_key,
        attachments_json=row.attachments_json,  # type: ignore[arg-type]
        state=row.state.value if hasattr(row.state, "value") else str(row.state),  # type: ignore[arg-type]
        attempts=row.attempts,
        next_retry_at=row.next_retry_at,
        last_error=row.last_error,
        provider_message_id=row.provider_message_id,
        sent_at=row.sent_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=EmailMessageListResponse)
async def list_email_messages(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
    kind: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    subject_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> EmailMessageListResponse:
    stmt = select(EmailMessage).order_by(EmailMessage.created_at.desc())
    if kind is not None:
        try:
            stmt = stmt.where(EmailMessage.kind == EmailKind(kind))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid kind: {kind!r}") from exc
    if state is not None:
        try:
            stmt = stmt.where(EmailMessage.state == EmailState(state))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid state: {state!r}") from exc
    if subject_id is not None:
        stmt = stmt.where(EmailMessage.subject_id == subject_id)
    stmt = stmt.limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return EmailMessageListResponse(items=[_to_response(r) for r in rows])


@router.get("/{email_id}", response_model=EmailMessageResponse)
async def get_email_message(
    email_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> EmailMessageResponse:
    row = (
        await session.execute(select(EmailMessage).where(EmailMessage.id == email_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="email_message not found")
    return _to_response(row)


@router.get("/{email_id}/body")
async def get_email_body(
    email_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role(*_READ_ROLES))],
) -> Response:
    row = (
        await session.execute(select(EmailMessage).where(EmailMessage.id == email_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="email_message not found")
    raw_root = await SettingsService.get("email.storage_root", session=session)
    root = Path(str(raw_root))
    blob = file_storage.read_blob(row.body_html_storage_key, root=root)
    if blob is None:
        raise HTTPException(status_code=404, detail="email body blob missing")
    return Response(content=blob, media_type="text/html")


@router.post("/{email_id}/retry", response_model=EmailMessageResponse)
async def retry_email_message(
    email_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> EmailMessageResponse:
    try:
        row = await email_service.retry(email_id, session=session, actor_user_id=actor.id)
    except email_service.EmailMessageNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except email_service.EmailServiceError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await session.commit()
    return _to_response(row)


@router.post("/{email_id}/cancel", response_model=EmailMessageResponse)
async def cancel_email_message(
    email_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_WRITE_ROLES))],
) -> EmailMessageResponse:
    try:
        row = await email_service.cancel(email_id, session=session, actor_user_id=actor.id)
    except email_service.EmailMessageNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except email_service.InvalidEmailStateError as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await session.commit()
    return _to_response(row)


# ---------------------------------------------------------------------------
# Manual statement send (mounted under /customers)
# ---------------------------------------------------------------------------


@statements_router.post(
    "/{customer_id}/statements/send",
    response_model=EmailMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_statement(
    customer_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role(*_STATEMENT_ROLES))],
    payload: SendStatementRequest | None = None,
    include_paid: Annotated[bool, Query()] = False,
) -> EmailMessageResponse:
    from app.models.customer import Customer

    customer = (
        await session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(status_code=404, detail="customer not found")
    if not customer.primary_email:
        raise HTTPException(
            status_code=400,
            detail="customer has no primary_email — set one before sending a statement",
        )
    flag = (payload.include_paid if payload else include_paid) or include_paid

    try:
        rendered = await statement_renderer.render(customer_id, session=session, include_paid=flag)
        # Statements are NOT idempotency-guarded: each manual send is a new
        # row. We pass subject_id=None so the unique partial index doesn't
        # see them.
        row = await email_service.enqueue_email(
            EmailKind.STATEMENT,
            subject_kind="customer",
            subject_id=None,
            to_address=customer.primary_email,
            subject=rendered.subject,
            body_html=rendered.body_html,
            body_text=rendered.body_text,
            attachments=rendered.attachments,
            session=session,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from None
    await session.commit()
    if row is None:  # pragma: no cover — subject_id=None bypasses dedup
        raise HTTPException(status_code=500, detail="failed to enqueue statement")
    return _to_response(row)
