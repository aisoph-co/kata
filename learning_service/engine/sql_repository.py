"""`SqlLearningRepository` (PLAN_05 PR-B): the `LearningRepository` backed by
Postgres/SQLite through the request's `AsyncSession`, so `review`,
`card_state`, `concept_state` (migration 0005) and curriculum/focus
(migrations 0003/0004) survive a restart and stay one store.

Design: subclass `InMemoryLearningRepository` and hydrate its dicts once per
request (`load()`, a handful of bulk `SELECT`s — this dataset is small, see
PLAN_05) instead of teaching `select_next_items`/`apply_review`/`team/
service.py` to `await` a query per call. Everything those already call
(`list_concepts`, `get_item`, `card_states_for`, `add_card_state`, ...) is
inherited unchanged and stays synchronous, operating on the hydrated
snapshot — same as the in-memory repository today.

Two things a snapshot-then-mutate design cannot give you, so they are real
`AsyncSession` round trips instead:
- `commit_review`: the idempotency guarantee two concurrent identical
  `POST /me/reviews` need. Each request hydrates its own repo instance, so
  an in-memory check-then-insert across two instances is not a lock — only
  the database's unique constraint on `(person_id, idempotency_key)` is.
  Insert, catch the conflict, return the winner's stored result; never
  check first (PLAN_05 PR-B locked decision).
- `persist_derived_state`: `/admin/replay`'s durable half — one transaction,
  one commit, so a concurrent `/me/next` on another request's repository
  never observes a half-rebuilt `card_state`/`concept_state`.

`add_note`/`add_answer` queue their Postgres row via the session's
(synchronous) `add()` on top of the inherited in-memory write, so a POST
that follows with a real commit persists them. `delete_note`/
`delete_notes_for`/`delete_answers_for`/`purge_answers_older_than` override
the inherited sync methods with async ones that also issue a real `DELETE`
(callers must `isinstance`-check and `await`, same as `commit_review`/
`persist_derived_state` — see `notes.py`/`answers.py`), so the 90-day
retention sweep actually retires rows on Postgres instead of only emptying
the request's snapshot.

Every datetime read back from a row is normalized to UTC-aware on the way
in (`_as_utc`): asyncpg already returns `DateTime(timezone=True)` columns
tz-aware, but SQLite (the test fixture's dialect) drops tzinfo on every
round trip regardless of column type — `select_next_items`/`apply_review`/
team analytics all compare these against `datetime.now(timezone.utc)` and
raise on a naive/aware mismatch.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum.models import Concept as ConceptRow
from learning_service.curriculum.models import ConceptEdge as ConceptEdgeRow
from learning_service.curriculum.models import Item as ItemRow
from learning_service.engine.models import (
    Answer,
    CardState,
    Concept,
    ConceptEdge,
    ConceptState,
    Focus,
    Item,
    LearnerNote,
)
from learning_service.engine.repository import InMemoryLearningRepository
from learning_service.engine.sql_models import AnswerRow, CardStateRow, ConceptStateRow, LearnerNoteRow, ReviewRow
from learning_service.identity.models import Person
from learning_service.roster.models import Focus as FocusRow


class SqlLearningRepository(InMemoryLearningRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__()
        self.session = session

    async def load(self) -> None:
        session = self.session

        for row in (await session.execute(select(ConceptRow))).scalars():
            self.add_concept(
                Concept(
                    id=row.id,
                    course_id=row.course_id,
                    slug=row.slug,
                    title=row.title,
                    mastery_threshold=row.mastery_threshold,
                )
            )
        for row in (await session.execute(select(ConceptEdgeRow))).scalars():
            self.add_edge(
                ConceptEdge(
                    from_concept_id=row.from_concept_id,
                    to_concept_id=row.to_concept_id,
                    kind=row.kind,
                    weight=row.weight,
                )
            )
        # Only published items are ever selectable (PLAN_05 PR-B locked
        # decision) — a draft item created by `POST /admin/items` (default
        # status, per curriculum_admin.py) is invisible here until published.
        for row in (await session.execute(select(ItemRow).where(ItemRow.status == "published"))).scalars():
            self.add_item(
                Item(
                    id=row.id,
                    concept_id=row.concept_id,
                    kind=row.kind,
                    prompt=row.prompt,
                    payload=row.payload,
                    status=row.status,
                    created_at=_as_utc(row.created_at),
                )
            )

        await self._load_focuses()

        for row in (await session.execute(select(ReviewRow))).scalars():
            review = _review_dict(row)
            self.reviews.append(review)
            self._review_by_key[(row.person_id, row.idempotency_key)] = review
        for row in (await session.execute(select(CardStateRow))).scalars():
            self.add_card_state(
                CardState(
                    person_id=row.person_id,
                    item_id=row.item_id,
                    stability=row.stability,
                    difficulty=row.difficulty,
                    due_at=_as_utc(row.due_at),
                    state=row.state,
                    step=row.step,
                    reps=row.reps,
                    lapses=row.lapses,
                    last_review_at=_as_utc(row.last_review_at),
                )
            )
        for row in (await session.execute(select(ConceptStateRow))).scalars():
            self.add_concept_state(
                ConceptState(
                    person_id=row.person_id,
                    concept_id=row.concept_id,
                    p_known=row.p_known,
                    reviews=row.reviews,
                    last_review_at=_as_utc(row.last_review_at),
                )
            )
        # `InMemoryLearningRepository.add_answer`/`add_note`, not the
        # override below: hydrating an *existing* row must not re-queue it
        # for insert (the override's `session.add`), or the next commit in
        # this request re-inserts every previously-committed row and hits
        # the primary-key unique constraint.
        for row in (await session.execute(select(AnswerRow))).scalars():
            InMemoryLearningRepository.add_answer(
                self,
                Answer(
                    id=row.id, review_id=row.review_id, person_id=row.person_id, text=row.text,
                    created_at=_as_utc(row.created_at),
                ),
            )
        for row in (await session.execute(select(LearnerNoteRow))).scalars():
            InMemoryLearningRepository.add_note(
                self,
                LearnerNote(
                    id=row.id, person_id=row.person_id, text=row.text, created_at=_as_utc(row.created_at),
                    updated_at=_as_utc(row.updated_at),
                ),
            )

    async def _load_focuses(self) -> None:
        """Expand every `focus` row (migration 0004) into `focuses_for`
        entries the way `analytics/service.create_focus` used to mirror at
        write time: once per subtree member, for a `subtree`-scoped focus.

        Keyed by real `Person.id` only — every `/me/*` route resolves the
        acting identity to a `Person.id` first (`main.resolve_person_id`)
        whenever this repository is in play, so the old dual-key mirror
        (also under each member's `platform:external_id`) is dead weight,
        not a bridge to anything anymore.
        """
        session = self.session
        focus_rows = (await session.execute(select(FocusRow))).scalars().all()
        if not focus_rows:
            return

        children_of: dict[str, list[str]] = {}
        for person_id, manager_id in (await session.execute(select(Person.id, Person.manager_id))).all():
            if manager_id is not None:
                children_of.setdefault(manager_id, []).append(person_id)

        def subtree_of(root_id: str) -> list[str]:
            seen: set[str] = set()
            out: list[str] = []
            queue = list(children_of.get(root_id, []))
            while queue:
                person_id = queue.pop(0)
                if person_id in seen:
                    continue
                seen.add(person_id)
                out.append(person_id)
                queue.extend(children_of.get(person_id, []))
            return out

        for row in focus_rows:
            members = [row.scope_person_id]
            if row.scope_kind == "subtree":
                members += subtree_of(row.scope_person_id)
            for member in members:
                self.add_focus(
                    Focus(
                        id=row.id,
                        scope_kind=row.scope_kind,
                        scope_person_id=member,
                        concept_id=row.concept_id,
                        weight=row.weight,
                        expires_at=_as_utc(row.expires_at),
                    )
                )

    def add_note(self, note: LearnerNote) -> None:
        super().add_note(note)
        self.session.add(
            LearnerNoteRow(
                id=note.id, person_id=note.person_id, text=note.text, created_at=note.created_at, updated_at=note.updated_at
            )
        )

    def add_answer(self, answer: Answer) -> None:
        super().add_answer(answer)
        self.session.add(
            AnswerRow(
                id=answer.id, review_id=answer.review_id, person_id=answer.person_id, text=answer.text,
                created_at=answer.created_at,
            )
        )

    async def persist(self) -> None:
        """Commit whatever `add_note`/`add_answer` queued via `session.add`
        this request. Not needed after `commit_review` (it commits itself)."""
        await self.session.commit()

    # Deletes need a real `DELETE` (the in-memory list mutation the base
    # class does is not durable), so these override the inherited sync
    # methods with async ones of the same name — callers must `isinstance`-
    # check and `await` (see answers.py/notes.py) the same way they already
    # branch for `commit_review`/`persist_derived_state`.

    async def delete_note(self, person_id: str, note_id: str) -> bool:
        found = super().delete_note(person_id, note_id)
        if found:
            await self.session.execute(
                delete(LearnerNoteRow).where(LearnerNoteRow.id == note_id, LearnerNoteRow.person_id == person_id)
            )
            await self.session.commit()
        return found

    async def delete_notes_for(self, person_id: str) -> int:
        deleted = super().delete_notes_for(person_id)
        await self.session.execute(delete(LearnerNoteRow).where(LearnerNoteRow.person_id == person_id))
        await self.session.commit()
        return deleted

    async def delete_answers_for(self, person_id: str) -> int:
        deleted = super().delete_answers_for(person_id)
        await self.session.execute(delete(AnswerRow).where(AnswerRow.person_id == person_id))
        await self.session.commit()
        return deleted

    async def purge_answers_older_than(self, cutoff: datetime) -> int:
        purged = super().purge_answers_older_than(cutoff)
        await self.session.execute(delete(AnswerRow).where(AnswerRow.created_at < cutoff))
        await self.session.commit()
        return purged

    async def commit_review(self, review: dict, card_state: CardState, concept_state: ConceptState) -> tuple[dict, bool]:
        row = ReviewRow(
            id=review["id"],
            person_id=review["person_id"],
            item_id=review["item_id"],
            reviewed_at=datetime.fromisoformat(review["reviewed_at"]),
            kind=review["kind"],
            grade=review["grade"],
            rating=review["rating"],
            source=review["source"],
            idempotency_key=review["idempotency_key"],
            asserted_by=review["asserted_by"],
            result=review["result"],
            confidence=review.get("confidence"),
            bypassed=review.get("bypassed", False),
            concept_id=review.get("concept_id"),
            p_known_after=review.get("p_known_after"),
        )
        self.session.add(row)
        try:
            await self.session.flush()
        except IntegrityError:
            await self.session.rollback()
            existing = await self.session.execute(
                select(ReviewRow).where(
                    ReviewRow.person_id == review["person_id"],
                    ReviewRow.idempotency_key == review["idempotency_key"],
                )
            )
            existing_row = existing.scalar_one()
            return existing_row.result, False

        await self.session.merge(
            CardStateRow(
                person_id=card_state.person_id,
                item_id=card_state.item_id,
                stability=card_state.stability,
                difficulty=card_state.difficulty,
                due_at=card_state.due_at,
                state=card_state.state,
                step=card_state.step,
                reps=card_state.reps,
                lapses=card_state.lapses,
                last_review_at=card_state.last_review_at,
            )
        )
        await self.session.merge(
            ConceptStateRow(
                person_id=concept_state.person_id,
                concept_id=concept_state.concept_id,
                p_known=concept_state.p_known,
                reviews=concept_state.reviews,
                last_review_at=concept_state.last_review_at,
            )
        )
        await self.session.commit()
        return review["result"], True

    async def persist_derived_state(self) -> None:
        await self.session.execute(delete(CardStateRow))
        await self.session.execute(delete(ConceptStateRow))
        for card in self.card_states.values():
            self.session.add(
                CardStateRow(
                    person_id=card.person_id,
                    item_id=card.item_id,
                    stability=card.stability,
                    difficulty=card.difficulty,
                    due_at=card.due_at,
                    state=card.state,
                    step=card.step,
                    reps=card.reps,
                    lapses=card.lapses,
                    last_review_at=card.last_review_at,
                )
            )
        for concept_state in self.concept_states.values():
            self.session.add(
                ConceptStateRow(
                    person_id=concept_state.person_id,
                    concept_id=concept_state.concept_id,
                    p_known=concept_state.p_known,
                    reviews=concept_state.reviews,
                    last_review_at=concept_state.last_review_at,
                )
            )
        for review in self.reviews:
            await self.session.execute(
                update(ReviewRow)
                .where(ReviewRow.id == review["id"])
                .values(concept_id=review.get("concept_id"), p_known_after=review.get("p_known_after"))
            )
        await self.session.commit()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=timezone.utc)


def _review_dict(row: ReviewRow) -> dict:
    return {
        "id": row.id,
        "person_id": row.person_id,
        "item_id": row.item_id,
        "reviewed_at": _as_utc(row.reviewed_at).isoformat(),
        "kind": row.kind,
        "grade": row.grade,
        "rating": row.rating,
        "source": row.source,
        "idempotency_key": row.idempotency_key,
        "asserted_by": row.asserted_by,
        "result": row.result,
        "confidence": row.confidence,
        "bypassed": row.bypassed,
        "concept_id": row.concept_id,
        "p_known_after": row.p_known_after,
    }
