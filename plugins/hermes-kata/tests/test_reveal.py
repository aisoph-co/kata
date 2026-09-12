"""AGCTM-69 reveal tests: tallying is counts-only (never who picked what),
crediting a correct answerer by name never leaks anyone's wrong answer, and
the reveal says what's missing instead of fabricating a leaderboard or team
note."""
from hermes_kata.reveal import (
    CorrectAnswerers,
    QuizQuestion,
    QuizTally,
    load_item_catalog,
    load_quiz_questions,
    record_submit_review,
    render_reveal,
)

QUESTION = QuizQuestion(
    item_id="lm-1",
    position=1,
    total_questions=1,
    concept="ledger-migrations",
    prompt="Which lock?",
    options=["none", "read", "row write", "full table"],
    correct_index=2,
)


def test_load_quiz_questions_reads_the_vendored_ledger_migrations_seed():
    questions = load_quiz_questions(["lm-1", "lm-2"])

    assert [q.item_id for q in questions] == ["lm-1", "lm-2"]
    assert all(q.concept == "ledger-migrations" for q in questions)
    assert all(q.source_ref == "PAY-1863" for q in questions)
    assert [q.position for q in questions] == [1, 2]
    assert all(q.total_questions == 2 for q in questions)


def test_tally_records_counts_only_never_who_picked_what():
    tally = QuizTally()
    record_submit_review(tally, "lm-1", {"choice": 2})
    record_submit_review(tally, "lm-1", {"choice": 0})

    assert tally.counts_for("lm-1") == {2: 1, 0: 1}
    # No method on QuizTally can answer "who" — only "how many".
    assert not hasattr(tally, "who_picked")


def test_an_msq_style_response_is_ignored():
    tally = QuizTally()
    record_submit_review(tally, "lm-1", {"choices": [0, 1]})
    assert tally.counts_for("lm-1") == {}


def test_correct_answerers_only_ever_records_a_correct_choice():
    tally = QuizTally()
    correct = CorrectAnswerers()
    catalog = load_item_catalog()

    record_submit_review(tally, "lm-1", {"choice": 2}, correct_answerers=correct, person_name="Hugo", catalog=catalog)
    record_submit_review(tally, "lm-1", {"choice": 0}, correct_answerers=correct, person_name="Nushka", catalog=catalog)

    assert correct.names_for("lm-1") == ["Hugo"]
    assert "Nushka" not in correct.names_for("lm-1")


def test_render_reveal_states_counts_and_never_shows_a_wrong_answer():
    tally = QuizTally()
    correct = CorrectAnswerers()
    for choice, name in [(2, "Hugo"), (2, "Daniel"), (0, "Nushka"), (1, "Ada")]:
        record_submit_review(tally, "lm-1", {"choice": choice}, correct_answerers=correct, person_name=name)

    text = render_reveal([QUESTION], tally, correct_answerers=correct)

    assert "2 of 4" in text  # 2 people picked the correct option, of 4 respondents
    assert "Hugo" in text
    assert "Daniel" in text
    # Nushka and Ada answered wrong — never named anywhere in the reveal.
    assert "Nushka" not in text
    assert "Ada" not in text
    assert "Scheduling a follow-up rep on `ledger-migrations`" in text


def test_render_reveal_says_whats_missing_instead_of_fabricating():
    tally = QuizTally()
    text = render_reveal([QUESTION], tally)

    assert "Team note: not available yet" in text
    assert "Leaderboard: not available yet" in text


def test_render_reveal_uses_leaderboard_and_team_note_when_given():
    tally = QuizTally()
    record_submit_review(tally, "lm-1", {"choice": 2})

    text = render_reveal(
        [QUESTION],
        tally,
        team_note="Most of the team is solid on locking.",
        leaderboard=[{"rank": 1, "name": "Hugo Marchetti", "points": 120}],
    )

    assert "Team note. Most of the team is solid on locking." in text
    assert "Leaderboard:" in text
    assert "1. Hugo Marchetti — 120" in text
