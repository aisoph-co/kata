"""Identity resolution (spec §Identity, roles, teams → Rules): exact
`(platform, external_id)` match, then `(platform, alt_id)`; otherwise unknown.
A person is never created here — this only looks up.

Also covers US-A2 linking: `mint_link_code` issues a one-time, 15-minute
code for an already-resolved person; `consume_link_code` redeems it once
to attach a new platform identity to that person.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.identity.models import Identity, LinkCode, Person

LINK_CODE_TTL = timedelta(minutes=15)


class LinkCodeInvalid(Exception):
    """The code is unknown, expired, or already used."""


class IdentityAlreadyLinked(Exception):
    """The (platform, external_id) pair is already linked to a person."""


async def resolve_identity(
    session: AsyncSession, *, platform: str, external_id: str, alt_id: str | None = None
) -> Person | None:
    exact = await session.execute(
        select(Person)
        .join(Identity, Identity.person_id == Person.id)
        .where(Identity.platform == platform, Identity.external_id == external_id)
    )
    person = exact.scalar_one_or_none()
    if person is not None or not alt_id:
        return person

    via_alt = await session.execute(
        select(Person)
        .join(Identity, Identity.person_id == Person.id)
        .where(Identity.platform == platform, Identity.alt_id == alt_id)
    )
    return via_alt.scalar_one_or_none()


async def mint_link_code(session: AsyncSession, *, person_id: str) -> LinkCode:
    link_code = LinkCode(
        code=secrets.token_urlsafe(16),
        person_id=person_id,
        expires_at=datetime.now(timezone.utc) + LINK_CODE_TTL,
    )
    session.add(link_code)
    await session.commit()
    return link_code


def _as_utc(dt: datetime) -> datetime:
    # SQLite (used in tests) drops tzinfo on round-trip even for a
    # `DateTime(timezone=True)` column; Postgres preserves it. Values in this
    # table are always written in UTC, so a naive value is UTC too.
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def consume_link_code(
    session: AsyncSession, *, code: str, platform: str, external_id: str, alt_id: str | None = None
) -> Identity:
    result = await session.execute(select(LinkCode).where(LinkCode.code == code))
    link_code = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if link_code is None or link_code.used_at is not None or _as_utc(link_code.expires_at) < now:
        raise LinkCodeInvalid(code)

    existing = await session.execute(
        select(Identity).where(Identity.platform == platform, Identity.external_id == external_id)
    )
    if existing.scalar_one_or_none() is not None:
        raise IdentityAlreadyLinked(f"{platform}:{external_id}")

    link_code.used_at = now
    identity = Identity(person_id=link_code.person_id, platform=platform, external_id=external_id, alt_id=alt_id)
    session.add(identity)
    await session.commit()
    return identity
