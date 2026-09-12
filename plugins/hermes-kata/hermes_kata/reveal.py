"""Team-quiz collection and manual reveal (spec §6/§8, AGCTM-69, issue G1
"post, collect, reveal", frames 06-07).

Collection rides the existing plumbing: a learner's tap resolves through
`clarify` (job 3) to `submit_review`, whose forwarder (`forwarder.py`) calls
`record_submit_review` here for every accepted `{"choice": <index>}`
response. This module never records *who* picked a given option — only
counts (`QuizTally`) — and separately tracks *who got it right*
(`CorrectAnswerers`), the one identity this plugin ever keeps against a quiz
answer (KATA-24: "never credits an answer to a name and never lists an
individual's wrong answer"). The reveal itself (`render_reveal`) is built on
demand — there is no timer in this plugin; something else (a slash command,
a cron-triggered turn) decides when to call it.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

BAR_LENGTH = 8
FILLED = "▓"
EMPTY = "░"


def _default_items_json_path() -> Path:
    override = os.environ.get("KATA_QUIZ_ITEMS_JSON")
    if override:
        return Path(override)
    # Vendored placeholder until Stage 2's content ingestion lands a real
    # item catalog (this issue "needs neither the web half of this stage nor
    # Stage 2's content ingestion") — same drop-in-override convention
    # `catalog.py` uses for `tools.json` via `KATA_TOOLS_JSON`.
    return Path(__file__).parent / "quiz_items.json"


def load_item_catalog(path: Optional[Path] = None) -> dict[str, dict]:
    path = path or _default_items_json_path()
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    return {item["item_id"]: item for item in items}


@dataclass(frozen=True)
class QuizQuestion:
    item_id: str
    position: int  # 1-based position in today's quiz, for the "N/total" header
    total_questions: int
    concept: str
    prompt: str
    options: Sequence[str]
    correct_index: int
    source_ref: Optional[str] = None  # e.g. "PAY-1863", for the source chip


def load_quiz_questions(slugs: Sequence[str], items_path: Optional[Path] = None) -> list[QuizQuestion]:
    """Today's questions, in `slugs` order, from the item catalog."""
    catalog = load_item_catalog(items_path)
    total = len(slugs)
    questions = []
    for position, item_id in enumerate(slugs, start=1):
        item = catalog[item_id]
        questions.append(
            QuizQuestion(
                item_id=item_id,
                position=position,
                total_questions=total,
                concept=item["concept"],
                prompt=item["prompt"],
                options=tuple(item["options"]),
                correct_index=item["correct_index"],
                source_ref=item.get("source_ref"),
            )
        )
    return questions


class QuizTally:
    """Per-(item, option) answer counts. Counts only — recording who picked
    what would break the privacy rule, so there is no method on this class
    that could (AGCTM-69)."""

    def __init__(self) -> None:
        self._counts: dict[str, dict[int, int]] = {}
        self._lock = threading.Lock()

    def record(self, item_id: str, option_index: int) -> None:
        with self._lock:
            item_counts = self._counts.setdefault(item_id, {})
            item_counts[option_index] = item_counts.get(option_index, 0) + 1

    def counts_for(self, item_id: str) -> dict[int, int]:
        with self._lock:
            return dict(self._counts.get(item_id, {}))

    def reset(self, item_id: str) -> None:
        with self._lock:
            self._counts.pop(item_id, None)


class CorrectAnswerers:
    """Per-item list of people who answered *correctly* — the one identity
    this plugin ever keeps against a quiz answer. A wrong answer never
    reaches this class: `record_submit_review` only calls `.record` here
    once it has already checked the response against the item's
    `correct_index`."""

    def __init__(self) -> None:
        self._names: dict[str, list[str]] = {}
        self._lock = threading.Lock()

    def record(self, item_id: str, name: str) -> None:
        with self._lock:
            names = self._names.setdefault(item_id, [])
            if name not in names:
                names.append(name)

    def names_for(self, item_id: str) -> list[str]:
        with self._lock:
            return list(self._names.get(item_id, []))

    def reset(self, item_id: str) -> None:
        with self._lock:
            self._names.pop(item_id, None)


def record_submit_review(
    tally: QuizTally,
    item_id: str,
    response: Mapping[str, Any],
    *,
    correct_answerers: Optional[CorrectAnswerers] = None,
    person_name: Optional[str] = None,
    catalog: Optional[Mapping[str, dict]] = None,
) -> None:
    """Update `tally` from a resolved `mcq` item's `submit_review` response
    (`{"choice": <index>}`). An `msq` response (`{"choices": [...]}`) or
    anything else is ignored — the quiz is `mcq`-only.

    When `correct_answerers` and `person_name` are both given, also credits
    `person_name` against `item_id`, but only when `choice` matches the
    item's `correct_index` — a wrong answer updates `tally` as always and
    never touches `correct_answerers`."""
    choice = response.get("choice")
    if choice is None:
        return
    choice = int(choice)
    tally.record(item_id, choice)

    if correct_answerers is None or person_name is None:
        return
    catalog = catalog if catalog is not None else load_item_catalog()
    item = catalog.get(item_id)
    if item is None:
        return
    if choice == item["correct_index"]:
        correct_answerers.record(item_id, person_name)


def _bar(count: int, total: int) -> str:
    filled = round(BAR_LENGTH * count / total) if total > 0 else 0
    filled = max(0, min(BAR_LENGTH, filled))
    return FILLED * filled + EMPTY * (BAR_LENGTH - filled)


def render_question(
    question: QuizQuestion, tally: QuizTally, *, correct_answerers: Optional[CorrectAnswerers] = None
) -> str:
    """One question block of the reveal: title with the `N/total`/`<correct>
    of <total>` chip, one line per option with a bar and its count, the
    correct option marked with a leading `✓`. When `correct_answerers` is
    given, appends a "Correct: ..." line crediting whoever answered it right
    by name — nothing is ever appended for anyone who answered wrong;
    `CorrectAnswerers` has no way to know who that was."""
    counts = tally.counts_for(question.item_id)
    total = sum(counts.values())
    correct_count = counts.get(question.correct_index, 0)

    lines = [f"{question.position}/{question.total_questions} · {question.prompt}  {correct_count} of {total}"]
    for index, option in enumerate(question.options):
        count = counts.get(index, 0)
        marker = "✓ " if index == question.correct_index else "  "
        lines.append(f"{marker}{option}  {_bar(count, total)}  {count}")
    if correct_answerers is not None:
        names = correct_answerers.names_for(question.item_id)
        if names:
            lines.append(f"Correct: {', '.join(names)}")
    return "\n".join(lines)


_MISSING_LEADERBOARD = "Leaderboard: not available yet — GET /team/overview has no points/streak data."
_MISSING_TEAM_NOTE = "Team note: not available yet — GET /team/overview has no concept-level state for this item."


def render_reveal(
    questions: Sequence[QuizQuestion],
    tally: QuizTally,
    *,
    team_note: Optional[str] = None,
    leaderboard: Optional[Sequence[Mapping[str, Any]]] = None,
    correct_answerers: Optional[CorrectAnswerers] = None,
    scheduled_concept: Optional[str] = None,
) -> str:
    """The full reveal message (frame 07): one block per question, then the
    team note, then the leaderboard — names only ever appear on the
    leaderboard and (when `correct_answerers` is passed) against a question
    they got *right*, never against an option chosen wrong. If either the
    team note or the leaderboard isn't available yet, say so instead of
    fabricating one.

    `scheduled_concept` names the one concept this reveal is scheduling a
    follow-up rep for; defaults to the quiz's own concept."""
    blocks = [render_question(q, tally, correct_answerers=correct_answerers) for q in questions]
    blocks.append(f"Team note. {team_note}" if team_note else _MISSING_TEAM_NOTE)
    concept_to_schedule = scheduled_concept or (questions[0].concept if questions else None)
    if concept_to_schedule:
        blocks.append(f"Scheduling a follow-up rep on `{concept_to_schedule}` for the team.")
    if leaderboard:
        lines = ["Leaderboard:"]
        for entry in leaderboard:
            lines.append(f"{entry['rank']}. {entry['name']} — {entry['points']}")
        blocks.append("\n".join(lines))
    else:
        blocks.append(_MISSING_LEADERBOARD)
    return "\n\n".join(blocks)
