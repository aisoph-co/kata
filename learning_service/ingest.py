"""`POST /admin/ingest` (KATA-13/CI1): the "Connect team context" trigger.

Reads the seeded `1-context/issues.jsonl` and `seed_data/{concepts,items}
.json` (`learning_service.ingestion`) and writes the resulting course/
concept/edge/topic/item graph through the *existing*, frozen v1.2.1
`/admin/courses` -> `/admin/concepts` -> `/admin/edges` -> `/admin/topics`
-> `/admin/items` routes — this module adds no new way to write curriculum
data, it only calls the ones that already exist, over an in-process ASGI
transport, forwarding this request's own operator identity and service
token to each nested call.

Streams one newline-delimited JSON object per row as it's written (`type`:
`concept` | `edge` | `topic` | `item` | `empty` | `done`), so the
Connections screen (KATA-7/W3) shows rows arriving rather than waiting on
the whole run — SCREENS.md #02's "first concept visible within 5 seconds".
An empty `issues.jsonl` writes nothing and streams one `empty` event (frame
02's other required state: "no issues found," zero concepts, no spinner).

Re-triggering — including against a core that `LEARNING_SEED=ferry` already
seeded at boot (`learning_service/seed.py`, same `seed_data/*.json`) — is a
no-op-and-continue, not a duplicate or a crash: the course is matched by
title (the boot loader never sets a slug) before any write is attempted,
and a concept/topic/item collision comes back from the nested call as the
same 422 `curriculum_service` already raises for a fresh write.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from learning_service.ingestion import (
    ConceptDraft,
    EdgeDraft,
    ItemDraft,
    TopicDraft,
    build_topics,
    extract_concepts,
    extract_edges,
    extract_items,
    load_concepts_doc,
    load_issues,
    load_items_doc,
    seed_context_dir,
)
from learning_service.main import app, require_operator

router = APIRouter()


def _event(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload) + "\n").encode("utf-8")


async def _create(client: httpx.AsyncClient, path: str, body: dict[str, Any]) -> dict[str, Any] | None:
    """POSTs to an existing frozen `/admin/*` route. `None` on a 422 —
    already-exists is the one validation failure this route treats as
    "reuse what's there"; every other 422 propagates via `raise_for_status`."""
    response = await client.post(path, json=body)
    if response.status_code == 422:
        return None
    response.raise_for_status()
    return response.json()


async def _find(client: httpx.AsyncClient, path: str, key: str, params: dict[str, Any], matches) -> dict[str, Any] | None:
    response = await client.get(path, params=params)
    response.raise_for_status()
    return next((row for row in response.json().get(key, []) if matches(row)), None)


async def _get_or_create_course(client: httpx.AsyncClient, *, title: str, slug: str, description: str) -> dict[str, Any]:
    # Checked *before* creating, not create-then-422-fallback: `POST
    # /admin/courses` only rejects a duplicate `slug`, never a duplicate
    # title, and `learning_service/seed.py`'s own boot loader creates this
    # exact course with no slug at all — a create-first attempt would pass
    # its own uniqueness check and silently duplicate the course.
    existing = await _find(client, "/admin/courses", "courses", {}, lambda c: c["slug"] == slug or c["title"] == title)
    if existing is not None:
        return existing
    created = await _create(client, "/admin/courses", {"title": title, "slug": slug, "description": description})
    if created is None:
        raise RuntimeError(f"course {title!r} could not be created or found")
    return created


async def _get_or_create_concept(client: httpx.AsyncClient, course_id: str, draft: ConceptDraft) -> dict[str, Any]:
    created = await _create(
        client,
        "/admin/concepts",
        {
            "course_id": course_id,
            "slug": draft.slug,
            "title": draft.title,
            "description": draft.description,
            "mastery_threshold": draft.mastery_threshold,
        },
    )
    if created is not None:
        return created
    existing = await _find(client, "/admin/concepts", "concepts", {"course_id": course_id}, lambda c: c["slug"] == draft.slug)
    if existing is None:
        raise RuntimeError(f"concept {draft.slug!r} could not be created or found")
    return existing


async def _create_edge_if_new(
    client: httpx.AsyncClient, concept_ids: dict[str, str], draft: EdgeDraft
) -> dict[str, Any] | None:
    return await _create(
        client,
        "/admin/edges",
        {
            "from_concept_id": concept_ids[draft.from_slug],
            "to_concept_id": concept_ids[draft.to_slug],
            "kind": draft.kind,
            "weight": draft.weight,
        },
    )


async def _get_or_create_topic(
    client: httpx.AsyncClient, course_id: str, concept_ids: dict[str, str], draft: TopicDraft
) -> dict[str, Any] | None:
    created = await _create(
        client,
        "/admin/topics",
        {
            "course_id": course_id,
            "slug": draft.slug,
            "title": draft.title,
            "description": draft.description,
            "persona_role": draft.persona_role,
            "entry_concept_id": concept_ids[draft.entry_slug],
            "concept_ids": [concept_ids[s] for s in draft.concept_slugs],
            "grounded_in": list(draft.grounded_in),
        },
    )
    if created is not None:
        return created
    # No `GET /admin/topics` exists to reuse this the way courses/concepts
    # do — `GET /topics?all_roles=true` (the same read the Connections
    # screen itself uses) is the one place every topic is listable.
    return await _find(client, "/topics", "topics", {"all_roles": "true"}, lambda t: t["slug"] == draft.slug)


async def _create_item_if_new(client: httpx.AsyncClient, concept_id: str, draft: ItemDraft) -> dict[str, Any] | None:
    # Matched by prompt, not "this concept already has an item": a concept
    # legitimately carries several items (`seed_data/items.json`), so
    # existence-of-any would silently drop every item after the first.
    existing = await client.get("/admin/items", params={"concept_id": concept_id})
    existing.raise_for_status()
    if any(row["prompt"] == draft.prompt for row in existing.json().get("items", [])):
        return None
    return await _create(
        client,
        "/admin/items",
        {"concept_id": concept_id, "kind": draft.kind, "prompt": draft.prompt, "payload": draft.payload, "status": draft.status},
    )


async def _run(headers: dict[str, str]) -> AsyncIterator[bytes]:
    issues = load_issues(seed_context_dir())
    if not issues:
        yield _event({"type": "empty", "message": "no issues found"})
        return

    concepts_doc = load_concepts_doc()
    concepts = extract_concepts(issues, concepts_doc)
    edges = extract_edges(concepts_doc)
    items = extract_items(load_items_doc(), concepts)
    topics = build_topics(concepts)
    counts = {"concepts": 0, "edges": 0, "topics": 0, "items_published": 0, "items_draft": 0}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://ingest.internal", headers=headers) as client:
        course = await _get_or_create_course(
            client,
            title=concepts_doc["course"]["title"],
            slug=concepts_doc["course"]["slug"],
            description=concepts_doc["course"]["description"],
        )

        concept_ids: dict[str, str] = {}
        for draft in concepts:
            concept = await _get_or_create_concept(client, course["id"], draft)
            concept_ids[draft.slug] = concept["id"]
            counts["concepts"] += 1
            yield _event({"type": "concept", "concept": concept})

        for draft in edges:
            edge = await _create_edge_if_new(client, concept_ids, draft)
            if edge is not None:
                counts["edges"] += 1
                yield _event({"type": "edge", "edge": edge})

        for draft in topics:
            topic = await _get_or_create_topic(client, course["id"], concept_ids, draft)
            if topic is not None:
                counts["topics"] += 1
                yield _event({"type": "topic", "topic": topic})

        for draft in items:
            item = await _create_item_if_new(client, concept_ids[draft.concept_slug], draft)
            if item is not None:
                counts["items_published" if item["status"] == "published" else "items_draft"] += 1
                yield _event({"type": "item", "item": item})

    yield _event({"type": "done", "counts": counts})


@router.post("/admin/ingest")
async def admin_ingest(request: Request, _: None = Depends(require_operator)) -> StreamingResponse:
    # Forwards this request's own already-validated credentials to every
    # nested `/admin/*` call below — no separate service-to-service secret
    # to manage, and every nested write is checked by the same
    # `require_operator` the top-level request just passed.
    headers = {
        "authorization": request.headers.get("authorization", ""),
        "x-acting-identity": request.headers.get("x-acting-identity", ""),
    }
    return StreamingResponse(_run(headers), media_type="application/x-ndjson")
