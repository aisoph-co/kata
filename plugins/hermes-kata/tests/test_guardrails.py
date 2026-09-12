"""§4 Socratic guardrail tests.

KAT-X3's five recorded Socratic eval transcripts and 50 graded answers
(AGCTM-16) are a separate eval-set deliverable and had not landed when this
harness was built. Per KATA-10, this ships the guardrail *code* plus a test
harness run against one synthetic transcript authored inline below —
re-run against the real eval set the moment AGCTM-16 lands.

Done check: the seeded transcript passes all five guardrail assertions;
a transcript with an opening declarative claim fails only the first,
proving the test isn't vacuous.
"""
from hermes_kata.guardrails import (
    ALL_GUARDRAILS,
    BYPASS_GRADE_CAP,
    bypass_is_honoured,
    closes_with_summary_and_scheduled_review,
    concedes_when_learner_is_right,
    is_bypass_phrase,
    never_opens_with_the_answer,
    one_question_per_turn,
)
from hermes_kata.guardrails import Transcript, Turn

ITEM = {
    "id": "item-42",
    "concept_id": "concept-ptr-ub",
    "kind": "debate",
    "reference": "Incrementing a pointer past the end of an array is undefined behavior in C.",
    "explanation": (
        "Undefined behavior means the compiler may assume that path never "
        "happens and optimize accordingly."
    ),
}


def _seeded_transcript() -> Transcript:
    """One debate covering all five guardrail beats: opens with a
    question, one question per turn, concedes a correct claim, honours a
    bypass with a capped review, and closes with a two-line summary plus
    a scheduled review against a fresh item in the same concept."""
    return Transcript(
        item=ITEM,
        turns=[
            Turn(
                role="assistant",
                text=(
                    "What do you think happens when a pointer is incremented "
                    "past the end of an array in C?"
                ),
            ),
            Turn(
                role="learner",
                text=(
                    "I think it's undefined behavior because the standard "
                    "doesn't guarantee what happens after that."
                ),
                correct=True,
            ),
            Turn(
                role="assistant",
                text=(
                    "You're right — that's undefined behavior. What could a "
                    "compiler assume once it decides that path never happens?"
                ),
            ),
            Turn(
                role="learner",
                text="Just tell me the short version, I don't need the compiler theory.",
            ),
            Turn(
                role="assistant",
                text=(
                    "The compiler may assume the increment never leaves the "
                    "array and skip the bounds check, which can corrupt "
                    "memory. Want to check that against one more example?"
                ),
                tool_calls=[
                    {
                        "name": "submit_review",
                        "args": {
                            "item_id": "item-42",
                            "concept_id": "concept-ptr-ub",
                            "kind": "debate",
                            "response": {"note": "bypassed"},
                            "grade": 0.3,
                        },
                    }
                ],
            ),
            Turn(role="learner", text="Got it, that makes sense. One more check sounds good."),
            Turn(
                role="assistant",
                text=(
                    "You now see why pointer overrun is undefined behavior.\n"
                    "That bypass is capped so it won't inflate mastery.\n\n"
                    "Next review will retest this concept in three days."
                ),
                is_closing=True,
                tool_calls=[
                    {
                        "name": "submit_review",
                        "args": {
                            "item_id": "item-77",
                            "concept_id": "concept-ptr-ub",
                            "kind": "short_answer",
                            "response": {"text": "undefined behavior"},
                            "grade": 0.9,
                        },
                    }
                ],
            ),
        ],
    )


def test_seeded_transcript_passes_all_five_guardrails():
    transcript = _seeded_transcript()

    assert never_opens_with_the_answer(transcript)
    assert one_question_per_turn(transcript)
    assert concedes_when_learner_is_right(transcript)
    assert bypass_is_honoured(transcript)
    assert closes_with_summary_and_scheduled_review(transcript)
    assert all(guardrail(transcript) for guardrail in ALL_GUARDRAILS)


def test_opening_declarative_claim_fails_the_never_opens_with_answer_check():
    """Proves the test isn't vacuous: an opening turn that states the
    reference answer (long word-for-word overlap) must fail rule 1 even
    though every other guardrail still passes."""
    transcript = _seeded_transcript()
    transcript.turns[0] = Turn(
        role="assistant",
        text=(
            "Incrementing a pointer past the end of an array is undefined "
            "behavior in C — so what do you think that implies?"
        ),
    )

    assert not never_opens_with_the_answer(transcript)
    # the rest of the transcript is untouched, so it isn't a vacuous fail-everything case
    assert one_question_per_turn(transcript)
    assert concedes_when_learner_is_right(transcript)
    assert bypass_is_honoured(transcript)
    assert closes_with_summary_and_scheduled_review(transcript)


def test_second_question_in_a_turn_fails_one_question_per_turn():
    transcript = _seeded_transcript()
    transcript.turns[2] = Turn(
        role="assistant",
        text="You're right. What could go wrong? And what about the compiler's optimizer?",
    )

    assert not one_question_per_turn(transcript)


def test_no_concession_after_a_correct_claim_fails():
    transcript = _seeded_transcript()
    transcript.turns[2] = Turn(
        role="assistant",
        text="What could a compiler assume once it decides that path never happens?",
    )

    assert not concedes_when_learner_is_right(transcript)


def test_bypass_without_a_capped_review_fails():
    transcript = _seeded_transcript()
    transcript.turns[4].tool_calls[0]["args"]["grade"] = 1.0

    assert not bypass_is_honoured(transcript)
    assert transcript.turns[4].tool_calls[0]["args"]["grade"] > BYPASS_GRADE_CAP


def test_missing_scheduled_review_at_close_fails_not_silently_accepted():
    transcript = _seeded_transcript()
    transcript.turns[-1].tool_calls = []

    assert not closes_with_summary_and_scheduled_review(transcript)


def test_is_bypass_phrase_matches_the_fixed_list_case_insensitively():
    assert is_bypass_phrase("Just Tell Me already")
    assert is_bypass_phrase("I give up, what's the answer?")
    assert not is_bypass_phrase("I think it's undefined behavior")
