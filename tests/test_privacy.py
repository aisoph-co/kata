"""Privacy, first-class (spec §Testing, "Privacy": "must pass before any
deploy"): no `/team/*`/`/admin/*` response ever carries an `answer` or
`learner_note`/`text` field from those tables; `/me/answers`/`/me/notes`
never leak across people, including for operators; plugin routes without
the service token are 401, with the token but an unknown identity are 403;
a review's acting person always comes from the header, never the body.
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
from learning_service.grading.stub import StubGraderClient  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.privacy.models import Answer, LearnerNote  # noqa: E402
from learning_service.reviews import get_llm_client  # noqa: E402

TOKEN_HEADER = {"Authorization": "Bearer test-token"}


def _auth(external_id: str) -> dict:
    return {**TOKEN_HEADER, "X-Acting-Identity": f"slack:{external_id}"}


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
    manager = Person(display_name="Manager", email="m@example.com", is_operator=True)
    learner = Person(display_name="Learner", email="l@example.com")
    session.add_all([manager, learner])
    await session.flush()
    learner.manager_id = manager.id
    session.add_all(
        [
            Identity(person_id=manager.id, platform="slack", external_id="M"),
            Identity(person_id=learner.id, platform="slack", external_id="L"),
        ]
    )
    course = Course(title="Payments")
    session.add(course)
    await session.flush()
    concept = Concept(course_id=course.id, slug="c1", title="C1")
    session.add(concept)
    await session.flush()
    item = Item(
        concept_id=concept.id, kind="short_answer", prompt="explain",
        payload={"reference": "ref", "rubric": "widget factory pattern"}, status="published",
    )
    session.add(item)
    session.add(LearnerNote(person_id=learner.id, text="prefers examples in Go"))
    await session.commit()
    return {"manager": manager, "learner": learner, "concept": concept, "item": item}


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_llm_client] = lambda: StubGraderClient()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_llm_client, None)


def _has_field(payload, field: str) -> bool:
    """Recursively checks whether `field` appears anywhere as a JSON key in
    `payload` (dict/list nesting)."""
    if isinstance(payload, dict):
        if field in payload:
            return True
        return any(_has_field(v, field) for v in payload.values())
    if isinstance(payload, list):
        return any(_has_field(v, field) for v in payload)
    return False


def test_plugin_route_without_token_is_401(client, seeded):
    r = client.get("/me/progress", headers={"X-Acting-Identity": "slack:L"})
    assert r.status_code == 401


def test_plugin_route_with_token_but_unknown_identity_is_403(client, seeded):
    r = client.get("/me/progress", headers=_auth("nobody"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


def test_review_body_cannot_assert_a_different_learner(client, seeded):
    # the review schema has no learner-id field at all: supplying one is a
    # rejected, not silently-ignored, extra field (extra="forbid").
    body = {
        "item_id": seeded["item"].id, "idempotency_key": "k1",
        "response": {"text": "widget factory pattern"}, "person_id": seeded["manager"].id,
    }
    r = client.post("/me/reviews", json=body, headers=_auth("L"))
    assert r.status_code == 422


async def test_me_answers_never_returns_another_persons_rows(client, seeded, session):
    session.add(Answer(review_id="r1", person_id=seeded["manager"].id, text="the manager's own answer"))
    await session.commit()

    # even though the manager is an operator, /me/answers is scoped to the
    # acting person, not a superuser read.
    r = client.get("/me/answers", headers=_auth("L"))
    assert r.status_code == 200
    assert r.json()["answers"] == []


async def test_team_and_admin_responses_never_carry_answer_or_note_fields(client, seeded, session):
    r = client.post(
        "/me/reviews",
        json={"item_id": seeded["item"].id, "idempotency_key": "k1", "response": {"text": "widget factory pattern"}},
        headers=_auth("L"),
    )
    assert r.status_code == 200

    for path, headers in [
        ("/team/overview", _auth("M")),
        (f"/team/people/{seeded['learner'].id}", _auth("M")),
        (f"/team/concepts/{seeded['concept'].id}", _auth("M")),
        ("/team/digest", _auth("M")),
        ("/team/recommendations", _auth("M")),
        ("/team/audit", _auth("M")),
    ]:
        resp = client.get(path, headers=headers)
        assert resp.status_code == 200, f"{path}: {resp.text}"
        body = resp.json()
        assert not _has_field(body, "answer"), f"{path} leaked an answer field"
        assert not _has_field(body, "text"), f"{path} leaked a text field"
        assert not _has_field(body, "learner_note"), f"{path} leaked a learner_note field"

    admin_replay = client.post("/admin/replay", headers=TOKEN_HEADER)
    assert admin_replay.status_code == 200
    assert not _has_field(admin_replay.json(), "answer")
    assert not _has_field(admin_replay.json(), "text")


def test_me_notes_never_returns_another_persons_rows(client, seeded):
    r = client.get("/me/notes", headers=_auth("M"))
    assert r.status_code == 200
    assert r.json()["notes"] == []  # the note was seeded for the learner, not the manager


async def test_outside_subtree_returns_403_outside_subtree(client, seeded, session):
    stranger = Person(display_name="Stranger", email="s@example.com")
    session.add(stranger)
    await session.flush()
    session.add(Identity(person_id=stranger.id, platform="slack", external_id="S"))
    await session.commit()

    r = client.get(f"/team/people/{stranger.id}", headers=_auth("M"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"
