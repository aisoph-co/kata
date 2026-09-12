"""`POST /admin/ingest` (KATA-13/CI1): the trigger streams one ndjson event
per row it writes, through the *existing* `/admin/courses` -> `/admin/
concepts` -> `/admin/edges` -> `/admin/topics` -> `/admin/items` routes.
Same in-memory SQLite fixture as `test_admin_curriculum.py`.
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service import seed as seed_module  # noqa: E402
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


def _events(response) -> list[dict]:
    lines = [line for line in response.text.split("\n") if line.strip()]
    return [json.loads(line) for line in lines]


@pytest.fixture
def two_concept_source(monkeypatch, tmp_path):
    """Only `idempotency`/`retry-safety` get a real citation here — the
    other 12 real `seed_data/concepts.json` concepts are still created (the
    curated content doesn't depend on this file), but their items must come
    back `draft`, and only the `junior_swe` topic has anything to cite."""
    issues = [{"key": "PAY-1", "concepts": ["idempotency", "retry-safety"], "title": "t1"}]
    (tmp_path / "issues.jsonl").write_text("\n".join(json.dumps(i) for i in issues), encoding="utf-8")
    monkeypatch.setenv("KATA_SEED_CONTEXT_DIR", str(tmp_path))
    return tmp_path


def test_requires_operator(client):
    r = client.post("/admin/ingest", headers=LEARNER_AUTH)
    assert r.status_code == 403


def test_empty_source_streams_one_empty_event_and_writes_nothing(client, tmp_path, monkeypatch):
    monkeypatch.setenv("KATA_SEED_CONTEXT_DIR", str(tmp_path))  # no issues.jsonl in this directory

    r = client.post("/admin/ingest", headers=OPERATOR_AUTH)
    assert r.status_code == 200
    assert _events(r) == [{"type": "empty", "message": "no issues found"}]

    assert client.get("/admin/courses", headers=OPERATOR_AUTH).json()["courses"] == []


def test_ingestion_writes_the_real_fourteen_concept_course(client, two_concept_source):
    r = client.post("/admin/ingest", headers=OPERATOR_AUTH)
    assert r.status_code == 200
    events = _events(r)

    concept_events = [e for e in events if e["type"] == "concept"]
    assert len(concept_events) == 14
    assert events[0]["type"] == "concept"  # the very first event is already a concept, not a course/setup event

    done = events[-1]
    assert done["type"] == "done"
    assert done["counts"]["concepts"] == 14
    assert done["counts"]["edges"] == 21  # 14 prerequisite + 7 related, from seed_data/concepts.json
    assert done["counts"]["topics"] == 1  # only junior_swe has a cited concept in this fixture
    # idempotency (4 items) + retry-safety (3 items) are the only cited concepts.
    assert done["counts"]["items_published"] == 7
    assert done["counts"]["items_draft"] == 46 - 7


def test_uncited_concepts_get_draft_items_never_published(client, two_concept_source):
    client.post("/admin/ingest", headers=OPERATOR_AUTH)

    concepts = client.get("/admin/concepts", headers=OPERATOR_AUTH).json()["concepts"]
    double_entry_id = next(c["id"] for c in concepts if c["slug"] == "double-entry")
    items = client.get("/admin/items", headers=OPERATOR_AUTH, params={"concept_id": double_entry_id}).json()["items"]
    assert len(items) == 3
    assert all(i["status"] == "draft" for i in items)

    idempotency_id = next(c["id"] for c in concepts if c["slug"] == "idempotency")
    items = client.get("/admin/items", headers=OPERATOR_AUTH, params={"concept_id": idempotency_id}).json()["items"]
    assert all(i["status"] == "published" for i in items)
    assert all(i["payload"].get("grounded_in") == ["PAY-1"] for i in items)


def test_prerequisite_edges_are_written_acyclic(client, two_concept_source):
    client.post("/admin/ingest", headers=OPERATOR_AUTH)

    edges = client.get("/admin/edges", headers=OPERATOR_AUTH, params={"kind": "prerequisite"}).json()["edges"]
    assert len(edges) == 14  # every write already passed `curriculum_service`'s own acyclicity check


def test_retriggering_is_a_no_op_not_a_duplicate_or_a_crash(client, two_concept_source):
    first = _events(client.post("/admin/ingest", headers=OPERATOR_AUTH))
    second = _events(client.post("/admin/ingest", headers=OPERATOR_AUTH))

    assert first[-1]["counts"]["concepts"] == second[-1]["counts"]["concepts"] == 14
    assert first[-1]["counts"]["topics"] == second[-1]["counts"]["topics"] == 1  # reused, still reported
    assert second[-1]["counts"]["edges"] == 0
    assert second[-1]["counts"]["items_published"] == 0
    assert second[-1]["counts"]["items_draft"] == 0

    assert len(client.get("/admin/courses", headers=OPERATOR_AUTH).json()["courses"]) == 1


async def test_reuses_a_core_already_seeded_by_learning_seed_ferry_at_boot(client, session, monkeypatch):
    """`LEARNING_SEED=ferry` (`learning_service/serve.py`) loads this exact
    course/concept/edge/item content directly, before this route ever runs
    — the Dockerfile documents it as set on the live Railway service. That
    loader creates the course with no slug at all, so a title-only match is
    the one thing standing between this route and a duplicate course."""

    class _FakeScope:
        async def __aenter__(self_inner):
            self_inner._s = session
            return session

        async def __aexit__(self_inner, *exc):
            return None

    monkeypatch.setattr(seed_module, "session_scope", lambda: _FakeScope())
    seeded = await seed_module.seed_ferry()
    assert seeded["status"] == "loaded"

    events = _events(client.post("/admin/ingest", headers=OPERATOR_AUTH))
    done = events[-1]
    assert done["type"] == "done"
    assert done["counts"]["concepts"] == 14  # reused, not re-created
    assert done["counts"]["edges"] == 0  # all 21 already existed
    assert done["counts"]["topics"] == 5  # the one thing `seed.py` never writes
    assert done["counts"]["items_published"] == 0  # all 46 already existed, published by `seed.py` itself

    assert len(client.get("/admin/courses", headers=OPERATOR_AUTH).json()["courses"]) == 1


def test_real_ferry_seed_produces_fourteen_concepts_and_one_topic_per_role(client, monkeypatch):
    monkeypatch.delenv("KATA_SEED_CONTEXT_DIR", raising=False)  # the real vendored seed

    events = _events(client.post("/admin/ingest", headers=OPERATOR_AUTH))
    done = events[-1]
    assert done["type"] == "done"
    assert done["counts"]["concepts"] == 14
    assert done["counts"]["edges"] == 21
    assert done["counts"]["items_published"] == 46
    assert done["counts"]["items_draft"] == 0

    topics = client.get("/topics", headers=OPERATOR_AUTH, params={"all_roles": "true"}).json()["topics"]
    assert {t["persona_role"] for t in topics} == {"pm", "uxd", "junior_swe", "senior_swe", "tech_lead"}
