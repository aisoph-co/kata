"""§1 contract test: the generated Hermes tool set equals `tools.json`
exactly — the catalog is the whole surface, not a floor."""
from conftest import FakePluginContext

from hermes_kata.catalog import load_tool_catalog, register_tools


def test_registered_tools_match_catalog_exactly():
    catalog = load_tool_catalog()
    ctx = FakePluginContext()

    registered = register_tools(ctx, client=None, catalog=catalog)

    assert set(registered) == {tool.name for tool in catalog}
    assert set(ctx.tools) == {tool.name for tool in catalog}
    for tool in catalog:
        entry = ctx.tools[tool.name]
        assert entry["toolset"] == "learning"
        assert entry["schema"] == tool.parameters
        assert entry["description"] == tool.description


def test_no_other_tool_registered_under_the_learning_toolset():
    catalog = load_tool_catalog()
    ctx = FakePluginContext()

    register_tools(ctx, client=None, catalog=catalog)

    learning_tools = {name for name, entry in ctx.tools.items() if entry["toolset"] == "learning"}
    assert learning_tools == {tool.name for tool in catalog}
