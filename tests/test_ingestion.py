"""`GET /admin/ingest` (CI1, `build-day/issues.md` "CI1", KATA-13): the
ingestion trigger, SSE streaming, and LLM concept/item extraction.
`run_ingestion` is exercised directly for the pure extraction helpers and
the empty-source path; the route is exercised through `TestClient` for
auth and the real streamed SSE sequence against the seeded
`1-context/issues.jsonl` fixture. `get_extraction_client` is always
overridden with `StubExtractionClient` so no test ever calls a live model.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item, Topic  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.extraction.sources import concept_frequency  # noqa: E402
from learning_service.extraction.stub import StubExtractionClient  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402

# `learning_service.main` must import before `learning_service.ingestion`:
# `main` registers `ingestion.router` at the bottom of its own module body,
# so importing `ingestion`'s functions first would try to import `main`
# from inside `ingestion`'s own (still-incomplete) import — the same
# ordering every other admin test module (e.g. `test_admin_curriculum.py`)
# relies on by only ever importing `app` from `main`.
from learning_service.main import app, get_extraction_client  # noqa: E402
from learning_service.ingestion import (  # noqa: E402
    extract_concept_drafts,
    extract_related_pairs,
    load_context_issues,
    run_ingestion,
)

TOKEN_HEADER = {"Authorization": "Bearer test-token"}
OPERATOR_AUTH = {**TOKEN_HEADER, "X-Acting-Identity": "slack:operator"}
LEARNER_AUTH = {**TOKEN_HEADER, "X-Acting-Identity": "slack:learner"}

ISSUES = [
    {"key": "PAY-1", "concepts": ["idempotency", "retry-safety"]},
    {"key": "PAY-2", "concepts": ["idempotency"]},
    {"key": "PAY-3", "concepts": []},
]


def _stub_extraction_client(issues: list[dict] | None = None) -> StubExtractionClient:
    return StubExtractionClient(concept_frequency(issues if issues is not None else load_context_issues()))


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
    app.dependency_overrides[get_extraction_client] = _stub_extraction_client
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_extraction_client, None)


# ---------------------------------------------------------------------------
# Pure extraction helpers
# ---------------------------------------------------------------------------


def test_extract_concept_drafts_dedupes_in_first_seen_order_and_cites_issues():
    drafts = extract_concept_drafts(ISSUES)
    assert [d["slug"] for d in drafts] == ["idempotency", "retry-safety"]
    idempotency = next(d for d in drafts if d["slug"] == "idempotency")
    assert idempotency["grounded_in"] == ["PAY-1", "PAY-2"]
    assert idempotency["title"] == "Idempotency"
    assert "PAY-1" in idempotency["description"] and "PAY-2" in idempotency["description"]


def test_extract_concept_drafts_empty_source_yields_nothing():
    assert extract_concept_drafts([]) == []


def test_extract_related_pairs_dedupes_unordered():
    pairs = extract_related_pairs(ISSUES)
    assert len(pairs) == 1
    assert set(pairs[0]) == {"idempotency", "retry-safety"}


def test_load_context_issues_reads_the_seeded_1_context_source():
    # `fixtures/ferry/issues.jsonl`, vendored from `docs/seed/1-context/
    # issues.jsonl` per `fixtures/ferry/SOURCE.md` — the real seeded source
    # the done check triggers ingestion against.
    issues = load_context_issues()
    assert len(issues) > 0
    assert all("key" in issue and "concepts" in issue for issue in issues)


# ---------------------------------------------------------------------------
# `run_ingestion` — empty source
# ---------------------------------------------------------------------------


async def test_run_ingestion_empty_source_yields_only_empty_event_and_writes_nothing(session: AsyncSession):
    events = [chunk async for chunk in run_ingestion(session, _stub_extraction_client(), issues=[])]
    assert events == [b"event: empty\ndata: {}\n\n"]
    assert (await session.execute(select(Course.id))).first() is None


# ---------------------------------------------------------------------------
# `run_ingestion` — the review gate on an untraceable concept
# ---------------------------------------------------------------------------


async def test_run_ingestion_untraceable_concept_gets_no_item_and_stays_draft(session: AsyncSession):
    # `key` missing (not just falsy) is the only way `extract_concept_drafts`
    # produces an empty `grounded_in` — the "no traceable citation" case the
    # done check names explicitly.
    untraceable_issues = [
        {"concepts": ["mystery-concept"]},
        {"key": "PAY-1", "concepts": ["idempotency"]},
    ]
    events = [
        chunk
        async for chunk in run_ingestion(
            session, _stub_extraction_client(untraceable_issues), issues=untraceable_issues
        )
    ]
    assert events[-1].startswith(b"event: done")

    concepts = (await session.execute(select(Concept))).scalars().all()
    mystery = next(c for c in concepts if c.slug == "mystery-concept")
    assert mystery is not None  # still part of the graph — completeness, not correctness

    items = (await session.execute(select(Item).where(Item.concept_id == mystery.id))).scalars().all()
    assert items == []  # nothing was ever drafted for it, so nothing can be published

    idempotency = next(c for c in concepts if c.slug == "idempotency")
    idempotency_items = (await session.execute(select(Item).where(Item.concept_id == idempotency.id))).scalars().all()
    assert len(idempotency_items) == 1
    assert idempotency_items[0].status == "draft"


# ---------------------------------------------------------------------------
# Route — auth
# ---------------------------------------------------------------------------


def test_ingest_requires_operator(client: TestClient):
    r = client.get("/admin/ingest", headers=LEARNER_AUTH)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_operator"


def test_ingest_requires_service_token(client: TestClient):
    r = client.get("/admin/ingest", headers={"X-Acting-Identity": "slack:operator"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Route — the real seeded 1-context source, streamed
# ---------------------------------------------------------------------------


def test_ingest_streams_concepts_then_done(client: TestClient):
    with client.stream("GET", "/admin/ingest", headers=OPERATOR_AUTH) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())

    events = [chunk for chunk in body.split("\n\n") if chunk.strip()]
    assert events[0].startswith("event: concept")
    assert events[-1].startswith("event: done")
    concept_events = [e for e in events if e.startswith("event: concept")]
    assert len(concept_events) == len(extract_concept_drafts(load_context_issues()))


async def test_ingest_route_writes_course_concepts_edges_topic(client: TestClient, session: AsyncSession):
    with client.stream("GET", "/admin/ingest", headers=OPERATOR_AUTH):
        pass

    courses = (await session.execute(select(Course))).scalars().all()
    assert len(courses) == 1
    course = courses[0]

    concepts = (await session.execute(select(Concept).where(Concept.course_id == course.id))).scalars().all()
    expected = extract_concept_drafts(load_context_issues())
    assert len(concepts) == len(expected)
    assert {c.slug for c in concepts} == {d["slug"] for d in expected}

    edges = (await session.execute(select(ConceptEdge))).scalars().all()
    expected_pairs = extract_related_pairs(load_context_issues())
    assert len(edges) == len(expected_pairs)
    assert {e.kind for e in edges} <= {"prerequisite", "related"}

    # "a validated-acyclic graph": the prerequisite subgraph specifically
    # must have no cycle — `curriculum_service.create_edge` enforces this on
    # every write, this just re-checks the graph actually landed that way.
    adjacency: dict[str, list[str]] = {}
    for edge in edges:
        if edge.kind == "prerequisite":
            adjacency.setdefault(edge.from_concept_id, []).append(edge.to_concept_id)

    def _has_cycle() -> bool:
        state: dict[str, int] = {}  # 0 unvisited, 1 in progress, 2 done

        def visit(node: str) -> bool:
            state[node] = 1
            for neighbor in adjacency.get(node, []):
                if state.get(neighbor) == 1 or (state.get(neighbor, 0) == 0 and visit(neighbor)):
                    return True
            state[node] = 2
            return False

        return any(visit(node) for node in adjacency if state.get(node, 0) == 0)

    assert not _has_cycle()

    items = (await session.execute(select(Item).where(Item.concept_id.in_([c.id for c in concepts])))).scalars().all()
    # Every seeded Ferry issue carries a `key`, so every one of the 14
    # concepts has a traceable citation and gets exactly one drafted item.
    assert len(items) == len(concepts)
    assert all(item.status == "draft" for item in items)
    assert all(item.payload["citations"] for item in items)

    topics = (await session.execute(select(Topic).where(Topic.course_id == course.id))).scalars().all()
    assert len(topics) == 1
    assert topics[0].persona_role == "tech_lead"
    assert set(topics[0].grounded_in) == {issue["key"] for issue in load_context_issues()}


async def test_ingest_route_empty_source_reports_no_issues_found(client: TestClient, session: AsyncSession, monkeypatch):
    monkeypatch.setattr("learning_service.ingestion.load_context_issues", lambda: [])

    with client.stream("GET", "/admin/ingest", headers=OPERATOR_AUTH) as r:
        body = "".join(r.iter_text())

    assert body.strip() == "event: empty\ndata: {}"
    assert (await session.execute(select(Course.id))).first() is None
