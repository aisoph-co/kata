"""Alembic environment: reads `DATABASE_URL` the same way the app does (spec
§Deployment: `DATABASE_URL` to Neon; migrations run on start). Async, since
the app and all its models are async SQLAlchemy.

Imports every package's `models` module so `Base.metadata` (the
`target_metadata` below) sees every table before `alembic revision
--autogenerate` diffs against it, not just `identity`'s own.
"""

from __future__ import annotations

import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config

from learning_service.db import async_url
from learning_service.identity.models import Base
from learning_service.curriculum import models as _curriculum_models  # noqa: F401
from learning_service.roster import models as _roster_models  # noqa: F401

config = context.config

target_metadata = Base.metadata


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return async_url(url)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": _database_url()},
        prefix="sqlalchemy.",
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
