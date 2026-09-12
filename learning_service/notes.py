"""`GET/POST /me/notes`, `DELETE /me/notes/{id}`, `DELETE /me/notes` (spec
§Privacy and retention, §API): the acting person's own private tutoring-
personalization notes. Written and read only through these routes — never
joined by `/team/*`, `/admin/*`, or a digest.

Caps (20 notes/person, 500 chars/note) are enforced on every `POST`; past
either returns 422 `note_cap`. Notes have no retention window — they are the
learner's own and deletable at will.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from learning_service.engine.models import NOTE_MAX_CHARS, NOTE_MAX_COUNT, LearnerNote
from learning_service.engine.repository import LearningRepository
from learning_service.engine.sql_repository import SqlLearningRepository
from learning_service.main import _error, get_repository, resolve_person_id

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
    repo: LearningRepository = Depends(get_repository),
) -> dict[str, Any]:
    notes = sorted(repo.notes_for(person_id), key=lambda n: (n.created_at, n.id), reverse=True)
    return {"notes": [_note_out(note) for note in notes]}


@router.post("/me/notes")
async def create_me_note(
    request: Request,
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> dict[str, Any]:
    try:
        body = NoteCreateRequest.model_validate(await request.json())
    except ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc

    if len(body.text) > NOTE_MAX_CHARS or len(repo.notes_for(person_id)) >= NOTE_MAX_COUNT:
        raise _error(422, "note_cap", f"at most {NOTE_MAX_COUNT} notes of {NOTE_MAX_CHARS} characters each")

    now = datetime.now(timezone.utc)
    note = LearnerNote(id=str(uuid.uuid4()), person_id=person_id, text=body.text, created_at=now, updated_at=now)
    repo.add_note(note)
    if isinstance(repo, SqlLearningRepository):
        await repo.persist()
    return _note_out(note)


@router.delete("/me/notes", status_code=204)
async def delete_me_notes(
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> Response:
    if isinstance(repo, SqlLearningRepository):
        await repo.delete_notes_for(person_id)
    else:
        repo.delete_notes_for(person_id)
    return Response(status_code=204)


@router.delete("/me/notes/{note_id}", status_code=204)
async def delete_me_note(
    note_id: str,
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> Response:
    if isinstance(repo, SqlLearningRepository):
        found = await repo.delete_note(person_id, note_id)
    else:
        found = repo.delete_note(person_id, note_id)
    if not found:
        raise _error(404, "not_found", "note not found")
    return Response(status_code=204)
