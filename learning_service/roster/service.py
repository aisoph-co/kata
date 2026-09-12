"""Roster import (US-A3, AGCTM-35, spec §Identity, roles, teams → Roster
seeding): upsert persons by email, link the manager tree by manager email,
create a `slack` identity when a Slack user ID is supplied, and create a
`web` identity for every person from their normalized email (web-app-design.md
Contract change #6).

Three passes over the batch: the first upserts every person by email so a
manager listed after their reports still resolves; the second links
`manager_id` once every person in the batch has an id; the third creates
platform identities (`slack` conditionally, `web` unconditionally).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.identity.models import Identity, Person
from learning_service.roster.schemas import ROLES, RosterImportPerson


class UnknownManager(Exception):
    """`manager_email` matches no person in this import or the existing roster."""


class SlackIdentityConflict(Exception):
    """`slack_user_id` is already linked to a different person."""


class InvalidRole(Exception):
    """`role` is not one of the recognized role values."""


class WebIdentityConflict(Exception):
    """The normalized email is already linked to a different person."""


async def import_roster(
    session: AsyncSession, *, persons: list[RosterImportPerson]
) -> tuple[list[Person], int, int]:
    created = 0
    updated = 0
    by_email: dict[str, Person] = {}

    for entry in persons:
        if entry.role is not None and entry.role not in ROLES:
            raise InvalidRole(entry.role)

        result = await session.execute(select(Person).where(Person.email == entry.email))
        person = result.scalar_one_or_none()
        if person is None:
            person = Person(
                email=entry.email,
                display_name=entry.display_name,
                is_operator=entry.is_operator or False,
                role=entry.role,
            )
            session.add(person)
            created += 1
        else:
            person.display_name = entry.display_name
            if entry.is_operator is not None:
                person.is_operator = entry.is_operator
            if entry.role is not None:
                person.role = entry.role
            updated += 1
        by_email[entry.email] = person

    await session.flush()

    for entry in persons:
        if entry.manager_email is None:
            continue
        manager = by_email.get(entry.manager_email)
        if manager is None:
            result = await session.execute(select(Person).where(Person.email == entry.manager_email))
            manager = result.scalar_one_or_none()
        if manager is None:
            raise UnknownManager(entry.manager_email)
        by_email[entry.email].manager_id = manager.id

    for entry in persons:
        if entry.slack_user_id is None:
            continue
        person = by_email[entry.email]
        existing = await session.execute(
            select(Identity).where(Identity.platform == "slack", Identity.external_id == entry.slack_user_id)
        )
        identity = existing.scalar_one_or_none()
        if identity is None:
            session.add(
                Identity(person_id=person.id, platform="slack", external_id=entry.slack_user_id, is_primary=True)
            )
        elif identity.person_id != person.id:
            raise SlackIdentityConflict(entry.slack_user_id)

    # Contract change #6: every imported person gets a `(platform: web,
    # external_id: <normalized email>)` identity, so web sign-in only ever
    # calls `POST /identities/resolve` — it never writes identity state
    # itself. Unconditional, unlike the slack pass above, since every roster
    # entry already requires `email`.
    await session.flush()

    for entry in persons:
        person = by_email[entry.email]
        normalized_email = entry.email.strip().lower()
        existing = await session.execute(
            select(Identity).where(Identity.platform == "web", Identity.external_id == normalized_email)
        )
        identity = existing.scalar_one_or_none()
        if identity is not None:
            if identity.person_id != person.id:
                raise WebIdentityConflict(normalized_email)
            continue
        # `is_primary` only when nothing else already claims it: a person
        # imported with a `slack_user_id` got a primary slack identity in the
        # pass above, and two primary identities for one person means nothing.
        claimed = await session.execute(select(Identity).where(Identity.person_id == person.id))
        session.add(
            Identity(
                person_id=person.id,
                platform="web",
                external_id=normalized_email,
                is_primary=claimed.scalars().first() is None,
            )
        )

    await session.commit()
    ordered = [by_email[entry.email] for entry in persons]
    return ordered, created, updated


async def get_subtree_ids(session: AsyncSession, root_id: str) -> list[str]:
    """All persons transitively reporting up to `root_id` via `manager_id`
    (spec §Team analytics: "operate only on persons in that subtree"),
    excluding `root_id` itself. A whole-roster scan plus an in-memory BFS —
    the roster is small (tens of persons), so this is simpler and more
    portable across SQLite/Postgres than a recursive CTE.
    """
    result = await session.execute(select(Person.id, Person.manager_id))
    children_of: dict[str, list[str]] = {}
    for person_id, manager_id in result.all():
        if manager_id is not None:
            children_of.setdefault(manager_id, []).append(person_id)

    subtree: list[str] = []
    seen: set[str] = set()
    queue = list(children_of.get(root_id, []))
    while queue:
        person_id = queue.pop(0)
        if person_id in seen:
            continue
        seen.add(person_id)
        subtree.append(person_id)
        queue.extend(children_of.get(person_id, []))
    return subtree
