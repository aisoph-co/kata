"""`GET /me/progress` + `GET /me/due-summary` wiring: auth, response shape,
unlocked/mastered/due semantics.

See `test_me_next_endpoint.py`'s module docstring for why `resolve_person_id`
is overridden with a placeholder here.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.engine.models import CardState, Concept, ConceptEdge, ConceptState, Item  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.main import ActingIdentity, acting_identity, app, get_repository, resolve_person_id  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}
PERSON = "slack:U1"
NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


async def _placeholder_person_id(identity: ActingIdentity = Depends(acting_identity)) -> str:
    return f"{identity.platform}:{identity.external_id}"


def mcq(item_id: str, concept_id: str) -> Item:
    return Item(
        id=item_id,
        concept_id=concept_id,
        kind="mcq",
        prompt=f"prompt {item_id}",
        payload={"options": ["a", "b"], "correct_index": 0, "explanation": "because"},
        status="published",
    )


@pytest.fixture
def repo() -> InMemoryLearningRepository:
    return InMemoryLearningRepository()


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[resolve_person_id] = _placeholder_person_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(resolve_person_id, None)


def test_me_progress_requires_token(client):
    r = client.get("/me/progress", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_me_due_summary_requires_token(client):
    r = client.get("/me/due-summary", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_me_progress_empty_curriculum(client):
    r = client.get("/me/progress", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["concepts"] == []
    assert body["summary"] == {
        "retention": {
            "d1": {"accuracy": None, "samples": 0},
            "d7": {"accuracy": None, "samples": 0},
            "d30": {"accuracy": None, "samples": 0},
        },
        "bypass_rate": None,
        "calibration": None,
        "review_count": 0,
        "last_active": None,
    }


def test_me_due_summary_empty_curriculum(client):
    r = client.get("/me/due-summary", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"due_count": 0, "overdue_count": 0, "new_available_count": 0}


def test_me_progress_reports_p_known_mastered_due_unlocked(repo, client):
    foundation = Concept(id="found", course_id="course", slug="found", title="Foundation", mastery_threshold=0.85)
    advanced = Concept(id="adv", course_id="course", slug="adv", title="Advanced", mastery_threshold=0.85)
    repo.add_concept(foundation)
    repo.add_concept(advanced)
    repo.add_edge(ConceptEdge(from_concept_id="found", to_concept_id="adv", kind="prerequisite"))
    repo.add_item(mcq("found-item", "found"))
    repo.add_item(mcq("adv-item", "adv"))
    repo.add_concept_state(ConceptState(person_id=PERSON, concept_id="found", p_known=0.9))
    repo.add_card_state(
        CardState(
            person_id=PERSON,
            item_id="found-item",
            stability=10,
            difficulty=5,
            due_at=NOW - timedelta(days=1),
        )
    )

    r = client.get("/me/progress", headers=AUTH)
    assert r.status_code == 200
    by_id = {c["concept_id"]: c for c in r.json()["concepts"]}

    assert by_id["found"] == {"concept_id": "found", "p_known": 0.9, "mastered": True, "due_count": 1, "unlocked": True}
    assert by_id["adv"] == {"concept_id": "adv", "p_known": pytest.approx(0.2), "mastered": False, "due_count": 0, "unlocked": True}


def test_me_progress_locked_concept_is_not_unlocked(repo, client):
    foundation = Concept(id="found", course_id="course", slug="found", title="Foundation")
    advanced = Concept(id="adv", course_id="course", slug="adv", title="Advanced")
    repo.add_concept(foundation)
    repo.add_concept(advanced)
    repo.add_edge(ConceptEdge(from_concept_id="found", to_concept_id="adv", kind="prerequisite"))

    r = client.get("/me/progress", headers=AUTH)
    by_id = {c["concept_id"]: c for c in r.json()["concepts"]}
    assert by_id["adv"]["unlocked"] is False


def test_me_due_summary_counts_overdue_and_new_available(repo, client):
    concept = Concept(id="c1", course_id="course", slug="c1", title="C1")
    repo.add_concept(concept)
    repo.add_item(mcq("i1", "c1"))
    repo.add_item(mcq("i2", "c1"))
    repo.add_card_state(
        CardState(
            person_id=PERSON,
            item_id="i1",
            stability=10,
            difficulty=5,
            due_at=NOW - timedelta(days=1),
        )
    )

    r = client.get("/me/due-summary", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["overdue_count"] == 1
    assert body["new_available_count"] == 1
    assert body["due_count"] == body["overdue_count"] + body["new_available_count"]


def test_me_due_summary_excludes_locked_and_mastered_concepts(repo, client):
    locked = Concept(id="locked", course_id="course", slug="locked", title="Locked")
    gate = Concept(id="gate", course_id="course", slug="gate", title="Gate")
    mastered = Concept(id="mastered", course_id="course", slug="mastered", title="Mastered", mastery_threshold=0.85)
    repo.add_concept(locked)
    repo.add_concept(gate)
    repo.add_concept(mastered)
    repo.add_edge(ConceptEdge(from_concept_id="gate", to_concept_id="locked", kind="prerequisite"))
    repo.add_item(mcq("locked-item", "locked"))
    repo.add_item(mcq("mastered-item", "mastered"))
    repo.add_concept_state(ConceptState(person_id=PERSON, concept_id="mastered", p_known=0.9))

    r = client.get("/me/due-summary", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"due_count": 0, "overdue_count": 0, "new_available_count": 0}


def test_me_progress_summary_reports_bypass_rate_and_calibration(repo, client):
    repo.add_concept(Concept(id="c1", course_id="course", slug="c1", title="C1"))
    repo.add_item(mcq("i1", "c1"))
    base = NOW - timedelta(days=10)
    repo.append_review(
        {
            "id": "r1",
            "person_id": PERSON,
            "item_id": "i1",
            "reviewed_at": base.isoformat(),
            "kind": "mcq",
            "grade": 1.0,
            "rating": 3,
            "source": "web",
            "idempotency_key": "k1",
            "asserted_by": "x",
            "result": {},
            "confidence": 4,
            "bypassed": False,
        }
    )
    repo.append_review(
        {
            "id": "r2",
            "person_id": PERSON,
            "item_id": "i1",
            "reviewed_at": (base + timedelta(days=1)).isoformat(),
            "kind": "mcq",
            "grade": 0.0,
            "rating": 1,
            "source": "web",
            "idempotency_key": "k2",
            "asserted_by": "x",
            "result": {},
            "confidence": 2,
            "bypassed": True,
        }
    )

    r = client.get("/me/progress", headers=AUTH)
    summary = r.json()["summary"]
    assert summary["review_count"] == 2
    assert summary["bypass_rate"] == 0.5
    # Mean confidence 3 -> (3-1)/4 = 0.5; accuracy 1 of 2 = 0.5 -> calibrated.
    assert summary["calibration"] == pytest.approx(0.0)
    assert summary["last_active"] is not None
    # 1 sample, below the 5-sample floor for accuracy, but the count is real.
    assert summary["retention"]["d1"] == {"accuracy": None, "samples": 1}


def test_me_progress_and_due_summary_scoped_to_acting_person(repo, client):
    concept = Concept(id="c1", course_id="course", slug="c1", title="C1")
    repo.add_concept(concept)
    repo.add_item(mcq("i1", "c1"))
    repo.add_concept_state(ConceptState(person_id="slack:OTHER", concept_id="c1", p_known=0.9))
    repo.add_card_state(
        CardState(
            person_id="slack:OTHER",
            item_id="i1",
            stability=10,
            difficulty=5,
            due_at=NOW - timedelta(days=1),
        )
    )

    r = client.get("/me/progress", headers=AUTH)
    concepts = r.json()["concepts"]
    assert concepts[0]["p_known"] == pytest.approx(0.2)
    assert concepts[0]["due_count"] == 0

    r = client.get("/me/due-summary", headers=AUTH)
    body = r.json()
    assert body["overdue_count"] == 0
    assert body["new_available_count"] == 1
