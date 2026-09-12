"""Closed-form BKT update against hand-computed values (spec §Testing,
"Unit": "BKT update against hand-computed values").
"""

from learning_service.engine.bkt import P_GUESS_MCQ, P_GUESS_OTHER, P_SLIP, P_TRANSIT, p_guess, update_p_known


def test_p_guess_by_kind():
    assert p_guess("mcq") == P_GUESS_MCQ
    assert p_guess("self_rated") == P_GUESS_OTHER
    assert p_guess("short_answer") == P_GUESS_OTHER
    assert p_guess("teach_back") == P_GUESS_OTHER


def test_update_p_known_correct_mcq_hand_computed():
    # p=0.20, correct, mcq: posterior = .2*.9 / (.2*.9 + .8*.25) = .18/.38
    posterior = 0.2 * (1 - P_SLIP) / (0.2 * (1 - P_SLIP) + 0.8 * P_GUESS_MCQ)
    expected = posterior + (1 - posterior) * P_TRANSIT
    assert update_p_known(0.2, "mcq", True) == expected
    assert abs(update_p_known(0.2, "mcq", True) - 0.5526315789473685) < 1e-9


def test_update_p_known_incorrect_mcq_hand_computed():
    posterior = 0.2 * P_SLIP / (0.2 * P_SLIP + 0.8 * (1 - P_GUESS_MCQ))
    expected = posterior + (1 - posterior) * P_TRANSIT
    assert update_p_known(0.2, "mcq", False) == expected


def test_update_p_known_increases_on_correct_and_decreases_on_incorrect():
    assert update_p_known(0.5, "mcq", True) > 0.5
    assert update_p_known(0.5, "mcq", False) < 0.5


def test_update_p_known_never_leaves_unit_interval():
    p = 0.01
    for _ in range(50):
        p = update_p_known(p, "self_rated", True)
        assert 0.0 <= p <= 1.0
    p = 0.99
    for _ in range(50):
        p = update_p_known(p, "self_rated", False)
        assert 0.0 <= p <= 1.0


def test_repeated_correct_answers_converge_toward_mastery():
    p = 0.20
    for _ in range(10):
        p = update_p_known(p, "mcq", True)
    assert p > 0.85
