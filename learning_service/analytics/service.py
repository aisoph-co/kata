"""Team-level metrics (spec §Team analytics, the metric table) and `focus`
persistence (spec §API, `POST /team/focus`). Reads `concept_state`/
`card_state`/`review` through the same snapshot helpers `engine.selection`
uses, and the roster through `roster.service.get_subtree_ids`, so team
analytics has exactly one source of truth for each.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.analytics.summary import person_learning_summary, subtree_retention
from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum.models import Concept, ConceptEdge, Item
from learning_service.engine.models import AT_RISK_THRESHOLD, P_INIT, CardState, ConceptState, Focus, Review, as_utc
from learning_service.engine.selection import (
    build_prereqs_of,
    card_states_for,
    concept_states_by_id,
    is_mastered,
    is_unlocked,
    new_available_count,
    p_known_for,
)

RECOMMENDATION_LIMIT = 5
DEFAULT_DIGEST_DAYS = 7


async def reviews_for(session: AsyncSession, person_id: str) -> list[Review]:
    result = await session.execute(select(Review).where(Review.person_id == person_id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Per-concept / per-person metrics
# ---------------------------------------------------------------------------


def is_at_risk(
    states: dict[str, ConceptState], card_states: list[CardState], items_by_id: dict[str, Item], concept_id: str, now: datetime
) -> bool:
    if p_known_for(states, concept_id) >= AT_RISK_THRESHOLD:
        return False
    for card in card_states:
        if as_utc(card.due_at) > now:
            continue
        item = items_by_id.get(card.item_id)
        if item is not None and item.concept_id == concept_id:
            return True
    return False


async def concept_summary(
    session: AsyncSession, concept: Concept, subtree_ids: list[str], items_by_id: dict[str, Item], now: datetime
) -> dict:
    if not subtree_ids:
        return {"concept_id": concept.id, "mean_mastery": P_INIT, "share_mastered": 0.0, "at_risk_count": 0}

    p_knowns = []
    mastered_count = 0
    at_risk_count = 0
    for pid in subtree_ids:
        states = await concept_states_by_id(session, pid)
        p_knowns.append(p_known_for(states, concept.id))
        if is_mastered(states, concept):
            mastered_count += 1
        card_states = await card_states_for(session, pid)
        if is_at_risk(states, card_states, items_by_id, concept.id, now):
            at_risk_count += 1

    return {
        "concept_id": concept.id,
        "mean_mastery": sum(p_knowns) / len(subtree_ids),
        "share_mastered": mastered_count / len(subtree_ids),
        "at_risk_count": at_risk_count,
    }


async def team_retention(session: AsyncSession, person_ids: list[str]) -> dict:
    """QA-style team-aggregate retention for `GET /team/overview`: pooled
    across whichever ids the caller passes (`team.py` includes the acting
    manager's own reviews alongside their subtree, unlike the `people` read,
    which deliberately excludes the caller)."""
    pooled: list[Review] = []
    for pid in person_ids:
        pooled.extend(await reviews_for(session, pid))
    return subtree_retention(pooled)


async def person_summary(session: AsyncSession, person_id: str, concepts: list[Concept], now: datetime, window_days: int) -> dict:
    window_start = now - timedelta(days=window_days)
    reviews = await reviews_for(session, person_id)
    learning = person_learning_summary(reviews)

    completed_in_window = sum(1 for r in reviews if as_utc(r.reviewed_at) >= window_start)
    card_states = await card_states_for(session, person_id)
    still_overdue = sum(1 for c in card_states if as_utc(c.due_at) <= now)
    due_in_window = completed_in_window + still_overdue
    adherence = 1.0 if due_in_window == 0 else completed_in_window / due_in_window

    states = await concept_states_by_id(session, person_id)
    velocity = 0
    for concept in concepts:
        state = states.get(concept.id)
        if state is None or state.last_review_at is None:
            continue
        if is_mastered(states, concept) and as_utc(state.last_review_at) >= window_start:
            velocity += 1

    return {
        "adherence": adherence,
        "velocity": velocity,
        "last_active": learning["last_active"],
        "bypass_rate": learning["bypass_rate"],
        "retention": learning["retention"],
        "calibration": learning["calibration"],
    }


async def due_count_for_person(
    session: AsyncSession, person_id: str, concepts: list[Concept], prereqs_of: dict, concept_items: dict, now: datetime
) -> int:
    card_states = await card_states_for(session, person_id)
    overdue_count = sum(1 for card in card_states if as_utc(card.due_at) <= now)
    reviewed_item_ids = {c.item_id for c in card_states}
    states = await concept_states_by_id(session, person_id)
    return overdue_count + new_available_count(concepts, states, prereqs_of, concept_items, reviewed_item_ids)


# ---------------------------------------------------------------------------
# Recommendations (spec §Team analytics, "Recommendation")
# ---------------------------------------------------------------------------


def _dependents_count(concepts: list[Concept], prereq_edges: list[ConceptEdge], concept_id: str) -> int:
    children_of: dict[str, list[str]] = {c.id: [] for c in concepts}
    for edge in prereq_edges:
        if edge.from_concept_id in children_of:
            children_of[edge.from_concept_id].append(edge.to_concept_id)

    seen: set[str] = set()
    queue = list(children_of.get(concept_id, []))
    while queue:
        cid = queue.pop(0)
        if cid in seen:
            continue
        seen.add(cid)
        queue.extend(children_of.get(cid, []))
    return len(seen)


async def build_recommendations(session: AsyncSession, subtree_ids: list[str], limit: int = RECOMMENDATION_LIMIT) -> list[dict]:
    concepts = await curriculum_service.list_concepts(session)
    prereq_edges = await curriculum_service.list_edges(session, kind="prerequisite")
    prereqs_of = build_prereqs_of(concepts, prereq_edges)

    if not subtree_ids:
        return []

    states_by_person = {pid: await concept_states_by_id(session, pid) for pid in subtree_ids}

    candidates = []
    for concept in concepts:
        unlocked_count = sum(1 for pid in subtree_ids if is_unlocked(states_by_person[pid], concept.id, prereqs_of))
        if unlocked_count * 2 < len(subtree_ids):
            continue
        mean_mastery = sum(p_known_for(states_by_person[pid], concept.id) for pid in subtree_ids) / len(subtree_ids)
        dependents = _dependents_count(concepts, prereq_edges, concept.id)
        score = (1 - mean_mastery) * (1 + dependents)
        candidates.append(
            {"concept_id": concept.id, "score": score, "mean_mastery": mean_mastery, "dependents_count": dependents}
        )

    candidates.sort(key=lambda c: (-c["score"], c["concept_id"]))
    return candidates[:limit]


# ---------------------------------------------------------------------------
# Focus (spec §API `POST /team/focus`, `DELETE /team/focus/{id}`)
# ---------------------------------------------------------------------------


async def create_focus(
    session: AsyncSession,
    *,
    scope_kind: str,
    scope_person_id: str,
    concept_id: str,
    weight: float,
    expires_at: datetime | None,
    set_by: str,
) -> Focus:
    """Upserts on `(scope_kind, scope_person_id, concept_id)` — a repeat
    POST for the same scope+concept replaces `weight`/`expires_at`/`set_by`
    rather than adding a second row (which would compound the weight in
    `engine.selection._focus_weight`)."""
    existing = await session.execute(
        select(Focus).where(
            Focus.scope_kind == scope_kind, Focus.scope_person_id == scope_person_id, Focus.concept_id == concept_id
        )
    )
    focus = existing.scalar_one_or_none()
    if focus is None:
        focus = Focus(
            scope_kind=scope_kind,
            scope_person_id=scope_person_id,
            concept_id=concept_id,
            weight=weight,
            set_by=set_by,
            expires_at=expires_at,
        )
        session.add(focus)
    else:
        focus.weight = weight
        focus.expires_at = expires_at
        focus.set_by = set_by
    await session.commit()
    return focus


async def delete_focus(session: AsyncSession, focus_id: str) -> Focus | None:
    focus = await session.get(Focus, focus_id)
    if focus is None:
        return None
    await session.delete(focus)
    await session.commit()
    return focus
