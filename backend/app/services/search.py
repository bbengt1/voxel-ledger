"""Global search service (#251).

A single endpoint operators can hit from the top-bar omnibar to jump
to any entity by name, number, or other obvious identifier. Each
entity kind contributes a small ILIKE query against the columns the
operator would type to find a row.

Performance: each kind is its own bounded query (LIMIT 5). Substring
``ILIKE`` is fine at the data volumes this single-tenant app sees;
when an operator complains about latency, the next step is a Postgres
``tsvector`` index, not a different shape of API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bill import Bill
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.models.job import Job
from app.models.material import Material
from app.models.printer import Printer
from app.models.product import Product
from app.models.quote import Quote
from app.models.refund import Refund
from app.models.sale import Sale
from app.models.sales_channel import SalesChannel
from app.models.supply import Supply
from app.models.vendor import Vendor

# Per-kind cap to keep one noisy entity from drowning out the others.
PER_KIND_LIMIT = 5
# Total cap so a wildcard-ish query returns a bounded payload.
TOTAL_LIMIT = 20


@dataclass(frozen=True)
class SearchHit:
    kind: str
    id: str
    label: str
    sublabel: str | None
    href: str


def _wrap(needle: str) -> str:
    """Return the ILIKE pattern for a substring match."""
    safe = needle.replace("%", r"\%").replace("_", r"\_")
    return f"%{safe}%"


async def _products(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Product)
        .where(Product.is_archived.is_(False))
        .where(
            or_(
                Product.name.ilike(pattern),
                Product.sku.ilike(pattern),
                Product.upc.ilike(pattern),
            )
        )
        .order_by(Product.name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="product",
            id=str(p.id),
            label=p.name,
            sublabel=p.sku,
            href=f"/catalog/products/{p.id}",
        )
        for p in rows
    ]


async def _materials(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Material)
        .where(Material.is_archived.is_(False))
        .where(
            or_(
                Material.name.ilike(pattern),
                Material.brand.ilike(pattern),
            )
        )
        .order_by(Material.name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="material",
            id=str(m.id),
            label=m.name,
            sublabel=m.brand,
            href=f"/catalog/materials/{m.id}",
        )
        for m in rows
    ]


async def _supplies(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Supply)
        .where(Supply.is_archived.is_(False))
        .where(
            or_(
                Supply.name.ilike(pattern),
                Supply.vendor.ilike(pattern),
                Supply.item_number.ilike(pattern),
            )
        )
        .order_by(Supply.name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="supply",
            id=str(s.id),
            label=s.name,
            sublabel=s.vendor,
            href=f"/catalog/supplies/{s.id}",
        )
        for s in rows
    ]


async def _customers(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Customer)
        .where(Customer.state != "archived")
        .where(
            or_(
                Customer.display_name.ilike(pattern),
                Customer.legal_name.ilike(pattern),
                Customer.primary_email.ilike(pattern),
            )
        )
        .order_by(Customer.display_name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="customer",
            id=str(c.id),
            label=c.display_name,
            sublabel=c.primary_email,
            href=f"/customers/{c.id}",
        )
        for c in rows
    ]


async def _vendors(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Vendor)
        .where(Vendor.state != "archived")
        .where(
            or_(
                Vendor.display_name.ilike(pattern),
                Vendor.legal_name.ilike(pattern),
                Vendor.primary_email.ilike(pattern),
            )
        )
        .order_by(Vendor.display_name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="vendor",
            id=str(v.id),
            label=v.display_name,
            sublabel=v.primary_email,
            href=f"/vendors/{v.id}",
        )
        for v in rows
    ]


async def _sales(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Sale)
        .where(Sale.sale_number.ilike(pattern))
        .order_by(Sale.sale_number.desc())
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="sale",
            id=str(s.id),
            label=s.sale_number,
            sublabel=getattr(s, "customer_name", None),
            href=f"/sales/{s.id}",
        )
        for s in rows
    ]


async def _invoices(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Invoice)
        .where(Invoice.invoice_number.ilike(pattern))
        .order_by(Invoice.invoice_number.desc())
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="invoice",
            id=str(i.id),
            label=i.invoice_number,
            sublabel=None,
            href=f"/invoices/{i.id}",
        )
        for i in rows
    ]


async def _quotes(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Quote)
        .where(Quote.quote_number.ilike(pattern))
        .order_by(Quote.quote_number.desc())
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="quote",
            id=str(q.id),
            label=q.quote_number,
            sublabel=None,
            href=f"/quotes/{q.id}",
        )
        for q in rows
    ]


async def _refunds(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Refund)
        .where(Refund.refund_number.ilike(pattern))
        .order_by(Refund.refund_number.desc())
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="refund",
            id=str(r.id),
            label=r.refund_number,
            sublabel=None,
            href=f"/sales/refunds/{r.id}",
        )
        for r in rows
    ]


async def _jobs(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Job)
        .where(Job.job_number.ilike(pattern))
        .order_by(Job.job_number.desc())
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="job",
            id=str(j.id),
            label=j.job_number,
            sublabel=None,
            href=f"/production/jobs/{j.id}",
        )
        for j in rows
    ]


async def _bills(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Bill)
        .where(Bill.bill_number.ilike(pattern))
        .order_by(Bill.bill_number.desc())
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="bill",
            id=str(b.id),
            label=b.bill_number,
            sublabel=None,
            href=f"/bills/{b.id}",
        )
        for b in rows
    ]


async def _printers(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(Printer)
        .where(Printer.is_archived.is_(False))
        .where(
            or_(
                Printer.name.ilike(pattern),
                Printer.slug.ilike(pattern),
            )
        )
        .order_by(Printer.name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="printer",
            id=str(p.id),
            label=p.name,
            sublabel=p.slug,
            href=f"/production/printers/{p.id}",
        )
        for p in rows
    ]


async def _channels(session: AsyncSession, pattern: str) -> list[SearchHit]:
    stmt = (
        select(SalesChannel)
        .where(SalesChannel.is_active.is_(True))
        .where(
            or_(
                SalesChannel.name.ilike(pattern),
                SalesChannel.slug.ilike(pattern),
            )
        )
        .order_by(SalesChannel.name)
        .limit(PER_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        SearchHit(
            kind="channel",
            id=str(c.id),
            label=c.name,
            sublabel=c.slug,
            href="/sales/channels",
        )
        for c in rows
    ]


_KIND_ORDER = (
    "product",
    "material",
    "supply",
    "customer",
    "vendor",
    "sale",
    "invoice",
    "quote",
    "refund",
    "job",
    "bill",
    "printer",
    "channel",
)


async def search(session: AsyncSession, query: str) -> list[dict[str, Any]]:
    """Run every per-kind search and return up to ``TOTAL_LIMIT`` hits.

    Empty or whitespace-only queries return an empty list — the UI
    short-circuits this case too, but defending here keeps the route
    consistent.
    """
    needle = (query or "").strip()
    if not needle:
        return []
    pattern = _wrap(needle)

    buckets: dict[str, list[SearchHit]] = {}
    for fn, kind in (
        (_products, "product"),
        (_materials, "material"),
        (_supplies, "supply"),
        (_customers, "customer"),
        (_vendors, "vendor"),
        (_sales, "sale"),
        (_invoices, "invoice"),
        (_quotes, "quote"),
        (_refunds, "refund"),
        (_jobs, "job"),
        (_bills, "bill"),
        (_printers, "printer"),
        (_channels, "channel"),
    ):
        try:
            buckets[kind] = await fn(session, pattern)
        except Exception:  # noqa: BLE001
            # One broken kind shouldn't sink the whole search.
            buckets[kind] = []

    out: list[dict[str, Any]] = []
    for kind in _KIND_ORDER:
        for hit in buckets.get(kind, []):
            out.append(
                {
                    "kind": hit.kind,
                    "id": hit.id,
                    "label": hit.label,
                    "sublabel": hit.sublabel,
                    "href": hit.href,
                }
            )
            if len(out) >= TOTAL_LIMIT:
                return out
    return out
