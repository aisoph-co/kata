"""Identity resolution (AGCTM-27 / spec §Identity, roles, teams → Rules):
exact `(platform, external_id)` match, then `(platform, alt_id)`, else
unknown — a person is never auto-created. Uses an in-memory SQLite engine so
these run without a live Postgres, same as the rest of this suite.

Also covers linking a second platform via a one-time code (AGCTM-34).
"""

import os
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, LinkCode, Person  # noqa: E402
from learning_service.identity.service import resolve_identity  # noqa: E402
from learning_service.main import app  # noqa: E402


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
    person = Person(display_name="Ada Lovelace", email="ada@example.com", is_operator=False)
    session.add(person)
    await session.flush()
    session.add(Identity(person_id=person.id, platform="slack", external_id="U1", alt_id=None))
    session.add(Identity(person_id=person.id, platform="signal", external_id="+15550000", alt_id="uuid-42"))
    await session.commit()
    return person


async def test_resolve_by_exact_platform_and_external_id(session, seeded):
    person = await resolve_identity(session, platform="slack", external_id="U1")
    assert person is not None
    assert person.id == seeded.id


async def test_resolve_falls_back_to_alt_id(session, seeded):
    person = await resolve_identity(session, platform="signal", external_id="not-the-external-id", alt_id="uuid-42")
    assert person is not None
    assert person.id == seeded.id


async def test_resolve_prefers_exact_over_alt_id(session, seeded):
    # exact external_id match wins even when a (wrong) alt_id is also supplied
    person = await resolve_identity(session, platform="slack", external_id="U1", alt_id="does-not-exist")
    assert person is not None
    assert person.id == seeded.id


async def test_resolve_unknown_identity_returns_none(session, seeded):
    assert await resolve_identity(session, platform="slack", external_id="nope") is None
    assert await resolve_identity(session, platform="slack", external_id="nope", alt_id="also-nope") is None


async def test_resolve_never_creates_a_person(session):
    assert await resolve_identity(session, platform="slack", external_id="ghost") is None
    result = await session.execute(select(Person))
    assert result.scalars().all() == []


@pytest.fixture
def client(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_identities_resolve_requires_service_token(client):
    r = client.post("/identities/resolve", json={"platform": "slack", "external_id": "U1"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "unauthorized"


def test_identities_resolve_unknown_identity_is_403(client):
    r = client.post(
        "/identities/resolve",
        headers={"Authorization": "Bearer test-token"},
        json={"platform": "slack", "external_id": "nope"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


def test_identities_resolve_unknown_identity_logs_the_body_fields(client, caplog):
    """The identity here only ever arrives in the request body — this
    warning is the only place an operator sees what failed to resolve."""
    import logging

    with caplog.at_level(logging.INFO, logger="learning_service.auth"):
        r = client.post(
            "/identities/resolve",
            headers={"Authorization": "Bearer test-token"},
            json={"platform": "slack", "external_id": "nope", "alt_id": "also-nope"},
        )
    assert r.status_code == 403
    records = [rec for rec in caplog.records if rec.name == "learning_service.auth"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert "path=/identities/resolve" in message
    assert "slack" in message
    assert "nope" in message
    assert "also-nope" in message
    assert "test-token" not in message


def test_identities_resolve_known_identity_returns_person_summary(client, seeded):
    r = client.post(
        "/identities/resolve",
        headers={"Authorization": "Bearer test-token"},
        json={"platform": "slack", "external_id": "U1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == seeded.id
    assert body["display_name"] == "Ada Lovelace"
    assert body["email"] == "ada@example.com"


def test_identities_resolve_by_alt_id_returns_person_summary(client, seeded):
    r = client.post(
        "/identities/resolve",
        headers={"Authorization": "Bearer test-token"},
        json={"platform": "signal", "external_id": "unused", "alt_id": "uuid-42"},
    )
    assert r.status_code == 200
    assert r.json()["id"] == seeded.id


# ---------------------------------------------------------------------------
# US-A2 (AGCTM-34): POST /me/link-code mints a one-time, 15-minute code;
# POST /identities/link consumes it and creates the new identity.
# ---------------------------------------------------------------------------


def test_me_link_code_requires_service_token(client):
    r = client.post("/me/link-code", headers={"X-Acting-Identity": "slack:U1"})
    assert r.status_code == 401


def test_me_link_code_unknown_identity_is_403(client):
    r = client.post(
        "/me/link-code",
        headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:nope"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


def test_me_link_code_unknown_identity_logs_the_failed_identity(client, caplog):
    """The `request_link_code` flow a real Slack user hits via the Hermes
    bot — the live path this warning exists for."""
    import logging

    with caplog.at_level(logging.INFO, logger="learning_service.auth"):
        r = client.post(
            "/me/link-code",
            headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:nope;alt=also-nope"},
        )
    assert r.status_code == 403
    records = [rec for rec in caplog.records if rec.name == "learning_service.auth"]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    message = records[0].getMessage()
    assert "path=/me/link-code" in message
    assert "slack" in message
    assert "nope" in message
    assert "also-nope" in message
    assert "test-token" not in message


async def test_me_link_code_mints_a_single_use_15_minute_code(client, session, seeded):
    r = client.post(
        "/me/link-code",
        headers={"Authorization": "Bearer test-token", "X-Acting-Identity": "slack:U1"},
    )
    assert r.status_code == 200
    body = r.json()

    result = await session.execute(select(LinkCode).where(LinkCode.code == body["code"]))
    link_code = result.scalar_one()
    assert link_code.person_id == seeded.id
    assert link_code.used_at is None
    expires_at = link_code.expires_at.replace(tzinfo=timezone.utc)
    ttl = expires_at - datetime.now(timezone.utc)
    assert timedelta(minutes=14) < ttl <= timedelta(minutes=15)


def test_identities_link_requires_service_token(client):
    r = client.post("/identities/link", json={"code": "x", "platform": "telegram", "external_id": "T1"})
    assert r.status_code == 401


def test_identities_link_unknown_code_is_403(client):
    r = client.post(
        "/identities/link",
        headers={"Authorization": "Bearer test-token"},
        json={"code": "does-not-exist", "platform": "telegram", "external_id": "T1"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


async def test_identities_link_consumes_the_code_and_creates_the_identity(client, session, seeded):
    session.add(
        LinkCode(
            code="a-valid-code",
            person_id=seeded.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    await session.commit()

    r = client.post(
        "/identities/link",
        headers={"Authorization": "Bearer test-token"},
        json={"code": "a-valid-code", "platform": "telegram", "external_id": "T1", "alt_id": "alt-1"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["person_id"] == seeded.id
    assert body["platform"] == "telegram"
    assert body["external_id"] == "T1"
    assert body["alt_id"] == "alt-1"
    assert body["is_primary"] is False

    person = await resolve_identity(session, platform="telegram", external_id="T1")
    assert person is not None
    assert person.id == seeded.id

    used = await session.execute(select(LinkCode).where(LinkCode.code == "a-valid-code"))
    assert used.scalar_one().used_at is not None


async def test_identities_link_rejects_an_already_used_code(client, session, seeded):
    session.add(
        LinkCode(
            code="used-code",
            person_id=seeded.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            used_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    r = client.post(
        "/identities/link",
        headers={"Authorization": "Bearer test-token"},
        json={"code": "used-code", "platform": "telegram", "external_id": "T2"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


async def test_identities_link_rejects_an_expired_code(client, session, seeded):
    session.add(
        LinkCode(
            code="expired-code",
            person_id=seeded.id,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
    )
    await session.commit()

    r = client.post(
        "/identities/link",
        headers={"Authorization": "Bearer test-token"},
        json={"code": "expired-code", "platform": "telegram", "external_id": "T3"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["code"] == "unknown_identity"


async def test_identities_link_rejects_a_platform_identity_already_linked(client, session, seeded):
    other = Person(display_name="Grace Hopper", email="grace@example.com", is_operator=False)
    session.add(other)
    await session.flush()
    session.add(
        LinkCode(
            code="another-code",
            person_id=other.id,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
    )
    await session.commit()

    r = client.post(
        "/identities/link",
        headers={"Authorization": "Bearer test-token"},
        # slack:U1 is already linked to `seeded` via the `seeded` fixture.
        json={"code": "another-code", "platform": "slack", "external_id": "U1"},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"
