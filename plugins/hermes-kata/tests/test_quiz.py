"""Frame 06 team-quiz post tests: confidence picker before the tap, then the
item itself, both native `clarify` shapes; a source chip naming the concept
and the grounding artifact; the live "N of 9 answered" line."""
import pytest

from hermes_kata.quiz import CONFIDENCE_CHOICES, TeamQuizItemRegistry, run_team_quiz
from hermes_kata.reveal import QuizTally

TODAY_SLUGS = ("lm-1", "lm-2")
ROSTER_SIZE = 9  # ten-person golden scenario: the poster isn't one of the nine respondents


def test_run_team_quiz_posts_confidence_picker_then_item_both_via_clarify():
    tally = QuizTally()
    registry = TeamQuizItemRegistry()

    post = run_team_quiz(list(TODAY_SLUGS), tally=tally, roster_size=ROSTER_SIZE, reveal_seconds=600, registry=registry)

    assert len(post.confidence_prompts) == len(post.questions) == 2
    for confidence in post.confidence_prompts:
        assert confidence["choices"] == list(CONFIDENCE_CHOICES)
        assert confidence["multi_select"] is False

    for question, choice_kwargs in zip(post.questions, post.question_prompts):
        assert choice_kwargs["choices"] == list(question.options)
        assert choice_kwargs["multi_select"] is False


def test_run_team_quiz_names_the_concept_and_source_in_the_chip():
    tally = QuizTally()

    post = run_team_quiz(list(TODAY_SLUGS), tally=tally, roster_size=ROSTER_SIZE, reveal_seconds=600)

    assert "ledger-migrations" in post.chip
    assert "PAY-1863" in post.chip


def test_run_team_quiz_answered_line_reflects_the_live_tally():
    tally = QuizTally()

    post = run_team_quiz(list(TODAY_SLUGS), tally=tally, roster_size=ROSTER_SIZE, reveal_seconds=600)
    assert all(line == "0 of 9 answered · reveal in 10:00" for line in post.answered_lines)

    tally.record("lm-1", 2)
    tally.record("lm-1", 0)
    post_again = run_team_quiz(list(TODAY_SLUGS), tally=tally, roster_size=ROSTER_SIZE, reveal_seconds=45)
    assert post_again.answered_lines[0] == "2 of 9 answered · reveal in 0:45"
    assert post_again.answered_lines[1] == "0 of 9 answered · reveal in 0:45"


def test_run_team_quiz_marks_posted_items_in_the_registry():
    tally = QuizTally()
    registry = TeamQuizItemRegistry()

    run_team_quiz(list(TODAY_SLUGS), tally=tally, roster_size=ROSTER_SIZE, reveal_seconds=600, registry=registry)

    assert registry.is_quiz_item("lm-1")
    assert registry.is_quiz_item("lm-2")
    assert not registry.is_quiz_item("some-other-item")


def test_registry_clears_a_prior_days_items_when_a_new_round_is_marked():
    registry = TeamQuizItemRegistry()
    registry.mark(["yesterday-1"])
    registry.mark(["lm-1", "lm-2"])

    assert not registry.is_quiz_item("yesterday-1")
    assert registry.is_quiz_item("lm-1")


def test_run_team_quiz_raises_on_no_items():
    with pytest.raises(ValueError):
        run_team_quiz([], tally=QuizTally(), roster_size=ROSTER_SIZE, reveal_seconds=600)
