"""`/team/*` (spec §Team analytics, §Privacy and retention "Audit", §API):
metric definitions, subtree scoping (`403 outside_subtree`/`not_a_manager`),
focus CRUD, and an audit row for every request that reaches a handler.
"""

import os
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, Course, Item  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import ConceptState, Focus  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.privacy.models import AuditEntry  # noqa: E402

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
    m = Person(display_name="Manager", email="m@example.com", is_operator=True)
    a = Person(display_name="Alice", email="a@example.com")
    b = Person(display_name="Bob", email="b@example.com")
    d = Person(display_name="Dana", email="d@example.com")  # unrelated, outside M's subtree
    session.add_all([m, a, b, d])
    await session.flush()
    a.manager_id = m.id
    b.manager_id = m.id
    c = Person(display_name="Cate", email="c@example.com", manager_id=a.id)
    session.add(c)
    await session.flush()
    x = Person(display_name="Xander", email="x@example.com", manager_id=d.id)  # gives D reports too
    session.add(x)
    await session.flush()
    for person, ext in [(m, "M"), (a, "A"), (b, "B"), (c, "C"), (d, "D"), (x, "X")]:
        session.add(Identity(person_id=person.id, platform="slack", external_id=ext))

    course = Course(title="Payments")
    session.add(course)
    await session.flush()
    concept = Concept(course_id=course.id, slug="c1", title="C1", mastery_threshold=0.85)
    session.add(concept)
    await session.flush()
    item = Item(concept_id=concept.id, kind="mcq", prompt="q", payload={"options": ["a", "b"], "correct_index": 0}, status="published")
    session.add(item)
    session.add(ConceptState(person_id=a.id, concept_id=concept.id, p_known=0.95, reviews=3))
    await session.commit()
    return {"m": m, "a": a, "b": b, "c": c, "d": d, "concept": concept, "item": item}


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_a_person_with_no_reports_gets_not_a_manager(client, seeded):
    r = client.get("/team/overview", headers=_auth("C"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_a_manager"


def test_team_overview_metrics(client, seeded):
    r = client.get("/team/overview", headers=_auth("M"))
    assert r.status_code == 200
    body = r.json()
    concept_summary = body["concepts"][0]
    # subtree of M = {A, B, C}; A is mastered (0.95), B and C are at p_init.
    assert concept_summary["mean_mastery"] == pytest.approx((0.95 + 0.20 + 0.20) / 3)
    assert concept_summary["share_mastered"] == pytest.approx(1 / 3)
    people_ids = {p["person_id"] for p in body["people"]}
    assert people_ids == {seeded["a"].id, seeded["b"].id, seeded["c"].id}
    assert "retention" in body


def test_team_people_detail_for_subtree_member(client, seeded):
    r = client.get(f"/team/people/{seeded['c'].id}", headers=_auth("M"))
    assert r.status_code == 200
    body = r.json()
    assert body["person_id"] == seeded["c"].id
    assert "calibration" in body
    assert "retention" in body


def test_team_people_detail_outside_subtree_is_403(client, seeded):
    r = client.get(f"/team/people/{seeded['d'].id}", headers=_auth("M"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"


def test_team_concept_detail(client, seeded):
    r = client.get(f"/team/concepts/{seeded['concept'].id}", headers=_auth("M"))
    assert r.status_code == 200
    by_person = {p["person_id"]: p for p in r.json()["people"]}
    assert by_person[seeded["a"].id]["mastered"] is True
    assert by_person[seeded["b"].id]["mastered"] is False


def test_team_recommendations_capped_at_five(client, seeded):
    r = client.get("/team/recommendations", headers=_auth("M"))
    assert r.status_code == 200
    assert len(r.json()["recommendations"]) <= 5


def test_team_digest_fields(client, seeded):
    r = client.get("/team/digest", headers=_auth("M"))
    assert r.status_code == 200
    body = r.json()
    assert body["subtree_root_id"] == seeded["m"].id
    assert "at_risk" in body and "recommendations" in body and "concepts" in body


async def test_focus_create_and_upsert(client, seeded, session):
    body = {"scope_kind": "person", "scope_person_id": seeded["a"].id, "concept_id": seeded["concept"].id, "weight": 2.0}
    r = client.post("/team/focus", json=body, headers=_auth("M"))
    assert r.status_code == 200
    focus_id = r.json()["id"]

    # posting the same scope+concept again upserts, not duplicates.
    body["weight"] = 3.0
    r2 = client.post("/team/focus", json=body, headers=_auth("M"))
    assert r2.status_code == 200
    assert r2.json()["id"] == focus_id
    assert r2.json()["weight"] == 3.0

    rows = (await session.execute(select(Focus))).scalars().all()
    assert len(rows) == 1


def test_focus_scope_outside_subtree_is_403(client, seeded):
    body = {"scope_kind": "person", "scope_person_id": seeded["d"].id, "concept_id": seeded["concept"].id}
    r = client.post("/team/focus", json=body, headers=_auth("M"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"


def test_manager_may_root_a_subtree_focus_at_themself(client, seeded):
    body = {"scope_kind": "subtree", "scope_person_id": seeded["m"].id, "concept_id": seeded["concept"].id}
    r = client.post("/team/focus", json=body, headers=_auth("M"))
    assert r.status_code == 200


def test_delete_focus_not_owned_is_403(client, seeded):
    body = {"scope_kind": "person", "scope_person_id": seeded["a"].id, "concept_id": seeded["concept"].id}
    focus = client.post("/team/focus", json=body, headers=_auth("M")).json()
    # D is a manager (of X) but neither set this focus nor manages A.
    r = client.delete(f"/team/focus/{focus['id']}", headers=_auth("D"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"


def test_audit_requires_operator(client, seeded):
    r = client.get("/team/audit", headers=_auth("M"))
    assert r.status_code == 200


def test_audit_by_a_non_operator_manager_is_403(client, seeded):
    # D is a manager (of X) but not an operator.
    r = client.get("/team/audit", headers=_auth("D"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_operator"


async def test_audit_row_written_for_every_team_call(client, seeded, session):
    client.get("/team/overview", headers=_auth("M"))
    client.get(f"/team/people/{seeded['d'].id}", headers=_auth("M"))  # 403 outside_subtree
    client.get("/team/overview", headers=_auth("C"))  # 403 not_a_manager

    rows = (await session.execute(select(AuditEntry))).scalars().all()
    endpoints = [row.endpoint for row in rows]
    assert "/team/overview" in endpoints
    assert endpoints.count("/team/overview") >= 1
    assert any(row.subject_scope.startswith("person:") for row in rows)
    assert any(row.subject_scope == "n/a" for row in rows)  # the not_a_manager call
