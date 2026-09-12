"""Job 3's Socratic half (adapter-contract), formalized: the five-row
guardrail table (spec §4, `docs/personas-and-user-stories.md` KAT-S1/S2/S3,
KAT-X3) as constants and pure functions a test can assert against, plus the
system-prompt text that states the same rules to Kata. One source of truth
for both, so the prompt wording and the check can't drift apart (spec §4:
"not scattered across the system prompt").

KAT-X3's real eval set (AGCTM-16: five recorded Socratic transcripts, 50
graded answers) is tracked separately and may not have landed yet — this
module also ships `evaluate_guardrails`, a small harness that runs the same
five assertions against a `SeededTranscript`, plus one authored inline in
`tests/test_guardrails.py`. Re-run the harness unchanged against the real
transcripts once AGCTM-16 lands; nothing here should need to change shape.

This module is also where the `socratic-debate` skill (the turn-by-turn
playbook `SKILL.md` bundled alongside this package) gets wired into Hermes,
via `register_socratic_debate_skill` — both registrations
(`register_guardrails_section` for the system-prompt text, this one for the
skill) are called from `__init__.py`'s `register()`; without that wiring the
rules and the playbook exist on disk but never reach a live turn.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

# "Just tell me" and its equivalents (spec §4, row 4). A first cut for the
# demo team's dialect — spec's "Open items" section expects this list to get
# tuned against real transcripts before ship without changing its shape.
BYPASS_PHRASES: tuple[str, ...] = (
    "just tell me",
    "just give me the answer",
    "tell me the answer",
    "skip to the answer",
    "i give up",
)

# Concession phrases (spec §4, row 3) — a turn following a correct learner
# claim must contain one of these before any further question.
CONCESSION_PHRASES: tuple[str, ...] = (
    "you're right",
    "you are right",
    "exactly",
    "that's it",
    "that's correct",
    "correct!",
    "spot on",
)

# "≥ 8 consecutive words" overlap threshold (spec §4, row 1).
OVERLAP_WORD_THRESHOLD = 8

# Grade cap applied when `submit_review` follows a bypass phrase (spec §4,
# row 4: "bypass caps mastery").
BYPASS_GRADE_CAP = 0.3

SECTION_ID = "kata-guardrails"
MAX_CHARS = 2000

# The `socratic-debate` skill ships inside this plugin's own directory
# (`plugins/hermes-kata/skills/socratic-debate/SKILL.md`), a sibling of this
# `hermes_kata/` package, not a separate deploy step. Hermes plugins
# register skills programmatically (`ctx.register_skill(name, content)` in
# `register()`); the loader namespaces it by the plugin's `plugin.yaml` name
# as `hermes-kata:socratic-debate` — the id `build-day/scripts/
# start-demo-dm.sh`'s `--skill` flag passes.
SKILL_ID = "socratic-debate"
SKILL_PATH = Path(__file__).resolve().parent.parent / "skills" / SKILL_ID / "SKILL.md"

SYSTEM_PROMPT_GUARDRAILS = """\
Socratic guardrails — follow every one of these on every turn of a debate,
short_answer, or teach_back item:
1. Never open with the answer. Your first turn asks a question; it never
   states the answer or a declarative claim about the concept.
2. Ask exactly one question per turn, then stop and wait for the learner.
3. When the learner's stated reasoning is correct, say so plainly (e.g.
   "you're right", "exactly") before continuing or closing.
4. If the learner says "just tell me" (or an equivalent), give the answer
   immediately with no lecture, then ask exactly one closing question.
5. End every debate/teach-back with exactly two lines naming what changed,
   then a review against a real item in the concept under debate.
"""


def count_questions(text: str) -> int:
    return text.count("?")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


def shares_long_run(a: str, b: str, threshold: int = OVERLAP_WORD_THRESHOLD) -> bool:
    """True if `a` and `b` share a run of `threshold`-or-more consecutive
    words (spec §4, row 1's overlap check)."""
    wa, wb = _words(a), _words(b)
    if len(wa) < threshold or len(wb) < threshold:
        return False
    b_ngrams = {tuple(wb[i : i + threshold]) for i in range(len(wb) - threshold + 1)}
    return any(tuple(wa[i : i + threshold]) in b_ngrams for i in range(len(wa) - threshold + 1))


def opens_with_question_only(turn_text: str, reference: str) -> bool:
    """Row 1: exactly one `?`, and no sentence shares >= threshold
    consecutive words with the item's reference/explanation field."""
    if count_questions(turn_text) != 1:
        return False
    return not any(shares_long_run(sentence, reference) for sentence in _sentences(turn_text))


def is_one_question_per_turn(turn_text: str) -> bool:
    """Row 2 (applies to every assistant turn except the closing summary)."""
    return count_questions(turn_text) == 1


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in phrases)


def is_bypass_phrase(text: str) -> bool:
    return _contains_any(text, BYPASS_PHRASES)


def concedes_before_next_question(turn_text: str) -> bool:
    """Row 3: a concession phrase is present, and comes before the first
    question in the turn (a closing turn with no question at all still
    counts, as long as the concession is there)."""
    lowered = turn_text.lower()
    concession_positions = [lowered.find(phrase) for phrase in CONCESSION_PHRASES if phrase in lowered]
    if not concession_positions:
        return False
    first_concession = min(concession_positions)
    first_question = turn_text.find("?")
    return first_question == -1 or first_concession < first_question


def bypass_reply_is_compliant(reply_text: str) -> bool:
    """Row 4: exactly one `?` (the closing question), asked after some
    non-empty answer text — i.e. the answer comes first, with no lecture,
    and the turn still closes with one question."""
    if count_questions(reply_text) != 1:
        return False
    answer_text = reply_text.split("?")[0]
    return bool(answer_text.strip())


def bypass_grade_is_capped(grade: float, cap: float = BYPASS_GRADE_CAP) -> bool:
    return grade <= cap


def register_guardrails_section(ctx: Any) -> None:
    """Wire `SYSTEM_PROMPT_GUARDRAILS` into the live system prompt (same
    `after_memory` position `mcq.py`'s rendering section and `identity.py`'s
    notes section use — the only position Hermes currently supports).
    Called from `__init__.py`'s `register()`."""
    ctx.register_system_prompt_section(
        SECTION_ID,
        SYSTEM_PROMPT_GUARDRAILS,
        position="after_memory",
        max_chars=MAX_CHARS,
    )


def register_socratic_debate_skill(ctx: Any, skill_path: Path = SKILL_PATH) -> None:
    """Reads the bundled `SKILL.md` and hands its content to Hermes's own
    skill registry, namespaced by the plugin as `hermes-kata:socratic-debate`.
    Without this call the file sits on disk unused — the same failure mode
    `register_guardrails_section` fixed for `SYSTEM_PROMPT_GUARDRAILS`."""
    ctx.register_skill(SKILL_ID, skill_path.read_text())


def is_two_line_closing_summary(closing_text: str, scheduling_marker: str = "\n\n") -> bool:
    """Row 5: the closing message is exactly two non-empty lines before any
    scheduling note. `scheduling_marker` splits the summary from whatever
    scheduling text follows it (a blank line, by convention)."""
    summary_part = closing_text.split(scheduling_marker, 1)[0]
    lines = [line for line in summary_part.splitlines() if line.strip()]
    return len(lines) == 2


@dataclass(frozen=True)
class DebateTurn:
    speaker: str  # "kata" or "learner"
    text: str


@dataclass(frozen=True)
class SeededTranscript:
    """One debate transcript, seeded inline. Indices point at the turns each
    guardrail row needs context for — which turn is the concession, which
    pair is the bypass exchange, which turn closes the debate — since a
    synthetic transcript has no grading rubric to derive that from."""

    reference: str
    turns: tuple[DebateTurn, ...]
    concession_turn: int
    bypass_learner_turn: int
    bypass_reply_turn: int
    bypass_grade: float
    closing_turn: int


GuardrailResults = dict[str, bool]

GUARDRAIL_ROWS: tuple[str, ...] = (
    "never_opens_with_answer",
    "one_question_per_turn",
    "concedes_when_learner_is_right",
    "bypass_is_honoured",
    "closes_with_two_line_summary",
)


def evaluate_guardrails(transcript: SeededTranscript) -> GuardrailResults:
    """Run all five guardrail-table rows (spec §4) against one seeded
    transcript, keyed by `GUARDRAIL_ROWS`. This is the harness KAT-X3's real
    eval set (five recorded transcripts, 50 graded answers) runs unchanged
    once AGCTM-16 lands — until then it runs against transcripts authored
    inline, one seeded here."""
    kata_turns = [t for t in transcript.turns if t.speaker == "kata"]
    if not kata_turns:
        raise ValueError("evaluate_guardrails: transcript has no kata turns")

    opening_turn = kata_turns[0]
    closing_turn = transcript.turns[transcript.closing_turn]
    concession_turn = transcript.turns[transcript.concession_turn]
    bypass_learner_turn = transcript.turns[transcript.bypass_learner_turn]
    bypass_reply_turn = transcript.turns[transcript.bypass_reply_turn]

    # Row 2 covers every kata turn except the closing summary.
    non_closing_kata_turns = [t for t in kata_turns if t is not closing_turn]

    return {
        "never_opens_with_answer": opens_with_question_only(opening_turn.text, transcript.reference),
        "one_question_per_turn": all(is_one_question_per_turn(t.text) for t in non_closing_kata_turns),
        "concedes_when_learner_is_right": concedes_before_next_question(concession_turn.text),
        "bypass_is_honoured": (
            is_bypass_phrase(bypass_learner_turn.text)
            and bypass_reply_is_compliant(bypass_reply_turn.text)
            and bypass_grade_is_capped(transcript.bypass_grade)
        ),
        "closes_with_two_line_summary": is_two_line_closing_summary(closing_turn.text),
    }
