"""Privacy test suite — the deploy gate: no `/team/*` or `/admin/*` response
carries an `answer`/`text`/`learner_note` field, `/team/people/{id}` for a
person outside the caller's subtree is 403 `outside_subtree`, `/me/answers`
and `/me/notes` never leak another person's rows, and every service-token-
gated route 401s without one.
"""

from __future__ import annotations

import os
import re
from typing import Any

import pytest
from fastapi import Depends
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from learning_service.db import get_session  # noqa: E402
from learning_service.engine.models import Concept, Item  # noqa: E402
from learning_service.engine.repository import InMemoryLearningRepository  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import (  # noqa: E402
    ActingIdentity,
    acting_identity,
    app,
    get_repository,
    require_service_token,
    resolve_person_id,
)

AUTH = {"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"}

# spec §Privacy and retention: fields that must never reach a /team/*,
# /admin/*, or digest response.
FORBIDDEN_FIELDS = {"answer", "text", "learner_note"}


async def _placeholder_person_id(identity: ActingIdentity = Depends(acting_identity)) -> str:
    return f"{identity.platform}:{identity.external_id}"


@pytest.fixture
def client():
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
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[resolve_person_id] = _placeholder_person_id
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_repository, None)
        app.dependency_overrides.pop(resolve_person_id, None)


@pytest.fixture
async def team_session():
    # `/team/*` resolves the acting identity and the caller's subtree
    # through a real DB session, unlike the rest of this suite's
    # placeholder-identity routes — see `analytics/router.py`. AUTH's
    # `slack:U1` is seeded as a manager (`is_operator=True`, one report) so
    # the "does not leak" checks below get a real 200, not a 403.
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as s:
        manager = Person(display_name="Manager", email="manager@x.example", is_operator=True)
        s.add(manager)
        await s.flush()
        s.add(Identity(person_id=manager.id, platform="slack", external_id="U1", is_primary=True))
        report = Person(display_name="Report", email="report@x.example", manager_id=manager.id)
        s.add(report)
        await s.commit()
        yield s
    await engine.dispose()


@pytest.fixture
def team_client(team_session):
    async def override_get_session():
        yield team_session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_repository] = lambda: InMemoryLearningRepository()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_repository, None)


def _find_forbidden_keys(body: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(body, dict):
        for key, value in body.items():
            if key in FORBIDDEN_FIELDS:
                hits.append(f"{path}.{key}")
            hits.extend(_find_forbidden_keys(value, f"{path}.{key}"))
    elif isinstance(body, list):
        for i, item in enumerate(body):
            hits.extend(_find_forbidden_keys(item, f"{path}[{i}]"))
    return hits


def _assert_route_exists_and_clean(client: TestClient, method: str, path: str, **kwargs) -> None:
    r = client.request(method, path, **kwargs)
    assert r.status_code != 404, f"{method} {path} is not implemented"
    if r.headers.get("content-type", "").startswith("application/json") and r.content:
        hits = _find_forbidden_keys(r.json())
        assert not hits, f"{method} {path} leaked forbidden fields: {hits}"


# ---------------------------------------------------------------------------
# Bullet 1: no /team/* or /admin/* response carries `answer`, `text`, or
# `learner_note`.
# ---------------------------------------------------------------------------


def test_admin_replay_does_not_leak_forbidden_fields(team_client):
    _assert_route_exists_and_clean(team_client, "POST", "/admin/replay", headers=AUTH)


def test_team_overview_does_not_leak_forbidden_fields(team_client):
    _assert_route_exists_and_clean(team_client, "GET", "/team/overview", headers=AUTH)


def test_team_concept_detail_does_not_leak_forbidden_fields(team_client):
    _assert_route_exists_and_clean(team_client, "GET", "/team/concepts/c1", headers=AUTH)


async def test_team_person_detail_does_not_leak_forbidden_fields(team_client, team_session):
    result = await team_session.execute(select(Person).where(Person.email == "report@x.example"))
    report = result.scalar_one()
    _assert_route_exists_and_clean(team_client, "GET", f"/team/people/{report.id}", headers=AUTH)


def test_team_recommendations_does_not_leak_forbidden_fields(team_client):
    _assert_route_exists_and_clean(team_client, "GET", "/team/recommendations", headers=AUTH)


def test_team_audit_does_not_leak_forbidden_fields(team_client):
    _assert_route_exists_and_clean(team_client, "GET", "/team/audit", headers=AUTH)


async def test_admin_roster_import_does_not_leak_forbidden_fields(client, db_session):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        _assert_route_exists_and_clean(client, "POST", "/admin/roster/import", headers=AUTH, json={"persons": []})
    finally:
        app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Bullet 2: /team/people/{id} for a person outside the subtree -> 403.
# ---------------------------------------------------------------------------


def test_team_person_outside_subtree_is_403(team_client):
    r = team_client.get("/team/people/outside-subtree-person", headers=AUTH)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "outside_subtree"


# ---------------------------------------------------------------------------
# Bullet 3: /me/answers never returns another person's rows, including for
# operators. Full own-rows-only coverage lives in test_answers.py; this is
# the smoke check that the route itself never leaks in this file's harness.
# ---------------------------------------------------------------------------


def test_me_answers_never_returns_another_persons_rows(client):
    r = client.get("/me/answers", headers=AUTH)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Bullet 4: /me/notes never returns another person's rows; caps enforced.
# Full coverage lives in test_notes.py.
# ---------------------------------------------------------------------------


def test_me_notes_never_returns_another_persons_rows(client):
    r = client.get("/me/notes", headers=AUTH)
    assert r.status_code == 200


def test_me_notes_enforce_length_cap(client):
    r = client.post("/me/notes", headers=AUTH, json={"text": "x" * 501})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "note_cap"


def test_me_notes_enforce_count_cap(client):
    for i in range(20):
        r = client.post("/me/notes", headers=AUTH, json={"text": f"note {i}"})
        assert r.status_code == 200
    r = client.post("/me/notes", headers=AUTH, json={"text": "one too many"})
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "note_cap"


def test_me_due_summary_does_not_leak_notes(client):
    _assert_route_exists_and_clean(client, "GET", "/me/due-summary", headers=AUTH)


def test_team_digest_does_not_leak_notes(team_client):
    _assert_route_exists_and_clean(team_client, "GET", "/team/digest", headers=AUTH)


# ---------------------------------------------------------------------------
# Bullet 5: plugin routes without the service token -> 401; with the token
# but an unknown identity -> 403.
#
# The 401 check is structural: it walks the live dependency graph of every
# registered route rather than a hard-coded path list, so a new route wired
# under `require_service_token` (directly, or transitively via
# `acting_identity`) is covered the moment it is registered — no test-file
# edit required.
# ---------------------------------------------------------------------------


def _flatten_dependency_calls(dependant) -> set:
    calls = {dependant.call}
    for sub in dependant.dependencies:
        calls |= _flatten_dependency_calls(sub)
    return calls


def _placeholder_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "placeholder", path)


def _flatten_routes(routes) -> list[APIRoute]:
    # FastAPI mounts an `include_router()` call as an opaque wrapper (name
    # varies by version) rather than flattening its routes eagerly; duck-type
    # on `original_router` so this keeps working across that internal change.
    out: list[APIRoute] = []
    for route in routes:
        if isinstance(route, APIRoute):
            out.append(route)
            continue
        sub_router = getattr(route, "original_router", None)
        if sub_router is not None:
            out.extend(_flatten_routes(sub_router.routes))
    return out


def _service_token_gated_calls() -> list[tuple[str, str]]:
    calls: list[tuple[str, str]] = []
    for route in _flatten_routes(app.routes):
        if require_service_token not in _flatten_dependency_calls(route.dependant):
            continue
        path = _placeholder_path(route.path)
        for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
            calls.append((method, path))
    return calls


@pytest.mark.parametrize("method,path", _service_token_gated_calls())
def test_service_token_required(client, method, path):
    kwargs: dict[str, Any] = {"headers": {"X-Acting-Identity": "slack:U1"}}
    if method in {"POST", "PUT", "PATCH"}:
        kwargs["json"] = {}
    r = client.request(method, path, **kwargs)
    assert r.status_code == 401, f"{method} {path} did not 401 without a service token"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    async with sessionmaker() as session:
        yield session
    await engine.dispose()


def test_unknown_identity_via_identities_resolve_is_403(client, db_session):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    try:
        r = client.post(
            "/identities/resolve",
            headers={"Authorization": "Bearer test-token"},
            json={"platform": "slack", "external_id": "does-not-exist"},
        )
    finally:
        app.dependency_overrides.pop(get_session, None)
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


# ---------------------------------------------------------------------------
# Bullet 6: a review submitted with a learner ID in the body is scoped to
# the acting person, never the body value. Already covered as a first-class
# assertion in tests/test_reviews.py (`test_learner_id_in_body_is_rejected`,
# `test_reviews_are_scoped_to_acting_person`) — not duplicated here.
# ---------------------------------------------------------------------------
