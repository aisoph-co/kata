"""`GET /me/next` wiring: auth, limit validation, response shape.

`resolve_person_id` (main.py) always resolves the acting identity to a real
`Person.id` through a DB session; these tests exercise the engine in
isolation (an in-memory `LearningRepository`, no roster), so `resolve_person_id`
is overridden with the same `platform:external_id` placeholder kata's other
engine-focused test files use — `acting_identity` (and, through it,
`require_service_token`) stays a real, un-overridden dependency, so the auth
checks below still exercise the real thing.
"""

import os

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.engine.models import Concept, Item  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.main import ActingIdentity, acting_identity, app, get_repository, resolve_person_id  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}


async def _placeholder_person_id(identity: ActingIdentity = Depends(acting_identity)) -> str:
    return f"{identity.platform}:{identity.external_id}"


@pytest.fixture
def client():
    repo = InMemoryLearningRepository()
    repo.add_concept(Concept(id="c1", course_id="course", slug="c1", title="C1"))
    repo.add_item(
        Item(
            id="i1",
            concept_id="c1",
            kind="mcq",
            prompt="2+2?",
            payload={"options": ["3", "4"], "correct_index": 1, "explanation": "arithmetic"},
            status="published",
        )
    )
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[resolve_person_id] = _placeholder_person_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(resolve_person_id, None)


def test_me_next_requires_token(client):
    r = client.get("/me/next", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_me_next_requires_identity(client):
    r = client.get("/me/next", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422


def test_me_next_strips_answer_keys(client):
    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["reason"] is None
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item == {
        "id": "i1",
        "concept_id": "c1",
        "kind": "mcq",
        "prompt": "2+2?",
        "payload": {"options": ["3", "4"]},
    }


def test_me_next_limit_default_and_bounds(client):
    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200

    r = client.get("/me/next?limit=0", headers=AUTH)
    assert r.status_code == 422

    r = client.get("/me/next?limit=21", headers=AUTH)
    assert r.status_code == 422

    r = client.get("/me/next?limit=20", headers=AUTH)
    assert r.status_code == 200


def test_me_next_empty_reason(client):
    empty_repo = InMemoryLearningRepository()
    app.dependency_overrides[get_repository] = lambda: empty_repo
    r = client.get("/me/next", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["reason"] == "all_mastered"
