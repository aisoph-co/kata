"""SQLAlchemy models for `person` and `identity` (spec §Identity, roles, teams
→ Tables). `link_code` and `focus` are US-A2 and later.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Person(Base):
    __tablename__ = "person"

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    display_name: Mapped[str]
    email: Mapped[str] = mapped_column(unique=True)
    is_operator: Mapped[bool] = mapped_column(default=False)
    manager_id: Mapped[str | None] = mapped_column(ForeignKey("person.id"), default=None)
    # Contract v1.2.0: tech_lead | senior_swe | junior_swe | pm | uxd,
    # set at roster-import time (spec §Identity, roles, teams; web-app-design.md
    # Contract change #8). Not DB-enforced as an enum so a new role never
    # needs a migration.
    role: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    identities: Mapped[list["Identity"]] = relationship(back_populates="person")


class Identity(Base):
    __tablename__ = "identity"
    __table_args__ = (UniqueConstraint("platform", "external_id", name="uq_identity_platform_external_id"),)

    id: Mapped[str] = mapped_column(primary_key=True, default=_uuid)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    platform: Mapped[str]
    external_id: Mapped[str]
    alt_id: Mapped[str | None] = mapped_column(default=None)
    is_primary: Mapped[bool] = mapped_column(default=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    person: Mapped["Person"] = relationship(back_populates="identities")


class LinkCode(Base):
    __tablename__ = "link_code"

    code: Mapped[str] = mapped_column(primary_key=True)
    person_id: Mapped[str] = mapped_column(ForeignKey("person.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
