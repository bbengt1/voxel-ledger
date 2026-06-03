"""Jobs + plates endpoints (Phase 5.2, #78).

Thin layer over ``app.services.jobs`` + ``app.services.plates``. Routers
commit the transaction, map service-layer errors to HTTP, and gate each
route on role.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.core.db import get_session
from app.models.auth import User
from app.models.job import Job
from app.models.plate import Plate
from app.schemas.jobs import (
    AssignPrinterRequest,
    JobCreate,
    JobListResponse,
    JobResponse,
    JobUpdate,
    PlateCreate,
    PlateResponse,
    PlateRunRequest,
    PlateUpdate,
)
from app.schemas.production_orders import DiscoveredPlateResponse
from app.services import job_discovery as discovery_service
from app.services import jobs as jobs_service
from app.services import plates as plates_service
from app.services import printers as printers_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


def _plate_to_response(plate: Plate) -> PlateResponse:
    grams = plate.print_grams_by_material or {}
    return PlateResponse(
        id=plate.id,
        job_id=plate.job_id,
        name=plate.name,
        plate_number=plate.plate_number,
        parts_per_set=plate.parts_per_set,
        print_minutes=plate.print_minutes,
        print_grams_by_material={str(k): str(v) for k, v in grams.items()},
        print_hours_setup_minutes=plate.print_hours_setup_minutes,
        assigned_printer_ids=[str(p) for p in (plate.assigned_printer_ids or [])],
        runs_completed=plate.runs_completed,
        created_at=plate.created_at,
        updated_at=plate.updated_at,
    )


def _job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        job_number=job.job_number,
        product_id=job.product_id,
        part_id=job.part_id,
        part_sku=job.part.sku if job.part else None,
        part_name=job.part.name if job.part else None,
        customer_id=job.customer_id,
        state=job.state.value,  # type: ignore[arg-type]
        quantity_ordered=job.quantity_ordered,
        description=job.description,
        priority=job.priority,
        due_at=job.due_at,
        notes=job.notes,
        actor_user_id=job.actor_user_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        plates=[_plate_to_response(p) for p in job.plates],
        pieces_produced=jobs_service.pieces_produced(job),
    )


def _map_jobs_error(exc: Exception) -> HTTPException:
    if isinstance(exc, jobs_service.JobNotFoundError | jobs_service.PlateNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, jobs_service.ImmutableFieldError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.InvalidJobStateError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.JobLockedError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.ProductLookupError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.PrinterLookupError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.NoPrinterAssignedError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.ReceivingLocationError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.InvalidCursorError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, plates_service.PlatesServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, jobs_service.JobsServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    raise exc


# ---------------------------------------------------------------------------
# Job CRUD
# ---------------------------------------------------------------------------


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: JobCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    try:
        job = await jobs_service.create(
            session,
            part_id=payload.part_id,
            quantity_ordered=payload.quantity_ordered,
            priority=payload.priority,
            due_at=payload.due_at,
            notes=payload.notes,
            description=payload.description,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    return _job_to_response(job)


@router.get("", response_model=JobListResponse)
async def list_jobs(
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
    state: Annotated[str | None, Query()] = None,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JobListResponse:
    try:
        page = await jobs_service.list_jobs(
            session,
            state=state,
            product_id=product_id,
            search=search,
            cursor=cursor,
            limit=limit,
        )
    except Exception as exc:
        raise _map_jobs_error(exc) from None
    return JobListResponse(
        items=[_job_to_response(j) for j in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(require_role("owner", "production", "sales"))],
) -> JobResponse:
    try:
        job = await jobs_service.get(session, job_id)
    except Exception as exc:
        raise _map_jobs_error(exc) from None
    return _job_to_response(job)


_PATCH_IMMUTABLE_KEYS = ("product_id", "part_id")


@router.patch("/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: uuid.UUID,
    payload: JobUpdate,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    # Re-parse the raw body to enforce immutability rejection at the
    # contract surface; ``JobUpdate`` ignores unknown fields by default.
    try:
        raw = await request.json()
    except Exception:
        raw = {}
    if isinstance(raw, dict):
        for key in _PATCH_IMMUTABLE_KEYS:
            if key in raw:
                raise HTTPException(
                    status_code=400,
                    detail=f"{key} is immutable post-create",
                )
    patch = payload.model_dump(exclude_unset=True)
    try:
        job = await jobs_service.update(session, job_id=job_id, patch=patch, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    job = await jobs_service.get(session, job.id)
    return _job_to_response(job)


@router.post(
    "/{job_id}/duplicate",
    response_model=JobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    """Create a fresh DRAFT job by cloning ``job_id``'s product, plates,
    and free-text fields. Plate ``runs_completed`` is reset to 0 and a
    new ``job_number`` is allocated."""
    try:
        new_job = await jobs_service.duplicate(
            session, source_job_id=job_id, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    return _job_to_response(new_job)


@router.post("/{job_id}/submit", response_model=JobResponse)
async def submit_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    try:
        await jobs_service.submit(session, job_id=job_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    job = await jobs_service.get(session, job_id)
    return _job_to_response(job)


@router.post("/{job_id}/start", response_model=JobResponse)
async def start_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    try:
        await jobs_service.start(session, job_id=job_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    job = await jobs_service.get(session, job_id)
    return _job_to_response(job)


@router.post("/{job_id}/complete", response_model=JobResponse)
async def complete_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    try:
        await jobs_service.complete(session, job_id=job_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    job = await jobs_service.get(session, job_id)
    return _job_to_response(job)


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(
    job_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> JobResponse:
    try:
        await jobs_service.cancel(session, job_id=job_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    job = await jobs_service.get(session, job_id)
    return _job_to_response(job)


# ---------------------------------------------------------------------------
# Plate CRUD
# ---------------------------------------------------------------------------


@router.post(
    "/{job_id}/plates",
    response_model=PlateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_plate(
    job_id: uuid.UUID,
    payload: PlateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PlateResponse:
    try:
        plate = await plates_service.create(
            session,
            job_id=job_id,
            name=payload.name,
            plate_number=payload.plate_number,
            parts_per_set=payload.parts_per_set,
            print_minutes=payload.print_minutes,
            print_grams_by_material=payload.print_grams_by_material,
            print_hours_setup_minutes=payload.print_hours_setup_minutes,
            assigned_printer_ids=payload.assigned_printer_ids,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()
    return _plate_to_response(plate)


@router.patch("/{job_id}/plates/{plate_id}", response_model=PlateResponse)
async def update_plate(
    job_id: uuid.UUID,
    plate_id: uuid.UUID,
    payload: PlateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PlateResponse:
    patch = payload.model_dump(exclude_unset=True)
    try:
        plate = await plates_service.update(
            session, plate_id=plate_id, patch=patch, actor_user_id=actor.id
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    if plate.job_id != job_id:
        await session.rollback()
        raise HTTPException(status_code=404, detail="plate not found on this job")
    await session.commit()
    # ``updated_at`` uses ``onupdate=func.now()``; after the UPDATE the
    # attribute is expired, so reload in the async context before building
    # the response (the sync serializer can't trigger a lazy load).
    await session.refresh(plate)
    return _plate_to_response(plate)


@router.delete("/{job_id}/plates/{plate_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plate(
    job_id: uuid.UUID,
    plate_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> None:
    # Verify parentage first to give a clean 404.
    try:
        plate = await plates_service._load_plate(session, plate_id)
    except Exception as exc:
        raise _map_jobs_error(exc) from None
    if plate.job_id != job_id:
        raise HTTPException(status_code=404, detail="plate not found on this job")
    try:
        await plates_service.delete(session, plate_id=plate_id, actor_user_id=actor.id)
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    await session.commit()


@router.post(
    "/{job_id}/plates/{plate_id}/assign-printer",
    response_model=PlateResponse,
)
async def assign_printer(
    job_id: uuid.UUID,
    plate_id: uuid.UUID,
    payload: AssignPrinterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PlateResponse:
    try:
        plate = await plates_service.assign_printer(
            session,
            plate_id=plate_id,
            printer_id=payload.printer_id,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    if plate.job_id != job_id:
        await session.rollback()
        raise HTTPException(status_code=404, detail="plate not found on this job")
    await session.commit()
    # ``updated_at`` uses ``onupdate=func.now()``; after the UPDATE the
    # attribute is expired, so reload in the async context before building
    # the response (the sync serializer can't trigger a lazy load).
    await session.refresh(plate)
    return _plate_to_response(plate)


@router.post(
    "/{job_id}/plates/{plate_id}/unassign-printer",
    response_model=PlateResponse,
)
async def unassign_printer(
    job_id: uuid.UUID,
    plate_id: uuid.UUID,
    payload: AssignPrinterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PlateResponse:
    try:
        plate = await plates_service.unassign_printer(
            session,
            plate_id=plate_id,
            printer_id=payload.printer_id,
            actor_user_id=actor.id,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    if plate.job_id != job_id:
        await session.rollback()
        raise HTTPException(status_code=404, detail="plate not found on this job")
    await session.commit()
    # ``updated_at`` uses ``onupdate=func.now()``; after the UPDATE the
    # attribute is expired, so reload in the async context before building
    # the response (the sync serializer can't trigger a lazy load).
    await session.refresh(plate)
    return _plate_to_response(plate)


class _DiscoverFromPrinterRequest(BaseModel):
    printer_id: uuid.UUID
    filename: str = Field(min_length=1)


@router.post("/discover-from-printer", response_model=DiscoveredPlateResponse)
async def discover_from_printer(
    payload: _DiscoverFromPrinterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    _actor: Annotated[User, Depends(get_current_user)],
) -> DiscoveredPlateResponse:
    """Parse Moonraker metadata for one gcode file and return the same
    ``DiscoveredPlateResponse`` shape as the sidecar discover endpoint.

    Moonraker exposes ``estimated_time``, per-extruder ``filament_used_mm``,
    ``filament_weight``, ``filament_name``, ``filament_total``, and
    ``object_count`` (via ``object_height`` + slicer metadata). We map
    those into the same plate-population payload the UI already knows
    how to apply.
    """
    try:
        printer = await printers_service.get(session, payload.printer_id)
    except printers_service.PrinterNotFoundError:
        raise HTTPException(status_code=404, detail="printer not found") from None
    if not printer.moonraker_url:
        raise HTTPException(status_code=404, detail="moonraker not configured")

    try:
        result = await discovery_service.discover_from_moonraker(
            moonraker_url=printer.moonraker_url,
            api_key=printer.moonraker_api_key,
            filename=payload.filename,
        )
    except discovery_service.MoonrakerFetchError as exc:
        raise HTTPException(status_code=502, detail=f"moonraker fetch failed: {exc}") from None

    return DiscoveredPlateResponse(
        print_minutes=result.print_minutes,
        filament_grams_by_material=dict(result.filament_grams_by_material),
        parts_per_set=result.parts_per_set,
        source_format=result.source_format,
        source_filename=result.source_filename,
    )


@router.post("/discover", response_model=DiscoveredPlateResponse)
async def discover_from_sidecar(
    _actor: Annotated[User, Depends(get_current_user)],
    file: Annotated[UploadFile, File()],
) -> DiscoveredPlateResponse:
    """Parse a PrusaSlicer/Bambu Studio .gcode.json sidecar and return the
    extracted plate fields. No DB writes — the UI uses this to pre-fill
    the plate-create form. Any authenticated role may call this.
    """
    content = await file.read()
    try:
        # Dispatcher routes JSON sidecars and 3MF archives to the right
        # parser based on a zip-magic sniff of the first four bytes.
        result = discovery_service.parse_job_artifact(content, source_filename=file.filename)
    except discovery_service.UnknownSidecarFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from None
    except discovery_service.MalformedSidecarError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return DiscoveredPlateResponse(
        print_minutes=result.print_minutes,
        filament_grams_by_material={k: v for k, v in result.filament_grams_by_material.items()},
        parts_per_set=result.parts_per_set,
        source_format=result.source_format,
        source_filename=result.source_filename,
    )


@router.post(
    "/{job_id}/plates/{plate_id}/record-run",
    response_model=PlateResponse,
)
async def record_run(
    job_id: uuid.UUID,
    plate_id: uuid.UUID,
    payload: PlateRunRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    actor: Annotated[User, Depends(require_role("owner", "production"))],
) -> PlateResponse:
    # Confirm parentage first.
    try:
        plate = await plates_service._load_plate(session, plate_id)
    except Exception as exc:
        raise _map_jobs_error(exc) from None
    if plate.job_id != job_id:
        raise HTTPException(status_code=404, detail="plate not found on this job")
    try:
        plate = await jobs_service.record_plate_run(
            session,
            plate_id=plate_id,
            actor_user_id=actor.id,
            runs_completed_delta=payload.runs_completed_delta,
        )
    except Exception as exc:
        await session.rollback()
        raise _map_jobs_error(exc) from None
    # Refresh server-side timestamps before commit expires the instance.
    await session.refresh(plate)
    await session.commit()
    return _plate_to_response(plate)
