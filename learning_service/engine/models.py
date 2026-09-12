"""Data shapes for the learning engine (spec §Curriculum, §Learning engine).

Minimal fields only — enough to drive next-item selection. Full persistence
(Postgres tables, Epic A/C/E) is out of scope for US-B1; these are plain
dataclasses so the selection logic in `selection.py` has no database
dependency and is unit-testable on its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

_EPOCH = datetime.min.replace(tzinfo=timezone.utc)

P_INIT = 0.20
DEFAULT_MASTERY_THRESHOLD = 0.85
ANSWER_RETENTION_DAYS = 90
NOTE_MAX_COUNT = 20
NOTE_MAX_CHARS = 500
# spec §Team analytics, "at risk": p_known < 0.5 and >= 1 overdue card.
AT_RISK_THRESHOLD = 0.5

# Fields never shown to a learner before grading (spec §Curriculum, "Item
# payloads" + the "Learner-facing endpoints" paragraph). `correct_indices` is
# `msq`'s answer key (v1.1.0, PR #26 on AGCTM-10), the plural counterpart of
# `mcq`'s `correct_index`.
ANSWER_KEY_FIELDS = {"correct_index", "correct_indices", "answer", "reference", "rubric", "explanation"}


@dataclass(frozen=True)
class Concept:
    id: str
    course_id: str
    slug: str
    title: str
    mastery_threshold: float = DEFAULT_MASTERY_THRESHOLD


@dataclass(frozen=True)
class ConceptEdge:
    from_concept_id: str
    to_concept_id: str
    kind: str  # "prerequisite" | "related"
    weight: float = 1.0


@dataclass(frozen=True)
class Item:
    id: str
    concept_id: str
    kind: str  # "mcq" | "msq" | "self_rated" | "short_answer" | "teach_back"
    prompt: str
    payload: dict = field(default_factory=dict)
    # PLAN_05 PR-B: matches `curriculum.models.Item.status`'s default — the
    # curriculum table is the truth for status (only `published` items are
    # selectable), so an item constructed without an explicit status should
    # default to invisible, same as `POST /admin/items` does, not visible.
    status: str = "draft"
    created_at: datetime = _EPOCH

    def stripped_payload(self) -> dict:
        return {k: v for k, v in self.payload.items() if k not in ANSWER_KEY_FIELDS}


@dataclass(frozen=True)
class CardState:
    person_id: str
    item_id: str
    stability: float
    difficulty: float
    due_at: datetime
    state: str = "review"  # "learning" | "review" | "relearning" (py-fsrs State)
    step: int | None = None  # py-fsrs learning/relearning step; None once in "review"
    reps: int = 0
    lapses: int = 0
    last_review_at: datetime | None = None


@dataclass(frozen=True)
class ConceptState:
    person_id: str
    concept_id: str
    p_known: float = P_INIT
    reviews: int = 0
    last_review_at: datetime | None = None


@dataclass(frozen=True)
class Answer:
    id: str
    review_id: str
    person_id: str
    text: str
    created_at: datetime


@dataclass(frozen=True)
class LearnerNote:
    id: str
    person_id: str
    text: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Focus:
    id: str
    scope_kind: str  # "subtree" | "person"
    scope_person_id: str
    concept_id: str
    weight: float = 1.5
    expires_at: datetime | None = None
