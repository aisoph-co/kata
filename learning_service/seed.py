"""`python -m learning_service.seed ferry` / `LEARNING_SEED=ferry` on start
(spec §Deployment; KATA-4 R6): loads the Ferry golden scenario — the ten-
person roster, the `ferry-payments-core` curriculum, and ninety days of
review history — directly into this service's own database.

Vendored from `agents-everywhere-hackathon/docs/seed/` (`0-team/roster.json`,
`2-curriculum/{concepts,items}.json`, `3-history/reviews.jsonl`) into
`seed_data/` alongside this module: the deployed image only ever contains
this repo, so the seed has to travel with it rather than reach across to the
planning repo at runtime.

Two things this loader does that `docs/seed/load_seed.py` (the HTTP-only,
contract-checking loader) cannot:

1.  It writes `review` rows directly through this process's own DB session,
    with each row's real historical `reviewed_at` — `POST /me/reviews` takes
    no such field (`docs/seed/OPEN-QUESTIONS.md` Q3), so a live HTTP replay
    would stamp every rep "now" and the dashboard would open flat. Writing
    the rows directly and then running the exact same rebuild `POST
    /admin/replay` uses (`engine.replay.rebuild_derived_state`) keeps
    `card_state`/`concept_state` identical to what a live history would have
    produced, without a second implementation to keep in sync.
2.  It is idempotent: re-running it (a container restart with `LEARNING_SEED
    =ferry` still set, or a second manual invocation) is a no-op once the
    scenario's first review is already on record, checked by that review's
    own deterministic `idempotency_key` — never by counting rows, which
    would drift the moment anyone reviews live against the seeded roster.

Roster import here reuses `roster.service.import_roster` directly (not
`POST /admin/roster/import`) so a container that only ever runs this module
never needs its own HTTP round trip to itself. The one piece a live import
*does* still need doing after every run — HERMES_KATA's digest-job wiring
(`roster/router.py`'s own docstring) — is out of scope for this module: the
seed's roster snapshot for `KATA_ROSTER_JSON` is written the same way a live
`POST /admin/roster/import` writes it, by `roster.router`, not duplicated
here.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum.models import Course
from learning_service.db import session_scope
from learning_service.engine.replay import rebuild_derived_state
from learning_service.engine.sql_models import ReviewRow
from learning_service.engine.sql_repository import SqlLearningRepository
from learning_service.roster.schemas import RosterImportPerson
from learning_service.roster.service import import_roster

SEED_DATA = Path(__file__).parent / "seed_data"
SCENARIOS = ("ferry",)

# The four fields RosterImportPerson has always taken.
_ROSTER_KEYS = ("email", "display_name", "manager_email", "slack_user_id", "is_operator", "role")


def _log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} learning-seed {msg}", flush=True)


def _load_json(name: str) -> Any:
    return json.loads((SEED_DATA / name).read_text(encoding="utf-8"))


def _roster_persons() -> list[RosterImportPerson]:
    roster = _load_json("roster.json")
    out = []
    for p in roster["persons"]:
        seed = p.get("_seed", {})
        fields = {k: p[k] for k in ("email", "display_name", "manager_email", "slack_user_id") if k in p}
        fields["is_operator"] = seed.get("is_operator")
        fields["role"] = seed.get("role")
        out.append(RosterImportPerson(**fields))
    return out


async def _already_seeded(session: AsyncSession) -> bool:
    """The scenario's own marker: the first review's `idempotency_key` is
    deterministic (`generate_reviews.py`'s own `uuid5`), so its presence on
    record means this whole scenario already loaded — checked before
    touching curriculum or history, never by counting rows."""
    reviews = _reviews()
    if not reviews:
        return False
    marker = reviews[0]["idempotency_key"]
    existing = await session.execute(select(ReviewRow.id).where(ReviewRow.idempotency_key == marker).limit(1))
    return existing.first() is not None


def _reviews() -> list[dict[str, Any]]:
    path = SEED_DATA / "reviews.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


async def _load_curriculum(session: AsyncSession) -> tuple[str, dict[str, str]]:
    concepts_doc = _load_json("concepts.json")
    course = await curriculum_service.create_course(
        session, title=concepts_doc["course"]["title"], description=concepts_doc["course"]["description"]
    )
    concept_id: dict[str, str] = {}
    for c in concepts_doc["concepts"]:
        concept = await curriculum_service.create_concept(
            session,
            course_id=course.id,
            slug=c["slug"],
            title=c["title"],
            description=c["description"],
            mastery_threshold=c["mastery_threshold"],
        )
        concept_id[c["slug"]] = concept.id

    for e in concepts_doc["prerequisite_edges"]:
        await curriculum_service.create_edge(
            session,
            from_concept_id=concept_id[e["from"]],
            to_concept_id=concept_id[e["to"]],
            kind="prerequisite",
            weight=e.get("weight", 1.0),
        )
    for e in concepts_doc["related_edges"]:
        await curriculum_service.create_edge(
            session,
            from_concept_id=concept_id[e["a"]],
            to_concept_id=concept_id[e["b"]],
            kind="related",
            weight=e.get("weight", 1.0),
        )
    return course.id, concept_id


async def _load_items(session: AsyncSession, concept_id: dict[str, str]) -> dict[str, str]:
    item_id: dict[str, str] = {}
    for it in _load_json("items.json"):
        item = await curriculum_service.create_item(
            session,
            concept_id=concept_id[it["concept"]],
            kind=it["kind"],
            prompt=it["prompt"],
            payload=it["payload"],
            # Explicit `published`: a `draft` item is never scheduled
            # (`docs/seed/load_seed.py`'s own comment) and the whole seed
            # would load and then serve nothing.
            status="published",
        )
        item_id[it["slug"]] = item.id
    return item_id


async def _load_reviews(session: AsyncSession, persons_by_email: dict[str, str], item_id: dict[str, str]) -> int:
    count = 0
    for r in _reviews():
        person_id = persons_by_email.get(r["person_email"])
        target_item_id = item_id.get(r["item_slug"])
        if person_id is None or target_item_id is None:
            # Never fabricate a link a golden file doesn't actually resolve.
            _log(f"skipping review {r['idempotency_key']}: unresolved person/item")
            continue
        session.add(
            ReviewRow(
                id=str(uuid.uuid4()),
                person_id=person_id,
                item_id=target_item_id,
                reviewed_at=datetime.fromisoformat(r["reviewed_at"].replace("Z", "+00:00")),
                kind=r["kind"],
                grade=r["grade"],
                rating=r["rating"],
                source=r["source"],
                idempotency_key=r["idempotency_key"],
                asserted_by=r["asserted_by"],
                result={"grade": r["grade"], "rating": r["rating"], "seed": "ferry"},
                confidence=r.get("confidence"),
                bypassed=r.get("bypassed", False),
            )
        )
        count += 1
    await session.commit()
    return count


def _write_kata_roster_json(persons_by_email: dict[str, str], roster_source: list[dict[str, Any]]) -> str | None:
    """Same shape `roster/router.py` writes after a live `POST /admin/roster/
    import`: `{persons: [{id, slack_user_id}, ...]}`, the shape `hermes_kata.
    commands.load_roster` reads (`hermes_kata/commands.py`'s own docstring)."""
    target = os.environ.get("KATA_ROSTER_JSON")
    if not target:
        return None
    payload = {
        "persons": [
            {"id": persons_by_email[p["email"]], "slack_user_id": p["slack_user_id"]}
            for p in roster_source
            if p.get("slack_user_id") and p["email"] in persons_by_email
        ]
    }
    out_path = Path(target)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(out_path)


async def seed_ferry() -> dict[str, Any]:
    async with session_scope() as session:
        if await _already_seeded(session):
            _log("ferry: already loaded, skipping (idempotent)")
            return {"status": "already_loaded"}

        roster_source = _load_json("roster.json")["persons"]
        persons, created, updated = await import_roster(session, persons=_roster_persons())
        persons_by_email = {p.email: p.id for p in persons}

        # A fresh course/concepts/items load only ever happens the same run
        # the marker check above found nothing — a second run stops at
        # `_already_seeded` before reaching here, so this never duplicates
        # the curriculum on a restart.
        existing_course = await session.execute(select(Course.id).limit(1))
        if existing_course.first() is not None:
            _log("ferry: a course already exists; skipping curriculum+review load, roster only")
            return {"status": "roster_only", "persons_created": created, "persons_updated": updated}

        _course_id, concept_id = await _load_curriculum(session)
        item_id = await _load_items(session, concept_id)
        review_count = await _load_reviews(session, persons_by_email, item_id)

        repo = SqlLearningRepository(session)
        await repo.load()
        counts = rebuild_derived_state(repo)
        await repo.persist_derived_state()

        roster_json_path = _write_kata_roster_json(persons_by_email, roster_source)

        result = {
            "status": "loaded",
            "persons_created": created,
            "persons_updated": updated,
            "concepts": len(concept_id),
            "items": len(item_id),
            "reviews_loaded": review_count,
            **counts,
            "kata_roster_json": roster_json_path,
        }
        _log(f"ferry: {result}")
        return result


async def _run(scenario: str) -> int:
    if scenario not in SCENARIOS:
        _log(f"usage: python -m learning_service.seed <{'|'.join(SCENARIOS)}>")
        return 2
    if not os.environ.get("DATABASE_URL"):
        _log(f"{scenario}: DATABASE_URL not set, nothing to seed")
        return 0
    try:
        await seed_ferry()
    except Exception as exc:  # noqa: BLE001 — a failed seed must fail the run, not go silent
        _log(f"{scenario}: failed: {exc}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    scenario = argv[0] if argv else os.environ.get("LEARNING_SEED", "")
    if not scenario:
        _log(f"usage: python -m learning_service.seed <{'|'.join(SCENARIOS)}>")
        return 2
    return asyncio.run(_run(scenario))


if __name__ == "__main__":
    raise SystemExit(main())
