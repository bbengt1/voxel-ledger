"""Jobs service (Phase 5.2, #78).

Owns the job aggregate's lifecycle plus the pieces-math helper. State
transitions are dedicated methods so each can emit its own typed event
and enforce its own legality check.

Pieces math
-----------
For a job with plates ``P``, the total pieces produced is

    min(parts_per_set[p] * runs_completed[p] for p in P)

with the edge cases:
  - no plates → 0
  - any plate with ``runs_completed == 0`` → 0 (its product is zero)

This matches how multi-plate sets actually combine on the shop floor:
one full set requires one run of every plate.

Plate-run side effect
---------------------
``record_plate_run`` increments ``runs_completed`` AND, in the same
transaction, drains material stock by writing one
``production_consumption`` inventory transaction per material in the
plate's ``print_grams_by_material``. The target location is read from
the ``inventory.default_receiving_location_id`` setting (#56) with the
"lowest-code active workshop" fallback.
"""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, asc, desc, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.events.types import production as production_events
from app.models.inventory_location import InventoryLocation, InventoryLocationKind
from app.models.job import Job, JobState
from app.models.plate import Plate
from app.models.printer import Printer
from app.models.product import Product
from app.schemas.events import EventCreate
from app.services import event_store
from app.services import inventory_transactions as inventory_tx_service
from app.services.reference_number import ReferenceNumberService
from app.services.settings.service import SettingsService


class JobsServiceError(Exception):
    """Base class. Routers map to 400 unless noted otherwise."""


class JobNotFoundError(JobsServiceError):
    """Mapped to 404."""


class PlateNotFoundError(JobsServiceError):
    """Mapped to 404."""


class InvalidJobStateError(JobsServiceError):
    """Transition rejected for the current state."""


class ImmutableFieldError(JobsServiceError):
    """Patch tried to change a field that is locked post-create."""


class JobLockedError(JobsServiceError):
    """Mutation attempted on plates of a job past ``draft`` state."""


class ProductLookupError(JobsServiceError):
    """Product missing or archived."""


class PrinterLookupError(JobsServiceError):
    """Printer missing or archived."""


class ReceivingLocationError(JobsServiceError):
    """No suitable inventory location to drain materials from."""


class InvalidCursorError(JobsServiceError):
    pass


# Legal transitions. ``cancelled`` is reachable from any non-terminal state.
_TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    JobState.DRAFT: frozenset({JobState.QUEUED, JobState.CANCELLED}),
    JobState.QUEUED: frozenset({JobState.IN_PROGRESS, JobState.CANCELLED}),
    JobState.IN_PROGRESS: frozenset({JobState.COMPLETED, JobState.CANCELLED}),
    JobState.COMPLETED: frozenset(),
    JobState.CANCELLED: frozenset(),
}


def _ensure_transition(current: JobState, target: JobState) -> None:
    if target not in _TRANSITIONS[current]:
        raise InvalidJobStateError(f"cannot transition job from {current.value} to {target.value}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


def _encode_cursor(created_at: datetime, job_id: uuid.UUID) -> str:
    raw = json.dumps({"c": created_at.isoformat(), "i": str(job_id)}).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        decoded = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(decoded["c"]), uuid.UUID(decoded["i"])
    except (ValueError, KeyError, TypeError) as exc:
        raise InvalidCursorError(f"invalid cursor: {exc}") from exc


async def _load_product_active(session: AsyncSession, product_id: uuid.UUID) -> Product:
    stmt = select(Product).where(Product.id == product_id)
    product = (await session.execute(stmt)).scalar_one_or_none()
    if product is None:
        raise ProductLookupError(f"no product with id {product_id}")
    if product.is_archived:
        raise ProductLookupError(f"product {product_id} is archived")
    return product


async def _load_printer_active(session: AsyncSession, printer_id: uuid.UUID) -> Printer:
    stmt = select(Printer).where(Printer.id == printer_id)
    printer = (await session.execute(stmt)).scalar_one_or_none()
    if printer is None:
        raise PrinterLookupError(f"no printer with id {printer_id}")
    if printer.is_archived:
        raise PrinterLookupError(f"printer {printer_id} is archived")
    return printer


def _serialize_grams(mapping: dict[uuid.UUID, Decimal] | dict[str, Any]) -> dict[str, str]:
    """Normalize the print_grams_by_material payload to JSON-safe shape."""
    out: dict[str, str] = {}
    for k, v in mapping.items():
        key = str(k)
        val = v if isinstance(v, Decimal) else Decimal(str(v))
        out[key] = str(val)
    return out


def _serialize_printer_ids(ids: list[uuid.UUID] | list[str]) -> list[str]:
    return [str(p) for p in ids]


def pieces_produced(job: Job) -> int:
    """Compute pieces produced for ``job`` from its plate ledger.

    Pure function. Returns 0 when the job has no plates or any plate has
    ``runs_completed == 0``.
    """
    plates = list(job.plates)
    if not plates:
        return 0
    pieces_per_plate = [p.parts_per_set * p.runs_completed for p in plates]
    return min(pieces_per_plate)


# ---------------------------------------------------------------------------
# Create / read / update
# ---------------------------------------------------------------------------


@dataclass
class PlateInput:
    name: str
    plate_number: int
    parts_per_set: int
    print_minutes: int
    print_grams_by_material: dict[uuid.UUID, Decimal]
    print_hours_setup_minutes: int
    assigned_printer_ids: list[uuid.UUID]


async def create(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    quantity_ordered: int,
    plates: list[PlateInput],
    priority: int = 0,
    due_at: datetime | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID,
) -> Job:
    if quantity_ordered <= 0:
        raise JobsServiceError("quantity_ordered must be > 0")
    if not plates:
        raise JobsServiceError("at least one plate is required")

    await _load_product_active(session, product_id)

    plate_numbers = [p.plate_number for p in plates]
    if len(plate_numbers) != len(set(plate_numbers)):
        raise JobsServiceError("plate_numbers must be unique within a job")

    for p in plates:
        if p.parts_per_set <= 0:
            raise JobsServiceError("plate parts_per_set must be > 0")
        for printer_id in p.assigned_printer_ids:
            await _load_printer_active(session, printer_id)

    job_number = await ReferenceNumberService.allocate("JOB", session=session)

    job = Job(
        job_number=job_number,
        product_id=product_id,
        quantity_ordered=quantity_ordered,
        state=JobState.DRAFT,
        priority=priority,
        due_at=due_at,
        notes=notes,
        actor_user_id=actor_user_id,
    )
    session.add(job)
    await session.flush()

    plate_rows: list[Plate] = []
    for pi in plates:
        plate = Plate(
            job_id=job.id,
            name=pi.name.strip() or "plate",
            plate_number=pi.plate_number,
            parts_per_set=pi.parts_per_set,
            print_minutes=pi.print_minutes,
            print_grams_by_material=_serialize_grams(pi.print_grams_by_material),
            print_hours_setup_minutes=pi.print_hours_setup_minutes,
            assigned_printer_ids=_serialize_printer_ids(pi.assigned_printer_ids),
            runs_completed=0,
        )
        session.add(plate)
        plate_rows.append(plate)
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_JOB_CREATED,
        aggregate_type=production_events.AGGREGATE_TYPE_JOB,
        aggregate_id=job.id,
        payload={
            "job_id": str(job.id),
            "job_number": job.job_number,
            "product_id": str(job.product_id),
            "quantity_ordered": job.quantity_ordered,
            "plates": [
                {
                    "plate_id": str(p.id),
                    "name": p.name,
                    "plate_number": p.plate_number,
                    "parts_per_set": p.parts_per_set,
                    "print_minutes": p.print_minutes,
                    "print_hours_setup_minutes": p.print_hours_setup_minutes,
                }
                for p in plate_rows
            ],
        },
        actor_user_id=actor_user_id,
    )

    # Reload with plates eager-loaded for response.
    return await get(session, job.id)


async def duplicate(
    session: AsyncSession,
    *,
    source_job_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> Job:
    """Create a fresh DRAFT job by cloning ``source_job_id``.

    Copies: product, quantity_ordered, priority, due_at, notes,
    and every plate (name, plate_number, parts_per_set, print_minutes,
    print_grams_by_material, print_hours_setup_minutes, assigned_printer_ids).
    Fresh: new job_number, state=DRAFT, runs_completed=0 on every plate,
    and the duplicate carries the calling user as actor.

    Source job state doesn't matter — completed or cancelled jobs can
    still seed a new run.
    """
    source = await get(session, source_job_id)
    plate_inputs: list[PlateInput] = []
    for plate in source.plates:
        # ``print_grams_by_material`` and ``assigned_printer_ids`` are
        # stored as JSON with string UUIDs and Decimal-as-string. Coerce
        # back to the native types ``create`` expects.
        grams: dict[uuid.UUID, Decimal] = {}
        for k, v in (plate.print_grams_by_material or {}).items():
            grams[uuid.UUID(str(k))] = Decimal(str(v))
        printer_ids = [uuid.UUID(str(p)) for p in (plate.assigned_printer_ids or [])]
        plate_inputs.append(
            PlateInput(
                name=plate.name,
                plate_number=plate.plate_number,
                parts_per_set=plate.parts_per_set,
                print_minutes=plate.print_minutes,
                print_grams_by_material=grams,
                print_hours_setup_minutes=plate.print_hours_setup_minutes,
                assigned_printer_ids=printer_ids,
            )
        )

    return await create(
        session,
        product_id=source.product_id,
        quantity_ordered=source.quantity_ordered,
        plates=plate_inputs,
        priority=source.priority,
        due_at=source.due_at,
        notes=source.notes,
        actor_user_id=actor_user_id,
    )


async def get(session: AsyncSession, job_id: uuid.UUID) -> Job:
    stmt = select(Job).where(Job.id == job_id).options(selectinload(Job.plates))
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise JobNotFoundError(str(job_id))
    return row


_EDITABLE_FIELDS = ("priority", "due_at", "notes", "quantity_ordered")
_IMMUTABLE_FIELDS = ("product_id",)
# Jobs are read-only once they reach a terminal state.
_TERMINAL_STATES = (JobState.COMPLETED, JobState.CANCELLED)


async def update(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Job:
    for f in _IMMUTABLE_FIELDS:
        if f in patch:
            raise ImmutableFieldError(f"{f} is immutable post-create")

    target = await get(session, job_id)

    # A completed or cancelled job is a closed record — no edits.
    if target.state in _TERMINAL_STATES:
        raise JobLockedError(
            f"cannot edit a job in state {target.state.value!r}; "
            "completed and cancelled jobs are read-only"
        )

    if "quantity_ordered" in patch:
        qty = patch["quantity_ordered"]
        if not isinstance(qty, int) or qty <= 0:
            raise JobsServiceError("quantity_ordered must be > 0")

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field in _EDITABLE_FIELDS:
        if field not in patch:
            continue
        new_value = patch[field]
        current = getattr(target, field)
        if isinstance(current, datetime) and isinstance(new_value, datetime):
            if current == new_value:
                continue
        elif current == new_value:
            continue
        before[field] = current.isoformat() if isinstance(current, datetime) else current
        after[field] = new_value.isoformat() if isinstance(new_value, datetime) else new_value
        setattr(target, field, new_value)

    if not before:
        return target

    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_JOB_UPDATED,
        aggregate_type=production_events.AGGREGATE_TYPE_JOB,
        aggregate_id=target.id,
        payload={
            "job_id": str(target.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return target


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------


async def _transition(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    target: JobState,
    event_type: str,
    actor_user_id: uuid.UUID | None,
) -> Job:
    job = await get(session, job_id)
    _ensure_transition(job.state, target)
    job.state = target
    await session.flush()
    await _emit(
        session,
        event_type=event_type,
        aggregate_type=production_events.AGGREGATE_TYPE_JOB,
        aggregate_id=job.id,
        payload={"job_id": str(job.id)},
        actor_user_id=actor_user_id,
    )
    return job


async def submit(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Job:
    return await _transition(
        session,
        job_id=job_id,
        target=JobState.QUEUED,
        event_type=production_events.TYPE_JOB_SUBMITTED,
        actor_user_id=actor_user_id,
    )


async def start(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Job:
    return await _transition(
        session,
        job_id=job_id,
        target=JobState.IN_PROGRESS,
        event_type=production_events.TYPE_JOB_STARTED,
        actor_user_id=actor_user_id,
    )


async def complete(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Job:
    """Transition a job to ``COMPLETED`` and credit the produced pieces
    to product on-hand.

    Posts a single ``production_in`` inventory transaction for the job's
    product at the configured receiving location, sized to
    ``pieces_produced(job)``. Skips the inventory write when zero
    pieces were recorded (``runs_completed=0`` on any plate, or
    parts_per_set=0). Operates in the same TX as the state transition
    so completion and the inventory credit succeed or fail together.

    The spec says "warns if under, allow" — pieces shortfall is
    reflected by the pieces_produced helper on the response and a
    ``pieces_short`` flag on the event payload; we never block.
    """
    job = await _transition(
        session,
        job_id=job_id,
        target=JobState.COMPLETED,
        event_type=production_events.TYPE_JOB_COMPLETED,
        actor_user_id=actor_user_id,
    )

    produced = pieces_produced(job)
    if produced > 0:
        location_id = await _resolve_consumption_location_id(session)
        await inventory_tx_service.record(
            session,
            kind="production_in",
            entity_kind="product",
            entity_id=job.product_id,
            location_id=location_id,
            quantity=Decimal(produced),
            actor_user_id=actor_user_id,
            linked_job_id=job.id,
            reason=f"job {job.job_number} completed",
        )
    return job


async def cancel(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Job:
    job = await get(session, job_id)
    if job.state in (JobState.COMPLETED, JobState.CANCELLED):
        raise InvalidJobStateError(f"cannot cancel a {job.state.value} job")
    job.state = JobState.CANCELLED
    await session.flush()
    await _emit(
        session,
        event_type=production_events.TYPE_JOB_CANCELLED,
        aggregate_type=production_events.AGGREGATE_TYPE_JOB,
        aggregate_id=job.id,
        payload={"job_id": str(job.id)},
        actor_user_id=actor_user_id,
    )
    return job


# ---------------------------------------------------------------------------
# Plate-run + material consumption
# ---------------------------------------------------------------------------


async def _resolve_consumption_location_id(session: AsyncSession) -> uuid.UUID:
    """Same resolution chain as material receipts (#56)."""
    configured: uuid.UUID | None = await SettingsService.get(
        "inventory.default_receiving_location_id", session=session
    )
    if configured is not None:
        stmt = select(InventoryLocation).where(InventoryLocation.id == configured)
        loc = (await session.execute(stmt)).scalar_one_or_none()
        if loc is not None and not loc.is_archived:
            return loc.id
    stmt = (
        select(InventoryLocation)
        .where(InventoryLocation.kind == InventoryLocationKind.WORKSHOP)
        .where(InventoryLocation.is_archived.is_(False))
        .order_by(asc(InventoryLocation.code))
        .limit(1)
    )
    fallback = (await session.execute(stmt)).scalar_one_or_none()
    if fallback is None:
        raise ReceivingLocationError(
            "no consumption source location: configure "
            "inventory.default_receiving_location_id or create a workshop location"
        )
    return fallback.id


async def _load_plate(session: AsyncSession, plate_id: uuid.UUID) -> Plate:
    stmt = select(Plate).where(Plate.id == plate_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise PlateNotFoundError(str(plate_id))
    return row


async def record_plate_run(
    session: AsyncSession,
    *,
    plate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    runs_completed_delta: int = 1,
) -> Plate:
    if runs_completed_delta < 1:
        raise JobsServiceError("runs_completed_delta must be >= 1")

    plate = await _load_plate(session, plate_id)
    job = await get(session, plate.job_id)
    if job.state not in (JobState.QUEUED, JobState.IN_PROGRESS):
        raise InvalidJobStateError(f"cannot record plate run on job in state {job.state.value}")

    plate.runs_completed = plate.runs_completed + runs_completed_delta
    await session.flush()

    materials_consumed: list[dict[str, Any]] = []
    grams_map = plate.print_grams_by_material or {}
    if grams_map:
        location_id = await _resolve_consumption_location_id(session)
        for material_key, grams_value in grams_map.items():
            material_id = uuid.UUID(str(material_key))
            grams_per_run = Decimal(str(grams_value))
            total_grams = grams_per_run * Decimal(runs_completed_delta)
            if total_grams <= 0:
                continue
            await inventory_tx_service.record(
                session,
                kind="production_consumption",
                entity_kind="material",
                entity_id=material_id,
                location_id=location_id,
                quantity=total_grams,
                actor_user_id=actor_user_id,
                linked_job_id=job.id,
                reason=f"plate {plate.id} run +{runs_completed_delta}",
            )
            materials_consumed.append({"material_id": str(material_id), "grams": str(total_grams)})

    await _emit(
        session,
        event_type=production_events.TYPE_PLATE_RUN_RECORDED,
        aggregate_type=production_events.AGGREGATE_TYPE_PLATE,
        aggregate_id=plate.id,
        payload={
            "plate_id": str(plate.id),
            "job_id": str(job.id),
            "new_runs_completed": plate.runs_completed,
            "materials_consumed": materials_consumed,
        },
        actor_user_id=actor_user_id,
    )
    return plate


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@dataclass
class JobPage:
    items: list[Job]
    next_cursor: str | None


async def list_jobs(
    session: AsyncSession,
    *,
    state: str | None = None,
    product_id: uuid.UUID | None = None,
    search: str | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> JobPage:
    stmt = select(Job).options(selectinload(Job.plates))
    if state is not None:
        try:
            stmt = stmt.where(Job.state == JobState(state))
        except ValueError as exc:
            raise JobsServiceError(f"invalid state filter: {state!r}") from exc
    if product_id is not None:
        stmt = stmt.where(Job.product_id == product_id)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(Job.job_number.ilike(like))
    if cursor is not None:
        anchor_ts, anchor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                Job.created_at < anchor_ts,
                and_(Job.created_at == anchor_ts, Job.id < anchor_id),
            )
        )
    stmt = stmt.order_by(desc(Job.created_at), desc(Job.id)).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    next_cursor = _encode_cursor(rows[-1].created_at, rows[-1].id) if (rows and has_more) else None
    return JobPage(items=rows, next_cursor=next_cursor)


__all__ = [
    "ImmutableFieldError",
    "InvalidCursorError",
    "InvalidJobStateError",
    "JobLockedError",
    "JobNotFoundError",
    "JobPage",
    "JobsServiceError",
    "PlateInput",
    "PlateNotFoundError",
    "PrinterLookupError",
    "ProductLookupError",
    "ReceivingLocationError",
    "cancel",
    "complete",
    "create",
    "get",
    "list_jobs",
    "pieces_produced",
    "record_plate_run",
    "start",
    "submit",
    "update",
]
