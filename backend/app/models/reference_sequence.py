"""ORM model for the reference number allocator (Phase 1.3).

One row per ``(prefix, year)`` pair. ``last_value`` is the most recently
allocated sequence number for that bucket. The allocator increments via
``INSERT ... ON CONFLICT DO UPDATE RETURNING`` — see
``app.services.reference_number`` and v1 incident #243 for why we don't
use COUNT here.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class ReferenceSequence(Base):
    __tablename__ = "reference_sequence"

    prefix: Mapped[str] = mapped_column(String(32), primary_key=True)
    year: Mapped[int] = mapped_column(Integer, primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
