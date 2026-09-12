"""FSRS-6 card update via `py-fsrs` (spec §Learning engine, "FSRS") and
retrievability (spec §Learning engine, "Next-item selection", step 1)."""

from datetime import datetime, timedelta, timezone

from learning_service.engine.fsrs_engine import review_card
from learning_service.engine.retrievability import retrievability


def test_first_review_creates_a_card_with_reps_one():
    now = datetime.now(timezone.utc)
    card = review_card(None, 3, now)
    assert card.reps == 1
    assert card.lapses == 0
    assert card.last_review_at == now
    assert card.due_at > now


def test_again_rating_counts_as_a_lapse():
    now = datetime.now(timezone.utc)
    card = review_card(None, 1, now)
    assert card.lapses == 1


def test_repeated_good_reviews_increase_stability_and_due_at():
    now = datetime.now(timezone.utc)
    card = review_card(None, 3, now)
    later = now + timedelta(days=1)
    card2 = review_card(card, 3, later)
    assert card2.reps == 2
    assert card2.due_at > card.due_at


def test_retrievability_is_zero_before_any_review():
    now = datetime.now(timezone.utc)
    assert retrievability(2.0, None, now) == 0.0


def test_retrievability_decreases_as_time_passes():
    now = datetime.now(timezone.utc)
    reviewed_at = now - timedelta(days=1)
    r1 = retrievability(5.0, reviewed_at, now)
    r2 = retrievability(5.0, now - timedelta(days=10), now)
    assert 0.0 < r2 < r1 <= 1.0


def test_retrievability_is_about_point_nine_at_stability_days_elapsed():
    now = datetime.now(timezone.utc)
    stability = 10.0
    r = retrievability(stability, now - timedelta(days=stability), now)
    assert abs(r - 0.9) < 1e-6
