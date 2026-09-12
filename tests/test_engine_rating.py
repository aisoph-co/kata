"""Unit tests for rating mapping per kind (AGCTM-30, spec §Learning engine
"Rating mapping"; msq scoring/buckets from AGCTM-10 comment 01a07655,
field names corrected in 01a0769e)."""

from learning_service.engine.rating import SELF_RATED_GRADE, msq_rating, msq_score, short_answer_rating


def test_self_rated_grade_table():
    assert SELF_RATED_GRADE == {1: 0.0, 2: 0.5, 3: 0.85, 4: 1.0}


def test_short_answer_rating_buckets():
    assert short_answer_rating(0.0) == 1
    assert short_answer_rating(0.39) == 1
    assert short_answer_rating(0.4) == 2
    assert short_answer_rating(0.69) == 2
    assert short_answer_rating(0.7) == 3
    assert short_answer_rating(0.89) == 3
    assert short_answer_rating(0.9) == 4
    assert short_answer_rating(1.0) == 4


def test_msq_score_full_credit():
    assert msq_score(chosen=[0, 2], correct_indices=[0, 2]) == 1.0


def test_msq_score_partial_credit_penalizes_false_positives():
    # TP=1, FP=1, |C|=2 -> max(0, 1-1)/2 = 0
    assert msq_score(chosen=[0, 1], correct_indices=[0, 2]) == 0.0
    # TP=1, FP=0, |C|=2 -> 0.5
    assert msq_score(chosen=[0], correct_indices=[0, 2]) == 0.5


def test_msq_score_zero_selections_is_zero():
    assert msq_score(chosen=[], correct_indices=[0, 1]) == 0.0


def test_msq_score_empty_answer_key_is_zero():
    assert msq_score(chosen=[0], correct_indices=[]) == 0.0


def test_msq_rating_buckets():
    assert msq_rating(0.0) == 1
    assert msq_rating(0.49) == 1
    assert msq_rating(0.5) == 2
    assert msq_rating(0.74) == 2
    assert msq_rating(0.75) == 3
    assert msq_rating(0.99) == 3
    assert msq_rating(1.0) == 4
