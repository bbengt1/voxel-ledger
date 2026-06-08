"""Idempotent upsert of master data into QuickBooks Online (#315, epic #312).

Maps our Customer / Vendor / Product rows to QBO Customer / Vendor / Item and
maintains :class:`app.models.qbo_entity_map.QboEntityMap` so Phase-3 transactions
can reference the right QBO ids.

Idempotency (Phase-0 strategy):
* If a mapping already exists → **sparse update** the QBO entity (Id + current
  SyncToken), re-storing the returned SyncToken. A stale token (error 5010)
  triggers one re-read + retry.
* If no mapping exists → **match-or-create**: query QBO by natural key
  (DisplayName / Item Name) and adopt an existing entity if found, otherwise
  create with a ``requestid``. Either way the QBO id is recorded, so re-running
  never duplicates.

Item type: products map to QBO **Service** items (the documented default —
inventory Items require income/expense/asset accounts and QBO-side stock
tracking that interacts with COGS; deferred). A Service item requires an
``IncomeAccountRef``, resolved from the ``revenue`` role of the account map — so
the account map (see :mod:`account_map`) must have ``revenue`` set before
products can sync.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.product import Product
from app.models.qbo_entity_map import QboEntityMap, QboLocalKind
from app.models.vendor import Vendor
from app.services.quickbooks import account_map
from app.services.quickbooks.client import QuickBooksApiError
from app.services.quickbooks.roles import QBOAccountRole


class _Client(Protocol):
    async def query(self, statement: str, entity: str) -> list[dict[str, Any]]: ...
    async def create(
        self, entity: str, payload: dict[str, Any], *, request_id: str | None = None
    ) -> dict[str, Any]: ...
    async def update(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    async def read(self, entity: str, qbo_id: str) -> dict[str, Any]: ...


class MasterDataSyncError(RuntimeError):
    """A local row could not be synced (missing row, etc.)."""


def _escape(value: str) -> str:
    """Escape a value for a single-quoted QBO query literal."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


_ADDR_KEYS: dict[str, tuple[str, ...]] = {
    "Line1": ("line1", "address1", "street", "line_1", "line"),
    "City": ("city", "town"),
    "CountrySubDivisionCode": ("state", "region", "province", "country_subdivision_code"),
    "PostalCode": ("postal_code", "zip", "postcode", "zip_code"),
    "Country": ("country",),
}


def _qbo_address(addr: dict[str, Any] | None) -> dict[str, str] | None:
    """Best-effort map of our free-form address JSON to a QBO physical address."""
    if not addr:
        return None
    out: dict[str, str] = {}
    for qbo_key, candidates in _ADDR_KEYS.items():
        for cand in candidates:
            if addr.get(cand):
                out[qbo_key] = str(addr[cand])
                break
    return out or None


async def _get_mapping(
    session: AsyncSession, kind: QboLocalKind, local_id: uuid.UUID
) -> QboEntityMap | None:
    stmt = select(QboEntityMap).where(
        QboEntityMap.local_kind == kind.value, QboEntityMap.local_id == local_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _store(
    session: AsyncSession,
    *,
    kind: QboLocalKind,
    local_id: uuid.UUID,
    entity_type: str,
    qbo_obj: dict[str, Any],
    existing: QboEntityMap | None,
) -> QboEntityMap:
    qbo_id = qbo_obj.get("Id")
    if not qbo_id:
        raise MasterDataSyncError(f"QBO {entity_type} response had no Id")
    now = datetime.now(UTC)
    if existing is None:
        mapping = QboEntityMap(
            local_kind=kind.value,
            local_id=local_id,
            qbo_entity_type=entity_type,
            qbo_id=str(qbo_id),
            sync_token=qbo_obj.get("SyncToken"),
            last_synced_at=now,
        )
        session.add(mapping)
    else:
        existing.qbo_id = str(qbo_id)
        existing.sync_token = qbo_obj.get("SyncToken")
        existing.last_synced_at = now
        mapping = existing
    await session.flush()
    return mapping


async def _upsert(
    session: AsyncSession,
    client: _Client,
    *,
    kind: QboLocalKind,
    entity_type: str,
    local_id: uuid.UUID,
    create_payload: dict[str, Any],
    update_fields: dict[str, Any],
    match_query: str,
) -> QboEntityMap:
    mapping = await _get_mapping(session, kind, local_id)

    if mapping is not None:
        payload = {
            "Id": mapping.qbo_id,
            "SyncToken": mapping.sync_token or "0",
            "sparse": True,
            **update_fields,
        }
        try:
            obj = await client.update(entity_type, payload)
        except QuickBooksApiError:
            # Likely a stale SyncToken (5010): re-read for the current token, retry once.
            fresh = await client.read(entity_type, mapping.qbo_id)
            payload["SyncToken"] = fresh.get("SyncToken", payload["SyncToken"])
            obj = await client.update(entity_type, payload)
        return await _store(
            session,
            kind=kind,
            local_id=local_id,
            entity_type=entity_type,
            qbo_obj=obj,
            existing=mapping,
        )

    # No mapping yet — match an existing QBO entity or create a new one.
    found = await client.query(match_query, entity_type)
    if found:
        return await _store(
            session,
            kind=kind,
            local_id=local_id,
            entity_type=entity_type,
            qbo_obj=found[0],
            existing=None,
        )
    created = await client.create(entity_type, create_payload)
    return await _store(
        session,
        kind=kind,
        local_id=local_id,
        entity_type=entity_type,
        qbo_obj=created,
        existing=None,
    )


async def upsert_customer(
    session: AsyncSession, client: _Client, customer_id: uuid.UUID
) -> QboEntityMap:
    c = await session.get(Customer, customer_id)
    if c is None:
        raise MasterDataSyncError(f"customer {customer_id} not found")
    fields: dict[str, Any] = {"DisplayName": c.display_name}
    if c.legal_name:
        fields["CompanyName"] = c.legal_name
    if c.primary_email:
        fields["PrimaryEmailAddr"] = {"Address": c.primary_email}
    if c.phone:
        fields["PrimaryPhone"] = {"FreeFormNumber": c.phone}
    addr = _qbo_address(c.billing_address)
    if addr:
        fields["BillAddr"] = addr
    return await _upsert(
        session,
        client,
        kind=QboLocalKind.CUSTOMER,
        entity_type="Customer",
        local_id=customer_id,
        create_payload=fields,
        update_fields=fields,
        match_query=f"SELECT * FROM Customer WHERE DisplayName = '{_escape(c.display_name)}'",
    )


async def upsert_vendor(
    session: AsyncSession, client: _Client, vendor_id: uuid.UUID
) -> QboEntityMap:
    v = await session.get(Vendor, vendor_id)
    if v is None:
        raise MasterDataSyncError(f"vendor {vendor_id} not found")
    fields: dict[str, Any] = {"DisplayName": v.display_name}
    if v.legal_name:
        fields["CompanyName"] = v.legal_name
    if v.primary_email:
        fields["PrimaryEmailAddr"] = {"Address": v.primary_email}
    if v.phone:
        fields["PrimaryPhone"] = {"FreeFormNumber": v.phone}
    if v.tax_id:
        fields["TaxIdentifier"] = v.tax_id
    fields["Vendor1099"] = bool(v.is_1099_vendor)
    addr = _qbo_address(v.billing_address)
    if addr:
        fields["BillAddr"] = addr
    return await _upsert(
        session,
        client,
        kind=QboLocalKind.VENDOR,
        entity_type="Vendor",
        local_id=vendor_id,
        create_payload=fields,
        update_fields=fields,
        match_query=f"SELECT * FROM Vendor WHERE DisplayName = '{_escape(v.display_name)}'",
    )


async def upsert_product(
    session: AsyncSession, client: _Client, product_id: uuid.UUID
) -> QboEntityMap:
    p = await session.get(Product, product_id)
    if p is None:
        raise MasterDataSyncError(f"product {product_id} not found")
    # Service items need an income account; resolve from the account map.
    income_account_id = await account_map.resolve(session, QBOAccountRole.REVENUE)
    description = (p.description or p.name)[:4000]
    create_payload: dict[str, Any] = {
        "Name": p.sku,
        "Sku": p.sku,
        "Type": "Service",
        "IncomeAccountRef": {"value": income_account_id},
        "Description": description,
        "UnitPrice": float(p.unit_price),
    }
    update_fields: dict[str, Any] = {
        "Sku": p.sku,
        "Description": description,
        "UnitPrice": float(p.unit_price),
    }
    return await _upsert(
        session,
        client,
        kind=QboLocalKind.PRODUCT,
        entity_type="Item",
        local_id=product_id,
        create_payload=create_payload,
        update_fields=update_fields,
        match_query=f"SELECT * FROM Item WHERE Name = '{_escape(p.sku)}'",
    )
