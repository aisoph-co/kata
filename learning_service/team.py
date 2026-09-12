"""`/team/*` (spec §Team analytics, §Privacy and retention, §API):
manager-facing analytics over the acting person's subtree.

Every route below resolves the acting identity to a `Person`, requires that
person to have at least one direct report (`403 not_a_manager` otherwise —
spec: "403 if the acting person has no reports"), and writes an `audit` row
for every request that reaches that point, success or 403 alike — including
`GET /team/audit`'s own `403 not_operator` — never for `401`, which
`acting_identity` raises before any handler here runs (spec §Privacy and
retention, "Audit").
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.analytics import service as analytics_service
from learning_service.curriculum import service as curriculum_service
from learning_service.db import get_session
from learning_service.engine.models import DEFAULT_FOCUS_WEIGHT, Focus
from learning_service.engine.selection import (
    build_prereqs_of,
    card_states_for,
    concept_states_by_id,
    due_count_for_concept,
    is_mastered,
    is_unlocked,
    items_by_concept,
    p_known_for,
)
from learning_service.identity.models import Person
from learning_service.identity.service import resolve_identity
from learning_service.logging_utils import log_unknown_identity
from learning_service.main import ActingIdentity, _error, acting_identity
from learning_service.privacy import service as privacy_service
from learning_service.roster.service import get_subtree_ids

router = APIRouter()

MIN_DIGEST_DAYS = 1
MAX_DIGEST_DAYS = 90


@dataclass(frozen=True)
class ManagerContext:
    person: Person
    subtree_ids: list[str]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def require_manager(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    session: AsyncSession = Depends(get_session),
) -> ManagerContext:
    person = await resolve_identity(
        session, platform=identity.platform, external_id=identity.external_id, alt_id=identity.alt_id
    )
    if person is None:
        log_unknown_identity(
            path=request.url.path, platform=identity.platform, external_id=identity.external_id, alt_id=identity.alt_id
        )
        raise _error(403, "unknown_identity", "no person matches this identity")

    subtree_ids = await get_subtree_ids(session, person.id)
    if not subtree_ids:
        await privacy_service.write_audit(session, actor_person_id=person.id, subject_scope="n/a", endpoint=request.url.path)
        raise _error(403, "not_a_manager", "acting person has no reports")
    return ManagerContext(person=person, subtree_ids=subtree_ids)


async def require_operator_manager(
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> ManagerContext:
    if not ctx.person.is_operator:
        await privacy_service.write_audit(session, actor_person_id=ctx.person.id, subject_scope="n/a", endpoint=request.url.path)
        raise _error(403, "not_operator", "operator access required")
    return ctx


@router.get("/team/overview")
async def team_overview(
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = _now()
    concepts = await curriculum_service.list_concepts(session)
    concept_items = await items_by_concept(session, status="published")
    items_by_id = {item.id: item for items in concept_items.values() for item in items}
    concept_summaries = [
        await analytics_service.concept_summary(session, c, ctx.subtree_ids, items_by_id, now) for c in concepts
    ]
    people_summaries = []
    for pid in ctx.subtree_ids:
        summary = await analytics_service.person_summary(session, pid, concepts, now, analytics_service.DEFAULT_DIGEST_DAYS)
        people_summaries.append(
            {
                "person_id": pid,
                "adherence": summary["adherence"],
                "velocity": summary["velocity"],
                "last_active": summary["last_active"],
                "bypass_rate": summary["bypass_rate"],
            }
        )

    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {
        "concepts": concept_summaries,
        "people": people_summaries,
        # Pooled over the acting manager's own reviews plus their subtree
        # (unlike `people` above, which excludes the caller — a manager is
        # also a practitioner). Concept-level aggregate only.
        "retention": await analytics_service.team_retention(session, [ctx.person.id, *ctx.subtree_ids]),
    }


@router.get("/team/concepts/{concept_id}")
async def team_concept_detail(
    concept_id: str,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    concept = await curriculum_service.get_concept(session, concept_id)
    people = []
    if concept is not None:
        for pid in ctx.subtree_ids:
            states = await concept_states_by_id(session, pid)
            people.append({"person_id": pid, "p_known": p_known_for(states, concept_id), "mastered": is_mastered(states, concept)})

    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"concept:{concept_id}", endpoint=request.url.path
    )
    return {"concept_id": concept_id, "people": people}


@router.get("/team/people/{person_id}")
async def team_person_detail(
    person_id: str,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if person_id not in ctx.subtree_ids:
        await privacy_service.write_audit(
            session, actor_person_id=ctx.person.id, subject_scope=f"person:{person_id}", endpoint=request.url.path
        )
        raise _error(403, "outside_subtree", "subject is not in the caller's subtree")

    now = _now()
    concepts = await curriculum_service.list_concepts(session)
    prereqs_of = build_prereqs_of(concepts, await curriculum_service.list_edges(session, kind="prerequisite"))
    concept_items = await items_by_concept(session, status="published")

    states = await concept_states_by_id(session, person_id)
    card_states = await card_states_for(session, person_id)
    items_by_id = {item.id: item for items in concept_items.values() for item in items}
    concept_entries = [
        {
            "concept_id": c.id,
            "p_known": p_known_for(states, c.id),
            "mastered": is_mastered(states, c),
            "due_count": due_count_for_concept(card_states, items_by_id, c.id, now),
            "unlocked": is_unlocked(states, c.id, prereqs_of),
        }
        for c in concepts
    ]
    summary = await analytics_service.person_summary(session, person_id, concepts, now, analytics_service.DEFAULT_DIGEST_DAYS)
    due_count = await analytics_service.due_count_for_person(session, person_id, concepts, prereqs_of, concept_items, now)

    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"person:{person_id}", endpoint=request.url.path
    )
    return {
        "person_id": person_id,
        "concepts": concept_entries,
        "adherence": summary["adherence"],
        "velocity": summary["velocity"],
        "due_count": due_count,
        "last_active": summary["last_active"],
        "bypass_rate": summary["bypass_rate"],
        "retention": summary["retention"],
        "calibration": summary["calibration"],
    }


@router.get("/team/recommendations")
async def team_recommendations(
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    recommendations = await analytics_service.build_recommendations(session, ctx.subtree_ids)
    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {"recommendations": recommendations}


@router.get("/team/digest")
async def team_digest(
    request: Request,
    days: int = Query(default=analytics_service.DEFAULT_DIGEST_DAYS, ge=MIN_DIGEST_DAYS, le=MAX_DIGEST_DAYS),
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    now = _now()
    period_start = now - timedelta(days=days)
    concepts = await curriculum_service.list_concepts(session)
    concept_items = await items_by_concept(session, status="published")
    items_by_id = {item.id: item for items in concept_items.values() for item in items}
    concept_summaries = [
        await analytics_service.concept_summary(session, c, ctx.subtree_ids, items_by_id, now) for c in concepts
    ]

    at_risk = []
    for c in concepts:
        for pid in ctx.subtree_ids:
            states = await concept_states_by_id(session, pid)
            card_states = await card_states_for(session, pid)
            if analytics_service.is_at_risk(states, card_states, items_by_id, c.id, now):
                at_risk.append({"person_id": pid, "concept_id": c.id})

    recommendations = await analytics_service.build_recommendations(session, ctx.subtree_ids)

    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {
        "subtree_root_id": ctx.person.id,
        "period_start": period_start,
        "period_end": now,
        "concepts": concept_summaries,
        "at_risk": at_risk,
        "recommendations": recommendations,
    }


class FocusCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope_kind: str
    scope_person_id: str
    concept_id: str
    weight: float = Field(default=DEFAULT_FOCUS_WEIGHT, gt=0)
    expires_at: datetime | None = None


@router.post("/team/focus")
async def create_team_focus(
    body: FocusCreateRequest,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    if body.scope_kind not in ("subtree", "person"):
        raise _error(422, "validation_error", "scope_kind must be 'subtree' or 'person'")
    if await curriculum_service.get_concept(session, body.concept_id) is None:
        raise _error(422, "validation_error", f"unknown concept_id {body.concept_id!r}")

    # spec §Identity, roles, teams, "Rules": "subtree of a person" = that
    # person plus all transitive reports, so a manager may root a `subtree`
    # focus at themself to cover their whole team — unlike reads, which
    # deliberately exclude the caller.
    allowed_scope_ids = {ctx.person.id, *ctx.subtree_ids}
    if body.scope_person_id not in allowed_scope_ids:
        await privacy_service.write_audit(
            session, actor_person_id=ctx.person.id, subject_scope=f"person:{body.scope_person_id}", endpoint=request.url.path
        )
        raise _error(403, "outside_subtree", "scope_person_id is not in the caller's subtree")

    focus = await analytics_service.create_focus(
        session,
        scope_kind=body.scope_kind,
        scope_person_id=body.scope_person_id,
        concept_id=body.concept_id,
        weight=body.weight,
        expires_at=body.expires_at,
        set_by=ctx.person.id,
    )

    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"{body.scope_kind}:{body.scope_person_id}", endpoint=request.url.path
    )
    return {
        "id": focus.id,
        "scope_kind": focus.scope_kind,
        "scope_person_id": focus.scope_person_id,
        "concept_id": focus.concept_id,
        "set_by": focus.set_by,
        "weight": focus.weight,
        "expires_at": focus.expires_at,
        "created_at": focus.created_at,
    }


@router.delete("/team/focus/{id}", status_code=204)
async def delete_team_focus(
    id: str,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(select(Focus).where(Focus.id == id))
    focus = result.scalar_one_or_none()
    if focus is None:
        raise _error(404, "not_found", "focus not found")

    owns_scope = focus.scope_person_id == ctx.person.id or focus.scope_person_id in ctx.subtree_ids
    if focus.set_by != ctx.person.id and not owns_scope:
        await privacy_service.write_audit(session, actor_person_id=ctx.person.id, subject_scope=f"focus:{id}", endpoint=request.url.path)
        raise _error(403, "outside_subtree", "caller neither set this focus nor owns its scope")

    await analytics_service.delete_focus(session, id)
    await privacy_service.write_audit(session, actor_person_id=ctx.person.id, subject_scope=f"focus:{id}", endpoint=request.url.path)


@router.get("/team/audit")
async def team_audit(
    request: Request,
    ctx: ManagerContext = Depends(require_operator_manager),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    entries = await privacy_service.list_audit_for(session, [ctx.person.id, *ctx.subtree_ids])
    await privacy_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {
        "entries": [
            {"id": e.id, "actor_person_id": e.actor_person_id, "subject_scope": e.subject_scope, "endpoint": e.endpoint, "at": e.at}
            for e in entries
        ]
    }
