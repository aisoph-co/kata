"""`GET /me/answers` + `DELETE /me/answers` (spec §Privacy and retention,
§API): the acting person's own short-answer submissions, paginated, with
90-day retention purged inline, and immediate self-deletion.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.privacy.models import Answer  # noqa: E402

AUTH_1 = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}
AUTH_2 = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U2"}


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
async def seeded(session: AsyncSession):
    p1 = Person(display_name="Ada", email="ada@example.com")
    p2 = Person(display_name="Bea", email="bea@example.com")
    session.add_all([p1, p2])
    await session.flush()
    session.add_all(
        [
            Identity(person_id=p1.id, platform="slack", external_id="U1"),
            Identity(person_id=p2.id, platform="slack", external_id="U2"),
        ]
    )
    await session.commit()
    return {"p1": p1, "p2": p2}


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


async def test_answers_are_scoped_to_the_acting_person(client, session, seeded):
    session.add(Answer(review_id="r1", person_id=seeded["p1"].id, text="mine"))
    session.add(Answer(review_id="r2", person_id=seeded["p2"].id, text="not mine"))
    await session.commit()

    r = client.get("/me/answers", headers=AUTH_1)
    assert r.status_code == 200
    texts = [a["text"] for a in r.json()["answers"]]
    assert texts == ["mine"]


async def test_pagination_via_cursor(client, session, seeded):
    now = datetime.now(timezone.utc)
    for i in range(5):
        session.add(Answer(review_id=f"r{i}", person_id=seeded["p1"].id, text=f"answer-{i}", created_at=now - timedelta(minutes=i)))
    await session.commit()

    first = client.get("/me/answers?limit=2", headers=AUTH_1).json()
    assert len(first["answers"]) == 2
    assert first["next_cursor"] is not None

    second = client.get(f"/me/answers?limit=2&cursor={first['next_cursor']}", headers=AUTH_1).json()
    assert len(second["answers"]) == 2
    assert {a["id"] for a in first["answers"]}.isdisjoint({a["id"] for a in second["answers"]})


async def test_expired_answers_are_purged_on_read(client, session, seeded):
    now = datetime.now(timezone.utc)
    session.add(Answer(review_id="old", person_id=seeded["p1"].id, text="stale", created_at=now - timedelta(days=91)))
    session.add(Answer(review_id="fresh", person_id=seeded["p1"].id, text="fresh", created_at=now))
    await session.commit()

    r = client.get("/me/answers", headers=AUTH_1)
    texts = [a["text"] for a in r.json()["answers"]]
    assert texts == ["fresh"]

    remaining = (await session.execute(select(Answer))).scalars().all()
    assert len(remaining) == 1


async def test_delete_removes_only_the_caller_own_answers(client, session, seeded):
    session.add(Answer(review_id="r1", person_id=seeded["p1"].id, text="mine"))
    session.add(Answer(review_id="r2", person_id=seeded["p2"].id, text="not mine"))
    await session.commit()

    r = client.delete("/me/answers", headers=AUTH_1)
    assert r.status_code == 204

    remaining = (await session.execute(select(Answer))).scalars().all()
    assert [a.person_id for a in remaining] == [seeded["p2"].id]
