"""Team-quiz post plan (spec §6/§8, issue G1, frame 06): for each of today's
items, the confidence picker before the tap, then the item itself — both
native Block Kit buttons via Hermes `clarify`, never chat text (job 3's rule,
`prompts.py`'s `MCQ_MSQ_INSTRUCTION`).

Not a live network driver: `run_team_quiz` is a pure function that plans
what gets posted; whatever issues the turn (a cron-triggered command or a
model turn following the digest prompt, `digests.py`'s `TEAM_QUIZ_PROMPT`)
makes the actual `clarify` calls from that plan. Collection is the existing
plumbing (`forwarder.py`'s `submit_review` forwarder -> `reveal.
record_submit_review` -> `QuizTally`); this module's only touch on that path
is `TeamQuizItemRegistry`, so a resolved answer to one of *today's* items is
sent with `platform="slack_thread"` (KATA-24: already a valid enum value in
the frozen contract, no contract change needed).
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from .reveal import CorrectAnswerers, QuizQuestion, QuizTally, load_quiz_questions

CONFIDENCE_CHOICES: tuple[str, ...] = ("1", "2", "3", "4", "5")
CONFIDENCE_QUESTION = "Confidence (1-5) before you answer?"

# Demo defaults — `docs/seed/verify_demo_beats.py`'s ten-persona golden
# scenario: ten persons, the poster isn't one of the nine respondents.
DEFAULT_ROSTER_SIZE = int(os.environ.get("KATA_QUIZ_ROSTER_SIZE", "9"))
DEFAULT_REVEAL_SECONDS = int(os.environ.get("KATA_QUIZ_REVEAL_SECONDS", "600"))


def confidence_clarify_kwargs() -> dict:
    """The confidence picker posted before every quiz question's tap
    (SCREENS.md #06: "confidence row 1-5 before the tap") — same `clarify`
    shape job 3 uses, single-select."""
    return {"question": CONFIDENCE_QUESTION, "choices": list(CONFIDENCE_CHOICES), "multi_select": False}


def question_clarify_kwargs(question: QuizQuestion) -> dict:
    """The quiz question itself, native Block Kit buttons via `clarify` —
    never chat-text options."""
    return {"question": question.prompt, "choices": list(question.options), "multi_select": False}


def answered_status_line(answered: int, total: int, seconds_remaining: int) -> str:
    """The live "N of 9 answered · reveal in m:ss" line (SCREENS.md #06).
    Pure formatting over already-known counts — there is no timer in this
    plugin; `seconds_remaining` is whatever the caller (a live cron turn, a
    status command) computes from its own clock."""
    seconds_remaining = max(0, seconds_remaining)
    minutes, seconds = divmod(seconds_remaining, 60)
    return f"{answered} of {total} answered · reveal in {minutes}:{seconds:02d}"


def source_chip(question: QuizQuestion) -> str:
    """`ledger-migrations` — from PAY-1863 (SCREENS.md #06: "source chip
    (`ledger-migrations`, from `#payments-incidents`)"). Names the question's
    own concept plus the grounding artifact reference, the same reference
    W3's excerpt view resolves, so the chip and the click target it wires to
    agree on what "source" means."""
    ref = question.source_ref or "an ungrounded item"
    return f"`{question.concept}` — from {ref}"


class TeamQuizItemRegistry:
    """Item ids posted as *this* team-quiz round. Consulted by
    `forwarder.py`'s `submit_review` forwarder so a resolved answer to one of
    them is written `source = slack_thread` (the core derives `source` from
    the acting identity's platform, so sending `platform="slack_thread"` for
    exactly these item ids is enough — no header shape or schema changes).
    Cleared and re-marked each time a new round is posted — an item id from a
    prior day never lingers."""

    def __init__(self) -> None:
        self._ids: set[str] = set()
        self._lock = threading.Lock()

    def mark(self, item_ids: Sequence[str]) -> None:
        with self._lock:
            self._ids = set(item_ids)

    def clear(self) -> None:
        with self._lock:
            self._ids.clear()

    def is_quiz_item(self, item_id: Optional[str]) -> bool:
        with self._lock:
            return item_id in self._ids


@dataclass
class TeamQuizState:
    """The plugin's own team-quiz state (issue G1): one `QuizTally`, one
    `TeamQuizItemRegistry`, one `CorrectAnswerers`, created once at plugin
    start (`__init__.py::register`) and threaded through both the
    `submit_review` forwarder (collection) and whatever later issues the
    daily post or the on-demand reveal."""

    tally: QuizTally
    registry: TeamQuizItemRegistry
    correct_answerers: CorrectAnswerers


@dataclass(frozen=True)
class TeamQuizPost:
    """What `run_team_quiz` plans to post, plus the live status computed at
    call time."""

    concept: str
    questions: tuple[QuizQuestion, ...]
    chip: str
    confidence_prompts: tuple[dict, ...]
    question_prompts: tuple[dict, ...]
    answered_lines: tuple[str, ...]


def run_team_quiz(
    slugs: Sequence[str],
    *,
    tally: QuizTally,
    roster_size: int = DEFAULT_ROSTER_SIZE,
    reveal_seconds: int = DEFAULT_REVEAL_SECONDS,
    registry: Optional[TeamQuizItemRegistry] = None,
    items_path: Optional[Path] = None,
) -> TeamQuizPost:
    """Plan today's quiz post: for each item, the confidence picker before
    the tap, then the item itself. Marks `slugs` in `registry` so a resolved
    answer is later written `source = slack_thread`. Returns the plan plus
    the live "N of <roster_size> answered · reveal in <m:ss>" line per
    question, read from `tally` at call time — empty right after posting,
    moving as resolved answers land, same counts a later reveal reads."""
    questions = load_quiz_questions(slugs, items_path)
    if not questions:
        raise ValueError("run_team_quiz: no quiz items given")

    if registry is not None:
        registry.mark(slugs)

    concept = questions[0].concept
    chip = source_chip(questions[0])

    confidence_prompts = tuple(confidence_clarify_kwargs() for _ in questions)
    question_prompts = tuple(question_clarify_kwargs(question) for question in questions)
    answered_lines = tuple(
        answered_status_line(sum(tally.counts_for(question.item_id).values()), roster_size, reveal_seconds)
        for question in questions
    )

    return TeamQuizPost(
        concept=concept,
        questions=tuple(questions),
        chip=chip,
        confidence_prompts=confidence_prompts,
        question_prompts=question_prompts,
        answered_lines=answered_lines,
    )
