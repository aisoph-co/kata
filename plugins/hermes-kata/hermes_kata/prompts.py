"""System-prompt instruction for rendering `mcq`/`msq` items (spec §8).

No new rendering code: the relay layer already turns a `clarify` call into
native buttons (mcq) or checkboxes (msq) per platform
(`gateway/platforms/base.py`). This is the instruction that gets the agent
to call `clarify` instead of ever typing options as chat text.
"""
from __future__ import annotations

MCQ_MSQ_INSTRUCTION = """\
When presenting an `mcq` item, call clarify(question=<item prompt>, \
choices=<item options>, multi_select=false). Never type the options as \
chat text.
When presenting an `msq` item, call clarify(question=<item prompt>, \
choices=<item options>, multi_select=true) — same rule, multi-select on.
Wait for the clarify result before calling submit_review.
"""


def register_item_rendering_prompt(ctx) -> None:
    ctx.register_system_prompt_section(
        "kata-item-rendering",
        lambda session_info: MCQ_MSQ_INSTRUCTION,
        position="after_memory",
    )
