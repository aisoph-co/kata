"""Grading (spec §Decisions, "Grading": "the service grades, calling
OpenRouter with a per-item rubric... Slack and web grade identically; the
Hermes agent never sees answer keys"). `mcq`/`msq`/`self_rated` are
deterministic; `short_answer` calls an `LLMClient` (OpenRouter in
production, a stub in tests — spec §Testing, "Grading").
"""

from __future__ import annotations
