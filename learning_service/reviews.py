"""`GET /me/next` + `POST /me/reviews` (spec §Learning engine, §API):
next-item selection and review submission — grades a response, advances
`card_state` via FSRS-6 and `concept_state` via BKT, and returns
`{grade, rating, correct, explanation, confidence, bypassed, next_due_at,
concept}`.

The `review` log is the append-only source of truth; `card_state`/
`concept_state` are derived caches recomputed here on every submission
(`POST /admin/replay` recomputes them the same way from the log alone —
`engine/replay.py`).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from learning_service.curriculum import service as curriculum_service
from learning_service.curriculum.models import DEFAULT_MASTERY_THRESHOLD
from learning_service.db import get_session
from learning_service.engine.models import Review
from learning_service.engine.replay import apply_review
from learning_service.engine.selection import DEFAULT_LIMIT, MAX_LIMIT, select_next_items, stripped_payload
from learning_service.grading.openrouter import GradingError, LLMClient, OpenRouterClient
from learning_service.grading.service import grade_response
from learning_service.grading.stub import StubGraderClient
from learning_service.main import ActingIdentity, _error, acting_identity, resolve_person_id
from learning_service.privacy.models import Answer

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


def _build_llm_client() -> LLMClient:
    # `LEARNING_LLM=stub` swaps in a deterministic grader so demos and tests
    # never call OpenRouter or spend money; unset stays OpenRouter. A
    # missing `OPENROUTER_API_KEY` only fails a `short_answer` review at
    # grading time, not startup.
    if os.environ.get("LEARNING_LLM") == "stub":
        return StubGraderClient()
    return OpenRouterClient()


_llm_client: LLMClient = _build_llm_client()


def get_llm_client() -> LLMClient:
    return _llm_client


@router.get("/me/next")
async def me_next(
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await select_next_items(session, person_id, datetime.now(timezone.utc), limit)
    return {
        "items": [
            {
                "id": s.item.id,
                "concept_id": s.concept_id,
                "kind": s.item.kind,
                "prompt": s.item.prompt,
                "payload": stripped_payload(s.item),
            }
            for s in result.items
        ],
        "reason": result.reason,
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
    # Contract v1.2.1 (row 1): `confidence` is stated *before* the reveal
    # (1-5), a different thing from `self_rated`'s post-reveal rating (1-4).
    # `bypassed` is "just tell me": the learner asked for the answer instead
    # of answering.
    confidence: int | None = Field(default=None, ge=1, le=5)
    bypassed: bool = False


@router.post("/me/reviews")
async def submit_review(
    request: Request,
    identity: ActingIdentity = Depends(acting_identity),
    person_id: str = Depends(resolve_person_id),
    session: AsyncSession = Depends(get_session),
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict[str, Any]:
    try:
        submission = ReviewSubmission.model_validate(await request.json())
    except ValidationError as exc:
        raise _error(422, "validation_error", str(exc)) from exc

    existing = await session.execute(
        select(Review).where(Review.person_id == person_id, Review.idempotency_key == submission.idempotency_key)
    )
    existing_review = existing.scalar_one_or_none()
    if existing_review is not None:
        raise HTTPException(
            status_code=409,
            detail={"code": "idempotency_replay", "message": "idempotency_key already used", "result": existing_review.result},
        )

    item = await curriculum_service.get_item(session, submission.item_id)
    if item is None:
        raise _error(404, "item_not_found", f"unknown item_id {submission.item_id!r}")

    validated_response: BaseModel | None = None

    if submission.bypassed:
        # "Just tell me": the learner never actually answers, so validation
        # and grading are skipped entirely — before the teach_back/no_grader
        # check below, so bypass stays the one possible action on a
        # teach_back item. Grade 0.0, rating 1 (never a success; a bypassed
        # review never grades above 0.3 per this issue's done check).
        grade, rating, correct = 0.0, 1, False
        payload = item.payload or {}
        explanation = payload.get("explanation") or payload.get("answer") or payload.get("reference")
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
    # Generated here, not after `apply_review` returns: an exact
    # `reviewed_at` tie is broken by `id`, the same key `engine.replay`
    # sorts by, so this review and a later `/admin/replay` of it agree.
    review_id = str(uuid.uuid4())

    new_card, new_concept_state = await apply_review(
        session,
        person_id=person_id,
        item_id=item.id,
        concept_id=item.concept_id,
        kind=item.kind,
        rating=rating,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )

    concept = await curriculum_service.get_concept(session, item.concept_id)
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

    review = Review(
        id=review_id,
        person_id=person_id,
        item_id=item.id,
        concept_id=item.concept_id,
        reviewed_at=reviewed_at,
        kind=item.kind,
        grade=grade,
        rating=rating,
        source=_SOURCE_BY_PLATFORM.get(identity.platform, identity.platform),
        idempotency_key=submission.idempotency_key,
        asserted_by=f"{identity.platform}:{identity.external_id}",
        result=response_body,
        confidence=submission.confidence,
        bypassed=submission.bypassed,
    )
    session.add(review)

    # spec §Privacy and retention: `answer` rows are written only for
    # short_answer (and, once it has a grader, teach_back) kinds. A bypassed
    # short_answer never validated a real response, so there is no answer
    # text to record.
    if item.kind == "short_answer" and validated_response is not None:
        session.add(Answer(review_id=review_id, person_id=person_id, text=validated_response.text, created_at=reviewed_at))

    await session.commit()
    return response_body
