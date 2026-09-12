"""Unit tests for per-kind grading dispatch (AGCTM-30). `short_answer` is
exercised only against `StubLLMClient` — no live model calls."""

import pytest

from learning_service.engine.grading import NoGraderError, grade_response
from learning_service.engine.models import Item
from tests.stub_llm import StubLLMClient


def mcq_item(correct_index: int = 1) -> Item:
    return Item(
        id="i-mcq",
        concept_id="c1",
        kind="mcq",
        prompt="2+2?",
        payload={"options": ["3", "4"], "correct_index": correct_index, "explanation": "arithmetic"},
    )


def msq_item() -> Item:
    return Item(
        id="i-msq",
        concept_id="c1",
        kind="msq",
        prompt="pick the primes",
        payload={"options": ["2", "3", "4"], "correct_indices": [0, 1], "explanation": "2 and 3 are prime"},
    )


def self_rated_item() -> Item:
    return Item(
        id="i-sr",
        concept_id="c1",
        kind="self_rated",
        prompt="recall the mnemonic",
        payload={"answer": "the model answer"},
    )


def short_answer_item() -> Item:
    return Item(
        id="i-sa",
        concept_id="c1",
        kind="short_answer",
        prompt="explain recursion",
        payload={"reference": "a function calling itself", "rubric": "mentions base case"},
    )


@pytest.mark.parametrize(
    ("choice", "expected_grade", "expected_rating", "expected_correct"),
    [(1, 1.0, 3, True), (0, 0.0, 1, False)],
)
async def test_mcq_grading(choice, expected_grade, expected_rating, expected_correct):
    result = await grade_response(mcq_item(), {"choice": choice}, StubLLMClient())
    assert result.grade == expected_grade
    assert result.rating == expected_rating
    assert result.correct is expected_correct
    assert result.explanation == "arithmetic"


async def test_msq_grading_uses_partial_credit_and_binarizes_via_rating():
    result = await grade_response(msq_item(), {"choices": [0]}, StubLLMClient())
    assert result.grade == 0.5
    assert result.rating == 2  # Hard: 0.5 <= score < 0.75
    assert result.correct is False

    result = await grade_response(msq_item(), {"choices": [0, 1]}, StubLLMClient())
    assert result.grade == 1.0
    assert result.rating == 4
    assert result.correct is True


async def test_self_rated_grading_uses_the_learners_rating_directly():
    result = await grade_response(self_rated_item(), {"rating": 4}, StubLLMClient())
    assert result.grade == 1.0
    assert result.rating == 4
    assert result.correct is True
    assert result.explanation == "the model answer"

    result = await grade_response(self_rated_item(), {"rating": 1}, StubLLMClient())
    assert result.grade == 0.0
    assert result.correct is False


async def test_short_answer_grading_calls_the_stub_llm_client_only():
    stub = StubLLMClient(grades={"a function calling itself, base case handled": 0.95})
    result = await grade_response(
        short_answer_item(), {"text": "a function calling itself, base case handled"}, stub
    )
    assert result.grade == 0.95
    assert result.rating == 4
    assert result.correct is True
    assert len(stub.calls) == 1
    assert stub.calls[0]["rubric"] == "mentions base case"
    assert stub.calls[0]["reference"] == "a function calling itself"


async def test_teach_back_has_no_grader():
    item = Item(id="i-tb", concept_id="c1", kind="teach_back", prompt="explain it back", payload={})
    with pytest.raises(NoGraderError):
        await grade_response(item, {"text": "whatever"}, StubLLMClient())
