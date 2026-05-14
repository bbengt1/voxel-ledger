"""Race-safe reference number allocator.

# NEVER use COUNT(*) for reference numbering — see v1 issue #243.

Background
----------
In v1 we numbered sales by ``SELECT COUNT(*) + 1 FROM sale``. Under
concurrent writers two carts could read the same count, both assign the
same reference, and one would silently overwrite the other (incident
#243). The fix is a dedicated ``reference_sequence`` table keyed by
``(prefix, year)`` with a single atomic upsert that increments and
returns the new value in one round-trip. No COUNT, no read-modify-write
window, no race.

Allocation
----------
``ReferenceNumberService.allocate(prefix, *, session, year=None)`` issues
the next reference for the ``(prefix, year)`` pair as
``{PREFIX}-{YYYY}-{NNNN}``. Year defaults to the current UTC year, so
sequences naturally reset at the year boundary.

Padding
-------
The numeric suffix is zero-padded to ``DEFAULT_PADDING`` (4) digits.
A prefix can override the default via ``PADDING_OVERRIDES`` (module-level
dict for now; TODO move into the typed settings registry in #25 once it
lands). If ``last_value`` exceeds the configured width we **expand** the
digit count rather than truncate — e.g. value ``10000`` with padding=4
serializes as ``S-2026-10000``. We log a warning the first time a prefix
crosses the threshold so operations notices well before things look weird
on invoices.

Concurrency
-----------
The allocator must be deterministic under concurrent writers. We use
``INSERT ... ON CONFLICT (prefix, year) DO UPDATE SET last_value =
reference_sequence.last_value + 1 RETURNING last_value`` — Postgres
takes a row lock on the conflicting row, runs the increment, and returns
the new value in a single statement. The lock auto-releases on
commit/rollback. SQLite (used by unit tests) supports the same UPSERT
syntax but serializes the entire database under its global write lock;
the headline concurrency property test runs against real PG.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_PADDING = 4

# Per-prefix padding overrides. Module-level for now; TODO(#25 settings
# service) — move into the typed settings registry once the structured
# settings store exists.
PADDING_OVERRIDES: dict[str, int] = {}

# Track which prefixes have already crossed their configured padding so
# the "value exceeds padding" warning fires once per process per prefix
# instead of on every allocation.
_PADDING_OVERFLOW_LOGGED: set[str] = set()

_REF_RE = re.compile(r"^([A-Z]+)-(\d{4})-(\d+)$")


def format_reference(
    prefix: str,
    year: int,
    value: int,
    padding: int = DEFAULT_PADDING,
) -> str:
    """Pure formatter: ``{PREFIX}-{YYYY}-{NNNN}``.

    If ``value`` already has more digits than ``padding`` allows, the
    suffix expands to fit. We never truncate — collisions are forever.
    """
    actual_padding = max(padding, len(str(value)))
    return f"{prefix}-{year:04d}-{str(value).zfill(actual_padding)}"


def parse_reference(ref: str) -> tuple[str, int, int]:
    """Inverse of :func:`format_reference`.

    Raises ``ValueError`` on malformed input. Accepts any non-empty
    numeric suffix (so expanded values like ``S-2026-10000`` round-trip).
    """
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(f"malformed reference {ref!r}; expected PREFIX-YYYY-NNNN")
    return m.group(1), int(m.group(2)), int(m.group(3))


def _padding_for(prefix: str) -> int:
    return PADDING_OVERRIDES.get(prefix, DEFAULT_PADDING)


def _maybe_log_overflow(prefix: str, value: int, padding: int) -> None:
    if value < 10**padding:
        return
    key = f"{prefix}:{padding}"
    if key in _PADDING_OVERFLOW_LOGGED:
        return
    _PADDING_OVERFLOW_LOGGED.add(key)
    logger.warning(
        "reference sequence %s exceeded configured padding=%d (value=%d); "
        "digit count will expand. Bump PADDING_OVERRIDES to silence.",
        prefix,
        padding,
        value,
    )


class ReferenceNumberService:
    """Stateless façade around the atomic upsert allocator."""

    @staticmethod
    async def allocate(
        prefix: str,
        *,
        session: AsyncSession,
        year: int | None = None,
    ) -> str:
        """Allocate and format the next reference for ``(prefix, year)``.

        The caller owns the transaction — we flush but do not commit. The
        row lock taken by the upsert holds until commit/rollback, which
        is the property that serializes concurrent writers.
        """
        target_year = year if year is not None else datetime.now(UTC).year

        # Atomic upsert + increment + RETURNING. Equivalent to
        # SELECT FOR UPDATE then UPDATE in one round-trip; no second
        # query, no race window. This is the whole point of the table.
        stmt = text(
            """
            INSERT INTO reference_sequence (prefix, year, last_value)
            VALUES (:prefix, :year, 1)
            ON CONFLICT (prefix, year)
            DO UPDATE SET last_value = reference_sequence.last_value + 1
            RETURNING last_value
            """
        )
        result = await session.execute(
            stmt,
            {"prefix": prefix, "year": target_year},
        )
        value = int(result.scalar_one())

        padding = _padding_for(prefix)
        _maybe_log_overflow(prefix, value, padding)
        return format_reference(prefix, target_year, value, padding)
