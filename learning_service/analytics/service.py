"""Team analytics computation (spec §Team analytics) and focus/audit
persistence (spec §Privacy and retention → "Audit"; §API `POST /team/focus`).

Concept/item/review state (`concept_state`, `card_state`, the review log) is
read through the same `LearningRepository` `/me/*` and `select_next_items`
use (see `engine/repository.py`; this is always `SqlLearningRepository` in
this build), so team analytics reads the identical source of truth rather
than standing up a second one. Roster (`person.manager_id`, `is_operator`)
is read from Postgres via `roster.service.get_subtree_ids`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.analytics.models import AuditEntry
from learning_service.engine.analytics import person_learning_summary, subtree_retention
from learning_service.engine.models import AT_RISK_THRESHOLD, P_INIT
from learning_service.engine.repository import LearningRepository
from learning_service.engine.selection import build_prereqs_of, is_mastered, is_unlocked, p_known_for
from learning_service.roster.models import Focus as DbFocus

RECOMMENDATION_LIMIT = 5
DEFAULT_DIGEST_DAYS = 7


def _as_utc(dt: datetime) -> datetime:
    # SQLite drops tzinfo on round-trip even for `DateTime(timezone=True)`;
    # every value here is written in UTC, so a naive value is UTC too.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


async def write_audit(session: AsyncSession, *, actor_person_id: str, subject_scope: str, endpoint: str) -> None:
    session.add(AuditEntry(actor_person_id=actor_person_id, subject_scope=subject_scope, endpoint=endpoint))
    await session.commit()


async def list_audit_for_subtree(session: AsyncSession, *, actor_ids: list[str]) -> list[AuditEntry]:
    result = await session.execute(
        select(AuditEntry).where(AuditEntry.actor_person_id.in_(actor_ids)).order_by(AuditEntry.at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Per-concept / per-person metrics (spec §Team analytics, the metric table)
# ---------------------------------------------------------------------------


def is_at_risk(repo: LearningRepository, person_id: str, concept_id: str, now: datetime) -> bool:
    if p_known_for(repo, person_id, concept_id) >= AT_RISK_THRESHOLD:
        return False
    for card in repo.card_states_for(person_id):
        if card.due_at > now:
            continue
        item = repo.get_item(card.item_id)
        if item is not None and item.concept_id == concept_id:
            return True
    return False


def due_count_for_concept(repo: LearningRepository, person_id: str, concept_id: str, now: datetime) -> int:
    count = 0
    for card in repo.card_states_for(person_id):
        if card.due_at > now:
            continue
        item = repo.get_item(card.item_id)
        if item is not None and item.concept_id == concept_id:
            count += 1
    return count


def due_count_for_person(
    repo: LearningRepository,
    person_id: str,
    concepts: list,
    prereqs_of: dict,
    now: datetime,
) -> int:
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
    return overdue_count + new_available_count


def concept_summary(repo: LearningRepository, concept, subtree_ids: list[str], now: datetime) -> dict:
    if not subtree_ids:
        return {"concept_id": concept.id, "mean_mastery": P_INIT, "share_mastered": 0.0, "at_risk_count": 0}
    p_knowns = [p_known_for(repo, pid, concept.id) for pid in subtree_ids]
    mastered_count = sum(1 for pid in subtree_ids if is_mastered(repo, pid, concept))
    at_risk_count = sum(1 for pid in subtree_ids if is_at_risk(repo, pid, concept.id, now))
    return {
        "concept_id": concept.id,
        "mean_mastery": sum(p_knowns) / len(subtree_ids),
        "share_mastered": mastered_count / len(subtree_ids),
        "at_risk_count": at_risk_count,
    }


def team_retention(repo: LearningRepository, person_ids: list[str]) -> dict:
    """The pooled counterpart of `person_learning_summary`'s retention
    bands, for `GET /team/overview` — an individual's d30 band is
    frequently thin, but the team-aggregate band usually clears
    `_MIN_RETENTION_SAMPLES`. Callers pass whichever ids the team curve
    should cover; `analytics/router.py` includes the acting manager's own
    reviews alongside their subtree, unlike the `people` read below, which
    deliberately excludes the caller."""
    pooled = [review for pid in person_ids for review in repo.reviews_for(pid)]
    return subtree_retention(pooled)


def person_summary(
    repo: LearningRepository, person_id: str, concepts: list, now: datetime, window_days: int
) -> dict:
    window_start = now - timedelta(days=window_days)
    reviews = repo.reviews_for(person_id)
    learning = person_learning_summary(reviews)

    completed_in_window = sum(1 for r in reviews if _parse(r["reviewed_at"]) >= window_start)
    # "reviews due" has no stored history once a card is reviewed again (its
    # `due_at` advances), so due-in-window is approximated as completions in
    # the window plus cards still overdue right now (spec §Team analytics,
    # "adherence": "1.0 when nothing was due").
    still_overdue = sum(1 for c in repo.card_states_for(person_id) if c.due_at <= now)
    due_in_window = completed_in_window + still_overdue
    adherence = 1.0 if due_in_window == 0 else completed_in_window / due_in_window

    # "concepts newly mastered in the trailing 7 days": concept_state has no
    # timestamped mastery-crossing event, so this counts concepts currently
    # mastered whose most recent review (the one that could have crossed the
    # threshold) falls inside the window.
    velocity = 0
    for concept in concepts:
        state = repo.concept_state_for(person_id, concept.id)
        if state is None or state.last_review_at is None:
            continue
        if is_mastered(repo, person_id, concept) and _as_utc(state.last_review_at) >= window_start:
            velocity += 1

    return {
        "adherence": adherence,
        "velocity": velocity,
        "last_active": learning["last_active"],
        # Concept-level /team/* views still never see an answer or a
        # review's own detail — these are the same scalar aggregates
        # /me/progress.summary reports.
        "bypass_rate": learning["bypass_rate"],
        "retention": learning["retention"],
        "calibration": learning["calibration"],
    }


def _parse(reviewed_at) -> datetime:
    if isinstance(reviewed_at, datetime):
        return _as_utc(reviewed_at)
    return datetime.fromisoformat(str(reviewed_at).replace("Z", "+00:00"))


# ---------------------------------------------------------------------------
# Recommendations (spec §Team analytics, "Recommendation")
# ---------------------------------------------------------------------------


def _dependents_count(concepts: list, prereq_edges: list, concept_id: str) -> int:
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


def build_recommendations(
    repo: LearningRepository, subtree_ids: list[str], now: datetime, limit: int = RECOMMENDATION_LIMIT
) -> list[dict]:
    concepts = repo.list_concepts()
    prereq_edges = repo.list_edges("prerequisite")
    prereqs_of = build_prereqs_of(concepts, prereq_edges)

    if not subtree_ids:
        return []

    candidates = []
    for concept in concepts:
        unlocked_count = sum(1 for pid in subtree_ids if is_unlocked(repo, pid, concept.id, prereqs_of))
        if unlocked_count * 2 < len(subtree_ids):
            continue
        mean_mastery = sum(p_known_for(repo, pid, concept.id) for pid in subtree_ids) / len(subtree_ids)
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
) -> DbFocus:
    """Upserts on `(scope_kind, scope_person_id, concept_id)`: a repeated
    identical POST replaces the existing row's
    `weight`/`expires_at`/`set_by` rather than adding a new one, so posting
    the same focus twice always leaves exactly one row and one weight
    application (otherwise `_focus_weight` would multiply over every
    duplicate).

    `SqlLearningRepository.load()` reads this table directly — expanding
    `subtree` scopes into `focuses_for(person_id)` at hydration time — so
    every request gets a fresh, correct view with no in-process mirror to
    keep in sync.
    """
    existing = await session.execute(
        select(DbFocus).where(
            DbFocus.scope_kind == scope_kind,
            DbFocus.scope_person_id == scope_person_id,
            DbFocus.concept_id == concept_id,
        )
    )
    focus_row = existing.scalar_one_or_none()
    if focus_row is None:
        focus_row = DbFocus(
            scope_kind=scope_kind,
            scope_person_id=scope_person_id,
            concept_id=concept_id,
            weight=weight,
            set_by=set_by,
            expires_at=expires_at,
        )
        session.add(focus_row)
    else:
        focus_row.weight = weight
        focus_row.expires_at = expires_at
        focus_row.set_by = set_by
    await session.commit()
    return focus_row


async def delete_focus(session: AsyncSession, *, focus_id: str) -> DbFocus | None:
    result = await session.execute(select(DbFocus).where(DbFocus.id == focus_id))
    focus_row = result.scalar_one_or_none()
    if focus_row is None:
        return None
    await session.delete(focus_row)
    await session.commit()
    return focus_row
