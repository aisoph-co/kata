"""`GET /me/concept-graph` (spec §Curriculum, "concept graph"): concepts +
edges of the course. C1 has no `concept_state` yet (that's the `engine`
package), so every node reads at the BKT `p_init` default and is never
`mastered`; only prerequisite-free concepts are `unlocked`. Uses an
in-memory SQLite engine, same as `test_admin_curriculum.py`.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course  # noqa: E402,F401
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
        person = Person(display_name="Learner", email="learner@example.com")
        s.add(person)
        await s.flush()
        s.add(Identity(person_id=person.id, platform="slack", external_id="U1", is_primary=True))
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


def test_requires_service_token(client):
    r = client.get("/me/concept-graph", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_unknown_identity_is_403(client):
    r = client.get("/me/concept-graph", headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:nope"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


async def test_nodes_and_edges_shape(session: AsyncSession, client):
    operator = Person(display_name="Ops", email="ops@example.com", is_operator=True)
    session.add(operator)
    await session.flush()
    session.add(Identity(person_id=operator.id, platform="slack", external_id="operator", is_primary=True))
    await session.commit()
    operator_auth = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:operator"}

    course = client.post("/admin/courses", headers=operator_auth, json={"title": "Course"}).json()
    found = client.post(
        "/admin/concepts", headers=operator_auth, json={"course_id": course["id"], "slug": "found", "title": "Foundation"}
    ).json()
    adv = client.post(
        "/admin/concepts", headers=operator_auth, json={"course_id": course["id"], "slug": "adv", "title": "Advanced"}
    ).json()
    client.post(
        "/admin/edges",
        headers=operator_auth,
        json={"from_concept_id": found["id"], "to_concept_id": adv["id"], "kind": "prerequisite"},
    )

    r = client.get("/me/concept-graph", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    by_slug = {n["slug"]: n for n in body["nodes"]}
    assert by_slug["found"]["unlocked"] is True
    assert by_slug["found"]["mastered"] is False
    assert by_slug["adv"]["unlocked"] is False  # gated on an unmastered prerequisite
    assert body["edges"] == [
        {"from_concept_id": found["id"], "to_concept_id": adv["id"], "kind": "prerequisite", "weight": 1.0}
    ]
