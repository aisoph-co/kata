"""Job 3 (adapter-contract): render choice items.

No new rendering code — both `mcq` and `msq` items go through the built-in
`clarify` tool, which already round-trips as native buttons/checkboxes per
platform (spec §8). This module shapes the `clarify` call, maps its
resolution back to `submit_review`'s payload, and — via
`register_mcq_rendering_section` — puts the instruction to actually do that
into the live system prompt (spec §8: "the system prompt instructs the
agent..."). Without that section registered, nothing tells Kata to call
`clarify` instead of typing options as chat text.
"""

from __future__ import annotations

from typing import Any, Mapping

MCQ_KIND = "mcq"
MSQ_KIND = "msq"

SECTION_ID = "kata-mcq-rendering"
MAX_CHARS = 1000

SYSTEM_PROMPT_MCQ_RENDERING = """\
MCQ/MSQ rendering — never print item options as chat text:
1. For an `mcq` item, call clarify(question=item.prompt, \
choices=item.options, multi_select=false).
2. For an `msq` item (select-all-that-apply), call \
clarify(question=item.prompt, choices=item.options, multi_select=true).
3. Wait for clarify's resolution rather than asking the learner to reply \
with option numbers in chat.
"""


def clarify_kwargs_for_item(item: Mapping[str, Any]) -> dict:
    """Build the `clarify(...)` call arguments for an `mcq` or `msq` item
    (spec §8). Never renders options as chat text."""
    kind = item["kind"]
    if kind not in (MCQ_KIND, MSQ_KIND):
        raise ValueError(f"clarify_kwargs_for_item: not a choice item kind: {kind!r}")
    return {
        "question": item["prompt"],
        "choices": list(item["options"]),
        "multi_select": kind == MSQ_KIND,
    }


def submit_review_response(item: Mapping[str, Any], prompt_response: Any) -> dict:
    """Map a resolved `clarify` response back to `submit_review`'s
    `response` payload (spec §8):

    - `mcq`'s tap: `event.prompt_response.option_id` -> `{"choice": <index>}`
    - `msq`'s selections: a decoded list -> `{"choices": [<index>, ...]}`
    """
    kind = item["kind"]
    if kind == MCQ_KIND:
        return {"choice": int(prompt_response)}
    if kind == MSQ_KIND:
        choices = [int(v) for v in prompt_response]
        return {"choices": choices}
    raise ValueError(f"submit_review_response: not a choice item kind: {kind!r}")


def register_mcq_rendering_section(ctx: Any) -> None:
    """Wire `SYSTEM_PROMPT_MCQ_RENDERING` into the live system prompt (same
    `after_memory` position the spec uses for context injection)."""
    ctx.register_system_prompt_section(
        SECTION_ID,
        SYSTEM_PROMPT_MCQ_RENDERING,
        position="after_memory",
        max_chars=MAX_CHARS,
    )
