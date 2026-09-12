"""`/admin/courses`, `/admin/concepts`, `/admin/edges`, `/admin/items` (US-C1,
AGCTM-38, spec §Curriculum): operator CRUD, prerequisite acyclicity -> 422
`cycle`, item kind enum, and publish flipping item status. Uses an in-memory
SQLite engine, same as `test_admin_roster_import.py`.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item  # noqa: E402,F401
from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402

TOKEN_HEADER = {"Authorization": "Bearer test-token"}
OPERATOR_AUTH = {**TOKEN_HEADER, "X-Acting-Identity": "slack:operator"}
LEARNER_AUTH = {**TOKEN_HEADER, "X-Acting-Identity": "slack:learner"}


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        operator = Person(display_name="Ops", email="ops@example.com", is_operator=True)
        learner = Person(display_name="Learner", email="learner@example.com", is_operator=False)
        s.add_all([operator, learner])
        await s.flush()
        s.add_all(
            [
                Identity(person_id=operator.id, platform="slack", external_id="operator", is_primary=True),
                Identity(person_id=learner.id, platform="slack", external_id="learner", is_primary=True),
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


def _make_course(client, title="Course A"):
    r = client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": title})
    assert r.status_code == 201
    return r.json()


def _make_concept(client, course_id, slug, title=None):
    r = client.post(
        "/admin/concepts",
        headers=OPERATOR_AUTH,
        json={"course_id": course_id, "slug": slug, "title": title or slug},
    )
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# Auth: service token, is_operator
# ---------------------------------------------------------------------------


def test_requires_service_token(client):
    r = client.get("/admin/courses", headers={"X-Acting-Identity": "slack:operator"})
    assert r.status_code == 401


def test_requires_known_identity(client):
    r = client.get("/admin/courses", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:nobody"})
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


def test_requires_known_identity_logs_the_failed_identity(client, caplog):
    import logging

    with caplog.at_level(logging.INFO, logger="learning_service.auth"):
        r = client.get("/admin/courses", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:nobody"})
    assert r.status_code == 403
    records = [rec for rec in caplog.records if rec.name == "learning_service.auth"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert "path=/admin/courses" in message
    assert "slack" in message
    assert "nobody" in message
    assert "test-token" not in message


def test_requires_operator(client):
    r = client.get("/admin/courses", headers=LEARNER_AUTH)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_operator"


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------


def test_create_and_list_and_get_course(client):
    course = _make_course(client, "Backend Fundamentals")
    assert course["title"] == "Backend Fundamentals"

    r = client.get("/admin/courses", headers=OPERATOR_AUTH)
    assert r.status_code == 200
    assert [c["id"] for c in r.json()["courses"]] == [course["id"]]

    r = client.get(f"/admin/courses/{course['id']}", headers=OPERATOR_AUTH)
    assert r.status_code == 200
    assert r.json()["title"] == "Backend Fundamentals"


def test_get_missing_course_is_404(client):
    r = client.get("/admin/courses/does-not-exist", headers=OPERATOR_AUTH)
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_update_course(client):
    course = _make_course(client)
    r = client.patch(f"/admin/courses/{course['id']}", headers=OPERATOR_AUTH, json={"title": "Renamed"})
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"


def test_create_course_with_slug(client):
    r = client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": "Course A", "slug": "course-a"})
    assert r.status_code == 201
    assert r.json()["slug"] == "course-a"


def test_duplicate_course_slug_is_a_validation_error(client):
    client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": "Course A", "slug": "dup"})
    r = client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": "Course B", "slug": "dup"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_course_slug_is_optional_and_multiple_null_slugs_are_allowed(client):
    a = client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": "Course A"})
    b = client.post("/admin/courses", headers=OPERATOR_AUTH, json={"title": "Course B"})
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["slug"] is None and b.json()["slug"] is None


def test_update_course_slug(client):
    course = _make_course(client)
    r = client.patch(f"/admin/courses/{course['id']}", headers=OPERATOR_AUTH, json={"slug": "course-a"})
    assert r.status_code == 200
    assert r.json()["slug"] == "course-a"


def test_delete_course(client):
    course = _make_course(client)
    r = client.delete(f"/admin/courses/{course['id']}", headers=OPERATOR_AUTH)
    assert r.status_code == 204
    assert client.get(f"/admin/courses/{course['id']}", headers=OPERATOR_AUTH).status_code == 404


def test_cannot_delete_course_with_concepts(client):
    course = _make_course(client)
    _make_concept(client, course["id"], "c1")
    r = client.delete(f"/admin/courses/{course['id']}", headers=OPERATOR_AUTH)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# Concepts
# ---------------------------------------------------------------------------


def test_create_concept_requires_existing_course(client):
    r = client.post(
        "/admin/concepts", headers=OPERATOR_AUTH, json={"course_id": "nope", "slug": "c1", "title": "C1"}
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_duplicate_slug_in_course_is_a_validation_error(client):
    course = _make_course(client)
    _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/concepts",
        headers=OPERATOR_AUTH,
        json={"course_id": course["id"], "slug": "c1", "title": "Duplicate"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_same_slug_in_different_courses_is_allowed(client):
    course_a = _make_course(client, "A")
    course_b = _make_course(client, "B")
    _make_concept(client, course_a["id"], "c1")
    r = client.post(
        "/admin/concepts", headers=OPERATOR_AUTH, json={"course_id": course_b["id"], "slug": "c1", "title": "C1"}
    )
    assert r.status_code == 201


def test_list_concepts_filtered_by_course(client):
    course_a = _make_course(client, "A")
    course_b = _make_course(client, "B")
    _make_concept(client, course_a["id"], "c1")
    _make_concept(client, course_b["id"], "c2")
    r = client.get(f"/admin/concepts?course_id={course_a['id']}", headers=OPERATOR_AUTH)
    assert r.status_code == 200
    [concept] = r.json()["concepts"]
    assert concept["slug"] == "c1"


def test_update_concept(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.patch(f"/admin/concepts/{concept['id']}", headers=OPERATOR_AUTH, json={"mastery_threshold": 0.9})
    assert r.status_code == 200
    assert r.json()["mastery_threshold"] == 0.9


def test_delete_concept_blocked_by_items(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": "mcq", "prompt": "2+2?", "payload": {}},
    )
    r = client.delete(f"/admin/concepts/{concept['id']}", headers=OPERATOR_AUTH)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_delete_concept_cascades_edges(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    r = client.delete(f"/admin/concepts/{a['id']}", headers=OPERATOR_AUTH)
    assert r.status_code == 204
    r = client.get(f"/admin/edges?concept_id={b['id']}", headers=OPERATOR_AUTH)
    assert r.json()["edges"] == []


# ---------------------------------------------------------------------------
# Edges: acyclicity, related-edge normalization and weight range
# ---------------------------------------------------------------------------


def test_create_prerequisite_edge(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    assert r.status_code == 201
    assert r.json()["from_concept_id"] == a["id"]
    assert r.json()["to_concept_id"] == b["id"]


def test_direct_cycle_is_rejected(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": b["id"], "to_concept_id": a["id"], "kind": "prerequisite"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "cycle"


def test_transitive_cycle_is_rejected(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    c = _make_concept(client, course["id"], "c")
    client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": b["id"], "to_concept_id": c["id"], "kind": "prerequisite"},
    )
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": c["id"], "to_concept_id": a["id"], "kind": "prerequisite"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "cycle"


def test_self_loop_prerequisite_is_a_cycle(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": a["id"], "kind": "prerequisite"},
    )
    assert r.status_code == 422


def test_prerequisite_across_courses_is_a_validation_error(client):
    course_a = _make_course(client, "A")
    course_b = _make_course(client, "B")
    a = _make_concept(client, course_a["id"], "a")
    b = _make_concept(client, course_b["id"], "b")
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_related_edge_is_normalized_lowest_id_first(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    lo, hi = sorted([a["id"], b["id"]])
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": hi, "to_concept_id": lo, "kind": "related", "weight": 0.5},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["from_concept_id"] == lo
    assert body["to_concept_id"] == hi


def test_related_edge_weight_out_of_range_is_a_validation_error(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "related", "weight": 1.5},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_duplicate_edge_is_a_validation_error(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_delete_edge(client):
    course = _make_course(client)
    a = _make_concept(client, course["id"], "a")
    b = _make_concept(client, course["id"], "b")
    r = client.post(
        "/admin/edges",
        headers=OPERATOR_AUTH,
        json={"from_concept_id": a["id"], "to_concept_id": b["id"], "kind": "prerequisite"},
    )
    edge_id = r.json()["id"]
    r = client.delete(f"/admin/edges/{edge_id}", headers=OPERATOR_AUTH)
    assert r.status_code == 204
    assert client.get("/admin/edges", headers=OPERATOR_AUTH).json()["edges"] == []


# ---------------------------------------------------------------------------
# Items: kind enum, publish flips status
# ---------------------------------------------------------------------------


def test_create_item_defaults_to_draft(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={
            "concept_id": concept["id"],
            "kind": "mcq",
            "prompt": "2+2?",
            "payload": {"options": ["3", "4"], "correct_index": 1, "explanation": "arithmetic"},
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "draft"
    assert body["payload"]["correct_index"] == 1


@pytest.mark.parametrize("kind", ["mcq", "self_rated", "short_answer", "teach_back"])
def test_valid_item_kinds_are_accepted(client, kind):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": kind, "prompt": "prompt", "payload": {}},
    )
    assert r.status_code == 201


def test_invalid_item_kind_is_a_validation_error(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": "essay", "prompt": "prompt", "payload": {}},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_publish_flips_item_status(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": "mcq", "prompt": "2+2?", "payload": {}},
    )
    item_id = r.json()["id"]
    r = client.post(f"/admin/items/{item_id}/publish", headers=OPERATOR_AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "published"

    r = client.get(f"/admin/items/{item_id}", headers=OPERATOR_AUTH)
    assert r.json()["status"] == "published"


def test_update_item_prompt(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": "mcq", "prompt": "old", "payload": {}},
    )
    item_id = r.json()["id"]
    r = client.patch(f"/admin/items/{item_id}", headers=OPERATOR_AUTH, json={"prompt": "new"})
    assert r.status_code == 200
    assert r.json()["prompt"] == "new"


def test_delete_item(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": "mcq", "prompt": "2+2?", "payload": {}},
    )
    item_id = r.json()["id"]
    r = client.delete(f"/admin/items/{item_id}", headers=OPERATOR_AUTH)
    assert r.status_code == 204
    assert client.get(f"/admin/items/{item_id}", headers=OPERATOR_AUTH).status_code == 404


def test_list_items_filtered_by_concept_and_status(client):
    course = _make_course(client)
    concept = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/items",
        headers=OPERATOR_AUTH,
        json={"concept_id": concept["id"], "kind": "mcq", "prompt": "2+2?", "payload": {}},
    )
    item_id = r.json()["id"]
    client.post(f"/admin/items/{item_id}/publish", headers=OPERATOR_AUTH)

    r = client.get(f"/admin/items?concept_id={concept['id']}&status=published", headers=OPERATOR_AUTH)
    assert [i["id"] for i in r.json()["items"]] == [item_id]

    r = client.get(f"/admin/items?concept_id={concept['id']}&status=draft", headers=OPERATOR_AUTH)
    assert r.json()["items"] == []


# ---------------------------------------------------------------------------
# Topics (Contract v1.2.0)
# ---------------------------------------------------------------------------


def test_create_topic(client):
    course = _make_course(client)
    entry = _make_concept(client, course["id"], "c1")
    other = _make_concept(client, course["id"], "c2")
    r = client.post(
        "/admin/topics",
        headers=OPERATOR_AUTH,
        json={
            "course_id": course["id"],
            "slug": "topic-a",
            "title": "Topic A",
            "persona_role": "pm",
            "entry_concept_id": entry["id"],
            "concept_ids": [entry["id"], other["id"]],
            "grounded_in": ["PAY-1841", "sprint-history.md#sprint-42"],
        },
    )
    assert r.status_code == 201
    body = r.json()
    assert body["slug"] == "topic-a"
    assert body["grounded_in"] == ["PAY-1841", "sprint-history.md#sprint-42"]
    assert body["persona_role"] == "pm"
    assert body["entry_concept_id"] == entry["id"]
    assert sorted(body["concept_ids"]) == sorted([entry["id"], other["id"]])


def test_create_topic_requires_operator(client):
    r = client.post(
        "/admin/topics",
        headers=LEARNER_AUTH,
        json={
            "course_id": "x", "slug": "t", "title": "T", "persona_role": "pm",
            "entry_concept_id": "x", "concept_ids": ["x"], "grounded_in": ["PAY-1"],
        },
    )
    assert r.status_code == 403


def test_create_topic_unknown_persona_role_is_a_validation_error(client):
    course = _make_course(client)
    entry = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/topics",
        headers=OPERATOR_AUTH,
        json={
            "course_id": course["id"],
            "slug": "topic-a",
            "title": "Topic A",
            "persona_role": "wizard",
            "entry_concept_id": entry["id"],
            "concept_ids": [entry["id"]],
            "grounded_in": ["PAY-1"],
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_create_topic_entry_concept_must_be_a_member(client):
    course = _make_course(client)
    entry = _make_concept(client, course["id"], "c1")
    other = _make_concept(client, course["id"], "c2")
    r = client.post(
        "/admin/topics",
        headers=OPERATOR_AUTH,
        json={
            "course_id": course["id"],
            "slug": "topic-a",
            "title": "Topic A",
            "persona_role": "pm",
            "entry_concept_id": entry["id"],
            "concept_ids": [other["id"]],
            "grounded_in": ["PAY-1"],
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_create_topic_without_a_citation_is_rejected(client):
    """KAT-C1: an uncited topic must never be published. The citation data has
    existed in the seed fixtures all along; this is the API refusing to create
    one without it."""
    course = _make_course(client)
    entry = _make_concept(client, course["id"], "c1")
    r = client.post(
        "/admin/topics",
        headers=OPERATOR_AUTH,
        json={
            "course_id": course["id"],
            "slug": "topic-a",
            "title": "Topic A",
            "persona_role": "pm",
            "entry_concept_id": entry["id"],
            "concept_ids": [entry["id"]],
            "grounded_in": [],
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"
