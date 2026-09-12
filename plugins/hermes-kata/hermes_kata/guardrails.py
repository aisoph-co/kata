"""Socratic guardrails as tests (spec §4).

The bypass-phrase list, the concession-phrase list, and the "≥ 8
consecutive words" overlap threshold are constants here, not scattered
across the system prompt, so the system-prompt text and the test
assertions read the same source of truth and cannot drift.

`Transcript`/`Turn` are the minimal shape a test needs to run the five
guardrail assertions from spec §4 against a debate/teach-back exchange —
real or, until KAT-X3's five recorded transcripts (AGCTM-16) land, a
synthetic one authored inline in the test.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# --- constants (spec §4, "first cut for the demo team's dialect") ---------

BYPASS_PHRASES = [
    "just tell me",
    "just give me the answer",
    "can you just say it",
    "i give up",
    "skip to the answer",
]

CONCESSION_PHRASES = [
    "you're right",
    "you are right",
    "exactly",
    "that's it",
    "that's correct",
    "nailed it",
    "spot on",
]

OVERLAP_THRESHOLD = 8  # consecutive shared words that mean "this is the answer"
BYPASS_GRADE_CAP = 0.3  # core: bypass caps mastery, KAT-S2

_BYPASS_PATTERN = re.compile("|".join(re.escape(p) for p in BYPASS_PHRASES), re.IGNORECASE)

# --- system-prompt rules (same constants, stated as instructions) ---------

SOCRATIC_GUARDRAIL_INSTRUCTION = f"""\
In a debate, or a `short_answer`/`teach_back` item, follow these rules:
1. Never open with the answer: your first turn is a question about the \
concept — no declarative claim, exactly one `?`.
2. One question per turn: ask exactly one question, then stop and wait.
3. Concede when the learner is right: if their stated reasoning is \
correct, say so plainly (e.g. {", ".join(repr(p) for p in CONCESSION_PHRASES)}) \
before asking anything else.
4. Honour "just tell me" or an equivalent (a fixed list of phrasings): \
give the answer immediately, no lecture, then ask exactly one closing \
question. Call submit_review with the answer as `response` and a grade \
capped at {BYPASS_GRADE_CAP} — a bypass never earns full mastery credit.
5. Close every debate with exactly two lines naming what changed, then a \
`review` call against a real item in the concept under debate. A debate \
that ends with no such call is a failed debate, not a silent pass.
"""


def register_guardrail_prompt(ctx) -> None:
    ctx.register_system_prompt_section(
        "kata-socratic-guardrails",
        lambda session_info: SOCRATIC_GUARDRAIL_INSTRUCTION,
        position="after_memory",
    )


# --- transcript shape -------------------------------------------------


@dataclass
class Turn:
    role: str  # "assistant" | "learner"
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    correct: bool = False  # learner turn only: reasoning graded correct per rubric
    is_closing: bool = False  # assistant turn only: the closing summary turn


@dataclass
class Transcript:
    item: dict[str, Any]  # {"concept_id", "reference", "explanation", ...}
    turns: list[Turn]


def submit_review_calls(turn: Turn) -> list[dict[str, Any]]:
    return [call for call in turn.tool_calls if call.get("name") == "submit_review"]


def is_bypass_phrase(text: str) -> bool:
    return _BYPASS_PATTERN.search(text) is not None


def _normalize_words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _shares_long_word_overlap(a: str, b: str, threshold: int = OVERLAP_THRESHOLD) -> bool:
    words_a, words_b = _normalize_words(a), _normalize_words(b)
    if len(words_a) < threshold or len(words_b) < threshold:
        return False
    windows_b = {tuple(words_b[i : i + threshold]) for i in range(len(words_b) - threshold + 1)}
    return any(
        tuple(words_a[i : i + threshold]) in windows_b
        for i in range(len(words_a) - threshold + 1)
    )


def _contains_concession_before_question(text: str) -> bool:
    question_pos = text.find("?")
    lower = text.lower()
    for phrase in CONCESSION_PHRASES:
        pos = lower.find(phrase.lower())
        if pos != -1 and (question_pos == -1 or pos < question_pos):
            return True
    return False


def closing_message_is_two_line_summary(text: str) -> bool:
    """The summary is the paragraph before any scheduling note — a blank
    line separates the two. Exactly two non-empty lines in that first
    paragraph, whatever comes after."""
    summary = text.strip().split("\n\n", 1)[0]
    lines = [line for line in summary.split("\n") if line.strip()]
    return len(lines) == 2


# --- the five guardrail assertions (spec §4 table, in order) --------------


def never_opens_with_the_answer(transcript: Transcript) -> bool:
    if not transcript.turns:
        return False
    opening = transcript.turns[0]
    if opening.role != "assistant" or opening.text.count("?") != 1:
        return False
    references = [transcript.item.get("reference"), transcript.item.get("explanation")]
    return not any(
        _shares_long_word_overlap(opening.text, ref) for ref in references if ref
    )


def one_question_per_turn(transcript: Transcript) -> bool:
    return all(
        turn.text.count("?") == 1
        for turn in transcript.turns
        if turn.role == "assistant" and not turn.is_closing
    )


def concedes_when_learner_is_right(transcript: Transcript) -> bool:
    turns = transcript.turns
    for i, turn in enumerate(turns):
        if turn.role != "learner" or not turn.correct:
            continue
        if i + 1 >= len(turns) or turns[i + 1].role != "assistant":
            return False
        if not _contains_concession_before_question(turns[i + 1].text):
            return False
    return True


def bypass_is_honoured(transcript: Transcript) -> bool:
    turns = transcript.turns
    for i, turn in enumerate(turns):
        if turn.role != "learner" or not is_bypass_phrase(turn.text):
            continue
        if i + 1 >= len(turns) or turns[i + 1].role != "assistant":
            return False
        reply = turns[i + 1]
        calls = submit_review_calls(reply)
        if not calls:
            return False
        if not any(call.get("args", {}).get("response") for call in calls):
            return False
        if not any(call.get("args", {}).get("grade", 1.0) <= BYPASS_GRADE_CAP for call in calls):
            return False
        if reply.text.count("?") != 1:
            return False
    return True


def closes_with_summary_and_scheduled_review(transcript: Transcript) -> bool:
    closing_turns = [turn for turn in transcript.turns if turn.is_closing]
    if not closing_turns:
        return False
    closing = closing_turns[-1]
    if not closing_message_is_two_line_summary(closing.text):
        return False
    concept_id = transcript.item.get("concept_id")
    valid_kinds = {"short_answer", "self_rated"}
    return any(
        call.get("args", {}).get("concept_id") == concept_id
        and call.get("args", {}).get("kind") in valid_kinds
        for call in submit_review_calls(closing)
    )


ALL_GUARDRAILS = [
    never_opens_with_the_answer,
    one_question_per_turn,
    concedes_when_learner_is_right,
    bypass_is_honoured,
    closes_with_summary_and_scheduled_review,
]
