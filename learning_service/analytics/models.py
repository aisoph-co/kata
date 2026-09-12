"""SQLAlchemy model for `audit` (spec §Privacy and retention → "Audit").
Shares `identity.models.Base` so a single Alembic chain covers the whole
schema. `focus` lives in `roster.models.Focus` (migration 0004) — this
package only owns the audit log and the team-analytics computation that
reads it.
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


class AuditEntry(Base):
    """One row per `/team/*` request that passed the service token (spec
    §Privacy and retention, "Audit"), including `403 not_a_manager` /
    `not_operator` / `outside_subtree` — never for `401`.
    """

    __tablename__ = "audit"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    actor_person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    subject_scope: Mapped[str]
    endpoint: Mapped[str]
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
