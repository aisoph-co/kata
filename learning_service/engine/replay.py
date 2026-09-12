"""The one step that advances `card_state` and `concept_state` for a review
(spec §Learning engine, "Replay"): `POST /me/reviews` calls `apply_review`
with a freshly graded result; `POST /admin/replay` calls `rebuild_derived_
state` to truncate and rebuild both tables from the whole `review` log.

Both fold the same `(reviewed_at, id)`-ordered history through the same
`bkt.update_p_known`/`fsrs_engine.review_card` pure functions, so replayed
state is identical to live state by construction (KAT-X4) rather than by
keeping two implementations in sync: `apply_review` always recomputes a
card's/concept's whole state from its full review history (including the
row about to be recorded, not yet inserted), never an O(1) increment on top
of the previous snapshot — the review volumes here (tens of learners) make
the O(n) re-fold cheap, and it means there is exactly one code path for
"what is this card's/concept's state", live or replayed.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.engine.bkt import update_p_known
from learning_service.engine.fsrs_engine import CardUpdate, review_card
from learning_service.engine.models import P_INIT, CardState, ConceptState, Review, as_utc

_CardEntry = tuple[datetime, str, int]  # (reviewed_at, review_id, rating)
_ConceptEntry = tuple[datetime, str, int, str]  # (reviewed_at, review_id, rating, kind)


def _fold_card(entries: Sequence[_CardEntry]) -> CardUpdate:
    card: CardUpdate | None = None
    for _reviewed_at, _review_id, rating in sorted(entries):
        card = review_card(card, rating, _reviewed_at)
    assert card is not None
    return card


def _fold_concept(entries: Sequence[_ConceptEntry]) -> tuple[float, int, datetime | None]:
    p_known = P_INIT
    reviews = 0
    last_review_at: datetime | None = None
    for reviewed_at, _review_id, rating, kind in sorted(entries):
        p_known = update_p_known(p_known, kind, rating >= 3)
        reviews += 1
        last_review_at = reviewed_at
    return p_known, reviews, last_review_at


def _apply_card_update(card_state: CardState, update: CardUpdate) -> None:
    card_state.stability = update.stability
    card_state.difficulty = update.difficulty
    card_state.due_at = update.due_at
    card_state.state = update.state
    card_state.step = update.step
    card_state.reps = update.reps
    card_state.lapses = update.lapses
    card_state.last_review_at = update.last_review_at


async def apply_review(
    session: AsyncSession,
    *,
    person_id: str,
    item_id: str,
    concept_id: str,
    kind: str,
    rating: int,
    reviewed_at: datetime,
    review_id: str,
) -> tuple[CardState, ConceptState]:
    """Recomputes `card_state` for `(person_id, item_id)` and `concept_state`
    for `(person_id, concept_id)` from the full review history for each key,
    including the review about to be recorded (`review_id` must not yet be
    in the `review` table — the caller inserts it after this returns)."""
    item_rows = (
        await session.execute(
            select(Review.reviewed_at, Review.id, Review.rating).where(
                Review.person_id == person_id, Review.item_id == item_id
            )
        )
    ).all()
    item_entries: list[_CardEntry] = [(as_utc(r.reviewed_at), r.id, r.rating) for r in item_rows]
    item_entries.append((reviewed_at, review_id, rating))
    card_update = _fold_card(item_entries)

    concept_rows = (
        await session.execute(
            select(Review.reviewed_at, Review.id, Review.rating, Review.kind).where(
                Review.person_id == person_id, Review.concept_id == concept_id
            )
        )
    ).all()
    concept_entries: list[_ConceptEntry] = [(as_utc(r.reviewed_at), r.id, r.rating, r.kind) for r in concept_rows]
    concept_entries.append((reviewed_at, review_id, rating, kind))
    p_known, reviews_count, last_review_at = _fold_concept(concept_entries)

    card_state = await session.get(CardState, (person_id, item_id))
    if card_state is None:
        card_state = CardState(person_id=person_id, item_id=item_id, stability=0, difficulty=0, due_at=reviewed_at)
        session.add(card_state)
    _apply_card_update(card_state, card_update)

    concept_state = await session.get(ConceptState, (person_id, concept_id))
    if concept_state is None:
        concept_state = ConceptState(person_id=person_id, concept_id=concept_id)
        session.add(concept_state)
    concept_state.p_known = p_known
    concept_state.reviews = reviews_count
    concept_state.last_review_at = last_review_at

    return card_state, concept_state


async def rebuild_derived_state(session: AsyncSession) -> dict[str, int]:
    """`POST /admin/replay` (spec §Learning engine, "Replay"): truncates
    `card_state`/`concept_state` and rebuilds them from `review` in
    `(person_id, reviewed_at, id)` order."""
    await session.execute(delete(CardState))
    await session.execute(delete(ConceptState))

    rows = (
        await session.execute(
            select(
                Review.person_id, Review.item_id, Review.concept_id, Review.kind, Review.rating, Review.reviewed_at, Review.id
            ).order_by(Review.person_id, Review.reviewed_at, Review.id)
        )
    ).all()

    card_groups: dict[tuple[str, str], list[_CardEntry]] = {}
    concept_groups: dict[tuple[str, str], list[_ConceptEntry]] = {}
    for row in rows:
        reviewed_at = as_utc(row.reviewed_at)
        card_groups.setdefault((row.person_id, row.item_id), []).append((reviewed_at, row.id, row.rating))
        concept_groups.setdefault((row.person_id, row.concept_id), []).append(
            (reviewed_at, row.id, row.rating, row.kind)
        )

    for (person_id, item_id), entries in card_groups.items():
        update = _fold_card(entries)
        card_state = CardState(person_id=person_id, item_id=item_id, stability=0, difficulty=0, due_at=update.due_at)
        _apply_card_update(card_state, update)
        session.add(card_state)

    for (person_id, concept_id), entries in concept_groups.items():
        p_known, reviews_count, last_review_at = _fold_concept(entries)
        session.add(
            ConceptState(
                person_id=person_id,
                concept_id=concept_id,
                p_known=p_known,
                reviews=reviews_count,
                last_review_at=last_review_at,
            )
        )

    await session.commit()
    return {
        "replayed_reviews": len(rows),
        "card_state_count": len(card_groups),
        "concept_state_count": len(concept_groups),
    }
