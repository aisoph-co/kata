"""`POST /admin/replay` (spec §Learning engine, "Replay"): a scheduling or
mastery bug is fixed by replay, not migration. Truncates `card_state` and
`concept_state`, then rebuilds them by iterating the append-only `review`
log in `(person_id, reviewed_at, id)` order through `apply_review` — the
same step `POST /me/reviews` uses live — so replayed state is identical to
live state.

`openapi.yaml` documents `403 "Not an operator"` for this route, so it is
gated on `require_operator` (a real `Person.is_operator` check), unlike a
prior reference implementation that only checked the service token.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from learning_service.engine.replay import rebuild_derived_state
from learning_service.engine.repository import LearningRepository
from learning_service.engine.sql_repository import SqlLearningRepository
from learning_service.main import get_repository, require_operator

router = APIRouter()


@router.post("/admin/replay")
async def admin_replay(
    _: None = Depends(require_operator),
    repo: LearningRepository = Depends(get_repository),
) -> dict[str, Any]:
    # `rebuild_derived_state` only touches `repo`'s in-memory dicts, so a
    # concurrent `/me/next` reading through a *different*
    # `SqlLearningRepository` instance never sees a half-rebuilt state:
    # `persist_derived_state` below is the one write, one transaction, one
    # commit that makes the rebuild visible to Postgres at all.
    counts = rebuild_derived_state(repo)
    if isinstance(repo, SqlLearningRepository):
        await repo.persist_derived_state()

    return {"status": "ok", **counts}
