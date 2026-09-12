"""`person_learning_summary` (Contract v1.2.0): retention bands, bypass rate,
calibration — pure function over a person's own review log rows.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from learning_service.engine.analytics import person_learning_summary, subtree_retention

BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _review(item_id: str, day_offset: int, rating: int, *, person_id="p1", confidence=None, bypassed=False) -> dict:
    return {
        "person_id": person_id,
        "item_id": item_id,
        "reviewed_at": (BASE + timedelta(days=day_offset)).isoformat(),
        "rating": rating,
        "confidence": confidence,
        "bypassed": bypassed,
    }


def test_empty_review_log_returns_all_nulls():
    summary = person_learning_summary([])
    assert summary == {
        "retention": {
            "d1": {"accuracy": None, "samples": 0},
            "d7": {"accuracy": None, "samples": 0},
            "d30": {"accuracy": None, "samples": 0},
        },
        "bypass_rate": None,
        "calibration": None,
        "review_count": 0,
        "last_active": None,
    }


def test_retention_band_needs_five_samples_for_accuracy_but_always_reports_samples():
    # Four pairs at a 1-day gap, all correct: below the 5-sample floor ->
    # accuracy null, but samples still reports the real count (QA finding A).
    reviews = []
    for i in range(4):
        reviews.append(_review(f"item-{i}", 0, 3))
        reviews.append(_review(f"item-{i}", 1, 3))
    summary = person_learning_summary(reviews)
    assert summary["retention"]["d1"] == {"accuracy": None, "samples": 4}


def test_retention_band_boundaries_and_accuracy():
    # d1 band: gap == 1 day exactly. 5 pairs, 3 correct (rating>=3).
    reviews = []
    for i in range(5):
        reviews.append(_review(f"item-{i}", 0, 3))
        reviews.append(_review(f"item-{i}", 1, 3 if i < 3 else 1))
    # d7 band: gap in [5, 10]. 5 pairs, all correct.
    for i in range(5):
        reviews.append(_review(f"d7-item-{i}", 10, 3))
        reviews.append(_review(f"d7-item-{i}", 10 + 5 + i, 3))
    # d30 band: gap in [21, 45]. 5 pairs, all incorrect.
    for i in range(5):
        reviews.append(_review(f"d30-item-{i}", 20, 3))
        reviews.append(_review(f"d30-item-{i}", 20 + 21 + i, 1))
    # A 4-day gap falls in no band and must not pollute any of them.
    reviews.append(_review("no-band-item", 0, 3))
    reviews.append(_review("no-band-item", 4, 3))

    summary = person_learning_summary(reviews)
    assert summary["retention"]["d1"] == {"accuracy": pytest.approx(3 / 5), "samples": 5}
    assert summary["retention"]["d7"] == {"accuracy": 1.0, "samples": 5}
    assert summary["retention"]["d30"] == {"accuracy": 0.0, "samples": 5}


def test_subtree_retention_pools_across_people_without_cross_contamination():
    # Two different people reviewing the *same* item_id must not be treated
    # as one learner's repeat: grouping is by (person_id, item_id).
    reviews = [
        _review("shared-item", 0, 3, person_id="alice"),
        _review("shared-item", 100, 3, person_id="bob"),  # a huge gap, wrong person
    ]
    assert subtree_retention(reviews) == {
        "d1": {"accuracy": None, "samples": 0},
        "d7": {"accuracy": None, "samples": 0},
        "d30": {"accuracy": None, "samples": 0},
    }


def test_subtree_retention_aggregates_five_samples_across_five_people():
    reviews = []
    for i in range(5):
        reviews.append(_review("item-x", 0, 3, person_id=f"person-{i}"))
        reviews.append(_review("item-x", 1, 3, person_id=f"person-{i}"))
    assert subtree_retention(reviews)["d1"] == {"accuracy": 1.0, "samples": 5}


def test_subtree_retention_of_no_reviews_is_all_zero_samples():
    assert subtree_retention([]) == {
        "d1": {"accuracy": None, "samples": 0},
        "d7": {"accuracy": None, "samples": 0},
        "d30": {"accuracy": None, "samples": 0},
    }


def test_bypass_rate_is_share_of_all_reviews():
    reviews = [
        _review("i1", 0, 3, bypassed=False),
        _review("i2", 0, 1, bypassed=True),
        _review("i3", 0, 1, bypassed=True),
        _review("i4", 0, 3, bypassed=False),
    ]
    summary = person_learning_summary(reviews)
    assert summary["bypass_rate"] == 0.5
    assert summary["review_count"] == 4


def test_calibration_null_when_no_review_has_confidence():
    reviews = [_review("i1", 0, 3), _review("i2", 0, 1)]
    assert person_learning_summary(reviews)["calibration"] is None


def test_calibration_positive_means_overconfident():
    # Stated confidence 5/5, the highest possible (=1.0 rescaled), but only
    # ever wrong (accuracy 0.0) -> +1.0, the ceiling of the scale.
    reviews = [_review("i1", d, 1, confidence=5) for d in range(3)]
    summary = person_learning_summary(reviews)
    assert summary["calibration"] == pytest.approx(1.0)


def test_calibration_negative_means_underconfident():
    # Stated confidence 1/5, the lowest statement possible (=0.0 rescaled),
    # but always right (accuracy 1.0) -> -1.0, the floor of the scale.
    reviews = [_review("i1", d, 3, confidence=1) for d in range(3)]
    summary = person_learning_summary(reviews)
    assert summary["calibration"] == pytest.approx(-1.0)


def test_calibration_is_zero_when_the_lowest_confidence_matches_being_wrong():
    # Always states confidence 1 (=0.0) and is always wrong (accuracy 0.0):
    # perfectly calibrated. The old c/5 scale scored this +0.2 overconfident.
    reviews = [_review("i1", d, 1, confidence=1) for d in range(3)]
    assert person_learning_summary(reviews)["calibration"] == pytest.approx(0.0)


def test_last_active_is_the_latest_reviewed_at():
    reviews = [_review("i1", 0, 3), _review("i1", 5, 3), _review("i1", 2, 3)]
    summary = person_learning_summary(reviews)
    assert summary["last_active"] == BASE + timedelta(days=5)
