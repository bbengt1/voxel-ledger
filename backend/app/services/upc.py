"""Internal UPC-A generator.

Mints deterministic UPC-A codes in the company-internal namespace
``04xxxxxxxxx`` + check digit (12 digits total). The allocator looks
at the highest existing serial under the ``04`` prefix and assigns
``max + 1`` — sequential, no randomness, no retry budget.

The check digit follows the GS1 UPC-A algorithm:
  - sum digits in odd positions (1st, 3rd, ..., 11th), multiply by 3,
  - add digits in even positions (2nd, 4th, ..., 10th),
  - check digit = ``(10 - total % 10) % 10``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product

INTERNAL_UPC_PREFIX = "04"
_SERIAL_DIGITS = 9
_MAX_SERIAL = (10**_SERIAL_DIGITS) - 1


class UpcGenerationError(Exception):
    """Raised when the ``04``-prefixed serial space is exhausted."""


def compute_check_digit(eleven_digits: str) -> str:
    """Return the GS1 UPC-A check digit for an 11-digit base."""
    if len(eleven_digits) != 11 or not eleven_digits.isdigit():
        raise ValueError("base must be exactly 11 digits")
    odd_sum = sum(int(d) for d in eleven_digits[::2])
    even_sum = sum(int(d) for d in eleven_digits[1::2])
    total = odd_sum * 3 + even_sum
    return str((10 - total % 10) % 10)


def is_valid_upc_a(value: str) -> bool:
    return (
        len(value) == 12
        and value.isdigit()
        and compute_check_digit(value[:11]) == value[-1]
    )


def build_internal_upc_a(serial: int) -> str:
    """Build the UPC-A for a given serial under the internal prefix."""
    if serial < 1 or serial > _MAX_SERIAL:
        raise ValueError("internal UPC serial is outside the supported range")
    first_eleven = f"{INTERNAL_UPC_PREFIX}{serial:0{_SERIAL_DIGITS}d}"
    return first_eleven + compute_check_digit(first_eleven)


def _serial_from_internal_upc(value: str | None) -> int | None:
    if (
        not value
        or len(value) != 12
        or not value.startswith(INTERNAL_UPC_PREFIX)
        or not value.isdigit()
    ):
        return None
    if not is_valid_upc_a(value):
        return None
    return int(value[len(INTERNAL_UPC_PREFIX):11])


async def allocate_unique_upc(session: AsyncSession) -> str:
    """Mint the next unused internal UPC-A.

    Scans existing products whose UPC starts with ``04`` (including
    archived ones, so reserved serials stay reserved), then issues
    ``max(serial) + 1``. If a hand-assigned UPC has claimed that slot,
    the next free serial is returned.
    """
    result = await session.execute(
        select(Product.upc).where(Product.upc.like(f"{INTERNAL_UPC_PREFIX}%"))
    )
    existing = {upc for upc in result.scalars().all() if upc}
    max_serial = max(
        (
            serial
            for serial in (_serial_from_internal_upc(upc) for upc in existing)
            if serial is not None
        ),
        default=0,
    )

    for serial in range(max_serial + 1, _MAX_SERIAL + 1):
        candidate = build_internal_upc_a(serial)
        if candidate not in existing:
            return candidate

    raise UpcGenerationError(
        "no internal UPC-A values remain in the 04 namespace"
    )


__all__ = [
    "INTERNAL_UPC_PREFIX",
    "UpcGenerationError",
    "allocate_unique_upc",
    "build_internal_upc_a",
    "compute_check_digit",
    "is_valid_upc_a",
]
