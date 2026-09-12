"""`POST /admin/roster/import` (spec §API, §Identity roles teams → Roster
seeding). Gated on the service token alone, not `require_operator`: roster
import is the bootstrap path — the roster import cannot itself produce an
operator, and an operator-gated `/admin/*` route needs one to already exist
(OPEN-QUESTIONS.md Q4). Revisit once Q4 lands an answer.
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
