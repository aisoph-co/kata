"""FSRS-6 `card_state` update via `py-fsrs` (spec §Learning engine, "FSRS").

`enable_fuzzing` stays off: AGCTM-36's replay must derive a byte-identical
`card_state` from the same `review` log, and py-fsrs's fuzz draws from the
unseeded global `random` module rather than anything we control.
"""

from __future__ import annotations

from datetime import datetime

import fsrs

from learning_service.engine.models import CardState

DESIRED_RETENTION = 0.9

_SCHEDULER = fsrs.Scheduler(desired_retention=DESIRED_RETENTION, enable_fuzzing=False)

_RATING_BY_VALUE = {1: fsrs.Rating.Again, 2: fsrs.Rating.Hard, 3: fsrs.Rating.Good, 4: fsrs.Rating.Easy}
_STATE_TO_NAME = {fsrs.State.Learning: "learning", fsrs.State.Review: "review", fsrs.State.Relearning: "relearning"}
_NAME_TO_STATE = {name: state for state, name in _STATE_TO_NAME.items()}


def _to_card(existing: CardState | None) -> fsrs.Card:
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


def review_card(
    existing: CardState | None,
    person_id: str,
    item_id: str,
    rating: int,
    reviewed_at: datetime,
) -> CardState:
    """Advance `existing` (or a fresh card, if this is the first review) with
    `rating` at `reviewed_at`, returning the new `card_state` row."""
    card = _to_card(existing)
    new_card, _log = _SCHEDULER.review_card(card, _RATING_BY_VALUE[rating], reviewed_at)
    return CardState(
        person_id=person_id,
        item_id=item_id,
        stability=new_card.stability,
        difficulty=new_card.difficulty,
        due_at=new_card.due,
        state=_STATE_TO_NAME[new_card.state],
        step=new_card.step,
        reps=(existing.reps if existing else 0) + 1,
        lapses=(existing.lapses if existing else 0) + (1 if rating == 1 else 0),
        last_review_at=reviewed_at,
    )
