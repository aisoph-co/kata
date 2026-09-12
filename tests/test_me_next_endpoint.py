"""`GET /me/next` (spec §Learning engine, "Next-item selection", §Testing
"Unit": "next-item ordering (overdue first, unlocked only, depth and focus
weighting, co-review)").
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import CardState, ConceptState  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}


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


async def _person(session, external_id="U1"):
    person = Person(display_name="Ada", email=f"{external_id}@example.com")
    session.add(person)
    await session.flush()
    session.add(Identity(person_id=person.id, platform="slack", external_id=external_id))
    await session.commit()
    return person


async def _course(session):
    course = Course(title="Payments")
    session.add(course)
    await session.flush()
    return course


def test_unknown_identity_is_403(client, session):
    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 403  # no person seeded yet


async def test_new_items_from_unlocked_concept_only(client, session):
    await _person(session)
    course = await _course(session)
    foundation = Concept(course_id=course.id, slug="found", title="Foundation")
    advanced = Concept(course_id=course.id, slug="adv", title="Advanced")
    session.add_all([foundation, advanced])
    await session.flush()
    session.add(ConceptEdge(from_concept_id=foundation.id, to_concept_id=advanced.id, kind="prerequisite"))
    f_item = Item(concept_id=foundation.id, kind="mcq", prompt="q1", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    a_item = Item(concept_id=advanced.id, kind="mcq", prompt="q2", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    draft_item = Item(concept_id=foundation.id, kind="mcq", prompt="q3", payload={}, status="draft")
    session.add_all([f_item, a_item, draft_item])
    await session.commit()

    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    item_ids = [i["id"] for i in body["items"]]
    assert f_item.id in item_ids
    assert a_item.id not in item_ids  # locked: foundation not mastered
    assert draft_item.id not in item_ids  # not published
    # answer keys stripped
    for i in body["items"]:
        assert "correct_index" not in i["payload"]


async def test_overdue_reviews_come_before_new_items(client, session):
    person = await _person(session)
    course = await _course(session)
    concept = Concept(course_id=course.id, slug="c1", title="C1")
    session.add(concept)
    await session.flush()
    overdue_item = Item(concept_id=concept.id, kind="mcq", prompt="overdue", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    new_item = Item(concept_id=concept.id, kind="mcq", prompt="new", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    session.add_all([overdue_item, new_item])
    await session.flush()
    now = datetime.now(timezone.utc)
    session.add(
        CardState(
            person_id=person.id, item_id=overdue_item.id, stability=2.0, difficulty=5.0,
            due_at=now - timedelta(days=1), state="review", reps=1, lapses=0, last_review_at=now - timedelta(days=5),
        )
    )
    await session.commit()

    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["id"] == overdue_item.id


async def test_all_mastered_reason_when_nothing_due_or_new(client, session):
    person = await _person(session)
    course = await _course(session)
    concept = Concept(course_id=course.id, slug="c1", title="C1", mastery_threshold=0.85)
    session.add(concept)
    await session.flush()
    session.add(ConceptState(person_id=person.id, concept_id=concept.id, p_known=0.9, reviews=5))
    await session.commit()

    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["reason"] == "all_mastered"


async def test_blocked_by_prerequisites_reason(client, session):
    await _person(session)
    course = await _course(session)
    foundation = Concept(course_id=course.id, slug="found", title="Foundation")
    advanced = Concept(course_id=course.id, slug="adv", title="Advanced")
    session.add_all([foundation, advanced])
    await session.flush()
    session.add(ConceptEdge(from_concept_id=foundation.id, to_concept_id=advanced.id, kind="prerequisite"))
    # only the locked concept has items; foundation (unlocked) has none.
    a_item = Item(concept_id=advanced.id, kind="mcq", prompt="q", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    session.add(a_item)
    await session.commit()

    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["reason"] == "blocked_by_prerequisites"


async def test_limit_is_clamped_between_1_and_20(client, session):
    person = await _person(session)
    course = await _course(session)
    concept = Concept(course_id=course.id, slug="c1", title="C1")
    session.add(concept)
    await session.flush()
    for i in range(3):
        session.add(Item(concept_id=concept.id, kind="mcq", prompt=f"q{i}", payload={"options": ["a", "b"], "correct_index": 0}, status="published"))
    await session.commit()

    r = client.get("/me/next?limit=1", headers=AUTH)
    assert r.status_code == 200
    assert len(r.json()["items"]) == 1


async def test_co_review_pulls_in_a_related_neighbour(client, session):
    person = await _person(session)
    course = await _course(session)
    a = Concept(course_id=course.id, slug="a", title="A")
    b = Concept(course_id=course.id, slug="b", title="B")
    session.add_all([a, b])
    await session.flush()
    session.add(ConceptEdge(from_concept_id=a.id, to_concept_id=b.id, kind="related", weight=0.8))
    a_item = Item(concept_id=a.id, kind="mcq", prompt="a-item", payload={"options": ["x", "y"], "correct_index": 0}, status="published")
    b_item = Item(concept_id=b.id, kind="mcq", prompt="b-item", payload={"options": ["x", "y"], "correct_index": 0}, status="published")
    session.add_all([a_item, b_item])
    # p_known for `a` below the co-review threshold (0.5) -> its neighbour
    # `b` should be pulled in alongside it.
    session.add(ConceptState(person_id=person.id, concept_id=a.id, p_known=0.3, reviews=1))
    await session.commit()

    r = client.get("/me/next?limit=20", headers=AUTH)
    assert r.status_code == 200
    item_ids = [i["id"] for i in r.json()["items"]]
    assert a_item.id in item_ids
    assert b_item.id in item_ids
