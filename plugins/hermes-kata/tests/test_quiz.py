"""Spec §6/§8, frames 06-07: the daily team-quiz question posts as `clarify`
Block Kit buttons with a confidence gate, an "N of 9 answered" line, and a
source chip; the reveal is presenter-triggered (`/kata-reveal`), states a
team-level count per option, names one concept to schedule, shows the
leaderboard, and never attributes an answer to a person.

`AUDIENCE`/the counts below mirror this issue's own done check and the
Ferry seed's sprint-history beat: nine reports (Quinn, the tech lead,
doesn't answer their own team's quiz), four of nine can explain the lock,
one of nine can explain why the dry run matters.
"""

from __future__ import annotations

import pytest
from fakes import FakeLearningServiceClient

from hermes_kata.quiz import (
    QUIZ_ANSWER_SOURCE_PLATFORM,
    DailyQuestion,
    LeaderboardEntry,
    QuizSession,
    SourceChip,
    announcement_kwargs,
    answered_line,
    build_reveal,
    handle_reveal_command,
    record_answer,
    render_reveal_blocks,
    source_chip_text,
    submit_quiz_answer,
)

AUDIENCE = [f"p{i}" for i in range(2, 11)]  # nine reports, Quinn (p1) excluded

QUESTION = DailyQuestion(
    id="item-lock-migration",
    prompt="Before `add_posting_currency` goes back in, what must change?",
    options=["Chunk the backfill and run it off-peak", "Nothing — just re-run it", "Add a lock timeout"],
    concept_id="concept-migrations",
    correct_index=0,
    source=SourceChip(label="PAY-1863", thread_ref="sprint-42 · reverted migration"),
)


def _session() -> QuizSession:
    return QuizSession(question=QUESTION, audience=AUDIENCE)


def test_announcement_uses_clarify_with_a_confidence_gate():
    session = _session()
    kwargs = announcement_kwargs(session)

    assert kwargs["question"] == QUESTION.prompt
    assert kwargs["choices"] == QUESTION.options
    assert kwargs["multi_select"] is False
    assert kwargs["confidence_scale"] == (1, 5)


def test_answered_line_starts_at_zero_of_nine():
    assert answered_line(_session()) == "0 of 9 answered"


def test_source_chip_names_the_originating_thread():
    assert source_chip_text(_session()) == "PAY-1863 · sprint-42 · reverted migration"


def test_record_answer_advances_the_answered_line():
    session = _session()
    record_answer(session, "p2", 0, confidence=4)

    assert answered_line(session) == "1 of 9 answered"


def test_record_answer_refuses_someone_outside_the_audience():
    session = _session()
    with pytest.raises(ValueError):
        record_answer(session, "p1", 0, confidence=3)  # Quinn — not in AUDIENCE


def test_record_answer_refuses_confidence_outside_one_to_five():
    session = _session()
    with pytest.raises(ValueError):
        record_answer(session, "p2", 0, confidence=6)


def test_submit_quiz_answer_grades_through_reviews_then_tracks_locally():
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/reviews", {"grade": 1.0, "correct": True})
    session = _session()

    result = submit_quiz_answer(
        client,
        session,
        person_id="p2",
        external_id="U0FERRY02",
        option_index=0,
        confidence=4,
        idempotency_key="quiz-p2-1",
    )

    assert result == {"grade": 1.0, "correct": True}
    assert session.answers["p2"] == 0
    call = client.calls[-1]
    assert call["path"] == "/me/reviews"
    assert call["json_body"] == {
        "item_id": "item-lock-migration",
        "idempotency_key": "quiz-p2-1",
        "response": {"choice": 0},
    }


def test_submit_quiz_answer_never_asserts_the_persons_own_platform():
    # The bug the reviewer caught: sending `platform="slack"` (a learner's
    # real DM platform) here would land `review.source = "slack_dm"`
    # server-side, not `slack_thread` — this asserts the identity actually
    # sent, not just that some review call happened.
    client = FakeLearningServiceClient()
    client.set_response("POST", "/me/reviews", {"grade": 1.0, "correct": True})
    session = _session()

    submit_quiz_answer(
        client,
        session,
        person_id="p2",
        external_id="U0FERRY02",
        option_index=0,
        confidence=4,
        idempotency_key="quiz-p2-1",
    )

    identity = client.calls[-1]["identity"]
    assert identity.platform == QUIZ_ANSWER_SOURCE_PLATFORM
    assert identity.platform != "slack"
    assert identity.external_id == "U0FERRY02"


def _answer_the_ferry_beat(session: QuizSession) -> None:
    # Four of nine pick the correct (index 0) option, one picks index 2
    # ("add a lock timeout" — explains the dry run's caution but not the
    # lock itself), the remaining four don't answer.
    for person_id in AUDIENCE[:4]:
        record_answer(session, person_id, 0, confidence=4)
    record_answer(session, AUDIENCE[4], 2, confidence=2)


def test_reveal_states_four_of_nine_and_one_of_nine_exactly():
    session = _session()
    _answer_the_ferry_beat(session)

    reveal = build_reveal(
        session,
        concept_to_schedule="concept-migrations",
        leaderboard=[LeaderboardEntry(display_name="Daniel Okonkwo", score=42)],
    )

    lines = [option["line"] for option in reveal["options"]]
    assert any(line.startswith("4 of 9 picked") for line in lines)
    assert any(line.startswith("1 of 9 picked") for line in lines)
    assert reveal["concept_to_schedule"] == "concept-migrations"


def test_reveal_never_attributes_an_answer_to_a_person():
    session = _session()
    _answer_the_ferry_beat(session)

    reveal = build_reveal(session, concept_to_schedule="concept-migrations", leaderboard=[])

    dumped = str(reveal)
    for person_id in AUDIENCE:
        assert person_id not in dumped


def test_reveal_shows_the_leaderboard_by_name_not_by_question_answer():
    session = _session()
    _answer_the_ferry_beat(session)

    reveal = build_reveal(
        session,
        concept_to_schedule="concept-migrations",
        leaderboard=[LeaderboardEntry(display_name="Daniel Okonkwo", score=42)],
    )

    assert reveal["leaderboard"] == [{"display_name": "Daniel Okonkwo", "score": 42}]


def test_reveal_marks_the_session_revealed_and_refuses_a_later_tap():
    session = _session()
    _answer_the_ferry_beat(session)
    build_reveal(session, concept_to_schedule="concept-migrations", leaderboard=[])

    assert session.revealed is True
    with pytest.raises(ValueError):
        record_answer(session, AUDIENCE[5], 0, confidence=3)


def test_handle_reveal_command_refuses_a_non_manager_presenter():
    session = _session()
    _answer_the_ferry_beat(session)

    with pytest.raises(PermissionError):
        handle_reveal_command(
            session, requested_by_is_manager=False, concept_to_schedule="concept-migrations", leaderboard=[]
        )
    assert session.revealed is False  # refused before any state changed


def test_handle_reveal_command_is_presenter_triggered_not_a_timer_and_refuses_a_second_reveal():
    session = _session()
    _answer_the_ferry_beat(session)

    first = handle_reveal_command(
        session, requested_by_is_manager=True, concept_to_schedule="concept-migrations", leaderboard=[]
    )
    question_block_text = first["blocks"][1]["text"]["text"]
    assert "*4*  ✅ *Chunk the backfill and run it off-peak*" in question_block_text

    with pytest.raises(ValueError):
        handle_reveal_command(
            session, requested_by_is_manager=True, concept_to_schedule="concept-migrations", leaderboard=[]
        )


def test_render_reveal_blocks_matches_the_kata_reveal_blockkit_template():
    session = _session()
    _answer_the_ferry_beat(session)
    reveal = build_reveal(
        session,
        concept_to_schedule="concept-migrations",
        leaderboard=[LeaderboardEntry(display_name="Daniel Okonkwo", score=42)],
    )

    message = render_reveal_blocks(session, reveal, team_note="Chunking showed up; the lock itself didn't.")

    header_text = message["blocks"][0]["text"]["text"]
    assert header_text.startswith("*Before `add_posting_currency` goes back in, what must change?*")
    assert "`4 of 9`" in header_text
    assert "⚠️" not in header_text  # 4 of 9 (44%) is above the low-turnout threshold

    question_text = message["blocks"][1]["text"]["text"]
    assert "`" + "█" * 4 + "░" * 6 + "`" in question_text  # 4 of 9 audience -> round(10 * 4/9) = 4 filled cells
    assert "✅ *Chunk the backfill and run it off-peak*" in question_text
    assert "Nothing — just re-run it" in question_text and "✅ *Nothing" not in question_text

    assert message["blocks"][2] == {"type": "divider"}
    assert message["blocks"][3]["text"]["text"] == "> *Team note.* Chunking showed up; the lock itself didn't."
    assert "*Leaderboard*" in message["blocks"][4]["text"]["text"]
    assert "`1`  *Daniel Okonkwo* · 42" in message["blocks"][4]["text"]["text"]
    assert message["blocks"][-1]["type"] == "context"


def test_render_reveal_blocks_warns_on_a_low_correct_rate():
    session = _session()
    record_answer(session, AUDIENCE[0], 2, confidence=2)  # only 1 of 9 picks the correct option
    reveal = build_reveal(session, concept_to_schedule="concept-migrations", leaderboard=[])

    message = render_reveal_blocks(session, reveal)

    header_text = message["blocks"][0]["text"]["text"]
    assert "⚠️ `0 of 9`" in header_text


def test_render_reveal_blocks_omits_team_note_and_leaderboard_blocks_when_not_supplied():
    session = _session()
    _answer_the_ferry_beat(session)
    reveal = build_reveal(session, concept_to_schedule="concept-migrations", leaderboard=[])

    message = render_reveal_blocks(session, reveal)

    block_types = [block["type"] for block in message["blocks"]]
    assert block_types == ["section", "section", "divider", "context"]


def test_render_reveal_blocks_never_attributes_an_answer_to_a_person():
    session = _session()
    _answer_the_ferry_beat(session)
    reveal = build_reveal(
        session,
        concept_to_schedule="concept-migrations",
        leaderboard=[LeaderboardEntry(display_name="Daniel Okonkwo", score=42)],
    )

    message = render_reveal_blocks(session, reveal, team_note="Chunking showed up.")

    dumped = str(message)
    for person_id in AUDIENCE:
        assert person_id not in dumped
