"""End-to-end plugin-registration test.

`hermes_kata.register(ctx)` is what Hermes actually calls at plugin start;
it must use the real `PluginContext` API. `FakePluginContext` exposes only
`register_tool`/`register_hook`/`register_system_prompt_section` — the
methods the real Hermes `PluginContext` ships — so calling a shortcut that
doesn't exist on the real API (e.g. a `register_pre_gateway_dispatch`) fails
this test with `AttributeError` rather than passing a suite that never
exercised real plugin startup.
"""
from conftest import FakePluginContext

import hermes_kata
from hermes_kata.catalog import load_tool_catalog


def test_register_wires_tools_identity_hook_and_prompt_section_via_real_api():
    ctx = FakePluginContext()

    quiz_state = hermes_kata.register(ctx)

    catalog = load_tool_catalog()
    # The forwarded learning-service catalog, plus issue G1's three
    # plugin-native tools (sync_digest_jobs/post_team_quiz/reveal_team_quiz)
    # — commands.py, not a learning-service endpoint, so they're additional
    # to the catalog rather than in it.
    assert set(ctx.tools) == {tool.name for tool in catalog} | {
        "sync_digest_jobs",
        "post_team_quiz",
        "reveal_team_quiz",
    }
    for name in ("sync_digest_jobs", "post_team_quiz", "reveal_team_quiz"):
        assert ctx.tools[name]["toolset"] == "learning"

    assert list(ctx.hooks) == ["pre_gateway_dispatch"]
    assert len(ctx.hooks["pre_gateway_dispatch"]) == 1
    assert callable(ctx.hooks["pre_gateway_dispatch"][0])

    assert "kata-item-rendering" in ctx.prompt_sections
    assert "kata-team-quiz-commands" in ctx.prompt_sections

    # register() returns the live TeamQuizState so a test (or anything else
    # that needs it) can reach the same tally the registered tools use.
    assert quiz_state.tally is not None
