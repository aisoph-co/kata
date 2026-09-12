"""Cron entry points for the nightly `learning-retention` job and the
`learning-replay` rebuild (spec §Deployment).

`retention` issues the same `DELETE ... WHERE created_at < cutoff`
`SqlLearningRepository.purge_answers_older_than` runs inline on every
`/me/answers` request (see `answers.py`), so a person who never calls that
route still gets their expired answers purged nightly. `DATABASE_URL` unset
(dev/test, `docker compose run` without Postgres) is a no-op, not a
failure — there is nothing to purge.

`replay` calls the same rebuild `POST /admin/replay` uses (`engine.replay.
rebuild_derived_state`), against a `SqlLearningRepository` hydrated from a
`session_scope()` session, so the nightly cron and the HTTP route share one
implementation.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from learning_service.db import session_scope
from learning_service.engine.models import ANSWER_RETENTION_DAYS
from learning_service.engine.replay import rebuild_derived_state
from learning_service.engine.sql_models import AnswerRow
from learning_service.engine.sql_repository import SqlLearningRepository

JOBS = ("retention", "replay")


def _log(msg: str) -> None:
    print(f"{datetime.now(timezone.utc).isoformat()} learning-cli {msg}", flush=True)


async def _purge_expired_answers() -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(days=ANSWER_RETENTION_DAYS)
    async with session_scope() as session:
        result = await session.execute(delete(AnswerRow).where(AnswerRow.created_at < cutoff))
        await session.commit()
        return result.rowcount or 0


def retention() -> int:
    if not os.environ.get("DATABASE_URL"):
        _log("retention: DATABASE_URL not set, nothing to purge")
        return 0
    try:
        purged = asyncio.run(_purge_expired_answers())
    except Exception as exc:  # noqa: BLE001 — a failed sweep must fail the cron run, not go silent
        _log(f"retention: failed: {exc}")
        return 1
    _log(f"retention: purged {purged} answer row(s) older than {ANSWER_RETENTION_DAYS} days")
    return 0


async def _rebuild_derived_state() -> dict[str, int]:
    async with session_scope() as session:
        repo = SqlLearningRepository(session)
        await repo.load()
        counts = rebuild_derived_state(repo)
        await repo.persist_derived_state()
        return counts


def replay() -> int:
    if not os.environ.get("DATABASE_URL"):
        _log("replay: DATABASE_URL not set, nothing to rebuild")
        return 0
    try:
        counts = asyncio.run(_rebuild_derived_state())
    except Exception as exc:  # noqa: BLE001 — a failed rebuild must fail the cron run, not go silent
        _log(f"replay: failed: {exc}")
        return 1
    _log(f"replay: rebuilt {counts['card_state_count']} card_state, {counts['concept_state_count']} concept_state "
         f"row(s) from {counts['replayed_reviews']} review(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    job = argv[0] if argv else ""
    if job not in JOBS:
        _log(f"usage: python -m learning_service.cli <{'|'.join(JOBS)}>")
        return 2
    _log(f"start job={job} database={'configured' if os.environ.get('DATABASE_URL') else 'unconfigured'}")
    return {"retention": retention, "replay": replay}[job]()


if __name__ == "__main__":
    raise SystemExit(main())
