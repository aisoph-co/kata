"""`POST /admin/replay`: truncate-and-rebuild contract, including the
"replay reproduces live state exactly" regression the issue's done-check
calls out by name.

Unlike the reference build this was ported from, `/admin/replay` requires
`require_operator` (a real `Person.is_operator` check via a DB session) per
`openapi.yaml`'s documented `403 "Not an operator"` — so these tests seed a
real sqlite-backed roster (an operator `Person` + identity) and override
`get_session`, in addition to overriding `get_repository` with the
in-memory engine repository the reference tests use.
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import CardState, Concept, ConceptState, Item  # noqa: E402
from learning_service.engine.replay import apply_review, parse_reviewed_at, rebuild_derived_state  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app, get_repository  # noqa: E402

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}
NON_OPERATOR_AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U2"}


def _seed_repo() -> InMemoryLearningRepository:
    repo = InMemoryLearningRepository()
    repo.add_concept(Concept(id="c1", course_id="course", slug="c1", title="C1"))
    repo.add_item(
        Item(
            id="item-1",
            concept_id="c1",
            kind="mcq",
            prompt="2+2?",
            payload={"options": ["3", "4"], "correct_index": 1, "explanation": "arithmetic"},
        )
    )
    return repo


@pytest.fixture
def repo():
    return _seed_repo()


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        operator = Person(display_name="Operator", email="operator@x.example", is_operator=True)
        s.add(operator)
        await s.flush()
        s.add(Identity(person_id=operator.id, platform="slack", external_id="U1", is_primary=True))
        non_operator = Person(display_name="Learner", email="learner@x.example", is_operator=False)
        s.add(non_operator)
        await s.flush()
        s.add(Identity(person_id=non_operator.id, platform="slack", external_id="U2", is_primary=True))
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture
def client(repo, session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_repository] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_repository, None)


def _log(repo: InMemoryLearningRepository, *, person_id: str, item_id: str, reviewed_at: str, rating: int) -> None:
    repo.append_review(
        {
            "person_id": person_id,
            "item_id": item_id,
            "reviewed_at": reviewed_at,
            "kind": "mcq",
            "grade": 1.0 if rating >= 3 else 0.0,
            "rating": rating,
            "source": "web",
            "idempotency_key": f"{person_id}-{reviewed_at}",
            "asserted_by": f"web:{person_id}",
        }
    )


def test_replay_requires_service_token(client):
    r = client.post("/admin/replay")
    assert r.status_code == 401


def test_replay_requires_operator(client):
    r = client.post("/admin/replay", headers=NON_OPERATOR_AUTH)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_operator"


def test_replay_on_an_empty_log_returns_zero_counts(client):
    r = client.post("/admin/replay", headers=AUTH)
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "replayed_reviews": 0, "card_state_count": 0, "concept_state_count": 0}


def test_replay_truncates_stale_derived_state_before_rebuilding(client, repo):
    # Garbage left over from a bug: no matching review, must not survive replay.
    repo.card_states[("ghost", "ghost")] = CardState(
        person_id="ghost", item_id="ghost", stability=1.0, difficulty=1.0, due_at=datetime.now(timezone.utc)
    )
    repo.concept_states[("ghost", "ghost")] = ConceptState(person_id="ghost", concept_id="ghost")

    _log(repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-01T09:00:00Z", rating=3)

    r = client.post("/admin/replay", headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "replayed_reviews": 1, "card_state_count": 1, "concept_state_count": 1}
    assert ("ghost", "ghost") not in repo.card_states
    assert ("ghost", "ghost") not in repo.concept_states
    assert ("p1", "item-1") in repo.card_states


def test_replay_matches_a_live_submission_through_me_reviews(client, repo):
    submit = client.post(
        "/me/reviews",
        json={"item_id": "item-1", "idempotency_key": "k1", "response": {"choice": 1}},
        headers=AUTH,
    )
    assert submit.status_code == 200
    live_card_states = dict(repo.card_states)
    live_concept_states = dict(repo.concept_states)
    assert live_card_states and live_concept_states

    replay = client.post("/admin/replay", headers=AUTH)
    assert replay.status_code == 200
    assert replay.json()["replayed_reviews"] == 1
    assert repo.card_states == live_card_states
    assert repo.concept_states == live_concept_states


def test_replay_orders_same_timestamp_reviews_by_id(client, repo):
    # Same person, same instant: order must follow `id`, not insertion luck.
    repo.add_item(Item(id="item-2", concept_id="c1", kind="mcq", prompt="?", payload={"correct_index": 0}))
    same_instant = "2026-08-01T09:00:00Z"
    repo.append_review(
        {
            "id": "b",
            "person_id": "p1",
            "item_id": "item-1",
            "reviewed_at": same_instant,
            "kind": "mcq",
            "grade": 1.0,
            "rating": 3,
            "source": "web",
            "idempotency_key": "p1-b",
            "asserted_by": "web:p1",
        }
    )
    repo.append_review(
        {
            "id": "a",
            "person_id": "p1",
            "item_id": "item-2",
            "reviewed_at": same_instant,
            "kind": "mcq",
            "grade": 1.0,
            "rating": 3,
            "source": "web",
            "idempotency_key": "p1-a",
            "asserted_by": "web:p1",
        }
    )

    # Ids "a" then "b": the order `rebuild_derived_state` sorts the tie into
    # — build `expected` the same way `/admin/replay` itself does (a full
    # rebuild from the logged rows), not by chaining bare `apply_review`
    # calls: those don't append to the log, so a fold triggered by this
    # very same timestamp tie (see `engine/replay.py`) would have nothing
    # to read `expected`'s history from.
    expected = _seed_repo()
    expected.add_item(Item(id="item-2", concept_id="c1", kind="mcq", prompt="?", payload={"correct_index": 0}))
    _log(expected, person_id="p1", item_id="item-1", reviewed_at=same_instant, rating=3)
    expected.reviews[-1]["id"] = "b"
    _log(expected, person_id="p1", item_id="item-2", reviewed_at=same_instant, rating=3)
    expected.reviews[-1]["id"] = "a"
    rebuild_derived_state(expected)

    r = client.post("/admin/replay", headers=AUTH)
    assert r.status_code == 200
    assert repo.concept_states[("p1", "c1")] == expected.concept_states[("p1", "c1")]


def _multi_person_scenario() -> InMemoryLearningRepository:
    """A small hand-built "golden-like" scenario (three persons, a two-
    concept course with a prerequisite edge, reviews spread over several
    simulated days) — a self-contained stand-in for the fixtures/generate.py
    golden-scenario infrastructure (out of scope here; see the ported
    fixture skip note), used to exercise the same "replay reproduces live
    state exactly" property end to end across more than one item/person."""
    repo = InMemoryLearningRepository()
    repo.add_concept(Concept(id="found", course_id="course", slug="found", title="Foundation", mastery_threshold=0.6))
    repo.add_concept(Concept(id="adv", course_id="course", slug="adv", title="Advanced"))
    from learning_service.engine.models import ConceptEdge

    repo.add_edge(ConceptEdge(from_concept_id="found", to_concept_id="adv", kind="prerequisite"))
    repo.add_item(Item(id="found-i1", concept_id="found", kind="mcq", prompt="?", payload={"correct_index": 0}))
    repo.add_item(Item(id="adv-i1", concept_id="adv", kind="mcq", prompt="?", payload={"correct_index": 0}))

    base = datetime(2026, 8, 1, tzinfo=timezone.utc)
    reviews = []
    ratings_cycle = [3, 3, 1, 4, 2, 3, 3]
    for p in range(3):
        person_id = f"p{p}"
        for day in range(10):
            item_id = "found-i1" if day % 2 == 0 else "adv-i1"
            reviews.append(
                {
                    "id": f"{person_id}-r{day}",
                    "person_id": person_id,
                    "item_id": item_id,
                    "reviewed_at": (base + timedelta(days=day, hours=p)).isoformat(),
                    "kind": "mcq",
                    "grade": 1.0,
                    "rating": ratings_cycle[(day + p) % len(ratings_cycle)],
                    "source": "web",
                    "idempotency_key": f"{person_id}-r{day}",
                    "asserted_by": f"web:{person_id}",
                }
            )
    for review in reviews:
        repo.append_review(dict(review))
    return repo, reviews


async def test_replay_reproduces_live_state_over_a_multi_person_multi_day_scenario():
    """The AC that matters (KAT-X4): after simulating several days of
    reviews across multiple persons/items/concepts, replayed
    `card_state`/`concept_state` equal live state exactly."""
    live_repo, reviews = _multi_person_scenario()
    live_repo.clear_derived_state()
    for review in sorted(reviews, key=lambda r: (r["person_id"], r["reviewed_at"], r["id"])):
        item = live_repo.get_item(review["item_id"])
        apply_review(
            live_repo,
            person_id=review["person_id"],
            item_id=review["item_id"],
            concept_id=item.concept_id,
            kind=review["kind"],
            rating=review["rating"],
            reviewed_at=parse_reviewed_at(review["reviewed_at"]),
            review_id=review["id"],
        )

    replay_repo, _ = _multi_person_scenario()
    # Stale state from a prior (buggy) computation must not survive replay.
    replay_repo.card_states[("ghost", "ghost")] = CardState(
        person_id="ghost", item_id="ghost", stability=1.0, difficulty=1.0, due_at=datetime.now(timezone.utc)
    )

    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        operator = Person(display_name="Operator", email="operator2@x.example", is_operator=True)
        s.add(operator)
        await s.flush()
        s.add(Identity(person_id=operator.id, platform="slack", external_id="U1", is_primary=True))
        await s.commit()

        async def override_get_session():
            yield s

        app.dependency_overrides[get_session] = override_get_session
        app.dependency_overrides[get_repository] = lambda: replay_repo
        try:
            client = TestClient(app)
            r = client.post("/admin/replay", headers=AUTH)
        finally:
            app.dependency_overrides.pop(get_session, None)
            app.dependency_overrides.pop(get_repository, None)
    await engine.dispose()

    assert r.status_code == 200
    assert r.json() == {
        "status": "ok",
        "replayed_reviews": len(reviews),
        "card_state_count": len(live_repo.card_states),
        "concept_state_count": len(live_repo.concept_states),
    }
    assert replay_repo.card_states == live_repo.card_states
    assert replay_repo.concept_states == live_repo.concept_states


def test_apply_review_out_of_order_matches_rebuild_derived_state():
    """DB-free pin for the fold itself (`_fold_card_state`/
    `_fold_concept_state`, engine/replay.py) — no HTTP, no SQL."""
    repo = _seed_repo()

    later_reviewed_at = parse_reviewed_at("2026-08-20T00:00:00Z")
    apply_review(
        repo, person_id="p1", item_id="item-1", concept_id="c1", kind="mcq", rating=4,
        reviewed_at=later_reviewed_at, review_id="later-review",
    )
    _log(repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-20T00:00:00Z", rating=4)
    repo.reviews[-1]["id"] = "later-review"

    # Out of order: earlier than "later-review", already on record for the
    # same item/concept — must trigger both folds, not the O(1) update.
    earlier_reviewed_at = parse_reviewed_at("2026-08-01T00:00:00Z")
    new_card, new_concept_state = apply_review(
        repo, person_id="p1", item_id="item-1", concept_id="c1", kind="mcq", rating=1,
        reviewed_at=earlier_reviewed_at, review_id="earlier-review",
    )

    expected_repo = _seed_repo()
    _log(expected_repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-20T00:00:00Z", rating=4)
    expected_repo.reviews[-1]["id"] = "later-review"
    _log(expected_repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-01T00:00:00Z", rating=1)
    expected_repo.reviews[-1]["id"] = "earlier-review"
    rebuild_derived_state(expected_repo)

    assert new_card == expected_repo.card_states[("p1", "item-1")]
    assert new_concept_state == expected_repo.concept_states[("p1", "c1")]


def test_apply_review_equal_timestamp_ties_break_by_id_not_arrival_order():
    """KAT-X4 regression (AE Reviewer, `Verdict: fix`): two *live* reviews
    sharing the exact same `reviewed_at` must fold in `(reviewed_at, id)`
    order — the same tie-break `rebuild_derived_state` uses — regardless of
    which one happened to arrive (and get applied) first. A strict `<` in
    `apply_review`'s out-of-order check let an equal-timestamp collision
    fall through to the O(1) incremental branch, which applies purely in
    arrival order; this pins the fix (`<=`) against a case where arrival
    order ("z" then "a") is the reverse of id order.
    """
    repo = _seed_repo()
    same_instant = parse_reviewed_at("2026-08-15T00:00:00Z")

    # Arrives first: review_id "z", lexicographically *after* "a".
    apply_review(
        repo, person_id="p1", item_id="item-1", concept_id="c1", kind="mcq", rating=4,
        reviewed_at=same_instant, review_id="z",
    )
    _log(repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-15T00:00:00Z", rating=4)
    repo.reviews[-1]["id"] = "z"

    # Arrives second: review_id "a" — same instant, but sorts *before* "z".
    new_card, new_concept_state = apply_review(
        repo, person_id="p1", item_id="item-1", concept_id="c1", kind="mcq", rating=1,
        reviewed_at=same_instant, review_id="a",
    )
    _log(repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-15T00:00:00Z", rating=1)
    repo.reviews[-1]["id"] = "a"

    # The canonical order a full replay would use is by id ("a" then "z"),
    # the reverse of arrival order — build the expected state that way.
    expected_repo = _seed_repo()
    _log(expected_repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-15T00:00:00Z", rating=4)
    expected_repo.reviews[-1]["id"] = "z"
    _log(expected_repo, person_id="p1", item_id="item-1", reviewed_at="2026-08-15T00:00:00Z", rating=1)
    expected_repo.reviews[-1]["id"] = "a"
    rebuild_derived_state(expected_repo)

    assert new_card == expected_repo.card_states[("p1", "item-1")]
    assert new_concept_state == expected_repo.concept_states[("p1", "c1")]
