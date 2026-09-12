"""FSRS-6 `card_state` update via `py-fsrs` (spec §Learning engine, "FSRS").

`enable_fuzzing` stays off: KAT-X4's replay must derive byte-identical
`card_state` from the same `review` log, and py-fsrs's fuzz draws from the
unseeded global `random` module rather than anything this service controls.

`review_card` is a pure function of `(existing, rating, reviewed_at)` —
no database — so `engine.replay` can fold a whole review history through it
without a session in hand.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import fsrs

DESIRED_RETENTION = 0.9

_SCHEDULER = fsrs.Scheduler(desired_retention=DESIRED_RETENTION, enable_fuzzing=False)

_RATING_BY_VALUE = {1: fsrs.Rating.Again, 2: fsrs.Rating.Hard, 3: fsrs.Rating.Good, 4: fsrs.Rating.Easy}
_STATE_TO_NAME = {fsrs.State.Learning: "learning", fsrs.State.Review: "review", fsrs.State.Relearning: "relearning"}
_NAME_TO_STATE = {name: state for state, name in _STATE_TO_NAME.items()}


@dataclass(frozen=True)
class CardUpdate:
    stability: float
    difficulty: float
    due_at: datetime
    state: str  # "learning" | "review" | "relearning"
    step: int | None
    reps: int
    lapses: int
    last_review_at: datetime


def _to_card(existing: CardUpdate | None) -> fsrs.Card:
    if existing is None:
        return fsrs.Card()
    return fsrs.Card(
        state=_NAME_TO_STATE[existing.state],
        step=existing.step,
        stability=existing.stability,
        difficulty=existing.difficulty,
        due=existing.due_at,
        last_review=existing.last_review_at,
    )


def review_card(existing: CardUpdate | None, rating: int, reviewed_at: datetime) -> CardUpdate:
    """Advance `existing` (or a fresh card, if this is the first review)
    with `rating` at `reviewed_at`."""
    card = _to_card(existing)
    new_card, _log = _SCHEDULER.review_card(card, _RATING_BY_VALUE[rating], reviewed_at)
    return CardUpdate(
        stability=new_card.stability,
        difficulty=new_card.difficulty,
        due_at=new_card.due,
        state=_STATE_TO_NAME[new_card.state],
        step=new_card.step,
        reps=(existing.reps if existing else 0) + 1,
        lapses=(existing.lapses if existing else 0) + (1 if rating == 1 else 0),
        last_review_at=reviewed_at,
    )
