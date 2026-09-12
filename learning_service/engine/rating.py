"""Rating mapping per item kind (spec §Learning engine, "Rating mapping").

`msq`'s scoring and FSRS-rating buckets are from the AGCTM-10 comment
thread that added it in v1.1.0 (comment `01a07655`, field names corrected
in `01a0769e`) — deliberately different bucket edges from `short_answer`,
so the two are not shared.
"""

from __future__ import annotations

from collections.abc import Iterable

# self_rated: learner's 1-4 rating used directly; grade recorded per table.
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
