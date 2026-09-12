"""SQLAlchemy model for `focus` (spec §Identity, roles, teams → Tables,
"Focus"). `concept_id` references `curriculum.models.Concept` by table name
only, the same cross-package pattern `curriculum.models` itself is not
subject to, so this module never needs to import `curriculum`.

Read and applied by the `engine` package's `GET /me/next` scoring; managed
through `POST`/`DELETE /team/focus` once the `api` package lands them. This
package owns only the table and, later, its own CRUD.
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


class Focus(Base):
    __tablename__ = "focus"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    scope_kind: Mapped[str]  # "subtree" | "person"
    scope_person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    concept_id: Mapped[str] = mapped_column(ForeignKey("concept.id"))
    set_by: Mapped[str] = mapped_column(ForeignKey("person.id"))
    weight: Mapped[float] = mapped_column(default=1.5)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
