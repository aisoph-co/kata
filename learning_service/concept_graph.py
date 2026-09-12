"""`GET /me/concept-graph`: concepts and edges of the course, with the
acting person's own `p_known`/`mastered`/`unlocked` per node, so the web app
can draw the concept map.

C1 ships the structural graph only: `card_state`/`concept_state` (the BKT
mastery the engine package computes per review) don't exist yet, so every
concept reads at `p_init` and nothing is ever `mastered` here — only
prerequisite-free concepts are `unlocked`. C2 replaces `_p_known_for` and
`_is_mastered` with a live `concept_state` query at zero contract change
(the response shape is already final).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum.models import Concept
from learning_service.db import get_session
from learning_service.main import resolve_person_id

router = APIRouter()

# spec §Learning engine → BKT: p_init, duplicated here until C2's engine
# package is the one source of truth for concept mastery.
P_INIT = 0.20


def _p_known_for(person_id: str, concept_id: str) -> float:
    return P_INIT


def _is_mastered(person_id: str, concept: Concept) -> bool:
    return _p_known_for(person_id, concept.id) >= concept.mastery_threshold


@router.get("/me/concept-graph")
async def me_concept_graph(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    concepts = await curriculum_service.list_concepts(session)
    prereq_edges = await curriculum_service.list_edges(session, kind="prerequisite")
    related_edges = await curriculum_service.list_edges(session, kind="related")

    has_prereq = {edge.to_concept_id for edge in prereq_edges}

    nodes = [
        {
            "concept_id": concept.id,
            "slug": concept.slug,
            "title": concept.title,
            "p_known": _p_known_for(person_id, concept.id),
            "mastered": _is_mastered(person_id, concept),
            "unlocked": concept.id not in has_prereq,
        }
        for concept in concepts
    ]
    edges = [
        {"from_concept_id": e.from_concept_id, "to_concept_id": e.to_concept_id, "kind": e.kind, "weight": e.weight}
        for e in [*prereq_edges, *related_edges]
    ]
    return {"nodes": nodes, "edges": edges}
