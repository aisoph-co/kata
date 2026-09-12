"""SQLAlchemy models for `course`, `concept`, `concept_edge`, `item` (spec
§Curriculum → Tables). Shares `identity.models.Base` so a single Alembic
chain and a single `Base.metadata.create_all()` cover the whole schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from learning_service.identity.models import Base

DEFAULT_MASTERY_THRESHOLD = 0.85


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Course(Base):
    __tablename__ = "course"
    __table_args__ = (UniqueConstraint("slug", name="uq_course_slug"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    # Contract v1.2.0 (spec §Curriculum, OPEN-QUESTIONS.md Q5): optional,
    # unique when set, so a loader can address a course by a stable handle
    # across re-runs the way `Concept.slug` already does.
    slug: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Concept(Base):
    __tablename__ = "concept"
    __table_args__ = (UniqueConstraint("course_id", "slug", name="uq_concept_course_slug"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.id"))
    slug: Mapped[str]
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    mastery_threshold: Mapped[float] = mapped_column(default=DEFAULT_MASTERY_THRESHOLD)


class ConceptEdge(Base):
    __tablename__ = "concept_edge"
    # Directed pairs are unique per kind. Related edges are normalized to
    # lowest-id-first at write time (spec §Curriculum), so this also prevents
    # storing the same undirected pair twice.
    __table_args__ = (
        UniqueConstraint("from_concept_id", "to_concept_id", "kind", name="uq_concept_edge_from_to_kind"),
    )

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    from_concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    to_concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    kind: Mapped[str]  # "prerequisite" | "related"
    weight: Mapped[float] = mapped_column(default=1.0)


class Item(Base):
    __tablename__ = "item"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    kind: Mapped[str]  # "mcq" | "msq" | "self_rated" | "short_answer" | "teach_back"
    prompt: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default="draft")  # "draft" | "published"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Topic(Base):
    """Contract v1.2.0 (spec §Curriculum, OPEN-QUESTIONS.md Q6, web-app-design.md
    Contract change #5): a named subgraph of a course's concepts — one per
    persona/role, e.g. "sca-exemption-change" for `pm`. `entry_concept_id` is
    where a learner with no history starts (the shallowest concept in the
    topic). Membership is `topic_concept`, below.
    """

    __tablename__ = "topic"
    __table_args__ = (UniqueConstraint("course_id", "slug", name="uq_topic_course_slug"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(ForeignKey("course.id"))
    slug: Mapped[str]
    title: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    persona_role: Mapped[str]
    entry_concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    # KAT-C1/C2 ("connect, don't list"): the source artifacts this topic was
    # derived from, each an identifier a human can follow — an issue key
    # (`PAY-1841`) or a repo path, optionally with a heading anchor
    # (`sprint-history.md#sprint-42--stop-double-charging`). Already asserted
    # real at seed-generation time by `docs/seed/verify_demo_beats.py`; this
    # column is what finally carries it out through the API, so Screen 2 can
    # show *why* a topic was chosen instead of asserting it was.
    grounded_in: Mapped[list] = mapped_column(JSON, default=list)


class TopicConcept(Base):
    __tablename__ = "topic_concept"

    topic_id: Mapped[str] = mapped_column(ForeignKey("topic.id"), primary_key=True)
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"), primary_key=True)
