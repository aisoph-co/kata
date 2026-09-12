"""`StubGraderClient` (PLAN_05 PR-A, `LEARNING_LLM=stub`): deterministic
grading by word overlap against the rubric's first line, so the demo and
tests never call OpenRouter."""

from __future__ import annotations

from learning_service.engine.stub_grader import StubGraderClient

RUBRIC = "explain the recursive call\nSecond line is ignored."


async def test_full_word_match_grades_one():
    client = StubGraderClient()
    grade, _ = await client.grade(
        prompt="p", reference="r", rubric=RUBRIC, response_text="I will explain the recursive call in detail"
    )
    assert grade == 1.0


async def test_half_word_match_grades_half():
    client = StubGraderClient()
    grade, _ = await client.grade(
        prompt="p", reference="r", rubric=RUBRIC, response_text="I will explain the process"
    )
    assert grade == 0.5


async def test_below_half_word_match_grades_low():
    client = StubGraderClient()
    grade, _ = await client.grade(prompt="p", reference="r", rubric=RUBRIC, response_text="totally unrelated answer")
    assert grade == 0.1


async def test_matching_is_whole_word_not_substring():
    # Regression: "sum" is a substring of "consumer" and "assumption" but is
    # not the same word — a naive `word in response_text` match would wrongly
    # grade this 1.0.
    client = StubGraderClient()
    grade, _ = await client.grade(prompt="p", reference="r", rubric="sum", response_text="consumer assumption")
    assert grade == 0.1


async def test_matching_is_case_insensitive():
    client = StubGraderClient()
    grade, _ = await client.grade(
        prompt="p", reference="r", rubric=RUBRIC, response_text="EXPLAIN THE RECURSIVE CALL"
    )
    assert grade == 1.0


async def test_empty_rubric_grades_minimum():
    client = StubGraderClient()
    grade, explanation = await client.grade(prompt="p", reference="r", rubric="", response_text="anything")
    assert grade == 0.1
    assert "empty" in explanation.lower() or "no words" in explanation.lower()


async def test_never_touches_network():
    # No httpx / OpenRouter import happens in this module at all — the stub
    # grader is a pure string comparison.
    import learning_service.engine.stub_grader as module

    assert "httpx" not in dir(module)
