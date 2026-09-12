"""Roster import (spec §Identity, roles, teams → Roster seeding): upsert
persons by email, link the manager tree by manager email, create a `slack`
identity when a Slack user ID is supplied, and create a `web` identity for
every person from their normalized email unconditionally (spec: "the `web`
identity is created by the roster importer at import time... not on first
login").

Three passes over the batch: the first upserts every person by email so a
manager listed after their reports still resolves; the second links
`manager_id` once every person in the batch has an id; the third creates
platform identities (`slack` conditionally, `web` unconditionally).

Also covers subtree resolution (spec §Identity, roles, teams → Rules,
"Subtree"): a recursive CTE over `manager_id`, meant to be cached per
request by the caller (e.g. a FastAPI dependency with `request.state`).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.identity.models import Identity, Person
from learning_service.roster.schemas import ROLES, RosterImportPerson

# `plugins/hermes-kata` sits next to `learning_service` in this same
# monorepo checkout (KATA-4, carried from KATA-11's human gate) — not a
# declared dependency of this package (its own `pyproject.toml` has none on
# `hermes-kata`, and never will: the two ship as separate deployables, see
# `hermes_kata.commands._real_create_job_fn`'s own "only works inside a real
# Hermes install" note). Reached by path, best-effort, only for the one pure
# function below that needs no live Hermes.
_HERMES_KATA_PLUGIN_SRC = Path(__file__).resolve().parents[2] / "plugins" / "hermes-kata"


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

    # Every imported person gets a `(platform: web, external_id: <normalized
    # email>)` identity, so web sign-in only ever calls
    # `POST /identities/resolve` — it never writes identity state itself.
    # Unconditional, unlike the slack pass above, since every roster entry
    # already requires `email`.
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
        # imported with a `slack_user_id` got a primary slack identity in
        # the pass above, and two primary identities for one person means
        # nothing.
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


def write_kata_roster_json(persons: list[Person], request_persons: list[RosterImportPerson]) -> str | None:
    """After every successful `POST /admin/roster/import`, refresh the file
    `KATA_ROSTER_JSON` points at with this roster's `{id, slack_user_id}`
    pairs — the shape `hermes_kata.commands.load_roster` reads (its own
    docstring: "the same `{id, slack_user_id}` shape a caller builds by
    matching `POST /admin/roster/import`'s request persons against its
    response persons by email"). Vendored `hermes_kata/roster.json` stays
    empty on purpose (it must never fabricate a recipient) — this is the
    roster source `KATA_ROSTER_JSON` exists to point at instead (G1's
    human-gate carry-over, KATA-11 -> KATA-4). `None`, not an empty file,
    when the variable isn't set — this process never guesses a path.
    """
    target = os.environ.get("KATA_ROSTER_JSON")
    if not target:
        return None
    by_email = {p.email: p for p in persons}
    payload = {
        "persons": [
            {"id": by_email[entry.email].id, "slack_user_id": entry.slack_user_id}
            for entry in request_persons
            if entry.slack_user_id and entry.email in by_email
        ]
    }
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(path)


def plan_digest_jobs_count(persons: list[Person], request_persons: list[RosterImportPerson]) -> int | None:
    """Best-effort `sync_digest_jobs` count for the import response:
    `hermes_kata.digests.plan_digest_jobs` is pure (no live Hermes/
    `cron.jobs` needed, unlike `create_digest_jobs`/`sync_digest_jobs`
    itself), so it can run inside this process and report a real number —
    proof G1's twelve-job done check (ten due-rep, one team-quiz, one
    teach-back) will hold once a live Hermes turn actually calls
    `sync_digest_jobs`, without this process pretending to be Hermes or
    creating a single cron job itself.

    `None`, never a fabricated number, when the plugin isn't reachable
    (an image that doesn't vendor `plugins/`) or `KATA_TEAM_CHANNEL` isn't
    configured — the team-quiz/teach-back jobs need a channel to deliver to.
    """
    team_channel = os.environ.get("KATA_TEAM_CHANNEL")
    if not team_channel:
        return None
    try:
        if _HERMES_KATA_PLUGIN_SRC.is_dir() and str(_HERMES_KATA_PLUGIN_SRC) not in sys.path:
            sys.path.insert(0, str(_HERMES_KATA_PLUGIN_SRC))
        from hermes_kata.digests import plan_digest_jobs
    except ImportError:
        return None
    by_email = {p.email: p for p in persons}
    roster_persons = [
        {"id": by_email[entry.email].id, "slack_user_id": entry.slack_user_id}
        for entry in request_persons
        if entry.email in by_email
    ]
    return len(plan_digest_jobs(roster_persons, team_channel=team_channel))


_SUBTREE_CTE = text(
    """
    WITH RECURSIVE subtree(id) AS (
        SELECT :root_id AS id
        UNION ALL
        SELECT p.id FROM person p JOIN subtree s ON p.manager_id = s.id
    )
    SELECT id FROM subtree
    """
)


async def get_subtree_ids(session: AsyncSession, root_id: str) -> list[str]:
    """`root_id` plus all its transitive reports via `manager_id` (spec
    §Identity, roles, teams → Rules, "Subtree": "Subtree of a person = the
    person plus all transitive reports") — `root_id` itself is included. A
    recursive CTE — the caller is responsible for caching the result per
    request, per the spec's own wording.
    """
    result = await session.execute(_SUBTREE_CTE, {"root_id": root_id})
    return [row[0] for row in result.all()]


async def is_manager(session: AsyncSession, person_id: str) -> bool:
    """"Manager" is not a stored role; a person is a manager iff at least
    one person reports to them (spec §Identity, roles, teams → Rules)."""
    result = await session.execute(select(Person.id).where(Person.manager_id == person_id).limit(1))
    return result.first() is not None
