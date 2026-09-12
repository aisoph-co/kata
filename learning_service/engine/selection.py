"""Next-item selection (spec §Learning engine, "Next-item selection") plus
the mastery/unlocked/due-count helpers `progress.py`, `team.py`, and
`analytics` all share, so there is exactly one definition of "unlocked" and
"mastered" in the service.

Order: overdue reviews (retrievability ascending) -> new items from
unlocked concepts (score = (1-p_known)*depth_weight*focus_weight, highest
first) -> co-review of up to two related concepts for any selected concept
below the 0.5 mastery line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum.models import Concept, ConceptEdge, Item
from learning_service.engine.models import P_INIT, CardState, ConceptState, Focus, as_utc
from learning_service.engine.retrievability import retrievability
from learning_service.identity.models import Person

DEFAULT_LIMIT = 5
MAX_LIMIT = 20
CO_REVIEW_THRESHOLD = 0.5
CO_REVIEW_MIN_WEIGHT = 0.5
CO_REVIEW_MAX_NEIGHBORS = 2


@dataclass(frozen=True)
class SelectedItem:
    item: Item
    concept_id: str


@dataclass(frozen=True)
class NextResult:
    items: list[SelectedItem]
    reason: str | None  # "all_mastered" | "blocked_by_prerequisites" | None


def stripped_payload(item: Item) -> dict:
    from learning_service.engine.models import ANSWER_KEY_FIELDS

    return {k: v for k, v in (item.payload or {}).items() if k not in ANSWER_KEY_FIELDS}


# ---------------------------------------------------------------------------
# Snapshot loaders
# ---------------------------------------------------------------------------


async def concept_states_by_id(session: AsyncSession, person_id: str) -> dict[str, ConceptState]:
    result = await session.execute(select(ConceptState).where(ConceptState.person_id == person_id))
    return {cs.concept_id: cs for cs in result.scalars().all()}


async def card_states_for(session: AsyncSession, person_id: str) -> list[CardState]:
    result = await session.execute(select(CardState).where(CardState.person_id == person_id))
    return list(result.scalars().all())


async def items_by_concept(session: AsyncSession, *, status: str | None = "published") -> dict[str, list[Item]]:
    items = await curriculum_service.list_items(session, status=status)
    by_concept: dict[str, list[Item]] = {}
    for item in items:
        by_concept.setdefault(item.concept_id, []).append(item)
    return by_concept


async def ancestor_ids(session: AsyncSession, person_id: str) -> set[str]:
    """`person_id` plus every manager above it (used to resolve which
    `subtree`-scoped focuses apply to this person — spec §Identity, roles,
    teams: "subtree of a person = the person plus all transitive reports")."""
    result = await session.execute(select(Person.id, Person.manager_id))
    manager_of = dict(result.all())
    ancestors = {person_id}
    current = manager_of.get(person_id)
    while current is not None and current not in ancestors:
        ancestors.add(current)
        current = manager_of.get(current)
    return ancestors


async def focuses_all(session: AsyncSession) -> list[Focus]:
    result = await session.execute(select(Focus))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Mastery / unlocked / focus
# ---------------------------------------------------------------------------


def p_known_for(states: dict[str, ConceptState], concept_id: str) -> float:
    state = states.get(concept_id)
    return state.p_known if state is not None else P_INIT


def is_mastered(states: dict[str, ConceptState], concept: Concept) -> bool:
    return p_known_for(states, concept.id) >= concept.mastery_threshold


def build_prereqs_of(concepts: list[Concept], prereq_edges: list[ConceptEdge]) -> dict[str, list[Concept]]:
    concepts_by_id = {c.id: c for c in concepts}
    prereqs_of: dict[str, list[Concept]] = {c.id: [] for c in concepts}
    for edge in prereq_edges:
        if edge.to_concept_id in prereqs_of and edge.from_concept_id in concepts_by_id:
            prereqs_of[edge.to_concept_id].append(concepts_by_id[edge.from_concept_id])
    return prereqs_of


def is_unlocked(states: dict[str, ConceptState], concept_id: str, prereqs_of: dict[str, list[Concept]]) -> bool:
    for prereq in prereqs_of.get(concept_id, []):
        if not is_mastered(states, prereq):
            return False
    return True


def _depths(concepts: list[Concept], prereq_edges: list[ConceptEdge]) -> dict[str, int]:
    prereqs_of: dict[str, list[str]] = {c.id: [] for c in concepts}
    for edge in prereq_edges:
        if edge.to_concept_id in prereqs_of:
            prereqs_of[edge.to_concept_id].append(edge.from_concept_id)

    depth: dict[str, int] = {}

    def compute(concept_id: str, seen: frozenset[str]) -> int:
        if concept_id in depth:
            return depth[concept_id]
        parents = prereqs_of.get(concept_id, [])
        if not parents:
            depth[concept_id] = 0
        else:
            depth[concept_id] = 1 + max(compute(p, seen | {concept_id}) for p in parents if p not in seen)
        return depth[concept_id]

    for c in concepts:
        compute(c.id, frozenset())
    return depth


def _focus_weight(
    focuses: list[Focus], ancestors: set[str], person_id: str, concept_id: str, now: datetime
) -> float:
    weight = 1.0
    for focus in focuses:
        if focus.concept_id != concept_id:
            continue
        if focus.expires_at is not None and as_utc(focus.expires_at) <= now:
            continue
        if focus.scope_kind == "person" and focus.scope_person_id == person_id:
            weight *= focus.weight
        elif focus.scope_kind == "subtree" and focus.scope_person_id in ancestors:
            weight *= focus.weight
    return weight


# ---------------------------------------------------------------------------
# Due counts (shared by /me/due-summary, /team/people/{id}, analytics)
# ---------------------------------------------------------------------------


def due_count_for_concept(card_states: list[CardState], items_by_id: dict[str, Item], concept_id: str, now: datetime) -> int:
    count = 0
    for card in card_states:
        if as_utc(card.due_at) > now:
            continue
        item = items_by_id.get(card.item_id)
        if item is not None and item.concept_id == concept_id:
            count += 1
    return count


def new_available_count(
    concepts: list[Concept],
    states: dict[str, ConceptState],
    prereqs_of: dict[str, list[Concept]],
    concept_items: dict[str, list[Item]],
    reviewed_item_ids: set[str],
) -> int:
    count = 0
    for concept in concepts:
        if not is_unlocked(states, concept.id, prereqs_of) or is_mastered(states, concept):
            continue
        for item in concept_items.get(concept.id, []):
            if item.id not in reviewed_item_ids:
                count += 1
    return count


# ---------------------------------------------------------------------------
# Next-item selection
# ---------------------------------------------------------------------------


async def select_next_items(session: AsyncSession, person_id: str, now: datetime, limit: int = DEFAULT_LIMIT) -> NextResult:
    limit = max(1, min(limit, MAX_LIMIT))

    concepts = await curriculum_service.list_concepts(session)
    concepts_by_id = {c.id: c for c in concepts}
    prereq_edges = await curriculum_service.list_edges(session, kind="prerequisite")
    related_edges = await curriculum_service.list_edges(session, kind="related")
    depths = _depths(concepts, prereq_edges)
    max_depth = max(depths.values(), default=0)
    prereqs_of = build_prereqs_of(concepts, prereq_edges)

    states = await concept_states_by_id(session, person_id)
    card_states = await card_states_for(session, person_id)
    concept_items = await items_by_concept(session, status="published")
    items_by_id: dict[str, Item] = {item.id: item for items in concept_items.values() for item in items}
    reviewed_item_ids = {c.item_id for c in card_states}

    focuses = await focuses_all(session)
    ancestors = await ancestor_ids(session, person_id)

    selected: list[SelectedItem] = []
    used_item_ids: set[str] = set()

    def add(item: Item) -> bool:
        if item.id in used_item_ids or len(selected) >= limit:
            return False
        used_item_ids.add(item.id)
        selected.append(SelectedItem(item=item, concept_id=item.concept_id))
        return True

    # 1. Overdue reviews, retrievability ascending (most forgotten first).
    overdue = [c for c in card_states if as_utc(c.due_at) <= now]
    overdue.sort(key=lambda c: retrievability(c.stability, as_utc(c.last_review_at) if c.last_review_at else None, now))
    for card in overdue:
        if len(selected) >= limit:
            break
        item = items_by_id.get(card.item_id)
        if item is not None:
            add(item)

    # 2. New items from unlocked, not-yet-mastered concepts, highest score first.
    def unlocked_and_open(concept: Concept) -> bool:
        return is_unlocked(states, concept.id, prereqs_of) and not is_mastered(states, concept)

    candidates = [c for c in concepts if unlocked_and_open(c)]

    def score(concept: Concept) -> float:
        p_known = p_known_for(states, concept.id)
        depth_weight = 1 + 0.25 * (max_depth - depths[concept.id])
        return (1 - p_known) * depth_weight * _focus_weight(focuses, ancestors, person_id, concept.id, now)

    candidates.sort(key=lambda c: (-score(c), c.id))

    for concept in candidates:
        if len(selected) >= limit:
            break
        for item in concept_items.get(concept.id, []):
            if item.id in reviewed_item_ids:
                continue
            if not add(item):
                break

    # 3. Co-review: for each concept represented so far with p_known < 0.5,
    # pull in up to two related, unlocked neighbours (weight >= 0.5).
    seed_concept_ids = list(dict.fromkeys(s.concept_id for s in selected))

    def neighbors_of(concept_id: str) -> list[tuple[str, float]]:
        found = []
        for edge in related_edges:
            if edge.weight < CO_REVIEW_MIN_WEIGHT:
                continue
            if edge.from_concept_id == concept_id and edge.to_concept_id in concepts_by_id:
                found.append((edge.to_concept_id, edge.weight))
            elif edge.to_concept_id == concept_id and edge.from_concept_id in concepts_by_id:
                found.append((edge.from_concept_id, edge.weight))
        found.sort(key=lambda pair: (-pair[1], pair[0]))
        return found

    for concept_id in seed_concept_ids:
        if len(selected) >= limit:
            break
        if p_known_for(states, concept_id) >= CO_REVIEW_THRESHOLD:
            continue
        contributed = 0
        for neighbor_id, _weight in neighbors_of(concept_id):
            if contributed >= CO_REVIEW_MAX_NEIGHBORS or len(selected) >= limit:
                break
            if neighbor_id not in concepts_by_id or not is_unlocked(states, neighbor_id, prereqs_of):
                continue
            neighbor_overdue = [
                (card, items_by_id[card.item_id])
                for card in card_states
                if as_utc(card.due_at) <= now
                and card.item_id not in used_item_ids
                and card.item_id in items_by_id
                and items_by_id[card.item_id].concept_id == neighbor_id
            ]
            neighbor_overdue.sort(
                key=lambda pair: retrievability(pair[0].stability, as_utc(pair[0].last_review_at) if pair[0].last_review_at else None, now)
            )
            picked = neighbor_overdue[0][1] if neighbor_overdue else None
            if picked is None:
                for item in concept_items.get(neighbor_id, []):
                    if item.id not in reviewed_item_ids and item.id not in used_item_ids:
                        picked = item
                        break
            if picked is not None and add(picked):
                contributed += 1

    if selected:
        return NextResult(items=selected, reason=None)

    all_mastered = all(is_mastered(states, c) for c in concepts)
    reason = "all_mastered" if all_mastered else "blocked_by_prerequisites"
    return NextResult(items=[], reason=reason)
