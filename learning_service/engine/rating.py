"""Rating mapping per item kind (spec §Learning engine, "Rating mapping").

`msq` is in the frozen contract (`ItemKind` enum, `contracts/openapi.yaml`)
but not spelled out in the core design spec's own rating table; its scoring
and FSRS-rating buckets below are deliberately distinct from
`short_answer`'s, so the two never share bucket edges by accident.
"""

from __future__ import annotations

from collections.abc import Iterable

# self_rated: learner's 1-4 rating used directly; grade recorded per the
# spec's own table (0 / 0.5 / 0.85 / 1.0).
SELF_RATED_GRADE = {1: 0.0, 2: 0.5, 3: 0.85, 4: 1.0}


def msq_score(chosen: Iterable[int], correct_indices: Iterable[int]) -> float:
    """`score = max(0, TP - FP) / |C|` — zero selections or an empty answer
    key both score 0."""
    chosen_set = set(chosen)
    correct_set = set(correct_indices)
    if not correct_set:
        return 0.0
    true_positive = len(chosen_set & correct_set)
    false_positive = len(chosen_set - correct_set)
    return max(0, true_positive - false_positive) / len(correct_set)


def msq_rating(score: float) -> int:
    if score < 0.5:
        return 1  # Again
    if score < 0.75:
        return 2  # Hard
    if score < 1.0:
        return 3  # Good
    return 4  # Easy


def short_answer_rating(grade: float) -> int:
    if grade < 0.4:
        return 1  # Again
    if grade < 0.7:
        return 2  # Hard
    if grade < 0.9:
        return 3  # Good
    return 4  # Easy
