"""Withholding-profile service (Phase 9.7, #159).

Pure CRUD + a few helpers used by ``bill_payments.record_payment``:

* :func:`resolve_for_vendor` — walk per-vendor → setting → none.
* :func:`vendor_ytd_payment_total` — sum of ``state=posted`` bill
  payments for the vendor in the current (or supplied) calendar year.
* :func:`build_ytd_report` — per-vendor YTD paid + withheld for the
  year, feeds the 1099-NEC preparation flow.
"""

from __future__ import annotations

import io
import uuid
from collections.abc import Sequence
from csv import writer as csv_writer
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import asc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.types import tax as tax_events
from app.models.account import Account, AccountType
from app.models.bill_payment import BillPayment, BillPaymentApplication, BillPaymentState
from app.models.vendor import Vendor
from app.models.withholding_profile import WithholdingProfile
from app.schemas.events import EventCreate
from app.services import event_store
from app.services.settings.service import SettingsService

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class WithholdingServiceError(Exception):
    """Base. Routers default to 400."""


class WithholdingProfileNotFoundError(WithholdingServiceError):
    """Mapped to 404."""


class DuplicateWithholdingProfileError(WithholdingServiceError):
    """``code`` collides with another row."""


class InvalidWithholdingProfileError(WithholdingServiceError):
    """Field-level validation (bad account type, out-of-range rate, etc.)."""


# ---------------------------------------------------------------------------
# Decimal helpers
# ---------------------------------------------------------------------------

_QUANTUM = Decimal("0.000001")
_ZERO = Decimal("0")
_ONE = Decimal("1")


def _q(value: Decimal | str | int | float) -> Decimal:
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(_QUANTUM, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------


async def _emit(
    session: AsyncSession,
    *,
    event_type: str,
    aggregate_id: uuid.UUID,
    payload: dict[str, Any],
    actor_user_id: uuid.UUID | None,
) -> None:
    await event_store.append(
        EventCreate(
            type=event_type,
            aggregate_type=tax_events.AGGREGATE_TYPE_WITHHOLDING_PROFILE,
            aggregate_id=aggregate_id,
            payload=payload,
            occurred_at=datetime.now(UTC),
            correlation_id=uuid.uuid4(),
            actor_user_id=actor_user_id,
        ),
        session=session,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _validate_account(session: AsyncSession, *, account_id: uuid.UUID, role: str) -> Account:
    acct = (
        await session.execute(select(Account).where(Account.id == account_id))
    ).scalar_one_or_none()
    if acct is None:
        raise InvalidWithholdingProfileError(f"{role}: account not found ({account_id})")
    if acct.is_archived:
        raise InvalidWithholdingProfileError(f"{role}: account {acct.code!r} is archived")
    actual = acct.type.value if hasattr(acct.type, "value") else acct.type
    if actual != AccountType.LIABILITY.value:
        raise InvalidWithholdingProfileError(
            f"{role}: account {acct.code!r} has type {actual!r}; expected 'liability'"
        )
    return acct


def _serialize(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _payload_create(profile: WithholdingProfile) -> dict[str, Any]:
    return {
        "withholding_profile_id": str(profile.id),
        "code": profile.code,
        "name": profile.name,
        "jurisdiction": profile.jurisdiction,
        "rate": str(profile.rate),
        "liability_account_id": str(profile.liability_account_id),
        "threshold_per_year": str(profile.threshold_per_year)
        if profile.threshold_per_year is not None
        else None,
        "form_kind": profile.form_kind,
        "is_active": profile.is_active,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


async def create_profile(
    session: AsyncSession,
    *,
    code: str,
    name: str,
    jurisdiction: str,
    rate: Decimal | str,
    liability_account_id: uuid.UUID,
    threshold_per_year: Decimal | str | None = None,
    form_kind: str | None = None,
    notes: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> WithholdingProfile:
    code_s = (code or "").strip()
    name_s = (name or "").strip()
    juris_s = (jurisdiction or "").strip()
    if not code_s:
        raise InvalidWithholdingProfileError("code is required")
    if not name_s:
        raise InvalidWithholdingProfileError("name is required")
    if not juris_s:
        raise InvalidWithholdingProfileError("jurisdiction is required")

    rate_d = _q(rate)
    if rate_d < _ZERO or rate_d > _ONE:
        raise InvalidWithholdingProfileError(f"rate must be between 0 and 1 (got {rate_d})")

    threshold_d: Decimal | None = None
    if threshold_per_year is not None:
        threshold_d = _q(threshold_per_year)
        if threshold_d < _ZERO:
            raise InvalidWithholdingProfileError("threshold_per_year must be >= 0")

    await _validate_account(session, account_id=liability_account_id, role="liability_account_id")

    profile = WithholdingProfile(
        id=uuid.uuid4(),
        code=code_s,
        name=name_s,
        jurisdiction=juris_s,
        rate=rate_d,
        liability_account_id=liability_account_id,
        threshold_per_year=threshold_d,
        form_kind=form_kind,
        notes=notes,
        is_active=True,
        created_by_user_id=actor_user_id,
    )
    session.add(profile)
    try:
        await session.flush()
    except IntegrityError as exc:
        raise DuplicateWithholdingProfileError(
            f"withholding profile code {code_s!r} already exists"
        ) from exc

    await _emit(
        session,
        event_type=tax_events.TYPE_WITHHOLDING_PROFILE_CREATED,
        aggregate_id=profile.id,
        payload=_payload_create(profile),
        actor_user_id=actor_user_id,
    )
    return profile


_UPDATABLE = (
    "name",
    "jurisdiction",
    "rate",
    "liability_account_id",
    "threshold_per_year",
    "form_kind",
    "notes",
)


async def update_profile(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    patch: dict[str, Any],
    actor_user_id: uuid.UUID | None = None,
) -> WithholdingProfile:
    profile = await get_profile(session, profile_id)

    illegal = set(patch) - set(_UPDATABLE)
    if illegal:
        raise InvalidWithholdingProfileError(
            f"cannot update fields {sorted(illegal)} on withholding_profile"
        )

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for field, new_value in patch.items():
        if field == "rate":
            new_value = _q(new_value)
            if new_value < _ZERO or new_value > _ONE:
                raise InvalidWithholdingProfileError(
                    f"rate must be between 0 and 1 (got {new_value})"
                )
        elif field == "threshold_per_year":
            if new_value is not None:
                new_value = _q(new_value)
                if new_value < _ZERO:
                    raise InvalidWithholdingProfileError("threshold_per_year must be >= 0")
        elif field == "liability_account_id" and new_value is not None:
            await _validate_account(session, account_id=new_value, role="liability_account_id")
        current = getattr(profile, field)
        if current == new_value:
            continue
        before[field] = _serialize(current)
        after[field] = _serialize(new_value)
        setattr(profile, field, new_value)

    if not before:
        return profile

    await session.flush()
    await _emit(
        session,
        event_type=tax_events.TYPE_WITHHOLDING_PROFILE_UPDATED,
        aggregate_id=profile.id,
        payload={
            "withholding_profile_id": str(profile.id),
            "before": before,
            "after": after,
        },
        actor_user_id=actor_user_id,
    )
    return profile


async def archive_profile(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    actor_user_id: uuid.UUID | None = None,
) -> WithholdingProfile:
    profile = await get_profile(session, profile_id)
    if not profile.is_active:
        return profile
    profile.is_active = False
    await session.flush()
    await _emit(
        session,
        event_type=tax_events.TYPE_WITHHOLDING_PROFILE_ARCHIVED,
        aggregate_id=profile.id,
        payload={
            "withholding_profile_id": str(profile.id),
            "code": profile.code,
            "name": profile.name,
        },
        actor_user_id=actor_user_id,
    )
    return profile


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def get_profile(session: AsyncSession, profile_id: uuid.UUID) -> WithholdingProfile:
    row = (
        await session.execute(select(WithholdingProfile).where(WithholdingProfile.id == profile_id))
    ).scalar_one_or_none()
    if row is None:
        raise WithholdingProfileNotFoundError(str(profile_id))
    return row


@dataclass
class WithholdingProfilePage:
    items: list[WithholdingProfile]
    next_cursor: str | None


async def list_profiles(
    session: AsyncSession,
    *,
    active: bool | None = None,
    search: str | None = None,
    limit: int = 50,
) -> list[WithholdingProfile]:
    stmt = select(WithholdingProfile)
    if active is not None:
        stmt = stmt.where(WithholdingProfile.is_active == active)
    if search:
        like = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                WithholdingProfile.code.ilike(like),
                WithholdingProfile.name.ilike(like),
                WithholdingProfile.jurisdiction.ilike(like),
            )
        )
    stmt = stmt.order_by(asc(WithholdingProfile.code)).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


# ---------------------------------------------------------------------------
# Resolution + YTD
# ---------------------------------------------------------------------------


async def resolve_for_vendor(session: AsyncSession, *, vendor: Vendor) -> WithholdingProfile | None:
    """Resolve the active withholding profile for ``vendor``.

    Order: vendor.withholding_profile_id → setting
    ``ap.default_withholding_profile_id`` → None. Inactive profiles
    short-circuit to None.
    """
    if vendor.withholding_profile_id is not None:
        profile = (
            await session.execute(
                select(WithholdingProfile).where(
                    WithholdingProfile.id == vendor.withholding_profile_id
                )
            )
        ).scalar_one_or_none()
        if profile is not None and profile.is_active:
            return profile

    default_id = await SettingsService.get("ap.default_withholding_profile_id", session=session)
    if default_id is None:
        return None
    if isinstance(default_id, str):
        default_id = uuid.UUID(default_id)
    profile = (
        await session.execute(select(WithholdingProfile).where(WithholdingProfile.id == default_id))
    ).scalar_one_or_none()
    if profile is None or not profile.is_active:
        return None
    return profile


async def vendor_ytd_payment_total(
    session: AsyncSession,
    *,
    vendor_id: uuid.UUID,
    year: int | None = None,
    as_of: datetime | None = None,
) -> Decimal:
    """Return Σ ``amount`` of ``state=posted`` bill payments for the vendor
    in the requested calendar year.

    ``as_of`` defaults to "now"; payments after that timestamp are
    ignored — used by the bill-payment apply flow to compute YTD BEFORE
    the in-flight payment.
    """
    now = as_of or datetime.now(UTC)
    yr = year if year is not None else now.year
    start = datetime(yr, 1, 1, tzinfo=UTC)
    end = datetime(yr + 1, 1, 1, tzinfo=UTC)
    stmt = (
        select(func.coalesce(func.sum(BillPayment.amount), 0))
        .where(BillPayment.vendor_id == vendor_id)
        .where(BillPayment.state == BillPaymentState.POSTED)
        .where(BillPayment.occurred_at >= start)
        .where(BillPayment.occurred_at < end)
        .where(BillPayment.occurred_at <= now)
    )
    raw = (await session.execute(stmt)).scalar_one()
    return _q(Decimal(str(raw or 0)))


# ---------------------------------------------------------------------------
# YTD report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class YtdRow:
    vendor_id: str
    vendor_number: str
    display_name: str
    profile_id: str | None
    profile_code: str | None
    form_kind: str | None
    total_paid: Decimal
    total_withheld: Decimal


@dataclass(frozen=True)
class YtdReport:
    year: int
    rows: list[YtdRow]
    grand_total_paid: Decimal
    grand_total_withheld: Decimal


async def build_ytd_report(
    session: AsyncSession,
    *,
    year: int,
    profile_id: uuid.UUID | None = None,
) -> YtdReport:
    """Year-end roll-up: per-vendor total paid + total withheld."""
    start = datetime(year, 1, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC)

    # Total paid per vendor (state=posted bill payments).
    paid_stmt = (
        select(
            BillPayment.vendor_id,
            func.coalesce(func.sum(BillPayment.amount), 0).label("total_paid"),
        )
        .where(BillPayment.state == BillPaymentState.POSTED)
        .where(BillPayment.occurred_at >= start)
        .where(BillPayment.occurred_at < end)
        .group_by(BillPayment.vendor_id)
    )
    paid_by_vendor: dict[uuid.UUID, Decimal] = {
        row[0]: _q(Decimal(str(row[1] or 0))) for row in (await session.execute(paid_stmt)).all()
    }

    # Withheld per vendor — join applications back to payments.
    wh_stmt = (
        select(
            BillPayment.vendor_id,
            BillPaymentApplication.withholding_profile_id,
            func.coalesce(func.sum(BillPaymentApplication.withholding_amount), 0).label(
                "total_withheld"
            ),
        )
        .select_from(BillPaymentApplication)
        .join(BillPayment, BillPayment.id == BillPaymentApplication.bill_payment_id)
        .where(BillPayment.state == BillPaymentState.POSTED)
        .where(BillPayment.occurred_at >= start)
        .where(BillPayment.occurred_at < end)
        .where(BillPaymentApplication.withholding_amount > 0)
    )
    if profile_id is not None:
        wh_stmt = wh_stmt.where(BillPaymentApplication.withholding_profile_id == profile_id)
    wh_stmt = wh_stmt.group_by(BillPayment.vendor_id, BillPaymentApplication.withholding_profile_id)
    wh_rows = list((await session.execute(wh_stmt)).all())

    # Roll up per-vendor (take the first profile we see — typically there
    # is only one per vendor per year).
    withheld_by_vendor: dict[uuid.UUID, Decimal] = {}
    profile_by_vendor: dict[uuid.UUID, uuid.UUID | None] = {}
    for vid, pid, total in wh_rows:
        withheld_by_vendor[vid] = withheld_by_vendor.get(vid, _ZERO) + _q(Decimal(str(total or 0)))
        profile_by_vendor.setdefault(vid, pid)

    vendor_ids: Sequence[uuid.UUID]
    if profile_id is not None:
        vendor_ids = list(withheld_by_vendor.keys())
    else:
        vendor_ids = list({*paid_by_vendor.keys(), *withheld_by_vendor.keys()})
    vendors: dict[uuid.UUID, Vendor] = {}
    profiles: dict[uuid.UUID, WithholdingProfile] = {}
    if vendor_ids:
        vendor_rows = (
            (await session.execute(select(Vendor).where(Vendor.id.in_(vendor_ids)))).scalars().all()
        )
        vendors = {v.id: v for v in vendor_rows}
        all_pids = {pid for pid in profile_by_vendor.values() if pid is not None}
        if all_pids:
            prof_rows = (
                (
                    await session.execute(
                        select(WithholdingProfile).where(WithholdingProfile.id.in_(all_pids))
                    )
                )
                .scalars()
                .all()
            )
            profiles = {p.id: p for p in prof_rows}

    rows: list[YtdRow] = []
    grand_paid = _ZERO
    grand_withheld = _ZERO
    for vid in sorted(
        vendor_ids, key=lambda v: vendors.get(v).vendor_number if vendors.get(v) else str(v)
    ):
        v = vendors.get(vid)
        total_paid = paid_by_vendor.get(vid, _ZERO)
        total_withheld = withheld_by_vendor.get(vid, _ZERO)
        pid = profile_by_vendor.get(vid)
        prof = profiles.get(pid) if pid else None
        rows.append(
            YtdRow(
                vendor_id=str(vid),
                vendor_number=v.vendor_number if v else "?",
                display_name=v.display_name if v else "?",
                profile_id=str(pid) if pid else None,
                profile_code=prof.code if prof else None,
                form_kind=prof.form_kind if prof else None,
                total_paid=total_paid,
                total_withheld=total_withheld,
            )
        )
        grand_paid += total_paid
        grand_withheld += total_withheld

    return YtdReport(
        year=year,
        rows=rows,
        grand_total_paid=grand_paid,
        grand_total_withheld=grand_withheld,
    )


def ytd_report_to_csv(report: YtdReport) -> str:
    buf = io.StringIO()
    w = csv_writer(buf)
    w.writerow(
        [
            "vendor_number",
            "display_name",
            "profile_code",
            "form_kind",
            "total_paid",
            "total_withheld",
        ]
    )
    for row in report.rows:
        w.writerow(
            [
                row.vendor_number,
                row.display_name,
                row.profile_code or "",
                row.form_kind or "",
                str(row.total_paid),
                str(row.total_withheld),
            ]
        )
    w.writerow(
        [
            "GRAND TOTAL",
            "",
            "",
            "",
            str(report.grand_total_paid),
            str(report.grand_total_withheld),
        ]
    )
    return buf.getvalue()


__all__ = [
    "DuplicateWithholdingProfileError",
    "InvalidWithholdingProfileError",
    "WithholdingProfileNotFoundError",
    "WithholdingProfilePage",
    "WithholdingServiceError",
    "YtdReport",
    "YtdRow",
    "archive_profile",
    "build_ytd_report",
    "create_profile",
    "get_profile",
    "list_profiles",
    "resolve_for_vendor",
    "update_profile",
    "vendor_ytd_payment_total",
    "ytd_report_to_csv",
]
