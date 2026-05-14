"""Pydantic schemas for the users-admin API surface (Phase 1.6)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.auth import Role


class UserResponse(BaseModel):
    """Single user, as returned by GET /users and PATCH /users/{id}."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_login: datetime | None = None


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=255)
    role: Role


class UserCreateResponse(BaseModel):
    """Same as UserResponse but carries the freshly-generated password.

    The password appears in the response body exactly once — there is no
    other surface that returns it. The router never logs it.
    """

    model_config = ConfigDict(from_attributes=True)

    user: UserResponse
    generated_password: str


class UserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: Role | None = None
    is_active: bool | None = None


class UserListResponse(BaseModel):
    items: list[UserResponse]
    next_cursor: str | None = None


class PasswordResetResponse(BaseModel):
    user_id: uuid.UUID
    generated_password: str
