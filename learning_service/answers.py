"""`GET /me/answers` + `DELETE /me/answers` (spec §Privacy and retention,
§API): the acting person's own short-answer submissions, paginated, and
immediate self-deletion. `answer` rows are written by `POST /me/reviews`
(see `reviews.py`) for `short_answer` items.

90-day retention is enforced inline on every request this router handles,
by purging expired rows before reading or deleting, on top of the nightly
`learning_service.cli retention` cron (spec §Deployment).
"""

from __future__ import annotations

import base64
from typing import Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.db import get_session
from learning_service.main import resolve_person_id
from learning_service.privacy import service as privacy_service

router = APIRouter()


def _encode_cursor(answer_id: str) -> str:
    return base64.urlsafe_b64encode(answer_id.encode()).decode()


def _decode_cursor(cursor: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception:
        return None


@router.get("/me/answers")
async def me_answers(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    await privacy_service.purge_expired_answers(session)
    answers = await privacy_service.list_answers(session, person_id)

    start = 0
    if cursor:
        after_id = _decode_cursor(cursor)
        if after_id is not None:
            for i, answer in enumerate(answers):
                if answer.id == after_id:
                    start = i + 1
                    break

    page = answers[start : start + limit]
    next_cursor = _encode_cursor(page[-1].id) if start + limit < len(answers) else None

    return {
        "answers": [
            {"id": a.id, "review_id": a.review_id, "text": a.text, "created_at": a.created_at.isoformat()}
            for a in page
        ],
        "next_cursor": next_cursor,
    }


@router.delete("/me/answers", status_code=204)
async def delete_me_answers(
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await privacy_service.purge_expired_answers(session)
    await privacy_service.delete_answers(session, person_id)
    return Response(status_code=204)
