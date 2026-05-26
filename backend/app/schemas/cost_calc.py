"""Pydantic schemas for the live cost-calc endpoint (Phase 5.3, #79)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CalcPlateInputPayload(BaseModel):
    """A single plate's shape as proposed by the composer."""

    parts_per_set: int = Field(gt=0)
    print_minutes: int = Field(ge=0)
    print_grams_by_material: dict[uuid.UUID, Decimal] = Field(default_factory=dict)
    setup_minutes: int = Field(default=0, ge=0)
    assigned_printer_ids: list[uuid.UUID] = Field(default_factory=list)


class CalcInputsPayload(BaseModel):
    plates: list[CalcPlateInputPayload] = Field(min_length=1)
    quantity_ordered: int = Field(ge=0)


class CalcRequest(BaseModel):
    """POST body. Exactly one of ``job_id`` or ``inputs`` must be set."""

    job_id: uuid.UUID | None = None
    inputs: CalcInputsPayload | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> CalcRequest:
        present = sum(1 for v in (self.job_id, self.inputs) if v is not None)
        if present != 1:
            raise ValueError("exactly one of `job_id` or `inputs` is required")
        return self


class PerPlateCostResponse(BaseModel):
    plate_index: int
    parts_per_set: int
    runs: int
    material_cost: Decimal
    labor_cost: Decimal
    machine_cost: Decimal


class CalcResultResponse(BaseModel):
    pieces_per_set: int
    sets_required: int
    material_cost: Decimal
    supply_cost: Decimal
    labor_cost: Decimal
    machine_cost: Decimal
    overhead_cost: Decimal
    total_cost: Decimal
    cost_per_piece: Decimal
    suggested_unit_price: Decimal
    # #249 itemized breakdown of ``machine_cost`` when the plate's
    # printer carries per-printer cost params; zero otherwise.
    electricity_cost: Decimal = Decimal("0.00")
    preheat_cost: Decimal = Decimal("0.00")
    depreciation_cost: Decimal = Decimal("0.00")
    failure_adjustment_cost: Decimal = Decimal("0.00")
    per_plate: list[PerPlateCostResponse]
