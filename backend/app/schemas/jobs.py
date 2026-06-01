"""Pydantic schemas for the jobs + plates API surface (Phase 5.2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

JobStateLiteral = Literal[
    "draft",
    "queued",
    "in_progress",
    "completed",
    "cancelled",
]


# --- Plate -----------------------------------------------------------------


class PlateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    plate_number: int = Field(ge=1)
    parts_per_set: int = Field(gt=0)
    print_minutes: int = Field(ge=0)
    print_grams_by_material: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    print_hours_setup_minutes: int = Field(default=0, ge=0)
    assigned_printer_ids: list[uuid.UUID] = Field(default_factory=list)


class PlateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    plate_number: int | None = Field(default=None, ge=1)
    parts_per_set: int | None = Field(default=None, gt=0)
    print_minutes: int | None = Field(default=None, ge=0)
    print_grams_by_material: dict[uuid.UUID, Decimal] | None = None
    print_hours_setup_minutes: int | None = Field(default=None, ge=0)


class PlateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    name: str
    plate_number: int
    parts_per_set: int
    print_minutes: int
    print_grams_by_material: dict[str, str]
    print_hours_setup_minutes: int
    assigned_printer_ids: list[str]
    runs_completed: int
    created_at: datetime
    updated_at: datetime


class PlateRunRequest(BaseModel):
    runs_completed_delta: int = Field(default=1, ge=1)


class AssignPrinterRequest(BaseModel):
    printer_id: uuid.UUID


# --- Job -------------------------------------------------------------------


class JobCreate(BaseModel):
    """A job produces a **part** (epic #267 Phase 4): pass ``part_id`` and a
    quantity — the recipe comes from the part. The legacy product path
    (``product_id`` + ``plates``) is retained for transition.
    """

    part_id: uuid.UUID | None = None
    product_id: uuid.UUID | None = None
    quantity_ordered: int = Field(gt=0)
    priority: int = Field(default=0)
    due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4096)
    plates: list[PlateCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _part_xor_product(self) -> JobCreate:
        if self.part_id is not None:
            if self.product_id is not None or self.plates:
                raise ValueError("a part job takes part_id only — no product_id or plates")
        else:
            if self.product_id is None:
                raise ValueError("either part_id or product_id is required")
            if not self.plates:
                raise ValueError("a product job requires at least one plate")
        return self


class JobUpdate(BaseModel):
    """Editable post-create: ``priority``, ``due_at``, ``notes`` and
    ``quantity_ordered`` — while the job is non-terminal.

    ``product_id`` is immutable; the service rejects it with 400.
    Completed/cancelled jobs are read-only.
    """

    priority: int | None = None
    due_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=4096)
    quantity_ordered: int | None = Field(default=None, gt=0)


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_number: str
    product_id: uuid.UUID | None = None
    part_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    state: JobStateLiteral
    quantity_ordered: int
    priority: int
    due_at: datetime | None = None
    notes: str | None = None
    actor_user_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    plates: list[PlateResponse] = Field(default_factory=list)
    pieces_produced: int = 0


class JobListResponse(BaseModel):
    items: list[JobResponse]
    next_cursor: str | None = None
