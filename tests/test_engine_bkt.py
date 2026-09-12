"""Unit tests for the closed-form BKT update (AGCTM-30, spec §Learning
engine "BKT") against hand-computed values."""

import pytest

from learning_service.engine.bkt import P_GUESS_MCQ, P_GUESS_OTHER, P_SLIP, P_TRANSIT, p_guess, update_p_known


def test_p_guess_by_kind():
    assert p_guess("mcq") == P_GUESS_MCQ
    assert p_guess("msq") == P_GUESS_OTHER
    assert p_guess("self_rated") == P_GUESS_OTHER
    assert p_guess("short_answer") == P_GUESS_OTHER


def test_correct_mcq_update_matches_hand_computation():
    p = 0.20
    posterior = p * (1 - P_SLIP) / (p * (1 - P_SLIP) + (1 - p) * P_GUESS_MCQ)
    expected = posterior + (1 - posterior) * P_TRANSIT
    assert update_p_known(p, "mcq", correct=True) == pytest.approx(expected)
    assert update_p_known(p, "mcq", correct=True) == pytest.approx(0.55263, abs=1e-4)


def test_incorrect_mcq_update_matches_hand_computation():
    p = 0.20
    posterior = p * P_SLIP / (p * P_SLIP + (1 - p) * (1 - P_GUESS_MCQ))
    expected = posterior + (1 - posterior) * P_TRANSIT
    assert update_p_known(p, "mcq", correct=False) == pytest.approx(expected)
    assert update_p_known(p, "mcq", correct=False) == pytest.approx(0.17742, abs=1e-4)


def test_short_answer_uses_the_non_mcq_guess_rate():
    p = 0.20
    posterior = p * (1 - P_SLIP) / (p * (1 - P_SLIP) + (1 - p) * P_GUESS_OTHER)
    expected = posterior + (1 - posterior) * P_TRANSIT
    assert update_p_known(p, "short_answer", correct=True) == pytest.approx(expected)


def test_repeated_correct_reviews_increase_p_known_towards_one():
    p = 0.20
    for _ in range(10):
        p = update_p_known(p, "mcq", correct=True)
    assert p > 0.95
