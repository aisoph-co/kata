"""SQLAlchemy models for `review`, `card_state`, `concept_state`, `answer`,
`learner_note` (PLAN_05 PR-B, migration 0005): the engine's derived and
append-only state, persisted so it survives a restart. Shares
`identity.models.Base` so a single Alembic chain and a single
`Base.metadata.create_all()` cover the whole schema (see `curriculum.models`,
`team.models` for the same pattern).

`review.result` stores the exact response body `POST /me/reviews` returned
(spec §Learning engine), so an idempotent replay of the same
`(person_id, idempotency_key)` returns byte-identical output without
recomputing grading or FSRS/BKT (see `engine/sql_repository.py`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from learning_service.identity.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewRow(Base):
    __tablename__ = "review"
    __table_args__ = (UniqueConstraint("person_id", "idempotency_key", name="uq_review_person_idempotency_key"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[str]
    item_id: Mapped[str]
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    kind: Mapped[str]
    grade: Mapped[float]
    rating: Mapped[int]
    source: Mapped[str]
    idempotency_key: Mapped[str]
    asserted_by: Mapped[str]
    result: Mapped[dict] = mapped_column(JSON)
    # Contract v1.2.0 (web-app-design.md Contract change #1): stated
    # confidence (1-5, before the reveal) and whether the learner asked for
    # the answer instead of answering. Real columns, not folded into
    # `result`, so bypass_rate/calibration/retention can be computed with a
    # column read rather than a JSON reach-in.
    confidence: Mapped[int | None] = mapped_column(Integer, default=None)
    bypassed: Mapped[bool] = mapped_column(Boolean, default=False)
    # PLAN_08 (`GET /me/history`, migration 0008): written at review time
    # (`reviews.py`) and backfilled by `POST /admin/replay`/seed
    # (`engine/replay.py:rebuild_derived_state`) — never recomputed on read.
    # Nullable so a legacy row from before this column existed reads as
    # `null` until the next replay backfills it.
    concept_id: Mapped[str | None] = mapped_column(default=None)
    p_known_after: Mapped[float | None] = mapped_column(default=None)


class CardStateRow(Base):
    __tablename__ = "card_state"

    person_id: Mapped[str] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(primary_key=True)
    stability: Mapped[float]
    difficulty: Mapped[float]
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str]
    step: Mapped[int | None] = mapped_column(Integer, default=None)
    reps: Mapped[int] = mapped_column(default=0)
    lapses: Mapped[int] = mapped_column(default=0)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class ConceptStateRow(Base):
    __tablename__ = "concept_state"

    person_id: Mapped[str] = mapped_column(primary_key=True)
    concept_id: Mapped[str] = mapped_column(primary_key=True)
    p_known: Mapped[float]
    reviews: Mapped[int] = mapped_column(default=0)
    last_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)


class AnswerRow(Base):
    __tablename__ = "answer"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    review_id: Mapped[str]
    person_id: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LearnerNoteRow(Base):
    __tablename__ = "learner_note"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[str]
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
