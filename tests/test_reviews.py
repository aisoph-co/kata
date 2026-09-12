"""`POST /me/reviews` tests: grading, FSRS/BKT wiring, idempotency replay,
and acting-person scoping. `short_answer` is graded through `StubLLMClient`
only — no live model calls.

See `test_me_next_endpoint.py`'s module docstring for why `resolve_person_id`
is overridden with a placeholder here (an in-memory `LearningRepository`, no
roster) while `acting_identity`/`require_service_token` stay real.
"""

import os

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.engine.models import Concept, Item  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.main import (  # noqa: E402
    ActingIdentity,
    acting_identity,
    app,
    get_llm_client,
    get_repository,
    resolve_person_id,
)
from tests.stub_llm import StubLLMClient  # noqa: E402

AUTH = {
    "Authorization": "Bearer test-token",
    "X-Acting-Identity": "slack:U1",
}


async def _placeholder_person_id(identity: ActingIdentity = Depends(acting_identity)) -> str:
    return f"{identity.platform}:{identity.external_id}"


def _seed_repo() -> InMemoryLearningRepository:
    repo = InMemoryLearningRepository()
    repo.add_concept(Concept(id="c1", course_id="course", slug="c1", title="C1"))
    repo.add_item(
        Item(
            id="item-mcq-1",
            concept_id="c1",
            kind="mcq",
            prompt="2+2?",
            payload={"options": ["3", "4"], "correct_index": 1, "explanation": "arithmetic"},
        )
    )
    repo.add_item(
        Item(
            id="item-msq-1",
            concept_id="c1",
            kind="msq",
            prompt="pick the primes",
            payload={"options": ["2", "3", "4"], "correct_indices": [0, 1], "explanation": "2 and 3 are prime"},
        )
    )
    repo.add_item(
        Item(
            id="item-self-rated-1",
            concept_id="c1",
            kind="self_rated",
            prompt="recall the mnemonic",
            payload={"answer": "the model answer"},
        )
    )
    repo.add_item(
        Item(
            id="item-short-answer-1",
            concept_id="c1",
            kind="short_answer",
            prompt="explain recursion",
            payload={"reference": "a function calling itself", "rubric": "mentions base case"},
        )
    )
    repo.add_item(
        Item(
            id="item-teach-back-1",
            concept_id="c1",
            kind="teach_back",
            prompt="teach it back",
            payload={"reference": "ref", "rubric": "rubric"},
        )
    )
    return repo


@pytest.fixture
def repo():
    return _seed_repo()


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_llm_client] = lambda: StubLLMClient(default_grade=0.95)
    app.dependency_overrides[resolve_person_id] = _placeholder_person_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(get_llm_client, None)
        app.dependency_overrides.pop(resolve_person_id, None)


@pytest.fixture
def client_with_stub(repo):
    stub = StubLLMClient(default_grade=0.95)
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_llm_client] = lambda: stub
    app.dependency_overrides[resolve_person_id] = _placeholder_person_id
    try:
        yield TestClient(app), stub
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(get_llm_client, None)
        app.dependency_overrides.pop(resolve_person_id, None)


def test_reviews_requires_service_token(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"choice": 1}},
        headers={"X-Acting-Identity": "slack:U1"},
    )
    assert r.status_code == 401


def test_submit_correct_mcq_review_returns_full_grade_contract(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"choice": 1}},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 1.0
    assert body["rating"] == 3
    assert body["correct"] is True
    assert body["explanation"] == "arithmetic"
    assert body["next_due_at"]
    assert 0 <= body["concept"]["p_known"] <= 1
    assert body["concept"]["mastered"] is False


def test_submit_incorrect_mcq_review(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"choice": 0}},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 0.0
    assert body["rating"] == 1
    assert body["correct"] is False


def test_submit_msq_review_partial_credit(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-msq-1", "idempotency_key": "k1", "response": {"choices": [0]}},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 0.5
    assert body["rating"] == 2
    assert body["correct"] is False


def test_submit_self_rated_review(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-self-rated-1", "idempotency_key": "k1", "response": {"rating": 4}},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 1.0
    assert body["rating"] == 4
    assert body["correct"] is True
    assert body["explanation"] == "the model answer"


def test_submit_short_answer_review_uses_stub_llm(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-short-answer-1", "idempotency_key": "k1", "response": {"text": "a base-case recursive call"}},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 0.95
    assert body["rating"] == 4
    assert body["correct"] is True
    assert "stub grading" in body["explanation"]


def test_response_shape_must_match_item_kind(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"text": "nope"}},
        headers=AUTH,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_unknown_item_id_is_rejected(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "does-not-exist", "idempotency_key": "k1", "response": {"choice": 0}},
        headers=AUTH,
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "item_not_found"


def test_teach_back_returns_no_grader(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-teach-back-1", "idempotency_key": "k1", "response": {"text": "anything"}},
        headers=AUTH,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "no_grader"


def test_duplicate_idempotency_key_replays_original_result(client):
    first = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "dup-key", "response": {"choice": 1}},
        headers=AUTH,
    )
    assert first.status_code == 200

    second = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "dup-key", "response": {"choice": 0}},
        headers=AUTH,
    )
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "idempotency_replay"
    assert detail["result"] == first.json()


def test_learner_id_in_body_is_rejected(client):
    r = client.post(
        "/me/reviews",
        json={
            "item_id": "item-mcq-1",
            "idempotency_key": "k1",
            "response": {"choice": 0},
            "person_id": "someone-else",
        },
        headers=AUTH,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_reviews_are_scoped_to_acting_person(client):
    r1 = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "shared-key", "response": {"choice": 1}},
        headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"},
    )
    assert r1.status_code == 200

    # Same idempotency key, different acting person: not a replay.
    r2 = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "shared-key", "response": {"choice": 0}},
        headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U2"},
    )
    assert r2.status_code == 200
    assert r2.json()["correct"] is False


def test_append_only_review_log_records_the_submission(client, repo):
    client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"choice": 1}},
        headers=AUTH,
    )
    assert len(repo.reviews) == 1
    logged = repo.reviews[0]
    assert logged["item_id"] == "item-mcq-1"
    assert logged["kind"] == "mcq"
    assert logged["grade"] == 1.0
    assert logged["rating"] == 3
    assert logged["source"] == "slack_dm"
    assert logged["asserted_by"] == "slack:U1"


def test_bypassed_mcq_review_caps_grade_and_rating(client):
    r = client.post(
        "/me/reviews",
        json={
            "item_id": "item-mcq-1",
            "idempotency_key": "k1",
            "response": {"choice": 1},
            "bypassed": True,
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    # Hard requirement: a bypassed review never grades above 0.3.
    assert body["grade"] <= 0.3
    assert body["grade"] == 0.0
    assert body["rating"] == 1
    assert body["correct"] is False
    assert body["explanation"] == "arithmetic"
    assert body["bypassed"] is True


def test_bypassed_teach_back_returns_the_canned_reference_instead_of_no_grader(client):
    # teach_back is the one item kind where bypass is the only possible
    # action, so it must not 422 no_grader.
    r = client.post(
        "/me/reviews",
        json={
            "item_id": "item-teach-back-1",
            "idempotency_key": "k1",
            "response": {"text": "anything"},
            "bypassed": True,
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 0.0
    assert body["rating"] == 1
    assert body["correct"] is False
    assert body["explanation"] == "ref"


def test_bypassed_short_answer_never_calls_the_grader(client_with_stub):
    # A bypassed short_answer must not pay for a live grader call whose
    # result is then discarded.
    client, stub = client_with_stub
    r = client.post(
        "/me/reviews",
        json={
            "item_id": "item-short-answer-1",
            "idempotency_key": "k1",
            "response": {"text": "a base-case recursive call"},
            "bypassed": True,
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == 0.0
    assert body["rating"] == 1
    assert body["correct"] is False
    assert body["explanation"] == "a function calling itself"
    assert stub.calls == []


def test_confidence_is_stored_and_echoed(client, repo):
    r = client.post(
        "/me/reviews",
        json={
            "item_id": "item-mcq-1",
            "idempotency_key": "k1",
            "response": {"choice": 1},
            "confidence": 4,
        },
        headers=AUTH,
    )
    assert r.status_code == 200
    assert r.json()["confidence"] == 4
    assert repo.reviews[0]["confidence"] == 4
    assert repo.reviews[0]["bypassed"] is False


def test_confidence_out_of_range_is_rejected(client):
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"choice": 1}, "confidence": 6},
        headers=AUTH,
    )
    assert r.status_code == 422


def test_repeated_correct_reviews_increase_p_known(client):
    first = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k1", "response": {"choice": 1}},
        headers=AUTH,
    )
    second = client.post(
        "/me/reviews",
        json={"item_id": "item-mcq-1", "idempotency_key": "k2", "response": {"choice": 1}},
        headers=AUTH,
    )
    assert second.json()["concept"]["p_known"] > first.json()["concept"]["p_known"]
