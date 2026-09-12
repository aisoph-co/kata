"""Async SQLAlchemy engine and session factory (spec §Decisions: SQLAlchemy 2,
asyncpg). `DATABASE_URL` is asyncpg's own `postgresql://` form; SQLAlchemy's
asyncpg dialect needs the `+asyncpg` driver segment, so it is rewritten here.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def async_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _engine, _sessionmaker
    if _sessionmaker is None:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_async_engine(async_url(url), pool_pre_ping=True, pool_recycle=300)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _get_sessionmaker()() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """A session for callers outside the request cycle (startup seed, cron
    entry points) that can't use the `get_session` FastAPI dependency."""
    async with _get_sessionmaker()() as session:
        yield session
