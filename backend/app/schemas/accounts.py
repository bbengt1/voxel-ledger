"""Pydantic schemas for the accounts API surface (Phase 4.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccountTypeLiteral = Literal[
    "asset",
    "liability",
    "equity",
    "revenue",
    "expense",
]


class ParentChainItem(BaseModel):
    """Leaner shape for the parent chain — avoids recursive parent_chain
    blowup on the wire."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    type: AccountTypeLiteral


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    type: AccountTypeLiteral
    parent_account_id: uuid.UUID | None = None
    description: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    # Populated only by ``GET /accounts/{id}``; list endpoints leave it empty.
    parent_chain: list[ParentChainItem] = Field(default_factory=list)


class AccountCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    type: AccountTypeLiteral
    parent_account_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4096)


class AccountUpdateRequest(BaseModel):
    """PATCH-style. ``code`` and ``type`` are intentionally NOT here — the
    service rejects them via a separate guard if a client sneaks them in."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_account_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=4096)


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    next_cursor: str | None = None


class AccountTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    type: AccountTypeLiteral
    parent_account_id: uuid.UUID | None = None
    description: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    children: list[AccountTreeNode] = Field(default_factory=list)


AccountTreeNode.model_rebuild()


class AccountTreeResponse(BaseModel):
    items: list[AccountTreeNode]
