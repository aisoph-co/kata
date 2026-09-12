"""CI1 (KATA-13): the extraction client that turns concept drafts
`ingestion.extract_concept_drafts` already discovered (deterministic,
citation-accurate) into a real prerequisite/related classification per
co-occurring pair, and one citation-grounded multiple-choice item per
concept.

`ExtractionClient` is a structural protocol so `run_ingestion` and the test
suite can swap in `extraction.stub.StubExtractionClient` with no live model
calls, the same real/stub split a later grading package is expected to use
for its own LLM calls (`LEARNING_LLM=stub`).
"""

from __future__ import annotations

import json
import os
from typing import Any, Protocol

import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o-mini"

_RELATION_SYSTEM_PROMPT = (
    "You are structuring a course's concept graph from real engineering-issue "
    "excerpts. Given two concepts that co-occurred on at least one issue, decide "
    "whether one is a prerequisite the other depends on, or whether they are "
    'merely related. Reply with strict JSON of the form {"kind": '
    '"prerequisite"|"related", "from_slug": <string>, "to_slug": <string>, '
    '"weight": <float 0-1>} and nothing else. For "prerequisite", from_slug is '
    "the dependency and to_slug is the concept that depends on it."
)

_ITEM_SYSTEM_PROMPT = (
    "You are writing one multiple-choice review item for a concept, grounded "
    "only in the citations given — never invent a fact the citations don't "
    'support. Reply with strict JSON of the form {"prompt": <string>, '
    '"options": [<string>, <string>, <string>, <string>], "correct_index": '
    '<int 0-3>, "explanation": <string>} and nothing else. Exactly one option '
    "is correct; the other three are plausible but wrong distractors a learner "
    "could actually pick."
)


class ExtractionClient(Protocol):
    async def classify_relation(self, *, concept_a: dict[str, Any], concept_b: dict[str, Any]) -> dict[str, Any]: ...

    async def draft_item(self, *, concept: dict[str, Any], distractor_pool: list[str]) -> dict[str, Any] | None: ...


class ExtractionError(RuntimeError):
    """The extraction client could not produce a usable structured reply."""


class OpenRouterExtractionClient:
    """Real implementation — one JSON-mode chat completion per question
    asked."""

    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 20.0) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        self._model = model if model is not None else os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
        self._timeout = timeout

    async def _complete(self, *, system_prompt: str, user_content: str) -> dict[str, Any]:
        if not self._api_key:
            raise ExtractionError("OPENROUTER_API_KEY is not configured")
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                OPENROUTER_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "response_format": {"type": "json_object"},
                },
            )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ExtractionError(f"unparseable extraction response: {content!r}") from exc

    async def classify_relation(self, *, concept_a: dict[str, Any], concept_b: dict[str, Any]) -> dict[str, Any]:
        user_content = (
            f"Concept A ({concept_a['slug']}): {concept_a['title']} — {concept_a['description']}\n"
            f"Concept B ({concept_b['slug']}): {concept_b['title']} — {concept_b['description']}"
        )
        payload = await self._complete(system_prompt=_RELATION_SYSTEM_PROMPT, user_content=user_content)
        try:
            return {
                "kind": str(payload["kind"]),
                "from_slug": str(payload["from_slug"]),
                "to_slug": str(payload["to_slug"]),
                # Floored above zero, not just clamped to it: a related
                # edge with `weight == 0` is rejected downstream
                # (`curriculum_service.create_edge` requires `(0, 1]`), and
                # a cycle-fallback (`run_ingestion`) may need to write this
                # exact weight as `related`.
                "weight": max(0.05, min(1.0, float(payload["weight"]))),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtractionError(f"malformed relation classification: {payload!r}") from exc

    async def draft_item(self, *, concept: dict[str, Any], distractor_pool: list[str]) -> dict[str, Any] | None:
        # `distractor_pool` isn't needed here — the live model invents its
        # own distractors from the concept's own citations. `stub.py`'s
        # deterministic client is the one that needs sibling titles handed
        # to it.
        del distractor_pool
        if not concept.get("grounded_in"):
            return None
        user_content = (
            f"Concept ({concept['slug']}): {concept['title']} — {concept['description']}\n"
            f"Grounded in: {', '.join(concept['grounded_in'])}"
        )
        payload = await self._complete(system_prompt=_ITEM_SYSTEM_PROMPT, user_content=user_content)
        try:
            options = [str(o) for o in payload["options"]]
            correct_index = int(payload["correct_index"])
            if len(options) != 4 or not (0 <= correct_index < 4):
                raise ValueError("options must have exactly 4 entries with a valid correct_index")
            return {
                "kind": "mcq",
                "prompt": str(payload["prompt"]),
                "options": options,
                "correct_index": correct_index,
                "explanation": str(payload["explanation"]),
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ExtractionError(f"malformed item draft: {payload!r}") from exc
