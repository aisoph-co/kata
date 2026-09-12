"""`GET /me/concept-graph` (Contract v1.2.1 additive change #6): concepts and
edges of a course, with the acting person's own `p_known`/`mastered`/
`unlocked` per node, so the web app can draw the concept map (Screen 2).

`p_known`/`mastered`/`unlocked` are read from `concept_state` (BKT) via the
`engine` package (KATA-2's follow-up issue, this one) — see
`engine.selection` for the shared "is this concept mastered/unlocked"
definitions every other route (`/me/next`, `/me/progress`, `/team/*`) also
uses, so there is exactly one answer to each question in the service.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.db import get_session
from learning_service.engine.selection import build_prereqs_of, concept_states_by_id, is_mastered, is_unlocked, p_known_for
from learning_service.main import resolve_person_id

router = APIRouter()


@router.get("/me/concept-graph")
async def me_concept_graph(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    concepts = await curriculum_service.list_concepts(session)
    prereq_edges = await curriculum_service.list_edges(session, kind="prerequisite")
    related_edges = await curriculum_service.list_edges(session, kind="related")
    prereqs_of = build_prereqs_of(concepts, prereq_edges)
    states = await concept_states_by_id(session, person_id)

    nodes = [
        {
            "concept_id": concept.id,
            "slug": concept.slug,
            "title": concept.title,
            "p_known": p_known_for(states, concept.id),
            "mastered": is_mastered(states, concept),
            "unlocked": is_unlocked(states, concept.id, prereqs_of),
        }
        for concept in concepts
    ]
    edges = [
        {
            "from_concept_id": edge.from_concept_id,
            "to_concept_id": edge.to_concept_id,
            "kind": edge.kind,
            "weight": edge.weight,
        }
        for edge in [*prereq_edges, *related_edges]
    ]
    return {"nodes": nodes, "edges": edges}
