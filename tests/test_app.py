"""App skeleton (spec §API → Authentication): `/health` unauthenticated,
`/whoami` requires a bearer token and `X-Acting-Identity`.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base  # noqa: E402
from learning_service.main import app  # noqa: E402

client = TestClient(app)


def test_health_is_unauthenticated():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["version"] == "1.2.1"


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session():
        async with sessionmaker() as s:
            yield s

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_session, None)
        await engine.dispose()


def test_health_db_reaches_the_database(db_session):
    r = client.get("/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "reachable"}


def test_whoami_requires_bearer_token():
    r = client.get("/whoami", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_whoami_requires_acting_identity_header():
    r = client.get("/whoami", headers={"Authorization": "Bearer test-token"})
    assert r.status_code == 422


def test_whoami_returns_the_parsed_identity():
    r = client.get(
        "/whoami", headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "signal:+1555;alt=uuid-1"}
    )
    assert r.status_code == 200
    assert r.json()["acting_identity"] == {"platform": "signal", "external_id": "+1555", "alt_id": "uuid-1"}
