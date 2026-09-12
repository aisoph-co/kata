"""Spec §4: the five-row guardrail table (KAT-S1/S2/S3, KAT-X3).

Unit tests exercise each pure function directly; `test_seeded_transcript_*`
below run all five rows together against one seeded debate transcript, via
`evaluate_guardrails` — the harness that will run KAT-X3's real eval set
(five recorded transcripts, 50 graded answers, AGCTM-16) once it lands. That
eval set had not landed when this issue was built, so the transcript here is
authored inline, per this issue's body: "ships the guardrail code and a test
harness that runs against whatever transcripts exist yet (even one synthetic
transcript authored inline)".
"""

from __future__ import annotations

import dataclasses

from fakes import FakePluginContext

from hermes_kata.guardrails import (
    BYPASS_GRADE_CAP,
    GUARDRAIL_ROWS,
    SECTION_ID,
    SKILL_ID,
    SKILL_PATH,
    SYSTEM_PROMPT_GUARDRAILS,
    DebateTurn,
    SeededTranscript,
    bypass_grade_is_capped,
    bypass_reply_is_compliant,
    concedes_before_next_question,
    evaluate_guardrails,
    is_bypass_phrase,
    is_one_question_per_turn,
    is_two_line_closing_summary,
    opens_with_question_only,
    register_guardrails_section,
    register_socratic_debate_skill,
    shares_long_run,
)

REFERENCE = (
    "A stale cache entry is one that no longer reflects the source of truth "
    "after the underlying data changed; overwriting it on the next write, "
    "rather than invalidating it immediately, is what lets callers observe "
    "stale data in between."
)


# Row 1 — never opens with the answer.
def test_opening_turn_with_only_a_question_passes():
    assert opens_with_question_only(
        "If two writes to the same cache key race, what should a reader see right after?", REFERENCE
    )


def test_opening_turn_restating_the_reference_fails():
    turn = (
        "A stale cache entry is one that no longer reflects the source of truth "
        "after the underlying data changed. Does that match what you expected?"
    )
    assert not opens_with_question_only(turn, REFERENCE)


def test_opening_turn_with_two_questions_fails():
    assert not opens_with_question_only("What is a stale read? Have you hit one before?", REFERENCE)


def test_shares_long_run_detects_an_eight_word_overlap_regardless_of_position():
    a = "overwriting it on the next write rather than invalidating it"
    assert shares_long_run(a, REFERENCE)
    assert not shares_long_run("a totally unrelated sentence about pizza toppings today", REFERENCE)


# Row 2 — one question per turn.
def test_single_question_turn_passes():
    assert is_one_question_per_turn("So what would a third reader see in that window?")


def test_zero_or_multiple_questions_fail():
    assert not is_one_question_per_turn("Here is a statement with no question.")
    assert not is_one_question_per_turn("Is that right? Are you sure?")


# Row 3 — concedes when the learner is right.
def test_concession_before_next_question_passes():
    assert concedes_before_next_question("Exactly — that race is what causes the stale read. What would you check?")


def test_no_concession_phrase_fails():
    assert not concedes_before_next_question("Okay. What about the other write?")


def test_concession_after_a_question_in_the_same_turn_fails():
    text = "What would you check first? Exactly, that's it."
    assert not concedes_before_next_question(text)


# Row 4 — "just tell me" is honoured, logged, still followed by one question.
def test_bypass_phrase_detection():
    assert is_bypass_phrase("ugh, just tell me")
    assert is_bypass_phrase("Just give me the answer already")
    assert not is_bypass_phrase("I think I know the answer")


def test_bypass_reply_gives_answer_then_asks_exactly_one_question():
    reply = "A write-ordering version check on each key. Does that match what you were expecting?"
    assert bypass_reply_is_compliant(reply)


def test_bypass_reply_with_no_question_fails():
    assert not bypass_reply_is_compliant("A write-ordering version check on each key.")


def test_bypass_reply_with_no_answer_text_fails():
    assert not bypass_reply_is_compliant("?")


def test_bypass_grade_is_capped():
    assert bypass_grade_is_capped(0.0)
    assert bypass_grade_is_capped(BYPASS_GRADE_CAP)
    assert not bypass_grade_is_capped(0.31)
    assert not bypass_grade_is_capped(1.0)


# Row 5 — closes with a two-line summary and a scheduled retrieval question.
def test_two_line_closing_summary_passes():
    closing = "You found the race between the two writes.\nNext time: invalidation across replicas.\n\nScheduled a review."
    assert is_two_line_closing_summary(closing)


def test_closing_summary_with_wrong_line_count_fails():
    assert not is_two_line_closing_summary("You found it today.\n\nScheduled a review.")
    assert not is_two_line_closing_summary("Line one.\nLine two.\nLine three.\n\nScheduled a review.")


# Wiring — without this, SYSTEM_PROMPT_GUARDRAILS is defined but never
# reaches the live prompt.
def test_register_guardrails_section_puts_the_guardrail_text_in_the_prompt():
    ctx = FakePluginContext()
    register_guardrails_section(ctx)
    assert ctx.system_prompt_sections[SECTION_ID]["content"] == SYSTEM_PROMPT_GUARDRAILS
    assert ctx.system_prompt_sections[SECTION_ID]["position"] == "after_memory"


# The `socratic-debate` skill — registered, not just present on disk (a
# `SKILL.md` file with nothing calling `register_skill` would sit unused,
# the same failure mode fixed above for `SYSTEM_PROMPT_GUARDRAILS`).
def test_socratic_debate_skill_file_exists_and_has_frontmatter():
    content = SKILL_PATH.read_text()
    assert content.startswith("---\n")
    assert f"name: {SKILL_ID}" in content


def test_register_socratic_debate_skill_registers_the_bundled_file():
    ctx = FakePluginContext()
    register_socratic_debate_skill(ctx)
    assert ctx.skills[SKILL_ID] == SKILL_PATH


# --- Seeded transcript: all five rows run together (KAT-X3's harness shape) ---

SEEDED_TRANSCRIPT = SeededTranscript(
    reference=REFERENCE,
    turns=(
        DebateTurn(
            "kata",
            "If two requests write to the same cache key milliseconds apart, what "
            "should a third request reading right after see?",
        ),
        DebateTurn("learner", "I think the cache just keeps whatever was written most recently."),
        DebateTurn(
            "kata",
            "If the second write actually started before the first one finished, "
            "could 'most recent' still be wrong?",
        ),
        DebateTurn(
            "learner",
            "Oh — if the writes raced, the cache could end up holding the older "
            "value even though it looks like it was written last, so it's stale.",
        ),
        DebateTurn(
            "kata",
            "Exactly — a race between the two writes can leave a newer-looking read "
            "actually wrong. What would you check to tell the two writes apart?",
        ),
        DebateTurn("learner", "just tell me"),
        DebateTurn(
            "kata",
            "A write-ordering version on each key, so the cache only accepts a "
            "write if its version is newer than what's stored. Does that match "
            "what you were expecting?",
        ),
        DebateTurn(
            "kata",
            "You connected the stale read to a missing write-ordering guard.\n"
            "Next time we'll look at invalidation across replicas.\n\n"
            "Scheduled a review on CACHE-CONSISTENCY-1.",
        ),
    ),
    concession_turn=4,
    bypass_learner_turn=5,
    bypass_reply_turn=6,
    bypass_grade=BYPASS_GRADE_CAP,
    closing_turn=7,
)


def test_seeded_transcript_passes_all_five_guardrail_rows():
    results = evaluate_guardrails(SEEDED_TRANSCRIPT)
    assert set(results) == set(GUARDRAIL_ROWS)
    assert all(results.values()), results


def test_seeded_transcript_with_a_declarative_opening_fails_only_the_never_answers_first_row():
    # Proves the harness isn't vacuous: an opening turn that states the
    # reference's own claim (rather than asking about it) must fail row 1,
    # with the rest of the transcript untouched.
    bad_opening = DebateTurn(
        "kata",
        "A stale cache entry is one that no longer reflects the source of truth "
        "after the underlying data changed. Does that match what you expected?",
    )
    transcript = dataclasses.replace(
        SEEDED_TRANSCRIPT, turns=(bad_opening,) + SEEDED_TRANSCRIPT.turns[1:]
    )

    results = evaluate_guardrails(transcript)

    assert results["never_opens_with_answer"] is False
    passing_rows = {row: passed for row, passed in results.items() if row != "never_opens_with_answer"}
    assert all(passing_rows.values()), passing_rows
