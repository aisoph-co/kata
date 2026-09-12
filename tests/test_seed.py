"""`learning_service.seed` (spec §Deployment, KATA-4 R6): the vendored seed
data is present, `seed_ferry()` loads it, and re-running it is a no-op.

Uses an in-memory SQLite engine, same convention as `test_admin_roster_
import.py`/`test_identity.py`.
"""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service import seed as seed_module  # noqa: E402
from learning_service.curriculum.models import Course, Item  # noqa: E402
from learning_service.engine.sql_models import ReviewRow  # noqa: E402
from learning_service.identity.models import Base, Person  # noqa: E402


@pytest.fixture
async def session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    class _FakeScope:
        async def __aenter__(self_inner):
            self_inner._s = sessionmaker()
            return self_inner._s

        async def __aexit__(self_inner, *exc):
            await self_inner._s.close()

    monkeypatch.setattr(seed_module, "session_scope", lambda: _FakeScope())

    async with sessionmaker() as s:
        yield s
    await engine.dispose()


def test_seed_data_is_vendored():
    """The image only ever contains this repo, so the seed has to travel
    with it (see `seed.py`'s own module docstring) — never reach across to
    the planning repo at runtime."""
    assert (seed_module.SEED_DATA / "roster.json").is_file()
    assert (seed_module.SEED_DATA / "concepts.json").is_file()
    assert (seed_module.SEED_DATA / "items.json").is_file()
    assert (seed_module.SEED_DATA / "reviews.jsonl").is_file()

    roster = json.loads((seed_module.SEED_DATA / "roster.json").read_text())
    assert len(roster["persons"]) == 10


async def test_seed_ferry_loads_roster_curriculum_and_reviews(session):
    result = await seed_module.seed_ferry()
    assert result["status"] == "loaded"
    assert result["persons_created"] == 10

    persons = (await session.execute(select(Person))).scalars().all()
    assert len(persons) == 10

    courses = (await session.execute(select(Course))).scalars().all()
    assert len(courses) == 1

    items = (await session.execute(select(Item))).scalars().all()
    assert len(items) == result["items"] > 0
    assert all(i.status == "published" for i in items)

    reviews = (await session.execute(select(ReviewRow))).scalars().all()
    assert len(reviews) == result["reviews_loaded"] > 0

    assert result["card_state_count"] > 0
    assert result["concept_state_count"] > 0


async def test_seed_ferry_is_idempotent(session):
    first = await seed_module.seed_ferry()
    assert first["status"] == "loaded"

    second = await seed_module.seed_ferry()
    assert second["status"] == "already_loaded"

    reviews = (await session.execute(select(ReviewRow))).scalars().all()
    assert len(reviews) == first["reviews_loaded"]

    persons = (await session.execute(select(Person))).scalars().all()
    assert len(persons) == 10


async def test_seed_ferry_writes_kata_roster_json(session, tmp_path, monkeypatch):
    target = tmp_path / "roster.json"
    monkeypatch.setenv("KATA_ROSTER_JSON", str(target))

    result = await seed_module.seed_ferry()
    assert result["kata_roster_json"] == str(target)

    written = json.loads(target.read_text())
    # Every seeded person carries a slack_user_id (`docs/seed/0-team/
    # roster.json`), so all ten show up here — the file `hermes_kata.
    # commands.load_roster` reads (KATA-11 -> KATA-4 wiring).
    assert len(written["persons"]) == 10
    assert all({"id", "slack_user_id"} <= p.keys() for p in written["persons"])
