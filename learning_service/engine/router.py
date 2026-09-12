"""`GET /me/next` + `POST /me/reviews` (spec §API, §Learning engine): grades a
submission, advances `card_state` via FSRS-6 and `concept_state` via BKT, and
returns `{grade, rating, correct, explanation, next_due_at, concept}`.

The `review` log (`repo.reviews`) is the append-only source of truth;
`card_state`/`concept_state` are derived caches recomputed here on every
submission (`POST /admin/replay`'s later replay recomputes them the same
way from the log alone).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from learning_service.engine.grading import grade_response
from learning_service.engine.models import DEFAULT_MASTERY_THRESHOLD, Answer
from learning_service.engine.openrouter import GradingError, LLMClient
from learning_service.engine.replay import apply_review
from learning_service.engine.repository import LearningRepository
from learning_service.engine.selection import DEFAULT_LIMIT, MAX_LIMIT, select_next_items
from learning_service.engine.sql_repository import SqlLearningRepository
from learning_service.main import (
    ActingIdentity,
    _error,
    acting_identity,
    get_llm_client,
    get_repository,
    resolve_person_id,
)

router = APIRouter()

# spec §Learning engine, `review.source`: platform -> source enum value.
_SOURCE_BY_PLATFORM = {
    "slack": "slack_dm",
    "telegram": "telegram",
    "discord": "discord",
    "whatsapp": "whatsapp",
    "signal": "signal",
    "web": "web",
}


class ChoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choice: int


class ChoicesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    choices: list[int] = Field(min_length=1)


class RatingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rating: int = Field(ge=1, le=4)


class TextResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


_RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "mcq": ChoiceResponse,
    "msq": ChoicesResponse,
    "self_rated": RatingResponse,
    "short_answer": TextResponse,
}


class ReviewSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str
    idempotency_key: str
    response: dict[str, Any]
    # Contract v1.2.0: `confidence` is stated *before* the reveal (1-5), a
    # different thing from `self_rated`'s post-reveal rating (1-4) — never
    # conflate the two. `bypassed` is the "just tell me" action: the learner
    # asked for the answer instead of answering.
    confidence: int | None = Field(default=None, ge=1, le=5)
    bypassed: bool = False


@router.get("/me/next")
async def me_next(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
) -> dict:
    result = select_next_items(repo, person_id, datetime.now(timezone.utc), limit)
    return {
        "items": [
            {
                "id": s.item.id,
                "concept_id": s.concept_id,
                "kind": s.item.kind,
                "prompt": s.item.prompt,
                "payload": s.item.stripped_payload(),
            }
            for s in result.items
        ],
        "reason": result.reason,
    }


@router.post("/me/reviews")
async def submit_review(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    person_id: str = Depends(resolve_person_id),
    repo: LearningRepository = Depends(get_repository),
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict[str, Any]:
    try:
        submission = ReviewSubmission.model_validate(await request.json())
    except ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc

    existing_review = repo.find_review(person_id, submission.idempotency_key)
    if existing_review is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "idempotency_replay",
                "message": "idempotency_key already used",
                "result": existing_review["result"],
            },
        )

    item = repo.get_item(submission.item_id)
    if item is None:
        raise _error(404, "item_not_found", f"unknown item_id {submission.item_id!r}")

    validated_response: BaseModel | None = None

    if submission.bypassed:
        # web-app-design.md Contract change #1 / KAT-S2: a bypass is "just
        # tell me" — the learner never actually answers, so validation and
        # grading are skipped entirely. This must run *before* the
        # teach_back/no_grader check and the grader dispatch below, or the
        # one kind where bypass is the only possible action gets rejected,
        # and a bypassed short_answer still pays for a live LLM call whose
        # result is immediately discarded. Grade 0.0, rating 1 (never a
        # success; replay's uniform `rating >= 3` treats it as incorrect, no
        # kind-specific branch needed), and the canned answer/explanation
        # returned regardless of kind so the learner actually gets told.
        grade, rating, correct = 0.0, 1, False
        explanation = item.payload.get("explanation") or item.payload.get("answer") or item.payload.get("reference")
    else:
        if item.kind == "teach_back":
            raise _error(422, "no_grader", "teach_back items have no grader yet")

        response_model = _RESPONSE_MODELS.get(item.kind)
        if response_model is None:
            raise _error(422, "no_grader", f"no grader for item kind {item.kind!r}")
        try:
            validated_response = response_model.model_validate(submission.response)
        except ValidationError as exc:
            raise _error(422, "validation_error", str(exc)) from exc

        try:
            result = await grade_response(item, validated_response.model_dump(), llm_client)
        except GradingError as exc:
            raise _error(502, "grading_failed", str(exc)) from exc
        grade, rating, correct, explanation = result.grade, result.rating, result.correct, result.explanation

    reviewed_at = datetime.now(timezone.utc)
    # Generated here, not after `apply_review` returns: an out-of-order
    # review (engine/replay.py, `_fold_card_state`/`_fold_concept_state`)
    # breaks an exact `reviewed_at` tie by `id`, the same key
    # `rebuild_derived_state` sorts by — passing this review's real id in as
    # the tiebreak keeps a live tie and a later `/admin/replay` of it in
    # agreement.
    review_id = str(uuid.uuid4())

    new_card, new_concept_state = apply_review(
        repo,
        person_id=person_id,
        item_id=item.id,
        concept_id=item.concept_id,
        kind=item.kind,
        rating=rating,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )

    concept = repo.get_concept(item.concept_id)
    mastery_threshold = concept.mastery_threshold if concept is not None else DEFAULT_MASTERY_THRESHOLD

    response_body = {
        "grade": grade,
        "rating": rating,
        "correct": correct,
        "explanation": explanation,
        "confidence": submission.confidence,
        "bypassed": submission.bypassed,
        "next_due_at": new_card.due_at.isoformat(),
        "concept": {
            "p_known": new_concept_state.p_known,
            "mastered": new_concept_state.p_known >= mastery_threshold,
        },
    }
    review = {
        "id": review_id,
        "person_id": person_id,
        "item_id": item.id,
        "reviewed_at": reviewed_at.isoformat(),
        "kind": item.kind,
        "grade": grade,
        "rating": rating,
        "source": _SOURCE_BY_PLATFORM.get(identity.platform, identity.platform),
        "idempotency_key": submission.idempotency_key,
        "asserted_by": f"{identity.platform}:{identity.external_id}",
        "result": response_body,
        "confidence": submission.confidence,
        "bypassed": submission.bypassed,
        # `concept_id`/`p_known_after`: written here, at the point where
        # `item.concept_id` and the just-computed `new_concept_state.p_known`
        # are both in hand, rather than recomputed on read — see
        # `engine/replay.py:rebuild_derived_state` for the replay/seed
        # backfill of the same two fields on historical rows.
        "concept_id": item.concept_id,
        "p_known_after": new_concept_state.p_known,
    }
    # spec §Privacy and retention: `answer` rows are written only for
    # short_answer (teach_back has no grader yet, so it never reaches this
    # line — see the 422 `no_grader` branch above). A bypassed short_answer
    # never validated a real response (see above), so there is no answer
    # text to record.
    if item.kind == "short_answer" and validated_response is not None:
        answer = Answer(
            id=str(uuid.uuid4()),
            review_id=review_id,
            person_id=person_id,
            text=validated_response.text,
            created_at=reviewed_at,
        )
        repo.add_answer(answer)

    if isinstance(repo, SqlLearningRepository):
        # Never check-then-insert (PLAN_05 PR-B locked decision): two
        # concurrent identical submissions both reach here and both compute
        # the same `response_body`; only one `review` row wins the unique
        # constraint on `(person_id, idempotency_key)` and its
        # card_state/concept_state are the ones persisted. The loser
        # discards its own (already-mutated-in-memory, never durably
        # written) computation and gets the same 409 `idempotency_replay`
        # the sequential pre-check above raises — the response, not just its
        # `result` payload, must match.
        stored_result, is_new = await repo.commit_review(review, new_card, new_concept_state)
        if not is_new:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "idempotency_replay",
                    "message": "idempotency_key already used",
                    "result": stored_result,
                },
            )
        return stored_result

    repo.append_review(review)
    return response_body
