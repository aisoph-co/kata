"""`/team/*` (spec §Team analytics, §Privacy and retention, §API):
manager-facing analytics over the acting person's subtree.

Every route below resolves the acting identity to a `Person`, requires that
person to have at least one direct report (`403 not_a_manager` otherwise —
spec: "403 if the acting person has no reports"), and writes an `audit` row
for every request that reaches that point, success or 403 alike — including
`GET /team/audit`'s own `403 not_operator` — never for `401`, which
`acting_identity` raises before any of this runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.analytics import service as team_service
from learning_service.analytics.schemas import (
    AuditResponse,
    FocusCreateRequest,
    FocusOut,
    RecommendationsResponse,
    TeamConceptDetailResponse,
    TeamDigestResponse,
    TeamOverviewResponse,
    TeamPersonDetailResponse,
)
from learning_service.db import get_session
from learning_service.engine.repository import LearningRepository
from learning_service.engine.selection import build_prereqs_of, is_mastered, is_unlocked, p_known_for
from learning_service.identity.models import Person
from learning_service.identity.service import resolve_identity
from learning_service.logging_utils import log_unknown_identity
from learning_service.main import ActingIdentity, _error, acting_identity, get_repository
from learning_service.roster.models import Focus as DbFocus
from learning_service.roster.service import get_subtree_ids

router = APIRouter()

MIN_DIGEST_DAYS = 1
MAX_DIGEST_DAYS = 90


@dataclass(frozen=True)
class ManagerContext:
    person: Person
    subtree_ids: list[str]


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
            path=request.url.path,
            platform=identity.platform,
            external_id=identity.external_id,
            alt_id=identity.alt_id,
        )
        raise _error(403, "unknown_identity", "no person matches this identity")

    # `roster.service.get_subtree_ids` (spec §Identity, roles, teams →
    # Rules, "Subtree") includes `person.id` itself in the result — this
    # package's own "subtree" everywhere below (the manager's *reports*,
    # excluding the caller, per the "9 reportees" AC) is that result with
    # the caller's own id filtered back out.
    subtree_ids = [pid for pid in await get_subtree_ids(session, person.id) if pid != person.id]
    if not subtree_ids:
        await team_service.write_audit(
            session, actor_person_id=person.id, subject_scope="n/a", endpoint=request.url.path
        )
        raise _error(403, "not_a_manager", "acting person has no reports")
    return ManagerContext(person=person, subtree_ids=subtree_ids)


async def require_operator_manager(
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> ManagerContext:
    if not ctx.person.is_operator:
        await team_service.write_audit(
            session, actor_person_id=ctx.person.id, subject_scope="n/a", endpoint=request.url.path
        )
        raise _error(403, "not_operator", "operator access required")
    return ctx


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("/team/overview", response_model=TeamOverviewResponse)
async def team_overview(
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    now = _now()
    concepts = repo.list_concepts()
    concept_summaries = [team_service.concept_summary(repo, c, ctx.subtree_ids, now) for c in concepts]
    people_summaries = [
        {
            "person_id": pid,
            **{
                k: v
                for k, v in team_service.person_summary(
                    repo, pid, concepts, now, team_service.DEFAULT_DIGEST_DAYS
                ).items()
                if k in ("adherence", "velocity", "last_active", "bypass_rate")
            },
        }
        for pid in ctx.subtree_ids
    ]
    await team_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {
        "concepts": concept_summaries,
        "people": people_summaries,
        # Retention pooled over the acting manager's own reviews plus their
        # subtree (unlike `people` above, which excludes the caller — a
        # manager is also a practitioner). Concept-level aggregate only.
        "retention": team_service.team_retention(repo, [ctx.person.id, *ctx.subtree_ids]),
    }


@router.get("/team/concepts/{concept_id}", response_model=TeamConceptDetailResponse)
async def team_concept_detail(
    concept_id: str,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    concept = repo.get_concept(concept_id)
    people = []
    if concept is not None:
        for pid in ctx.subtree_ids:
            people.append(
                {
                    "person_id": pid,
                    "p_known": p_known_for(repo, pid, concept_id),
                    "mastered": is_mastered(repo, pid, concept),
                }
            )
    await team_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"concept:{concept_id}", endpoint=request.url.path
    )
    return {"concept_id": concept_id, "people": people}


@router.get("/team/people/{person_id}", response_model=TeamPersonDetailResponse)
async def team_person_detail(
    person_id: str,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    if person_id not in ctx.subtree_ids:
        await team_service.write_audit(
            session,
            actor_person_id=ctx.person.id,
            subject_scope=f"person:{person_id}",
            endpoint=request.url.path,
        )
        raise _error(403, "outside_subtree", "subject is not in the caller's subtree")

    now = _now()
    concepts = repo.list_concepts()
    prereqs_of = build_prereqs_of(concepts, repo.list_edges("prerequisite"))
    concept_entries = [
        {
            "concept_id": c.id,
            "p_known": p_known_for(repo, person_id, c.id),
            "mastered": is_mastered(repo, person_id, c),
            "due_count": team_service.due_count_for_concept(repo, person_id, c.id, now),
            "unlocked": is_unlocked(repo, person_id, c.id, prereqs_of),
        }
        for c in concepts
    ]
    summary = team_service.person_summary(repo, person_id, concepts, now, team_service.DEFAULT_DIGEST_DAYS)
    due_count = team_service.due_count_for_person(repo, person_id, concepts, prereqs_of, now)

    await team_service.write_audit(
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


@router.get("/team/recommendations", response_model=RecommendationsResponse)
async def team_recommendations(
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    recommendations = team_service.build_recommendations(repo, ctx.subtree_ids, _now())
    await team_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {"recommendations": recommendations}


@router.get("/team/digest", response_model=TeamDigestResponse)
async def team_digest(
    request: Request,
    days: int = Query(default=team_service.DEFAULT_DIGEST_DAYS, ge=MIN_DIGEST_DAYS, le=MAX_DIGEST_DAYS),
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    now = _now()
    period_start = now - timedelta(days=days)
    concepts = repo.list_concepts()
    concept_summaries = [team_service.concept_summary(repo, c, ctx.subtree_ids, now) for c in concepts]
    at_risk = [
        {"person_id": pid, "concept_id": c.id}
        for c in concepts
        for pid in ctx.subtree_ids
        if team_service.is_at_risk(repo, pid, c.id, now)
    ]
    recommendations = team_service.build_recommendations(repo, ctx.subtree_ids, now)

    await team_service.write_audit(
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


@router.post("/team/focus", response_model=FocusOut)
async def create_team_focus(
    body: FocusCreateRequest,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    if body.scope_kind not in ("subtree", "person"):
        raise _error(422, "validation_error", "scope_kind must be 'subtree' or 'person'")
    if repo.get_concept(body.concept_id) is None:
        raise _error(422, "validation_error", f"unknown concept_id {body.concept_id!r}")

    # Spec §Roster Rules: "subtree of a person" = that person plus all
    # transitive reports, so a manager may root a `subtree` focus at
    # themself to cover their whole team — unlike reads, which deliberately
    # exclude the caller (the "9 reportees" AC).
    allowed_scope_ids = {ctx.person.id, *ctx.subtree_ids}
    if body.scope_person_id not in allowed_scope_ids:
        await team_service.write_audit(
            session,
            actor_person_id=ctx.person.id,
            subject_scope=f"person:{body.scope_person_id}",
            endpoint=request.url.path,
        )
        raise _error(403, "outside_subtree", "scope_person_id is not in the caller's subtree")

    focus_row = await team_service.create_focus(
        session,
        scope_kind=body.scope_kind,
        scope_person_id=body.scope_person_id,
        concept_id=body.concept_id,
        weight=body.weight,
        expires_at=body.expires_at,
        set_by=ctx.person.id,
    )

    await team_service.write_audit(
        session,
        actor_person_id=ctx.person.id,
        subject_scope=f"{body.scope_kind}:{body.scope_person_id}",
        endpoint=request.url.path,
    )
    return {
        "id": focus_row.id,
        "scope_kind": focus_row.scope_kind,
        "scope_person_id": focus_row.scope_person_id,
        "concept_id": focus_row.concept_id,
        "set_by": focus_row.set_by,
        "weight": focus_row.weight,
        "expires_at": focus_row.expires_at,
        "created_at": focus_row.created_at,
    }


@router.delete("/team/focus/{id}", status_code=204)
async def delete_team_focus(
    id: str,
    request: Request,
    ctx: ManagerContext = Depends(require_manager),
    session: AsyncSession = Depends(get_session),
) -> None:
    result = await session.execute(select(DbFocus).where(DbFocus.id == id))
    focus_row = result.scalar_one_or_none()
    if focus_row is None:
        raise _error(404, "not_found", "focus not found")

    owns_scope = focus_row.scope_person_id == ctx.person.id or focus_row.scope_person_id in ctx.subtree_ids
    if focus_row.set_by != ctx.person.id and not owns_scope:
        await team_service.write_audit(
            session, actor_person_id=ctx.person.id, subject_scope=f"focus:{id}", endpoint=request.url.path
        )
        raise _error(403, "outside_subtree", "caller neither set this focus nor owns its scope")

    await team_service.delete_focus(session, focus_id=id)
    await team_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"focus:{id}", endpoint=request.url.path
    )


@router.get("/team/audit", response_model=AuditResponse)
async def team_audit(
    request: Request,
    ctx: ManagerContext = Depends(require_operator_manager),
    session: AsyncSession = Depends(get_session),
) -> dict:
    entries = await team_service.list_audit_for_subtree(session, actor_ids=[ctx.person.id, *ctx.subtree_ids])
    await team_service.write_audit(
        session, actor_person_id=ctx.person.id, subject_scope=f"subtree:{ctx.person.id}", endpoint=request.url.path
    )
    return {
        "entries": [
            {
                "id": e.id,
                "actor_person_id": e.actor_person_id,
                "subject_scope": e.subject_scope,
                "endpoint": e.endpoint,
                "at": e.at,
            }
            for e in entries
        ]
    }
