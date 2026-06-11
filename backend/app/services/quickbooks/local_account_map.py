"""Local chart-of-accounts ``Account`` → QBO Account id map (#316, epic #312).

The role map (:mod:`app.services.quickbooks.account_map`) covers posting lines
that resolve through an abstract role. Two sites don't have a fixed role —
inter-account transfers and the bank auto-matcher post to *arbitrary* accounts
chosen per transaction. This map resolves those specific local accounts to the
QBO account ids the operator selected.

:func:`resolve` is called by the local-JE builder at drain time; the enqueuing
site only stores the local ``account_id`` in the payload.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.qbo_local_account_map import QboLocalAccountMap


class LocalAccountNotMappedError(RuntimeError):
    """A transfer/matcher posting hit a local account with no QBO mapping yet."""


class UnknownLocalAccountError(ValueError):
    """A local account id that doesn't exist was supplied to :func:`set_mappings`."""


async def get_map(session: AsyncSession) -> dict[str, dict[str, str | None]]:
    """Return ``{local_account_id: {qbo_account_id, qbo_account_name}}``."""
    rows = (await session.execute(select(QboLocalAccountMap))).scalars().all()
    return {
        str(r.account_id): {
            "qbo_account_id": r.qbo_account_id,
            "qbo_account_name": r.qbo_account_name,
        }
        for r in rows
    }


async def resolve(session: AsyncSession, account_id: uuid.UUID | str) -> str:
    """Return the QBO account id mapped for ``account_id`` or raise."""
    key = account_id if isinstance(account_id, uuid.UUID) else uuid.UUID(str(account_id))
    row = (
        await session.execute(
            select(QboLocalAccountMap).where(QboLocalAccountMap.account_id == key)
        )
    ).scalar_one_or_none()
    if row is None:
        raise LocalAccountNotMappedError(
            f"local account {key} is not mapped to a QBO account; set it in the "
            "QuickBooks admin panel (local-account-map) before syncing transfers/matches"
        )
    return row.qbo_account_id


async def set_mappings(
    session: AsyncSession,
    mappings: dict[str, dict[str, str | None]],
    *,
    actor_user_id: uuid.UUID | None,
) -> None:
    """Upsert local-account→QBO-account mappings.

    ``mappings`` is ``{local_account_id: {qbo_account_id, qbo_account_name?}}``.
    Validates each local account exists. Caller commits."""
    for raw_id, value in mappings.items():
        try:
            account_id = uuid.UUID(str(raw_id))
        except (ValueError, AttributeError) as exc:
            raise UnknownLocalAccountError(f"invalid local account id {raw_id!r}") from exc
        qbo_account_id = value.get("qbo_account_id")
        if not qbo_account_id:
            raise UnknownLocalAccountError(f"account {raw_id} missing qbo_account_id")
        exists = (
            await session.execute(select(Account.id).where(Account.id == account_id))
        ).scalar_one_or_none()
        if exists is None:
            raise UnknownLocalAccountError(f"local account {account_id} does not exist")
        existing = (
            await session.execute(
                select(QboLocalAccountMap).where(QboLocalAccountMap.account_id == account_id)
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                QboLocalAccountMap(
                    account_id=account_id,
                    qbo_account_id=qbo_account_id,
                    qbo_account_name=value.get("qbo_account_name"),
                    updated_by_user_id=actor_user_id,
                )
            )
        else:
            existing.qbo_account_id = qbo_account_id
            existing.qbo_account_name = value.get("qbo_account_name")
            existing.updated_by_user_id = actor_user_id
    await session.flush()
