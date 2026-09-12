"""Demo seed (spec §Deployment): loads a named scenario into Postgres so a
freshly deployed service can immediately walk every route with realistic
data. `LEARNING_SEED=ferry` at startup (see `main.py`'s `_lifespan`) and
`python -m learning_service.seed ferry` from the CLI both call `seed()`
below. `ferry` is a teammate's realistic payments-team seed vendored from
another repo (`fixtures/ferry/SOURCE.md`); more scenarios can be registered
in `SCENARIOS` later the same way.

Idempotent across a restart: the scenario's `course.id` is a deterministic
uuid5 (`fixtures/ferry_scenario.py`), so a second run against the same
database finds it already there and writes nothing new.

Reviews are written straight to the `review` table (the append-only source
of truth), then `engine.replay.rebuild_derived_state` folds them into
`card_state`/`concept_state` the same way `POST /admin/replay` does — so the
seeded scenario's derived state is exactly what a live replay of this same
review log would produce.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum.models import Concept, ConceptEdge, Course, Item, Topic, TopicConcept
from learning_service.db import session_scope
from learning_service.engine.models import Review
from learning_service.engine.replay import rebuild_derived_state
from learning_service.fixtures import load_ferry_scenario
from learning_service.identity.models import Identity, Person

SCENARIOS = {"ferry": load_ferry_scenario}


def _log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} learning-seed {msg}", flush=True)


def _parse_reviewed_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _write_curriculum_and_roster(session: AsyncSession, scenario: dict) -> None:
    persons_by_id: dict[str, Person] = {}
    for p in scenario["persons"]:
        person = Person(
            id=p["id"], display_name=p["display_name"], email=p["email"], is_operator=p["is_operator"], role=p.get("role")
        )
        session.add(person)
        persons_by_id[p["id"]] = person
    await session.flush()
    for p in scenario["persons"]:
        if p["manager_id"] is not None:
            persons_by_id[p["id"]].manager_id = p["manager_id"]

    for ident in scenario["identities"]:
        session.add(
            Identity(
                id=ident["id"],
                person_id=ident["person_id"],
                platform=ident["platform"],
                external_id=ident["external_id"],
                alt_id=ident["alt_id"],
                is_primary=ident["is_primary"],
            )
        )

    course = scenario["course"]
    session.add(
        Course(id=course["id"], title=course["title"], description=course["description"], slug=course.get("slug"))
    )
    # Postgres enforces the `concept.course_id` FK at insert time (unlike the
    # SQLite test fixtures, which don't turn FK enforcement on), so the
    # course row must exist before concepts referencing it are inserted.
    await session.flush()

    for concept in scenario["concepts"]:
        session.add(
            Concept(
                id=concept["id"],
                course_id=concept["course_id"],
                slug=concept["slug"],
                title=concept["title"],
                description=concept["description"],
                mastery_threshold=concept["mastery_threshold"],
            )
        )
    # Same reasoning: edges, items and topics FK to `concept.id`.
    await session.flush()

    for edge in scenario["concept_edges"]:
        session.add(
            ConceptEdge(
                id=edge["id"],
                from_concept_id=edge["from_concept_id"],
                to_concept_id=edge["to_concept_id"],
                kind=edge["kind"],
                weight=edge["weight"],
            )
        )
    for item in scenario["items"]:
        session.add(
            Item(
                id=item["id"],
                concept_id=item["concept_id"],
                kind=item["kind"],
                prompt=item["prompt"],
                payload=item["payload"],
                status=item["status"],
            )
        )
    for topic in scenario.get("topics", []):
        session.add(
            Topic(
                id=topic["id"],
                course_id=topic["course_id"],
                slug=topic["slug"],
                title=topic["title"],
                description=topic["description"],
                persona_role=topic["persona_role"],
                entry_concept_id=topic["entry_concept_id"],
                grounded_in=topic.get("grounded_in", []),
            )
        )
        for concept_id in topic["concept_ids"]:
            session.add(TopicConcept(topic_id=topic["id"], concept_id=concept_id))
    await session.commit()


async def _write_reviews(session: AsyncSession, scenario: dict) -> None:
    """Writes `scenario["reviews"]` as `review` rows, then rebuilds
    `card_state`/`concept_state` from the whole log — the same path
    `POST /admin/replay` uses (`engine.replay.rebuild_derived_state`).

    `result` (the response body a live `POST /me/reviews` would have
    returned) is not part of the fixture — these reviews were never
    submitted through that route — so a minimal stand-in is stored instead;
    it only matters if something later replays this exact
    `(person_id, idempotency_key)`, which the seed never does.
    """
    for review in scenario["reviews"]:
        session.add(
            Review(
                id=review["id"],
                person_id=review["person_id"],
                item_id=review["item_id"],
                concept_id=review["concept_id"],
                reviewed_at=_parse_reviewed_at(review["reviewed_at"]),
                kind=review["kind"],
                grade=review["grade"],
                rating=review["rating"],
                source=review["source"],
                idempotency_key=review["idempotency_key"],
                asserted_by=review["asserted_by"],
                result={"grade": review["grade"], "rating": review["rating"], "seeded": True},
                confidence=review.get("confidence"),
                bypassed=review.get("bypassed", False),
            )
        )
    await session.commit()
    await rebuild_derived_state(session)


async def seed(session: AsyncSession, scenario_name: str = "ferry") -> bool:
    """Loads `scenario_name` into `session`. Returns True the first time it
    seeds this database, False when it already had the scenario (a restart)."""
    if scenario_name not in SCENARIOS:
        raise ValueError(f"unknown seed scenario {scenario_name!r}; choices: {sorted(SCENARIOS)}")
    scenario = SCENARIOS[scenario_name]()

    already_seeded = await session.get(Course, scenario["course"]["id"]) is not None
    if already_seeded:
        _log(f"scenario={scenario_name} already seeded, skipping")
        return False

    await _write_curriculum_and_roster(session, scenario)
    await _write_reviews(session, scenario)
    _log(
        f"scenario={scenario_name} seeded: {len(scenario['persons'])} persons, "
        f"{len(scenario['concepts'])} concepts, {len(scenario['items'])} items, "
        f"{len(scenario['reviews'])} reviews"
    )
    return True


async def _seed_from_cli(scenario_name: str) -> None:
    async with session_scope() as session:
        await seed(session, scenario_name)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    scenario_name = argv[0] if argv else ""
    if scenario_name not in SCENARIOS:
        _log(f"usage: python -m learning_service.seed <{'|'.join(SCENARIOS)}>")
        return 2
    if not os.environ.get("DATABASE_URL"):
        _log("DATABASE_URL not set, nothing to seed")
        return 0
    asyncio.run(_seed_from_cli(scenario_name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
