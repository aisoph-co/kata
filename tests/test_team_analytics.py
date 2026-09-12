"""`/team/*`: manager-facing analytics over the acting person's subtree.
Same in-memory-SQLite pattern as `test_admin_curriculum.py` and
`test_identity.py`: roster/focus/audit live in SQLite, concepts/items/
derived state live in the in-memory engine repository, same source `/me/*`
and `select_next_items` read (see `analytics/service.py`).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.analytics import service as team_service  # noqa: E402
from learning_service.analytics.models import AuditEntry  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import Concept, ConceptEdge, ConceptState, Item  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app, get_repository  # noqa: E402
from learning_service.roster.models import Focus as DbFocus  # noqa: E402
from learning_service.roster.service import get_subtree_ids  # noqa: E402

TOKEN_HEADER = {"Authorization": "Bearer test-token"}
NOW = datetime(2026, 9, 8, tzinfo=timezone.utc)


def auth_for(external_id: str) -> dict:
    return {**TOKEN_HEADER, "X-Acting-Identity": f"slack:{external_id}"}


# ---------------------------------------------------------------------------
# Fixtures: a small hand-built nested roster (ada -> ben -> carl, dana;
# ada -> erin; lea has no manager and no reports).
# ---------------------------------------------------------------------------


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        yield s
    await engine.dispose()


async def _person(session: AsyncSession, *, name: str, external_id: str, is_operator=False, manager=None) -> Person:
    person = Person(
        display_name=name, email=f"{external_id}@x.example", is_operator=is_operator,
        manager_id=manager.id if manager else None,
    )
    session.add(person)
    await session.flush()
    session.add(Identity(person_id=person.id, platform="slack", external_id=external_id, is_primary=True))
    await session.commit()
    return person


@pytest.fixture
async def roster(session: AsyncSession) -> dict:
    ada = await _person(session, name="Ada", external_id="ada", is_operator=True)
    ben = await _person(session, name="Ben", external_id="ben", manager=ada)
    erin = await _person(session, name="Erin", external_id="erin", manager=ada)
    carl = await _person(session, name="Carl", external_id="carl", manager=ben)
    dana = await _person(session, name="Dana", external_id="dana", manager=ben)
    lea = await _person(session, name="Lea", external_id="lea")
    return {"ada": ada, "ben": ben, "erin": erin, "carl": carl, "dana": dana, "lea": lea}


@pytest.fixture
def repo() -> InMemoryLearningRepository:
    r = InMemoryLearningRepository()
    r.add_concept(Concept(id="c1", course_id="course", slug="c1", title="C1"))
    r.add_concept(Concept(id="c2", course_id="course", slug="c2", title="C2"))
    r.add_item(Item(id="c1-i1", concept_id="c1", kind="mcq", prompt="?", payload={"correct_index": 0}))
    r.add_item(Item(id="c2-i1", concept_id="c2", kind="mcq", prompt="?", payload={"correct_index": 0}))
    return r


@pytest.fixture
def client(session: AsyncSession, repo: InMemoryLearningRepository):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_repository] = lambda: repo
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_repository, None)


async def _audit_rows(session: AsyncSession) -> list[AuditEntry]:
    result = await session.execute(select(AuditEntry))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Subtree resolution
# ---------------------------------------------------------------------------


async def test_subtree_resolution_on_nested_roster(session, roster):
    # `roster.service.get_subtree_ids` includes the root itself (kata's C1
    # semantics; see its own docstring/tests) — `analytics/router.py`'s
    # `require_manager` filters that back out to get the manager's reports.
    ada_subtree = set(await get_subtree_ids(session, roster["ada"].id))
    assert ada_subtree == {
        roster["ada"].id, roster["ben"].id, roster["erin"].id, roster["carl"].id, roster["dana"].id,
    }

    ben_subtree = set(await get_subtree_ids(session, roster["ben"].id))
    assert ben_subtree == {roster["ben"].id, roster["carl"].id, roster["dana"].id}

    assert await get_subtree_ids(session, roster["carl"].id) == [roster["carl"].id]
    assert await get_subtree_ids(session, roster["lea"].id) == [roster["lea"].id]


# ---------------------------------------------------------------------------
# Auth: not_a_manager / outside_subtree
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/team/overview", "/team/recommendations", "/team/digest", "/team/audit"],
)
def test_no_reports_is_not_a_manager(client, roster, path):
    r = client.get(path, headers=auth_for("lea"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_a_manager"


def test_person_outside_subtree_is_403(client, roster):
    # ben manages carl/dana, not erin (erin reports directly to ada).
    r = client.get(f"/team/people/{roster['erin'].id}", headers=auth_for("ben"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"


def test_person_in_subtree_returns_200(client, roster):
    r = client.get(f"/team/people/{roster['carl'].id}", headers=auth_for("ben"))
    assert r.status_code == 200
    assert r.json()["person_id"] == roster["carl"].id


def test_team_person_detail_reports_bypass_rate_retention_calibration(client, repo, roster):
    carl = roster["carl"].id
    repo.append_review(
        {
            "id": "r1", "person_id": carl, "item_id": "c1-i1", "reviewed_at": NOW.isoformat(),
            "kind": "mcq", "grade": 0.3, "rating": 1, "source": "web", "idempotency_key": "k1",
            "asserted_by": "x", "result": {}, "confidence": 3, "bypassed": True,
        }
    )
    r = client.get(f"/team/people/{carl}", headers=auth_for("ben"))
    assert r.status_code == 200
    body = r.json()
    assert body["bypass_rate"] == 1.0
    assert body["calibration"] == pytest.approx((3 - 1) / 4 - 0.0)
    assert body["retention"] == {
        "d1": {"accuracy": None, "samples": 0},
        "d7": {"accuracy": None, "samples": 0},
        "d30": {"accuracy": None, "samples": 0},
    }


def test_team_overview_person_rows_report_bypass_rate(client, repo, roster):
    carl = roster["carl"].id
    repo.append_review(
        {
            "id": "r1", "person_id": carl, "item_id": "c1-i1", "reviewed_at": NOW.isoformat(),
            "kind": "mcq", "grade": 1.0, "rating": 3, "source": "web", "idempotency_key": "k1",
            "asserted_by": "x", "result": {}, "confidence": None, "bypassed": False,
        }
    )
    r = client.get("/team/overview", headers=auth_for("ada"))
    assert r.status_code == 200
    by_id = {p["person_id"]: p for p in r.json()["people"]}
    assert by_id[carl]["bypass_rate"] == 0.0
    assert "retention" not in by_id[carl]
    assert "calibration" not in by_id[carl]


def test_team_overview_reports_subtree_pooled_retention(client, repo, roster):
    # A subtree-level aggregate so the dashboard has a real curve even when
    # no individual clears the 5-sample floor.
    base = NOW
    for i, person_id in enumerate([roster["carl"].id, roster["dana"].id, roster["erin"].id]):
        for offset, day in ((0, 0), (1, 1)):
            repo.append_review(
                {
                    "id": f"r-{person_id}-{offset}", "person_id": person_id, "item_id": "c1-i1",
                    "reviewed_at": (base + timedelta(days=day)).isoformat(),
                    "kind": "mcq", "grade": 1.0, "rating": 3, "source": "web",
                    "idempotency_key": f"k-{person_id}-{offset}", "asserted_by": "x", "result": {},
                    "confidence": None, "bypassed": False,
                }
            )
    r = client.get("/team/overview", headers=auth_for("ada"))
    assert r.status_code == 200
    retention = r.json()["retention"]
    assert retention["d1"]["samples"] == 3  # 3 subtree members, one pair each
    assert retention["d1"]["accuracy"] is None  # still below the 5-sample floor


def test_audit_endpoint_requires_operator(client, roster):
    # ben has reports but is not an operator.
    r = client.get("/team/audit", headers=auth_for("ben"))
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "not_operator"


async def test_audit_row_written_on_not_operator(client, session, roster):
    r = client.get("/team/audit", headers=auth_for("ben"))
    assert r.status_code == 403
    rows = await _audit_rows(session)
    assert len(rows) == 1
    assert rows[0].actor_person_id == roster["ben"].id
    assert rows[0].endpoint == "/team/audit"


# ---------------------------------------------------------------------------
# Audit: one row per read, including 403s, never for 401 or /me/*
# ---------------------------------------------------------------------------


async def test_audit_row_written_on_success(client, session, roster):
    r = client.get("/team/overview", headers=auth_for("ada"))
    assert r.status_code == 200
    rows = await _audit_rows(session)
    assert len(rows) == 1
    assert rows[0].actor_person_id == roster["ada"].id
    assert rows[0].endpoint == "/team/overview"


async def test_audit_row_written_on_not_a_manager(client, session, roster):
    r = client.get("/team/overview", headers=auth_for("lea"))
    assert r.status_code == 403
    rows = await _audit_rows(session)
    assert len(rows) == 1
    assert rows[0].actor_person_id == roster["lea"].id


async def test_audit_row_written_on_outside_subtree(client, session, roster):
    r = client.get(f"/team/people/{roster['erin'].id}", headers=auth_for("ben"))
    assert r.status_code == 403
    rows = await _audit_rows(session)
    assert len(rows) == 1
    assert rows[0].actor_person_id == roster["ben"].id


async def test_no_audit_row_without_service_token(client, session, roster):
    r = client.get("/team/overview", headers={"X-Acting-Identity": "slack:ada"})
    assert r.status_code == 401
    assert await _audit_rows(session) == []


async def test_no_audit_row_for_me_next(client, session, roster):
    client.get("/me/next", headers=auth_for("ada"))
    assert await _audit_rows(session) == []


async def test_team_audit_read_is_scoped_to_own_subtree_and_operator_only(client, session, roster):
    client.get("/team/overview", headers=auth_for("ada"))  # ada's own row
    client.get(f"/team/people/{roster['carl'].id}", headers=auth_for("ben"))  # ben, in ada's subtree

    r = client.get("/team/audit", headers=auth_for("ada"))
    assert r.status_code == 200
    actor_ids = {e["actor_person_id"] for e in r.json()["entries"]}
    assert roster["ada"].id in actor_ids
    assert roster["ben"].id in actor_ids


# ---------------------------------------------------------------------------
# Focus: permissions and next-item ranking
# ---------------------------------------------------------------------------


def test_focus_create_outside_subtree_is_403(client, roster):
    r = client.post(
        "/team/focus",
        headers=auth_for("ben"),
        json={"scope_kind": "person", "scope_person_id": roster["erin"].id, "concept_id": "c1"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"


def test_focus_create_unknown_concept_is_422(client, roster):
    r = client.post(
        "/team/focus",
        headers=auth_for("ben"),
        json={"scope_kind": "person", "scope_person_id": roster["carl"].id, "concept_id": "no-such-concept"},
    )
    assert r.status_code == 422


async def test_focus_create_and_delete_by_setter(client, session, roster):
    r = client.post(
        "/team/focus",
        headers=auth_for("ben"),
        json={"scope_kind": "person", "scope_person_id": roster["carl"].id, "concept_id": "c1", "weight": 2.0},
    )
    assert r.status_code == 200
    focus_id = r.json()["id"]
    assert r.json()["set_by"] == roster["ben"].id

    d = client.delete(f"/team/focus/{focus_id}", headers=auth_for("ben"))
    assert d.status_code == 204

    rows = (await session.execute(select(DbFocus).where(DbFocus.id == focus_id))).scalars().all()
    assert rows == []


def test_focus_delete_by_scope_owner_who_did_not_set_it(client, roster):
    # ada sets a focus on carl (in ada's subtree); ben also has carl in his
    # subtree and can remove it even though ben didn't set it.
    r = client.post(
        "/team/focus",
        headers=auth_for("ada"),
        json={"scope_kind": "person", "scope_person_id": roster["carl"].id, "concept_id": "c1"},
    )
    focus_id = r.json()["id"]
    d = client.delete(f"/team/focus/{focus_id}", headers=auth_for("ben"))
    assert d.status_code == 204


def test_focus_delete_by_neither_setter_nor_scope_owner_is_403(client, roster):
    r = client.post(
        "/team/focus",
        headers=auth_for("ada"),
        json={"scope_kind": "person", "scope_person_id": roster["erin"].id, "concept_id": "c1"},
    )
    focus_id = r.json()["id"]
    # ben doesn't manage erin and didn't set this focus.
    d = client.delete(f"/team/focus/{focus_id}", headers=auth_for("ben"))
    assert d.status_code == 403
    assert d.json()["detail"]["code"] == "outside_subtree"


def test_focus_delete_missing_is_404(client, roster):
    d = client.delete("/team/focus/does-not-exist", headers=auth_for("ada"))
    assert d.status_code == 404


async def test_subtree_scope_focus_applies_to_every_member(client, session, roster):
    # ada (not ben) sets the subtree focus, rooted at ben — a descendant of
    # ada's — so it should cascade to ben, carl, and dana. That expansion
    # (subtree membership) happens when `SqlLearningRepository.load()`
    # hydrates this row, not at write time (see `analytics/service.
    # create_focus`). This test only owns the write: one `subtree` row,
    # rooted at ben.
    r = client.post(
        "/team/focus",
        headers=auth_for("ada"),
        json={"scope_kind": "subtree", "scope_person_id": roster["ben"].id, "concept_id": "c1"},
    )
    assert r.status_code == 200

    rows = (await session.execute(select(DbFocus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].scope_kind == "subtree"
    assert rows[0].scope_person_id == roster["ben"].id


async def test_subtree_focus_rooted_at_self_covers_the_whole_team_including_self(client, session, roster):
    # Spec §Roster Rules: subtree of a person = that person plus all
    # transitive reports, so "focus my whole team" is a manager rooting a
    # `subtree` focus at themself. Unlike reads (which exclude the caller),
    # focus scope includes self.
    r = client.post(
        "/team/focus",
        headers=auth_for("ada"),
        json={"scope_kind": "subtree", "scope_person_id": roster["ada"].id, "concept_id": "c1", "weight": 1.5},
    )
    assert r.status_code == 200

    rows = (await session.execute(select(DbFocus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].scope_kind == "subtree"
    assert rows[0].scope_person_id == roster["ada"].id
    assert rows[0].weight == 1.5


async def test_focus_post_is_idempotent_per_scope_and_concept(client, session, roster):
    body = {"scope_kind": "person", "scope_person_id": roster["carl"].id, "concept_id": "c1", "weight": 1.5}
    r1 = client.post("/team/focus", headers=auth_for("ben"), json=body)
    r2 = client.post("/team/focus", headers=auth_for("ben"), json=body)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]

    # Without the fix, two identical POSTs used to create two rows (and
    # `_focus_weight` multiplied over every match: 1.5**2 == 2.25). It must
    # stay one row, weight 1.5.
    rows = (await session.execute(select(DbFocus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].weight == 1.5


async def test_focus_post_idempotent_upsert_replaces_weight_and_expiry(client, session, roster):
    scope_person_id = roster["carl"].id
    r1 = client.post(
        "/team/focus",
        headers=auth_for("ben"),
        json={"scope_kind": "person", "scope_person_id": scope_person_id, "concept_id": "c1", "weight": 1.5},
    )
    r2 = client.post(
        "/team/focus",
        headers=auth_for("ben"),
        json={"scope_kind": "person", "scope_person_id": scope_person_id, "concept_id": "c1", "weight": 3.0},
    )
    assert r1.json()["id"] == r2.json()["id"]
    assert r2.json()["weight"] == 3.0

    rows = (await session.execute(select(DbFocus))).scalars().all()
    assert len(rows) == 1
    assert rows[0].weight == 3.0


def test_focus_tilts_next_item_ranking_for_a_person_in_scope(client, roster):
    # A POST /team/focus row only tilts `select_next_items` through
    # `SqlLearningRepository.load()` (the bare in-memory `repo` fixture used
    # elsewhere in this file has no DB access, so it can't see this write).
    # This test only owns the write itself.
    r = client.post(
        "/team/focus",
        headers=auth_for("ben"),
        json={"scope_kind": "person", "scope_person_id": roster["carl"].id, "concept_id": "c2", "weight": 5.0},
    )
    assert r.status_code == 200
    assert r.json()["concept_id"] == "c2"
    assert r.json()["weight"] == 5.0


# ---------------------------------------------------------------------------
# Recommendations: formula and the "unlocked for >= half the subtree" filter
# ---------------------------------------------------------------------------


def test_recommendation_ranks_by_dependents_count_when_mastery_ties():
    r = InMemoryLearningRepository()
    r.add_concept(Concept(id="root-x", course_id="c", slug="x", title="X"))
    r.add_concept(Concept(id="root-y", course_id="c", slug="y", title="Y"))
    r.add_concept(Concept(id="child-z", course_id="c", slug="z", title="Z"))
    r.add_edge(ConceptEdge(from_concept_id="root-x", to_concept_id="child-z", kind="prerequisite"))

    subtree_ids = ["p1", "p2"]
    recs = team_service.build_recommendations(r, subtree_ids, NOW)
    by_id = {rec["concept_id"]: rec for rec in recs}
    # child-z is locked for everyone (nobody has mastered root-x), so it's
    # excluded by the "unlocked for >= half the subtree" filter.
    assert "child-z" not in by_id
    # root-x has one dependent (child-z), root-y has none -> root-x ranks first.
    assert by_id["root-x"]["dependents_count"] == 1
    assert by_id["root-y"]["dependents_count"] == 0
    assert recs[0]["concept_id"] == "root-x"


def test_recommendation_unlocked_for_at_least_half_the_subtree():
    r = InMemoryLearningRepository()
    r.add_concept(Concept(id="prereq", course_id="c", slug="prereq", title="Prereq", mastery_threshold=0.5))
    r.add_concept(Concept(id="gated", course_id="c", slug="gated", title="Gated"))
    r.add_edge(ConceptEdge(from_concept_id="prereq", to_concept_id="gated", kind="prerequisite"))

    subtree_ids = ["p1", "p2", "p3"]
    # Only p1 has mastered the prereq: 1 of 3 unlocked, below half -> excluded.
    r.add_concept_state(ConceptState(person_id="p1", concept_id="prereq", p_known=0.9))
    recs = team_service.build_recommendations(r, subtree_ids, NOW)
    assert "gated" not in {rec["concept_id"] for rec in recs}

    # p2 also masters it: 2 of 3 unlocked, >= half -> included.
    r.add_concept_state(ConceptState(person_id="p2", concept_id="prereq", p_known=0.9))
    recs = team_service.build_recommendations(r, subtree_ids, NOW)
    assert "gated" in {rec["concept_id"] for rec in recs}


# ---------------------------------------------------------------------------
# Digest
# ---------------------------------------------------------------------------


def test_digest_days_parameter_changes_the_echoed_window(client, roster):
    headers = auth_for("ada")

    default = client.get("/team/digest", headers=headers).json()
    custom = client.get("/team/digest?days=14", headers=headers).json()

    default_span = datetime.fromisoformat(default["period_end"]) - datetime.fromisoformat(default["period_start"])
    custom_span = datetime.fromisoformat(custom["period_end"]) - datetime.fromisoformat(custom["period_start"])
    assert abs(default_span - timedelta(days=7)) < timedelta(seconds=5)
    assert abs(custom_span - timedelta(days=14)) < timedelta(seconds=5)


def test_digest_days_out_of_range_is_422(client, roster):
    r = client.get("/team/digest?days=91", headers=auth_for("ada"))
    assert r.status_code == 422
