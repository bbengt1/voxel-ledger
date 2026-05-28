"""Inbound webhook endpoints (Phase 11.2, #194).

These routes are NOT JWT-gated -- they're called by external providers.
Auth IS the per-provider signature verification handled inside the
service layer. A bad signature returns 401 before any DB write.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.services.webhooks import inbound as inbound_service

router = APIRouter(prefix="/webhooks/inbound", tags=["webhooks"])


def _response_for(result: inbound_service.IntakeResult) -> dict[str, Any]:
    ev = result.event
    return {
        "id": str(ev.id),
        "status": "duplicate" if result.is_duplicate else ev.status.value,
        "kind": ev.kind.value,
        "provider": ev.provider,
        "external_event_id": ev.external_event_id,
    }


@router.post("/carriers/{provider}", status_code=status.HTTP_200_OK)
async def inbound_carrier(
    provider: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    body = await request.body()
    headers = dict(request.headers)
    try:
        result = await inbound_service.intake_carrier(
            session=session, provider=provider, body=body, headers=headers
        )
    except inbound_service.UnknownProviderError:
        raise HTTPException(status_code=404, detail="unknown carrier provider") from None
    except (
        inbound_service.InvalidSignatureError,
        inbound_service.MissingSecretError,
    ) as exc:
        await session.rollback()
        raise HTTPException(status_code=401, detail=str(exc)) from None
    except json.JSONDecodeError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid JSON body") from None
    response = _response_for(result)
    await session.commit()
    return response


@router.post("/marketplaces/{provider}", status_code=status.HTTP_200_OK)
async def inbound_marketplace(
    provider: str,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, Any]:
    body = await request.body()
    headers = dict(request.headers)
    try:
        result = await inbound_service.intake_marketplace(
            session=session, provider=provider, body=body, headers=headers
        )
    except inbound_service.UnknownProviderError:
        raise HTTPException(status_code=404, detail="unknown marketplace provider") from None
    except (
        inbound_service.InvalidSignatureError,
        inbound_service.MissingSecretError,
    ) as exc:
        await session.rollback()
        raise HTTPException(status_code=401, detail=str(exc)) from None
    except json.JSONDecodeError:
        await session.rollback()
        raise HTTPException(status_code=400, detail="invalid JSON body") from None
    response = _response_for(result)
    await session.commit()
    return response
