"""AGCTM-69's fallback for "reveal the team kata results" while no live quiz
exists to reveal (`team_reveal.py`): `kata_reveal` returns the pinned
Ferry-seed Block Kit payload (`docs/demo/slack/kata-reveal.blockkit.json`)
unchanged, and the plugin tells Kata to post it verbatim.
"""

from __future__ import annotations

import json

from fakes import FakePluginContext

from hermes_kata.team_reveal import (
    HARDCODED_REVEAL_BLOCKS,
    KATA_REVEAL_TOOL_NAME,
    SECTION_ID,
    SYSTEM_PROMPT_TEAM_REVEAL_RENDERING,
    make_team_reveal_handler,
    register_team_reveal,
    render_reveal_blocks,
)


def test_render_reveal_blocks_returns_the_pinned_template_unchanged():
    assert render_reveal_blocks() == HARDCODED_REVEAL_BLOCKS
    assert HARDCODED_REVEAL_BLOCKS["blocks"][0]["text"]["text"] == "*1/2 · Why did we revert?*   `4 of 9`"
    assert HARDCODED_REVEAL_BLOCKS["blocks"][-1]["type"] == "context"


def test_handler_returns_the_pinned_template_as_a_json_string():
    handler = make_team_reveal_handler()

    result = handler({}, session_id="sess-1")

    assert isinstance(result, str)
    assert json.loads(result) == HARDCODED_REVEAL_BLOCKS


def test_handler_ignores_any_arguments_and_session():
    handler = make_team_reveal_handler()

    result = handler({"anything": "goes"}, session_id=None)

    assert json.loads(result) == HARDCODED_REVEAL_BLOCKS


def test_register_team_reveal_wires_the_tool_and_the_system_prompt_section():
    ctx = FakePluginContext()

    register_team_reveal(ctx)

    assert KATA_REVEAL_TOOL_NAME in ctx.tools
    assert ctx.tools[KATA_REVEAL_TOOL_NAME]["toolset"] == "learning"
    assert json.loads(ctx.tools[KATA_REVEAL_TOOL_NAME]["handler"]({})) == HARDCODED_REVEAL_BLOCKS
    assert ctx.system_prompt_sections[SECTION_ID]["content"] == SYSTEM_PROMPT_TEAM_REVEAL_RENDERING
