"""hermes-kata: the entire integration surface between Hermes and the Kata
learning service. No other file in the Hermes config talks to the learning
service (spec: docs/superpowers/specs/2026-09-06-hermes-surface-spec.md).

Hermes loads this module and calls `register(ctx)` once at plugin start.
"""
from __future__ import annotations

from .catalog import register_tools
from .client import LearningServiceClient
from .commands import register_team_quiz_commands
from .guardrails import register_guardrail_prompt
from .identity import make_pre_gateway_dispatch
from .prompts import register_item_rendering_prompt
from .quiz import TeamQuizItemRegistry, TeamQuizState
from .reveal import CorrectAnswerers, QuizTally, record_submit_review

__all__ = ["register", "LearningServiceClient", "TeamQuizState"]


def register(ctx) -> TeamQuizState:
    client = LearningServiceClient()

    # Issue G1: one tally/registry/correct-answerers triple for the life of
    # this plugin, so the daily quiz post, every resolved answer, and the
    # on-demand reveal all read and write the same state.
    quiz_state = TeamQuizState(
        tally=QuizTally(), registry=TeamQuizItemRegistry(), correct_answerers=CorrectAnswerers()
    )

    def on_review(item_id, response, *, person_name=None):
        record_submit_review(
            quiz_state.tally, item_id, response, correct_answerers=quiz_state.correct_answerers,
            person_name=person_name,
        )

    register_tools(ctx, client, is_quiz_item=quiz_state.registry.is_quiz_item, on_review=on_review)
    ctx.register_hook("pre_gateway_dispatch", make_pre_gateway_dispatch(client))
    register_item_rendering_prompt(ctx)
    register_guardrail_prompt(ctx)
    register_team_quiz_commands(ctx, quiz_state)

    # Returned (rather than only kept as a closure) so a test, or anything
    # else that needs the live state, can reach the same tally/registry
    # `on_review` and the registered tools above are already using.
    return quiz_state
