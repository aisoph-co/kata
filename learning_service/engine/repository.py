"""In-memory curriculum/engine store, and the `LearningRepository` protocol
it implements (PLAN_05 PR-B).

`select_next_items`, `apply_review`, and `team/service.py`'s analytics
helpers only call methods on this surface, so `SqlLearningRepository`
(`engine/sql_repository.py`) can stand in for it without touching that
logic: it subclasses this class, hydrates the same in-memory dicts from
Postgres at the start of a request (`load()`), and durably persists the
handful of writes that must survive a restart or resolve a concurrent
duplicate (`commit_review()`, `replay()`) — everything else (reads, and
writes like `add_note`/`add_answer` that only need to be visible for the
rest of the same request) is the same dict mutation as today, inherited
unchanged.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from learning_service.engine.models import (
    Answer,
    CardState,
    Concept,
    ConceptEdge,
    ConceptState,
    Focus,
    Item,
    LearnerNote,
)


class LearningRepository(Protocol):
    """Today's `InMemoryLearningRepository` method surface, as a protocol.

    Obtaining an instance is async (`main.get_repository`, possibly
    hydrating from Postgres); the methods below are not — see the module
    docstring for why. `SqlLearningRepository` adds a few durable-write
    methods (`load`, `commit_review`, `replay`) outside this surface for
    the callers that need them.
    """

    def add_concept(self, concept: Concept) -> None: ...
    def add_edge(self, edge: ConceptEdge) -> None: ...
    def add_item(self, item: Item) -> None: ...
    def add_card_state(self, card_state: CardState) -> None: ...
    def add_concept_state(self, concept_state: ConceptState) -> None: ...
    def add_focus(self, focus: Focus) -> None: ...
    def list_concepts(self) -> list[Concept]: ...
    def get_concept(self, concept_id: str) -> Concept | None: ...
    def list_edges(self, kind: str) -> list[ConceptEdge]: ...
    def published_items(self, concept_id: str) -> list[Item]: ...
    def get_item(self, item_id: str) -> Item | None: ...
    def card_states_for(self, person_id: str) -> list[CardState]: ...
    def concept_state_for(self, person_id: str, concept_id: str) -> ConceptState | None: ...
    def focuses_for(self, person_id: str) -> list[Focus]: ...
    def find_review(self, person_id: str, idempotency_key: str) -> dict[str, Any] | None: ...
    def reviews_for(self, person_id: str) -> list[dict[str, Any]]: ...
    def append_review(self, review: dict[str, Any]) -> None: ...
    def add_answer(self, answer: Answer) -> None: ...
    def answers_for(self, person_id: str) -> list[Answer]: ...
    def delete_answers_for(self, person_id: str) -> int: ...
    def purge_answers_older_than(self, cutoff: datetime) -> int: ...
    def add_note(self, note: LearnerNote) -> None: ...
    def notes_for(self, person_id: str) -> list[LearnerNote]: ...
    def get_note(self, person_id: str, note_id: str) -> LearnerNote | None: ...
    def delete_note(self, person_id: str, note_id: str) -> bool: ...
    def delete_notes_for(self, person_id: str) -> int: ...


class InMemoryLearningRepository:
    def __init__(self) -> None:
        self.concepts: dict[str, Concept] = {}
        self.concept_edges: list[ConceptEdge] = []
        self.items: dict[str, Item] = {}
        self.card_states: dict[tuple[str, str], CardState] = {}
        self.concept_states: dict[tuple[str, str], ConceptState] = {}
        self.focuses: list[Focus] = []
        # Append-only `review` log (spec §Learning engine): the source of
        # truth `card_state`/`concept_state` are derived from. `_review_by_key`
        # is a rebuildable index over it for the `(person_id, idempotency_key)`
        # uniqueness check — it is not itself state.
        self.reviews: list[dict[str, Any]] = []
        self._review_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        # spec §Privacy and retention: `answer(id, review_id, person_id, text,
        # created_at)`, learner-owned and 90-day retained (see `answers.py`).
        self.answers: list[Answer] = []
        # spec §Privacy and retention: `learner_note(id, person_id, text,
        # created_at, updated_at)`, learner-owned tutoring personalization
        # (see `notes.py`). Capped at 20/person, 500 chars each; no retention
        # window since the learner can delete at will.
        self.notes: list[LearnerNote] = []

    def add_concept(self, concept: Concept) -> None:
        self.concepts[concept.id] = concept

    def add_edge(self, edge: ConceptEdge) -> None:
        self.concept_edges.append(edge)

    def add_item(self, item: Item) -> None:
        self.items[item.id] = item

    def add_card_state(self, card_state: CardState) -> None:
        self.card_states[(card_state.person_id, card_state.item_id)] = card_state

    def add_concept_state(self, concept_state: ConceptState) -> None:
        self.concept_states[(concept_state.person_id, concept_state.concept_id)] = concept_state

    def add_focus(self, focus: Focus) -> None:
        self.focuses.append(focus)

    def list_concepts(self) -> list[Concept]:
        return list(self.concepts.values())

    def get_concept(self, concept_id: str) -> Concept | None:
        return self.concepts.get(concept_id)

    def list_edges(self, kind: str) -> list[ConceptEdge]:
        return [e for e in self.concept_edges if e.kind == kind]

    def published_items(self, concept_id: str) -> list[Item]:
        items = [i for i in self.items.values() if i.concept_id == concept_id and i.status == "published"]
        return sorted(items, key=lambda i: (i.created_at, i.id))

    def get_item(self, item_id: str) -> Item | None:
        return self.items.get(item_id)

    def card_states_for(self, person_id: str) -> list[CardState]:
        return [c for c in self.card_states.values() if c.person_id == person_id]

    def concept_state_for(self, person_id: str, concept_id: str) -> ConceptState | None:
        return self.concept_states.get((person_id, concept_id))

    def focuses_for(self, person_id: str) -> list[Focus]:
        return [f for f in self.focuses if f.scope_person_id == person_id]

    def find_review(self, person_id: str, idempotency_key: str) -> dict[str, Any] | None:
        return self._review_by_key.get((person_id, idempotency_key))

    def reviews_for(self, person_id: str) -> list[dict[str, Any]]:
        return [r for r in self.reviews if r["person_id"] == person_id]

    def all_reviews(self) -> list[dict[str, Any]]:
        return list(self.reviews)

    def clear_derived_state(self) -> None:
        self.card_states.clear()
        self.concept_states.clear()

    def add_answer(self, answer: Answer) -> None:
        self.answers.append(answer)

    def answers_for(self, person_id: str) -> list[Answer]:
        return [a for a in self.answers if a.person_id == person_id]

    def delete_answers_for(self, person_id: str) -> int:
        remaining = [a for a in self.answers if a.person_id != person_id]
        deleted = len(self.answers) - len(remaining)
        self.answers = remaining
        return deleted

    def purge_answers_older_than(self, cutoff: datetime) -> int:
        remaining = [a for a in self.answers if a.created_at > cutoff]
        purged = len(self.answers) - len(remaining)
        self.answers = remaining
        return purged

    def add_note(self, note: LearnerNote) -> None:
        self.notes.append(note)

    def notes_for(self, person_id: str) -> list[LearnerNote]:
        return [n for n in self.notes if n.person_id == person_id]

    def get_note(self, person_id: str, note_id: str) -> LearnerNote | None:
        for note in self.notes:
            if note.person_id == person_id and note.id == note_id:
                return note
        return None

    def delete_note(self, person_id: str, note_id: str) -> bool:
        note = self.get_note(person_id, note_id)
        if note is None:
            return False
        self.notes.remove(note)
        return True

    def delete_notes_for(self, person_id: str) -> int:
        remaining = [n for n in self.notes if n.person_id != person_id]
        deleted = len(self.notes) - len(remaining)
        self.notes = remaining
        return deleted

    def append_review(self, review: dict[str, Any]) -> None:
        # `id` is the `(person_id, reviewed_at, id)` replay-order tiebreaker
        # (spec §Learning engine, "Replay"); a caller loading historical rows
        # (the golden fixture) supplies its own, a live submission gets the
        # log's insertion sequence.
        review.setdefault("id", len(self.reviews))
        self.reviews.append(review)
        self._review_by_key[(review["person_id"], review["idempotency_key"])] = review
