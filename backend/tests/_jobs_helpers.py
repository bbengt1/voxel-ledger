"""Shared helpers for jobs/plates tests (Phase 5.2; part-only since 8a)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.models.auth import Role
from app.models.job import Job, JobState
from app.models.plate import Plate
from app.services import material_receipts as receipts_service
from app.services import materials as materials_service
from app.services import parts as parts_service
from app.services import printers as printers_service
from app.services import products as products_service
from app.services.auth import create_user
from app.services.reference_number import ReferenceNumberService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def token_for(role: Role, client: AsyncClient, session: AsyncSession) -> str:
    email = f"{role.value}@example.com"
    await create_user(
        session,
        email=email,
        password="pw-correct",
        full_name=role.value,
        role=role,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "pw-correct"},
    )
    return r.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def seed_product(session: AsyncSession, *, name: str = "Widget"):
    product = await products_service.create(
        session,
        name=name,
        description=None,
        unit_price=Decimal("10"),
        actor_user_id=None,
    )
    await session.commit()
    return product


async def seed_printer(session: AsyncSession, *, name: str | None = None):
    """Create an **inert** active printer (no power/price → zero cost impact)
    for tests that need a printer to assign to a job/part."""
    suffix = uuid.uuid4().hex[:8]
    printer = await printers_service.create(
        session,
        name=name or f"Printer {suffix}",
        slug=f"printer-{suffix}",
        printer_type="other",
        actor_user_id=None,
    )
    await session.commit()
    return printer


async def seed_part(
    session: AsyncSession,
    *,
    name: str = "Bracket",
    grams: str = "50",
    parts_per_run: int = 1,
    print_minutes: int = 0,
    setup_minutes: int = 0,
    with_printer: bool = True,
):
    """Create a costed Part (material + receipt + part) for part-based job
    tests. Jobs now produce Parts (epic #267) — POST ``{part_id, quantity_ordered}``.

    By default the part has an inert printer assigned, so jobs created from it
    are startable (starting a job requires a printer — see ``jobs.start``).
    Pass ``with_printer=False`` to seed a printer-less part (e.g. to exercise
    the start-without-printer guard).
    """
    mat = await materials_service.create(
        session,
        name=f"PLA {uuid.uuid4().hex[:6]}",
        brand=None,
        material_type="PLA",
        color=None,
        density_g_per_cm3=None,
        spool_weight_grams=Decimal("1000"),
        actor_user_id=None,
    )
    await session.commit()
    await receipts_service.record(
        session,
        material_id=mat.id,
        grams=Decimal("1000"),
        total_cost=Decimal("20"),
        actor_user_id=None,
    )
    await session.commit()
    printer_ids: list[uuid.UUID] = []
    if with_printer:
        printer = await seed_printer(session)
        printer_ids = [printer.id]
    part = await parts_service.create(
        session,
        name=name,
        print_minutes=print_minutes,
        setup_minutes=setup_minutes,
        parts_per_run=parts_per_run,
        print_grams_by_material={mat.id: Decimal(grams)},
        assigned_printer_ids=printer_ids,
        actor_user_id=None,
    )
    await session.commit()
    return part


async def insert_legacy_product_job(
    session: AsyncSession,
    *,
    product_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    plates: list[dict],
    state: JobState = JobState.DRAFT,
    quantity_ordered: int = 1,
) -> Job:
    """Insert a pre-migration product-job (+ plates) as raw rows.

    The product+plates *create* path was retired in Phase 8a, so legacy
    product-jobs can only be simulated by direct inserts (which is what
    they are — historical data). Each ``plates`` entry is a dict with
    ``name``, ``plate_number``, ``parts_per_set`` and optional
    ``print_minutes``, ``grams`` ({material_id: Decimal}), ``setup``,
    ``runs_completed``.
    """
    job_number = await ReferenceNumberService.allocate("JOB", session=session)
    job = Job(
        job_number=job_number,
        product_id=product_id,
        part_id=None,
        quantity_ordered=quantity_ordered,
        state=state,
        actor_user_id=actor_user_id,
    )
    session.add(job)
    await session.flush()
    for pl in plates:
        session.add(
            Plate(
                job_id=job.id,
                name=pl["name"],
                plate_number=pl["plate_number"],
                parts_per_set=pl["parts_per_set"],
                print_minutes=pl.get("print_minutes", 0),
                print_grams_by_material={str(k): str(v) for k, v in pl.get("grams", {}).items()},
                print_hours_setup_minutes=pl.get("setup", 0),
                assigned_printer_ids=[],
                runs_completed=pl.get("runs_completed", 0),
            )
        )
    await session.flush()
    return job
