"""`GET /me/answers` + `DELETE /me/answers` wiring: pagination, own-rows-only
scoping (incl. operators), delete-all, and the 90-day retention purge.
Answer capture on `POST /me/reviews` for `short_answer` items is covered
here too since that's the only writer of `answer` rows.

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

from learning_service.engine.models import Answer, Concept, Item  # noqa: E402
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

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}
OTHER_AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U2"}
PERSON = "slack:U1"
OTHER_PERSON = "slack:U2"
NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


async def _placeholder_person_id(identity: ActingIdentity = Depends(acting_identity)) -> str:
    return f"{identity.platform}:{identity.external_id}"


def _seed_short_answer_item(repo: InMemoryLearningRepository) -> None:
    repo.add_concept(Concept(id="c1", course_id="course", slug="c1", title="C1"))
    repo.add_item(
        Item(
            id="item-short-answer-1",
            concept_id="c1",
            kind="short_answer",
            prompt="Explain recursion.",
            payload={"reference": "a function that calls itself", "rubric": "mentions base case"},
        )
    )


@pytest.fixture
def repo() -> InMemoryLearningRepository:
    return InMemoryLearningRepository()


@pytest.fixture
def client(repo):
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_llm_client] = lambda: StubLLMClient()
    app.dependency_overrides[resolve_person_id] = _placeholder_person_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(get_llm_client, None)
        app.dependency_overrides.pop(resolve_person_id, None)


def test_me_answers_requires_token(client):
    r = client.get("/me/answers", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_delete_me_answers_requires_token(client):
    r = client.delete("/me/answers", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_me_answers_empty(client):
    r = client.get("/me/answers", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"answers": [], "next_cursor": None}


def test_submitting_short_answer_review_records_an_answer(repo, client):
    _seed_short_answer_item(repo)
    r = client.post(
        "/me/reviews",
        json={"item_id": "item-short-answer-1", "idempotency_key": "k1", "response": {"text": "calls itself with a base case"}},
        headers=AUTH,
    )
    assert r.status_code == 200

    r = client.get("/me/answers", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert len(body["answers"]) == 1
    assert body["answers"][0]["text"] == "calls itself with a base case"
    assert body["answers"][0]["review_id"]
    assert body["answers"][0]["id"]
    assert body["answers"][0]["created_at"]
    assert body["next_cursor"] is None


def test_mcq_review_does_not_record_an_answer(client):
    r = client.get("/me/answers", headers=AUTH)
    assert r.json() == {"answers": [], "next_cursor": None}


def test_me_answers_never_returns_another_persons_rows(repo, client):
    repo.add_answer(Answer(id="a1", review_id="r1", person_id=PERSON, text="mine", created_at=NOW))
    repo.add_answer(Answer(id="a2", review_id="r2", person_id=OTHER_PERSON, text="theirs", created_at=NOW))

    r = client.get("/me/answers", headers=AUTH)
    texts = [a["text"] for a in r.json()["answers"]]
    assert texts == ["mine"]

    # An operator identity has no way to pass another person's id at all —
    # the route only ever reads the caller's own person_id off the acting
    # identity — so this is the same isolation, exercised from the other side.
    r = client.get("/me/answers", headers=OTHER_AUTH)
    texts = [a["text"] for a in r.json()["answers"]]
    assert texts == ["theirs"]


def test_me_answers_paginates_newest_first(repo, client):
    for i in range(5):
        repo.add_answer(
            Answer(id=f"a{i}", review_id=f"r{i}", person_id=PERSON, text=f"answer {i}", created_at=NOW + timedelta(seconds=i))
        )

    r = client.get("/me/answers", headers=AUTH, params={"limit": 2})
    body = r.json()
    assert [a["id"] for a in body["answers"]] == ["a4", "a3"]
    assert body["next_cursor"] is not None

    r = client.get("/me/answers", headers=AUTH, params={"limit": 2, "cursor": body["next_cursor"]})
    body = r.json()
    assert [a["id"] for a in body["answers"]] == ["a2", "a1"]
    assert body["next_cursor"] is not None

    r = client.get("/me/answers", headers=AUTH, params={"limit": 2, "cursor": body["next_cursor"]})
    body = r.json()
    assert [a["id"] for a in body["answers"]] == ["a0"]
    assert body["next_cursor"] is None


def test_delete_me_answers_wipes_only_the_callers_rows(repo, client):
    repo.add_answer(Answer(id="a1", review_id="r1", person_id=PERSON, text="mine", created_at=NOW))
    repo.add_answer(Answer(id="a2", review_id="r2", person_id=OTHER_PERSON, text="theirs", created_at=NOW))

    r = client.delete("/me/answers", headers=AUTH)
    assert r.status_code == 204

    assert client.get("/me/answers", headers=AUTH).json()["answers"] == []
    other_texts = [a["text"] for a in client.get("/me/answers", headers=OTHER_AUTH).json()["answers"]]
    assert other_texts == ["theirs"]


def test_answers_older_than_90_days_are_purged_on_read(repo, client):
    stale = NOW - timedelta(days=91)
    fresh = NOW - timedelta(days=1)
    repo.add_answer(Answer(id="stale", review_id="r1", person_id=PERSON, text="old", created_at=stale))
    repo.add_answer(Answer(id="fresh", review_id="r2", person_id=PERSON, text="new", created_at=fresh))

    r = client.get("/me/answers", headers=AUTH)
    texts = [a["text"] for a in r.json()["answers"]]
    assert texts == ["new"]
    assert repo.answers_for(PERSON) == [a for a in repo.answers if a.id == "fresh"]


def test_purge_answers_older_than_removes_expired_rows_across_all_persons():
    repo = InMemoryLearningRepository()
    cutoff = NOW - timedelta(days=90)
    repo.add_answer(Answer(id="old", review_id="r1", person_id=PERSON, text="old", created_at=cutoff - timedelta(days=1)))
    repo.add_answer(Answer(id="new", review_id="r2", person_id=OTHER_PERSON, text="new", created_at=cutoff + timedelta(days=1)))

    purged = repo.purge_answers_older_than(cutoff)

    assert purged == 1
    assert [a.id for a in repo.answers] == ["new"]
