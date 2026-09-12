"""`GET/POST /me/notes`, `DELETE /me/notes/{id}`, `DELETE /me/notes` (spec
§Privacy and retention, §API): 20-note/500-char caps -> 422 `note_cap`,
ownership isolation, no retention window.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402

AUTH_1 = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}
AUTH_2 = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U2"}


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
    p1 = Person(display_name="Ada", email="ada@example.com")
    p2 = Person(display_name="Bea", email="bea@example.com")
    session.add_all([p1, p2])
    await session.flush()
    session.add_all(
        [
            Identity(person_id=p1.id, platform="slack", external_id="U1"),
            Identity(person_id=p2.id, platform="slack", external_id="U2"),
        ]
    )
    await session.commit()
    return {"p1": p1, "p2": p2}


@pytest.fixture
def client(session: AsyncSession):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_create_and_list_own_notes(client, seeded):
    r = client.post("/me/notes", json={"text": "prefers examples in Go"}, headers=AUTH_1)
    assert r.status_code == 200
    note = r.json()
    assert note["text"] == "prefers examples in Go"

    listed = client.get("/me/notes", headers=AUTH_1).json()["notes"]
    assert len(listed) == 1
    assert listed[0]["id"] == note["id"]


def test_notes_are_scoped_to_the_acting_person(client, seeded):
    client.post("/me/notes", json={"text": "mine"}, headers=AUTH_1)
    client.post("/me/notes", json={"text": "not mine"}, headers=AUTH_2)

    listed_1 = client.get("/me/notes", headers=AUTH_1).json()["notes"]
    assert [n["text"] for n in listed_1] == ["mine"]


def test_note_over_500_chars_is_note_cap_422(client, seeded):
    r = client.post("/me/notes", json={"text": "x" * 501}, headers=AUTH_1)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "note_cap"


def test_21st_note_is_note_cap_422(client, seeded):
    for i in range(20):
        r = client.post("/me/notes", json={"text": f"note {i}"}, headers=AUTH_1)
        assert r.status_code == 200
    r = client.post("/me/notes", json={"text": "one too many"}, headers=AUTH_1)
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "note_cap"
    listed = client.get("/me/notes", headers=AUTH_1).json()["notes"]
    assert len(listed) == 20


def test_delete_one_note_not_owned_by_caller_is_404(client, seeded):
    note = client.post("/me/notes", json={"text": "mine"}, headers=AUTH_2).json()
    r = client.delete(f"/me/notes/{note['id']}", headers=AUTH_1)
    assert r.status_code == 404
    # not actually deleted
    assert len(client.get("/me/notes", headers=AUTH_2).json()["notes"]) == 1


def test_delete_one_note(client, seeded):
    note = client.post("/me/notes", json={"text": "mine"}, headers=AUTH_1).json()
    r = client.delete(f"/me/notes/{note['id']}", headers=AUTH_1)
    assert r.status_code == 204
    assert client.get("/me/notes", headers=AUTH_1).json()["notes"] == []


def test_delete_all_notes_only_deletes_the_callers_own(client, seeded):
    client.post("/me/notes", json={"text": "mine"}, headers=AUTH_1)
    client.post("/me/notes", json={"text": "not mine"}, headers=AUTH_2)

    r = client.delete("/me/notes", headers=AUTH_1)
    assert r.status_code == 204
    assert client.get("/me/notes", headers=AUTH_1).json()["notes"] == []
    assert len(client.get("/me/notes", headers=AUTH_2).json()["notes"]) == 1
