"""`GET /me/concept-graph` (Contract v1.2.1 additive change #6). `p_known`/
`mastered`/`unlocked` are real `concept_state`/BKT reads via the `engine`
package (KATA-2's follow-up issue) — a person with no review yet reads at
`engine.models.P_INIT` (0.20, spec §Learning engine, "BKT"), not 0.0.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course  # noqa: E402
from learning_service.db import get_session  # noqa: E402
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
    person = Person(display_name="Ada Lovelace", email="ada@example.com", is_operator=False)
    session.add(person)
    await session.flush()
    session.add(Identity(person_id=person.id, platform="slack", external_id="U1"))
    course = Course(title="Payments")
    session.add(course)
    await session.flush()
    foundation = Concept(course_id=course.id, slug="found", title="Foundation")
    advanced = Concept(course_id=course.id, slug="adv", title="Advanced")
    session.add_all([foundation, advanced])
    await session.flush()
    session.add(ConceptEdge(from_concept_id=foundation.id, to_concept_id=advanced.id, kind="prerequisite"))
    await session.commit()
    return {"foundation": foundation, "advanced": advanced}


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_requires_service_token(client):
    r = client.get("/me/concept-graph", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_unknown_identity_is_403(client, seeded):
    r = client.get("/me/concept-graph", headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:nobody"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


def test_returns_nodes_and_edges(client, seeded):
    r = client.get("/me/concept-graph", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    by_slug = {n["slug"]: n for n in body["nodes"]}
    assert by_slug["found"] == {
        "concept_id": seeded["foundation"].id, "slug": "found", "title": "Foundation",
        "p_known": 0.20, "mastered": False, "unlocked": True,
    }
    # "adv" has an unmet prerequisite (foundation is nowhere near its 0.85
    # mastery threshold at p_init), so it is not unlocked yet.
    assert by_slug["adv"]["unlocked"] is False
    assert body["edges"] == [
        {
            "from_concept_id": seeded["foundation"].id,
            "to_concept_id": seeded["advanced"].id,
            "kind": "prerequisite",
            "weight": 1.0,
        }
    ]
