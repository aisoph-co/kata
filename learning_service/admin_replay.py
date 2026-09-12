"""`POST /admin/replay` (spec §Learning engine, "Replay"): a scheduling or
mastery bug is fixed by replay, not migration. Truncates `card_state` and
`concept_state`, then rebuilds them by iterating the append-only `review`
log in `(person_id, reviewed_at, id)` order through the same fold
`POST /me/reviews` uses live (`engine/replay.py`), so replayed state is
identical to live state (KAT-X4).

Kept in its own module, not `admin.py` (KATA-2's file, still under review
when this issue was dispatched — see the Epic's dispatch comment), and
included from `main.py` the same way every other router here is.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.db import get_session
from learning_service.engine.replay import rebuild_derived_state
from learning_service.main import require_service_token

router = APIRouter()


@router.post("/admin/replay")
async def admin_replay(
    _: None = Depends(require_service_token),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    counts = await rebuild_derived_state(session)
    return {"status": "ok", **counts}
