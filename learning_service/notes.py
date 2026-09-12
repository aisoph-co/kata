"""`GET/POST /me/notes`, `DELETE /me/notes/{id}`, `DELETE /me/notes` (spec
§Privacy and retention, §API): the acting person's own private tutoring-
personalization notes. Written and read only through these routes — never
joined by `/team/*`, `/admin/*`, or a digest.

Caps (20 notes/person, 500 chars/note) are enforced on every `POST`; past
either returns 422 `note_cap`. Notes have no retention window — they are
the learner's own and deletable at will.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.db import get_session
from learning_service.main import _error, resolve_person_id
from learning_service.privacy import service as privacy_service
from learning_service.privacy.models import LearnerNote

router = APIRouter()


class NoteCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # No `max_length` here: an over-length note is the `note_cap` 422 the
    # spec asks for, not a generic `validation_error`.
    text: str = Field(min_length=1)


def _note_out(note: LearnerNote) -> dict[str, Any]:
    return {
        "id": note.id,
        "text": note.text,
        "created_at": note.created_at.isoformat(),
        "updated_at": note.updated_at.isoformat(),
    }


@router.get("/me/notes")
async def me_notes(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    notes = await privacy_service.list_notes(session, person_id)
    return {"notes": [_note_out(n) for n in notes]}


@router.post("/me/notes")
async def create_me_note(
    request: Request,
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    try:
        body = NoteCreateRequest.model_validate(await request.json())
    except ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc

    try:
        note = await privacy_service.create_note(session, person_id=person_id, text=body.text)
    except privacy_service.NoteCapExceeded as exc:
        raise _error(422, "note_cap", str(exc)) from exc
    return _note_out(note)


@router.delete("/me/notes", status_code=204)
async def delete_me_notes(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await privacy_service.delete_notes(session, person_id)
    return Response(status_code=204)


@router.delete("/me/notes/{note_id}", status_code=204)
async def delete_me_note(
    note_id: str,
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    found = await privacy_service.delete_note(session, person_id=person_id, note_id=note_id)
    if not found:
        raise _error(404, "not_found", "note not found")
    return Response(status_code=204)
