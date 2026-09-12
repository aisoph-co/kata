"""Per-kind grading dispatch (spec §Learning engine, "Rating mapping";
§Curriculum, "Item payloads"). `correct` is defined uniformly as
`rating >= 3` (spec §Learning engine, "BKT"), so replay never needs a
kind-specific branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from learning_service.curriculum.models import Item
from learning_service.engine.rating import SELF_RATED_GRADE, msq_rating, msq_score, short_answer_rating
from learning_service.grading.openrouter import LLMClient


@dataclass(frozen=True)
class GradeResult:
    grade: float
    rating: int
    correct: bool
    explanation: str | None


class NoGraderError(ValueError):
    """Raised for an item kind with no grader (`teach_back`, or unknown)."""


async def grade_response(item: Item, response: dict[str, Any], llm_client: LLMClient) -> GradeResult:
    payload = item.payload or {}
    if item.kind == "mcq":
        is_correct = response["choice"] == payload.get("correct_index")
        grade = 1.0 if is_correct else 0.0
        rating = 3 if is_correct else 1
        explanation = payload.get("explanation")
    elif item.kind == "msq":
        grade = msq_score(response["choices"], payload.get("correct_indices", []))
        rating = msq_rating(grade)
        explanation = payload.get("explanation")
    elif item.kind == "self_rated":
        rating = response["rating"]
        grade = SELF_RATED_GRADE[rating]
        explanation = payload.get("answer")
    elif item.kind == "short_answer":
        grade, explanation = await llm_client.grade(
            prompt=item.prompt,
            reference=payload.get("reference", ""),
            rubric=payload.get("rubric", ""),
            response_text=response["text"],
        )
        rating = short_answer_rating(grade)
    else:
        raise NoGraderError(f"no grader for item kind {item.kind!r}")

    return GradeResult(grade=grade, rating=rating, correct=rating >= 3, explanation=explanation)
