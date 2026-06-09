"""Document builders: turn an outbox row into a pushed QBO entity (#316).

A builder is registered per outbox ``kind``. It receives the session, a QBO
client, and the outbox row, builds the QBO document from ``row.payload`` (the
role-tagged spec), pushes it via the client (using ``row.request_id`` for
idempotency), and returns ``(qbo_entity_type, qbo_object)``.

Phase 3a ships the **generic JournalEntry** builder — the fallback for any
posting with no native QBO document. Native builders (Invoice/Bill/Payment/…)
register themselves in Phases 3b-3d. Reversals: the enqueuing site encodes the
reversing direction in ``payload`` (swapped debit/credit) for JE-based postings;
native builders branch on ``row.op`` (void/delete) when those land.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.quickbooks import account_map

if TYPE_CHECKING:
    from app.models.qbo_sync_outbox import QboSyncOutbox

# (entity_type, qbo_object)
BuilderFn = Callable[[AsyncSession, Any, "QboSyncOutbox"], Awaitable[tuple[str, dict[str, Any]]]]

_REGISTRY: dict[str, BuilderFn] = {}


class BuilderError(RuntimeError):
    """A permanent build problem (no builder for the kind, malformed spec)."""


def register_builder(kind: str, fn: BuilderFn) -> None:
    _REGISTRY[kind] = fn


def get_builder(kind: str) -> BuilderFn | None:
    return _REGISTRY.get(kind)


async def build_and_push(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    """Dispatch to the registered builder for ``row.kind`` and push to QBO."""
    builder = get_builder(row.kind)
    if builder is None:
        raise BuilderError(f"no QBO document builder registered for kind {row.kind!r}")
    return await builder(session, client, row)


async def _journal_entry_payload(session: AsyncSession, spec: dict[str, Any]) -> dict[str, Any]:
    """Build a balanced QBO JournalEntry payload from a role-tagged spec."""
    lines = spec.get("lines") or []
    if not lines:
        raise BuilderError("journal_entry spec has no lines")
    qbo_lines: list[dict[str, Any]] = []
    for leg in lines:
        try:
            account_id = await account_map.resolve(session, leg["role"])
        except KeyError as exc:
            raise BuilderError(f"journal_entry line missing 'role': {leg}") from exc
        posting = "Debit" if leg.get("posting") == "debit" else "Credit"
        detail: dict[str, Any] = {
            "PostingType": posting,
            "AccountRef": {"value": account_id},
        }
        entity = leg.get("entity")
        if entity and entity.get("type") and entity.get("qbo_id"):
            detail["Entity"] = {
                "Type": entity["type"],
                "EntityRef": {"value": entity["qbo_id"]},
            }
        line: dict[str, Any] = {
            "DetailType": "JournalEntryLineDetail",
            "Amount": float(leg["amount"]),
            "JournalEntryLineDetail": detail,
        }
        if leg.get("description"):
            line["Description"] = leg["description"]
        qbo_lines.append(line)

    payload: dict[str, Any] = {"Line": qbo_lines}
    if spec.get("doc_number"):
        payload["DocNumber"] = spec["doc_number"]
    if spec.get("private_note"):
        payload["PrivateNote"] = spec["private_note"]
    return payload


async def build_journal_entry(
    session: AsyncSession, client: Any, row: QboSyncOutbox
) -> tuple[str, dict[str, Any]]:
    payload = await _journal_entry_payload(session, row.payload)
    qbo_obj = await client.create("JournalEntry", payload, request_id=row.request_id)
    return "JournalEntry", qbo_obj


register_builder("journal_entry", build_journal_entry)
