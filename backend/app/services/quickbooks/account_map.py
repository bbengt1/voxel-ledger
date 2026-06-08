"""QBO account map: posting-line role → QBO Account id (#315, epic #312).

Resolves the abstract roles in :mod:`app.services.quickbooks.roles` to the QBO
``Account`` ids the operator selected. Phase 3 postings call :func:`resolve` for
every journal line; :func:`unmapped_roles` is the "is the map complete?" gate.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.qbo_account_map import QboAccountMap
from app.services.quickbooks.roles import QBO_ACCOUNT_ROLE_VALUES, QBOAccountRole


class _Queryable(Protocol):
    async def query(self, statement: str, entity: str) -> list[dict[str, Any]]: ...


class AccountRoleNotMappedError(RuntimeError):
    """A posting needs a role that hasn't been mapped to a QBO account yet."""


class UnknownAccountRoleError(ValueError):
    """A role string outside :class:`QBOAccountRole` was supplied."""


def all_roles() -> list[str]:
    return list(QBO_ACCOUNT_ROLE_VALUES)


async def list_qbo_accounts(client: _Queryable) -> list[dict[str, Any]]:
    """Fetch active QBO accounts to populate the mapping UI choices."""
    rows = await client.query(
        "SELECT Id, Name, AccountType, Classification FROM Account "
        "WHERE Active = true ORDERBY Name MAXRESULTS 1000",
        "Account",
    )
    return [
        {
            "id": row.get("Id"),
            "name": row.get("Name"),
            "account_type": row.get("AccountType"),
            "classification": row.get("Classification"),
        }
        for row in rows
    ]


async def get_map(session: AsyncSession) -> dict[str, dict[str, str | None]]:
    """Return ``{role: {qbo_account_id, qbo_account_name}}`` for mapped roles."""
    rows = (await session.execute(select(QboAccountMap))).scalars().all()
    return {
        r.role: {"qbo_account_id": r.qbo_account_id, "qbo_account_name": r.qbo_account_name}
        for r in rows
    }


async def unmapped_roles(session: AsyncSession) -> list[str]:
    """Roles with no QBO account assigned yet (Phase-3 readiness gate)."""
    mapped = set((await get_map(session)).keys())
    return [role for role in QBO_ACCOUNT_ROLE_VALUES if role not in mapped]


async def resolve(session: AsyncSession, role: QBOAccountRole | str) -> str:
    """Return the QBO account id for ``role`` or raise."""
    key = role.value if isinstance(role, QBOAccountRole) else role
    row = (
        await session.execute(select(QboAccountMap).where(QboAccountMap.role == key))
    ).scalar_one_or_none()
    if row is None:
        raise AccountRoleNotMappedError(
            f"no QBO account mapped for role {key!r}; set it in the QuickBooks admin panel"
        )
    return row.qbo_account_id


async def set_mappings(
    session: AsyncSession,
    mappings: dict[str, dict[str, str | None]],
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Upsert role→account mappings. ``mappings`` is ``{role: {qbo_account_id,
    qbo_account_name?}}``. Validates each role against :class:`QBOAccountRole`.
    Caller commits."""
    valid = set(QBO_ACCOUNT_ROLE_VALUES)
    for role, value in mappings.items():
        if role not in valid:
            raise UnknownAccountRoleError(f"unknown account role {role!r}")
        account_id = value.get("qbo_account_id")
        if not account_id:
            raise UnknownAccountRoleError(f"role {role!r} missing qbo_account_id")
        existing = (
            await session.execute(select(QboAccountMap).where(QboAccountMap.role == role))
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                QboAccountMap(
                    role=role,
                    qbo_account_id=account_id,
                    qbo_account_name=value.get("qbo_account_name"),
                    updated_by_user_id=actor_user_id,
                )
            )
        else:
            existing.qbo_account_id = account_id
            existing.qbo_account_name = value.get("qbo_account_name")
            existing.updated_by_user_id = actor_user_id
    await session.flush()
