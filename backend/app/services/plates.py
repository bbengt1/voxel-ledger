"""Plates service (Phase 5.2, #78).

CRUD for plates plus printer assignment. Mutations (create/update/delete)
are only legal while the parent job is in ``draft``; changing plate
geometry after the job leaves draft would corrupt the pieces/economics
math.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import production as production_events
from app.models.job import Job, JobState
from app.models.plate import Plate
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.jobs import (
    JobLockedError,
    JobNotFoundError,
    PlateNotFoundError,
    _load_printer_active,
    _serialize_grams,
    _serialize_printer_ids,
)


class PlatesServiceError(Exception):
    """Base class. Routers map subclasses to 400 unless noted."""


class DuplicatePlateNumberError(PlatesServiceError):
    pass


class PrinterAlreadyAssignedError(PlatesServiceError):
    pass


class PrinterNotAssignedError(PlatesServiceError):
    pass


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


async def _load_job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    stmt = select(Job).where(Job.id == job_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise JobNotFoundError(str(job_id))
    return row


async def _load_plate(session: AsyncSession, plate_id: uuid.UUID) -> Plate:
    stmt = select(Plate).where(Plate.id == plate_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise PlateNotFoundError(str(plate_id))
    return row


def _ensure_draft(job: Job) -> None:
    if job.state != JobState.DRAFT:
        raise JobLockedError(
            f"cannot modify plates on a job in state {job.state.value!r}; "
            "plates are locked once the job leaves draft"
        )


async def create(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    name: str,
    plate_number: int,
    parts_per_set: int,
    print_minutes: int,
    print_grams_by_material: dict[uuid.UUID, Decimal] | None = None,
    print_hours_setup_minutes: int = 0,
    assigned_printer_ids: list[uuid.UUID] | None = None,
    actor_user_id: uuid.UUID | None,
) -> Plate:
    if parts_per_set <= 0:
        raise PlatesServiceError("parts_per_set must be > 0")
    if print_minutes < 0:
        raise PlatesServiceError("print_minutes must be >= 0")

    job = await _load_job(session, job_id)
    _ensure_draft(job)

    dup = (
        await session.execute(
            select(Plate.id).where(Plate.job_id == job_id).where(Plate.plate_number == plate_number)
        )
    ).scalar_one_or_none()
    if dup is not None:
        raise DuplicatePlateNumberError(
            f"plate_number {plate_number} already exists on job {job_id}"
        )

    for printer_id in assigned_printer_ids or []:
        await _load_printer_active(session, printer_id)

    plate = Plate(
        job_id=job_id,
        name=name.strip() or "plate",
        plate_number=plate_number,
        parts_per_set=parts_per_set,
        print_minutes=print_minutes,
        print_grams_by_material=_serialize_grams(print_grams_by_material or {}),
        print_hours_setup_minutes=print_hours_setup_minutes,
        assigned_printer_ids=_serialize_printer_ids(assigned_printer_ids or []),
        runs_completed=0,
    )
    session.add(plate)
    await session.flush()
    return plate


_EDITABLE = (
    "name",
    "plate_number",
    "parts_per_set",
    "print_minutes",
    "print_grams_by_material",
    "print_hours_setup_minutes",
)


async def update(
    session: AsyncSession,
    *,
    plate_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> Plate:
    plate = await _load_plate(session, plate_id)
    job = await _load_job(session, plate.job_id)
    _ensure_draft(job)

    for field in _EDITABLE:
        if field not in patch:
            continue
        new_value = patch[field]
        if field == "print_grams_by_material" and new_value is not None:
            new_value = _serialize_grams(new_value)
        if field == "parts_per_set" and new_value is not None and new_value <= 0:
            raise PlatesServiceError("parts_per_set must be > 0")
        if field == "plate_number" and new_value is not None and new_value != plate.plate_number:
            dup = (
                await session.execute(
                    select(Plate.id)
                    .where(Plate.job_id == plate.job_id)
                    .where(Plate.plate_number == new_value)
                    .where(Plate.id != plate.id)
                )
            ).scalar_one_or_none()
            if dup is not None:
                raise DuplicatePlateNumberError(
                    f"plate_number {new_value} already exists on job {plate.job_id}"
                )
        setattr(plate, field, new_value)

    await session.flush()
    return plate


async def delete(
    session: AsyncSession,
    *,
    plate_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> None:
    plate = await _load_plate(session, plate_id)
    job = await _load_job(session, plate.job_id)
    _ensure_draft(job)
    await session.delete(plate)
    await session.flush()


async def assign_printer(
    session: AsyncSession,
    *,
    plate_id: uuid.UUID,
    printer_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Plate:
    plate = await _load_plate(session, plate_id)
    await _load_printer_active(session, printer_id)

    current = list(plate.assigned_printer_ids or [])
    ids = [str(p) for p in current]
    if str(printer_id) in ids:
        raise PrinterAlreadyAssignedError(
            f"printer {printer_id} already assigned to plate {plate_id}"
        )
    ids.append(str(printer_id))
    plate.assigned_printer_ids = ids
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_PLATE_ASSIGNED,
        aggregate_type=production_events.AGGREGATE_TYPE_PLATE,
        aggregate_id=plate.id,
        payload={
            "plate_id": str(plate.id),
            "job_id": str(plate.job_id),
            "printer_id": str(printer_id),
        },
        actor_user_id=actor_user_id,
    )
    return plate


async def unassign_printer(
    session: AsyncSession,
    *,
    plate_id: uuid.UUID,
    printer_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
) -> Plate:
    plate = await _load_plate(session, plate_id)
    current = list(plate.assigned_printer_ids or [])
    ids = [str(p) for p in current]
    if str(printer_id) not in ids:
        raise PrinterNotAssignedError(f"printer {printer_id} not assigned to plate {plate_id}")
    ids = [p for p in ids if p != str(printer_id)]
    plate.assigned_printer_ids = ids
    await session.flush()

    await _emit(
        session,
        event_type=production_events.TYPE_PLATE_UNASSIGNED,
        aggregate_type=production_events.AGGREGATE_TYPE_PLATE,
        aggregate_id=plate.id,
        payload={
            "plate_id": str(plate.id),
            "job_id": str(plate.job_id),
            "printer_id": str(printer_id),
        },
        actor_user_id=actor_user_id,
    )
    return plate


__all__ = [
    "DuplicatePlateNumberError",
    "PlatesServiceError",
    "PrinterAlreadyAssignedError",
    "PrinterNotAssignedError",
    "assign_printer",
    "create",
    "delete",
    "unassign_printer",
    "update",
]
