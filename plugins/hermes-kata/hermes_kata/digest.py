"""Job 4 (adapter-contract, spec §6): digest delivery — the cron jobs the
due-rep, team-quiz, and teach-back digests run on.

One `cron.jobs.create_job` per digest kind per recipient: a due-rep job for
every person in the roster, plus a single team-quiz job and a single
teach-back job addressed to the team's own chat (the same chat the quiz
posts the daily question into and `/kata-reveal` replies in, `quiz.py`).
`cron.jobs.create_job` is documented idempotent on `name` — calling it again
on every deploy/reload is safe and creates nothing new, so this module never
checks-then-creates.

A cron-triggered turn has no `MessageEvent`/session for `identity.py`'s hook
to bind — only the job's own name — so every job created here also gets its
acting identity recorded in `JobIdentityRegistry` (tools.py), which was
"empty until a digest-scheduling issue populates it" before this build.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

from .client import ActingIdentity
from .tools import TOOLSET, JobIdentityRegistry

DUE_REP_KIND = "due_rep"
TEAM_QUIZ_KIND = "team_quiz"
TEACH_BACK_KIND = "teach_back"

# Deploy-time defaults (UTC), not part of the frozen learning-service
# contract — retuning these never changes a job's `name`, so it never
# affects `create_job`'s idempotency key.
DUE_REP_SCHEDULE = "0 8 * * *"
TEAM_QUIZ_SCHEDULE = "0 9 * * 1-5"
TEACH_BACK_SCHEDULE = "0 9 * * 1"


@dataclass(frozen=True)
class DigestRecipient:
    """Whose chat a digest job delivers into and, for a `learning` tool
    call made from that job's own turn, whose identity backs it."""

    person_id: str
    platform: str
    external_id: str

    @property
    def identity(self) -> ActingIdentity:
        return ActingIdentity(platform=self.platform, external_id=self.external_id)


def due_rep_job_name(person_id: str) -> str:
    return f"kata-due-rep:{person_id}"


def team_quiz_job_name() -> str:
    return "kata-team-quiz"


def teach_back_job_name() -> str:
    return "kata-teach-back"


def create_digest_jobs(
    cron: Any,
    job_identities: JobIdentityRegistry,
    *,
    learners: Iterable[DigestRecipient],
    team_recipient: DigestRecipient,
) -> list[str]:
    """Create every digest cron job this build ships: one due-rep job per
    learner, one team-quiz job, one teach-back job — each scoped to the
    `learning` toolset only (a cron job never gets a wider toolset than a
    learner-triggered turn does) and each with `job_identities` populated so
    its own tool calls (`get_due_summary`, `submit_review`, ...) resolve an
    identity.

    Returns the job names created, in submission order — this issue's done
    check counts these: exactly ten due-rep + one team-quiz + one teach-back
    for the golden scenario's ten-person roster.
    """
    created: list[str] = []

    for learner in learners:
        name = due_rep_job_name(learner.person_id)
        cron.jobs.create_job(
            name=name,
            schedule=DUE_REP_SCHEDULE,
            toolset=TOOLSET,
            recipient={"platform": learner.platform, "external_id": learner.external_id},
            metadata={"kind": DUE_REP_KIND, "person_id": learner.person_id},
        )
        job_identities.set(name, learner.identity)
        created.append(name)

    for name, kind, schedule in (
        (team_quiz_job_name(), TEAM_QUIZ_KIND, TEAM_QUIZ_SCHEDULE),
        (teach_back_job_name(), TEACH_BACK_KIND, TEACH_BACK_SCHEDULE),
    ):
        cron.jobs.create_job(
            name=name,
            schedule=schedule,
            toolset=TOOLSET,
            recipient={"platform": team_recipient.platform, "external_id": team_recipient.external_id},
            metadata={"kind": kind},
        )
        job_identities.set(name, team_recipient.identity)
        created.append(name)

    return created


def load_digest_roster(path: Path) -> list[DigestRecipient]:
    """Parse the roster file a deploy step writes after `POST
    /admin/roster/import` completes (spec §6's own dependency: "roster
    import having run with chat IDs recorded") — `[{"person_id", "platform",
    "external_id"}, ...]`. This module has no way to list the roster itself
    (no such endpoint is in the frozen `tools.json`), so it only ever reads
    what that step already resolved.
    """
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [
        DigestRecipient(person_id=e["person_id"], platform=e["platform"], external_id=e["external_id"])
        for e in entries
    ]


def team_recipient_from_env(env: Optional[dict] = None) -> Optional[DigestRecipient]:
    """The team-quiz/teach-back recipient — the chat the daily question
    posts into. `KATA_TEAM_RECIPIENT_PERSON_ID` defaults to `"team"` since
    this recipient doesn't have to be a roster person (a channel has no
    `person_id` of its own)."""
    env = os.environ if env is None else env
    platform = env.get("KATA_TEAM_RECIPIENT_PLATFORM")
    external_id = env.get("KATA_TEAM_RECIPIENT_EXTERNAL_ID")
    if not platform or not external_id:
        return None
    return DigestRecipient(
        person_id=env.get("KATA_TEAM_RECIPIENT_PERSON_ID", "team"), platform=platform, external_id=external_id
    )
