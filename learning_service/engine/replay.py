"""The one step that advances `card_state` and `concept_state` for a review
(spec §Learning engine). `POST /me/reviews` calls it with a freshly graded
result; `POST /admin/replay` (AGCTM-36) calls it with a stored `review` row.
Same function, so replayed state is identical to live state by construction
rather than by keeping two implementations in sync.

`rebuild_derived_state` is the shared truncate-and-rebuild step `POST
/admin/replay` and the golden seed (PLAN_05 PR-B) both use: it only touches
the repository's in-memory dicts (via `clear_derived_state`/`add_card_state`/
`add_concept_state`, all synchronous on both `InMemoryLearningRepository` and
`SqlLearningRepository`); a SQL-backed repository additionally persists the
result durably — see `engine/sql_repository.py`.
"""

from __future__ import annotations

from datetime import datetime

from learning_service.engine.bkt import update_p_known
from learning_service.engine.fsrs_engine import review_card
from learning_service.engine.models import P_INIT, CardState, ConceptState
from learning_service.engine.repository import InMemoryLearningRepository


def parse_reviewed_at(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _fold_card_state(
    repo: InMemoryLearningRepository, person_id: str, item_id: str, rating: int, reviewed_at: datetime, review_id: str
) -> CardState:
    """Recompute `card_state` for one item from its whole review history
    (already-recorded rows plus the one in progress), in the same
    `(reviewed_at, id)` order `rebuild_derived_state` uses. Only needed when
    the incoming review is *not* the latest one on record for this item (see
    `apply_review`) — the ordinary case stays the O(1) incremental update
    below.

    `review_id` must be the review's own real id (the same one that will end
    up in the `review` log), not a placeholder: an exact `reviewed_at` tie
    against an already-recorded row is broken by `id`, same as
    `rebuild_derived_state`'s sort key, so a fake tiebreak here would sort
    this review differently than a later `/admin/replay` will.

    `review_id` may or may not already be among `repo.all_reviews()`: a live
    submission (`POST /me/reviews`) calls this before its review is
    appended to the log, so it supplies an entry no row yet has; `POST
    /admin/replay` (`rebuild_derived_state`, below) calls this while
    iterating the log it is rebuilding *from*, so the review is always
    already a row. Either way this must fold in exactly one entry per
    review — never zero (a live tie silently dropped) and never two (the
    same review double-counted during replay, which used to raise instead;
    KAT-X4 regression, AE Reviewer `Verdict: fix`).
    """
    rows = [r for r in repo.all_reviews() if r["person_id"] == person_id and r["item_id"] == item_id]
    entries = [(parse_reviewed_at(r["reviewed_at"]), str(r.get("id", "")), r["rating"]) for r in rows]
    if not any(entry_id == review_id for _, entry_id, _ in entries):
        entries.append((reviewed_at, review_id, rating))
    entries.sort(key=lambda e: (e[0], e[1]))

    card: CardState | None = None
    for ts, _id, entry_rating in entries:
        card = review_card(card, person_id, item_id, entry_rating, ts)
    assert card is not None
    return card


def _fold_concept_state(
    repo: InMemoryLearningRepository,
    person_id: str,
    concept_id: str,
    kind: str,
    rating: int,
    reviewed_at: datetime,
    review_id: str,
) -> ConceptState:
    """`concept_state` counterpart to `_fold_card_state`: BKT's `p_known`
    update is sequential too, so an out-of-order insert needs every review
    on record for this concept (across all its items) re-folded in order,
    not just appended on top of the current snapshot. Same `review_id`
    may-or-may-not-already-be-logged handling as `_fold_card_state` — see
    its docstring."""
    rows = []
    for r in repo.all_reviews():
        if r["person_id"] != person_id:
            continue
        item = repo.get_item(r["item_id"])
        if item is not None and item.concept_id == concept_id:
            rows.append(r)
    entries = [(parse_reviewed_at(r["reviewed_at"]), str(r.get("id", "")), r["rating"], r["kind"]) for r in rows]
    if not any(entry_id == review_id for _, entry_id, _, _ in entries):
        entries.append((reviewed_at, review_id, rating, kind))
    entries.sort(key=lambda e: (e[0], e[1]))

    p_known = P_INIT
    reviews = 0
    last_review_at: datetime | None = None
    for ts, _id, entry_rating, entry_kind in entries:
        p_known = update_p_known(p_known, entry_kind, entry_rating >= 3)
        reviews += 1
        last_review_at = ts
    return ConceptState(
        person_id=person_id, concept_id=concept_id, p_known=p_known, reviews=reviews, last_review_at=last_review_at
    )


def apply_review(
    repo: InMemoryLearningRepository,
    *,
    person_id: str,
    item_id: str,
    concept_id: str,
    kind: str,
    rating: int,
    reviewed_at: datetime,
    review_id: str,
) -> tuple[CardState, ConceptState]:
    existing_card = repo.card_states.get((person_id, item_id))
    # A live review is normally the newest one for its item/concept (server
    # time only moves forward), so the incremental update below — apply on
    # top of the current snapshot — matches a full chronological rebuild by
    # construction. That assumption breaks two ways: (1) the review log
    # already has a *later* `reviewed_at` on record for this item/concept
    # (e.g. seeded history dated after the live submission's wall-clock
    # time) — folding on top would silently rewrite the wrong (earlier) end
    # of the timeline; (2) an *equal* `reviewed_at` is on record — the
    # canonical order `rebuild_derived_state` uses is `(reviewed_at, id)`,
    # so which of two same-instant reviews comes first depends on `id`, not
    # on which one happened to be applied first live. Using `<=` (not `<`)
    # below routes both cases through the same full-history fold `/admin/
    # replay` does, just scoped to the one item/concept an out-of-order or
    # tied insert can affect, so it stays exact without a full-repository
    # rebuild on every request. (KAT-X4 regression: two live reviews sharing
    # a `reviewed_at` whose `id` order differs from arrival order used to
    # diverge from replay under a strict `<`.)
    if (
        existing_card is not None
        and existing_card.last_review_at is not None
        and reviewed_at <= existing_card.last_review_at
    ):
        new_card = _fold_card_state(repo, person_id, item_id, rating, reviewed_at, review_id)
    else:
        new_card = review_card(existing_card, person_id, item_id, rating, reviewed_at)
    repo.add_card_state(new_card)

    existing_concept_state = repo.concept_state_for(person_id, concept_id)
    if (
        existing_concept_state is not None
        and existing_concept_state.last_review_at is not None
        and reviewed_at <= existing_concept_state.last_review_at
    ):
        new_concept_state = _fold_concept_state(repo, person_id, concept_id, kind, rating, reviewed_at, review_id)
    else:
        prior_p_known = existing_concept_state.p_known if existing_concept_state is not None else P_INIT
        # `correct = rating >= 3` uniformly (spec §Learning engine, "BKT"; see
        # engine/grading.py) so replay never needs the original grading inputs.
        new_p_known = update_p_known(prior_p_known, kind, rating >= 3)

        new_concept_state = ConceptState(
            person_id=person_id,
            concept_id=concept_id,
            p_known=new_p_known,
            reviews=(existing_concept_state.reviews if existing_concept_state is not None else 0) + 1,
            last_review_at=reviewed_at,
        )
    repo.add_concept_state(new_concept_state)
    return new_card, new_concept_state


def rebuild_derived_state(repo: InMemoryLearningRepository) -> dict[str, int]:
    repo.clear_derived_state()

    ordered_reviews = sorted(
        repo.all_reviews(),
        key=lambda review: (review["person_id"], parse_reviewed_at(review["reviewed_at"]), str(review.get("id", ""))),
    )
    for review in ordered_reviews:
        item = repo.get_item(review["item_id"])
        if item is None:
            continue
        _, new_concept_state = apply_review(
            repo,
            person_id=review["person_id"],
            item_id=review["item_id"],
            concept_id=item.concept_id,
            kind=review["kind"],
            rating=review["rating"],
            reviewed_at=parse_reviewed_at(review["reviewed_at"]),
            review_id=str(review.get("id", "")),
        )
        # `GET /me/history` (PLAN_08): backfill both fields onto the review
        # dict in place — `ordered_reviews` holds the same dict objects as
        # `repo.reviews`, so this mutation is visible to callers reading the
        # log afterwards (`reviews_for`) without a second pass. Sorting this
        # loop globally by `(person_id, reviewed_at, id)` keeps each
        # concept's own subsequence chronological too, so the incremental
        # branch in `apply_review` runs here (not the out-of-order fold),
        # meaning `new_concept_state.p_known` is exactly this review's
        # post-state, not some later review's.
        review["concept_id"] = item.concept_id
        review["p_known_after"] = new_concept_state.p_known

    return {
        "replayed_reviews": len(ordered_reviews),
        "card_state_count": len(repo.card_states),
        "concept_state_count": len(repo.concept_states),
    }
