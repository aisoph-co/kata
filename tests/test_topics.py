"""`GET /topics` (Contract v1.2.0 additive change #5): filtered to the acting
person's own role when one is on record, else every topic.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402

TOKEN_HEADER = {"Authorization": "Bearer test-token"}
OPERATOR_AUTH = {**TOKEN_HEADER, "X-Acting-Identity": "slack:operator"}


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        operator = Person(display_name="Ops", email="ops@example.com", is_operator=True)
        pm = Person(display_name="Shane", email="shane@example.com", role="pm")
        no_role = Person(display_name="NoRole", email="norole@example.com")
        s.add_all([operator, pm, no_role])
        await s.flush()
        s.add_all(
            [
                Identity(person_id=operator.id, platform="slack", external_id="operator", is_primary=True),
                Identity(person_id=pm.id, platform="slack", external_id="shane", is_primary=True),
                Identity(person_id=no_role.id, platform="slack", external_id="norole", is_primary=True),
            ]
        )
        await s.commit()
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


def _make_topic(client, *, course_id, entry_concept_id, concept_ids, persona_role, slug):
    r = client.post(
        "/admin/topics",
        headers=OPERATOR_AUTH,
        json={
            "course_id": course_id,
            "slug": slug,
            "title": slug,
            "persona_role": persona_role,
            "entry_concept_id": entry_concept_id,
            "concept_ids": concept_ids,
            "grounded_in": [f"PAY-{slug}", f"{slug}.md#why"],
        },
    )
    assert r.status_code == 201
    return r.json()


@pytest.fixture
def curriculum(client):
    course = client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": "Course"}).json()
    c1 = client.post(
        "/admin/concepts",
        headers=OPERATOR_AUTH,
        json={"course_id": course["id"], "slug": "c1", "title": "C1"},
    ).json()
    c2 = client.post(
        "/admin/concepts",
        headers=OPERATOR_AUTH,
        json={"course_id": course["id"], "slug": "c2", "title": "C2"},
    ).json()
    pm_topic = _make_topic(
        client, course_id=course["id"], entry_concept_id=c1["id"], concept_ids=[c1["id"]],
        persona_role="pm", slug="pm-topic",
    )
    tl_topic = _make_topic(
        client, course_id=course["id"], entry_concept_id=c2["id"], concept_ids=[c2["id"]],
        persona_role="tech_lead", slug="tl-topic",
    )
    return {"course": course, "pm_topic": pm_topic, "tl_topic": tl_topic}


def test_requires_service_token(client):
    r = client.get("/topics")
    assert r.status_code == 401


def test_unknown_identity_is_403(client):
    r = client.get("/topics", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:nobody"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


def test_person_with_a_role_only_sees_their_own_topics(client, curriculum):
    r = client.get("/topics", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:shane"})
    assert r.status_code == 200
    slugs = [t["slug"] for t in r.json()["topics"]]
    assert slugs == ["pm-topic"]


def test_person_with_no_role_sees_every_topic(client, curriculum):
    r = client.get("/topics", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:norole"})
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()["topics"]}
    assert slugs == {"pm-topic", "tl-topic"}


def test_all_roles_true_bypasses_the_role_filter_for_any_caller(client, curriculum):
    """KATA-7/W3: the Connections screen shows persona topic cards across
    roles on one signed-in learner's own screen, so a role-bearing caller
    has to be able to opt out of the default per-role filter."""
    r = client.get("/topics?all_roles=true", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:shane"})
    assert r.status_code == 200
    slugs = {t["slug"] for t in r.json()["topics"]}
    assert slugs == {"pm-topic", "tl-topic"}


def test_all_roles_false_is_the_same_as_omitting_it(client, curriculum):
    r = client.get("/topics?all_roles=false", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:shane"})
    assert r.status_code == 200
    assert [t["slug"] for t in r.json()["topics"]] == ["pm-topic"]


def test_topics_carry_their_source_citations(client, curriculum):
    """KAT-C2: a topic has to say which issue or file put it on the list —
    `GET /topics` is where Screen 2 reads that from."""
    r = client.get("/topics", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:shane"})
    assert r.status_code == 200
    topics = r.json()["topics"]
    assert topics, "the pm person must see at least one topic"
    assert all(t["grounded_in"] for t in topics)
    assert topics[0]["grounded_in"] == ["PAY-pm-topic", "pm-topic.md#why"]
