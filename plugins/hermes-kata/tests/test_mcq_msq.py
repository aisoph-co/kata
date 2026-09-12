"""Spec §8: mcq/msq items render only through `clarify`, never as chat text;
msq resolves to a set (`response.choices`), mcq to a single choice."""

from __future__ import annotations

import pytest
from fakes import FakePluginContext

from hermes_kata.mcq import (
    SECTION_ID,
    SYSTEM_PROMPT_MCQ_RENDERING,
    clarify_kwargs_for_item,
    register_mcq_rendering_section,
    submit_review_response,
)

MCQ_ITEM = {
    "kind": "mcq",
    "prompt": "Which keyword declares a block-scoped variable in JS?",
    "options": ["var", "let", "function", "class"],
}

MSQ_ITEM = {
    "kind": "msq",
    "prompt": "Select every statement that is true of the DoD.",
    "options": ["A", "B", "C", "D"],
}


def test_mcq_clarify_call_has_choices_and_no_multi_select():
    kwargs = clarify_kwargs_for_item(MCQ_ITEM)
    assert kwargs["question"] == MCQ_ITEM["prompt"]
    assert kwargs["choices"] == MCQ_ITEM["options"]
    assert kwargs["multi_select"] is False


def test_msq_clarify_call_sets_multi_select_true():
    kwargs = clarify_kwargs_for_item(MSQ_ITEM)
    assert kwargs["choices"] == MSQ_ITEM["options"]
    assert kwargs["multi_select"] is True


def test_non_choice_item_kind_is_rejected():
    with pytest.raises(ValueError):
        clarify_kwargs_for_item({"kind": "short_answer", "prompt": "x", "options": []})


def test_mcq_tap_resolves_to_a_single_choice_payload():
    assert submit_review_response(MCQ_ITEM, 1) == {"choice": 1}


def test_msq_selection_resolves_to_a_choices_array_payload():
    assert submit_review_response(MSQ_ITEM, [0, 2]) == {"choices": [0, 2]}


def test_msq_selection_is_a_set_never_a_single_choice():
    result = submit_review_response(MSQ_ITEM, ["1", "3"])
    assert isinstance(result["choices"], list)
    assert result == {"choices": [1, 3]}


# Wiring — without this, SYSTEM_PROMPT_MCQ_RENDERING above is defined but
# never reaches the live prompt, so nothing tells the agent to call clarify
# instead of typing options as chat text.
def test_register_mcq_rendering_section_puts_the_instruction_in_the_prompt():
    ctx = FakePluginContext()
    register_mcq_rendering_section(ctx)
    assert ctx.system_prompt_sections[SECTION_ID]["content"] == SYSTEM_PROMPT_MCQ_RENDERING
    assert ctx.system_prompt_sections[SECTION_ID]["position"] == "after_memory"
