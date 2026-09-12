"""Grading dispatch per item kind (spec §Curriculum, "Item payloads"; §API
"Grading"), with a stub LLM client for `short_answer` (spec §Testing,
"Grading": "one recorded-response test per rubric shape").
"""

import pytest

from learning_service.curriculum.models import Item
from learning_service.grading.service import NoGraderError, grade_response
from learning_service.grading.stub import StubGraderClient


def _item(kind: str, payload: dict, prompt: str = "prompt") -> Item:
    return Item(id="item-1", concept_id="concept-1", kind=kind, prompt=prompt, payload=payload, status="published")


async def test_mcq_correct():
    item = _item("mcq", {"options": ["a", "b"], "correct_index": 1, "explanation": "because"})
    result = await grade_response(item, {"choice": 1}, StubGraderClient())
    assert result.grade == 1.0
    assert result.rating == 3
    assert result.correct is True
    assert result.explanation == "because"


async def test_mcq_incorrect():
    item = _item("mcq", {"options": ["a", "b"], "correct_index": 1})
    result = await grade_response(item, {"choice": 0}, StubGraderClient())
    assert result.grade == 0.0
    assert result.rating == 1
    assert result.correct is False


async def test_msq_partial_credit():
    item = _item("msq", {"options": ["a", "b", "c"], "correct_indices": [0, 1]})
    result = await grade_response(item, {"choices": [0]}, StubGraderClient())
    assert result.grade == 0.5
    assert result.rating == 2


async def test_self_rated_uses_learner_rating_directly():
    item = _item("self_rated", {"answer": "the answer"})
    result = await grade_response(item, {"rating": 4}, StubGraderClient())
    assert result.grade == 1.0
    assert result.rating == 4
    assert result.correct is True
    assert result.explanation == "the answer"


async def test_short_answer_uses_llm_client():
    item = _item("short_answer", {"reference": "ref", "rubric": "widget factory pattern"})
    result = await grade_response(item, {"text": "we used the widget factory pattern"}, StubGraderClient())
    assert result.grade == 1.0
    assert result.rating == 4
    assert result.correct is True


async def test_short_answer_partial_match_is_hard_or_lower():
    item = _item("short_answer", {"reference": "ref", "rubric": "widget factory pattern"})
    result = await grade_response(item, {"text": "no idea"}, StubGraderClient())
    assert result.grade == 0.1
    assert result.rating == 1


async def test_teach_back_has_no_grader():
    item = _item("teach_back", {"reference": "ref", "rubric": "rubric"})
    with pytest.raises(NoGraderError):
        await grade_response(item, {"text": "x"}, StubGraderClient())
