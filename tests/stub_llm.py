"""Stub `LLMClient` (spec §Learning engine, "short_answer graded via
OpenRouter ... tested with a stub LLM client"). No test in this suite calls
a live model."""

from __future__ import annotations


class StubLLMClient:
    """Returns a grade looked up by the learner's exact response text, so
    tests stay deterministic. Falls back to `default_grade` for unlisted
    responses."""

    def __init__(self, grades: dict[str, float] | None = None, default_grade: float = 0.5) -> None:
        self._grades = grades or {}
        self._default_grade = default_grade
        self.calls: list[dict[str, str]] = []

    async def grade(self, *, prompt: str, reference: str, rubric: str, response_text: str) -> tuple[float, str]:
        self.calls.append(
            {"prompt": prompt, "reference": reference, "rubric": rubric, "response_text": response_text}
        )
        grade = self._grades.get(response_text, self._default_grade)
        return grade, f"stub grading of {response_text!r} against rubric {rubric!r}"
