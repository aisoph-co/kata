"""`POST /me/reviews` (spec §Learning engine, §API): grading dispatch,
idempotency, `no_grader`, bypass, and the `answer` row a `short_answer`
review writes. Uses an in-memory SQLite engine and the stub grader
(`LEARNING_LLM=stub`), same pattern as the rest of this suite.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, Course, Item  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.privacy.models import Answer  # noqa: E402
from learning_service.reviews import get_llm_client  # noqa: E402
from learning_service.grading.stub import StubGraderClient  # noqa: E402

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
    concept = Concept(course_id=course.id, slug="c1", title="Concept 1")
    session.add(concept)
    await session.flush()
    mcq = Item(
        concept_id=concept.id, kind="mcq", prompt="2+2?",
        payload={"options": ["3", "4"], "correct_index": 1, "explanation": "arithmetic"}, status="published",
    )
    msq = Item(
        concept_id=concept.id, kind="msq", prompt="pick primes",
        payload={"options": ["2", "3", "4"], "correct_indices": [0, 1], "explanation": "primes"}, status="published",
    )
    self_rated = Item(concept_id=concept.id, kind="self_rated", prompt="rate yourself", payload={"answer": "42"}, status="published")
    short_answer = Item(
        concept_id=concept.id, kind="short_answer", prompt="explain it",
        payload={"reference": "ref", "rubric": "widget factory pattern"}, status="published",
    )
    teach_back = Item(concept_id=concept.id, kind="teach_back", prompt="teach it back", payload={"reference": "ref", "rubric": "r"}, status="published")
    session.add_all([mcq, msq, self_rated, short_answer, teach_back])
    await session.commit()
    return {
        "person": person, "course": course, "concept": concept,
        "mcq": mcq, "msq": msq, "self_rated": self_rated, "short_answer": short_answer, "teach_back": teach_back,
    }


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    # Import order across the test suite decides which grader `reviews.py`'s
    # module-level `_llm_client` builds (it reads `LEARNING_LLM` once, at
    # whichever test file first imports `learning_service.main`) — override
    # the dependency directly instead, so this file's `short_answer`
    # grading is deterministic regardless of collection order.
    app.dependency_overrides[get_llm_client] = lambda: StubGraderClient()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_llm_client, None)


def _submit(client, item_id, response, **extra):
    body = {"item_id": item_id, "idempotency_key": "k-1", **extra, "response": response}
    return client.post("/me/reviews", json=body, headers=AUTH)


def test_mcq_correct_advances_card_and_concept_state(client, seeded):
    r = _submit(client, seeded["mcq"].id, {"choice": 1})
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 1.0
    assert body["rating"] == 3
    assert body["correct"] is True
    assert body["explanation"] == "arithmetic"
    assert body["concept"]["p_known"] > 0.20  # advanced past P_INIT


def test_mcq_incorrect(client, seeded):
    r = _submit(client, seeded["mcq"].id, {"choice": 0})
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 0.0
    assert body["rating"] == 1
    assert body["correct"] is False


def test_msq_partial_credit(client, seeded):
    r = _submit(client, seeded["msq"].id, {"choices": [0]})
    assert r.status_code == 200
    assert r.json()["grade"] == 0.5


def test_self_rated_grade_table(client, seeded):
    r = _submit(client, seeded["self_rated"].id, {"rating": 4})
    assert r.status_code == 200
    assert r.json()["grade"] == 1.0
    assert r.json()["rating"] == 4


async def test_short_answer_writes_an_answer_row(client, seeded, session):
    r = _submit(client, seeded["short_answer"].id, {"text": "we used the widget factory pattern"})
    assert r.status_code == 200
    assert r.json()["grade"] == 1.0

    from sqlalchemy import select

    result = await session.execute(select(Answer))
    answers = result.scalars().all()
    assert len(answers) == 1
    assert answers[0].person_id == seeded["person"].id
    assert answers[0].text == "we used the widget factory pattern"


def test_teach_back_has_no_grader(client, seeded):
    r = _submit(client, seeded["teach_back"].id, {"text": "anything"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "no_grader"


def test_bypass_never_grades_above_point_three(client, seeded):
    r = _submit(client, seeded["mcq"].id, {"choice": 1}, bypassed=True)
    assert r.status_code == 200
    body = r.json()
    assert body["bypassed"] is True
    assert body["grade"] <= 0.3
    assert body["grade"] == 0.0
    assert body["correct"] is False


def test_bypass_of_teach_back_still_works_bypass_checked_first(client, seeded):
    r = _submit(client, seeded["teach_back"].id, {"text": "anything"}, bypassed=True)
    assert r.status_code == 200
    assert r.json()["grade"] == 0.0


def test_confidence_is_echoed_and_not_confused_with_self_rated_rating(client, seeded):
    r = _submit(client, seeded["self_rated"].id, {"rating": 4}, confidence=2)
    assert r.status_code == 200
    body = r.json()
    assert body["confidence"] == 2
    assert body["rating"] == 4


def test_idempotency_replay_returns_original_result(client, seeded):
    first = _submit(client, seeded["mcq"].id, {"choice": 1})
    assert first.status_code == 200
    second = _submit(client, seeded["mcq"].id, {"choice": 0})  # different response, same key
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "idempotency_replay"
    assert detail["result"] == first.json()


def test_a_learner_id_in_the_body_is_rejected(client, seeded):
    body = {
        "item_id": seeded["mcq"].id, "idempotency_key": "k-2", "response": {"choice": 1},
        "person_id": "someone-else",
    }
    r = client.post("/me/reviews", json=body, headers=AUTH)
    assert r.status_code == 422


def test_unknown_item_is_404(client, seeded):
    r = _submit(client, "nope", {"choice": 1})
    assert r.status_code == 404
