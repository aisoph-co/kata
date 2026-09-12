"""`GET /me/progress` + `GET /me/due-summary` (spec §API): per-concept
mastery/due/unlocked state and digest counts for the acting person.

Read-only over the `card_state`/`concept_state` derived caches that
`POST /me/reviews` and `POST /admin/replay` maintain, plus the `review` log
for `summary` (retention/bypass_rate/calibration/review_count/last_active,
Contract v1.2.1 `PersonLearningSummary`) — this module computes nothing new
beyond `analytics.summary`, it only reads.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.analytics.service import reviews_for
from learning_service.analytics.summary import person_learning_summary
from learning_service.curriculum import service as curriculum_service
from learning_service.db import get_session
from learning_service.engine.bkt import update_p_known
from learning_service.engine.models import P_INIT, Review, as_utc
from learning_service.engine.selection import (
    build_prereqs_of,
    card_states_for,
    concept_states_by_id,
    due_count_for_concept,
    is_mastered,
    is_unlocked,
    items_by_concept,
    new_available_count,
    p_known_for,
)
from learning_service.main import resolve_person_id

router = APIRouter()

_RATING_LABEL = {1: "again", 2: "hard", 3: "good", 4: "easy"}


@router.get("/me/progress")
async def me_progress(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    concepts = await curriculum_service.list_concepts(session)
    prereqs_of = build_prereqs_of(concepts, await curriculum_service.list_edges(session, kind="prerequisite"))
    states = await concept_states_by_id(session, person_id)
    card_states = await card_states_for(session, person_id)
    concept_items = await items_by_concept(session, status="published")
    items_by_id = {item.id: item for items in concept_items.values() for item in items}

    return {
        "concepts": [
            {
                "concept_id": concept.id,
                "p_known": p_known_for(states, concept.id),
                "mastered": is_mastered(states, concept),
                "due_count": due_count_for_concept(card_states, items_by_id, concept.id, now),
                "unlocked": is_unlocked(states, concept.id, prereqs_of),
            }
            for concept in concepts
        ],
        "summary": person_learning_summary(await reviews_for(session, person_id)),
    }


@router.get("/me/history")
async def me_history(
    days: int = Query(default=30, ge=1, le=365),
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return a chronological review trace for the Progress chart.

    V3 stores only the current concept state. Build each historical
    ``p_known_after`` value from the append-only review log using the same
    BKT transition as replay, without writing to the database.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await session.execute(
            select(Review)
            .where(Review.person_id == person_id)
            .order_by(Review.reviewed_at, Review.id)
        )
    ).scalars().all()

    p_known_by_concept: dict[str, float] = {}
    reviews = []
    for review in rows:
        p_known = update_p_known(
            p_known_by_concept.get(review.concept_id, P_INIT),
            review.kind,
            review.rating >= 3,
        )
        p_known_by_concept[review.concept_id] = p_known

        reviewed_at = as_utc(review.reviewed_at)
        if reviewed_at < cutoff:
            continue
        reviews.append(
            {
                "created_at": reviewed_at.isoformat(),
                "concept_id": review.concept_id,
                "item_id": review.item_id,
                "grade": review.grade,
                "rating": _RATING_LABEL.get(review.rating, "good"),
                "bypassed": review.bypassed,
                "p_known_after": p_known,
            }
        )

    return {"days": days, "reviews": reviews}


@router.get("/me/due-summary")
async def me_due_summary(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    concepts = await curriculum_service.list_concepts(session)
    prereqs_of = build_prereqs_of(concepts, await curriculum_service.list_edges(session, kind="prerequisite"))
    states = await concept_states_by_id(session, person_id)
    card_states = await card_states_for(session, person_id)
    concept_items = await items_by_concept(session, status="published")

    overdue_count = sum(1 for card in card_states if as_utc(card.due_at) <= now)
    reviewed_item_ids = {card.item_id for card in card_states}
    new_count = new_available_count(concepts, states, prereqs_of, concept_items, reviewed_item_ids)

    return {
        "due_count": overdue_count + new_count,
        "overdue_count": overdue_count,
        "new_available_count": new_count,
    }
