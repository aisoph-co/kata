"""`POST /admin/roster/import` (US-A3, AGCTM-35, spec §Identity, roles,
teams → Roster seeding): upsert persons by email, link `manager_id` from
manager email (in either import order), and create a `slack` identity when
a Slack user ID is supplied. Uses an in-memory SQLite engine, same as
`test_identity.py`.
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

os.environ.setdefault("SERVICE_TOKEN", "test-token")
os.environ.pop("DATABASE_URL", None)

from learning_service.db import get_session  # noqa: E402
from learning_service.identity.models import Base, Identity, Person  # noqa: E402
from learning_service.main import app  # noqa: E402

AUTH = {"Authorization": "Bearer test-token"}


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
def client(session):
    async def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_requires_service_token(client):
    r = client.post("/admin/roster/import", json={"persons": []})
    assert r.status_code == 401


def test_empty_import_is_a_no_op(client):
    r = client.post("/admin/roster/import", headers=AUTH, json={"persons": []})
    assert r.status_code == 200
    assert r.json() == {"created": 0, "updated": 0, "persons": []}


def test_creates_a_person_by_email(client):
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 1
    assert body["updated"] == 0
    [person] = body["persons"]
    assert person["email"] == "ada@example.com"
    assert person["display_name"] == "Ada Lovelace"
    assert person["is_operator"] is False


async def test_reimporting_the_same_email_updates_instead_of_duplicating(client, session):
    client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ada@example.com", "display_name": "Ada"}]},
    )
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace"}]},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created"] == 0
    assert body["updated"] == 1
    assert body["persons"][0]["display_name"] == "Ada Lovelace"

    result = await session.execute(select(Person).where(Person.email == "ada@example.com"))
    assert len(result.scalars().all()) == 1


async def test_manager_email_links_the_tree_regardless_of_list_order(client, session):
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={
            "persons": [
                {"email": "grace@example.com", "display_name": "Grace Hopper", "manager_email": "ada@example.com"},
                {"email": "ada@example.com", "display_name": "Ada Lovelace"},
            ]
        },
    )
    assert r.status_code == 200

    result = await session.execute(select(Person).where(Person.email == "grace@example.com"))
    grace = result.scalar_one()
    result = await session.execute(select(Person).where(Person.email == "ada@example.com"))
    ada = result.scalar_one()
    assert grace.manager_id == ada.id


async def test_manager_email_resolves_against_an_already_imported_person(client, session):
    session.add(Person(email="ada@example.com", display_name="Ada Lovelace", is_operator=False))
    await session.commit()

    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={
            "persons": [
                {"email": "grace@example.com", "display_name": "Grace Hopper", "manager_email": "ada@example.com"},
            ]
        },
    )
    assert r.status_code == 200

    result = await session.execute(select(Person).where(Person.email == "ada@example.com"))
    ada = result.scalar_one()
    result = await session.execute(select(Person).where(Person.email == "grace@example.com"))
    grace = result.scalar_one()
    assert grace.manager_id == ada.id


def test_unknown_manager_email_is_a_validation_error(client):
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={
            "persons": [
                {"email": "grace@example.com", "display_name": "Grace Hopper", "manager_email": "nobody@example.com"},
            ]
        },
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


async def test_slack_user_id_creates_an_identity(client, session):
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={
            "persons": [
                {"email": "ada@example.com", "display_name": "Ada Lovelace", "slack_user_id": "U1"},
            ]
        },
    )
    assert r.status_code == 200

    result = await session.execute(select(Identity).where(Identity.platform == "slack", Identity.external_id == "U1"))
    identity = result.scalar_one()
    result = await session.execute(select(Person).where(Person.email == "ada@example.com"))
    ada = result.scalar_one()
    assert identity.person_id == ada.id
    assert identity.is_primary is True


async def test_reimporting_the_same_slack_user_id_does_not_duplicate_the_identity(client, session):
    body = {"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace", "slack_user_id": "U1"}]}
    client.post("/admin/roster/import", headers=AUTH, json=body)
    r = client.post("/admin/roster/import", headers=AUTH, json=body)
    assert r.status_code == 200

    result = await session.execute(select(Identity).where(Identity.platform == "slack", Identity.external_id == "U1"))
    assert len(result.scalars().all()) == 1


async def test_is_operator_true_creates_an_operator(client, session):
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={
            "persons": [
                {"email": "quinn@example.com", "display_name": "Quinn", "is_operator": True, "role": "tech_lead"},
            ]
        },
    )
    assert r.status_code == 200
    person = r.json()["persons"][0]
    assert person["is_operator"] is True
    assert person["role"] == "tech_lead"

    result = await session.execute(select(Person).where(Person.email == "quinn@example.com"))
    quinn = result.scalar_one()
    assert quinn.is_operator is True
    assert quinn.role == "tech_lead"


async def test_reimporting_without_is_operator_or_role_leaves_them_unchanged(client, session):
    client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "quinn@example.com", "display_name": "Quinn", "is_operator": True, "role": "pm"}]},
    )
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "quinn@example.com", "display_name": "Quinn Halloran"}]},
    )
    assert r.status_code == 200
    person = r.json()["persons"][0]
    assert person["is_operator"] is True
    assert person["role"] == "pm"


def test_unknown_role_is_a_validation_error(client):
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "x@example.com", "display_name": "X", "role": "wizard"}]},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


def test_slack_user_id_already_linked_to_a_different_person_is_a_validation_error(client):
    client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace", "slack_user_id": "U1"}]},
    )
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "grace@example.com", "display_name": "Grace Hopper", "slack_user_id": "U1"}]},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


async def test_import_creates_a_web_identity_from_the_normalized_email(client, session):
    """Contract change #6: every imported person gets a `(web, <normalized
    email>)` identity, so web sign-in only ever resolves, never writes."""
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "Ada@Example.com", "display_name": "Ada Lovelace"}]},
    )
    assert r.status_code == 200

    result = await session.execute(
        select(Identity).where(Identity.platform == "web", Identity.external_id == "ada@example.com")
    )
    identity = result.scalar_one()
    result = await session.execute(select(Person).where(Person.email == "Ada@Example.com"))
    assert identity.person_id == result.scalar_one().id
    assert identity.is_primary is True


async def test_web_identity_is_created_even_without_a_slack_user_id(client, session):
    client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "grace@example.com", "display_name": "Grace Hopper"}]},
    )
    result = await session.execute(select(Identity).where(Identity.platform == "web"))
    assert [i.external_id for i in result.scalars().all()] == ["grace@example.com"]


async def test_reimporting_does_not_duplicate_the_web_identity(client, session):
    body = {"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace"}]}
    client.post("/admin/roster/import", headers=AUTH, json=body)
    r = client.post("/admin/roster/import", headers=AUTH, json=body)
    assert r.status_code == 200

    result = await session.execute(
        select(Identity).where(Identity.platform == "web", Identity.external_id == "ada@example.com")
    )
    assert len(result.scalars().all()) == 1


def test_web_identity_conflict_across_case_variant_emails_is_a_validation_error(client):
    client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace"}]},
    )
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ADA@EXAMPLE.COM", "display_name": "Someone Else"}]},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"


async def test_web_identity_is_not_primary_when_slack_already_claimed_it(client, session):
    """One primary per person: a roster entry with a `slack_user_id` gets its
    primary identity from slack, so the web identity rides alongside."""
    client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={
            "persons": [
                {"email": "ada@example.com", "display_name": "Ada Lovelace", "slack_user_id": "U9"}
            ]
        },
    )
    result = await session.execute(select(Person).where(Person.email == "ada@example.com"))
    ada = result.scalar_one()
    result = await session.execute(select(Identity).where(Identity.person_id == ada.id))
    primary_by_platform = {i.platform: i.is_primary for i in result.scalars().all()}
    assert primary_by_platform == {"slack": True, "web": False}


def test_other_is_not_a_role(client):
    """`other` was a sixth value behaviourally identical to an unset role
    (it matched no seeded topic, so `/topics` special-cased it back to
    "show everything"). Removed: "no specialist role" has one spelling."""
    r = client.post(
        "/admin/roster/import",
        headers=AUTH,
        json={"persons": [{"email": "ada@example.com", "display_name": "Ada Lovelace", "role": "other"}]},
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "validation_error"
