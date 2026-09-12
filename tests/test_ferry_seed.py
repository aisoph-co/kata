"""The `ferry` seed scenario (a teammate's realistic payments-team seed,
vendored from another repo — see `learning_service/fixtures/ferry/SOURCE.md`):
exact counts, Quinn as the sole operator, `confidence`/`bypassed` preserved
as real `review` columns, and — the seed's whole point (KATA-4 done check) —
a fresh `/me/progress` call for Hugo shows non-zero retention, proof the
60-day review history actually loaded and was replayed into `card_state`/
`concept_state`, not just that the rows landed in `review`.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.setdefault("LEARNING_LLM", "stub")
os.environ.pop("DATABASE_URL", None)

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item, Topic, TopicConcept  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import CardState, ConceptState, Review  # noqa: E402
from learning_service.fixtures import load_ferry_scenario  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.seed import seed  # noqa: E402

TOKEN_HEADER = {"Authorization": "Bearer test-token"}


@pytest.fixture
async def sessionmaker(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path}/ferry_seed_test.db"
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def test_ferry_seed_writes_expected_counts(sessionmaker):
    async with sessionmaker() as session:
        seeded = await seed(session, "ferry")

    assert seeded is True

    async with sessionmaker() as session:
        persons = (await session.execute(select(Person))).scalars().all()
        identities = (await session.execute(select(Identity))).scalars().all()
        concepts = (await session.execute(select(Concept))).scalars().all()
        edges = (await session.execute(select(ConceptEdge))).scalars().all()
        items = (await session.execute(select(Item))).scalars().all()
        reviews = (await session.execute(select(Review))).scalars().all()

    assert len(persons) == 10
    assert len(identities) >= 20
    assert len(concepts) == 14
    assert len(edges) == 21
    assert len(items) == 46
    assert len(reviews) == 2199
    assert all(item.status == "published" for item in items)


async def test_ferry_seed_is_idempotent_on_restart(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")

    async with sessionmaker() as session:
        seeded_again = await seed(session, "ferry")

    assert seeded_again is False

    async with sessionmaker() as session:
        persons = (await session.execute(select(Person))).scalars().all()
        reviews = (await session.execute(select(Review))).scalars().all()
    assert len(persons) == 10  # no duplicates
    assert len(reviews) == 2199


async def test_quinn_is_the_sole_operator(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")
        persons = (await session.execute(select(Person))).scalars().all()

    operators = [p for p in persons if p.is_operator]
    assert len(operators) == 1
    assert operators[0].email == "thangquynho@gmail.com"
    assert operators[0].role == "tech_lead"


async def test_shane_role_is_pm(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")
        result = await session.execute(select(Person).where(Person.email == "duyk16@gmail.com"))
        shane = result.scalar_one()
    assert shane.role == "pm"


async def test_ferry_seed_uses_the_real_team_slack_identities(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")
        result = await session.execute(
            select(Person.email, Identity.external_id).join(Identity).where(Identity.platform == "slack")
        )

    slack_by_email = dict(result.all())
    assert {
        "thangquynho@gmail.com": "U0C03BWUVEE",
        "daniel.okonkwo@ferry.example": "U0FERRY02",
        "wyyworks@gmail.com": "U0BVDPP22QL",
        "duyk16@gmail.com": "U0BV21HFZ47",
    }.items() <= slack_by_email.items()


async def test_ferry_seed_writes_five_topics(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")
        topics = (await session.execute(select(Topic))).scalars().all()
        memberships = (await session.execute(select(TopicConcept))).scalars().all()

    assert len(topics) == 5
    assert {t.persona_role for t in topics} == {"tech_lead", "senior_swe", "junior_swe", "pm", "uxd"}
    pm_topic = next(t for t in topics if t.persona_role == "pm")
    assert pm_topic.slug == "sca-exemption-change"
    assert len(memberships) > 0


async def test_ferry_topics_keep_their_source_citations(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")
        topics = (await session.execute(select(Topic))).scalars().all()

    assert all(t.grounded_in for t in topics), "every topic must cite at least one artifact"
    pm_topic = next(t for t in topics if t.persona_role == "pm")
    assert "PAY-1870" in pm_topic.grounded_in


async def test_confidence_and_bypassed_preserved_as_review_columns(sessionmaker):
    scenario = load_ferry_scenario()
    a_bypassed_review = next(r for r in scenario["reviews"] if r["bypassed"] is True)

    async with sessionmaker() as session:
        await seed(session, "ferry")
        row = (
            await session.execute(select(Review).where(Review.idempotency_key == a_bypassed_review["idempotency_key"]))
        ).scalar_one()
        bypassed_count = (await session.execute(select(Review).where(Review.bypassed.is_(True)))).scalars().all()

    assert row.bypassed is True
    assert row.confidence == a_bypassed_review["confidence"]
    assert len(bypassed_count) == 168


async def test_seed_replays_reviews_into_derived_state(sessionmaker):
    """The seed's whole point (KATA-4): loading `ferry` must leave `card_state`/
    `concept_state` populated, not just the `review` log — otherwise
    `/me/progress` reports zero retention even though history "loaded"."""
    async with sessionmaker() as session:
        await seed(session, "ferry")
        card_states = (await session.execute(select(CardState))).scalars().all()
        concept_states = (await session.execute(select(ConceptState))).scalars().all()

    assert len(card_states) > 0
    assert len(concept_states) > 0


@pytest.fixture
async def seeded_client(sessionmaker):
    async with sessionmaker() as session:
        await seed(session, "ferry")

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session
        try:
            yield TestClient(app)
        finally:
            app.dependency_overrides.pop(get_session, None)


def test_hugo_progress_shows_non_zero_retention(seeded_client):
    """KATA-4 done check: a fresh `/me/progress` call for Hugo shows
    non-zero retention — proof the seed actually loaded and was replayed,
    not just that the service is up."""
    r = seeded_client.get(
        "/me/progress", headers={**TOKEN_HEADER, "X-Acting-Identity": "slack:U0FERRY06"}
    )
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert summary["review_count"] > 0
    assert summary["last_active"] is not None
    assert any(band["samples"] > 0 for band in summary["retention"].values())
