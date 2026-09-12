"""Registers issue G1's three plugin-native tools — the only real extension
point the Hermes `PluginContext` offers (`ctx.register_tool`; there is no
command-registration hook on the real API, `hermes_cli/plugins.py:893` —
see `__init__.py`'s `register_hook` fix for the same lesson learned the hard
way about guessing at a method name that doesn't exist).

`sync_digest_jobs`, `post_team_quiz`, and `reveal_team_quiz` give
`digests.create_digest_jobs`, `quiz.run_team_quiz`, and `reveal.
render_reveal` real callers outside this plugin's own tests: a live Hermes
turn calls them exactly like any other registered tool, following the
system-prompt instruction this module also registers (same "no new
rendering code" pattern `prompts.py` already uses for `mcq`/`msq`).

Every handler here takes the same `(session_store, session_key,
job_identity=None, **kwargs)` shape `forwarder.py`'s tool handlers do, so
Hermes's dispatcher calls all of a plugin's tools uniformly regardless of
which module registered them; none of these three tools touch the acting
identity, so the first three positional arguments are accepted and ignored.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from .digests import create_digest_jobs
from .quiz import DEFAULT_TODAY_SLUGS, TeamQuizState, run_team_quiz
from .reveal import load_quiz_questions, render_reveal

TEAM_QUIZ_COMMAND_INSTRUCTION = """\
When this turn's own instructions say to run today's team quiz (the daily \
team-quiz digest job), call post_team_quiz(item_ids=[...today's item ids]) \
first, then call clarify once for each entry in its confidence_prompts and \
question_prompts, in that order, using each dict's own kwargs exactly — \
never invent or reorder choices. Post the chip and each entry of \
answered_lines as plain text alongside. Never call reveal_team_quiz from \
this job — the reveal is presenter-triggered only.
When a message is exactly "/kata-reveal <item-id> [item-id ...]", call \
reveal_team_quiz(item_ids=[...]) with those ids and reply with its "text" \
verbatim — never edit it, and never call it except in direct response to \
this command.
When a message is exactly "/kata-sync-digests <team-channel>", call \
sync_digest_jobs(team_channel=<team-channel>) and reply with how many jobs \
were created or updated.
"""


def _default_roster_json_path() -> Path:
    override = os.environ.get("KATA_ROSTER_JSON")
    if override:
        return Path(override)
    # Empty by default — honest about roster import (KATA-4) not having run
    # in this environment yet, rather than fabricating a recipient.
    # KATA_ROSTER_JSON overrides with no code change, same convention
    # tools.json/quiz_items.json already use.
    return Path(__file__).parent / "roster.json"


def load_roster(path: Optional[Path] = None) -> list[dict[str, Any]]:
    """The roster `sync_digest_jobs` plans against: the same `{id,
    slack_user_id}` shape a caller builds by matching `POST /admin/roster/
    import`'s request persons against its response persons by email
    (`digests.py`'s own doc). Vendored empty until KATA-4 lands a real
    snapshot here."""
    path = path or _default_roster_json_path()
    return json.loads(path.read_text(encoding="utf-8"))["persons"]


def _real_create_job_fn() -> Callable[..., Any]:
    try:
        from cron.jobs import create_job  # real Hermes install, spec §6 (cron/jobs.py:2207)
    except ImportError as exc:  # pragma: no cover - exercised only outside a real Hermes install
        raise RuntimeError(
            "hermes-kata: cron.jobs.create_job is not importable in this process — "
            "sync_digest_jobs only works inside a real Hermes install"
        ) from exc
    return create_job


def make_sync_digest_jobs_handler(
    *, create_job_fn: Optional[Callable[..., Any]] = None, roster_path: Optional[Path] = None
) -> Callable[..., dict]:
    def handler(session_store, session_key, job_identity=None, *, team_channel: str) -> dict:
        roster = load_roster(roster_path)
        created = create_digest_jobs(
            create_job_fn or _real_create_job_fn(), roster, team_channel=team_channel
        )
        return {"created": len(created)}

    return handler


def make_post_team_quiz_handler(quiz_state: TeamQuizState) -> Callable[..., dict]:
    def handler(session_store, session_key, job_identity=None, *, item_ids: Optional[Sequence[str]] = None) -> dict:
        post = run_team_quiz(list(item_ids) if item_ids else list(DEFAULT_TODAY_SLUGS), tally=quiz_state.tally, registry=quiz_state.registry)
        return {
            "concept": post.concept,
            "chip": post.chip,
            "confidence_prompts": list(post.confidence_prompts),
            "question_prompts": list(post.question_prompts),
            "answered_lines": list(post.answered_lines),
        }

    return handler


def make_reveal_team_quiz_handler(quiz_state: TeamQuizState) -> Callable[..., dict]:
    def handler(
        session_store,
        session_key,
        job_identity=None,
        *,
        item_ids: Sequence[str],
        team_note: Optional[str] = None,
        leaderboard: Optional[Sequence[dict]] = None,
    ) -> dict:
        questions = load_quiz_questions(list(item_ids))
        text = render_reveal(
            questions,
            quiz_state.tally,
            team_note=team_note,
            leaderboard=leaderboard,
            correct_answerers=quiz_state.correct_answerers,
        )
        return {"text": text}

    return handler


def register_team_quiz_commands(ctx, quiz_state: TeamQuizState) -> None:
    """Registers the three tools above under the `learning` toolset (the
    team-quiz digest job already carries `clarify` too, `digests.
    TEAM_QUIZ_TOOLSETS`) plus the system-prompt instruction that tells a
    turn when to call each one."""
    ctx.register_tool(
        name="sync_digest_jobs",
        toolset="learning",
        schema={
            "type": "object",
            "required": ["team_channel"],
            "properties": {"team_channel": {"type": "string"}},
            "additionalProperties": False,
        },
        handler=make_sync_digest_jobs_handler(),
        description=(
            "Create or idempotently update the due-rep, team-quiz, and teach-back digest cron "
            "jobs from the current roster (spec §6). Safe to re-run after every roster import."
        ),
    )
    ctx.register_tool(
        name="post_team_quiz",
        toolset="learning",
        schema={
            "type": "object",
            "properties": {"item_ids": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
        handler=make_post_team_quiz_handler(quiz_state),
        description=(
            "Plan today's team-quiz post: the confidence-picker clarify kwargs and each item's "
            "own clarify kwargs (in order), the source chip, and the live answered-count line."
        ),
    )
    ctx.register_tool(
        name="reveal_team_quiz",
        toolset="learning",
        schema={
            "type": "object",
            "required": ["item_ids"],
            "properties": {
                "item_ids": {"type": "array", "items": {"type": "string"}},
                "team_note": {"type": "string"},
                "leaderboard": {"type": "array"},
            },
            "additionalProperties": False,
        },
        handler=make_reveal_team_quiz_handler(quiz_state),
        description=(
            "Render the on-demand team-quiz reveal (AGCTM-69): call only in direct response to "
            "a presenter's /kata-reveal command, never on a schedule."
        ),
    )
    ctx.register_system_prompt_section(
        "kata-team-quiz-commands", lambda session_info: TEAM_QUIZ_COMMAND_INSTRUCTION, position="after_memory"
    )
