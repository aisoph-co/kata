"""`GET /me/progress` + `GET /me/due-summary` (spec §API, `ProgressResponse`/
`DueSummary` in `openapi.yaml`): per-concept mastery/due/unlocked state and
digest counts for the acting person.

Read-only over the `card_state`/`concept_state` derived caches that
`POST /me/reviews` and `POST /admin/replay` maintain; this module computes
nothing new, it only reads.

`DueSummary.due_count` is the digest headline total: `overdue_count` (cards
with `due_at <= now`, the same "due" `select_next_items` step 1 uses) plus
`new_available_count` (unreviewed items from unlocked, not-yet-mastered
concepts, the same candidate pool `select_next_items` step 2 draws from).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends

from learning_service.engine.analytics import person_learning_summary
from learning_service.engine.repository import LearningRepository
from learning_service.engine.selection import build_prereqs_of, is_mastered, is_unlocked, p_known_for
from learning_service.main import get_repository, resolve_person_id

router = APIRouter()


def _due_count(repo: LearningRepository, person_id: str, concept_id: str, now: datetime) -> int:
    count = 0
    for card in repo.card_states_for(person_id):
        if card.due_at > now:
            continue
        item = repo.get_item(card.item_id)
        if item is not None and item.concept_id == concept_id:
            count += 1
    return count


@router.get("/me/progress")
async def me_progress(
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    concepts = repo.list_concepts()
    prereqs_of = build_prereqs_of(concepts, repo.list_edges("prerequisite"))

    return {
        "concepts": [
            {
                "concept_id": concept.id,
                "p_known": p_known_for(repo, person_id, concept.id),
                "mastered": is_mastered(repo, person_id, concept),
                "due_count": _due_count(repo, person_id, concept.id, now),
                "unlocked": is_unlocked(repo, person_id, concept.id, prereqs_of),
            }
            for concept in concepts
        ],
        # Contract v1.2.0: the four MVP dashboard metrics beyond mastery —
        # retention, bypass rate, calibration, review count/recency —
        # derived from the review log, never the raw rows.
        "summary": person_learning_summary(repo.reviews_for(person_id)),
    }


@router.get("/me/due-summary")
async def me_due_summary(
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    concepts = repo.list_concepts()
    prereqs_of = build_prereqs_of(concepts, repo.list_edges("prerequisite"))

    card_states = repo.card_states_for(person_id)
    overdue_count = sum(1 for card in card_states if card.due_at <= now)

    reviewed_item_ids = {card.item_id for card in card_states}
    new_available_count = 0
    for concept in concepts:
        if not is_unlocked(repo, person_id, concept.id, prereqs_of) or is_mastered(repo, person_id, concept):
            continue
        for item in repo.published_items(concept.id):
            if item.id not in reviewed_item_ids:
                new_available_count += 1

    return {
        "due_count": overdue_count + new_available_count,
        "overdue_count": overdue_count,
        "new_available_count": new_available_count,
    }
