"""`learning_service.seed`: loading a named scenario into Postgres (SQLite
here, generic types only) must be idempotent across a restart, and
`/health` must report which scenario `LEARNING_SEED` names. Scenario-specific
acceptance criteria (exact counts, Quinn as sole operator, ...) live in
`test_ferry_seed.py`.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, Course  # noqa: E402
from learning_service.identity.models import Base, Person  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.seed import main, seed  # noqa: E402


@pytest.fixture
async def sessionmaker(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/seed_test.db"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_first_seed_writes_expected_rows(sessionmaker):
    async with sessionmaker() as session:
        seeded = await seed(session, "ferry")

    assert seeded is True

    async with sessionmaker() as session:
        persons = (await session.execute(select(Person))).scalars().all()
        concepts = (await session.execute(select(Concept))).scalars().all()
    assert len(persons) == 10
    assert len(concepts) == 14


async def test_restart_with_same_db_is_idempotent(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")

    # A restart against the same database must not duplicate rows.
    async with sessionmaker() as session:
        seeded_again = await seed(session, "ferry")

    assert seeded_again is False

    async with sessionmaker() as session:
        persons = (await session.execute(select(Person))).scalars().all()
    assert len(persons) == 10  # no duplicates


async def test_unknown_scenario_raises(sessionmaker):
    async with sessionmaker() as session:
        with pytest.raises(ValueError):
            await seed(session, "not-a-real-scenario")


def test_cli_rejects_unknown_or_missing_scenario():
    assert main([]) == 2
    assert main(["bogus"]) == 2


async def test_course_row_matches_expected_shape(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")
        course = (await session.execute(select(Course))).scalar_one()

    assert course.title == "Ferry Payments Core"
    assert course.slug == "ferry-payments-core"


def test_health_reports_the_configured_seed_scenario(monkeypatch):
    monkeypatch.setenv("LEARNING_SEED", "ferry")
    client = TestClient(app)
    assert client.get("/health").json()["seed"] == "ferry"


def test_health_reports_none_when_seed_names_an_unknown_scenario(monkeypatch):
    monkeypatch.setenv("LEARNING_SEED", "not-a-real-scenario")
    client = TestClient(app)
    assert client.get("/health").json()["seed"] == "none"


def test_health_reports_none_when_learning_seed_is_unset(monkeypatch):
    monkeypatch.delenv("LEARNING_SEED", raising=False)
    client = TestClient(app)
    assert client.get("/health").json()["seed"] == "none"

