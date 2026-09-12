"""Deterministic `ExtractionClient` behind `LEARNING_LLM=stub` — the only
`ExtractionClient` the test suite ever calls, so CI never spends money or
flakes on a live model.

Direction is inferred without reading either concept's meaning, purely from
how many distinct seeded issues each concept slug is tagged on: the concept
touched by more issues is treated as the broader, more foundational one a
narrower concept depends on (`kind="prerequisite"`, `from=` the
more-touched slug); a tie can't be resolved this way and is left `related`.
This is a workable placeholder for demos and tests, not a claim of real
inference — `client.OpenRouterExtractionClient` is what actually reads the
concepts' descriptions in production.
"""

from __future__ import annotations

from typing import Any


class StubExtractionClient:
    def __init__(self, frequency: dict[str, int]) -> None:
        self._frequency = frequency

    async def classify_relation(self, *, concept_a: dict[str, Any], concept_b: dict[str, Any]) -> dict[str, Any]:
        slug_a, slug_b = concept_a["slug"], concept_b["slug"]
        freq_a = self._frequency.get(slug_a, 0)
        freq_b = self._frequency.get(slug_b, 0)
        if freq_a == freq_b:
            return {"kind": "related", "from_slug": slug_a, "to_slug": slug_b, "weight": 0.6}
        from_slug, to_slug = (slug_a, slug_b) if freq_a > freq_b else (slug_b, slug_a)
        return {"kind": "prerequisite", "from_slug": from_slug, "to_slug": to_slug, "weight": 1.0}

    async def draft_item(self, *, concept: dict[str, Any], distractor_pool: list[str]) -> dict[str, Any] | None:
        # The review-gate rule: a concept with no traceable citation gets no
        # item at all — there's nothing sourced to ask, so it can never
        # leave `draft` (done check: "a concept with no traceable citation
        # is written draft, never published").
        if not concept.get("grounded_in"):
            return None

        title = concept["title"]
        distractors = [t for t in distractor_pool if t != title][:3]
        filler = 0
        while len(distractors) < 3:
            distractors.append(f"None of the above ({filler})")
            filler += 1
        options = [title, *distractors]
        # Deterministic rotation keyed by the concept's own slug, so the
        # correct option isn't always index 0 without needing real
        # randomness (which would break test determinism).
        offset = sum(ord(c) for c in concept["slug"]) % len(options)
        options = options[offset:] + options[:offset]

        return {
            "kind": "mcq",
            "prompt": f"Which of these does {concept['grounded_in'][0]} actually ground?",
            "options": options,
            "correct_index": options.index(title),
            "explanation": concept.get("description") or title,
        }
