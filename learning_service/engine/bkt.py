"""Closed-form BKT concept-state update (spec §Learning engine, "BKT"),
constants copied verbatim from the spec's own code block.

Pure function of `(p_known, kind, correct)` — no wall-clock or randomness —
so replaying the `review` log reproduces `concept_state` exactly (KAT-X4).
"""

from __future__ import annotations

P_GUESS_MCQ = 0.25
P_GUESS_OTHER = 0.10
P_SLIP = 0.10
P_TRANSIT = 0.15


def p_guess(kind: str) -> float:
    return P_GUESS_MCQ if kind == "mcq" else P_GUESS_OTHER


def update_p_known(p_known: float, kind: str, correct: bool) -> float:
    guess = p_guess(kind)
    if correct:
        posterior = p_known * (1 - P_SLIP) / (p_known * (1 - P_SLIP) + (1 - p_known) * guess)
    else:
        posterior = p_known * P_SLIP / (p_known * P_SLIP + (1 - p_known) * (1 - guess))
    return posterior + (1 - posterior) * P_TRANSIT
