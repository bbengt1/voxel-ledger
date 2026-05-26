"""UPC-A generator (#249-followup).

Mints a fresh 12-digit UPC-A code: 11 random digits + a mod-10 check
digit. The allocator retries against the products table until it finds
a value not already in use, so callers get a UPC that the partial
unique index ``ux_product_upc_not_null`` will accept.

The check digit follows the GS1 UPC-A algorithm:

  - sum the digits in odd positions (1st, 3rd, ..., 11th) and multiply
    by 3,
  - add the digits in even positions (2nd, 4th, ..., 10th),
  - the check digit is the smallest value that, added to the running
    total, makes it a multiple of 10 — i.e. ``(10 - total % 10) % 10``.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product


class UpcGenerationError(Exception):
    """Raised when the allocator exhausts its retry budget without
    finding an unused UPC. With ~10^11 candidate codes a collision in
    the configured retries is essentially impossible — this is a
    defence-in-depth signal, not an expected error."""


def compute_check_digit(eleven_digits: str) -> str:
    """Return the GS1 UPC-A check digit for an 11-digit base."""
    if len(eleven_digits) != 11 or not eleven_digits.isdigit():
        raise ValueError("base must be exactly 11 digits")
    odd_sum = sum(int(d) for d in eleven_digits[::2])  # positions 1,3,5,7,9,11
    even_sum = sum(int(d) for d in eleven_digits[1::2])  # positions 2,4,6,8,10
    total = odd_sum * 3 + even_sum
    return str((10 - total % 10) % 10)


def generate_upc_a() -> str:
    """Return a single random UPC-A (12 digits, check-digit included)."""
    base = "".join(str(secrets.randbelow(10)) for _ in range(11))
    return base + compute_check_digit(base)


async def _upc_in_use(session: AsyncSession, upc: str) -> bool:
    stmt = select(Product.id).where(Product.upc == upc)
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def allocate_unique_upc(session: AsyncSession, *, max_attempts: int = 10) -> str:
    """Mint a UPC-A guaranteed not to collide with an existing product.

    Each candidate is checked against the products table; the retry
    loop terminates on the first miss. ``max_attempts`` caps the loop
    for safety — at 10^11 candidates a single retry is already
    overwhelmingly likely to succeed.
    """
    for _ in range(max_attempts):
        candidate = generate_upc_a()
        if not await _upc_in_use(session, candidate):
            return candidate
    raise UpcGenerationError(
        f"could not allocate a unique UPC after {max_attempts} attempts"
    )


__all__ = [
    "UpcGenerationError",
    "allocate_unique_upc",
    "compute_check_digit",
    "generate_upc_a",
]
