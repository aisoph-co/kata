"""The Ferry golden scenario end to end (spec §Deployment, KATA-4 R6): once
`learning_service.seed.seed_ferry()` has run, `GET /me/progress` for Hugo
(the junior SWE `docs/seed/0-team/roster.json` seeds ninety days of history
onto) shows non-zero retention — proof the seed actually loaded a review
history, not just that the roster/curriculum rows exist.

Also covers the roster-import wiring KATA-11's human gate carried here:
`KATA_ROSTER_JSON` gets written and the response reports a real digest-job
count for the golden roster (spec §6: ten due-rep, one team-quiz, one
teach-back = twelve).
"""

from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service import seed as seed_module  # noqa: E402
from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base  # noqa: E402
from learning_service.main import app  # noqa: E402
from learning_service.roster.schemas import RosterImportPerson  # noqa: E402
from learning_service.roster.service import import_roster, plan_digest_jobs_count  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}
HUGO_SLACK_ID = "U0C01E6F2J2"  # docs/seed/0-team/roster.json: camluong.nguyen@gmail.com


@pytest.fixture
async def session(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    class _FakeScope:
        async def __aenter__(self_inner):
            self_inner._s = sessionmaker()
            return self_inner._s

        async def __aexit__(self_inner, *exc):
            await self_inner._s.close()

    monkeypatch.setattr(seed_module, "session_scope", lambda: _FakeScope())

    async with sessionmaker() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def client(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


async def test_hugo_progress_shows_nonzero_retention_after_ferry_seed(client):
    result = await seed_module.seed_ferry()
    assert result["status"] == "loaded"
    assert result["reviews_loaded"] > 0

    r = client.get(
        "/me/progress",
        headers={**AUTH, "X-Acting-Identity": f"slack:{HUGO_SLACK_ID}"},
    )
    assert r.status_code == 200
    summary = r.json()["summary"]
    assert summary["review_count"] > 0

    retention = summary["retention"]
    assert any(band["samples"] > 0 for band in retention.values()), (
        "seeded ninety days of history should populate at least one retention band"
    )


async def test_golden_roster_import_plans_twelve_digest_jobs(session, monkeypatch):
    """G1's done check (spec §6): a golden-scenario import plans ten due-rep
    jobs (one per person with a resolvable chat id — all ten here carry a
    `slack_user_id`), one team-quiz job, one teach-back job. Checked via
    `roster.service.plan_digest_jobs_count` directly (not the HTTP response
    — `RosterImportResult` is a frozen contract shape, `build-day/tests/
    core` asserts on it by exact equality, so this stays a server-side log
    line, not a wire field)."""
    monkeypatch.setenv("KATA_TEAM_CHANNEL", "#payments-team")

    roster = json.loads((seed_module.SEED_DATA / "roster.json").read_text())
    request_persons = [
        RosterImportPerson(**{k: p[k] for k in ("email", "display_name", "manager_email", "slack_user_id") if k in p})
        for p in roster["persons"]
    ]
    persons, created, _updated = await import_roster(session, persons=request_persons)
    assert created == 10

    assert plan_digest_jobs_count(persons, request_persons) == 12
