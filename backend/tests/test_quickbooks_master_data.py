"""QBO master-data mapping + account map (#315, epic #312).

Service-level idempotency (create → re-push update, match-existing, product needs
revenue mapping) exercised with an in-memory fake QBO client, plus the owner-only
admin endpoints (account map CRUD, account list, sync trigger) with the client
monkeypatched in.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

import pytest
from app.api.v1.admin import quickbooks_mapping as qbm
from app.models.auth import Role
from app.models.customer import Customer
from app.models.product import Product
from app.models.qbo_entity_map import QboEntityMap
from app.models.vendor import Vendor
from app.services.auth import create_user
from app.services.quickbooks import account_map, master_data
from app.services.quickbooks.roles import QBOAccountRole
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

QB = "/api/v1/admin/quickbooks"


class FakeQBO:
    """In-memory QBO double implementing the client surface used by Phase 2."""

    def __init__(self) -> None:
        self.store: dict[str, dict[str, dict[str, Any]]] = {}
        self.create_calls: list[tuple[str, dict[str, Any]]] = []
        self._next = 100

    def seed(self, entity: str, obj: dict[str, Any]) -> None:
        self.store.setdefault(entity, {})[obj["Id"]] = obj

    async def query(self, statement: str, entity: str) -> list[dict[str, Any]]:
        if entity == "Account":
            return list(self.store.get("Account", {}).values())
        field = "Name" if re.search(r"\bName =", statement) else "DisplayName"
        m = re.search(r"= '(.*)'", statement)
        value = m.group(1) if m else None
        return [o for o in self.store.get(entity, {}).values() if o.get(field) == value]

    async def create(
        self, entity: str, payload: dict[str, Any], *, request_id: str | None = None
    ) -> dict[str, Any]:
        self.create_calls.append((entity, payload))
        qid = str(self._next)
        self._next += 1
        obj = {**payload, "Id": qid, "SyncToken": "0"}
        self.store.setdefault(entity, {})[qid] = obj
        return obj

    async def update(self, entity: str, payload: dict[str, Any]) -> dict[str, Any]:
        qid = payload["Id"]
        cur = self.store[entity][qid]
        token = str(int(cur.get("SyncToken", "0")) + 1)
        merged = {**cur, **{k: v for k, v in payload.items() if k != "sparse"}, "SyncToken": token}
        self.store[entity][qid] = merged
        return merged

    async def read(self, entity: str, qbo_id: str) -> dict[str, Any]:
        return self.store[entity][qbo_id]


async def _seed_owner(client: AsyncClient, session: AsyncSession) -> str:
    await create_user(
        session,
        email="owner@example.com",
        password="pw-correct",
        full_name="owner",
        role=Role.OWNER,
        bcrypt_rounds=4,
    )
    await session.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"email": "owner@example.com", "password": "pw-correct"}
    )
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# service: idempotent upsert
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_upsert_customer_creates_then_updates_idempotently(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    cust = Customer(customer_number="C-1", display_name="Acme Co", primary_email="a@acme.test")
    app_session.add(cust)
    await app_session.commit()
    fake = FakeQBO()

    m1 = await master_data.upsert_customer(app_session, fake, cust.id)
    await app_session.commit()
    assert len(fake.create_calls) == 1
    assert m1.qbo_entity_type == "Customer"
    assert m1.sync_token == "0"
    first_qbo_id = m1.qbo_id

    # Re-running must NOT create a duplicate — it goes through the update path.
    m2 = await master_data.upsert_customer(app_session, fake, cust.id)
    await app_session.commit()
    assert len(fake.create_calls) == 1  # still one create
    assert m2.qbo_id == first_qbo_id
    assert m2.sync_token == "1"  # SyncToken advanced by the update
    # Exactly one mapping row exists.
    rows = (await app_session.execute(select(QboEntityMap))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_upsert_matches_existing_qbo_entity_without_creating(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    cust = Customer(customer_number="C-2", display_name="Globex")
    app_session.add(cust)
    await app_session.commit()
    fake = FakeQBO()
    # A QBO customer with the same DisplayName already exists.
    fake.seed("Customer", {"Id": "555", "DisplayName": "Globex", "SyncToken": "3"})

    mapping = await master_data.upsert_customer(app_session, fake, cust.id)
    await app_session.commit()
    assert fake.create_calls == []  # adopted, not created
    assert mapping.qbo_id == "555"
    assert mapping.sync_token == "3"


@pytest.mark.asyncio
async def test_upsert_vendor_creates(client: AsyncClient, app_session: AsyncSession) -> None:
    v = Vendor(vendor_number="V-1", display_name="Supplier Inc", is_1099_vendor=True)
    app_session.add(v)
    await app_session.commit()
    fake = FakeQBO()
    mapping = await master_data.upsert_vendor(app_session, fake, v.id)
    await app_session.commit()
    assert mapping.qbo_entity_type == "Vendor"
    assert fake.create_calls[0][1]["Vendor1099"] is True


@pytest.mark.asyncio
async def test_upsert_product_requires_revenue_mapping_then_creates_item(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    p = Product(sku="SKU-1", name="Widget", unit_price=Decimal("9.99"))
    app_session.add(p)
    await app_session.commit()
    fake = FakeQBO()

    # No account map yet → product sync is blocked.
    with pytest.raises(account_map.AccountRoleNotMappedError):
        await master_data.upsert_product(app_session, fake, p.id)

    await account_map.set_mappings(
        app_session,
        {"revenue": {"qbo_account_id": "77", "qbo_account_name": "Sales"}},
        actor_user_id=None,
    )
    await app_session.commit()

    mapping = await master_data.upsert_product(app_session, fake, p.id)
    await app_session.commit()
    assert mapping.qbo_entity_type == "Item"
    created = fake.create_calls[0][1]
    assert created["Type"] == "Service"
    assert created["Name"] == "SKU-1"
    assert created["IncomeAccountRef"] == {"value": "77"}


@pytest.mark.asyncio
async def test_upsert_missing_local_row_raises(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    import uuid

    with pytest.raises(master_data.MasterDataSyncError):
        await master_data.upsert_customer(app_session, FakeQBO(), uuid.uuid4())


# --------------------------------------------------------------------------- #
# service: account map
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_account_map_set_resolve_and_unmapped(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    # Everything unmapped initially.
    assert len(await account_map.unmapped_roles(app_session)) == len(account_map.all_roles())
    with pytest.raises(account_map.AccountRoleNotMappedError):
        await account_map.resolve(app_session, QBOAccountRole.REVENUE)

    await account_map.set_mappings(
        app_session,
        {"revenue": {"qbo_account_id": "10", "qbo_account_name": "Sales Income"}},
        actor_user_id=None,
    )
    await app_session.commit()
    assert await account_map.resolve(app_session, QBOAccountRole.REVENUE) == "10"
    assert "revenue" not in await account_map.unmapped_roles(app_session)


@pytest.mark.asyncio
async def test_account_map_rejects_unknown_role(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    with pytest.raises(account_map.UnknownAccountRoleError):
        await account_map.set_mappings(
            app_session, {"not_a_role": {"qbo_account_id": "1"}}, actor_user_id=None
        )


# --------------------------------------------------------------------------- #
# HTTP endpoints
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_account_map_endpoints_roundtrip(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _seed_owner(client, app_session)

    r = await client.get(f"{QB}/account-map", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "revenue" in body["roles"]
    assert body["mappings"] == {}
    assert "revenue" in body["unmapped"]

    r = await client.put(
        f"{QB}/account-map",
        headers=_auth(token),
        json={"mappings": {"revenue": {"qbo_account_id": "42", "qbo_account_name": "Sales"}}},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mappings"]["revenue"]["qbo_account_id"] == "42"
    assert "revenue" not in body["unmapped"]


@pytest.mark.asyncio
async def test_account_map_put_rejects_unknown_role(
    client: AsyncClient, app_session: AsyncSession
) -> None:
    token = await _seed_owner(client, app_session)
    r = await client.put(
        f"{QB}/account-map",
        headers=_auth(token),
        json={"mappings": {"bogus": {"qbo_account_id": "1"}}},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_list_accounts_endpoint(
    client: AsyncClient, app_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _seed_owner(client, app_session)
    fake = FakeQBO()
    fake.seed(
        "Account",
        {"Id": "1", "Name": "Sales", "AccountType": "Income", "Classification": "Revenue"},
    )
    fake.seed(
        "Account", {"Id": "2", "Name": "Checking", "AccountType": "Bank", "Classification": "Asset"}
    )
    monkeypatch.setattr(qbm, "QuickBooksClient", lambda session, settings: fake)

    r = await client.get(f"{QB}/accounts", headers=_auth(token))
    assert r.status_code == 200, r.text
    names = {a["name"] for a in r.json()}
    assert names == {"Sales", "Checking"}


@pytest.mark.asyncio
async def test_sync_endpoint_upserts_customer(
    client: AsyncClient, app_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = await _seed_owner(client, app_session)
    cust = Customer(customer_number="C-9", display_name="Initech")
    app_session.add(cust)
    await app_session.commit()
    fake = FakeQBO()
    monkeypatch.setattr(qbm, "QuickBooksClient", lambda session, settings: fake)

    r = await client.post(f"{QB}/sync/customer/{cust.id}", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["qbo_entity_type"] == "Customer"
    assert body["qbo_id"]
    assert len(fake.create_calls) == 1


@pytest.mark.asyncio
async def test_sync_endpoint_bad_kind(client: AsyncClient, app_session: AsyncSession) -> None:
    import uuid

    token = await _seed_owner(client, app_session)
    r = await client.post(f"{QB}/sync/widget/{uuid.uuid4()}", headers=_auth(token))
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_mapping_endpoints_owner_only(client: AsyncClient, app_session: AsyncSession) -> None:
    await create_user(
        app_session,
        email="book@example.com",
        password="pw-correct",
        full_name="book",
        role=Role.BOOKKEEPER,
        bcrypt_rounds=4,
    )
    await app_session.commit()
    r = await client.post(
        "/api/v1/auth/login", json={"email": "book@example.com", "password": "pw-correct"}
    )
    token = r.json()["access_token"]
    assert (await client.get(f"{QB}/account-map", headers=_auth(token))).status_code == 403


@pytest.mark.asyncio
async def test_phase2_endpoints_in_openapi(client: AsyncClient) -> None:
    paths = (await client.get("/api/v1/openapi.json")).json()["paths"]
    assert f"{QB}/accounts" in paths
    assert f"{QB}/account-map" in paths
    assert f"{QB}/sync/{{kind}}/{{local_id}}" in paths
