"""Async SQLAlchemy engine + session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.settings import Settings


class Base(DeclarativeBase):
    """Declarative base for ORM models. Empty for now."""


def make_engine(settings: Settings) -> AsyncEngine:
    """Create an async engine from settings.

    SQLite (used by unit tests) doesn't accept pool sizing args, so we branch.
    """
    url = settings.database_url
    if url.startswith("sqlite"):
        # In-memory SQLite needs StaticPool so every session shares the same
        # underlying connection; otherwise each session gets its own empty DB.
        kwargs: dict[str, object] = {"echo": settings.db_echo, "future": True}
        if ":memory:" in url:
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        return create_async_engine(url, **kwargs)
    return create_async_engine(
        url,
        echo=settings.db_echo,
        future=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
    )


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Populated by app startup (see app.main). Tests can override via the
# FastAPI dependency_overrides mechanism.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def set_engine(engine: AsyncEngine) -> None:
    global _engine, _session_factory
    _engine = engine
    _session_factory = make_session_factory(engine)


def get_engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database engine has not been initialized.")
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an AsyncSession."""
    if _session_factory is None:
        raise RuntimeError("Session factory has not been initialized.")
    async with _session_factory() as session:
        yield session


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
