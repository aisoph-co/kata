"""CI1 (`build-day/issues.md` "CI1", KATA-13) — ingestion trigger, streaming
wire-up, and LLM concept/item extraction. Wires the "Connect team context"
action to a real ingestion job: it walks the seeded `1-context/` grounding
material and creates a course, streaming each concept to the caller as it
is produced by calling the same course/concept/edge/topic writes `POST
/admin/courses` -> `/admin/concepts` -> `/admin/edges` -> `/admin/topics`
perform (`curriculum.service`, not a self-HTTP round trip — same
validation, same rows). A real `topic` row, not a slug-prefix workaround.

`extract_concept_drafts` is citation-accurate: one concept per distinct
`concepts` slug already tagged on a seeded issue, citing every issue key
that raised it. `extract_related_pairs` finds every pair of concepts that
co-occur on the same issue; each pair is then classified by an
`ExtractionClient` (`extraction/client.py`, real or `extraction/stub.py` in
tests) as either `prerequisite` or `related` — `curriculum_service.
create_edge` already validates prerequisite edges acyclic per course, so a
classification that would close a cycle is downgraded to `related` instead
of dropped, keeping the graph a validated-acyclic DAG. Citations are
enriched with the second and third seeded sources
(`extraction.sources.load_release_notes_source` — release notes, and the
repo-identifier tokens named inside them) and a fourth, best-effort one
(`extraction.exa.ExaClient`). One citation-grounded multiple-choice item is
drafted per concept and written `status="draft"` — ingestion never calls
`POST /admin/items/{id}/publish` itself, so every item it writes waits for
a human review gate. A concept with no traceable citation gets no item at
all, so there is nothing for it to ever publish.

Streamed as Server-Sent Events on a single request/response (one DB session
for the whole run, no detached background task and no second session to
manage): `event: concept` per concept as it's written, `event: empty` when
the source has nothing to ingest, `event: done` on success, `event: error`
on failure.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.db import get_session
from learning_service.extraction.client import ExtractionClient
from learning_service.extraction.exa import ExaClient
from learning_service.extraction.sources import (
    augment_citations,
    load_context_issues,
    load_release_notes_source,
)
from learning_service.main import get_extraction_client, require_operator

router = APIRouter()

# Small stagger between concepts so the client visibly receives them one at
# a time instead of all at once — well under the 5-second "first concept
# visible" done check even with every concept in `issues.jsonl`.
STREAM_DELAY_SECONDS = 0.2

# Only "tech_lead" is seeded `is_operator: true` in the Ferry roster
# (`docs/seed/0-team/roster.json`), so the topic this job creates is
# attributed to that role — the same role the operator triggering
# `/admin/ingest` has.
INGESTED_TOPIC_PERSONA_ROLE = "tech_lead"


def _humanize(slug: str) -> str:
    return slug.replace("-", " ").replace("_", " ").capitalize()


def extract_concept_drafts(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One draft per distinct concept slug tagged across `issues`, in
    first-seen order (deterministic run-to-run), each citing the issue keys
    that raised it."""
    drafts: dict[str, dict[str, Any]] = {}
    for issue in issues:
        key = issue.get("key")
        for slug in issue.get("concepts", []):
            draft = drafts.setdefault(
                slug,
                {"slug": slug, "title": _humanize(slug), "grounded_in": []},
            )
            if key and key not in draft["grounded_in"]:
                draft["grounded_in"].append(key)
    for draft in drafts.values():
        draft["description"] = f"Raised in {', '.join(draft['grounded_in'])}." if draft["grounded_in"] else ""
    return list(drafts.values())


def extract_related_pairs(issues: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """One co-occurring pair per two concept slugs that appear on the same
    issue, deduplicated and order-independent. `run_ingestion` hands each
    pair to an `ExtractionClient` to decide `prerequisite` vs `related` —
    this just avoids asking it to classify the same unordered pair twice."""
    seen: dict[frozenset[str], tuple[str, str]] = {}
    for issue in issues:
        slugs = issue.get("concepts", [])
        for i, a in enumerate(slugs):
            for b in slugs[i + 1 :]:
                if a == b:
                    continue
                seen.setdefault(frozenset((a, b)), (a, b))
    return list(seen.values())


def _sse(event: str, data: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n".encode()


def _concept_event(concept: Any) -> dict[str, Any]:
    return {
        "id": concept.id,
        "slug": concept.slug,
        "title": concept.title,
        "description": concept.description,
    }


async def _augment_with_exa(drafts: list[dict[str, Any]]) -> None:
    """Fourth source: for a concept whose only local citation is a single
    issue (thin grounding), look up one external result to cite alongside
    it. A no-op with no `EXA_API_KEY` configured, and never fails ingestion
    — a lookup error just leaves the concept's citations as they were."""
    client = ExaClient()
    for draft in drafts:
        if len(draft["grounded_in"]) > 1:
            continue
        try:
            result = await client.search(f"{draft['title']} Ferry payments")
        except Exception:  # noqa: BLE001 — Exa is enrichment, never load-bearing
            result = None
        if result and result.get("url"):
            citation = f"exa:{result['url']}"
            if citation not in draft["grounded_in"]:
                draft["grounded_in"].append(citation)


async def run_ingestion(
    session: AsyncSession,
    extraction_client: ExtractionClient,
    *,
    issues: list[dict[str, Any]] | None = None,
) -> AsyncIterator[bytes]:
    """The ingestion job itself, as an SSE byte stream. `issues` is
    injectable for tests exercising the empty-source path without touching
    the real fixture file; the trigger route always calls it with the
    default (`load_context_issues()`)."""
    if issues is None:
        issues = load_context_issues()

    if not issues:
        yield _sse("empty", {})
        return

    try:
        drafts = extract_concept_drafts(issues)
        pairs = extract_related_pairs(issues)
        augment_citations(drafts, load_release_notes_source())
        await _augment_with_exa(drafts)
        draft_by_slug = {draft["slug"]: draft for draft in drafts}

        course = await curriculum_service.create_course(
            session,
            title="Ingested team context",
            description="Ingested from the connected 1-context sources.",
            slug=f"ingest-{uuid.uuid4().hex[:12]}",
        )

        concept_by_slug: dict[str, Any] = {}
        for draft in drafts:
            concept = await curriculum_service.create_concept(
                session,
                course_id=course.id,
                slug=draft["slug"],
                title=draft["title"],
                description=draft["description"],
            )
            concept_by_slug[draft["slug"]] = concept
            yield _sse("concept", _concept_event(concept))
            await asyncio.sleep(STREAM_DELAY_SECONDS)

        for a_slug, b_slug in pairs:
            relation = await extraction_client.classify_relation(
                concept_a=draft_by_slug[a_slug], concept_b=draft_by_slug[b_slug]
            )
            kind = relation["kind"] if relation["kind"] in curriculum_service.EDGE_KINDS else "related"
            from_id = concept_by_slug[relation["from_slug"]].id
            to_id = concept_by_slug[relation["to_slug"]].id
            try:
                await curriculum_service.create_edge(
                    session, from_concept_id=from_id, to_concept_id=to_id, kind=kind, weight=relation["weight"]
                )
            except curriculum_service.CycleError:
                # The graph must stay a validated-acyclic DAG: a
                # prerequisite classification that would close a cycle is
                # downgraded to `related` instead of dropped, so the
                # relationship still lands on the graph, just undirected.
                await curriculum_service.create_edge(
                    session, from_concept_id=from_id, to_concept_id=to_id, kind="related", weight=relation["weight"]
                )

        item_count = 0
        for draft in drafts:
            concept = concept_by_slug[draft["slug"]]
            sibling_titles = [d["title"] for d in drafts if d["slug"] != draft["slug"]]
            item_draft = await extraction_client.draft_item(concept=draft, distractor_pool=sibling_titles)
            if item_draft is None:
                # Review gate: a concept with no traceable citation gets no
                # item at all, so nothing exists for it to publish — it
                # stays `draft` until re-ingested with a real source.
                continue
            await curriculum_service.create_item(
                session,
                concept_id=concept.id,
                kind=item_draft["kind"],
                prompt=item_draft["prompt"],
                payload={
                    "options": item_draft["options"],
                    "correct_index": item_draft["correct_index"],
                    "explanation": item_draft["explanation"],
                    "citations": draft["grounded_in"],
                },
                status="draft",  # ingestion never publishes; that's the human review gate
            )
            item_count += 1

        grounded_in = sorted({key for issue in issues for key in [issue.get("key")] if key})
        entry_concept = concept_by_slug[drafts[0]["slug"]]
        await curriculum_service.create_topic(
            session,
            course_id=course.id,
            slug=f"ingested-context-{course.id[:8]}",
            title="Ingested team context",
            persona_role=INGESTED_TOPIC_PERSONA_ROLE,
            entry_concept_id=entry_concept.id,
            concept_ids=[c.id for c in concept_by_slug.values()],
            grounded_in=grounded_in,
        )

        yield _sse("done", {"course_id": course.id, "concept_count": len(drafts), "item_count": item_count})
    except Exception as exc:  # noqa: BLE001 — surface it to the streaming client, don't 500 mid-stream
        yield _sse("error", {"message": str(exc)})


@router.get("/admin/ingest")
async def trigger_ingest(
    _: None = Depends(require_operator),
    session: AsyncSession = Depends(get_session),
    extraction_client: ExtractionClient = Depends(get_extraction_client),
) -> StreamingResponse:
    return StreamingResponse(run_ingestion(session, extraction_client), media_type="text/event-stream")
