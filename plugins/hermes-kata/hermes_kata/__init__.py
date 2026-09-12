"""hermes-kata: the entire integration surface between Hermes and the Kata
learning service. No other file in the Hermes config talks to the learning
service (spec: docs/superpowers/specs/2026-09-06-hermes-surface-spec.md).

Hermes loads this module and calls `register(ctx)` once at plugin start.
"""
from __future__ import annotations

from .catalog import register_tools
from .client import LearningServiceClient
from .identity import make_pre_gateway_dispatch
from .prompts import register_item_rendering_prompt

__all__ = ["register", "LearningServiceClient"]


def register(ctx) -> None:
    client = LearningServiceClient()
    register_tools(ctx, client)
    ctx.register_hook("pre_gateway_dispatch", make_pre_gateway_dispatch(client))
    register_item_rendering_prompt(ctx)
