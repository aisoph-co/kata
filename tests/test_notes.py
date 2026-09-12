"""`GET/POST /me/notes`, `DELETE /me/notes/{id}`, `DELETE /me/notes` wiring:
own-rows-only scoping, count/length caps -> 422 `note_cap`.

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

from learning_service.engine.models import LearnerNote  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.main import ActingIdentity, acting_identity, app, get_repository, resolve_person_id  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}
OTHER_AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U2"}
PERSON = "slack:U1"
OTHER_PERSON = "slack:U2"
NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


async def _placeholder_person_id(identity: ActingIdentity = Depends(acting_identity)) -> str:
    return f"{identity.platform}:{identity.external_id}"


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


def test_me_notes_requires_token(client):
    r = client.get("/me/notes", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_post_me_notes_requires_token(client):
    r = client.post("/me/notes", headers={"X-Acting-Identity": "slack:U1"}, json={"text": "hi"})
    assert r.status_code == 401


def test_me_notes_empty(client):
    r = client.get("/me/notes", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"notes": []}


def test_create_and_list_me_note(client):
    r = client.post("/me/notes", headers=AUTH, json={"text": "prefers examples in Go"})
    assert r.status_code == 200
    body = r.json()
    assert body["text"] == "prefers examples in Go"
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]

    r = client.get("/me/notes", headers=AUTH)
    notes = r.json()["notes"]
    assert len(notes) == 1
    assert notes[0]["id"] == body["id"]


def test_me_notes_never_returns_another_persons_rows(repo, client):
    repo.add_note(LearnerNote(id="n1", person_id=PERSON, text="mine", created_at=NOW, updated_at=NOW))
    repo.add_note(LearnerNote(id="n2", person_id=OTHER_PERSON, text="theirs", created_at=NOW, updated_at=NOW))

    r = client.get("/me/notes", headers=AUTH)
    texts = [n["text"] for n in r.json()["notes"]]
    assert texts == ["mine"]

    r = client.get("/me/notes", headers=OTHER_AUTH)
    texts = [n["text"] for n in r.json()["notes"]]
    assert texts == ["theirs"]


def test_me_notes_newest_first(repo, client):
    for i in range(3):
        repo.add_note(
            LearnerNote(
                id=f"n{i}", person_id=PERSON, text=f"note {i}", created_at=NOW + timedelta(seconds=i), updated_at=NOW
            )
        )

    r = client.get("/me/notes", headers=AUTH)
    assert [n["id"] for n in r.json()["notes"]] == ["n2", "n1", "n0"]


def test_note_over_500_chars_returns_note_cap(client):
    r = client.post("/me/notes", headers=AUTH, json={"text": "x" * 501})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "note_cap"


def test_21st_note_returns_note_cap(client):
    for i in range(20):
        r = client.post("/me/notes", headers=AUTH, json={"text": f"note {i}"})
        assert r.status_code == 200
    r = client.post("/me/notes", headers=AUTH, json={"text": "one too many"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "note_cap"


def test_note_cap_is_scoped_per_person(client):
    for i in range(20):
        assert client.post("/me/notes", headers=AUTH, json={"text": f"note {i}"}).status_code == 200
    assert client.post("/me/notes", headers=AUTH, json={"text": "over cap"}).status_code == 422
    # A different person is unaffected by this person's cap.
    assert client.post("/me/notes", headers=OTHER_AUTH, json={"text": "first note"}).status_code == 200


def test_delete_one_me_note(repo, client):
    repo.add_note(LearnerNote(id="n1", person_id=PERSON, text="mine", created_at=NOW, updated_at=NOW))
    repo.add_note(LearnerNote(id="n2", person_id=PERSON, text="also mine", created_at=NOW, updated_at=NOW))

    r = client.delete("/me/notes/n1", headers=AUTH)
    assert r.status_code == 204

    r = client.get("/me/notes", headers=AUTH)
    assert [n["id"] for n in r.json()["notes"]] == ["n2"]


def test_delete_one_me_note_not_owned_is_404(repo, client):
    repo.add_note(LearnerNote(id="n1", person_id=OTHER_PERSON, text="theirs", created_at=NOW, updated_at=NOW))

    r = client.delete("/me/notes/n1", headers=AUTH)
    assert r.status_code == 404
    assert client.get("/me/notes", headers=OTHER_AUTH).json()["notes"][0]["id"] == "n1"


def test_delete_one_me_note_unknown_id_is_404(client):
    r = client.delete("/me/notes/does-not-exist", headers=AUTH)
    assert r.status_code == 404


def test_delete_me_notes_wipes_only_the_callers_rows(repo, client):
    repo.add_note(LearnerNote(id="n1", person_id=PERSON, text="mine", created_at=NOW, updated_at=NOW))
    repo.add_note(LearnerNote(id="n2", person_id=OTHER_PERSON, text="theirs", created_at=NOW, updated_at=NOW))

    r = client.delete("/me/notes", headers=AUTH)
    assert r.status_code == 204

    assert client.get("/me/notes", headers=AUTH).json()["notes"] == []
    other_texts = [n["text"] for n in client.get("/me/notes", headers=OTHER_AUTH).json()["notes"]]
    assert other_texts == ["theirs"]
