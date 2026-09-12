"""Builds the `ferry` seed scenario from the vendored snapshot in
`learning_service/fixtures/ferry/` (see that directory's `SOURCE.md` for
provenance). Ferry's realistic payments-team roster, curriculum and 60-day
review history, copied verbatim from the hackathon repo's `docs/seed/` and
reshaped here into the dict shape `learning_service.seed` writes straight to
Postgres (`persons`, `identities`, `course`, `concepts`, `concept_edges`,
`items`, `topics`, `reviews`).

Every id is a uuid5 of a stable name (person email, concept/item slug, review
idempotency key), all under one namespace, so re-running this builder — and
therefore re-seeding against the same database — always produces the same
rows.
"""

from __future__ import annotations

import json
import uuid
from importlib import resources
from typing import Any

NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, "https://github.com/aisoph-co/agents-everywhere-hackathon/learning/ferry-seed"
)

# One day before the first simulated review (2026-07-14T09:02:13Z) — used as
# the identity "linked_at" timestamp; nothing in the acceptance criteria
# depends on its exact value.
_EPOCH = "2026-07-14T00:00:00Z"


def _id(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, ":".join(parts)))


def _read_json(filename: str) -> Any:
    data = resources.files("learning_service.fixtures").joinpath("ferry").joinpath(filename).read_text(
        encoding="utf-8"
    )
    return json.loads(data)


def _read_jsonl(filename: str) -> list[dict]:
    data = resources.files("learning_service.fixtures").joinpath("ferry").joinpath(filename).read_text(
        encoding="utf-8"
    )
    return [json.loads(line) for line in data.splitlines() if line.strip()]


def _build_persons_and_identities() -> tuple[list[dict], list[dict], dict[str, str]]:
    roster = _read_json("roster.json")["persons"]
    person_id_by_email = {p["email"]: _id("person", p["email"]) for p in roster}

    persons = []
    identities = []
    for p in roster:
        seed_bag = p["_seed"]
        persons.append(
            {
                "id": person_id_by_email[p["email"]],
                "display_name": p["display_name"],
                "email": p["email"],
                "is_operator": seed_bag["is_operator"],
                "role": seed_bag["role"],
                "manager_id": person_id_by_email.get(p["manager_email"]) if p["manager_email"] else None,
            }
        )
        # The roster's own slack_user_id, plus every identity `_seed`
        # declares (whatsapp/signal/web) — the slack id is treated as
        # primary since it's the one channel every person has.
        identities.append(
            {
                "id": _id("identity", "slack", p["slack_user_id"]),
                "person_id": person_id_by_email[p["email"]],
                "platform": "slack",
                "external_id": p["slack_user_id"],
                "alt_id": None,
                "is_primary": True,
                "linked_at": _EPOCH,
            }
        )
        for extra in seed_bag["identities"]:
            identities.append(
                {
                    "id": _id("identity", extra["platform"], extra["external_id"]),
                    "person_id": person_id_by_email[p["email"]],
                    "platform": extra["platform"],
                    "external_id": extra["external_id"],
                    "alt_id": None,
                    "is_primary": False,
                    "linked_at": _EPOCH,
                }
            )
    return persons, identities, person_id_by_email


def _build_curriculum() -> tuple[dict, list[dict], list[dict], dict[str, str]]:
    raw = _read_json("concepts.json")
    course_slug = raw["course"]["slug"]
    course_id = _id("course", course_slug)
    course = {
        "id": course_id,
        "title": raw["course"]["title"],
        "description": raw["course"]["description"],
        "slug": course_slug,
    }

    concept_id_by_slug = {c["slug"]: _id("concept", c["slug"]) for c in raw["concepts"]}
    concepts = [
        {
            "id": concept_id_by_slug[c["slug"]],
            "course_id": course_id,
            "slug": c["slug"],
            "title": c["title"],
            "description": c["description"],
            "mastery_threshold": c["mastery_threshold"],
        }
        for c in raw["concepts"]
    ]

    concept_edges = [
        {
            "id": _id("edge", "prerequisite", e["from"], e["to"]),
            "from_concept_id": concept_id_by_slug[e["from"]],
            "to_concept_id": concept_id_by_slug[e["to"]],
            "kind": "prerequisite",
            "weight": 1.0,
        }
        for e in raw["prerequisite_edges"]
    ]
    concept_edges += [
        {
            "id": _id("edge", "related", e["a"], e["b"]),
            "from_concept_id": concept_id_by_slug[e["a"]],
            "to_concept_id": concept_id_by_slug[e["b"]],
            "kind": "related",
            "weight": e["weight"],
        }
        for e in raw["related_edges"]
    ]
    return course, concepts, concept_edges, concept_id_by_slug


def _build_items(concept_id_by_slug: dict[str, str]) -> tuple[list[dict], dict[str, str]]:
    raw = _read_json("items.json")
    item_id_by_slug = {it["slug"]: _id("item", it["slug"]) for it in raw}
    items = [
        {
            "id": item_id_by_slug[it["slug"]],
            "concept_id": concept_id_by_slug[it["concept"]],
            "kind": it["kind"],
            "prompt": it["prompt"],
            "payload": it["payload"],
            "status": "published",
        }
        for it in raw
    ]
    return items, item_id_by_slug


def _build_topics(course_id: str, concept_id_by_slug: dict[str, str]) -> list[dict]:
    raw = _read_json("topics.json")["topics"]
    topics = []
    for t in raw:
        roles = t.get("personas") or [t["persona"]]
        for index, role in enumerate(roles):
            slug = t["slug"] if index == 0 else f"{t['slug']}-{role}"
            topics.append(
                {
                    "id": _id("topic", slug),
                    "course_id": course_id,
                    "slug": slug,
                    "title": t["title"],
                    "description": t.get("why_this_role_this_week", ""),
                    "persona_role": role,
                    "entry_concept_id": concept_id_by_slug[t["entry_concept"]],
                    "concept_ids": [concept_id_by_slug[s] for s in t["concepts"]],
                    "grounded_in": list(t["grounded_in"]),
                }
            )
    return topics


def _build_reviews(
    person_id_by_email: dict[str, str], item_id_by_slug: dict[str, str], concept_id_by_item_id: dict[str, str]
) -> list[dict]:
    raw = _read_jsonl("reviews.jsonl")
    reviews = []
    for r in raw:
        item_id = item_id_by_slug[r["item_slug"]]
        reviews.append(
            {
                "id": _id("review", r["idempotency_key"]),
                "person_id": person_id_by_email[r["person_email"]],
                "item_id": item_id,
                "concept_id": concept_id_by_item_id[item_id],
                "reviewed_at": r["reviewed_at"],
                "kind": r["kind"],
                "grade": r["grade"],
                "rating": r["rating"],
                "source": r["source"],
                "idempotency_key": r["idempotency_key"],
                "asserted_by": r["asserted_by"],
                "confidence": r["confidence"],
                "bypassed": r["bypassed"],
            }
        )
    return reviews


def build_ferry_scenario() -> dict:
    persons, identities, person_id_by_email = _build_persons_and_identities()
    course, concepts, concept_edges, concept_id_by_slug = _build_curriculum()
    items, item_id_by_slug = _build_items(concept_id_by_slug)
    concept_id_by_item_id = {item["id"]: item["concept_id"] for item in items}
    reviews = _build_reviews(person_id_by_email, item_id_by_slug, concept_id_by_item_id)
    topics = _build_topics(course["id"], concept_id_by_slug)

    return {
        "meta": {"name": "ferry_scenario", "source": "learning_service/fixtures/ferry/SOURCE.md"},
        "course": course,
        "concepts": concepts,
        "concept_edges": concept_edges,
        "items": items,
        "persons": persons,
        "identities": identities,
        "reviews": reviews,
        "topics": topics,
    }
