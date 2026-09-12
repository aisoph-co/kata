"""`GET /me/answers` + `DELETE /me/answers` (spec §Privacy and retention,
§API): the acting person's own short-answer submissions, paginated, and
immediate self-deletion. `answer` rows are written by `engine/router.py`'s
`POST /me/reviews` for `short_answer` items.

90-day retention is enforced inline, on every request this router handles,
by purging expired rows before reading or deleting (`SqlLearningRepository.
purge_answers_older_than` issues a real Postgres `DELETE` too, not just an
in-memory snapshot mutation). The dedicated nightly CLI cron (`cli.py`)
covers a person who never calls this route at all.
"""

from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Response

from learning_service.engine.models import ANSWER_RETENTION_DAYS
from learning_service.engine.repository import LearningRepository
from learning_service.engine.sql_repository import SqlLearningRepository
from learning_service.main import get_repository, resolve_person_id

router = APIRouter()


def _encode_cursor(answer_id: str) -> str:
    return base64.urlsafe_b64encode(answer_id.encode()).decode()


def _decode_cursor(cursor: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(cursor.encode()).decode()
    except Exception:
        return None


async def _purge_expired(repo: LearningRepository) -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ANSWER_RETENTION_DAYS)
    if isinstance(repo, SqlLearningRepository):
        await repo.purge_answers_older_than(cutoff)
    else:
        repo.purge_answers_older_than(cutoff)


@router.get("/me/answers")
async def me_answers(
    cursor: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> dict[str, Any]:
    await _purge_expired(repo)
    answers = sorted(repo.answers_for(person_id), key=lambda a: (a.created_at, a.id), reverse=True)

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
            {
                "id": answer.id,
                "review_id": answer.review_id,
                "text": answer.text,
                "created_at": answer.created_at.isoformat(),
            }
            for answer in page
        ],
        "next_cursor": next_cursor,
    }


@router.delete("/me/answers", status_code=204)
async def delete_me_answers(
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> Response:
    await _purge_expired(repo)
    if isinstance(repo, SqlLearningRepository):
        await repo.delete_answers_for(person_id)
    else:
        repo.delete_answers_for(person_id)
    return Response(status_code=204)
