"""SQLAlchemy models for `review`, `card_state`, `concept_state`, `focus`
(spec §Learning engine → Tables; §Identity, roles, teams → Tables for
`focus`, kept here — see `engine/__init__.py`). Shares
`identity.models.Base` so a single `Base.metadata.create_all()` covers the
whole schema, same pattern as `curriculum.models`.

`review.result` stores the exact response body `POST /me/reviews` returned,
so a replayed `(person_id, idempotency_key)` idempotency hit returns
byte-identical output without recomputing grading or FSRS/BKT.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from learning_service.identity.models import Base

P_INIT = 0.20
ANSWER_RETENTION_DAYS = 90
NOTE_MAX_COUNT = 20
NOTE_MAX_CHARS = 500
# spec §Team analytics, "at risk": p_known < 0.5 and >= 1 overdue card.
AT_RISK_THRESHOLD = 0.5
DEFAULT_FOCUS_WEIGHT = 1.5

# Fields never shown to a learner before grading (spec §Curriculum, "Item
# payloads"; the "Learner-facing endpoints" paragraph). `correct_indices` is
# `msq`'s answer key, the plural counterpart of `mcq`'s `correct_index`.
ANSWER_KEY_FIELDS = {"correct_index", "correct_indices", "answer", "reference", "rubric", "explanation"}


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Review(Base):
    """Append-only (spec §Architecture, invariant 2): never updated or
    deleted except by the answer-retention job, which only touches `answer`.
    """

    __tablename__ = "review"
    __table_args__ = (UniqueConstraint("person_id", "idempotency_key", name="uq_review_person_idempotency_key"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    item_id: Mapped[str] = mapped_column(ForeignKey("item.id"))
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str]
    grade: Mapped[float]
    rating: Mapped[int]
    source: Mapped[str]
    idempotency_key: Mapped[str]
    asserted_by: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)
    # Contract v1.2.1 (row 1): stated confidence (1-5, before the reveal)
    # and whether the learner asked for the answer instead of answering.
    # Real columns, not folded into `result`, so bypass_rate/calibration/
    # retention read a column, not a JSON reach-in.
    confidence: Mapped[int | None] = mapped_column(Integer, default=None)
    bypassed: Mapped[bool] = mapped_column(Boolean, default=False)


class CardState(Base):
    """Derived (spec §Architecture, invariant 2): truncated and rebuilt by
    `POST /admin/replay`, never written except through `engine.replay`.
    """

    __tablename__ = "card_state"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("item.id"), primary_key=True)
    stability: Mapped[float]
    difficulty: Mapped[float]
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str]  # "learning" | "review" | "relearning" (py-fsrs State)
    step: Mapped[int | None] = mapped_column(Integer, default=None)
    reps: Mapped[int] = mapped_column(default=0)
    lapses: Mapped[int] = mapped_column(default=0)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ConceptState(Base):
    __tablename__ = "concept_state"

    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"), primary_key=True)
    p_known: Mapped[float] = mapped_column(default=P_INIT)
    reviews: Mapped[int] = mapped_column(default=0)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class Focus(Base):
    """A manager-set focus that tilts next-item selection (spec §Learning
    engine, "Next-item selection"; §API `POST /team/focus`). Unlike
    `concept_edge`, `focus.concept_id` does have an FK here: this package
    reads the concept catalog straight from the `concept` table (no second,
    unsynced copy), so the reference is always valid.
    """

    __tablename__ = "focus"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    scope_kind: Mapped[str]  # "subtree" | "person"
    scope_person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    weight: Mapped[float] = mapped_column(default=DEFAULT_FOCUS_WEIGHT)
    set_by: Mapped[str] = mapped_column(ForeignKey("person.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


def as_utc(value: datetime) -> datetime:
    """SQLite (tests) drops tzinfo on round-trip even for a
    `DateTime(timezone=True)` column; Postgres preserves it. Every value in
    this module is written in UTC, so a naive value read back is UTC too."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
