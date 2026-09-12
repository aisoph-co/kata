"""`POST /admin/replay` (spec §Learning engine, "Replay"; §Testing,
"Replay": "after the golden scenario, replayed derived state equals live
state exactly" — KAT-X4).
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import CardState, ConceptState  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402

TOKEN_HEADER = {"Authorization": "Bearer test-token"}


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
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.fixture
async def golden(session: AsyncSession):
    """A small golden scenario: three learners, two concepts (one gating
    the other), a handful of items, and a spread of reviews across several
    simulated days and item kinds — enough to exercise FSRS reps/lapses and
    BKT's correct/incorrect branches together."""
    people = []
    for i in range(3):
        person = Person(display_name=f"Learner {i}", email=f"learner{i}@example.com")
        session.add(person)
        await session.flush()
        session.add(Identity(person_id=person.id, platform="slack", external_id=f"U{i}"))
        people.append(person)

    course = Course(title="Payments")
    session.add(course)
    await session.flush()
    foundation = Concept(course_id=course.id, slug="found", title="Foundation")
    advanced = Concept(course_id=course.id, slug="adv", title="Advanced")
    session.add_all([foundation, advanced])
    await session.flush()
    session.add(ConceptEdge(from_concept_id=foundation.id, to_concept_id=advanced.id, kind="prerequisite"))

    f_mcq = Item(concept_id=foundation.id, kind="mcq", prompt="f-mcq", payload={"options": ["a", "b"], "correct_index": 1}, status="published")
    f_self = Item(concept_id=foundation.id, kind="self_rated", prompt="f-self", payload={"answer": "x"}, status="published")
    a_mcq = Item(concept_id=advanced.id, kind="mcq", prompt="a-mcq", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    session.add_all([f_mcq, f_self, a_mcq])
    await session.commit()
    return {"people": people, "foundation": foundation, "advanced": advanced, "items": [f_mcq, f_self, a_mcq]}


def _auth(external_id: str) -> dict:
    return {**TOKEN_HEADER, "X-Acting-Identity": f"slack:{external_id}"}


async def _snapshot(session: AsyncSession):
    await session.commit()
    cards = (await session.execute(select(CardState).order_by(CardState.person_id, CardState.item_id))).scalars().all()
    concepts = (await session.execute(select(ConceptState).order_by(ConceptState.person_id, ConceptState.concept_id))).scalars().all()
    return (
        [(c.person_id, c.item_id, round(c.stability, 6), round(c.difficulty, 6), c.due_at, c.state, c.step, c.reps, c.lapses) for c in cards],
        [(c.person_id, c.concept_id, round(c.p_known, 9), c.reviews, c.last_review_at) for c in concepts],
    )


async def test_replay_rebuilds_from_an_empty_log(client, session):
    r = client.post("/admin/replay", headers=TOKEN_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "replayed_reviews": 0, "card_state_count": 0, "concept_state_count": 0}


async def test_replay_requires_the_service_token(client, session):
    r = client.post("/admin/replay")
    assert r.status_code == 401


async def test_replayed_state_equals_live_state(client, session, golden):
    people = golden["people"]
    f_mcq, f_self, a_mcq = golden["items"]

    # Interleave several kinds of outcomes across the three learners so both
    # BKT branches (correct/incorrect) and FSRS lapses are exercised.
    submissions = [
        (people[0], f_mcq, {"choice": 1}, "k1"),  # correct
        (people[0], f_mcq, {"choice": 0}, "k2"),  # wrong -> lapse
        (people[0], f_self, {"rating": 4}, "k3"),
        (people[1], f_mcq, {"choice": 1}, "k1"),
        (people[1], a_mcq, {"choice": 0}, "k2"),  # locked, but grading doesn't check locks
        (people[2], f_self, {"rating": 1}, "k1"),
        (people[2], f_self, {"rating": 4}, "k2"),
        (people[0], f_mcq, {"choice": 1}, "k4"),
    ]
    for person, item, response, key in submissions:
        r = client.post(
            "/me/reviews",
            json={"item_id": item.id, "idempotency_key": key, "response": response},
            headers=_auth_for(person),
        )
        assert r.status_code == 200, r.text

    live_snapshot = await _snapshot(session)

    r = client.post("/admin/replay", headers=TOKEN_HEADER)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["replayed_reviews"] == len(submissions)

    replayed_snapshot = await _snapshot(session)
    assert replayed_snapshot == live_snapshot


def _auth_for(person) -> dict:
    # people were seeded with external_id U0/U1/U2 in fixture order; map by
    # display_name suffix instead of relying on closures across fixtures.
    idx = person.display_name.rsplit(" ", 1)[-1]
    return _auth(f"U{idx}")
