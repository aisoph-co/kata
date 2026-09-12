"""Unit tests for the FSRS-6 `card_state` wrapper (AGCTM-30, spec §Learning
engine "FSRS"). Determinism matters: AGCTM-36's replay asserts replayed
`card_state` equals live `card_state` exactly, which requires fuzzing off.
"""

from datetime import datetime, timedelta, timezone

from learning_service.engine.fsrs_engine import DESIRED_RETENTION, review_card

NOW = datetime(2026, 9, 6, tzinfo=timezone.utc)


def test_first_review_creates_a_card_state():
    card = review_card(None, "p1", "i1", rating=3, reviewed_at=NOW)
    assert card.person_id == "p1"
    assert card.item_id == "i1"
    assert card.reps == 1
    assert card.lapses == 0
    assert card.last_review_at == NOW
    assert card.due_at > NOW


def test_again_rating_counts_as_a_lapse():
    card = review_card(None, "p1", "i1", rating=1, reviewed_at=NOW)
    assert card.lapses == 1


def test_repeated_reviews_accumulate_reps_and_lapses():
    card = review_card(None, "p1", "i1", rating=3, reviewed_at=NOW)
    card = review_card(card, "p1", "i1", rating=1, reviewed_at=NOW + timedelta(days=1))
    card = review_card(card, "p1", "i1", rating=3, reviewed_at=NOW + timedelta(days=2))
    assert card.reps == 3
    assert card.lapses == 1


def test_review_card_is_deterministic_given_the_same_inputs():
    a = review_card(None, "p1", "i1", rating=3, reviewed_at=NOW)
    b = review_card(None, "p1", "i1", rating=3, reviewed_at=NOW)
    assert a == b


def test_replaying_a_review_sequence_reproduces_the_same_state():
    ratings = [3, 3, 1, 4, 2, 3]

    def replay():
        state = None
        for i, rating in enumerate(ratings):
            state = review_card(state, "p1", "i1", rating=rating, reviewed_at=NOW + timedelta(days=i))
        return state

    assert replay() == replay()


def test_easy_rating_schedules_further_out_than_again():
    again_card = review_card(None, "p1", "i1", rating=1, reviewed_at=NOW)
    easy_card = review_card(None, "p1", "i1", rating=4, reviewed_at=NOW)
    assert easy_card.due_at > again_card.due_at


def test_desired_retention_is_spec_default():
    assert DESIRED_RETENTION == 0.9
