"""Cron entry points invoked by the Railway `learning-retention` and
`learning-replay` services (spec §Deployment) and by `docker compose run`.

`retention` purges `answer` rows past the 90-day window (spec §Privacy and
retention); `replay` rebuilds `card_state`/`concept_state` from the `review`
log (spec §Learning engine, "Replay"). Both are no-ops when `DATABASE_URL`
is unset — same as `/health/db` — so this module stays importable, and its
CLI shape testable, without a live database.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

JOBS = ("retention", "replay")


def _log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} learning-cli {msg}", flush=True)


def retention() -> int:
    if not os.environ.get("DATABASE_URL"):
        _log("retention: DATABASE_URL not set, nothing to do")
        return 0

    async def _run() -> None:
        from learning_service.db import session_scope
        from learning_service.privacy.service import purge_expired_answers

        async with session_scope() as session:
            await purge_expired_answers(session)

    asyncio.run(_run())
    _log("retention: purged answer rows past the 90-day window")
    return 0


def replay() -> int:
    if not os.environ.get("DATABASE_URL"):
        _log("replay: DATABASE_URL not set, nothing to do")
        return 0

    async def _run() -> dict:
        from learning_service.db import session_scope
        from learning_service.engine.replay import rebuild_derived_state

        async with session_scope() as session:
            return await rebuild_derived_state(session)

    counts = asyncio.run(_run())
    _log(f"replay: rebuilt derived state ({counts})")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    job = argv[0] if argv else ""
    if job not in JOBS:
        _log(f"usage: python -m learning_service.cli <{'|'.join(JOBS)}>")
        return 2
    _log(f"start job={job}")
    return {"retention": retention, "replay": replay}[job]()


if __name__ == "__main__":
    raise SystemExit(main())
