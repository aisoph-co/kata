"""OpenRouter-backed grader for `short_answer` items (spec §Decisions,
"Grading").

`LLMClient` is a structural protocol so `grading.service.grade_response` —
and the test suite — can swap in a stub with no live model calls (spec
§Testing, "Grading": "one recorded-response test per rubric shape").
"""

from __future__ import annotations

import json
import os
from typing import Protocol

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

_SYSTEM_PROMPT = (
    "You are grading a learner's short-answer response against a rubric. "
    'Reply with strict JSON of the form {"grade": <float 0-1>, "explanation": <string>} '
    "and nothing else."
)


class LLMClient(Protocol):
    async def grade(self, *, prompt: str, reference: str, rubric: str, response_text: str) -> tuple[float, str]: ...


class GradingError(RuntimeError):
    """The grader could not produce a usable `(grade, explanation)` pair."""


class OpenRouterClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 20.0) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self._model = model if model is not None else os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self._timeout = timeout

    async def grade(self, *, prompt: str, reference: str, rubric: str, response_text: str) -> tuple[float, str]:
        if not self._api_key:
            raise GradingError("OPENROUTER_API_KEY is not configured")

        user_content = (
            f"Question: {prompt}\nRubric: {rubric}\nReference answer: {reference}\nLearner response: {response_text}"
        )
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            payload = json.loads(content)
            grade = float(payload["grade"])
            explanation = str(payload["explanation"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GradingError(f"unparseable OpenRouter grading response: {content!r}") from exc
        return max(0.0, min(1.0, grade)), explanation
