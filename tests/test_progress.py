"""`GET /me/progress` + `GET /me/due-summary` (spec §API): per-concept
mastery/due/unlocked state, and `PersonLearningSummary` (Contract v1.2.1:
retention bands, `bypass_rate`, `calibration`, `review_count`,
`last_active`).
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
async def seeded(session: AsyncSession):
    person = Person(display_name="Ada", email="ada@example.com")
    session.add(person)
    await session.flush()
    session.add(Identity(person_id=person.id, platform="slack", external_id="U1"))
    course = Course(title="Payments")
    session.add(course)
    await session.flush()
    foundation = Concept(course_id=course.id, slug="found", title="Foundation", mastery_threshold=0.85)
    advanced = Concept(course_id=course.id, slug="adv", title="Advanced")
    session.add_all([foundation, advanced])
    await session.flush()
    session.add(ConceptEdge(from_concept_id=foundation.id, to_concept_id=advanced.id, kind="prerequisite"))
    item = Item(concept_id=foundation.id, kind="mcq", prompt="q", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    session.add(item)
    await session.commit()
    return {"person": person, "foundation": foundation, "advanced": advanced, "item": item}


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_progress_defaults_before_any_review(client, seeded):
    r = client.get("/me/progress", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    by_id = {c["concept_id"]: c for c in body["concepts"]}
    found = by_id[seeded["foundation"].id]
    assert found["p_known"] == 0.20
    assert found["mastered"] is False
    assert found["unlocked"] is True
    adv = by_id[seeded["advanced"].id]
    assert adv["unlocked"] is False
    summary = body["summary"]
    assert summary["review_count"] == 0
    assert summary["last_active"] is None
    assert summary["bypass_rate"] is None
    assert summary["calibration"] is None
    assert summary["retention"] == {
        "d1": {"accuracy": None, "samples": 0},
        "d7": {"accuracy": None, "samples": 0},
        "d30": {"accuracy": None, "samples": 0},
    }


def test_progress_summary_after_reviews(client, seeded):
    r = client.post(
        "/me/reviews",
        json={"item_id": seeded["item"].id, "idempotency_key": "k1", "response": {"choice": 0}, "confidence": 4},
        headers=AUTH,
    )
    assert r.status_code == 200

    body = client.get("/me/progress", headers=AUTH).json()
    summary = body["summary"]
    assert summary["review_count"] == 1
    assert summary["last_active"] is not None
    assert summary["bypass_rate"] == 0.0
    # confidence=4 (scaled (4-1)/4=0.75), accuracy=1.0 (correct) -> -0.25
    assert summary["calibration"] == pytest.approx(-0.25)


def test_history_returns_chart_rows_for_the_acting_person(client, seeded):
    submitted = client.post(
        "/me/reviews",
        json={"item_id": seeded["item"].id, "idempotency_key": "history-k1", "response": {"choice": 0}},
        headers=AUTH,
    )
    assert submitted.status_code == 200

    history = client.get("/me/history?days=30", headers=AUTH)
    assert history.status_code == 200
    assert history.json()["days"] == 30
    row = history.json()["reviews"][-1]
    assert row["concept_id"] == seeded["foundation"].id
    assert row["item_id"] == seeded["item"].id
    assert row["rating"] == "good"
    assert row["bypassed"] is False

    progress = client.get("/me/progress", headers=AUTH).json()
    concept = next(item for item in progress["concepts"] if item["concept_id"] == seeded["foundation"].id)
    assert row["p_known_after"] == concept["p_known"]


async def test_progress_reflects_a_bypassed_review_in_bypass_rate(client, seeded):
    r = client.post(
        "/me/reviews",
        json={"item_id": seeded["item"].id, "idempotency_key": "k1", "response": {"choice": 0}, "bypassed": True},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = client.get("/me/progress", headers=AUTH).json()
    assert body["summary"]["bypass_rate"] == 1.0


async def test_due_summary_counts_overdue_and_new(client, seeded, session):
    person = seeded["person"]
    now = datetime.now(timezone.utc)
    session.add(
        CardState(
            person_id=person.id, item_id="ghost-item", stability=2.0, difficulty=5.0,
            due_at=now - timedelta(days=1), state="review", reps=1, lapses=0, last_review_at=now - timedelta(days=3),
        )
    )
    await session.commit()

    r = client.get("/me/due-summary", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["overdue_count"] == 1
    assert body["new_available_count"] == 1  # seeded["item"], foundation is unlocked
    assert body["due_count"] == 2


async def test_due_summary_excludes_new_items_from_a_mastered_concept(client, seeded, session):
    person = seeded["person"]
    session.add(ConceptState(person_id=person.id, concept_id=seeded["foundation"].id, p_known=0.95, reviews=3))
    await session.commit()

    r = client.get("/me/due-summary", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["new_available_count"] == 0
