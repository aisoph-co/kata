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

    hermes_kata.register(ctx)

    catalog = load_tool_catalog()
    assert set(ctx.tools) == {tool.name for tool in catalog}

    assert list(ctx.hooks) == ["pre_gateway_dispatch"]
    assert len(ctx.hooks["pre_gateway_dispatch"]) == 1
    assert callable(ctx.hooks["pre_gateway_dispatch"][0])

    assert "kata-item-rendering" in ctx.prompt_sections
