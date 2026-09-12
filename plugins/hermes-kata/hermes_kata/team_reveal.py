"""Team-level reveal (AGCTM-69): what "reveal the team kata results" answers
today. No cron job posts a daily MCQ question yet and no `QuizSession` has
ever collected a tap in production (see `quiz.py`) — so there is no live
per-option tally to render, and asking Kata to reveal one previously fell
through to it improvising a summary from generic team tools (`get_team_
overview`, `get_team_digest`, ...), never touching this plugin's own
rendering code at all.

This ships the pinned Ferry-seed reveal — the exact Block Kit payload in
`docs/demo/slack/kata-reveal.blockkit.json` (AGCTM-69 frame 07), matching
`quiz.py`'s own test fixture ("four of nine can explain the lock, one of
nine can explain why the dry run matters") — as a fixed `kata_reveal` tool
result, so a request to reveal has something real and correctly-shaped to
post today. Swap `HARDCODED_REVEAL_BLOCKS` for a live `quiz.py::
render_reveal_blocks(...)` call once a daily question is actually posted
and answered in production.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .tools import TOOLSET

KATA_REVEAL_TOOL_NAME = "kata_reveal"
SECTION_ID = "kata-team-reveal-rendering"
MAX_CHARS = 1200

# Pinned, not computed — the Ferry seed's own numbers, unchanged from
# `docs/demo/slack/kata-reveal.blockkit.json`.
HARDCODED_REVEAL_BLOCKS: dict = {
    "blocks": [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*1/2 · Why did we revert?*   `4 of 9`"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "`█░░░░░░░░░` *1*  The column name clashed\n"
                    "`████░░░░░░` *4*  ✅ *Backfill held a lock on `postings` for 34s*\n"
                    "`███░░░░░░░` *3*  It failed CI\n"
                    "`█░░░░░░░░░` *1*  Ledger was read-only"
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*2/2 · What has to be true before it goes back in?*   ⚠️ `1 of 9`",
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "`█░░░░░░░░░` *1*  ✅ *Chunked, off-peak, after a dry run on a prod snapshot*\n"
                    "`██░░░░░░░░` *2*  A bigger database instance\n"
                    "`███░░░░░░░` *3*  Run it during the daily deploy\n"
                    "`███░░░░░░░` *3*  Add the column NOT NULL to fail fast"
                ),
            },
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "> *Team note.* 4 of 9 can explain the lock; 1 of 9 can explain why the dry run "
                    "matters. Chunking and off-peak both showed up — the missing piece is that "
                    "_staging is 4% of prod, so the staging timing means nothing_. That is what "
                    "`PAY-1875` is for. `ledger-migrations` is now the team's flagged gap; tomorrow's "
                    "reps for everyone who missed it start there."
                ),
            },
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*Sprint 42 leaderboard*\n"
                    "`1`  *Yong Yi Tan* · 2/2 · 🔥 8 days\n"
                    "`2`  *Daniel Okonkwo* · 1/2 · 🔥 11 days\n"
                    "`2`  *Hugo Marchetti* · 1/2 · 🔥 9 days\n"
                    "`2`  *Victor Almeida* · 1/2 · 🔥 6 days\n"
                    "`5`  Julian, Titus, Shane, Mei Lin, Nushka · 0/2"
                ),
            },
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "*What Kata recorded:* nine `mcq` reviews, source `slack_thread`, each with the "
                        "confidence you tapped before the reveal. Your own answer is visible only to you "
                        "and in this thread; the manager view gets the concept-level state, never who "
                        "picked what."
                    ),
                }
            ],
        },
    ]
}

SYSTEM_PROMPT_TEAM_REVEAL_RENDERING = f"""\
When asked to reveal, show, or share the team's kata/quiz results, call \
`{KATA_REVEAL_TOOL_NAME}` (no arguments). Its result is `{{"blocks": [...]}}` \
— post the `text` of every block in the exact order given, unchanged: don't
summarize, paraphrase, drop lines, add commentary, or resolve any id/name
yourself. Never build this reply from `get_team_overview`, `get_team_digest`,
or any other team tool — `{KATA_REVEAL_TOOL_NAME}` is the only source for
this request.
"""


def render_reveal_blocks() -> dict:
    return HARDCODED_REVEAL_BLOCKS


def make_team_reveal_handler() -> Callable[..., str]:
    """Tool handler for `kata_reveal` — always returns the pinned Ferry-seed
    reveal (see module docstring); takes no arguments, hits no endpoint."""

    def handler(args: Any = None, *, session_id: Any = None, **kwargs: Any) -> str:
        return json.dumps(HARDCODED_REVEAL_BLOCKS)

    return handler


def register_team_reveal(ctx: Any) -> None:
    """Wires `kata_reveal` into the live tool catalog and tells Kata to use
    it (`__init__.py::register()`) — without both halves this is the same
    dead-code trap `quiz.py`'s own reveal was already in: correct rendering
    code nothing ever calls.
    """
    ctx.register_tool(
        name=KATA_REVEAL_TOOL_NAME,
        toolset=TOOLSET,
        schema={"type": "object", "properties": {}, "additionalProperties": False},
        handler=make_team_reveal_handler(),
        description="Return the team's kata/quiz reveal as a Slack Block Kit message, ready to post verbatim.",
    )
    ctx.register_system_prompt_section(
        SECTION_ID,
        SYSTEM_PROMPT_TEAM_REVEAL_RENDERING,
        position="after_memory",
        max_chars=MAX_CHARS,
    )
