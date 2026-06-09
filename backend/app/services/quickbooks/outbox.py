"""QBO sync outbox: enqueue + drain (#316, epic #312).

* :func:`enqueue` is called by posting sites (Phases 3b-3d) **inside the
  business transaction** so the outbox row and the operation commit together.
* :func:`run_pending` is the worker drain: builds + pushes each due row, with
  exponential backoff + jitter on transient errors and dead-letter past the
  retry window. No-ops unless ``quickbooks.enabled`` and a credential exists.

Idempotency: each row gets a stable ``request_id`` at enqueue, reused on every
retry (Phase-0 canonical key), so retried pushes never duplicate in QBO.
"""

from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.quickbooks import builders, oauth
from app.services.quickbooks.client import QuickBooksApiError, QuickBooksClient
from app.services.settings.service import SettingsService
from app.services.webhooks.dispatcher import backoff_for_attempt

log = logging.getLogger(__name__)

# Give up (dead-letter) once a transient failure keeps recurring past this window.
MAX_TOTAL_RETRY_SECONDS = 24 * 3600
_DRAIN_LIMIT = 50


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def is_enabled(session: AsyncSession) -> bool:
    return bool(await SettingsService.get("quickbooks.enabled", session=session))


async def enqueue(
    session: AsyncSession,
    *,
    kind: str,
    local_id: uuid.UUID,
    payload: dict[str, Any],
    op: str = "post",
    request_id: str | None = None,
) -> QboSyncOutbox:
    """Add a pending outbox row in the caller's transaction. Caller commits."""
    row = QboSyncOutbox(
        kind=kind,
        local_id=local_id,
        op=op,
        payload=payload,
        request_id=request_id or uuid.uuid4().hex,
        status=QboSyncStatus.PENDING.value,
        next_attempt_at=datetime.now(UTC),
    )
    session.add(row)
    await session.flush()
    return row


@dataclass
class RunResult:
    synced: int = 0
    retried: int = 0
    failed: int = 0
    dead: int = 0
    skipped: bool = False


async def run_pending(
    session: AsyncSession,
    settings: Settings,
    *,
    client: Any | None = None,
    now: datetime | None = None,
    rng: random.Random | None = None,
    limit: int = _DRAIN_LIMIT,
) -> RunResult:
    """Drain due outbox rows. Skips entirely unless enabled + connected."""
    now = now or datetime.now(UTC)
    if not await is_enabled(session):
        return RunResult(skipped=True)
    if await oauth.get_credential(session) is None:
        return RunResult(skipped=True)

    if client is None:
        client = QuickBooksClient(session, settings)

    rows = (
        (
            await session.execute(
                select(QboSyncOutbox)
                .where(QboSyncOutbox.status == QboSyncStatus.PENDING.value)
                .where(QboSyncOutbox.next_attempt_at <= now)
                .order_by(QboSyncOutbox.next_attempt_at.asc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    result = RunResult()
    for row in rows:
        row.attempts += 1
        try:
            entity_type, qbo_obj = await builders.build_and_push(session, client, row)
        except builders.BuilderError as exc:
            row.status = QboSyncStatus.FAILED.value  # permanent — needs a fix + manual retry
            row.last_error = str(exc)[:1000]
            result.failed += 1
        except builders.DependencyNotReadyError as exc:
            row.last_error = str(exc)[:1000]
            _retry_or_dead(row, now=now, rng=rng, result=result)
        except QuickBooksApiError as exc:
            row.last_error = str(exc)[:1000]
            permanent = 400 <= exc.status_code < 500 and exc.status_code != 429
            if permanent:
                row.status = QboSyncStatus.FAILED.value
                result.failed += 1
            else:
                _retry_or_dead(row, now=now, rng=rng, result=result)
        except Exception as exc:
            log.exception("quickbooks_sync.row_failed", extra={"outbox_id": str(row.id)})
            row.status = QboSyncStatus.FAILED.value
            row.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            result.failed += 1
        else:
            row.status = QboSyncStatus.SYNCED.value
            row.qbo_entity_type = entity_type
            row.qbo_id = str(qbo_obj.get("Id")) if qbo_obj.get("Id") else None
            row.last_error = None
            result.synced += 1
        await session.commit()

    return result


def _retry_or_dead(
    row: QboSyncOutbox, *, now: datetime, rng: random.Random | None, result: RunResult
) -> None:
    """Reschedule a transiently-failed row, or dead-letter it past the window."""
    if (now - _as_utc(row.created_at)).total_seconds() > MAX_TOTAL_RETRY_SECONDS:
        row.status = QboSyncStatus.DEAD.value
        result.dead += 1
    else:
        row.status = QboSyncStatus.PENDING.value
        row.next_attempt_at = now + timedelta(seconds=backoff_for_attempt(row.attempts, rng=rng))
        result.retried += 1
