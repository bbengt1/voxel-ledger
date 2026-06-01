"""Pydantic schemas for the BOM API surface (Phase 2.4)."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ComponentKind = Literal["material", "supply", "product", "part"]


class BomItemCreate(BaseModel):
    component_kind: ComponentKind
    component_id: uuid.UUID
    quantity: Decimal = Field(gt=0)
    notes: str | None = None


class BomItemUpdate(BaseModel):
    quantity: Decimal = Field(gt=0)


class BomItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    parent_product_id: uuid.UUID
    component_kind: ComponentKind
    component_id: uuid.UUID
    quantity: Decimal
    notes: str | None = None

    # Denormalized for UI convenience. ``resolved_unit_cost`` is the
    # current leaf cost (cost-per-gram for materials, unit_cost for
    # supplies, unit_cost_cached for sub-products). May be None when a
    # sub-product has no rolled-up cost yet.
    resolved_name: str
    resolved_unit_cost: Decimal | None = None
    line_cost: Decimal | None = None


class BomListResponse(BaseModel):
    items: list[BomItemResponse]
    # Convenience aggregate: sum of line costs, NULL if any leg is
    # unknown. Mirrors ``product.unit_cost_cached`` once the projection
    # has run.
    total_cost: Decimal | None = None


class CostBreakdownComponent(BaseModel):
    bom_item_id: uuid.UUID
    component_kind: ComponentKind
    component_id: uuid.UUID
    resolved_name: str
    quantity: Decimal
    unit_cost: Decimal | None = None
    line_cost: Decimal | None = None
    # Only populated when component_kind == "product".
    sub_tree: CostBreakdownResponse | None = None


class CostBreakdownResponse(BaseModel):
    product_id: uuid.UUID
    resolved_name: str
    total_cost: Decimal | None = None
    components: list[CostBreakdownComponent] = Field(default_factory=list)
    # True when the tree was truncated because depth exceeded the limit.
    truncated_at_depth: bool = False


CostBreakdownComponent.model_rebuild()
CostBreakdownResponse.model_rebuild()
