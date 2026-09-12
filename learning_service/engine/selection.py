"""Next-item selection (spec §Learning engine, "Next-item selection").

Order: overdue reviews (retrievability ascending) -> new items from unlocked
concepts (score = (1-p_known)*depth_weight*focus_weight, highest first) ->
co-review of up to two related concepts for any selected concept below the
0.5 mastery line.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from learning_service.engine.models import P_INIT, CardState, Concept, Item
from learning_service.engine.repository import InMemoryLearningRepository
from learning_service.engine.retrievability import retrievability

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


def p_known_for(repo: InMemoryLearningRepository, person_id: str, concept_id: str) -> float:
    state = repo.concept_state_for(person_id, concept_id)
    return state.p_known if state is not None else P_INIT


def is_mastered(repo: InMemoryLearningRepository, person_id: str, concept: Concept) -> bool:
    return p_known_for(repo, person_id, concept.id) >= concept.mastery_threshold


def _depths(concepts: list[Concept], prereq_edges: list) -> dict[str, int]:
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


def is_unlocked(
    repo: InMemoryLearningRepository, person_id: str, concept_id: str, prereqs_of: dict[str, list[Concept]]
) -> bool:
    for prereq in prereqs_of.get(concept_id, []):
        if not is_mastered(repo, person_id, prereq):
            return False
    return True


def build_prereqs_of(concepts: list[Concept], prereq_edges: list[ConceptEdge]) -> dict[str, list[Concept]]:
    concepts_by_id = {c.id: c for c in concepts}
    prereqs_of: dict[str, list[Concept]] = {c.id: [] for c in concepts}
    for edge in prereq_edges:
        if edge.to_concept_id in prereqs_of and edge.from_concept_id in concepts_by_id:
            prereqs_of[edge.to_concept_id].append(concepts_by_id[edge.from_concept_id])
    return prereqs_of


def _focus_weight(repo: InMemoryLearningRepository, person_id: str, concept_id: str, now: datetime) -> float:
    weight = 1.0
    for focus in repo.focuses_for(person_id):
        if focus.concept_id != concept_id:
            continue
        if focus.expires_at is not None and focus.expires_at <= now:
            continue
        weight *= focus.weight
    return weight


def _reviewed_item_ids(card_states: list[CardState]) -> set[str]:
    return {c.item_id for c in card_states}


def select_next_items(
    repo: InMemoryLearningRepository,
    person_id: str,
    now: datetime,
    limit: int = DEFAULT_LIMIT,
) -> NextResult:
    limit = max(1, min(limit, MAX_LIMIT))

    concepts = repo.list_concepts()
    concepts_by_id = {c.id: c for c in concepts}
    prereq_edges = repo.list_edges("prerequisite")
    related_edges = repo.list_edges("related")
    depths = _depths(concepts, prereq_edges)
    max_depth = max(depths.values(), default=0)

    prereqs_of = build_prereqs_of(concepts, prereq_edges)

    card_states = repo.card_states_for(person_id)
    reviewed_item_ids = _reviewed_item_ids(card_states)

    selected: list[SelectedItem] = []
    used_item_ids: set[str] = set()

    def add(item: Item) -> bool:
        if item.id in used_item_ids or len(selected) >= limit:
            return False
        used_item_ids.add(item.id)
        selected.append(SelectedItem(item=item, concept_id=item.concept_id))
        return True

    # 1. Overdue reviews, retrievability ascending (most forgotten first).
    overdue = [c for c in card_states if c.due_at <= now]
    overdue.sort(key=lambda c: retrievability(c.stability, c.last_review_at, now))
    for card in overdue:
        if len(selected) >= limit:
            break
        item = repo.get_item(card.item_id)
        if item is not None and item.status == "published":
            add(item)

    # 2. New items from unlocked, not-yet-mastered concepts, highest score first.
    def unlocked_and_open(concept: Concept) -> bool:
        return is_unlocked(repo, person_id, concept.id, prereqs_of) and not is_mastered(repo, person_id, concept)

    candidates = [c for c in concepts if unlocked_and_open(c)]

    def score(concept: Concept) -> float:
        p_known = p_known_for(repo, person_id, concept.id)
        depth_weight = 1 + 0.25 * (max_depth - depths[concept.id])
        return (1 - p_known) * depth_weight * _focus_weight(repo, person_id, concept.id, now)

    candidates.sort(key=lambda c: (-score(c), c.id))

    for concept in candidates:
        if len(selected) >= limit:
            break
        for item in repo.published_items(concept.id):
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
        if p_known_for(repo, person_id, concept_id) >= CO_REVIEW_THRESHOLD:
            continue
        contributed = 0
        for neighbor_id, _weight in neighbors_of(concept_id):
            if contributed >= CO_REVIEW_MAX_NEIGHBORS or len(selected) >= limit:
                break
            neighbor = concepts_by_id.get(neighbor_id)
            if neighbor is None or not is_unlocked(repo, person_id, neighbor_id, prereqs_of):
                continue
            neighbor_overdue = []
            for card in card_states:
                if card.due_at > now or card.item_id in used_item_ids:
                    continue
                neighbor_item = repo.get_item(card.item_id)
                if neighbor_item is not None and neighbor_item.concept_id == neighbor_id:
                    neighbor_overdue.append((card, neighbor_item))
            neighbor_overdue.sort(key=lambda pair: retrievability(pair[0].stability, pair[0].last_review_at, now))
            picked = neighbor_overdue[0][1] if neighbor_overdue else None
            if picked is None:
                for item in repo.published_items(neighbor_id):
                    if item.id not in reviewed_item_ids and item.id not in used_item_ids:
                        picked = item
                        break
            if picked is not None and add(picked):
                contributed += 1

    if selected:
        return NextResult(items=selected, reason=None)

    all_mastered = all(is_mastered(repo, person_id, c) for c in concepts)
    reason = "all_mastered" if all_mastered else "blocked_by_prerequisites"
    return NextResult(items=[], reason=reason)
