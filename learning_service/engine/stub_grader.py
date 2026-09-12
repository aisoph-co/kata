"""Deterministic `short_answer` grader behind `LEARNING_LLM=stub` (PLAN_05
PR-A): a demo/dev mode that never calls OpenRouter, so the seeded demo and
CI never spend money or flake on a live model.

Grade is decided by how many of the rubric's first line's words show up
(case-insensitive, whole-word) in the learner's response: every word -> 1.0,
at least half -> 0.5, otherwise -> 0.1.
"""

from __future__ import annotations

import re


class StubGraderClient:
    async def grade(self, *, prompt: str, reference: str, rubric: str, response_text: str) -> tuple[float, str]:
        rubric_first_line = rubric.splitlines()[0] if rubric else ""
        words = re.findall(r"\w+", rubric_first_line.lower())
        response_words = set(re.findall(r"\w+", response_text.lower()))

        if not words:
            return 0.1, "stub grader: rubric has no words to match, minimum credit"

        matched = sum(1 for word in words if word in response_words)
        if matched == len(words):
            grade = 1.0
        elif matched * 2 >= len(words):
            grade = 0.5
        else:
            grade = 0.1
        return grade, f"stub grader: matched {matched}/{len(words)} rubric words"
