"""Pydantic schemas for the AP aging report (Phase 8.4, #131).

Mirror of the AR aging response schemas in :mod:`app.schemas.late_fees`,
with ``vendor_number`` swapped in for ``customer_number``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class ApAgingBucketResponse(BaseModel):
    label: str
    amount: Decimal


class ApAgingRowResponse(BaseModel):
    vendor_id: uuid.UUID
    vendor_number: str
    display_name: str
    total_outstanding: Decimal
    buckets: list[ApAgingBucketResponse]


class ApAgingReportResponse(BaseModel):
    as_of: datetime
    bucket_labels: list[str]
    rows: list[ApAgingRowResponse]
    grand_total: Decimal
    grand_total_by_bucket: list[Decimal]
