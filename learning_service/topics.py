"""`GET /topics`: learner-facing list of topics, filtered to the acting
person's own role when one is on record, else every topic (spec §Curriculum,
"topic" per role/persona). "no specialist role" has exactly one spelling —
an unset `role` — so there is no second value to fold into it here.

`all_roles=true` (KATA-7/W3) bypasses that filter for any caller, role or
not: the Connections screen (SCREENS.md #02) shows three persona topic
cards side by side on one signed-in learner's own screen — a cross-role
view of what ingestion produced for the whole team, not "my own topics" —
and topics carry no per-person data (mastery lives on `/me/concept-graph`,
unaffected by this param), so there's nothing to protect by keeping the
default, per-role behavior mandatory. Default (param omitted) is unchanged
byte-for-byte from before, so every existing caller and test keeps its
current behavior.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum_admin import _topic_out
from learning_service.db import get_session
from learning_service.identity.service import resolve_identity
from learning_service.logging_utils import log_unknown_identity
from learning_service.main import ActingIdentity, _error, acting_identity

router = APIRouter()


@router.get("/topics")
async def list_topics(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    session: AsyncSession = Depends(get_session),
    all_roles: bool = Query(False, description="Bypass the caller's own-role filter and return every topic."),
) -> dict[str, Any]:
    person = await resolve_identity(
        session, platform=identity.platform, external_id=identity.external_id, alt_id=identity.alt_id
    )
    if person is None:
        log_unknown_identity(
            path=request.url.path,
            platform=identity.platform,
            external_id=identity.external_id,
            alt_id=identity.alt_id,
        )
        raise _error(403, "unknown_identity", "no person matches this identity")

    # `None` means unfiltered: a person with no role on record (or an
    # explicit `all_roles=true`) sees every topic.
    persona_role = None if all_roles else person.role
    topics = await curriculum_service.list_topics(session, persona_role=persona_role)
    return {
        "topics": [
            _topic_out(topic, await curriculum_service.topic_concept_ids(session, topic.id)) for topic in topics
        ]
    }
