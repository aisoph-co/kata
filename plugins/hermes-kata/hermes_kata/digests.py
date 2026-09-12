"""Digest cron jobs (spec §6, issue G1): one `cron.jobs.create_job` per
digest kind per recipient, idempotent on `name` — same `name` is the same
job, updated not duplicated, so re-running this after every roster import is
safe.

`plan_digest_jobs` is pure: given the roster this workspace's admin roster
import just processed — the request's own persons (which know each
person's `slack_user_id`) matched up with the response's persons (which
know each person's `id`) — it returns the exact set of jobs the spec calls
for: one due-rep job per person with a resolvable chat id, one team-quiz
job, one teach-back job. A person with no chat id yet (roster import hasn't
recorded one, KATA-4) gets no due-rep job — this never fabricates a
recipient.

The team-quiz job is the one digest kind that carries `clarify` on top of
`learning`: KATA-24 (G1) has it run the quiz round itself (confidence
picker, then the item's own buttons via `hermes_kata.quiz.run_team_quiz`),
not just announce it. Every other digest kind stays push-only, `learning`-
only (spec §6: "a digest is a push, not a conversation").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

DUE_REP_PROMPT = (
    "Render this learner's due-rep digest from get_due_summary: how many "
    "items are overdue, due today, and newly available. Keep it to a few "
    "lines, friendly, no lecture."
)
TEAM_QUIZ_PROMPT = (
    "Run today's team quiz (hermes_kata.quiz.run_team_quiz): for each item, "
    "call clarify for the confidence picker, then clarify for the item "
    "itself — never chat text. Post the source chip and the live 'N of "
    "<roster size> answered · reveal in m:ss' line. Never reveal an answer "
    "here; the presenter triggers the reveal later, on demand."
)
TEACH_BACK_PROMPT = (
    "Render this week's teach-back recommendations from "
    "get_team_recommendations: the top concepts the team should focus on "
    "next."
)

DUE_REP_SCHEDULE = "0 8 * * *"  # daily, learner's local morning
TEAM_QUIZ_SCHEDULE = "0 9 * * *"  # daily, team-configured time
TEACH_BACK_SCHEDULE = "0 9 * * 1"  # weekly

# The one digest kind that carries `clarify` (KATA-24) — every other kind
# stays the spec §6 default, `("learning",)`.
TEAM_QUIZ_TOOLSETS = ("learning", "clarify")


@dataclass(frozen=True)
class DigestJobSpec:
    kind: str
    name: str
    prompt: str
    schedule: str
    deliver: str
    enabled_toolsets: tuple[str, ...] = ("learning",)


def _chat_id(person_id: str, roster_persons: Sequence[Mapping[str, Any]]) -> Optional[str]:
    """`platform:external_id` for the person's own roster-import entry — the
    only identity source this function needs, since a `slack_user_id` on the
    import request becomes exactly that identity (`roster/service.py`'s
    import pass). No separate identity lookup call."""
    for person in roster_persons:
        if person.get("id") == person_id and person.get("slack_user_id"):
            return f"slack:{person['slack_user_id']}"
    return None


def plan_digest_jobs(
    roster_persons: Sequence[Mapping[str, Any]],
    *,
    team_channel: str,
    chat_id_for: Optional[Callable[[str], Optional[str]]] = None,
) -> list[DigestJobSpec]:
    """Pure planning: given the roster (one entry per person, each carrying
    at least `id` and, when known, `slack_user_id` — the shape a caller
    builds by matching `POST /admin/roster/import`'s request persons against
    its response persons by email) and a team channel, return the exact set
    of digest jobs the spec calls for — one due-rep job per person with a
    resolvable chat id, one team-quiz job, one teach-back job (spec §6: for
    the ten-person golden scenario, "exactly ten due-rep jobs, one
    team-quiz job, and one teach-back job")."""
    resolve_chat_id = chat_id_for or (lambda person_id: _chat_id(person_id, roster_persons))

    jobs: list[DigestJobSpec] = []
    for person in roster_persons:
        chat_id = resolve_chat_id(person["id"])
        if chat_id is None:
            continue
        jobs.append(
            DigestJobSpec(
                kind="due_rep",
                name=f"kata-due-rep-{person['id']}",
                prompt=DUE_REP_PROMPT,
                schedule=DUE_REP_SCHEDULE,
                deliver=chat_id,
            )
        )

    jobs.append(
        DigestJobSpec(
            kind="team_quiz",
            name="kata-team-quiz-team",
            prompt=TEAM_QUIZ_PROMPT,
            schedule=TEAM_QUIZ_SCHEDULE,
            deliver=team_channel,
            enabled_toolsets=TEAM_QUIZ_TOOLSETS,
        )
    )
    jobs.append(
        DigestJobSpec(
            kind="teach_back",
            name="kata-teach-back-team",
            prompt=TEACH_BACK_PROMPT,
            schedule=TEACH_BACK_SCHEDULE,
            deliver=team_channel,
        )
    )
    return jobs


def create_digest_jobs(
    create_job_fn: Callable[..., Any],
    roster_persons: Sequence[Mapping[str, Any]],
    *,
    team_channel: str,
    chat_id_for: Optional[Callable[[str], Optional[str]]] = None,
) -> list[Any]:
    """Create (or idempotently update) every planned job via `create_job_fn`
    (`cron.jobs.create_job`) — same `name` is the same job, so calling this
    again after a later roster import updates in place."""
    created = []
    for job in plan_digest_jobs(roster_persons, team_channel=team_channel, chat_id_for=chat_id_for):
        created.append(
            create_job_fn(
                name=job.name,
                prompt=job.prompt,
                schedule=job.schedule,
                deliver=job.deliver,
                enabled_toolsets=list(job.enabled_toolsets),
            )
        )
    return created
