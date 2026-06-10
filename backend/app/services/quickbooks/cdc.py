"""QBO change-data-capture (CDC) drift polling (#317, epic #312, Phase 4a).

QBO is the system of record. After Phase 3, postings flow out through the sync
outbox and land a ``qbo_id`` when ``synced``. This module polls QBO's CDC feed —
``GET /v3/company/{realm}/cdc?entities=…&changedSince=…`` — to detect *external*
edits/deletes to those entities (someone changing a synced doc directly in
QuickBooks). Such a change is **drift**: our record and QBO have diverged.

We never silently re-push (QBO is authoritative); drift is recorded in
``qbo_cdc_drift`` for admin review and folded into the Phase-4b reconciliation
gate. A new push of ours echoes back through CDC as a "change", so an *update*
only counts as drift when QBO's ``LastUpdatedTime`` is meaningfully newer than
when we marked the row synced; *deletes* always count.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings
from app.models.qbo_cdc_drift import QboCdcDrift, QboDriftStatus
from app.models.qbo_sync_outbox import QboSyncOutbox, QboSyncStatus
from app.services.quickbooks import oauth
from app.services.quickbooks.client import QuickBooksClient
from app.services.settings.service import SettingsService

log = logging.getLogger(__name__)

# QBO entity types we push (and therefore watch for drift). Master data
# (Customer/Vendor/Item) is excluded — its drift isn't accounting-material.
CDC_ENTITIES: tuple[str, ...] = (
    "Invoice",
    "SalesReceipt",
    "Payment",
    "Bill",
    "BillPayment",
    "CreditMemo",
    "JournalEntry",
)

_CURSOR_KEY = "quickbooks.cdc_cursor"
# QBO's CDC window is 30 days; default the first poll to a 30-day lookback.
_LOOKBACK_DAYS = 30
# An update within this many seconds of our own sync is treated as our echo,
# not external drift.
_ECHO_SKEW_SECONDS = 5
# Non-entity keys QBO mixes into each QueryResponse bucket.
_META_KEYS = frozenset({"startPosition", "maxResults", "totalCount"})


@dataclass
class CdcResult:
    scanned: int = 0  # CDC objects returned across all entities
    matched: int = 0  # objects matching a synced outbox row (ours)
    drift_new: int = 0  # newly recorded drift rows
    drift_updated: int = 0  # existing drift rows refreshed
    skipped: bool = False  # disabled / not connected


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _parse_qbo_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        # QBO emits ISO-8601 with offset, e.g. 2026-06-10T05:00:00-07:00.
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _iter_cdc_objects(body: dict[str, Any]):
    """Yield ``(entity_type, change_type, qbo_id, last_updated, obj)`` tuples
    from a raw CDC response. ``change_type`` is "deleted" or "updated"."""
    for response in body.get("CDCResponse", []) or []:
        for bucket in response.get("QueryResponse", []) or []:
            for key, value in bucket.items():
                if key in _META_KEYS or not isinstance(value, list):
                    continue
                entity_type = key
                for obj in value:
                    qbo_id = obj.get("Id")
                    if not qbo_id:
                        continue
                    deleted = str(obj.get("status", "")).lower() == "deleted"
                    change_type = "deleted" if deleted else "updated"
                    last_updated = _parse_qbo_time(
                        (obj.get("Metadata") or {}).get("LastUpdatedTime")
                    )
                    yield entity_type, change_type, str(qbo_id), last_updated, obj


async def _synced_index(
    session: AsyncSession, pairs: set[tuple[str, str]]
) -> dict[tuple[str, str], QboSyncOutbox]:
    """Map ``(entity_type, qbo_id)`` → the synced outbox row that produced it."""
    if not pairs:
        return {}
    qbo_ids = {qbo_id for _, qbo_id in pairs}
    rows = (
        (
            await session.execute(
                select(QboSyncOutbox)
                .where(QboSyncOutbox.status == QboSyncStatus.SYNCED.value)
                .where(QboSyncOutbox.qbo_id.in_(qbo_ids))
            )
        )
        .scalars()
        .all()
    )
    index: dict[tuple[str, str], QboSyncOutbox] = {}
    for row in rows:
        if row.qbo_entity_type and row.qbo_id:
            index[(row.qbo_entity_type, row.qbo_id)] = row
    return index


async def _record_drift(
    session: AsyncSession,
    *,
    entity_type: str,
    qbo_id: str,
    change_type: str,
    outbox_row: QboSyncOutbox,
    obj: dict[str, Any],
    now: datetime,
    result: CdcResult,
) -> None:
    """Upsert a drift row keyed by (entity_type, qbo_id)."""
    existing = (
        await session.execute(
            select(QboCdcDrift)
            .where(QboCdcDrift.entity_type == entity_type)
            .where(QboCdcDrift.qbo_id == qbo_id)
        )
    ).scalar_one_or_none()
    detail = {
        "change_type": change_type,
        "qbo_last_updated": (obj.get("Metadata") or {}).get("LastUpdatedTime"),
        "synced_at": outbox_row.updated_at.isoformat() if outbox_row.updated_at else None,
    }
    if existing is None:
        session.add(
            QboCdcDrift(
                entity_type=entity_type,
                qbo_id=qbo_id,
                change_type=change_type,
                local_kind=outbox_row.kind,
                local_id=outbox_row.local_id,
                occurrences=1,
                status=QboDriftStatus.OPEN.value,
                detail=detail,
                first_detected_at=now,
                last_detected_at=now,
            )
        )
        result.drift_new += 1
    else:
        existing.change_type = change_type
        existing.local_kind = outbox_row.kind
        existing.local_id = outbox_row.local_id
        existing.occurrences += 1
        existing.detail = detail
        existing.last_detected_at = now
        # A newer external change re-opens a row the operator had acknowledged.
        existing.status = QboDriftStatus.OPEN.value
        result.drift_updated += 1


async def poll(
    session: AsyncSession,
    settings: Settings,
    *,
    client: Any | None = None,
    now: datetime | None = None,
) -> CdcResult:
    """Poll QBO CDC since the stored cursor; record drift; advance the cursor.

    No-ops unless ``quickbooks.enabled`` and a credential exists. Caller need not
    commit — this commits the cursor + drift rows itself."""
    now = now or datetime.now(UTC)
    if not bool(await SettingsService.get("quickbooks.enabled", session=session)):
        return CdcResult(skipped=True)
    if await oauth.get_credential(session) is None:
        return CdcResult(skipped=True)

    if client is None:
        client = QuickBooksClient(session, settings)

    cursor = await SettingsService.get(_CURSOR_KEY, session=session)
    changed_since = cursor or (now - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y-%m-%dT%H:%M:%S%z")

    body = await client._request(
        "GET",
        "cdc",
        params={"entities": ",".join(CDC_ENTITIES), "changedSince": changed_since},
    )

    objects = list(_iter_cdc_objects(body))
    result = CdcResult(scanned=len(objects))
    pairs = {(etype, qid) for etype, _ct, qid, _lu, _obj in objects}
    index = await _synced_index(session, pairs)

    for entity_type, change_type, qbo_id, last_updated, obj in objects:
        outbox_row = index.get((entity_type, qbo_id))
        if outbox_row is None:
            continue  # not an entity we synced — ignore
        result.matched += 1
        if change_type == "updated":
            synced_at = _as_utc(outbox_row.updated_at) if outbox_row.updated_at else None
            # Skip our own write echoing back through CDC.
            if (
                last_updated is not None
                and synced_at is not None
                and last_updated <= synced_at + timedelta(seconds=_ECHO_SKEW_SECONDS)
            ):
                continue
        await _record_drift(
            session,
            entity_type=entity_type,
            qbo_id=qbo_id,
            change_type=change_type,
            outbox_row=outbox_row,
            obj=obj,
            now=now,
            result=result,
        )

    # Advance the cursor to this poll's start so the next poll only sees newer
    # changes. Stored as ISO-8601 UTC with offset (what QBO's changedSince wants).
    await SettingsService.set(
        _CURSOR_KEY,
        now.strftime("%Y-%m-%dT%H:%M:%S%z") or now.isoformat(),
        session=session,
        actor_user_id=None,
    )
    await session.commit()
    return result


async def open_drift_count(session: AsyncSession) -> int:
    """Count drift rows still awaiting operator review (for monitoring/gates)."""
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(QboCdcDrift)
                .where(QboCdcDrift.status == QboDriftStatus.OPEN.value)
            )
        ).scalar_one()
    )


# --------------------------------------------------------------------------- #
# Admin drift surface (#317 Phase 4b/4c) — list + acknowledge.
# --------------------------------------------------------------------------- #


class DriftNotFoundError(LookupError):
    """No drift row with the given id."""


async def list_drift(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 100,
    before: datetime | None = None,
) -> list[QboCdcDrift]:
    """Most-recently-detected-first page of drift rows, optionally filtered by
    status. ``before`` is a keyset cursor on ``last_detected_at``."""
    stmt = select(QboCdcDrift)
    if status is not None:
        stmt = stmt.where(QboCdcDrift.status == status)
    if before is not None:
        stmt = stmt.where(QboCdcDrift.last_detected_at < before)
    stmt = stmt.order_by(QboCdcDrift.last_detected_at.desc(), QboCdcDrift.id.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def acknowledge_drift(
    session: AsyncSession, drift_id: uuid.UUID, *, actor_user_id: uuid.UUID | None
) -> QboCdcDrift:
    """Mark a drift row reviewed. A later external change re-opens it (the CDC
    poll resets ``status`` to ``open``). Caller commits."""
    row = await session.get(QboCdcDrift, drift_id)
    if row is None:
        raise DriftNotFoundError(str(drift_id))
    row.status = QboDriftStatus.ACKNOWLEDGED.value
    row.acknowledged_at = datetime.now(UTC)
    row.acknowledged_by_user_id = actor_user_id
    await session.flush()
    await session.refresh(row)
    return row
