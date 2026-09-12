"""`POST /admin/roster/import` (spec §Identity, roles, teams → Roster
seeding). Adapted from `agency-v1/learning_service/admin.py`, which also
carries `POST /admin/replay` — that route rebuilds `card_state`/
`concept_state` from the review log, so it belongs to the `engine` package
(KATA-2's follow-up issue, which depends on this one) and is not vendored
here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.db import get_session
from learning_service.identity.schemas import PersonSummary
from learning_service.main import _error, require_service_token
from learning_service.roster.schemas import RosterImportRequest, RosterImportResult
from learning_service.roster.service import (
    InvalidRole,
    SlackIdentityConflict,
    UnknownManager,
    WebIdentityConflict,
    import_roster,
)

router = APIRouter()


@router.post("/admin/roster/import", response_model=RosterImportResult)
async def admin_roster_import(
    body: RosterImportRequest,
    _: None = Depends(require_service_token),
    session: AsyncSession = Depends(get_session),
) -> RosterImportResult:
    try:
        persons, created, updated = await import_roster(session, persons=body.persons)
    except UnknownManager as exc:
        raise _error(422, "validation_error", f"manager_email {exc} does not match any person") from exc
    except SlackIdentityConflict as exc:
        raise _error(422, "validation_error", f"slack_user_id {exc} is already linked to a different person") from exc
    except InvalidRole as exc:
        raise _error(422, "validation_error", f"role {exc} is not a recognized role") from exc
    except WebIdentityConflict as exc:
        raise _error(422, "validation_error", f"email {exc} is already linked to a different person") from exc
    return RosterImportResult(
        created=created,
        updated=updated,
        persons=[
            PersonSummary(
                id=p.id, display_name=p.display_name, email=p.email, is_operator=p.is_operator, role=p.role
            )
            for p in persons
        ],
    )
