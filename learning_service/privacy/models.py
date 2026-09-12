"""SQLAlchemy models for `answer`, `learner_note`, `audit` (spec §Privacy
and retention → Tables, "Audit"). Shares `identity.models.Base`, same
pattern as `curriculum.models`/`engine.models`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from learning_service.identity.models import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Answer(Base):
    """Written only for `short_answer` (and, once it has a grader,
    `teach_back`) reviews. Read only by `/me/answers`, authenticated as the
    owning person; no analytics/manager/admin/digest query ever joins this
    table (spec §Privacy and retention)."""

    __tablename__ = "answer"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    review_id: Mapped[str] = mapped_column(ForeignKey("review.id"))
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LearnerNote(Base):
    """Tutoring-personalization notes, written/read only through `/me/notes*`
    (spec §Privacy and retention). No manager, admin, analytics, or digest
    query joins this table."""

    __tablename__ = "learner_note"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    text: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEntry(Base):
    """One row per `/team/*` request that passed the service token (spec
    §Privacy and retention, "Audit"), including `403 not_a_manager`/
    `outside_subtree`/`not_operator` — never for `401`, which is raised
    before any handler (and so before any actor is known) runs."""

    __tablename__ = "audit"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    actor_person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    subject_scope: Mapped[str]
    endpoint: Mapped[str]
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
